"""Learning-curve evaluation: the E and E-minus libraries as they stood after N practice games, played frozen on
exactly the study's snapshot games (the 40 OOD + 40 ID games of the study's snapshot-150 streams).
usage: python tools/snapshot_curve.py STUDY_DIR --at 100 [--workers 24] [--output /root/ll-runs/snap-curve-100]
Together with the study's own snapshot-150 streams and its final evaluations (restricted to the same games) this
gives success at 100 / 150 / 200 / 300 practice games on identical games. Resumable; needs the model server.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings, write_json  # noqa: E402
from living_library.experiment import Runner, load_json, practice_key, stream_spec  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('study')
    p.add_argument('--at', type=int, required=True)
    p.add_argument('--workers', type=int, default=24)
    p.add_argument('--manifest', default='/root/ll-runs/manifest.json')
    p.add_argument('--output')
    a = p.parse_args(argv)
    study = Path(a.study)
    output = a.output or f'/root/ll-runs/snap-curve-{a.at}'
    cfg = Settings.load(study / 'settings.json')
    runner = Runner(cfg, load_json(a.manifest), output, probe=False)
    snaps = [s for s in load_json(study / 'plan.json') if s['phase'].startswith('snapshot-')]
    specs, tests = [], []
    for cond, rep in sorted({(s['condition'], s['replicate']) for s in snaps}):
        memory = load_json(study / 'checkpoints' / practice_key(cond, rep) / f'{a.at - 1:05d}.json')['memory']
        mine = [s for s in snaps if s['condition'] == cond and s['replicate'] == rep]
        holder = stream_spec(cond, 'practice', rep, mine[0]['tasks'][:1], replicate=rep)
        if not runner.hold(holder, memory, f'holder of {practice_key(cond, rep)} after {a.at} games'):
            raise ValueError(f'{output} holds a different snapshot; use a fresh --output per --at')
        specs.append(holder)
        for s in mine:
            phase = s['phase'].replace(s['phase'].split('-')[1], str(a.at), 1)  # snapshot-150-ood -> snapshot-100-ood
            t = stream_spec(cond, phase, s['seed'], s['tasks'], init=holder['key'], init_position=1,
                            frozen=True, replicate=rep)
            specs.append(t)
            tests.append(t)
    write_json(Path(output) / 'snapshot-meta.json', {'at': a.at, 'study': str(study),
                                                       'streams': [t['key'] for t in tests]})
    runner.execute(specs, workers=a.workers)
    for t in tests:
        recs = [load_json(runner._checkpoint(t['key'], i))['record'] for i in range(runner.count(t['key']))]
        print(f"{t['key']}: {sum(bool(r['success']) for r in recs)}/{len(recs)}")


if __name__ == '__main__':
    main()
