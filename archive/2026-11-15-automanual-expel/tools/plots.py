"""Figures and an HTML report for pilot and study runs. Works on partial runs at any time.

usage: python tools/plots.py RUN_DIR [RUN_DIR ...] [--out DIR] [--window 25] [--boot 2000]

Reads the committed checkpoints of every stream in each run directory (pilot and/or study) and
writes PNG figures plus report.html (figures embedded, skill tables included) to --out
(default: <first run dir>/figures). Needs matplotlib and numpy. Read-only on run data.

Figures:
  practice_curves     rolling task success over practice episodes (D, E, E-minus)
  library_growth      active library size, and accepted / rejected / duplicate skill candidates
  skill_invocations   cumulative skill-invocation success, E vs E-minus (H3's unit)
  eval_success        evaluation task success per condition, task-clustered bootstrap 95% CI
  eval_differences    paired differences for H1 (E-D), H3 task success (E-E-minus), H4 (E-E-text), E-C
  eval_curves         cumulative evaluation success by position (libraries keep updating)
  cost                model calls, weighted tokens (in + 4 x out) and model seconds per task
  cost_cumulative     cumulative weighted tokens incl. practice, E vs D (break-even view for H2)
  skill_usage         most-used skills: successful vs failed invocations
  failure_modes       most common program/planner error categories per condition
  pilot_gates         pilot gate values vs thresholds (pilot run only)
"""
import argparse
import base64
import collections
import html
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {'A': '#8c8c8c', 'B': '#b07aa1', 'C': '#4e79a7', 'D': '#f28e2b', 'E': '#e15759',
          'E-minus': '#76b7b2', 'E-text': '#59a14f', 'E-plus': '#9c27b0'}
ORDER = ['A', 'B', 'C', 'D', 'E', 'E-minus', 'E-text', 'E-plus']
LABEL = {'A': 'A flat', 'B': 'B flat+lib', 'C': 'C hierarchy', 'D': 'D trajectories', 'E': 'E full',
         'E-minus': 'E− append-only', 'E-text': 'E-text', 'E-plus': 'E+ consolidated'}
PHASES = {'evaluation': 'out-of-distribution (unseen rooms)', 'id-evaluation': 'in-distribution (seen rooms)'}


# -- loading ---------------------------------------------------------------------------
def load_run(run):
    """{stream key: {'spec': spec, 'records': [...], 'library': final library snapshot}}"""
    run = Path(run)
    plan = json.loads((run / 'plan.json').read_text()) if (run / 'plan.json').exists() else []
    streams = {}
    for spec in plan:
        directory = run / 'checkpoints' / spec['key']
        records, library, n, history = [], None, 0, []
        keep_history = spec['phase'] == 'practice'
        while (directory / f'{n:05d}.json').exists():
            saved = json.loads((directory / f'{n:05d}.json').read_text())
            records.append(saved['record'])
            library = saved['memory']['library']
            if keep_history:            # the library after every practice episode
                history.append(library)
            n += 1
        streams[spec['key']] = {'spec': {k: v for k, v in spec.items() if k != 'tasks'},
                                'total': len(spec['tasks']), 'records': records, 'library': library,
                                'history': history, 'run': run.name}
    return streams


def eligible_calls(records):
    return [c for r in records for c in r.get('invocations', []) if c.get('preconditions_held')]


def rolling(values, window):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return values
    c = np.cumsum(np.insert(values, 0, 0))
    out = np.empty(len(values))
    for i in range(len(values)):
        lo = max(0, i + 1 - window)
        out[i] = (c[i + 1] - c[lo]) / (i + 1 - lo)
    return out


def weighted_tokens(r):
    return (r.get('input_tokens') or 0) + 4 * (r.get('output_tokens') or 0)


