"""Explicit commands: fixture smoke test, manifest, pilot, freeze, study, analysis."""
import argparse
import json
from pathlib import Path
import sys

from .config import CONDITIONS, Settings, write_json
from .environments import build_manifest, demo_manifest
from .experiment import Runner, freeze, load_json, verify_freeze


def parser():
    p = argparse.ArgumentParser(prog='living-library', description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    manifest = commands.add_parser('manifest', help='index local ALFWorld data without running episodes')
    manifest.add_argument('--data-root', required=True)
    manifest.add_argument('--output', required=True)
    demo = commands.add_parser('demo', help='CPU-only deterministic fixture; no scientific conclusions')
    demo.add_argument('--output', required=True)
    demo.add_argument('--sample-count', type=int, default=3)
    demo.add_argument('--conditions', nargs='+', choices=CONDITIONS, default=list(CONDITIONS))
    for name in ('pilot', 'freeze', 'study'):
        command = commands.add_parser(name)
        command.add_argument('--config', default='configs/pilot.json')
        command.add_argument('--manifest', required=True)
        command.add_argument('--output', required=True)
        if name == 'freeze':
            command.add_argument('--pilot-dir', required=True)
        if name == 'study':
            command.add_argument('--freeze', required=True)
            command.add_argument('--conditions', nargs='+', choices=CONDITIONS, default=list(CONDITIONS))
    analyze = commands.add_parser('analyze')
    analyze.add_argument('--records', required=True)
    analyze.add_argument('--config', default='configs/pilot.json')
    analyze.add_argument('--output', required=True)
    return p


def save_analysis(records, cfg, output):
    from .analysis import analyze
    practice_costs = {}
    for condition in ('B', 'D', 'E', 'E-minus'):
        rows = [r for r in records if r['phase'] == 'practice' and r['condition'] == condition]
        total = (sum(r['gpu_seconds'] for r in rows) if rows and
                 all(r.get('gpu_seconds') is not None for r in rows) else None)
        practice_costs[condition] = {seed: total for seed in cfg.seeds}
    report = analyze(records, cfg, practice_costs)
    write_json(output, report)
    return report


def main(argv=None):
    args = parser().parse_args(argv)
    runner = None
    try:
        if args.command == 'manifest':
            write_json(args.output, build_manifest(args.data_root))
        elif args.command == 'demo':
            if not 1 <= args.sample_count <= 6:
                raise ValueError('demo sample count must be between 1 and 6')
            cfg = Settings(practice_episodes=args.sample_count, evaluation_games=args.sample_count,
                           step_budget=12, max_model_calls=20, bootstrap_samples=200)
            runner = Runner(cfg, demo_manifest(), args.output)
            records = runner.study(args.conditions, args.sample_count)
            save_analysis(records, cfg, Path(args.output) / 'analysis.json')
        elif args.command == 'analyze':
            save_analysis(load_json(args.records), Settings.load(args.config), args.output)
        else:
            cfg = Settings.load(args.config)
            manifest = load_json(args.manifest)
            if args.command == 'freeze':
                freeze(cfg, manifest, args.pilot_dir, args.output)
            elif args.command == 'pilot':
                runner = Runner(cfg, manifest, args.output)
                runner.pilot()
            else:
                verify_freeze(cfg, manifest, args.freeze)
                runner = Runner(cfg, manifest, args.output)
                records = runner.study(args.conditions, freeze_path=args.freeze)
                save_analysis(records, cfg, Path(args.output) / 'analysis.json')
        print(f'{args.command} complete: {args.output}')
        return 0
    except (ValueError, KeyError, OSError, ImportError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    finally:
        if runner is not None and hasattr(runner.model, 'close'):
            runner.model.close()


if __name__ == '__main__':
    raise SystemExit(main())
