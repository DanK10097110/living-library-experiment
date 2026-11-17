"""Preregistered, task-clustered statistics. Wall time never substitutes for compute cost.

Cost (H2) is weighted tokens per task, input + 4 x output, amortized over practice
(amendment 2026-11-14): the local server batches many streams at once, so per-request GPU
time is not observable, and replayed (cached) episodes must cost the same as live ones.

Each task is one bootstrap cluster. Seeds receive equal weight within tasks.
Invocation success pools eligible invocation numerators/denominators, resampling
whole task clusters; zero-use task clusters stay in the resampling population.
False success is the fraction of episodes where all subgoals passed but the task
failed; episodes with no subgoals are excluded. Missing observations are unknown.
"""
from collections import defaultdict
from dataclasses import asdict, is_dataclass
import math
import numpy as np


COST_METRIC = 'weighted_tokens'


def weighted_tokens(row):
    i, o = row.get('input_tokens'), row.get('output_tokens')
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in (i, o))
    return i + 4 * o if ok else None


def _row(row):
    result = dict(asdict(row) if is_dataclass(row) else row)
    if 'weighted_tokens' not in result:
        result['weighted_tokens'] = weighted_tokens(result)
    aliases = {'all_subgoals_passed': 'subgoals_passed', 'l2_programs': 'program_attempts',
               'rejected_programs': 'program_failures', 'candidate_versions': 'candidate_attempts',
               'candidate_rejections': 'rejections', 'reused_invocations': 'reused_skills'}
    for target, source in aliases.items():
        if target not in result and source in result:
            result[target] = result[source]
    if 'rejected_programs' not in result and 'program_errors' in result:
        result['rejected_programs'] = result['program_errors']
    if isinstance(result.get('rejected_programs'), list):
        result['rejected_programs'] = len(result['rejected_programs'])
    if isinstance(result.get('invocations'), list):
        calls = result['invocations']
        result['invocation_records'] = calls
        eligible = [c for c in calls if c.get('preconditions_held') is True]
        result['invocations'] = len(eligible)
        result['invocation_successes'] = sum(bool(c.get('success')) for c in eligible)
    return result


def _number(row, key):
    value = row.get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _false_success(rows):
    eligible = []
    for row in rows:
        count = row.get('subgoals', row.get('subgoal_count'))
        if count == 0 or count == []:
            continue
        if not isinstance(row.get('all_subgoals_passed'), bool) or not isinstance(row.get('success'), bool):
            return None
        eligible.append(row)
    return _ratio(sum(r['all_subgoals_passed'] and not r['success'] for r in eligible), len(eligible))


def pilot_report(practice_records, baseline_records, library_records, cfg):
    """Five pilot gates; unavailable evidence never passes a gate.

    Practice must contain the configured 300 episodes before reuse can pass.
    Skill reuse is measured from actual invocation logs, never Beta counters
    (append-only libraries deliberately do not update reliability counters).
    """
    practice = [_row(r) for r in practice_records]
    baseline = [_row(r) for r in baseline_records]
    libraries = [_row(r) for r in library_records]
    c = [r for r in baseline if r.get('condition') == 'C']
    em = [r for r in baseline if r.get('condition') == 'E-minus']
    # Callers may pass E-minus development separately from library snapshots.
    em += [r for r in libraries if r.get('condition') == 'E-minus' and 'success' in r]
    gates = {}
    def gate(name, value, triggered, action):
        gates[name] = {'value': value, 'status': 'unavailable' if value is None else
                       ('fail' if triggered(value) else 'pass'), 'action': action}
    for name, rows in [('baseline_ceiling', c), ('library_ceiling', em)]:
        value = _ratio(sum(bool(r['success']) for r in rows), len(rows))
        gate(name, value, lambda x: x > .85, 'switch_to_scienceworld')
    uses = defaultdict(int)
    for r in practice:
        for invocation in r.get('invocation_records', []):
            sid = invocation.get('skill_id', invocation.get('id'))
            if sid:
                uses[sid.split('@')[0]] += 1
        for sid, count in r.get('skill_uses', {}).items():
            uses[sid.split('@')[0]] += count
    # Explicit library usage logs can be supplied when records lack per-call ids.
    if not uses:
        for r in libraries:
            if 'id' in r and 'uses' in r:
                uses[r['id'].split('@')[0]] += r['uses']
    reuse = sum(n >= 5 for n in uses.values()) if len(practice) == cfg.pilot_practice and (uses or any('invocation_records' in r or 'skill_uses' in r for r in practice)) else None
    gate('repeated_skills', reuse, lambda x: x < 10, 'switch_to_scienceworld')
    gate('false_success', _false_success(c + em), lambda x: x > .10, 'tighten_predicates_then_retest')
    programs = sum(r.get('l2_programs', 0) for r in practice)
    bad = sum(r.get('rejected_programs', 0) + r.get('crashing_programs', 0) for r in practice)
    gate('program_failure', _ratio(bad, programs), lambda x: x > .40, 'improve_examples_decoding_or_model')
    return {'gates': gates, 'ready': all(g['status'] == 'pass' for g in gates.values()),
            'switch_domain': any(g['status'] == 'fail' and g['action'] == 'switch_to_scienceworld'
                                 for g in gates.values()), 'practice_episodes': len(practice)}


