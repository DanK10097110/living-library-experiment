"""A rule manual built from experience, after AutoManual (Chen et al., NeurIPS 2024, arXiv 2405.16247).

Adapted to this agent (a hierarchical step-by-step ReAct agent, not a code-writing planner):
  * A rule has a type, the rule text (it starts with when it applies), an example (a short action
    sequence or observation, not Python) and a validation note (AutoManual's validation log; never
    shown to the agent).
  * Types, as in AutoManual: Special Phenomenon/Mechanism, Success Process, Corrected Error,
    Unresolved Error. AutoManual's fifth type, Useful Helper Method (code), is this project's
    replay-verified code skill library, which keeps running alongside the manual.
  * After every practice game a Builder (the same local model) sees the game and the current rules.
    The case is decided from the game: direct success (won without an invalid action), indirect
    success (won after errors), failure. Case-conditioned prompting, as in AutoManual: the Builder
    first says whether the rules or the agent fell short, and each case limits what it may write.
    The limits are enforced in code, not only asked for.
  * No cap on the number of rules (AutoManual caps at 12 because it puts every rule in every prompt).
    Instead each rule carries a scope: the kind of task it came from, or "all". A game sees only the
    relevant rules (its kind's Success Process, then its kind's and general rules, newest first, at
    most SHOWN), and the Builder sees the rules relevant to the game it reviews (at most BUILDER_SEES),
    as the AutoManual authors suggest for scaling (retrieval, as in AutoGuide). The Builder still
    prefers updating a related rule to writing a near-duplicate; one Success Process per task kind.
  * E-minus (append-only) may only write new rules: no update, no delete, no merge.

Rule management follows ExpeL (Zhao et al., AAAI 2024, section 4.2): a new rule has importance 2;
UPVOTE and EDIT add 1, DOWNVOTE subtracts 1, and a rule is removed when its importance reaches 0. There
is no direct delete: a wrong rule disappears only after repeated disagreement, so one bad Builder call
cannot erase a good rule. Merging = edit one rule, downvote the other.

Selection and upkeep follow MACLA (Forouzandeh et al., AAMAS 2026, arXiv 2512.18950), implemented
from the paper (its released code does not implement these parts):
  * Bayesian reliability (sec. 4.2): each rule has Beta(alpha, beta), prior Beta(1, 1). After a
    practice game every rule the agent was shown gets alpha+1 if the game was won, else beta+1
    (MACLA checks a procedure's postconditions; a rule has none, so the game outcome is the signal).
  * Expected-utility selection (eq. 4): EU = Rel * mean * R_MAX - Risk * (1 - mean) * C_FAIL
    + LAMBDA_INFO * H[Beta], with Rel = embedding similarity of task and rule, Risk = the rule's share
    of failures on this kind of task. The kind's Success Process is always shown first.
  * Contrastive refinement (sec. 4.3): once a rule has >= MIN_CONTRAST won and lost games since its
    last refinement, the model compares them and rewrites the rule (tighter "When ..." condition,
    corrected steps). Contexts are kept per rule, at most K_CONTEXTS of each.
  * Merging (sec. 4.1/5.1): a new rule with similarity >= DUP_SIMILARITY to an existing rule of the
    same type and kind is merged into it (counted as agreement) instead of added.
  * Pruning (eq. 8): above CAPACITY rules, drop the lowest U = 0.5 mean + 0.3 use share + 0.2 recency.
  * Not taken: meta-procedures (the paper's description is inconsistent and its code never uses them).
E-minus is append-only: no Beta updates, refinement, merging or pruning.

The Builder answers with JSON operations (write_rule / update_rule / upvote_rule / downvote_rule),
never code.
"""
import math

from scipy.stats import beta as beta_distribution

R_MAX, C_FAIL, LAMBDA_INFO = 1.0, 0.5, 0.1     # MACLA sec. 5.1 / appendix C.2
MIN_CONTRAST = 3                                # MACLA sec. 5.1: >= 3 successes and >= 3 failures
K_CONTEXTS = 15                                 # MACLA sec. 5.1: K_fail
DUP_SIMILARITY = 0.85                           # MACLA sec. 5.1: theta_dup
CAPACITY = 200                                  # MACLA sec. 5.1: N_p
TAU = 100.0                                     # recency scale for pruning, in practice games
REFINE_GUIDE = (
    'A rule from an agent\'s manual was shown in several games of a household text game (ALFWorld). '
    'In some the agent won, in others it lost. Compare the won and lost games and rewrite the rule so it '
    'helps in cases like the won ones and does not mislead in cases like the lost ones: make its "When ..." '
    'condition more precise and correct its steps. Keep it short, keep its type, and do not invent '
    'commands the games did not show. Output {"rule": "...", "not_when": "a short condition under which '
    'the rule should not be used, or empty"}.')
