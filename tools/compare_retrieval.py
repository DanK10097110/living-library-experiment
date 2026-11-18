"""Compare retrieval variants from the per-game JSON files of tools/manual_check.py.

usage: python tools/compare_retrieval.py games_task.json games_plan.json ...   (the first is the baseline)
"""
import json
import sys
from pathlib import Path


def load(path):
    data = json.loads(Path(path).read_text())
    return data.get('retrieval', Path(path).stem), {g['id']: g for g in data['games']}


def main(paths):
    runs = [load(p) for p in paths]
    base = runs[0][1]
    print(f"{'variant':<14}{'wins':>8}{'paired W':>10}{'paired L':>10}{'mean shown':>12}{'distinct':>10}")
    for name, games in runs:
        both = [t for t in games if t in base]
        better = sum(games[t]['win'] and not base[t]['win'] for t in both)
        worse = sum(base[t]['win'] and not games[t]['win'] for t in both)
        shown = [len(g['rules_shown']) for g in games.values()]
        distinct = {r for g in games.values() for r in g['rules_shown']}
        print(f"{name:<14}{sum(g['win'] for g in games.values())}/{len(games):<6}{better:>10}{worse:>10}"
              f"{sum(shown) / max(1, len(shown)):>12.2f}{len(distinct):>10}")
    print('paired W / L: games won where the first file lost / lost where it won (common games only)')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
