"""Short live practice run for one condition, then a readable report of how its rule manual evolved.

Plays the first N pilot practice games (same order and settings as the pilot) in a scratch folder,
writes the final rules to <output>/rules.json, and prints: what the Builder wrote, updated, voted,
merged, refined and pruned per game, the final manual with each rule's reliability, and errors.

usage: python tools/mini_practice.py --games 48 --output /root/ll-runs/mini-macla [--condition E] [--workers 16]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, ordered, stream_spec  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--games', type=int, default=48)
    p.add_argument('--output', required=True)
    p.add_argument('--condition', default='E')
    p.add_argument('--workers', type=int, default=16)
    a = p.parse_args()
    cfg = Settings.load('configs/pilot.json')
    manifest = load_json('/root/ll-runs/manifest.json')
    runner = Runner(cfg, manifest, a.output)
    tasks = ordered(manifest['splits']['practice'], cfg.practice_seed, a.games, repeat=True)
    spec = stream_spec(a.condition, 'practice', cfg.practice_seed, tasks)
    runner.execute([spec], workers=a.workers, log=print)
    n = runner.count(spec['key'])
    records = [load_json(runner._checkpoint(spec['key'], i))['record'] for i in range(n)]
    rules = load_json(runner._checkpoint(spec['key'], n - 1))['memory'].get('rules', []) if n else []
    Path(a.output, 'rules.json').write_text(json.dumps(rules, indent=1))

    print(f'\n{n} games, won {sum(r["success"] for r in records)}')
    totals = collections.Counter()
    for r in records:
        m = r.get('manual', {})
        ops = collections.Counter(op['op'] for op in m.get('operations', []))
        totals.update(ops)
        merged = sum('merged a new rule' in e for e in m.get('errors', []))
        totals['merged'] += merged
        errors = [e for e in m.get('errors', []) if 'merged a new rule' not in e]
        totals['rejected or failed'] += len(errors)
        print(f"#{r['position']:3} {'WIN ' if r['success'] else 'fail'} {m.get('case', '-'):16} shown={len(r.get('rules_shown', []))} "
              f"ops={dict(ops)} merged={merged} rejected={errors[:2]}")
        for op in m.get('operations', []):
            if op['op'] in ('write_rule', 'refine'):
                print(f"       {op['op']}: {op.get('type', '')} {op['rule'][:150]}")
    print('\ntotals:', dict(totals))
    print(f'\nFINAL MANUAL ({len(rules)} rules)')
    for rule in sorted(rules, key=lambda x: (x['type'], -x.get('alpha', 1) / (x.get('alpha', 1) + x.get('beta', 1)))):
        a_, b_ = rule.get('alpha', 1), rule.get('beta', 1)
        print(f"{rule['id']:8} [{rule['type']}] {rule.get('task_type')} importance={rule.get('importance')} "
              f"Beta({a_},{b_}) mean={a_ / (a_ + b_):.2f}\n    {rule['rule'][:220]}")


if __name__ == '__main__':
    main()
