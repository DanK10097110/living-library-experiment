"""Retrieval methods compared in the lab. Each: fn(rules, query, k, similarity) -> ranked rule ids."""
import random

from .. import manual


def baseline(rules, query, k, similarity):
    """The live method, imported unchanged: manual.for_agent in 'task' mode (task-keyed + MACLA utility)."""
    return [r['id'] for r in manual.for_agent(rules, query['task_type'], k, query['goal'], similarity, 'task')]


def random_pick(rules, query, k, similarity, seed=0):
    """Reference: the same candidates as the baseline (recipe first, then this kind's and general rules),
    in random order. Shows how much the ranking itself adds."""
    rng = random.Random(f"{seed}:{query['id']}")
    visible = [r for r in rules if manual.shown_to_agent(r) and r['type'] != manual.avoid.POOL]
    recipe = [r for r in visible if r['type'] == 'Success Process' and r.get('task_type') == query['task_type']]
    others = [r for r in visible if r['type'] != 'Success Process'
              and r.get('task_type') in (query['task_type'], 'all', None)]
    rng.shuffle(others)
    return [r['id'] for r in (recipe + others)[:k]]


METHODS = {'baseline': baseline, 'random': random_pick}
