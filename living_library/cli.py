"""Explicit commands: fixture smoke test, manifest, study (with its early gate), status, analysis."""
import argparse
from pathlib import Path
import sys

from .config import CONDITIONS, MEMORY, Settings, write_json
from .environments import build_manifest, demo_manifest
from .experiment import GATE_MARGIN, Runner, load_json, restart_library, stream_key


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
    study = commands.add_parser('study')
    study.add_argument('--config', default='configs/pilot.json')
    study.add_argument('--manifest', required=True)
    study.add_argument('--output', required=True)
    study.add_argument('--conditions', nargs='+', choices=CONDITIONS, help='default: the conditions in the config')
    study.add_argument('--gate-at', type=int, default=75,
                       help='early gate after this many library practice games (0: no gate)')
    study.add_argument('--gate-games', type=int, default=30, help='paired development games for the early gate')
    study.add_argument('--gate-margin', type=int, default=GATE_MARGIN,
                       help='gate passes when E wins - C wins >= this (a bug detector)')
    study.add_argument('--past-gate', action='store_true',
                       help='continue from the checkpoint although the early gate failed')
    study.add_argument('--restart-library', action='store_true',
                       help='discard E/E-minus practice (every replicate) and everything built on it '
                            '(keeps C and D), then run')
    study.add_argument('--restart-streams', nargs='+', choices=['E'],
                       help="discard only these conditions' streams (every replicate) and what is built on them "
                            "(E: practice, gate, evaluations, snapshots), keeping C, D and E-minus if E-minus's "
                            "probe shows it unchanged, then run")
    session(study, workers=8)
    status = commands.add_parser('status', help='progress of a study output directory')
    status.add_argument('--output', required=True)
    analyze = commands.add_parser('analyze')
    analyze.add_argument('--records', required=True)
    analyze.add_argument('--config', default='configs/pilot.json')
    analyze.add_argument('--output', required=True)
    return p


def practice_costs(records, cfg):
    """{condition: {replicate: total weighted tokens of that replicate's practice}} (None if any is unknown)."""
    from .analysis import weighted_tokens
    costs = {}
    from .experiment import replicates
    for condition in MEMORY & set(cfg.conditions):
        for pseed in replicates(cfg, condition):
            rows = [r for r in records if r['phase'] == 'practice' and r['condition'] == condition
                    and r.get('replicate') == pseed]
            values = [weighted_tokens(r) for r in rows]
            costs.setdefault(condition, {})[pseed] = sum(values) if rows and None not in values else None
    return costs


def save_analysis(records, cfg, output):
    from .analysis import analyze
    costs = practice_costs(records, cfg)
    report = analyze(records, cfg, costs)
    write_json(output, report)
    # Secondary: in-distribution test (seen-room games outside the development set), same analysis.
    in_dist = [{**r, 'phase': 'evaluation'} for r in records if r['phase'] == 'id-evaluation']
    if in_dist:
        from dataclasses import replace
        n = len({r['task_id'] for r in in_dist})
        write_json(Path(output).with_name('analysis-in-distribution.json'),
                   analyze(in_dist, replace(cfg, evaluation_games=n), costs))
    return report


def print_status(output):
    output = Path(output)
    run = load_json(output / 'run.json')
    # Success counts come from records.json, refreshed at the end of every session.
    records = load_json(output / 'records.json') if (output / 'records.json').exists() else []
    wins, seen = {}, {}
    for r in records:
        key = stream_key(r['condition'], r['phase'], r['seed'], r.get('replicate'))
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
        print(f"  {key:30} {'#' * filled}{'.' * (20 - filled)} {done:4}/{n}{rate}")
    if (output / 'gate.json').exists():
        g = load_json(output / 'gate.json')
        verdict = 'passed' if g['passed'] else ('FAILED, continued' if g.get('continued') else 'FAILED, stopped')
        print(f"  early gate at {g['checkpoint']}: E {g['E_wins']} vs C {g['C_wins']} of {g['paired_games']} "
              f"paired games, {g['rule_count']} rules, {g['builder_errors']} builder errors -> {verdict}")


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
            if args.restart_library and args.restart_streams:
                raise ValueError('use either --restart-library or --restart-streams')
            if args.restart_library:
                restart_library(cfg, manifest, args.output)
            elif args.restart_streams:
                restart_library(cfg, manifest, args.output, streams=args.restart_streams)
            runner = Runner(cfg, manifest, args.output)
            records = runner.study(args.conditions, workers=args.workers,
                                   max_episodes=args.max_episodes, max_hours=args.max_hours,
                                   gate_at=args.gate_at, gate_games=args.gate_games,
                                   gate_margin=args.gate_margin, past_gate=args.past_gate)
            gate = runner.gate
            if gate is not None and not (gate['passed'] or gate.get('continued')):
                print(f'study stopped at the early gate: {Path(args.output) / "gate.json"}')
                return 3
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
