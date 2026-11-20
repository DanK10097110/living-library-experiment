"""Evaluate E's practice library as it stood after N practice games, on exactly the study's evaluation games.

usage: python tools/snapshot_eval.py STUDY_DIR --at 100 [--split ood|id|both] [--workers 16]
                                     --output /root/ll-runs/snap-eval-100

Plays condition E frozen (the library/rules of STUDY_DIR/checkpoints/practice-E-0 after game N, i.e. checkpoint
N-1), on the very same task lists (STUDY_DIR/plan.json: evaluation-E-<seed> = OOD, id-evaluation-E-<seed> = ID),
with the study's own settings (STUDY_DIR/settings.json) and seed, in the same frozen-evaluation way as the study.
Results are comparable game by game with the study's final E and C evaluation streams (same task ids).
Resumable: run the same command again to continue. Needs the model server, like the study itself.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings, digest, write_json  # noqa: E402
from living_library.experiment import Runner, load_json, stream_spec  # noqa: E402
from living_library.library import Library  # noqa: E402

PRACTICE = 'practice-E-0'
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


def study_streams(study, splits, seed):
    """{split: plan spec} of the study's frozen E evaluation streams (games, seed)."""
    plan = {s['key']: s for s in load_json(Path(study) / 'plan.json')}
    out = {}
    for split in splits:
        specs = [s for s in plan.values() if s['condition'] == 'E' and s['phase'] == SPLITS[split]
                 and s['seed'] == seed]
        if len(specs) != 1:
            raise ValueError(f'expected one E {SPLITS[split]} stream in {study}/plan.json, found {len(specs)}')
        out[split] = specs[0]
    return out


def prepare(study, at, splits, output, manifest, probe=True):
    """Check the study has `at` practice games, build the runner and the specs. Returns (runner, specs, tests)."""
    study = Path(study)
    practice_dir = study / 'checkpoints' / PRACTICE
    have = committed(practice_dir)
    if at < 1 or have < at:
        raise ValueError(f'{practice_dir} has {have} committed games; need {at}')
    cfg = Settings.load(study / 'settings.json')
    streams = study_streams(study, splits, cfg.seeds[0])
    runner = Runner(cfg, manifest, output, probe=probe)
    source = load_json(practice_dir / f'{at - 1:05d}.json')
    memory = source['memory']
    first = next(iter(streams.values()))['tasks'][:1]
    # A one-episode holder stream that only carries the library after game `at`, read frozen by the tests.
    holder = stream_spec('E', 'practice', 0, first)
    holder_file = Path(output) / 'checkpoints' / holder['key'] / '00000.json'
    if not holder_file.exists():
        initial = runner._initial(holder, {holder['key']: holder})
        record = {'success': False, 'task_id': first[0]['id'], 'position': 0,
                  'note': f'holder of {PRACTICE} after {at} games'}
        write_json(holder_file, {
            'stream_identity': runner._stream_identity(holder, initial), 'previous_hash': None, 'source_hash': None,
            'pre_library': Library(cfg).snapshot(), 'pre_library_hash': digest(Library(cfg).snapshot()),
            'memory': memory, 'memory_hash': digest(memory), 'record': record, 'record_hash': digest(record)})
    elif load_json(holder_file)['memory_hash'] != digest(memory):
        raise ValueError(f'{output} already holds a different snapshot; use a fresh --output per --at')
    tests = {}
    for split, spec in streams.items():
        tests[split] = stream_spec('E', spec['phase'], spec['seed'], spec['tasks'], init=holder['key'],
                                   init_position=1, frozen=True)
    write_json(Path(output) / 'snapshot-meta.json', {'at': at, 'study': str(study), 'splits': list(tests),
               'streams': {s: t['key'] for s, t in tests.items()}, 'games': {s: len(t['tasks']) for s, t in tests.items()}})
    return runner, [holder] + list(tests.values()), tests


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('study')
    p.add_argument('--at', type=int, required=True, help='practice games the library has seen (100, 200, ...)')
    p.add_argument('--split', choices=['ood', 'id', 'both'], default='both')
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--manifest', default='/root/ll-runs/manifest.json')
    p.add_argument('--output', help='default /root/ll-runs/snap-eval-AT')
    a = p.parse_args(argv)
    output = a.output or f'/root/ll-runs/snap-eval-{a.at}'
    splits = ['ood', 'id'] if a.split == 'both' else [a.split]
    runner, specs, tests = prepare(a.study, a.at, splits, output, load_json(a.manifest))
    runner.execute(specs, workers=a.workers)
    for split, t in tests.items():
        recs = [load_json(runner._checkpoint(t['key'], i))['record'] for i in range(runner.count(t['key']))]
        print(f"{split}: E@{a.at} {sum(bool(r['success']) for r in recs)}/{len(recs)} of {len(t['tasks'])} games")
    print('compare: python tools/compare_snapshots.py', a.study, output, '...')


if __name__ == '__main__':
    main()
