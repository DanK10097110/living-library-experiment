"""Re-run the practice games where skills failed, with the current code, from the same library.

For each failure category (skill code that did not parse, a contract that missed the subgoal's
result, a failed replay test, a skill call that failed on a redundant "go to"/"open" step), picks up
to N games from an archived run and replays each one from its original pre-game library. The
model's original answers come from a copy of that run's response cache, so the same skill
proposals meet the new code; anything new is asked of the live server. Prints before/after.

usage: python tools/recheck_failures.py OLD_RUN STREAM [STREAM ...] [--per-category 3] [--workers 8]
"""
import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CATEGORIES = {
    'syntax': lambda r: any('line continuation' in e or 'invalid syntax' in e for e in r['program_errors']),
    'contract': lambda r: any('contract must cover' in e for e in r['program_errors']),
    'replay': lambda r: any('failed replay tests' in e for e in r['program_errors']),
    'redundant step': lambda r: any(c['error'].startswith(('inadmissible command: go to', 'inadmissible command: open'))
                                    for c in r['invocations']),
}


def summary(r):
    calls = r['invocations']
    return {'success': r['success'], 'candidates': r['candidate_attempts'], 'rejected': r['candidate_rejections'],
            'refined_then_admitted': r.get('candidate_refinements', 0),
            'skill_calls_ok': f"{sum(c['success'] for c in calls)}/{len(calls)}",
            'errors': sorted({e[:140] for e in r['program_errors'] if e.startswith('candidate')})[:3]}


def rerun(job):
    from living_library.agents import Agent
    from living_library.config import Settings
    from living_library.environments import ALFWorld
    from living_library.library import Library, SentenceEmbedding
    from living_library.models import HTTPModel
    cfg = Settings(**job['settings'])
    model = HTTPModel(cfg, job['cache'])
    try:
        agent = Agent(cfg, job['condition'], model, Library.restore(job['pre_library'], cfg),
                      SentenceEmbedding(cfg.embedding, cfg.embedding_revision), ALFWorld,
                      trajectories=job['trajectories'])
        return job['label'], agent.run(job['task'], job['context']['seed'], job['context'])
    finally:
        model.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('old_run')
    p.add_argument('streams', nargs='+')
    p.add_argument('--per-category', type=int, default=3)
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    run = Path(a.old_run)
    settings = json.loads((run / 'settings.json').read_text())
    plan = {s['key']: s for s in json.loads((run / 'plan.json').read_text())}
    scratch = Path(tempfile.mkdtemp(prefix='recheck-'))
    jobs, before = [], {}
    for stream in a.streams:
        cache = scratch / f'{stream}.sqlite'
        shutil.copyfile(run / 'model-cache' / f'{stream}.sqlite', cache)
        files = sorted((run / 'checkpoints' / stream).glob('*.json'))
        picked = {name: [] for name in CATEGORIES}
        for f in files:
            saved = json.loads(f.read_text())
            r = saved['record']
            for name, test in CATEGORIES.items():
                if test(r) and len(picked[name]) < a.per_category:
                    picked[name].append(saved)
                    break
        for name, games in picked.items():
            for saved in games:
                r = saved['record']
                label = f"{stream} #{r['position']} [{name}]"
                before[label] = summary(r)
                context = {k: r[k] for k in ('condition', 'phase', 'seed', 'task_id', 'position', 'toy')}
                jobs.append({'label': label, 'settings': settings, 'cache': str(cache), 'condition': r['condition'],
                             'pre_library': saved['pre_library'], 'trajectories': [],
                             'task': plan[stream]['tasks'][r['position']], 'context': context})
    print(f'{len(jobs)} games to re-run', flush=True)
    totals = {'before': [0, 0], 'after': [0, 0]}
    with ProcessPoolExecutor(a.workers) as pool:
        for label, result in pool.map(rerun, jobs):
            after = summary(result)
            for key, s in (('before', before[label]), ('after', after)):
                totals[key][0] += s['rejected']
                totals[key][1] += s['candidates']
            print(f'\n{label}\n  before: {json.dumps(before[label])}\n  after:  {json.dumps(after)}', flush=True)
    for key, (rejected, candidates) in totals.items():
        print(f'{key}: {rejected}/{candidates} candidates rejected')
    shutil.rmtree(scratch, ignore_errors=True)


if __name__ == '__main__':
    main()