pilot_gate = pilot_report


def _index(rows):
    result = {}
    for row in rows:
        key = (row['task_id'], row['seed'])
        if key in result:
            raise ValueError(f'duplicate task/seed record: {key}')
        result[key] = row
    return result


def _paired(left, right, cfg):
    a, b = _index(left), _index(right)
    if set(a) != set(b):
        raise ValueError('paired comparison has different task/seed identifiers')
    by_task = defaultdict(set)
    for task, seed in a:
        by_task[task].add(seed)
    expected = set(cfg.seeds)
    if any(seeds != expected for seeds in by_task.values()):
        raise ValueError('each paired task must contain every configured seed')
    if len(by_task) != cfg.evaluation_games:
        raise ValueError('paired comparison must contain every configured evaluation task')
    return a, b, sorted(by_task)


def _bootstrap(differences, samples):
    d = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(0)
    # Batches keep the full study comfortably below a few MB of working memory.
    means = np.concatenate([d[rng.integers(0, len(d), (min(512, samples-i), len(d)))].mean(axis=1)
                            for i in range(0, samples, 512)])
    estimate = float(d.mean())
    low, high = np.quantile(means, [.025, .975])
    # Two-sided centered-bootstrap null with finite Monte Carlo correction.
    p = (1 + int(np.sum(np.abs(means-estimate) >= abs(estimate)-1e-15))) / (samples+1)
    return {'estimate': estimate, 'ci95': [float(low), float(high)], 'p_value': p,
            'tasks': len(d), 'status': 'available'}


def _bootstrap_invocations(counts, samples):
    data = np.asarray(counts, dtype=float)
    total = data.sum(axis=0)
    if total[1] == 0 or total[3] == 0:
        return {'status': 'unavailable', 'reason': 'condition has zero eligible skill invocations'}
    estimate = float(total[0]/total[1] - total[2]/total[3])
    rng = np.random.default_rng(0)
    draws, lower, upper, invalid = [], [], [], 0
    for i in range(0, samples, 512):
        pooled = data[rng.integers(0, len(data), (min(512, samples-i), len(data)))].sum(axis=1)
        valid = (pooled[:, 1] > 0) & (pooled[:, 3] > 0)
        invalid += int((~valid).sum())
        er = np.divide(pooled[:, 0], pooled[:, 1], out=np.zeros(len(pooled)), where=pooled[:, 1] > 0)
        dr = np.divide(pooled[:, 2], pooled[:, 3], out=np.zeros(len(pooled)), where=pooled[:, 3] > 0)
        # Keep zero-use task clusters. Undefined rates range over [0,1], so
        # these draws widen the interval and count as extreme for the p value.
        lower.extend((er - np.where(pooled[:, 3] > 0, dr, 1)).tolist())
        upper.extend((np.where(pooled[:, 1] > 0, er, 1) - dr).tolist())
        draws.extend((er[valid]-dr[valid]).tolist())
    draws = np.asarray(draws)
    lo, hi = float(np.quantile(lower, .025)), float(np.quantile(upper, .975))
    p = (1+invalid+int(np.sum(np.abs(draws-estimate) >= abs(estimate)-1e-15)))/(samples+1)
    return {'status': 'available', 'estimate': estimate, 'ci95': [lo, hi],
            'p_value': p, 'tasks': len(data), 'eligible_invocations': [int(total[1]), int(total[3])],
            'undefined_bootstrap_samples': invalid,
            'zero_denominator_policy': 'undefined resampled rates bounded by [0,1]; conservative CI and p'}


