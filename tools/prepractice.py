"""Run the study's practice streams early, alongside the pilot, to use idle GPU capacity.

Practice uses only training games and the same code/settings as the pilot, so nothing from the
held-out evaluation split is touched. The checkpoints land in the study output directory; if the
pilot passes and the freeze matches these settings and sources, `study` resumes from them.
If anything changes after the pilot, the study's identity check rejects this directory: delete it.

usage: python tools/prepractice.py --config configs/pilot.json --manifest M --output DIR
       [--conditions D E] [--workers 3] [--max-episodes N] [--max-hours H]

E-minus is left out by default: its study practice is the pilot's E-minus practice (same seed,
order and settings), which the study replays from the pilot's model cache.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import MEMORY, Settings  # noqa: E402
from living_library.experiment import Runner, load_json, validate_real_design  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='configs/pilot.json')
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--conditions', nargs='+')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--max-episodes', type=int)
    p.add_argument('--max-hours', type=float)
    args = p.parse_args()
    cfg, manifest = Settings.load(args.config), load_json(args.manifest)
    validate_real_design(cfg, manifest)
    runner = Runner(cfg, manifest, args.output)
    runner.workflow('study')
    # E-minus and E-plus practice start with the pilot's (replayed from its cache by `study`).
    conditions = args.conditions or [c for c in cfg.conditions if c in MEMORY and c not in ('E-minus', 'E-plus')]
    specs = [s for s in runner.study_specs(tuple(conditions)) if s['phase'] == 'practice']
    assert all(t['split'] == 'practice' for s in specs for t in s['tasks']), 'practice only'
    done = runner.execute(specs, args.workers, args.max_episodes, args.max_hours)
    print('pre-practice', 'complete' if done else 'paused', args.output)


if __name__ == '__main__':
    main()
