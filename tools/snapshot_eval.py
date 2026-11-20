"""Evaluate one E replicate's practice library as it stood after N practice games, on exactly the study's
evaluation games.

usage: python tools/snapshot_eval.py STUDY_DIR --at 100 [--replicate 0] [--split ood|id|both] [--workers 16]
                                     --output /root/ll-runs/snap-eval-100

Plays condition E frozen (the rules of STUDY_DIR/checkpoints/practice-E-<replicate> after game N, i.e. checkpoint
N-1), on the very same task lists (STUDY_DIR/plan.json: evaluation-E-r<replicate>-<seed> = OOD,
id-evaluation-E-r<replicate>-<seed> = ID), with the study's own settings (STUDY_DIR/settings.json) and seed, in the
same frozen-evaluation way as the study. Results are comparable game by game with the study's final E and C
evaluation streams (same task ids and stream keys). Resumable: run the same command again to continue. Needs the
model server, like the study itself.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings, write_json  # noqa: E402
from living_library.experiment import Runner, load_json, practice_key, stream_spec  # noqa: E402

SPLITS = {'ood': 'evaluation', 'id': 'id-evaluation'}


def committed(directory):
    """Contiguous committed checkpoints from position 0 (what Runner.count counts)."""
    directory = Path(directory)
    if not directory.exists():
        return 0
    names = {p.name for p in directory.glob('*.json')}
    n = 0
    while f'{n:05d}.json' in names:
        n += 1
    return n


def study_streams(study, splits, seed, replicate):
    """{split: plan spec} of the study's frozen E evaluation streams of this replicate (games, seed)."""
    plan = {s['key']: s for s in load_json(Path(study) / 'plan.json')}
    out = {}
    for split in splits:
        specs = [s for s in plan.values() if s['condition'] == 'E' and s['phase'] == SPLITS[split]
                 and s['seed'] == seed and s['replicate'] == replicate]
        if len(specs) != 1:
            raise ValueError(f'expected one E {SPLITS[split]} stream of replicate {replicate} in '
                             f'{study}/plan.json, found {len(specs)}')
        out[split] = specs[0]
    return out


def prepare(study, at, splits, output, manifest, replicate=0, probe=True):
    """Check the study has `at` practice games, build the runner and the specs. Returns (runner, specs, tests)."""
    study = Path(study)
    practice_dir = study / 'checkpoints' / practice_key('E', replicate)
    have = committed(practice_dir)
    if at < 1 or have < at:
        raise ValueError(f'{practice_dir} has {have} committed games; need {at}')
    cfg = Settings.load(study / 'settings.json')
    streams = study_streams(study, splits, cfg.seeds[0], replicate)
    runner = Runner(cfg, manifest, output, probe=probe)
    memory = load_json(practice_dir / f'{at - 1:05d}.json')['memory']
    first = next(iter(streams.values()))['tasks'][:1]
    # A one-game holder stream that only carries the library after game `at`, read frozen by the tests.
    holder = stream_spec('E', 'practice', replicate, first, replicate=replicate)
    if not runner.hold(holder, memory, f'holder of {practice_dir.name} after {at} games'):
        raise ValueError(f'{output} already holds a different snapshot; use a fresh --output per --at')
    tests = {split: stream_spec('E', spec['phase'], spec['seed'], spec['tasks'], init=holder['key'],
                                init_position=1, frozen=True, replicate=replicate)
             for split, spec in streams.items()}
    write_json(Path(output) / 'snapshot-meta.json', {
        'at': at, 'replicate': replicate, 'study': str(study), 'splits': list(tests),
        'streams': {s: t['key'] for s, t in tests.items()}, 'games': {s: len(t['tasks']) for s, t in tests.items()}})
    return runner, [holder] + list(tests.values()), tests


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('study')
    p.add_argument('--at', type=int, required=True, help='practice games the library has seen (100, 200, ...)')
    p.add_argument('--replicate', type=int, default=0, help='practice seed of the E library')
    p.add_argument('--split', choices=['ood', 'id', 'both'], default='both')
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--manifest', default='/root/ll-runs/manifest.json')
    p.add_argument('--output', help='default /root/ll-runs/snap-eval-AT[-rREPLICATE]')
    a = p.parse_args(argv)
    output = a.output or f'/root/ll-runs/snap-eval-{a.at}' + (f'-r{a.replicate}' if a.replicate else '')
    splits = ['ood', 'id'] if a.split == 'both' else [a.split]
    runner, specs, tests = prepare(a.study, a.at, splits, output, load_json(a.manifest), a.replicate)
    runner.execute(specs, workers=a.workers)
    for split, t in tests.items():
        recs = [load_json(runner._checkpoint(t['key'], i))['record'] for i in range(runner.count(t['key']))]
        print(f"{split}: E@{a.at} (replicate {a.replicate}) {sum(bool(r['success']) for r in recs)}/{len(recs)} "
              f"of {len(t['tasks'])} games")
    print('compare: python tools/compare_snapshots.py', a.study, output, '...')


if __name__ == '__main__':
    main()
