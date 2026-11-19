"""How large does E's rule manual get in a long run? Library size per practice game in the real practice runs,
rules added / removed per game, and a power-law extrapolation to 3000 games (MACLA pruning caps the manual at
manual.CAPACITY rules). Run in WSL: python tools/lab_growth.py [--games 3000]"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402

RUNS = Path('/root/ll-runs')


def curve(run):
    sizes, visible, added, removed, prev = [], [], 0, 0, set()
    for f in sorted((RUNS / run / 'checkpoints' / 'practice-E-0').glob('*.json')):
        rules = json.loads(f.read_text())['memory'].get('rules') or []
        rules = [r for r in rules if r['type'] != manual.avoid.POOL]
        ids = {r['id'] for r in rules}
        added += len(ids - prev)
        removed += len(prev - ids)
        prev = ids
        sizes.append(len(rules))
        visible.append(sum(manual.shown_to_agent(r) for r in rules))
    return sizes, visible, added, removed


def fit(sizes, start=8):
    """Least-squares fit of log(size) = log(c) + p log(game) over games >= start."""
    pts = [(math.log(i + 1), math.log(s)) for i, s in enumerate(sizes) if i + 1 >= start and s > 0]
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    p = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    return math.exp(my - p * mx), p


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--games', type=int, default=3000)
    a.add_argument('--runs', nargs='+', default=['practice-b', 'practice-d', 'practice-e', 'mini-macla', 'study'])
    args = a.parse_args()
    rows = []
    for run in args.runs:
        sizes, visible, added, removed = curve(run)
        if len(sizes) < 10:
            continue
        c, p = fit(sizes)
        cv, pv = fit(visible)
        half = len(sizes) // 2
        late = (sizes[-1] - sizes[half - 1]) / (len(sizes) - half)
        rows.append({'run': run, 'games': len(sizes), 'size': sizes[-1], 'visible': visible[-1], 'added': added,
                     'removed': removed, 'late_rate': late, 'p': p, 'pv': pv,
                     'at_games': min(manual.CAPACITY, c * args.games ** p), 'visible_at_games': cv * args.games ** pv,
                     'linear_late': sizes[-1] + late * (args.games - len(sizes))})
        r = rows[-1]
        print(f"{run:11s} games {r['games']:3d}: {r['size']:3d} rules ({r['visible']} visible), added {added}, removed "
              f"{removed}, 2nd-half rate {late:.2f}/game; size ~ n^{p:.2f} -> {r['at_games']:.0f} at {args.games} "
              f"games (visible ~ n^{pv:.2f} -> {r['visible_at_games']:.0f}); linear late rate -> "
              f"{r['linear_late']:.0f} (pruned to {manual.CAPACITY})")
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
