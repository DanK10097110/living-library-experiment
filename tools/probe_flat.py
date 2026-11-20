"""Diagnostic only (not experiment data): flat agent A on the first N development games.
usage: python tools/probe_flat.py <config.json> <N> <condition>"""
import json
import sys
import tempfile
import time

from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import ALFWorld
from living_library.embedding import LexicalEmbedding
from living_library.models import HTTPModel

cfg = Settings.load(sys.argv[1])
n, condition = int(sys.argv[2]), sys.argv[3]
tasks = json.load(open('/root/ll-runs/manifest.json'))['splits']['development'][:n]
model = HTTPModel(cfg, tempfile.mkdtemp() + '/cache.sqlite')
wins, start = 0, time.monotonic()
for i, task in enumerate(tasks):
    r = Agent(cfg, condition, model, LexicalEmbedding(), ALFWorld).run(task, 11, {'probe': i})
    wins += r['success']
    valid = sum(t['valid'] for t in r['trace'])
    print(f"{task['task_type']:32} {'WIN ' if r['success'] else 'fail'} steps {len(r['trace'])} valid {valid} calls {r['model_calls']}", flush=True)
print(f"{cfg.executor_model} {condition}: {wins}/{n} in {time.monotonic() - start:.0f}s")