NEW_IMPORTANCE = 2
import copy

SHOWN = 8           # rules shown to the planner and actor in a game
BUILDER_SEES = 24   # rules shown to the Builder for the game it reviews
TYPES = ('Special Phenomenon', 'Success Process', 'Corrected Error', 'Unresolved Error')
CASE_TYPES = {      # which rule types each case may WRITE (updates follow the same limits)
    'direct success': ('Success Process', 'Special Phenomenon'),
    'indirect success': ('Success Process', 'Special Phenomenon', 'Corrected Error'),
    'failure': ('Unresolved Error', 'Special Phenomenon'),
}
MAX_WRITES = {'direct success': 2, 'indirect success': 2, 'failure': 1}

BUILDER_GUIDE = (
    'You maintain a short manual of rules for an agent that does household tasks in a text game '
    '(ALFWorld). You get one finished game (its task, whether it was won, and its steps with what the '
    'game answered) and the current rules. Rule types: "Special Phenomenon" (how this game behaves, '
    'e.g. which commands work and how they must be phrased, where objects tend to be); "Success '
    'Process" (the steps that solve a kind of task, as a numbered list); "Corrected Error" (a mistake '
    'the agent made and then fixed, and what to do instead); "Unresolved Error" (what went wrong in a '
    'lost game: the situation, the action and the result, without guessing the cause). '
    'Every rule starts with when it applies (e.g. "When the task is to heat an object, ..."). '
    'Write only what this game shows; do not invent commands or places it did not show. Never name '
    'numbered objects ("drawer 3") in the rule text; the example may quote real steps. '
    'First set "diagnosis": "imperfect rules" if the game met something the rules do not cover or no '
    'Success Process exists for this kind of task, else "imperfect agent" if the rules covered it but '
    'the agent did not follow them. Then give "operations": write_rule {type, rule, example, scope}, where '
    'scope is "task" if the rule is about this kind of task only and "all" if it holds in every task; '
    'update_rule {id, and any of rule, example, validation} to add details to an existing rule '
    '(prefer this over writing a near-duplicate); upvote_rule {id} when this game confirms a rule; '
    'downvote_rule {id} when this game contradicts a rule or shows it is wrong (also downvote a rule you '
    'merged into another). Each rule has an importance; rules that reach 0 are removed. Never merge two '
    'Success Process rules. There is at most one Success Process per kind of task (task_type): if '
    'one exists for this kind of task, update it with what this game adds. Use "validation" to note when a later game confirmed or contradicted a '
    'rule, in one short sentence. Output {"diagnosis": "...", "operations": [...]}; an empty list is fine.')
CASE_NOTES = {
    'direct success': ' This game was won without mistakes: you may write or update a Success Process '
                      'and Special Phenomenon rules only.',
    'indirect success': ' This game was won after mistakes: if the rules fell short, write a Corrected '
                        'Error for the main mistake and a Success Process; if the agent ignored existing '
                        'rules, update those rules to stress what was ignored instead.',
    'failure': ' This game was lost: if the rules fell short, write at most ONE Unresolved Error rule; '
               'if the agent ignored existing rules, update them to stress what was ignored. Never '
               'write a Success Process from a lost game.',
}
APPEND_ONLY_NOTE = ' Append-only manual: you may only use write_rule; existing rules cannot be changed.'


def case_of(result):
    if not result['success']:
        return 'failure'
    return 'direct success' if all(t['valid'] for t in result['trace']) else 'indirect success'


def reliability(rule):
    return rule.get('alpha', 1) / (rule.get('alpha', 1) + rule.get('beta', 1))


def expected_utility(rule, relevance, task_type):
    """MACLA eq. 4."""
    a, b = rule.get('alpha', 1), rule.get('beta', 1)
    mean = a / (a + b)
    same = [c for c in rule.get('contexts', []) if c.get('task_type') == task_type]
    risk = sum(not c['won'] for c in same) / len(same) if same else 0.0
    return relevance * mean * R_MAX - risk * (1 - mean) * C_FAIL + LAMBDA_INFO * float(beta_distribution(a, b).entropy())


