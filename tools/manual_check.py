"""Is a rule manual useful? Play N development games with the manual (frozen, condition E with an
empty skill library) and compare with condition C on the same games from an earlier run.

usage: python tools/manual_check.py RULES.json REFERENCE_RUN [--games 30] [--workers 16]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, paired_comparison, stream_spec  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('rules')
    p.add_argument('reference')
    p.add_argument('--games', type=int, default=30)
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--retrieval', choices=manual.MODES, default='task',
                   help='how rules are chosen (never how they are written)')
    p.add_argument('--output', help='default /root/ll-runs/manual-check, with -MODE for other modes '
                                    '(resumable runs: one directory per variant)')
    p.add_argument('--json', help='per-game results (default OUTPUT/games.json)')
    a = p.parse_args()
    os.environ['LL_RETRIEVAL'] = a.retrieval     # inherited by worker processes
    a.output = a.output or '/root/ll-runs/manual-check' + ('' if a.retrieval == 'task' else '-' + a.retrieval)
    cfg = Settings.load('configs/pilot.json')
    runner = Runner(cfg, load_json('/root/ll-runs/manifest.json'), a.output)
    games = runner.pilot_development()[:a.games]
    rules = json.loads(Path(a.rules).read_text())
    # A one-episode "practice" stream that only holds the manual, read frozen by the test stream.
    holder = stream_spec('E', 'practice', 0, games[:1])
    holder_dir = Path(a.output) / 'checkpoints' / holder['key']
    test = stream_spec('E', 'development', cfg.seeds[0], games, init=holder['key'], init_position=1, frozen=True)
    if not holder_dir.exists():
        from living_library.config import digest, write_json
        from living_library.library import Library
        memory = {'library': Library(cfg).snapshot(), 'trajectories': [], 'rules': rules}
        initial = runner._initial(holder, {holder['key']: holder})
        record = {'success': False, 'task_id': games[0]['id'], 'position': 0, 'note': 'manual holder'}
        write_json(holder_dir / '00000.json', {
            'stream_identity': runner._stream_identity(holder, initial), 'previous_hash': None, 'source_hash': None,
            'pre_library': memory['library'], 'pre_library_hash': digest(memory['library']),
            'memory': memory, 'memory_hash': digest(memory), 'record': record, 'record_hash': digest(record)})
    runner.execute([holder, test], workers=a.workers, log=lambda *x: None)
    with_manual = {load_json(runner._checkpoint(test['key'], i))['record']['task_id']:
                   load_json(runner._checkpoint(test['key'], i))['record'] for i in range(runner.count(test['key']))}
    with_plans, visible = manual.plan_coverage(rules)
    out = Path(a.json or Path(a.output) / 'games.json')
    out.write_text(json.dumps({
        'retrieval': a.retrieval, 'rules_file': str(a.rules), 'rules_with_plans': with_plans, 'rules_visible': visible,
        'games': [{'id': t, 'win': bool(r['success']), 'rules_shown': r.get('rules_shown', [])}
                  for t, r in with_manual.items()]}, indent=1))
    print(f"retrieval={a.retrieval}: {with_plans} of {visible} visible rules have a stored won-game plan"
          f"{' (the others fall back to task)' if a.retrieval in ('plan', 'steps') else ''}; per-game results: {out}")
    reference = Path(a.reference) / 'checkpoints'
    ref_dir = next((d for d in (reference / 'development-C-11', reference / 'gate-C-11') if d.exists()),
                   reference / 'development-C-11')    # a pilot run or a study run (early gate)
    ref = {}
    for f in sorted(ref_dir.glob('*.json')):
        r = load_json(f)['record']
        ref[r['task_id']] = r
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
