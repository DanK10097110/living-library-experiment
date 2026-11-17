"""Explicit commands: fixture smoke test, manifest, pilot, freeze, study, analysis."""
import argparse
import json
from pathlib import Path
import sys

from .config import CONDITIONS, Settings, write_json
from .environments import build_manifest, demo_manifest
from .experiment import Runner, freeze, load_json, verify_freeze


def session(command, workers):
    command.add_argument('--workers', type=int, default=workers,
                         help='streams run in parallel (keep <= the model server slots)')
    command.add_argument('--max-episodes', type=int,
                         help='stop after this many newly committed episodes; rerun to continue')
    command.add_argument('--max-hours', type=float,
                         help='stop starting episodes after this many hours; rerun to continue')


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
    session(demo, workers=1)
    for name in ('pilot', 'freeze', 'study'):
        command = commands.add_parser(name)
        command.add_argument('--config', default='configs/pilot.json')
        command.add_argument('--manifest', required=True)
        command.add_argument('--output', required=True)
        if name == 'freeze':
            command.add_argument('--pilot-dir', required=True)
        if name == 'study':
            command.add_argument('--freeze', required=True)
            command.add_argument('--conditions', nargs='+', choices=CONDITIONS,
                                 help='default: the conditions in the config')
            command.add_argument('--reuse-pilot', metavar='PILOT_DIR',
                                 help="replay the pilot's E-minus practice model responses")
        if name != 'freeze':
            session(command, workers=8)
    status = commands.add_parser('status', help='progress of a pilot or study output directory')
    status.add_argument('--output', required=True)
    analyze = commands.add_parser('analyze')
    analyze.add_argument('--records', required=True)
    analyze.add_argument('--config', default='configs/pilot.json')
    analyze.add_argument('--output', required=True)
    return p


def save_analysis(records, cfg, output):
    from .analysis import analyze, weighted_tokens
    practice_costs = {}
    for condition in ('B', 'D', 'E', 'E-minus', 'E-plus'):
        if condition not in cfg.conditions:
            continue
        rows = [r for r in records if r['phase'] == 'practice' and r['condition'] == condition]
        costs = [weighted_tokens(r) for r in rows]
        total = sum(costs) if rows and None not in costs else None
        practice_costs[condition] = {seed: total for seed in cfg.seeds}
    report = analyze(records, cfg, practice_costs)
    write_json(output, report)
    # Secondary: in-distribution test (seen-room games the pilot never touched), same analysis.
    in_dist = [{**r, 'phase': 'evaluation'} for r in records if r['phase'] == 'id-evaluation']
    if in_dist:
        from dataclasses import replace
        n = len({r['task_id'] for r in in_dist})
        write_json(Path(output).with_name('analysis-in-distribution.json'),
                   analyze(in_dist, replace(cfg, evaluation_games=n), practice_costs))
    return report


def print_status(output):
    output = Path(output)
    run = load_json(output / 'run.json')
    # Success counts come from records.json, refreshed at the end of every session.
    records = load_json(output / 'records.json') if (output / 'records.json').exists() else []
    wins, seen = {}, {}
    for r in records:
        key = f"{r['phase']}-{r['condition']}-{r['seed']}"
        wins[key] = wins.get(key, 0) + bool(r['success'])
        seen[key] = seen.get(key, 0) + 1
    rows = []
    for spec in load_json(output / 'plan.json'):
        directory = output / 'checkpoints' / spec['key']
        names = {p.name for p in directory.glob('*.json')} if directory.exists() else set()
        done = 0
        while f'{done:05d}.json' in names:
            done += 1
        rows.append((spec['key'], done, len(spec['tasks'])))
    total_done, total = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print(f"{output} ({'toy' if run['toy'] else run['environment']}): {total_done}/{total} episodes")
    for key, done, n in rows:
        filled = round(20 * done / n)
        rate = f"  success {wins[key]}/{seen[key]}" if seen.get(key) else ''
        print(f"  {key:28} {'#' * filled}{'.' * (20 - filled)} {done:4}/{n}{rate}")


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
            records = runner.study(args.conditions, args.sample_count, workers=args.workers,
                                   max_episodes=args.max_episodes, max_hours=args.max_hours)
            if runner.complete:
                save_analysis(records, cfg, Path(args.output) / 'analysis.json')
        elif args.command == 'status':
            print_status(args.output)
            return 0
        elif args.command == 'analyze':
            save_analysis(load_json(args.records), Settings.load(args.config), args.output)
        else:
            cfg = Settings.load(args.config)
            manifest = load_json(args.manifest)
            if args.command == 'freeze':
                freeze(cfg, manifest, args.pilot_dir, args.output)
            elif args.command == 'pilot':
                runner = Runner(cfg, manifest, args.output)
                evidence = runner.pilot(args.workers, args.max_episodes, args.max_hours)
                if evidence is None:
                    print(f'pilot paused: {args.output}')
                    return 0
                print(json.dumps(evidence['gate'], indent=2))
            else:
                verify_freeze(cfg, manifest, args.freeze)
                runner = Runner(cfg, manifest, args.output)
                records = runner.study(args.conditions, freeze_path=args.freeze, workers=args.workers,
                                       max_episodes=args.max_episodes, max_hours=args.max_hours,
                                       reuse_pilot=args.reuse_pilot)
                if not runner.complete:
                    print(f'study paused: {args.output}')
                    return 0
                save_analysis(records, cfg, Path(args.output) / 'analysis.json')
        done = runner is None or runner.complete
        print(f"{args.command} {'complete' if done else 'paused'}: {args.output}")
        return 0
    except (ValueError, KeyError, OSError, ImportError, RuntimeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('interrupted; committed episodes are saved, rerun the same command to resume', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
