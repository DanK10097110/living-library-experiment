"""Is a C-vs-E difference on a game repeatable, or chance? Replay chosen development games several times
(different model sampling seeds) without a library (C) and with one frozen E library, using current code.

usage: python tools/repeat_check.py --library /root/ll-runs/study2/checkpoints/gate-75-E-r0-11
           --kinds pick_heat_then_place_in_recep look_at_obj_in_light --seeds 101 102 103 104
           [--settings /root/ll-runs/study2/settings.json] [--workers 24] [--output /root/ll-runs/repeat-check]

--library is a checkpoint directory of a frozen E stream (every checkpoint holds the same memory).
Writes OUTPUT/summary.json: per game and condition, (seed, won, actions, rules shown) for every replay.
Resumable: rerun the same command after a stop.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, stream_spec  # noqa: E402


def frozen_library(directory):
    memories = {load_json(f)['memory_hash'] for f in sorted(Path(directory).glob('*.json'))}
    if len(memories) != 1:
        raise ValueError(f'{directory}: expected one frozen memory, found {len(memories)}')
    return load_json(sorted(Path(directory).glob('*.json'))[0])['memory']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--library', required=True)
    p.add_argument('--kinds', nargs='*', default=[], help='task kinds to include (default: all)')
    p.add_argument('--games', nargs='*', default=[], help='substrings of game ids to include')
    p.add_argument('--seeds', nargs='+', type=int, default=[101, 102, 103, 104])
    p.add_argument('--settings', default='/root/ll-runs/study2/settings.json')
    p.add_argument('--workers', type=int, default=24)
    p.add_argument('--output', default='/root/ll-runs/repeat-check')
    a = p.parse_args()
    cfg = Settings.load(a.settings)
    runner = Runner(cfg, load_json('/root/ll-runs/manifest.json'), a.output)
    games = [g for g in runner.development_set()
             if (not a.kinds or g['id'].split('/')[1].split('-')[0] in a.kinds)
             and (not a.games or any(s in g['id'] for s in a.games))]
    if not games:
        raise ValueError('no development games match')
    memory = frozen_library(a.library)
    holder = stream_spec('E', 'practice', 0, games[:1], replicate=0)
    if not runner.hold(holder, memory, f'frozen library of {a.library}'):
        raise ValueError(f'{a.output} already holds a different library; use a fresh --output')
    specs = [holder]
    for seed in a.seeds:
        specs.append(stream_spec('C', 'development', seed, games))
        specs.append(stream_spec('E', 'development', seed, games, init=holder['key'], init_position=1,
                                 frozen=True, replicate=0))
    print(f'{len(games)} games x {len(a.seeds)} seeds x 2 conditions', flush=True)
    runner.execute(specs, workers=a.workers, log=lambda *x: None)
    summary = {g['id']: {'C': [], 'E': []} for g in games}
    for spec in specs[1:]:
        for i in range(runner.count(spec['key'])):
            r = load_json(runner._checkpoint(spec['key'], i))['record']
            summary[r['task_id']][spec['condition']].append(
                {'seed': spec['seed'], 'won': bool(r['success']), 'actions': len(r['trace']),
                 'rules_shown': r.get('rules_shown', []), 'checkpoint': str(runner._checkpoint(spec['key'], i))})
    (Path(a.output) / 'summary.json').write_text(json.dumps({'library': a.library, 'seeds': a.seeds,
                                                             'games': summary}, indent=1))
    for t, v in sorted(summary.items(), key=lambda kv: sum(x['won'] for x in kv[1]['C'])
                       - sum(x['won'] for x in kv[1]['E'])):
        c, e = v['C'], v['E']
        print(f"C {sum(x['won'] for x in c)}/{len(c)}  E {sum(x['won'] for x in e)}/{len(e)}  {t.split('/')[1]}")


if __name__ == '__main__':
    main()
