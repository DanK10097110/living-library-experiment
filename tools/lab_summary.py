"""Markdown tables from lab_bench.py results: mean (and spread over seeds) per method x N.
usage: python tools/lab_summary.py results/lab/data/bench-main.json [more.json ...]"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def table(results, split='all'):
    cells = defaultdict(list)
    for r in results:
        if split in r:
            cells[(r['n'], r['method'])].append(r)
    lines = ['| N (built) | method | cand. | rel. | useful@8 | P@3 | P@5 | P@8 | nDCG@3 | nDCG@8 | dup@8 | junk@8 | wrong@8 | lib junk | ms/q |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for (n, method), rs in sorted(cells.items()):
        def m(k, name):
            vals = [r[split][str(k)][name] if str(k) in r[split] else r[split][k][name] for r in rs]
            return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)
        u, us = m(8, 'useful')
        size = statistics.mean(r['size'] for r in rs)
        lines.append(
            f"| {n} ({size:.0f}) | {method} | {statistics.mean(r['candidates'] for r in rs):.0f} | "
            f"{statistics.mean(r['relevant_groups'] for r in rs):.0f} | {u:.2f} ± {us:.2f} | "
            f"{m(3, 'precision')[0]:.2f} | {m(5, 'precision')[0]:.2f} | {m(8, 'precision')[0]:.2f} ± {m(8, 'precision')[1]:.2f} | "
            f"{m(3, 'ndcg')[0]:.2f} | {m(8, 'ndcg')[0]:.2f} | {m(8, 'dup')[0]:.3f} | {m(8, 'junk')[0]:.2f} | "
            f"{m(8, 'wrong')[0]:.2f} | {statistics.mean(r['library_junk'] for r in rs):.2f} | "
            f"{1000 * statistics.mean(r['seconds_per_query'] for r in rs):.0f} |")
    return '\n'.join(lines)


def main():
    for path in sys.argv[1:]:
        results = json.loads(Path(path).read_text())
        seeds = len({r['seed'] for r in results})
        print(f'### {Path(path).name} ({seeds} seeds, {len(results)} runs)\n')
        print(table(results))
        for split in ('ood',):
            print(f'\n{split} queries only:\n')
            print(table(results, split))
        print()


if __name__ == '__main__':
    main()