def _cost(practice_costs, condition, seed):
    if condition == 'C':
        return 0.0
    if practice_costs is None:
        return None
    costs = practice_costs.get('E' if condition == 'E-text' else condition, {})
    value = costs.get(seed, costs.get(str(seed)))
    if isinstance(value, dict):
        value = value.get(COST_METRIC)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None


def _comparison(groups, left, right, metric, cfg, practice_costs):
    if not groups.get(left) or not groups.get(right):
        return {'status': 'unavailable', 'reason': 'missing condition'}
    a, b, tasks = _paired(groups[left], groups[right], cfg)
    if metric == 'invocation_success':
        counts = []
        for task in tasks:
            values = []
            for indexed in (a, b):
                numbers = [(_number(indexed[task, seed], 'invocation_successes'),
                            _number(indexed[task, seed], 'invocations')) for seed in cfg.seeds]
                if any(x is None or y is None or y < 0 or x < 0 or x > y for x, y in numbers):
                    return {'status': 'unavailable', 'reason': 'missing or invalid invocation counts'}
                values.extend([sum(x for x, _ in numbers), sum(y for _, y in numbers)])
            counts.append(values)
        return _bootstrap_invocations(counts, cfg.bootstrap_samples)
    differences = []
    for task in tasks:
        vals = []
        for seed in cfg.seeds:
            pair = []
            for condition, indexed in ((left, a), (right, b)):
                row = indexed[task, seed]
                value = _number(row, metric)
                if metric == COST_METRIC:
                    practice = _cost(practice_costs, condition, seed)
                    value = None if value is None or practice is None else value + practice/len(tasks)
                if value is None or (metric == COST_METRIC and value < 0):
                    return {'status': 'unavailable', 'reason': f'missing or invalid {metric} or practice cost accounting'}
                pair.append(value)
            vals.append(pair[0]-pair[1])
        differences.append(sum(vals)/len(vals))
    return _bootstrap(differences, cfg.bootstrap_samples)


def _holm(primary):
    available = sorted(((k, v['p_value']) for k, v in primary.items() if 'p_value' in v), key=lambda x: x[1])
    previous = 0.0
    # The preregistered family always contains four tests, even if some are unavailable.
    for rank, (key, p) in enumerate(available):
        previous = max(previous, min(1.0, (4-rank)*p))
        primary[key]['p_holm'] = previous
        primary[key]['reject_holm_05'] = previous <= .05


def _break_even(groups, cfg, practice_costs):
    if not groups.get('E') or not groups.get('D'):
        return None
    a, b, _ = _paired(groups['E'], groups['D'], cfg)
    results = {}
    for seed in cfg.seeds:
        rows = sorted([r for r in groups['E'] if r['seed'] == seed], key=lambda r: r.get('position', r.get('index', 0)))
        ec, dc = _cost(practice_costs, 'E', seed), _cost(practice_costs, 'D', seed)
        crossing = None
        for i, r in enumerate(rows, 1):
            dr = b[r['task_id'], seed]
            if r.get('position', r.get('index')) != dr.get('position', dr.get('index')):
                raise ValueError('break-even comparison requires identical task order')
            eg, dg = _number(r, COST_METRIC), _number(dr, COST_METRIC)
            if None in (ec, dc, eg, dg) or min(ec, dc, eg, dg) < 0:
                ec = dc = None
                break
            ec += eg
            dc += dg
            if crossing is None and ec < dc:
                crossing = i
        results[str(seed)] = {'first_task': crossing, 'status': 'unavailable' if ec is None else 'available',
                              'final_E': ec, 'final_D': dc}
    return results


