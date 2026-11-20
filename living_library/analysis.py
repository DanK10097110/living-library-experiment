"""Preregistered statistics (protocol.py). Wall time never substitutes for compute cost.

Cost (H2) is weighted tokens per task, input + 4 x output, amortized over practice
(amendment 2026-11-14): the local server batches many streams at once, so per-request GPU
time is not observable, and replayed (cached) episodes must cost the same as live ones.
Practice cost is amortized per replicate: each practice replicate's total is spread over the
evaluation tasks of the library it built.

Hierarchical paired bootstrap (redesign 2026-11-20): each bootstrap sample resamples the evaluation
tasks and, within each condition, its practice replicates (with replacement). A task's value for a
condition is the mean over the chosen replicates and the evaluation seeds, so library-to-library
variance is part of every interval. Memoryless conditions (C) have one replicate.

False success is the fraction of episodes where all subgoals passed but the task failed; episodes
with no subgoals are excluded. Missing observations are unknown.
"""
from collections import defaultdict
import math
import numpy as np


COST_METRIC = 'weighted_tokens'
# Holm family (protocol.py): H1 E-D task success, H2 E-D amortized cost, H3 E-E-minus task success.
HYPOTHESES = (('H1', 'D', 'success'), ('H2', 'D', COST_METRIC), ('H3', 'E-minus', 'success'))


def weighted_tokens(row):
    i, o = row.get('input_tokens'), row.get('output_tokens')
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in (i, o))
    return i + 4 * o if ok else None


def _number(row, key):
    value = weighted_tokens(row) if key == COST_METRIC else row.get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _false_success(rows):
    eligible = []
    for row in rows:
        if row.get('subgoal_count') == 0:
            continue
        if not isinstance(row.get('subgoals_passed'), bool) or not isinstance(row.get('success'), bool):
            return None
        eligible.append(row)
    return _ratio(sum(r['subgoals_passed'] and not r['success'] for r in eligible), len(eligible))


def _replicates(rows):
    """{replicate: {(task_id, seed): row}} of one condition's evaluation rows."""
    result = defaultdict(dict)
    for row in rows:
        key = (row['task_id'], row['seed'])
        replicate = row.get('replicate')
        if key in result[replicate]:
            raise ValueError(f'duplicate task/seed record: {key} (replicate {replicate})')
        result[replicate][key] = row
    return dict(result)


def _tasks(groups, conditions, cfg):
    """The evaluation tasks every replicate of every given condition played with every configured seed."""
    keys = None
    for condition in conditions:
        for indexed in groups[condition].values():
            if keys is None:
                keys = set(indexed)
            elif set(indexed) != keys:
                raise ValueError('paired comparison has different task/seed identifiers')
    by_task = defaultdict(set)
    for task, seed in keys:
        by_task[task].add(seed)
    if any(seeds != set(cfg.seeds) for seeds in by_task.values()):
        raise ValueError('each paired task must contain every configured seed')
    if len(by_task) != cfg.evaluation_games:
        raise ValueError('paired comparison must contain every configured evaluation task')
    return sorted(by_task)


def _practice_cost(practice_costs, condition, replicate):
    if condition not in practice_costs:
        return 0.0 if condition == 'C' else None
    value = practice_costs[condition].get(replicate, practice_costs[condition].get(str(replicate)))
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def _values(groups, condition, metric, tasks, cfg, practice_costs):
    """Array (replicates x tasks): the seed mean of `metric` per task and replicate, with the replicate's
    practice cost amortized over the tasks for the cost metric. None if anything is missing."""
    matrix = []
    for replicate, indexed in sorted(groups[condition].items(), key=lambda kv: str(kv[0])):
        practice = 0.0
        if metric == COST_METRIC:
            practice = _practice_cost(practice_costs or {}, condition, replicate)
            if practice is None:
                return None
        row = []
        for task in tasks:
            values = [_number(indexed[task, seed], metric) for seed in cfg.seeds]
            if any(v is None or (metric == COST_METRIC and v < 0) for v in values):
                return None
            row.append(sum(values) / len(values) + practice / len(tasks))
        matrix.append(row)
    return np.asarray(matrix, dtype=float)


def _bootstrap(left, right, samples):
    """Hierarchical paired bootstrap of mean(left) - mean(right); left/right are replicates x tasks."""
    rng = np.random.default_rng(0)
    tasks = left.shape[1]
    estimate = float(left.mean(axis=0).mean() - right.mean(axis=0).mean())
    means = []
    for start in range(0, samples, 512):
        n = min(512, samples - start)
        # Replicates drawn with replacement per condition and sample, as weights over the replicate rows.
        weights = [np.apply_along_axis(np.bincount, 1, rng.integers(0, m.shape[0], (n, m.shape[0])),
                                       minlength=m.shape[0]) / m.shape[0] for m in (left, right)]
        per_task = weights[0] @ left - weights[1] @ right                       # n x tasks
        chosen = rng.integers(0, tasks, (n, tasks))
        means.append(np.take_along_axis(per_task, chosen, axis=1).mean(axis=1))
    means = np.concatenate(means)
    low, high = np.quantile(means, [.025, .975])
    # Two-sided centered-bootstrap null with finite Monte Carlo correction.
    p = (1 + int(np.sum(np.abs(means - estimate) >= abs(estimate) - 1e-15))) / (samples + 1)
    return {'estimate': estimate, 'ci95': [float(low), float(high)], 'p_value': p, 'tasks': tasks,
            'replicates': [int(left.shape[0]), int(right.shape[0])], 'status': 'available'}


