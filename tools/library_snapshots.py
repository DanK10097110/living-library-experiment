"""Periodic library snapshots and trend tables for a practice run.

usage: python tools/library_snapshots.py RUN_DIR [--every 25] [--out results/library]
For each library stream in RUN_DIR/checkpoints (practice-E-0, practice-E-minus-0, practice-E-text-0): every
--every games (after game 25, 50, ...) writes OUT/snapshots/<stream>/g<NNN>.json|.txt (existing files are kept),
and always regenerates OUT/trends-<stream>.csv and OUT/TRENDS.md. Read-only on the run dir.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from show_library import is_hidden, mean, rule_lines  # noqa: E402

STREAMS = ('practice-E-0', 'practice-E-minus-0')
TYPES = ('Success Process', 'Corrected Error', 'Unresolved Error', 'Special Phenomenon', 'Anti-Pattern')
OPS = {'retire': ('retire', 'prune'), 'merge': ('merge_rule', 'dedupe'), 'refine': ('refine',)}
COLUMNS = (['games', 'rules_total', 'visible', 'hidden'] + [t.lower().replace(' ', '_') for t in TYPES]
           + ['added', 'removed', 'retire_ops', 'merge_ops', 'refine_ops', 'win_rate',
              'mean_words_visible', 'mean_usefulness_visible', 'revisions_total'])


def row_for(games, rules, prev_ids, window):
    rules = [r for r in rules if r.get('type') != 'Failure Pool']
    vis = [r for r in rules if not is_hidden(r)]
    ids = {r.get('id') for r in rules}
    ops = {k: 0 for k in OPS}
    wins = []
    for rec in window:
        wins.append(1 if rec.get('success') else 0)
        for o in (rec.get('manual') or {}).get('operations', []):
            for k, names in OPS.items():
                if o.get('op') in names:
                    ops[k] += 1
    row = {'games': games, 'rules_total': len(rules), 'visible': len(vis), 'hidden': len(rules) - len(vis)}
    for t in TYPES:
        row[t.lower().replace(' ', '_')] = sum(r.get('type') == t for r in rules)
    row.update(added=len(ids - prev_ids), removed=len(prev_ids - ids),
               retire_ops=ops['retire'], merge_ops=ops['merge'], refine_ops=ops['refine'],
               win_rate=round(sum(wins) / len(wins), 3) if wins else '',
               mean_words_visible=round(sum(len((r.get('rule') or '').split()) for r in vis) / len(vis), 1) if vis else '',
               mean_usefulness_visible=round(sum(mean(r) for r in vis) / len(vis), 3) if vis else '',
               revisions_total=sum(r.get('revisions') or 0 for r in rules))
    return row, ids


def process_stream(run, stream, every, out):
    files = sorted((run / 'checkpoints' / stream).glob('[0-9]*.json'), key=lambda f: int(f.stem))
    if not files:
        return None
    rows, prev_ids, window = [], set(), []
    for f in files:
        d = json.loads(f.read_text())
        window.append(d.get('record') or {})
        n = int(f.stem) + 1
        if n % every:
            continue
        rules = (d.get('memory') or {}).get('rules') or []
        row, prev_ids = row_for(n, rules, prev_ids, window)
        window = []
        rows.append(row)
        snap = out / 'snapshots' / stream
        snap.mkdir(parents=True, exist_ok=True)
        base = snap / f'g{n:03d}'
        if not base.with_suffix('.json').exists():
            base.with_suffix('.json').write_text(json.dumps({'stream': stream, 'games': n, 'rules': rules}, indent=1))
        if not base.with_suffix('.txt').exists():
            head = f'{stream} after {n} games: {len(rules)} rules\n\n'
            base.with_suffix('.txt').write_text(head + '\n'.join(rule_lines(rules)) + '\n')
    out.mkdir(parents=True, exist_ok=True)
    with (out / f'trends-{stream}.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


def trends_md(all_rows):
    lines = ['# Library trends', '', 'Window = games since the previous snapshot. Retired includes pruned; merges = '
             'near-duplicate merges (write-time and end of batch).', '']
    for stream, rows in all_rows.items():
        lines += [f'## {stream}', '', '| games | rules | visible | win rate (window) | added | removed | retired | merges '
                  '| refined |', '|---|---|---|---|---|---|---|---|---|']
        for r in rows:
            wr = f"{r['win_rate']:.2f}" if r['win_rate'] != '' else '-'
            lines.append(f"| {r['games']} | {r['rules_total']} | {r['visible']} | {wr} | {r['added']} | {r['removed']} "
                         f"| {r['retire_ops']} | {r['merge_ops']} | {r['refine_ops']} |")
        lines.append('')
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run_dir')
    p.add_argument('--every', type=int, default=25)
    p.add_argument('--out', default='results/library')
    a = p.parse_args()
    run, out = Path(a.run_dir), Path(a.out)
    all_rows = {}
    for s in STREAMS:
        rows = process_stream(run, s, a.every, out)
        if rows is not None:
            all_rows[s] = rows
    out.mkdir(parents=True, exist_ok=True)
    (out / 'TRENDS.md').write_text(trends_md(all_rows))
    print(f'{len(all_rows)} stream(s): ' + ', '.join(f'{s}={len(r)} snapshots' for s, r in all_rows.items()))


if __name__ == '__main__':
    main()
