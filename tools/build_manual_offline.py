"""Run the rule-manual Builder over archived practice games (no game replay) and print the manual.

Checks the Builder on real games before spending compute on a run: how many operations it makes,
which ones the case limits reject, and what the final rules say. Needs the model server.

usage: python tools/build_manual_offline.py RUN STREAM [--games 40] [--condition E] [--out rules.json]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402
from living_library.agents import Agent  # noqa: E402
from living_library.config import Settings  # noqa: E402
from living_library.environments import ALFWorld  # noqa: E402
from living_library.models import HTTPModel  # noqa: E402

from living_library.embedding import LexicalEmbedding  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run')
    p.add_argument('stream')
    p.add_argument('--games', type=int, default=40)
    p.add_argument('--condition', default='E')
    p.add_argument('--out')
    p.add_argument('--config', default='configs/pilot.json')
    a = p.parse_args()
    cfg = Settings.load(a.config)
    cache = Path('/tmp/manual-offline.sqlite')
    cache.unlink(missing_ok=True)
    model = HTTPModel(cfg, cache)
    rules, stats = [], collections.Counter()
    kinds = {}
    for tasks in json.loads(Path('/root/ll-runs/manifest.json').read_text())['splits'].values():
        kinds.update({task['id']: task['task_type'] for task in tasks})
    files = sorted((Path(a.run) / 'checkpoints' / a.stream).glob('*.json'))[:a.games]
    for i, f in enumerate(files):
        r = json.loads(f.read_text())['record']
        agent = Agent(cfg, a.condition, model, LexicalEmbedding(), ALFWorld, rules=rules)
        agent.result = {**r, 'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'model_wall_seconds': 0.0}
        agent.rules_shown = r.get('rules_shown', [])           # assessed (no planner citations in old records: none used)
        agent.public_task, agent.seed = {'goal': r.get('goal', '')}, r['seed']
        agent.task = {'task_type': kinds.get(r['task_id'])}
        agent.context = {k: r[k] for k in ('condition', 'phase', 'seed', 'task_id', 'position', 'toy')}
        agent.context['builder_offline'] = True
        agent.gpu_known = True
        report = manual.build(agent)
        stats[report['case']] += 1
        stats['operations'] += len(report['operations'])
        stats['rejected'] += len(report['errors'])
        for e in report['errors']:
            stats['why: ' + e.split(':')[0][:50]] += 1
        print(f"game {i:2} {report['case']:16} diag={report.get('diagnosis')!s:16} ops={[o['op'] for o in report['operations']]}"
              f" rejected={report['errors'][:2]} rules={len(rules)}", flush=True)
    model.close()
    print('\n' + json.dumps(stats, indent=1))
    print('\nFINAL MANUAL')
    for r in rules:
        ev = r.get('ev') or {}
        print(f"{r['id']} [{r['type']}] {r['rule']}\n    example: {r['example'][:200]}\n    validation: {r['validation']}"
              f"\n    evidence: shown {ev.get('shown', 0)}, followed {ev.get('followed', 0)}, m {manual.mean(r):+.2f}, "
              f"revisions {r.get('revisions', 0)}")
    if a.out:
        Path(a.out).write_text(json.dumps(rules, indent=1))


if __name__ == '__main__':
    main()