def bootstrap_ci(per_task, samples, rng):
    """Mean and percentile 95% CI over task clusters (per_task: array of per-task values)."""
    x = np.asarray(per_task, dtype=float)
    if len(x) == 0:
        return None, None, None
    idx = rng.integers(0, len(x), size=(samples, len(x)))
    means = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def per_task_success(rows):
    """Seed-averaged success per task: {task_id: mean}."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r['task_id']].append(float(r['success']))
    return {t: float(np.mean(v)) for t, v in by.items()}


# -- figures ---------------------------------------------------------------------------
def fig_practice_curves(streams, window):
    practice = {k: s for k, s in streams.items() if s['spec']['phase'] == 'practice' and s['records']}
    if not practice:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for key, s in sorted(practice.items()):
        c = s['spec']['condition']
        y = rolling([r['success'] for r in s['records']], window)
        ls = '--' if s['run'].startswith('pilot') else '-'
        ax.plot(np.arange(1, len(y) + 1), y, ls, color=COLORS.get(c), lw=2,
                label=f"{LABEL.get(c, c)} ({s['run']}, {len(y)}/{s['total']})")
    ax.set(xlabel='practice episode', ylabel=f'success (rolling {window})', ylim=(0, 1),
           title='Practice: task success as the memory grows')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def fig_library_growth(streams):
    lib = {k: s for k, s in streams.items() if s['spec']['condition'] in ('B', 'E', 'E-minus')
           and s['spec']['phase'] in ('practice', 'development') and s['records']}
    if not lib:
        return None
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for key, s in sorted(lib.items()):
        c, rs = s['spec']['condition'], s['records']
        x = np.arange(1, len(rs) + 1)
        ls = '-' if s['spec']['phase'] == 'practice' else ':'
        a1.plot(x, [r.get('library_size', 0) for r in rs], ls, color=COLORS.get(c), lw=2, label=f'{key} ({s["run"]})')
        # candidate_attempts already excludes duplicate-name candidates (agents.py).
        attempts = np.cumsum([r.get('candidate_attempts', 0) for r in rs])
        rejected = np.cumsum([r.get('candidate_rejections', 0) for r in rs])
        dupes = np.cumsum([r.get('candidate_duplicates', 0) for r in rs])
        if s['spec']['phase'] == 'practice':
            a2.plot(x, attempts - rejected, '-', color=COLORS.get(c), lw=2, label=f'{key} accepted')
            a2.plot(x, rejected, '--', color=COLORS.get(c), lw=1.5, label=f'{key} rejected')
            a2.plot(x, dupes, ':', color=COLORS.get(c), lw=1.5, label=f'{key} duplicate name')
    a1.set(xlabel='episode', ylabel='active skills', title='Library size')
    a2.set(xlabel='practice episode', ylabel='cumulative candidates', title='Skill admission')
    for a in (a1, a2):
        a.grid(alpha=.3)
        a.legend(fontsize=7)
    return fig


def fig_skill_invocations(streams):
    rows = {k: s for k, s in streams.items() if s['spec']['condition'] in ('B', 'E', 'E-minus') and s['records']}
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    any_line = False
    for key, s in sorted(rows.items()):
        calls = eligible_calls(s['records'])
        if not calls:
            continue
        y = np.cumsum([c['success'] for c in calls]) / np.arange(1, len(calls) + 1)
        ls = '-' if s['spec']['phase'] == 'practice' else ':'
        ax.plot(np.arange(1, len(y) + 1), y, ls, color=COLORS.get(s['spec']['condition']), lw=2,
                label=f"{key} ({s['run']}): {int(sum(c['success'] for c in calls))}/{len(calls)}")
        any_line = True
    if not any_line:
        plt.close(fig)
        return None
    ax.set(xlabel='skill invocation (preconditions held)', ylabel='cumulative success rate', ylim=(0, 1),
           title='Skill-invocation success (H3 unit): updating E vs append-only E−')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def eval_groups(streams, phase='evaluation'):
    groups = collections.defaultdict(list)
    for s in streams.values():
        if s['spec']['phase'] == phase:
            groups[s['spec']['condition']] += s['records']
    return groups


def fig_eval_success(groups, samples, rng, summary, phase='evaluation'):
    conds = [c for c in ORDER if groups.get(c)]
    if not conds:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, c in enumerate(conds):
        mean, lo, hi = bootstrap_ci(list(per_task_success(groups[c]).values()), samples, rng)
        summary.setdefault(phase, {})[c] = {'success': mean, 'ci95': [lo, hi], 'episodes': len(groups[c]),
                                                   'tasks': len(per_task_success(groups[c]))}
        ax.bar(i, mean, color=COLORS[c], yerr=[[mean - lo], [hi - mean]], capsize=5)
        ax.text(i, hi + .02, f'{mean:.0%}\nn={len(groups[c])}', ha='center', fontsize=8)
    ax.set_xticks(range(len(conds)), [LABEL[c] for c in conds], rotation=15)
    ax.set(ylabel='task success (seed-averaged)', ylim=(0, 1.1),
           title=f'Evaluation, {PHASES[phase]} (task-clustered bootstrap 95% CI)')
    ax.grid(axis='y', alpha=.3)
    return fig


def fig_eval_differences(groups, samples, rng, summary, phase='evaluation'):
    pairs = [('H1  E − D', 'E', 'D'), ('H4  E − E-text', 'E', 'E-text'),
             ('H3 (task)  E − E−', 'E', 'E-minus'), ('E − C (memory)', 'E', 'C'), ('C − A (hierarchy)', 'C', 'A'),
             ('E+ − E (consolidation)', 'E-plus', 'E')]
    rows = []
    for name, left, right in pairs:
        if not groups.get(left) or not groups.get(right):
            continue
        a = {(r['task_id'], r['seed']): r['success'] for r in groups[left]}
        b = {(r['task_id'], r['seed']): r['success'] for r in groups[right]}
        if right == 'A' or left == 'A':
            # A has one seed: compare per task means.
            pa, pb = per_task_success(groups[left]), per_task_success(groups[right])
            tasks = sorted(set(pa) & set(pb))
            diffs = [pa[t] - pb[t] for t in tasks]
        else:
            shared = set(a) & set(b)
            by = collections.defaultdict(list)
            for t, s in shared:
                by[t].append(float(a[t, s]) - float(b[t, s]))
            tasks = sorted(by)
            diffs = [np.mean(by[t]) for t in tasks]
        if not diffs:
            continue
        mean, lo, hi = bootstrap_ci(diffs, samples, rng)
        rows.append((name, mean, lo, hi, len(tasks)))
        summary.setdefault(f'differences {phase}', {})[name] = {'estimate': mean, 'ci95': [lo, hi], 'paired_tasks': len(tasks)}
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8, 0.7 * len(rows) + 1.5))
    for i, (name, mean, lo, hi, n) in enumerate(rows):
        ax.errorbar(mean, i, xerr=[[mean - lo], [hi - mean]], fmt='o', color='k', capsize=5)
        ax.text(hi + .01, i, f' {mean:+.1%} [{lo:+.1%}, {hi:+.1%}]  tasks={n}', va='center', fontsize=8)
    ax.axvline(0, color='grey', lw=1)
    ax.axvline(.10, color='#e15759', lw=1, ls='--', label='+10 pt success criterion')
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set(xlabel='paired difference in task success', xlim=(-0.6, 0.9),
           title=f'Paired comparisons, {PHASES[phase]} (bootstrap 95% CI, unadjusted)')
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(axis='x', alpha=.3)
    return fig


def fig_eval_curves(streams, phase='evaluation'):
    ev = {k: s for k, s in streams.items() if s['spec']['phase'] == phase and s['records']}
    if not ev:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    by_cond = collections.defaultdict(list)
    for s in ev.values():
        by_cond[s['spec']['condition']].append([r['success'] for r in s['records']])
    for c in ORDER:
        if c not in by_cond:
            continue
        n = min(len(x) for x in by_cond[c])
        y = np.mean([np.cumsum(x[:n]) / np.arange(1, n + 1) for x in by_cond[c]], axis=0)
        ax.plot(np.arange(1, n + 1), y, color=COLORS[c], lw=2, label=f'{LABEL[c]} ({len(by_cond[c])} seeds)')
    ax.set(xlabel='evaluation task (in run order)', ylabel='cumulative success', ylim=(0, 1),
           title=f'Learning curves, {PHASES[phase]} (libraries keep updating)')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def fig_cost(groups, summary):
    conds = [c for c in ORDER if groups.get(c)]
    if not conds:
        return None
    metrics = [('model calls / task', lambda r: r.get('model_calls', 0)),
               ('weighted tokens / task (in + 4×out)', weighted_tokens),
               ('model seconds / task', lambda r: r.get('model_wall_seconds') or 0)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, (name, f) in zip(axes, metrics):
        means = [np.mean([f(r) for r in groups[c]]) for c in conds]
        ax.bar(range(len(conds)), means, color=[COLORS[c] for c in conds])
        ax.set_xticks(range(len(conds)), conds)
        ax.set_title(name, fontsize=10)
        ax.grid(axis='y', alpha=.3)
        for c, m in zip(conds, means):
            summary.setdefault('cost', {}).setdefault(c, {})[name] = float(m)
    fig.suptitle('Evaluation cost per task (GPU-seconds are not measured; see report notes)')
    return fig


def fig_cost_cumulative(streams):
    def practice_cost(c):
        return sum(weighted_tokens(r) for s in streams.values() if s['spec']['phase'] == 'practice'
                   and s['spec']['condition'] == c for r in s['records'])
    ev = {k: s for k, s in streams.items() if s['spec']['phase'] == 'evaluation'
          and s['spec']['condition'] in ('D', 'E') and s['records']}
    if not ev:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for key, s in sorted(ev.items()):
        c = s['spec']['condition']
        y = practice_cost(c) + np.cumsum([weighted_tokens(r) for r in s['records']])
        ax.plot(np.arange(1, len(y) + 1), y / 1e6, color=COLORS[c], lw=2,
                ls='-' if s['spec']['seed'] == min(x['spec']['seed'] for x in ev.values()) else '--', label=key)
    ax.set(xlabel='evaluation task', ylabel='cumulative weighted tokens (M), incl. practice',
           title='Amortized cost: E vs D (H2 view; crossing = break-even)')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def fig_practice_length(streams, samples, rng, summary):
    """Marginal value of practice: frozen libraries after N practice episodes, ID vs OOD."""
    points = collections.defaultdict(list)          # (condition, subset) -> [(N, records)]
    tasks = {}
    for s in streams.values():
        phase = s['spec']['phase']
        if phase.startswith('snapshot-') and s['records']:
            _, n, subset = phase.split('-')
            points[(s['spec']['condition'], subset)].append((int(n), s['records']))
            tasks[subset] = {r['task_id'] for r in s['records']} | tasks.get(subset, set())
    if not points:
        return None
    # Final point = the main (frozen) evaluation of the full practice library, on the same games.
    for (condition, subset) in list(points):
        phase = 'evaluation' if subset == 'ood' else 'id-evaluation'
        for s in streams.values():
            if s['spec']['phase'] == phase and s['spec']['condition'] == condition and s['records']:
                practice = next((p for p in streams.values() if p['spec']['phase'] == 'practice'
                                 and p['spec']['condition'] == condition), None)
                rows = [r for r in s['records'] if r['task_id'] in tasks.get(subset, ())]
                if practice and rows:
                    points[(condition, subset)].append((practice['total'], rows))
    # Practice 0 = the no-memory baseline C on the same games (its first evaluation seed).
    base = {}
    for subset, phase in (('ood', 'evaluation'), ('id', 'id-evaluation')):
        rows = [r for s in streams.values() if s['spec']['phase'] == phase and s['spec']['condition'] == 'C'
                for r in s['records'] if r['task_id'] in tasks.get(subset, ())]
        seed = min((r['seed'] for r in rows), default=None)
        base[subset] = [r for r in rows if r['seed'] == seed]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, subset in zip(axes, ('id', 'ood')):
        for (condition, sub), series in sorted(points.items()):
            if sub != subset:
                continue
            series = sorted(series) if not base[subset] else [(0, base[subset])] + sorted(series)
            xs, ms, los, his = [], [], [], []
            for n, rows in series:
                m, lo, hi = bootstrap_ci([float(r['success']) for r in rows], samples, rng)
                xs.append(n); ms.append(m); los.append(m - lo); his.append(hi - m)
                summary.setdefault('practice_length', {}).setdefault(f'{condition} {subset}', {})[n] = {
                    'success': m, 'ci95': [lo, hi], 'games': len(rows)}
            ax.errorbar(xs, ms, yerr=[los, his], color=COLORS.get(condition), marker='o', capsize=4,
                        lw=2, label=LABEL.get(condition, condition))
        ax.set(xlabel='practice episodes before the library was frozen (0 = no memory, C)',
               title=PHASES['id-evaluation' if subset == 'id' else 'evaluation'], ylim=(0, 1))
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    axes[0].set_ylabel('task success on a fixed game subset')
    fig.suptitle('Marginal value of practice: does a bigger library keep helping?')
    fig.tight_layout()
    return fig


# -- library over time ------------------------------------------------------------------
def milestones_of(run_dirs):
    for run in run_dirs:
        path = Path(run) / 'settings.json'
        if path.exists():
            found = json.loads(path.read_text()).get('library_milestones') or []
            if found:
                return sorted(found)
    return []


def library_streams(streams):
    return {k: s for k, s in streams.items() if s['history'] and any(lib.get('skills') for lib in s['history'])}


def is_meta(sid):
    return '_then_' in sid.split('@')[0]


def fig_library_over_time(streams, milestones):
    libs = library_streams(streams)
    if not libs:
        return None
    fig, axes = plt.subplots(1, len(libs), figsize=(6.5 * len(libs), 4.5), squeeze=False)
    for ax, (key, s) in zip(axes[0], sorted(libs.items())):
        x = np.arange(1, len(s['history']) + 1)
        series = {
            'active skills': [len(l['active']) for l in s['history']],
            'versions written (incl. rejected)': [len(l['skills']) for l in s['history']],
            'retired (consolidation)': [len(l.get('meta', {}).get('retired', {})) for l in s['history']],
            'meta-skills (active)': [sum(is_meta(sid) for sid in l['active'].values()) for l in s['history']],
            'lessons': [len(l.get('meta', {}).get('lessons', [])) for l in s['history']],
        }
        for (name, y), style in zip(series.items(), ['-', ':', '--', '-.', '-']):
            if any(y):
                ax.plot(x, y, style, lw=2, label=name)
        for m in milestones:
            if m <= len(x):
                ax.axvline(m, color='grey', lw=.6, alpha=.6)
        ax.set(xlabel='practice episode (grey lines: saved library snapshots)', ylabel='count',
               title=f"{key} ({s['run']})")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.suptitle('How the library grows, consolidates and learns lessons over practice')
    fig.tight_layout()
    return fig


def fig_skill_heatmap(streams, milestones, top=30):
    """Successful uses of each skill per practice window between snapshots (rows: skills)."""
    libs = library_streams(streams)
    if not libs or not milestones:
        return None
    fig, axes = plt.subplots(1, len(libs), figsize=(7 * len(libs), 8), squeeze=False)
    edges = [0] + milestones
    for ax, (key, s) in zip(axes[0], sorted(libs.items())):
        counts = collections.defaultdict(lambda: np.zeros(len(milestones)))
        for position, r in enumerate(s['records']):
            window = next((i for i, m in enumerate(milestones) if position < m), None)
            if window is None:
                continue
            for c in r.get('invocations', []):
                if c.get('preconditions_held') and c.get('success'):
                    counts[c['skill_id']][window] += 1
        if not counts:
            ax.set_visible(False)
            continue
        names = sorted(counts, key=lambda k: -counts[k].sum())[:top]
        grid = np.array([counts[n] for n in names])
        image = ax.imshow(grid, aspect='auto', cmap='viridis')
        final = s['history'][-1]
        labels = [f"{n}{' (retired)' if final['skills'] and next((k for k in final['skills'] if k['id'] == n), {}).get('status') == 'retired' else ''}"
                  for n in names]
        ax.set_yticks(range(len(names)), labels, fontsize=7)
        ax.set_xticks(range(len(milestones)), [f'{a + 1}-{b}' for a, b in zip(edges, milestones)], rotation=45, fontsize=7)
        ax.set(xlabel='practice episodes', title=f'{key}: successful uses per window')
        fig.colorbar(image, ax=ax, shrink=.6)
    fig.tight_layout()
    return fig


def fig_skill_turnover(streams, milestones):
    """Per window: skills added, skills retired, and the share of episodes that used any skill."""
    libs = library_streams(streams)
    if not libs or not milestones:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    edges = [0] + milestones
    for key, s in sorted(libs.items()):
        c = s['spec']['condition']
        added, retired, used = [], [], []
        for a, b in zip(edges, milestones):
            if b > len(s['history']):
                break
            before = s['history'][a - 1] if a else {'skills': [], 'meta': {}}
            after = s['history'][b - 1]
            added.append(len(after['skills']) - len(before['skills']))
            retired.append(len(after.get('meta', {}).get('retired', {})) - len(before.get('meta', {}).get('retired', {})))
            window = s['records'][a:b]
            used.append(sum(bool(r.get('invocations')) for r in window) / max(1, len(window)))
        x = milestones[:len(added)]
        axes[0].plot(x, added, '-o', color=COLORS.get(c), label=f'{key} added')
        if any(retired):
            axes[0].plot(x, retired, '--x', color=COLORS.get(c), label=f'{key} retired')
        axes[1].plot(x, used, '-o', color=COLORS.get(c), label=key)
    axes[0].set(xlabel='practice episodes (end of window)', ylabel='skill versions', title='Library turnover per window')
    axes[1].set(xlabel='practice episodes (end of window)', ylabel='share of episodes', ylim=(0, 1),
                title='Episodes that used at least one skill')
    for ax in axes:
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def export_snapshots(streams, milestones, out):
    """The library at each milestone, one JSON file each, for any later analysis."""
    written = 0
    for key, s in library_streams(streams).items():
        for m in milestones:
            if m <= len(s['history']):
                path = out / 'libraries' / key / f'after-{m:03d}-episodes.json'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(s['history'][m - 1], indent=1))
                written += 1
    return written


def lessons_table(streams):
    rows = []
    for key, s in sorted(library_streams(streams).items()):
        for lesson in (s['history'][-1].get('meta', {}).get('lessons') or []):
            rows.append(f"<tr><td>{html.escape(key)}</td><td>{html.escape(lesson['applies_to'])}</td>"
                        f"<td>{lesson['score']:+d}</td><td>{lesson['shown']}</td><td>{html.escape(lesson['text'])}</td></tr>")
    if not rows:
        return ''
    return ('<h2>lessons (E+)</h2><table><tr><th>stream</th><th>applies to</th><th>score</th><th>shown</th>'
            '<th>lesson</th></tr>' + ''.join(rows) + '</table>')


def skill_usage(streams):
    """Per-skill invocation counts from the logs (append-only libraries keep no counters)."""
    usage = collections.defaultdict(lambda: collections.Counter())
    for key, s in streams.items():
        c = s['spec']['condition']
        for call in eligible_calls(s['records']):
            u = usage[(c, call['skill_id'])]
            u['ok' if call['success'] else 'fail'] += 1
    return usage


def fig_skill_usage(streams, top=25):
    usage = skill_usage(streams)
    if not usage:
        return None
    conds = [c for c in ('E', 'E-minus', 'B') if any(k[0] == c for k in usage)]
    fig, axes = plt.subplots(1, len(conds), figsize=(7 * len(conds), 7), squeeze=False)
    for ax, c in zip(axes[0], conds):
        items = sorted(((sid, u) for (cc, sid), u in usage.items() if cc == c),
                       key=lambda x: -(x[1]['ok'] + x[1]['fail']))[:top][::-1]
        names = [sid for sid, _ in items]
        ok = [u['ok'] for _, u in items]
        fail = [u['fail'] for _, u in items]
        ax.barh(names, ok, color='#59a14f', label='succeeded')
        ax.barh(names, fail, left=ok, color='#e15759', label='failed')
        ax.set(xlabel='invocations (preconditions held)', title=f'{LABEL.get(c, c)}: top {len(items)} skills')
        ax.tick_params(axis='y', labelsize=7)
        ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def error_category(e):
    e = re.sub(r'\d+', 'N', e)
    return e.split(':')[0][:40] + ': ' + e.split(':', 1)[-1].strip()[:50] if ':' in e else e[:80]


def fig_failure_modes(streams, top=8):
    by = collections.defaultdict(collections.Counter)
    for s in streams.values():
        for r in s['records']:
            by[s['spec']['condition']].update(error_category(e) for e in r.get('program_errors', []))
    conds = [c for c in ORDER if by.get(c)]
    if not conds:
        return None
    fig, axes = plt.subplots(len(conds), 1, figsize=(10, 2.2 * len(conds)), squeeze=False)
    for ax, c in zip(axes[:, 0], conds):
        items = by[c].most_common(top)[::-1]
        ax.barh([k for k, _ in items], [v for _, v in items], color=COLORS[c])
        ax.set_title(f'{LABEL[c]}: most common errors', fontsize=9)
        ax.tick_params(axis='y', labelsize=7)
    fig.tight_layout()
    return fig


def fig_pilot_gates(run_dirs, summary):
    for run in run_dirs:
        records_path = Path(run) / 'records.json'
        if not (Path(run) / 'workflow.json').exists():
            continue
        if json.loads((Path(run) / 'workflow.json').read_text()).get('workflow') != 'pilot':
            continue
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from living_library.analysis import pilot_report
        from living_library.config import Settings
        streams = load_run(run)
        recs = [r for s in streams.values() for r in s['records']]
        practice = [r for r in recs if r['phase'] == 'practice']
        dev = [r for r in recs if r['phase'] == 'development']
        settings = json.loads((Path(run) / 'settings.json').read_text())
        cfg = Settings(**settings)
        # Partial runs: compute gate values on what exists (the reuse gate needs all practice).
        report = pilot_report(practice, [r for r in dev if r['condition'] == 'C'],
                              [r for r in dev if r['condition'] == 'E-minus'], cfg)
        uses = collections.Counter(c['skill_id'] for c in eligible_calls(practice))
        gates = report['gates']
        gates['repeated_skills']['value_so_far'] = sum(n >= 5 for n in uses.values())
        summary['pilot_gates'] = gates
        names = {'baseline_ceiling': ('C success ≤ 85%', .85, False),
                 'library_ceiling': ('E− success ≤ 85%', .85, False),
                 'false_success': ('false success ≤ 10%', .10, False),
                 'program_failure': ('program failure ≤ 40%', .40, False),
                 'repeated_skills': ('skills used 5+ times ≥ 10', 10, True)}
        fig, axes = plt.subplots(1, 5, figsize=(15, 3.2))
        for ax, (gate, (title, threshold, higher_better)) in zip(axes, names.items()):
            g = gates.get(gate, {})
            v = g.get('value') if g.get('value') is not None else g.get('value_so_far')
            if v is None:
                ax.text(.5, .5, 'no data yet', ha='center', transform=ax.transAxes)
            else:
                ok = v >= threshold if higher_better else v <= threshold
                ax.bar([0], [v], color='#59a14f' if ok else '#e15759')
                ax.axhline(threshold, color='k', ls='--', lw=1)
                ax.text(0, v, f'{v:.2f}' if isinstance(v, float) else str(v), ha='center', va='bottom')
            ax.set_xticks([])
            ax.set_title(title + ('' if g.get('value') is not None else '\n(partial)'), fontsize=9)
        fig.suptitle(f'Pilot gates ({Path(run).name}, {len(practice)} practice / {len(dev)} development episodes)')
        fig.tight_layout()
        return fig
    return None


# -- report ----------------------------------------------------------------------------
def skill_table(streams):
    usage = skill_usage(streams)
    out = []
    for key, s in sorted(streams.items()):
        lib = s['library']
        if not lib or not lib['skills']:
            continue
        c = s['spec']['condition']
        active = set(lib['active'].values())
        rows = []
        for sk in sorted(lib['skills'], key=lambda sk: -sum(usage[(c, sk['id'])].values())):
            u = usage[(c, sk['id'])]
            n = u['ok'] + u['fail']
            rows.append(
                f"<tr><td><code>{html.escape(sk['id'])}</code></td><td>{'active' if sk['id'] in active else html.escape(sk['status'])}</td>"
                f"<td>{u['ok']}/{n}</td><td>{html.escape(', '.join(sk['parameters']))}</td>"
                f"<td>{html.escape('; '.join(sk['preconditions']))}</td><td>{html.escape('; '.join(sk['postconditions']))}</td>"
                f"<td>{html.escape(sk.get('parent') or '')}</td>"
                f"<td><details><summary>{html.escape(sk['description'][:80])}</summary><pre>{html.escape(sk['body'])}</pre></details></td></tr>")
        out.append(f"<h3>{html.escape(key)} <small>({html.escape(s['run'])}, after {len(s['records'])} episodes: "
                   f"{len(lib['skills'])} versions, {len(active)} active)</small></h3>"
                   "<table><tr><th>skill</th><th>status</th><th>ok/uses</th><th>params</th><th>pre</th>"
                   "<th>post</th><th>parent</th><th>description / body</th></tr>" + ''.join(rows) + '</table>')
    return '\n'.join(out)


def progress_table(streams):
    rows = ''.join(
        f"<tr><td>{html.escape(s['run'])}</td><td>{html.escape(k)}</td><td>{len(s['records'])}/{s['total']}</td>"
        f"<td>{(sum(r['success'] for r in s['records']) / len(s['records'])) if s['records'] else 0:.0%}</td></tr>"
        for k, s in sorted(streams.items(), key=lambda kv: (kv[1]['run'], kv[0])))
    return '<table><tr><th>run</th><th>stream</th><th>done</th><th>success</th></tr>' + rows + '</table>'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('runs', nargs='+')
    p.add_argument('--out')
    p.add_argument('--window', type=int, default=25)
    p.add_argument('--boot', type=int, default=2000)
    a = p.parse_args()
    out = Path(a.out or Path(a.runs[0]) / 'figures')
    out.mkdir(parents=True, exist_ok=True)
    streams = {}
    for run in a.runs:
        for k, s in load_run(run).items():
            streams[f"{Path(run).name}:{k}" if k in streams else k] = s
    rng = np.random.default_rng(0)
    # Library milestones from the run settings, else 8 evenly spaced points over the longest practice.
    longest = max((len(s['history']) for s in streams.values()), default=0)
    milestones = milestones_of(a.runs) or sorted({max(1, round(longest * k / 8)) for k in range(1, 9)} if longest else set())
    print('library snapshots written:', export_snapshots(streams, milestones, out))
    summary = {}
    groups = eval_groups(streams)
    id_groups = eval_groups(streams, 'id-evaluation')
    figures = [
        ('pilot_gates', lambda: fig_pilot_gates(a.runs, summary)),
        ('practice_curves', lambda: fig_practice_curves(streams, a.window)),
        ('library_growth', lambda: fig_library_growth(streams)),
        ('skill_invocations', lambda: fig_skill_invocations(streams)),
        ('skill_usage', lambda: fig_skill_usage(streams)),
        ('eval_success', lambda: fig_eval_success(groups, a.boot, rng, summary)),
        ('eval_differences', lambda: fig_eval_differences(groups, a.boot, rng, summary)),
        ('eval_curves', lambda: fig_eval_curves(streams)),
        ('eval_success_in_distribution', lambda: fig_eval_success(id_groups, a.boot, rng, summary, 'id-evaluation')),
        ('eval_differences_in_distribution', lambda: fig_eval_differences(id_groups, a.boot, rng, summary, 'id-evaluation')),
        ('eval_curves_in_distribution', lambda: fig_eval_curves(streams, 'id-evaluation')),
        ('practice_length', lambda: fig_practice_length(streams, a.boot, rng, summary)),
        ('library_over_time', lambda: fig_library_over_time(streams, milestones)),
        ('skill_heatmap', lambda: fig_skill_heatmap(streams, milestones)),
        ('skill_turnover', lambda: fig_skill_turnover(streams, milestones)),
        ('cost', lambda: fig_cost(groups, summary)),
        ('cost_cumulative', lambda: fig_cost_cumulative(streams)),
        ('failure_modes', lambda: fig_failure_modes(streams)),
    ]
    sections = []
    for name, make in figures:
        fig = make()
        if fig is None:
            continue
        fig.savefig(out / f'{name}.png', dpi=130, bbox_inches='tight')
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
        plt.close(fig)
        sections.append(f'<h2>{name.replace("_", " ")}</h2><img src="data:image/png;base64,'
                        f'{base64.b64encode(buf.getvalue()).decode()}">')
        print('wrote', out / f'{name}.png')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, default=float))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Living library report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:24px auto;padding:0 16px;color:#222}}
img{{max-width:100%}} table{{border-collapse:collapse;font-size:12px;margin:8px 0}}
td,th{{border:1px solid #ddd;padding:3px 6px;vertical-align:top}} pre{{white-space:pre-wrap;margin:4px 0}}
.note{{background:#fff7e0;padding:8px 12px;border-left:4px solid #f2b134}}</style></head><body>
<h1>Living skill library: run report</h1><p>Runs: {html.escape(', '.join(a.runs))}</p>
<p class="note">Partial runs are plotted as they stand; confidence intervals are unadjusted, task-clustered
percentile bootstraps (the preregistered analysis with Holm correction is <code>living_library analyze</code>).
GPU-seconds are not measured by the current server setup, so cost is shown as calls, weighted tokens and model
seconds.</p>
<h2>progress</h2>{progress_table(streams)}
{''.join(sections)}
{lessons_table(streams)}
<h2>skill libraries</h2>{skill_table(streams)}
</body></html>"""
    (out / 'report.html').write_text(page, encoding='utf-8')
    print('wrote', out / 'report.html')


if __name__ == '__main__':
    main()