def analyze(records, cfg, practice_costs=None):
    """Analyze evaluation records; missing pairs raise, missing measures are unknown.

    practice_costs maps condition -> seed -> total measured GPU seconds (or a
    dict containing weighted_tokens). E-text shares E's practice charge.
    Study success requires the H1 point difference >=10pp OR zero inside H1's
    95% interval with >=30% lower point amortized cost (weighted tokens); AND H3 >0 with its
    Holm-adjusted two-sided test significant at .05. H4 is reported separately.
    """
    rows = [_row(r) for r in records if _row(r).get('phase') == 'evaluation']
    groups = defaultdict(list)
    for row in rows:
        groups[row['condition']].append(row)
    primary = {name: _comparison(groups, 'E', other, metric, cfg, practice_costs)
               for name, other, metric in [('H1', 'D', 'success'), ('H2', 'D', COST_METRIC),
                                            ('H3', 'E-minus', 'invocation_success'), ('H4', 'E-text', 'success')]}
    _holm(primary)
    secondary = {'E_minus_C': _comparison(groups, 'E', 'C', 'success', cfg, practice_costs),
                 'E_minus_Eminus_task_success': _comparison(groups, 'E', 'E-minus', 'success', cfg, practice_costs),
                 # Extension arm (outside the Holm family): does consolidation help E?
                 'Eplus_minus_E': _comparison(groups, 'E-plus', 'E', 'success', cfg, practice_costs),
                 'Eplus_minus_E_invocations': _comparison(groups, 'E-plus', 'E', 'invocation_success', cfg, practice_costs),
                 'Eplus_minus_E_cost': _comparison(groups, 'E-plus', 'E', COST_METRIC, cfg, practice_costs),
                 'break_even': _break_even(groups, cfg, practice_costs), 'conditions': {}}
    for condition, rs in sorted(groups.items()):
        token_values = [None if _number(r, 'input_tokens') is None or _number(r, 'output_tokens') is None
                        else r['input_tokens']+4*r['output_tokens'] for r in rs]
        invocations = sum(r.get('invocations', 0) for r in rs)
        per_skill = defaultdict(lambda: {'successes': 0, 'invocations': 0})
        for r in rs:
            for call in r.get('invocation_records', []):
                sid = call.get('skill_id', call.get('id'))
                if sid:
                    per_skill[sid]['successes'] += bool(call.get('success'))
                    per_skill[sid]['invocations'] += 1
        secondary['conditions'][condition] = {
            'episodes': len(rs), 'success': sum(bool(r['success']) for r in rs)/len(rs),
            'weighted_tokens_per_task': None if None in token_values else sum(token_values)/len(rs),
            'false_success': _false_success(rs),
            'reuse_rate': _ratio(sum(r.get('reused_invocations', 0) for r in rs), invocations),
            'library_size': [r.get('library_size') for r in rs],
            'low_reliability_retrieval_rate': _ratio(sum(r.get('low_reliability_retrievals', 0) for r in rs),
                                                   sum(r.get('retrieved_skill_count', 0) for r in rs)),
            'skill_versions': dict(per_skill),
            'retrieval_errors': sum(not c.get('preconditions_held', True) for r in rs for c in r.get('invocation_records', [])),
            'candidate_rejection_rate': _ratio(sum(r.get('candidate_rejections', 0) for r in rs),
                                                sum(r.get('candidate_versions', 0) for r in rs))}
    h1, h2, h3 = (primary[k] for k in ('H1', 'H2', 'H3'))
    cost_ratio = None
    if h2['status'] == 'available':
        dt = sum(r[COST_METRIC] for r in groups['D']) + sum(_cost(practice_costs, 'D', s) for s in cfg.seeds)
        et = sum(r[COST_METRIC] for r in groups['E']) + sum(_cost(practice_costs, 'E', s) for s in cfg.seeds)
        cost_ratio = _ratio(et, dt)
    benefit = None
    if h1['status'] == 'available':
        benefit = h1['estimate'] >= cfg.success_margin
        if not benefit:
            benefit = (h1['ci95'][0] <= 0 <= h1['ci95'][1] and cost_ratio <= 1-cfg.cost_reduction) if cost_ratio is not None else None
    updating = (h3['estimate'] > 0 and h3['reject_holm_05']) if h3['status'] == 'available' else None
    criterion = False if benefit is False or updating is False else (True if benefit and updating else None)
    return {'primary': primary, 'secondary': secondary, 'study_success': criterion,
            'amortized_cost_ratio_E_D': cost_ratio, 'cost_metric': 'weighted tokens (input + 4 x output)',
            'gpu_seconds_measured': all(r.get('gpu_seconds') is not None for r in rows),
            'method': 'Paired task-cluster percentile bootstrap; equal seed task-success/cost means; pooled eligible invocation ratio resampling task clusters; centered two-sided bootstrap p; Holm family of four.',
            'criterion': 'H1 >=10pp OR zero in H1 CI with >=30% lower amortized weighted-token cost; AND H3 positive and Holm p<=.05.',
            'expected_evaluation_tasks': cfg.evaluation_games, 'toy': any(r.get('toy', False) for r in rows)}