def relevant(rules, task_type, k, query=None, similarity=None):
    """This kind of task's Success Process first, then its other rules and the general ones, ranked by
    MACLA's expected utility when a query and similarity function are given, else by importance."""
    def number(r):
        return int(r['id'].split('_')[1])
    recipe = [r for r in rules if r['type'] == 'Success Process' and r.get('task_type') == task_type]
    others = [r for r in rules if r not in recipe and r['type'] != 'Success Process'
              and r.get('task_type') in (task_type, 'all', None)]
    if query and similarity and others:
        scores = similarity(query, [r['rule'] for r in others])
        utility = {id(r): expected_utility(r, max(0.0, float(sc)), task_type) for r, sc in zip(others, scores)}
        others.sort(key=lambda r: (utility[id(r)], number(r)), reverse=True)
    else:
        others.sort(key=lambda r: (r.get('importance', NEW_IMPORTANCE), number(r)), reverse=True)
    return (recipe + others)[:k]


def new_rule(rule_id, kind, text, example, task_type):
    return {'id': rule_id, 'type': kind, 'rule': text, 'example': example, 'validation': '',
            'importance': NEW_IMPORTANCE, 'task_type': task_type, 'alpha': 1, 'beta': 1,
            'contexts': [], 'refined_at': [0, 0], 'last_used': None}


def render(rules, limit=300):
    """The rules as the planner and actor see them (validation notes are not shown)."""
    return [f"[{r['type']}] {r['rule']}" + (f" Example: {r['example'][:limit]}" if r.get('example') else '')
            for r in rules]


def _game(result, task_goal, max_steps=40):
    steps = [{'action': t['action'], 'valid': t['valid'], 'result': t['after'][:200]} for t in result['trace']]
    return {'task': task_goal, 'won': result['success'], 'steps': steps[-max_steps:]}


def apply(rules, operations, case, append_only, next_id, log, task_type=None, visible=None, similarity=None):
    """Apply Builder operations under the case limits; returns the applied operations (for batching).
    `visible`: ids the Builder was shown (it may only change those); default all."""
    applied, writes = [], 0
    visible = {r['id'] for r in rules} if visible is None else set(visible)
    by_id = {r['id']: r for r in rules}
    allowed = CASE_TYPES[case]
    for op in operations if isinstance(operations, list) else []:
        if not isinstance(op, dict):
            continue
        kind = op.get('op')
        try:
            if kind == 'write_rule':
                if op.get('type') not in TYPES or not isinstance(op.get('rule'), str) or not op['rule'].strip():
                    raise ValueError('rule needs a known type and text')
                if op['type'] not in allowed:
                    raise ValueError(f"a {case} may not write a {op['type']} rule")
                if writes >= MAX_WRITES[case]:
                    raise ValueError(f'a {case} may write at most {MAX_WRITES[case]} rule(s)')
                if any(r['rule'].strip() == op['rule'].strip() for r in rules):
                    raise ValueError('duplicate rule')
                if op['type'] == 'Success Process':
                    # As in AutoManual: one Success Process per kind of task; later games refine it.
                    existing = next((r for r in rules if r['type'] == 'Success Process'
                                     and r.get('task_type') == task_type), None)
                    if existing is not None:
                        raise ValueError(f"a Success Process for this kind of task exists ({existing['id']}): "
                                         'update it instead')
                scope = 'all' if op.get('scope') == 'all' and op['type'] != 'Success Process' else task_type
                twin = None if append_only or similarity is None else near_duplicate(
                    rules, op['type'], scope, op['rule'].strip(), similarity)
                if twin is not None:
                    # MACLA: merge into the existing rule instead of adding a near-copy (counts as agreement).
                    vote(rules, by_id, twin['id'], 1)
                    applied.append({'op': 'upvote_rule', 'id': twin['id']})
                    log.append(f"merged a new rule into {twin['id']}")
                    continue
                rule = new_rule(next_id(), op['type'], op['rule'].strip()[:600], str(op.get('example') or '')[:600],
                                scope)
                rules.append(rule)
                by_id[rule['id']] = rule
                writes += 1
                applied.append({'op': 'write_rule', **{k: rule[k] for k in ('type', 'rule', 'example', 'task_type')}})
            elif kind in ('update_rule', 'upvote_rule', 'downvote_rule'):
                if append_only:
                    raise ValueError('append-only manual: rules cannot be changed')
                rule = by_id.get(op.get('id'))
                if rule is None or rule.get('id') not in visible:
                    raise ValueError(f"unknown rule id {op.get('id')}")
                if kind != 'update_rule':
                    delta = 1 if kind == 'upvote_rule' else -1
                    if vote(rules, by_id, rule['id'], delta):
                        log.append(f"removed {rule['id']} (importance reached 0)")
                    applied.append({'op': kind, 'id': rule['id']})
                    continue
                changes = {k: str(op[k])[:600] for k in ('rule', 'example', 'validation') if isinstance(op.get(k), str)}
                if not changes:
                    raise ValueError('update needs rule, example or validation')
                if 'validation' in changes:   # keep the last few notes, as AutoManual does
                    changes['validation'] = ' | '.join(([rule['validation']] if rule['validation'] else [])
                                                       + [changes['validation']]).split(' | ')[-3:]
                    changes['validation'] = ' | '.join(changes['validation'])
                rule.update(changes)
                vote(rules, by_id, rule['id'], 1)            # ExpeL: EDIT also counts as agreement
                applied.append({'op': 'update_rule', 'id': rule['id'], **changes})
            else:
                raise ValueError(f'unknown operation {kind!r}')
        except ValueError as exc:
            log.append(str(exc))
    return applied


