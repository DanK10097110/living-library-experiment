"""Figures and an HTML report for study runs. Works on partial runs at any time.

usage: python tools/plots.py RUN_DIR [RUN_DIR ...] [--out DIR] [--window 25] [--boot 2000]

Reads the committed checkpoints of every stream in each run directory and writes PNG figures plus
report.html (figures embedded) to --out (default: <first run dir>/figures). Needs matplotlib and numpy.
Read-only on run data.

Figures:
  practice_curves     rolling task success over practice episodes (D, E, E-minus; one line per replicate)
  manual_growth       rule manual size over practice (visible rules, hidden notes, anti-patterns)
  eval_success        evaluation task success per condition (replicates pooled), task-clustered bootstrap 95% CI
  eval_differences    paired differences for H1 (E-D), H3 (E-E-minus), E-C, C-A
  practice_length     frozen libraries after N practice games on fixed ID/OOD subsets
  cost                model calls, weighted tokens (in + 4 x out) and model seconds per task
  cost_cumulative     cumulative weighted tokens incl. the replicate's practice, E vs D (H2 view)
  failure_modes       most common planner/actor error categories per condition
"""
import argparse
import base64
import collections
import html
import io
import json
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

COLORS = {'A': '#8c8c8c', 'C': '#4e79a7', 'D': '#f28e2b', 'E': '#e15759', 'E-minus': '#76b7b2'}
ORDER = ['A', 'C', 'D', 'E', 'E-minus']
LABEL = {'A': 'A flat', 'C': 'C hierarchy', 'D': 'D trajectories', 'E': 'E managed manual',
         'E-minus': 'E− append-only manual'}
PHASES = {'evaluation': 'out-of-distribution (unseen rooms)', 'id-evaluation': 'in-distribution (seen rooms)'}
HIDDEN = ('Unresolved Error', 'Failure Pool')
ANTI = 'Anti-Pattern'


