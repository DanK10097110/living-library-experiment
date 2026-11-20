"""Compare one E replicate's library over practice time (E@100, E@200, ..., final E@300) with C, on the study's
evaluation games.

usage: python tools/compare_snapshots.py STUDY_DIR SNAP_DIR [SNAP_DIR ...] [--replicate 0]
                                         [--output results/library/SNAPSHOT-EVAL.md]

SNAP_DIRs come from tools/snapshot_eval.py (those of other replicates are skipped). The final point is the study's
own frozen E evaluation of the replicate (only if finished); C is the study's C evaluation. Prints a table per split
(OOD = evaluation, ID = id-evaluation) and writes the same as markdown.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

SPLITS = {'ood': 'evaluation', 'id': 'id-evaluation'}
NAMES = {'ood': 'OOD (evaluation)', 'id': 'ID (id-evaluation)'}


def _load(path):
    return json.loads(Path(path).read_text())


def stream_results(root, key, total=None):
    """{task_id: bool win} of a stream's committed checkpoints; None if missing or (with total) unfinished."""
    d = Path(root) / 'checkpoints' / key
    files = sorted(d.glob('[0-9]*.json')) if d.exists() else []
    if not files or (total is not None and len(files) < total):
        return None
    return {r['task_id']: bool(r['success']) for r in (_load(f)['record'] for f in files)}


def collect(study, snaps, replicate=0):
    """-> (points, types): points[split] = ordered [(label, {task: win} | None)], types[split] = {task: task_type}."""
    study = Path(study)
    seed0 = _load(study / 'settings.json')['seeds'][0]
    plan = {s['key']: s for s in _load(study / 'plan.json')}
    n_final = len(list((study / 'checkpoints' / f'practice-E-{replicate}').glob('[0-9]*.json')))
    points, types = {}, {}
    for split, phase in SPLITS.items():
        e = [s for s in plan.values() if s['condition'] == 'E' and s['phase'] == phase and s['seed'] == seed0
             and s['replicate'] == replicate]
        c = [s for s in plan.values() if s['condition'] == 'C' and s['phase'] == phase and s['seed'] == seed0]
        if not e:
            continue
        total = len(e[0]['tasks'])
        types[split] = {t['id']: t.get('task_type', 'n/a') for t in e[0]['tasks']}
        rows = [('C', stream_results(study, c[0]['key'], total) if c else None)]
        found = []
        for sd in snaps:
            meta = _load(Path(sd) / 'snapshot-meta.json')
            if split in meta['splits'] and meta.get('replicate', 0) == replicate:
                found.append((meta['at'], stream_results(sd, meta['streams'][split], meta['games'][split])))
        rows += [(f'E@{at}', res) for at, res in sorted(found, key=lambda x: x[0])]
        rows.append((f'E@{n_final} (final)', stream_results(study, e[0]['key'], total)))
        points[split] = rows
    return points, types


def pair(a, b):
    """(a won where b lost, a lost where b won, common games)."""
    common = [t for t in a if t in b]
    return (sum(a[t] and not b[t] for t in common), sum(b[t] and not a[t] for t in common), len(common))


def render(points, types):
    out = []
    for split, rows in points.items():
        avail = [(label, res) for label, res in rows if res is not None]
        out += [f'## {NAMES[split]}', '']
        out += ['| point | wins/total | rate | vs C (won/lost) | vs previous E (won/lost) |', '|---|---|---|---|---|']
        prev, c = None, rows[0][1]
        for label, res in rows:
            if res is None:
                out.append(f'| {label} | not available | | | |')
                continue
            w = sum(res.values())
            vs_c = vs_prev = ''
            if label != 'C':
                if c is not None:
                    a, b, n = pair(res, c)
                    vs_c = f'+{a} / -{b} (n={n})'
                if prev is not None:
                    a, b, n = pair(res, prev)
                    vs_prev = f'+{a} / -{b} (n={n})'
                prev = res
            out.append(f'| {label} | {w}/{len(res)} | {w / len(res):.1%} | {vs_c} | {vs_prev} |')
        out += ['', 'Wins per task type (wins/games):', '']
        labels = [label for label, _ in avail]
        out += ['| task type | ' + ' | '.join(labels) + ' |', '|---|' + '---|' * len(labels)]
        by_type = defaultdict(list)
        for t, ty in types[split].items():
            by_type[ty].append(t)
        for ty in sorted(by_type):
            cells = [f'{sum(r.get(t, False) for t in by_type[ty])}/{len(by_type[ty])}' for _, r in avail]
            out.append(f'| {ty} | ' + ' | '.join(cells) + ' |')
        out.append('')
    return '\n'.join(out)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('study')
    p.add_argument('snaps', nargs='*')
    p.add_argument('--replicate', type=int, default=0, help='practice seed of the E library')
    p.add_argument('--output', default='results/library/SNAPSHOT-EVAL.md')
    a = p.parse_args(argv)
    points, types = collect(a.study, a.snaps, a.replicate)
    text = render(points, types)
    print(text)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f'# Snapshot evaluation: E (replicate {a.replicate}) over practice time\n\n'
                   'Same evaluation games, seed and settings for every column; E is frozen with the library after '
                   'N practice games. The "vs" columns count paired games (+ won where the other lost, '
                   '- lost where it won).\n\n' + text + '\n')
    print(f'written {out}')


if __name__ == '__main__':
    main()