def near_duplicate(rules, kind, scope, text, similarity):
    pool = [r for r in rules if r['type'] == kind and r.get('task_type') == scope]
    if not pool:
        return None
    scores = [float(x) for x in similarity(text, [r['rule'] for r in pool])]
    best = max(range(len(pool)), key=lambda i: scores[i])
    return pool[best] if scores[best] >= DUP_SIMILARITY else None


def observe(rules, shown_ids, won, context, position):
    """MACLA Beta update and contrastive contexts for the rules shown in a game; returns the op."""
    op = {'op': 'outcome', 'ids': list(shown_ids), 'won': bool(won), 'context': context, 'position': position}
    _observe(rules, op)
    return op


def _observe(rules, op):
    by_id = {r['id']: r for r in rules}
    for rule_id in op['ids']:
        rule = by_id.get(rule_id)
        if rule is None:
            continue
        key = 'alpha' if op['won'] else 'beta'
        rule[key] = rule.get(key, 1) + 1
        contexts = rule.get('contexts', []) + [{**op['context'], 'won': op['won']}]
        won = [c for c in contexts if c['won']][-K_CONTEXTS:]        # keep the newest K of each kind
        lost = [c for c in contexts if not c['won']][-K_CONTEXTS:]
        rule['contexts'] = won + lost
        rule['last_used'] = op['position']


def observed(rule):
    """Games won / lost while this rule was shown (from Beta(1, 1); contexts are capped, counts are not)."""
    return [rule.get('alpha', 1) - 1, rule.get('beta', 1) - 1]


def refinable(rule):
    won, lost = observed(rule)
    done = rule.get('refined_at', [0, 0])
    return won - done[0] >= MIN_CONTRAST and lost - done[1] >= MIN_CONTRAST


def refine(agent, rules, candidates, report):
    """MACLA contrastive refinement of at most one rule per game (cost control)."""
    for rule in candidates:
        if not refinable(rule):
            continue
        won = [c for c in rule['contexts'] if c['won']][-MIN_CONTRAST * 2:]
        lost = [c for c in rule['contexts'] if not c['won']][-MIN_CONTRAST * 2:]
        try:
            data = agent._ask('refiner', {'instructions': REFINE_GUIDE,
                                          'rule': {k: rule[k] for k in ('type', 'rule', 'example')},
                                          'won_games': won, 'lost_games': lost,
                                          'response_schema': {'rule': 'string', 'not_when': 'string'}})
            text = data.get('rule')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('refiner gave no rule')
            not_when = data.get('not_when') if isinstance(data.get('not_when'), str) else ''
            text = text.strip()[:600] + (f' Do not use it when {not_when.strip().rstrip(".")}.' if not_when.strip() else '')
            op = {'op': 'refine', 'id': rule['id'], 'rule': text, 'refined_at': observed(rule)}
            _refine(rules, op)
            report['operations'].append(op)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['errors'].append(f'refiner: {exc}'[:200])
        return


def _refine(rules, op):
    for rule in rules:
        if rule['id'] == op['id']:
            rule['rule'], rule['refined_at'] = op['rule'], op['refined_at']


def prune(rules, position, log):
    """MACLA eq. 8 above CAPACITY: drop the lowest 0.5 mean + 0.3 use share + 0.2 recency."""
    total = sum(r.get('alpha', 1) + r.get('beta', 1) - 2 for r in rules) or 1
    while len(rules) > CAPACITY:
        def utility(r):
            uses = r.get('alpha', 1) + r.get('beta', 1) - 2
            age = position - (r['last_used'] if r.get('last_used') is not None else 0)
            return 0.5 * reliability(r) + 0.3 * uses / total + 0.2 * math.exp(-max(age, 0) / TAU)
        victim = min(rules, key=utility)
        rules.remove(victim)
        log.append(f"pruned {victim['id']} (lowest utility)")


