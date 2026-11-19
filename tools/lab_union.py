"""Union of the real rule libraries -> one large frozen library for a manual_check run (BRIEF Phase 3).

Keeps every rule the agent can see from the real libraries (deduplicated by text), with their contexts and Beta
counts, renumbered rule_1.. . The live code allows one Success Process per kind of task, so only the one with most
wins per kind is kept as a Success Process; the others are dropped (listing them all would put several recipes of
one kind first in every game, a situation the live code never creates).
Run in WSL: python tools/lab_union.py [--output results/lab/data/union-rules-full.json]"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.lab import data, synth  # noqa: E402


def union(pool):
    recipes = synth.recipes(pool)
    rest = [r for r in pool if r['type'] != 'Success Process']
    rules = []
    for r in recipes + rest:
        rule = {k: v for k, v in r.items() if k != 'origin'}
        rule['id'] = f'rule_{len(rules) + 1}'
        rules.append(rule)
    return rules


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default=str(data.ROOT / 'results' / 'lab' / 'data' / 'union-rules-full.json'))
    a = p.parse_args()
    rules = union(data.real_pool())
    Path(a.output).write_text(json.dumps(rules, indent=1))
    print(len(rules), 'rules,', sum(bool(r.get('contexts')) for r in rules), 'with contexts;',
          dict(Counter(synth.short(r['task_type']) for r in rules)), '->', a.output)


if __name__ == '__main__':
    main()
