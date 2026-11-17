"""Model bake-off: condition C (no memory) on the first N pilot development games, all in parallel.

Compares a candidate model with the 35B MoE on exactly the games the MoE already played in the
pilot (same order, seed and settings; only the model differs). Needs the candidate served on
127.0.0.1:8000 (tools/serve-model.ps1 -Model <name>). Writes <output>/bakeoff.json.

usage: python tools/bakeoff.py --name qwen3-8b --output /root/ll-runs/bakeoff/qwen3-8b
       [--games 40] [--workers 16] [--reference /root/ll-runs/pilot]
"""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, load_json, stream_spec  # noqa: E402


def metrics():
    text = urlopen('http://127.0.0.1:8000/metrics', timeout=10).read().decode()
    return {line.split()[0].split(':')[1]: float(line.split()[1]) for line in text.splitlines()
            if line.startswith('llamacpp:') and len(line.split()) == 2}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--games', type=int, default=40)
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--config', default='configs/pilot.json')
    p.add_argument('--manifest', default='/root/ll-runs/manifest.json')
    p.add_argument('--reference', default='/root/ll-runs/pilot')
    a = p.parse_args()
    cfg = Settings.load(a.config)
    cfg.planner_model = cfg.executor_model = a.name
    manifest = load_json(a.manifest)
    runner = Runner(cfg, manifest, a.output)
    games = runner.pilot_development()[:a.games]
    spec = stream_spec('C', 'development', cfg.seeds[0], games)
    before, started = metrics(), time.monotonic()
    runner.execute([spec], workers=a.workers, log=lambda *x: None)
    wall, after = time.monotonic() - started, metrics()
    records = [load_json(runner._checkpoint(spec['key'], i))['record'] for i in range(runner.count(spec['key']))]
    reference = {}
    ref_dir = Path(a.reference) / 'checkpoints' / 'development-C-11'
    for i in range(a.games):
        path = ref_dir / f'{i:05d}.json'
        if path.exists():
            r = load_json(path)['record']
            reference[r['task_id']] = r['success']
    paired = [r for r in records if r['task_id'] in reference]
    generated = after.get('tokens_predicted_total', 0) - before.get('tokens_predicted_total', 0)
    prompt = after.get('prompt_tokens_total', 0) - before.get('prompt_tokens_total', 0)
    by_type = {}
    for r in records:
        kind = next(t['task_type'] for t in games if t['id'] == r['task_id'])
        by_type.setdefault(kind, [0, 0])
        by_type[kind][0] += r['success']
        by_type[kind][1] += 1
    report = {
        'model': a.name, 'games': len(records), 'success': sum(r['success'] for r in records),
        'success_rate': sum(r['success'] for r in records) / max(1, len(records)),
        'reference_moe_success_same_games': sum(reference[r['task_id']] for r in paired),
        'paired_games': len(paired),
        'wins_where_moe_lost': sum(r['success'] and not reference[r['task_id']] for r in paired),
        'losses_where_moe_won': sum(reference[r['task_id']] and not r['success'] for r in paired),
        'by_task_type': {k: f'{w}/{n}' for k, (w, n) in sorted(by_type.items())},
        'planner_fallbacks_per_game': sum(r['planner_fallbacks'] for r in records) / max(1, len(records)),
        'actor_followups_per_game': sum(r.get('actor_followups', 0) for r in records) / max(1, len(records)),
        'model_calls_per_game': sum(r['model_calls'] for r in records) / max(1, len(records)),
        'wall_minutes': round(wall / 60, 1),
        'games_per_hour': round(3600 * len(records) / wall, 1) if wall else None,
        'generated_tokens_per_second': round(generated / wall, 1) if wall else None,
        'prompt_tokens_per_second': round(prompt / wall, 1) if wall else None,
    }
    Path(a.output, 'bakeoff.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