def vote(rules, by_id, rule_id, delta):
    """Change a rule's importance; remove it at 0. Returns True if it was removed."""
    rule = by_id[rule_id]
    rule['importance'] = rule.get('importance', NEW_IMPORTANCE) + delta
    if rule['importance'] <= 0:
        rules.remove(rule)
        del by_id[rule_id]
        return True
    return False


def build(agent):
    """One Builder pass after a practice game. Mutates agent.rules; returns a report."""
    rules, report = agent.rules, {'case': case_of(agent.result), 'operations': [], 'errors': []}
    append_only = agent.condition == 'E-minus'
    counter = [max([int(r['id'].split('_')[1]) for r in rules] + [0])]

    def next_id():
        counter[0] += 1
        return f'rule_{counter[0]}'
    position = agent.context.get('position', 0)
    if not append_only and agent.rules_shown:
        report['operations'].append(observe(rules, agent.rules_shown, agent.result['success'],
                                            {'task': agent.public_task.get('goal', ''),
                                             'task_type': agent.task.get('task_type'),
                                             'steps': [t['action'] for t in agent.result['trace'] if t['valid']][-12:]},
                                            position))
    shown = relevant(rules, agent.task.get('task_type'), BUILDER_SEES)
    guide = BUILDER_GUIDE + CASE_NOTES[report['case']] + (APPEND_ONLY_NOTE if append_only else '')
    try:
        data = agent._ask('builder', {
            'instructions': guide,
            'game': _game(agent.result, agent.public_task.get('goal', '')),
            'task_type': agent.task.get('task_type'),
            'rules': [{k: r.get(k, NEW_IMPORTANCE if k == 'importance' else '')
                       for k in ('id', 'type', 'rule', 'example', 'validation', 'importance')} for r in shown],
            'response_schema': {'diagnosis': 'imperfect rules | imperfect agent',
                                'operations': [{'op': 'write_rule | update_rule | upvote_rule | downvote_rule', 'id': 'rule_N',
                                                'type': '|'.join(TYPES), 'rule': 'string', 'example': 'string',
                                                'validation': 'string'}]}})
        report['diagnosis'] = data.get('diagnosis')
        report['operations'] += apply(rules, data.get('operations'), report['case'], append_only, next_id,
                                      report['errors'], agent.task.get('task_type'), [r['id'] for r in shown],
                                      agent.embedder.similarity)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        report['errors'].append(f'builder: {exc}'[:200])
    if not append_only:
        refine(agent, rules, [r for r in rules if r['id'] in set(agent.rules_shown)], report)
        before = {r['id'] for r in rules}
        prune(rules, position, report['errors'])
        for gone in before - {r['id'] for r in rules}:
            report['operations'].append({'op': 'prune', 'id': gone})
    return report


def replay(live, operations, log):
    """Batching: apply one game's applied operations onto the live rules (ids re-issued for writes)."""
    rules = copy.deepcopy(live)
    by_id = {r['id']: r for r in rules}
    counter = max([int(r['id'].split('_')[1]) for r in rules] + [0])
    for op in operations:
        if op['op'] == 'outcome':
            _observe(rules, op)
            continue
        if op['op'] == 'refine':
            _refine(rules, op)
            continue
        if op['op'] == 'prune':
            if op['id'] in by_id:
                rules.remove(by_id.pop(op['id']))
            continue
        if op['op'] == 'write_rule':
            if any(r['rule'] == op['rule'] for r in rules) or (
                    op['type'] == 'Success Process' and any(r['type'] == 'Success Process' and
                                                             r.get('task_type') == op.get('task_type') for r in rules)):
                log.append(['duplicate rule', op['rule'][:60]])
                continue
            counter += 1
            rule = new_rule(f'rule_{counter}', op['type'], op['rule'], op['example'], op.get('task_type'))
            rules.append(rule)
            by_id[rule['id']] = rule
        elif op['id'] not in by_id:
            log.append(['rule already gone', op['id']])
        elif op['op'] in ('upvote_rule', 'downvote_rule'):
            vote(rules, by_id, op['id'], 1 if op['op'] == 'upvote_rule' else -1)
        else:
            by_id[op['id']].update({k: v for k, v in op.items() if k in ('rule', 'example', 'validation')})
            vote(rules, by_id, op['id'], 1)
    return rules