def _comparison(groups, left, right, metric, cfg, practice_costs):
    if not groups.get(left) or not groups.get(right):
        return {'status': 'unavailable', 'reason': 'missing condition'}
    tasks = _tasks(groups, (left, right), cfg)
    a = _values(groups, left, metric, tasks, cfg, practice_costs)
    b = _values(groups, right, metric, tasks, cfg, practice_costs)
    if a is None or b is None:
        return {'status': 'unavailable', 'reason': f'missing or invalid {metric} or practice cost accounting'}
    return _bootstrap(a, b, cfg.bootstrap_samples)


def _holm(primary):
    available = sorted(((k, v['p_value']) for k, v in primary.items() if 'p_value' in v), key=lambda x: x[1])
    previous = 0.0
    # The preregistered family always contains three tests, even if some are unavailable.
    for rank, (key, p) in enumerate(available):
        previous = max(previous, min(1.0, (len(HYPOTHESES) - rank) * p))
        primary[key]['p_holm'] = previous
        primary[key]['reject_holm_05'] = previous <= .05


def _amortized_cost(groups, condition, cfg, practice_costs):
    if not groups.get(condition):
        return None
    tasks = _tasks(groups, (condition,), cfg)
    values = _values(groups, condition, COST_METRIC, tasks, cfg, practice_costs)
    return None if values is None else float(values.mean())


def analyze(records, cfg, practice_costs=None):
    """Analyze evaluation records; missing pairs raise, missing measures are unknown.

    practice_costs maps condition -> replicate (practice seed) -> total weighted tokens of that replicate's
    practice (C needs none). Study success requires (the H1 point difference >= 10 pp, OR zero inside H1's
    95% interval with >= 30% lower amortized cost) AND H3 > 0 with its Holm-adjusted p <= .05.
    """
    rows = [r for r in records if r.get('phase') == 'evaluation']
    by_condition = defaultdict(list)
    for row in rows:
        by_condition[row['condition']].append(row)
    groups = {condition: _replicates(rs) for condition, rs in by_condition.items()}
    primary = {name: _comparison(groups, 'E', other, metric, cfg, practice_costs)
               for name, other, metric in HYPOTHESES}
    _holm(primary)
    secondary = {'E_minus_C': _comparison(groups, 'E', 'C', 'success', cfg, practice_costs), 'conditions': {}}
    for condition, rs in sorted(by_condition.items()):
        tokens = [weighted_tokens(r) for r in rs]
        secondary['conditions'][condition] = {
            'episodes': len(rs), 'success': sum(bool(r['success']) for r in rs) / len(rs),
            'success_by_replicate': {str(rep): sum(bool(r['success']) for r in indexed.values()) / len(indexed)
                                     for rep, indexed in sorted(groups[condition].items(), key=lambda kv: str(kv[0]))},
            'weighted_tokens_per_task': None if None in tokens else sum(tokens) / len(rs),
            'amortized_weighted_tokens_per_task': _amortized_cost(groups, condition, cfg, practice_costs),
            'false_success': _false_success(rs)}
    h1, h3 = primary['H1'], primary['H3']
    cost_ratio = None
    if primary['H2']['status'] == 'available':
        cost_ratio = _ratio(_amortized_cost(groups, 'E', cfg, practice_costs),
                            _amortized_cost(groups, 'D', cfg, practice_costs))
    benefit = None
    if h1['status'] == 'available':
        benefit = h1['estimate'] >= cfg.success_margin
        if not benefit:
            benefit = (h1['ci95'][0] <= 0 <= h1['ci95'][1] and cost_ratio <= 1 - cfg.cost_reduction) if cost_ratio is not None else None
    management = (h3['estimate'] > 0 and h3['reject_holm_05']) if h3['status'] == 'available' else None
    criterion = False if benefit is False or management is False else (True if benefit and management else None)
    return {'primary': primary, 'secondary': secondary, 'study_success': criterion,
            'amortized_cost_ratio_E_D': cost_ratio, 'cost_metric': 'weighted tokens (input + 4 x output)',
            'gpu_seconds_measured': all(r.get('gpu_seconds') is not None for r in rows),
            'method': 'Hierarchical paired percentile bootstrap: tasks resampled, and within each condition its '
                      'practice replicates; task value = mean over chosen replicates and evaluation seeds; '
                      'practice cost amortized per replicate; centered two-sided bootstrap p; Holm over H1-H3.',
            'criterion': '(H1 >= 10 pp OR zero in H1 CI with >= 30% lower amortized weighted-token cost) AND '
                         'H3 positive with Holm p <= .05.',
            'expected_evaluation_tasks': cfg.evaluation_games, 'toy': any(r.get('toy', False) for r in rows)}