# -- loading ---------------------------------------------------------------------------
def load_run(run):
    """{stream key: {'spec', 'total', 'records', 'history' (rules after every practice game), 'run'}}"""
    run = Path(run)
    plan = json.loads((run / 'plan.json').read_text()) if (run / 'plan.json').exists() else []
    streams = {}
    for spec in plan:
        directory = run / 'checkpoints' / spec['key']
        records, n, history = [], 0, []
        keep_history = spec['phase'] == 'practice' and spec['condition'] in ('E', 'E-minus')
        while (directory / f'{n:05d}.json').exists():
            saved = json.loads((directory / f'{n:05d}.json').read_text())
            records.append(saved['record'])
            if keep_history:
                history.append(saved['memory']['rules'])
            n += 1
        streams[spec['key']] = {'spec': {k: v for k, v in spec.items() if k != 'tasks'},
                                'total': len(spec['tasks']), 'records': records, 'history': history,
                                'run': run.name}
    return streams


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
    """Success per task averaged over seeds and replicates: {task_id: mean}."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r['task_id']].append(float(r['success']))
    return {t: float(np.mean(v)) for t, v in by.items()}


def replicate_label(s):
    rep = s['spec'].get('replicate')
    return '' if rep is None else f' r{rep}'


# -- figures ---------------------------------------------------------------------------
def fig_practice_curves(streams, window):
    practice = {k: s for k, s in streams.items() if s['spec']['phase'] == 'practice' and s['records']}
    if not practice:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    styles = ['-', '--', ':', '-.']
    for key, s in sorted(practice.items()):
        c = s['spec']['condition']
        y = rolling([r['success'] for r in s['records']], window)
        ls = styles[(s['spec'].get('replicate') or 0) % len(styles)]
        ax.plot(np.arange(1, len(y) + 1), y, ls, color=COLORS.get(c), lw=2,
                label=f"{LABEL.get(c, c)}{replicate_label(s)} ({s['run']}, {len(y)}/{s['total']})")
    ax.set(xlabel='practice episode', ylabel=f'success (rolling {window})', ylim=(0, 1),
           title='Practice: first-attempt task success as the memory grows')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def fig_manual_growth(streams, milestones):
    libs = {k: s for k, s in streams.items() if s['history']}
    if not libs:
        return None
    fig, axes = plt.subplots(1, len(libs), figsize=(6 * len(libs), 4.2), squeeze=False, sharey=True)
    for ax, (key, s) in zip(axes[0], sorted(libs.items())):
        x = np.arange(1, len(s['history']) + 1)
        series = {
            'visible rules': [sum(r['type'] not in HIDDEN and not r.get('hidden') for r in h) for h in s['history']],
            'hidden notes': [sum(r['type'] == 'Unresolved Error' or bool(r.get('hidden')) for r in h)
                             for h in s['history']],
            'anti-patterns': [sum(r['type'] == ANTI for r in h) for h in s['history']],
        }
        for (name, y), style in zip(series.items(), ['-', ':', '--']):
            ax.plot(x, y, style, lw=2, label=name)
        for m in milestones:
            if m <= len(x):
                ax.axvline(m, color='grey', lw=.6, alpha=.6)
        ax.set(xlabel='practice episode (grey lines: saved snapshots)', title=f"{key} ({s['run']})")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    axes[0][0].set_ylabel('rules')
    fig.suptitle('Rule manual size over practice')
    fig.tight_layout()
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
        tasks = per_task_success(groups[c])
        mean, lo, hi = bootstrap_ci(list(tasks.values()), samples, rng)
        summary.setdefault(phase, {})[c] = {'success': mean, 'ci95': [lo, hi], 'episodes': len(groups[c]),
                                            'tasks': len(tasks)}
        ax.bar(i, mean, color=COLORS[c], yerr=[[mean - lo], [hi - mean]], capsize=5)
        ax.text(i, hi + .02, f'{mean:.0%}\nn={len(groups[c])}', ha='center', fontsize=8)
    ax.set_xticks(range(len(conds)), [LABEL[c] for c in conds], rotation=15)
    ax.set(ylabel='task success (seed and replicate mean)', ylim=(0, 1.1),
           title=f'Evaluation, {PHASES[phase]} (task-clustered bootstrap 95% CI)')
    ax.grid(axis='y', alpha=.3)
    return fig


def fig_eval_differences(groups, samples, rng, summary, phase='evaluation'):
    pairs = [('H1  E − D', 'E', 'D'), ('H3  E − E−', 'E', 'E-minus'), ('E − C (memory)', 'E', 'C'),
             ('C − A (hierarchy)', 'C', 'A')]
    rows = []
    for name, left, right in pairs:
        if not groups.get(left) or not groups.get(right):
            continue
        pa, pb = per_task_success(groups[left]), per_task_success(groups[right])
        tasks = sorted(set(pa) & set(pb))
        diffs = [pa[t] - pb[t] for t in tasks]
        if not diffs:
            continue
        mean, lo, hi = bootstrap_ci(diffs, samples, rng)
        rows.append((name, mean, lo, hi, len(tasks)))
        summary.setdefault(f'differences {phase}', {})[name] = {'estimate': mean, 'ci95': [lo, hi],
                                                               'paired_tasks': len(tasks)}
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
           title=f'Paired comparisons, {PHASES[phase]} (task bootstrap, unadjusted; replicates pooled)')
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(axis='x', alpha=.3)
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
    def practice_cost(c, replicate):
        return sum(weighted_tokens(r) for s in streams.values() if s['spec']['phase'] == 'practice'
                   and s['spec']['condition'] == c and s['spec'].get('replicate') == replicate for r in s['records'])
    ev = {k: s for k, s in streams.items() if s['spec']['phase'] == 'evaluation'
          and s['spec']['condition'] in ('D', 'E') and s['records']}
    if not ev:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    styles = ['-', '--', ':', '-.']
    for key, s in sorted(ev.items()):
        c, rep = s['spec']['condition'], s['spec'].get('replicate')
        y = practice_cost(c, rep) + np.cumsum([weighted_tokens(r) for r in s['records']])
        ax.plot(np.arange(1, len(y) + 1), y / 1e6, color=COLORS[c], lw=2, ls=styles[(rep or 0) % len(styles)],
                label=key)
    ax.set(xlabel='evaluation task', ylabel='cumulative weighted tokens (M), incl. practice',
           title='Amortized cost: E vs D per replicate (H2 view; crossing = break-even)')
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    return fig


def fig_practice_length(streams, samples, rng, summary):
    """Marginal value of practice: frozen libraries after N practice episodes, ID vs OOD (replicates pooled)."""
    points = collections.defaultdict(lambda: collections.defaultdict(list))   # (condition, subset) -> N -> rows
    tasks = {}
    for s in streams.values():
        phase = s['spec']['phase']
        if phase.startswith('snapshot-') and s['records']:
            _, n, subset = phase.split('-')
            points[(s['spec']['condition'], subset)][int(n)] += s['records']
            tasks[subset] = {r['task_id'] for r in s['records']} | tasks.get(subset, set())
    if not points:
        return None
    # Final point = the main (frozen) evaluation of the full practice library, on the same games.
    for (condition, subset) in list(points):
        phase = 'evaluation' if subset == 'ood' else 'id-evaluation'
        practice = next((p for p in streams.values() if p['spec']['phase'] == 'practice'
                         and p['spec']['condition'] == condition), None)
        rows = [r for s in streams.values() if s['spec']['phase'] == phase and s['spec']['condition'] == condition
                for r in s['records'] if r['task_id'] in tasks.get(subset, ())]
        if practice and rows:
            points[(condition, subset)][practice['total']] += rows
    # Practice 0 = the no-memory baseline C on the same games (its first evaluation seed).
    base = {}
    for subset, phase in (('ood', 'evaluation'), ('id', 'id-evaluation')):
        rows = [r for s in streams.values() if s['spec']['phase'] == phase and s['spec']['condition'] == 'C'
                for r in s['records'] if r['task_id'] in tasks.get(subset, ())]
        seed = min((r['seed'] for r in rows), default=None)
        base[subset] = [r for r in rows if r['seed'] == seed]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, subset in zip(axes, ('id', 'ood')):
        for (condition, sub), by_n in sorted(points.items()):
            if sub != subset:
                continue
            series = ([(0, base[subset])] if base[subset] else []) + sorted(by_n.items())
            xs, ms, los, his = [], [], [], []
            for n, rows in series:
                m, lo, hi = bootstrap_ci(list(per_task_success(rows).values()), samples, rng)
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


# -- library over time ------------------------------------------------------------------
def milestones_of(run_dirs):
    for run in run_dirs:
        path = Path(run) / 'settings.json'
        if path.exists():
            found = json.loads(path.read_text()).get('library_milestones') or []
            if found:
                return sorted(found)
    return []


def export_snapshots(streams, milestones, out):
    """The rule manual at each milestone, one JSON file each, for any later analysis."""
    written = 0
    for key, s in streams.items():
        for m in milestones:
            if s['history'] and m <= len(s['history']):
                path = out / 'libraries' / key / f'after-{m:03d}-episodes.json'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(s['history'][m - 1], indent=1))
                written += 1
    return written


# -- report ----------------------------------------------------------------------------
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
        ('practice_curves', lambda: fig_practice_curves(streams, a.window)),
        ('manual_growth', lambda: fig_manual_growth(streams, milestones)),
        ('eval_success', lambda: fig_eval_success(groups, a.boot, rng, summary)),
        ('eval_differences', lambda: fig_eval_differences(groups, a.boot, rng, summary)),
        ('eval_success_in_distribution', lambda: fig_eval_success(id_groups, a.boot, rng, summary, 'id-evaluation')),
        ('eval_differences_in_distribution', lambda: fig_eval_differences(id_groups, a.boot, rng, summary, 'id-evaluation')),
        ('practice_length', lambda: fig_practice_length(streams, a.boot, rng, summary)),
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
td,th{{border:1px solid #ddd;padding:3px 6px;vertical-align:top}}
.note{{background:#fff7e0;padding:8px 12px;border-left:4px solid #f2b134}}</style></head><body>
<h1>Living library: run report</h1><p>Runs: {html.escape(', '.join(a.runs))}</p>
<p class="note">Partial runs are plotted as they stand; confidence intervals are unadjusted, task-clustered
percentile bootstraps with replicates pooled (the preregistered hierarchical analysis with Holm correction is
<code>living_library analyze</code>). GPU-seconds are not measured by the current server setup, so cost is shown
as calls, weighted tokens and model seconds.</p>
<h2>progress</h2>{progress_table(streams)}
{''.join(sections)}
</body></html>"""
    (out / 'report.html').write_text(page, encoding='utf-8')
    print('wrote', out / 'report.html')


if __name__ == '__main__':
    main()
