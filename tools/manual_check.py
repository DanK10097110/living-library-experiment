"""Is a rule manual useful? Play N development games with the manual (frozen, condition E with an
empty skill library) and compare with condition C on the same games from an earlier run.

usage: python tools/manual_check.py RULES.json REFERENCE_RUN [--games 30] [--workers 16]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, stream_spec  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('rules')
    p.add_argument('reference')
    p.add_argument('--games', type=int, default=30)
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--output', default='/root/ll-runs/manual-check')
    a = p.parse_args()
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
    ref = {}
    for f in sorted((Path(a.reference) / 'checkpoints' / 'development-C-11').glob('*.json')):
        r = load_json(f)['record']
        ref[r['task_id']] = r['success']
    paired = [t for t in with_manual if t in ref]
    m, c = sum(with_manual[t]['success'] for t in paired), sum(ref[t] for t in paired)
    print(f'{len(paired)} paired games: with manual {m}/{len(paired)}, without (C) {c}/{len(paired)}')
    print(f"  manual won where C lost: {sum(with_manual[t]['success'] and not ref[t] for t in paired)}; "
          f"lost where C won: {sum(ref[t] and not with_manual[t]['success'] for t in paired)}")
    print(f"  mean model calls per game with manual: "
          f"{sum(with_manual[t]['model_calls'] for t in paired) / max(1, len(paired)):.1f}")


if __name__ == '__main__':
    main()
