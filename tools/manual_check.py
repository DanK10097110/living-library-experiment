"""Is a rule manual useful? Play N development games with the manual (frozen, condition E) and compare with
condition C on the same games from an earlier run.

usage: python tools/manual_check.py RULES.json REFERENCE_RUN [--games 30] [--workers 16] [--output DIR]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, paired_comparison, stream_spec  # noqa: E402


def load_rules(path):
    """(rules, message): rules.json is stripped of per-rule 'contexts' (the games a rule was used in, which
    task-keyed retrieval uses as evidence), so prefer the sibling rules-full.json when the given file has none."""
    path = Path(path)
    rules = json.loads(path.read_text())
    if any(r.get('contexts') for r in rules):
        return rules, None
    full = path.with_name('rules-full.json')
    if full != path and full.exists():
        fuller = json.loads(full.read_text())
        if any(r.get('contexts') for r in fuller):
            return fuller, f'note: {path.name} has no contexts; using {full} instead'
    return rules, 'WARNING: rules have no contexts: task-keyed retrieval falls back to source tasks and rule text'


def reference_records(reference):
    """C's development games of an earlier run (a study's gate-C stream, or an old pilot's development-C)."""
    root = Path(reference) / 'checkpoints'
    found = [d for pattern in ('gate-C-*', 'development-C-*') for d in sorted(root.glob(pattern)) if d.is_dir()]
    if not found:
        raise ValueError(f'{reference} has no gate-C or development-C stream')
    return {r['task_id']: r for r in (load_json(f)['record'] for f in sorted(found[0].glob('*.json')))}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('rules')
    p.add_argument('reference')
    p.add_argument('--games', type=int, default=30)
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--output', default='/root/ll-runs/manual-check',
                   help='resumable run directory (one per rules file)')
    p.add_argument('--json', help='per-game results (default OUTPUT/games.json)')
    a = p.parse_args()
    cfg = Settings.load('configs/pilot.json')
    runner = Runner(cfg, load_json('/root/ll-runs/manifest.json'), a.output)
    games = runner.development_set()[:a.games]
    rules, message = load_rules(a.rules)
    if message:
        print(message, flush=True)
    # A one-game "practice" stream that only holds the manual, read frozen by the test stream.
    holder = stream_spec('E', 'practice', 0, games[:1], replicate=0)
    if not runner.hold(holder, {'trajectories': [], 'rules': rules}, f'manual holder of {a.rules}'):
        raise ValueError(f'{a.output} already holds a different manual; use a fresh --output')
    test = stream_spec('E', 'development', cfg.seeds[0], games, init=holder['key'], init_position=1, frozen=True,
                       replicate=0)
    runner.execute([holder, test], workers=a.workers, log=lambda *x: None)
    with_manual = {r['task_id']: r for r in (load_json(runner._checkpoint(test['key'], i))['record']
                                             for i in range(runner.count(test['key'])))}
    out = Path(a.json or Path(a.output) / 'games.json')
    out.write_text(json.dumps({
        'rules_file': str(a.rules),
        'games': [{'id': t, 'win': bool(r['success']), 'rules_shown': r.get('rules_shown', [])}
                  for t, r in with_manual.items()]}, indent=1))
    print(f'per-game results: {out}')
    ref = reference_records(a.reference)
    pair = paired_comparison(list(with_manual.values()), list(ref.values()))
    n = pair['games']
    print(f"{n} paired games: with manual {pair['wins']}/{n}, without (C) {pair['baseline_wins']}/{n}")
    print(f"  manual won where C lost: {pair['won_where_baseline_lost']}; "
          f"lost where C won: {pair['lost_where_baseline_won']}")
    paired = [t for t in with_manual if t in ref]
    print(f"  mean model calls per game with manual: "
          f"{sum(with_manual[t]['model_calls'] for t in paired) / max(1, len(paired)):.1f}")


if __name__ == '__main__':
    main()
