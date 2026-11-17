"""Library consolidation for condition E-plus (an extension arm, outside the preregistered core).

Every `consolidation_interval` episodes, E-plus runs three maintenance passes on its library:

  cleanup  (evidence) retire skills the evidence says are weak: the actor keeps ignoring them when
                    offered, they fail when chosen, or they were never chosen in two intervals.
                    Length is not a criterion: a one-step skill can be strong and a long one weak.
  compose  (rules)  skill pairs that repeatedly ran back to back become one meta-skill that
                    calls both (call("a@v1", ...) then call("b@v2", ...))
  merge    (model)  near-duplicate skills (same postcondition predicates, similar descriptions)
                    are rewritten by the curator role as one general skill; a skill that is too
                    specific (literal entities in its body, or only ever used with one argument
                    set) is sent alone to be generalized

  lessons  (model + simulation) a reflector turns a recent failure (contrasted with a success at
                    the same kind of task) into one general lesson in plain language; the lesson is
                    admitted only if, in simulation, it turns that failed game into a win and does
                    not break the successful one. Admitted lessons are shown to the actor for that
                    task type and scored by later outcomes; lessons that keep failing are dropped.

Nothing is trusted: a meta-skill or merged skill is admitted only through the library's normal
gate, after replaying every stored test of the skills it replaces and checking that its contract
covers theirs. Retired skills are kept (status "retired") for audit, never deleted, and a skill
that another active skill calls is never retired. Curator calls use the same local model and
their tokens are charged to the episode that triggered consolidation.
"""
import ast
import copy
import re

from .domain import Predicate
from .library import Skill

MERGE_GUIDE = (
    'You maintain a library of reusable ALFWorld skills. The skills below do nearly the same job. '
    'Write ONE general skill that can replace all of them (if only one skill is listed, it is too '
    'specific: rewrite it so it works for any objects and places of the same kind): a general name (no object or '
    'receptacle types in it, e.g. take_object_from_receptacle), parameters for every entity that '
    'differs between them, preconditions that hold for every one of them (use few), '
    'postconditions that include what each of them achieves, and a body of act(...) f-strings '
    'over the parameter names, copying their command words exactly. mappings: for EACH listed '
    'skill id, map every parameter of your skill to the parameter of that skill that plays the '
    'same role, or to the exact entity it hard-codes (e.g. "apple 1"). Example: {"candidate":{"name":"take_object_from_receptacle","description":'
    '"go to a receptacle and take an object from it","parameters":{"obj":"entity","place":'
    '"entity"},"preconditions":[],"postconditions":["holding(obj)"],"body":"act(f\\"go to '
    '{place}\\")\\nact(f\\"take {obj} from {place}\\")"},"mappings":{"take_cd_from_drawer@v1":'
    '{"obj":"cd","place":"drawer"}}}')
MAX_MERGES = 2          # curator calls per consolidation (it runs every batch)
MAX_LESSONS = 1         # reflector proposals (each costs up to 2 simulated episodes) per consolidation
LESSON_CAP = 12         # stored lessons; the lowest-scored go first
LESSONS_SHOWN = 3
LESSON_DROP = -3        # net score (wins - losses while shown) at which a lesson is dropped
REFLECT_GUIDE = (
    'You review an ALFWorld household agent. Given its FAILED attempt at a task (and, if present, a '
    'SUCCESSFUL attempt at the same kind of task), write ONE short general lesson (at most 30 words) '
    'that would help in any game of this kind: where objects tend to be, which commands work and '
    'how they are phrased, or how to order the steps. Never name numbered objects (like "drawer 3"). '
    'Write it as "Don\'t <what went wrong>; instead <what to do>." '
    'Do not repeat an existing lesson. Output {"lesson": "...", "applies_to": "<task type>" or "all"}.')
MIN_OFFERS = 8          # evidence needed before "ignored" can retire a skill
IGNORED_RATE = 0.1      # chosen in fewer than this share of the subgoals it was offered in
MAX_COMPOSES = 3
MAX_GROUP = 5
TESTS_PER_MEMBER = 3


def note(library, sid, event, arguments=None):
    """Usage evidence for E-plus: offered (shown to the actor in a subgoal) / chosen / ok."""
    stats = library.meta.setdefault('stats', {}).setdefault(sid, {'offered': 0, 'chosen': 0, 'ok': 0, 'arguments': []})
    stats[event] += 1
    if arguments is not None:
        key = sorted(arguments.items())
        if key not in [sorted(a.items()) for a in stats['arguments']] and len(stats['arguments']) < 10:
            stats['arguments'].append(dict(arguments))


def literal_entities(skill):
    """Concrete instances written into the body ("go to diningtable 1") instead of parameters."""
    found = []
    for node in ast.walk(ast.parse(skill.body)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += re.findall(r'\b[a-z]+ \d+\b', node.value)
    return found


def too_specific(library, skill):
    stats = library.meta.get('stats', {}).get(skill.id, {})
    return bool(literal_entities(skill)) or (stats.get('chosen', 0) >= 3 and len(stats.get('arguments', [])) == 1)


def weakness(library, cfg, skill):
    """Evidence that a skill does not pull its weight, or None. Never its length."""
    stats = library.meta.get('stats', {}).get(skill.id, {'offered': 0, 'chosen': 0, 'ok': 0})
    if stats['offered'] >= MIN_OFFERS and stats['chosen'] < IGNORED_RATE * stats['offered']:
        return f"ignored: chosen {stats['chosen']} of {stats['offered']} times offered"
    if stats['chosen'] >= cfg.min_uses and stats['ok'] < cfg.low_reliability * stats['chosen']:
        return f"unreliable: {stats['ok']}/{stats['chosen']} succeeded"
    if stats['chosen'] == 0 and library.meta.get('age', {}).get(skill.id, 0) >= 2:
        return 'never chosen in two consolidation intervals'
    return None


def referenced(library, sid):
    return any(f'"{sid}"' in s.body or f"'{sid}'" in s.body for s in library.current() if s.id != sid)


def rename(text, mapping):
    p = Predicate.parse(text)
    return f"{p.name}({', '.join(mapping.get(a, a) for a in p.args)})"


def concrete(texts, bindings):
    return {Predicate.parse(t).bind(bindings) for t in texts}


def track_pair(agent, sid, before, bindings, success, actions_after):
    """Called after each top-level E-plus invocation: usage evidence, and skills that ran back to back."""
    note(agent.library, sid, 'chosen', bindings)
    if success:
        note(agent.library, sid, 'ok')
    previous = agent.last_call
    if (success and previous and previous['actions_after'] == len(before['actions'])
            and previous['sid'] != sid):
        entry = agent.library.meta.setdefault('pairs', {}).setdefault(f"{previous['sid']}>{sid}", {'count': 0})
        entry['count'] += 1
        entry['example'] = {'snapshot': copy.deepcopy(previous['before']),
                            'first': copy.deepcopy(previous['bindings']), 'second': copy.deepcopy(bindings)}
    agent.last_call = ({'sid': sid, 'before': copy.deepcopy(before), 'bindings': copy.deepcopy(bindings),
                        'actions_after': actions_after} if success else None)


def _ask(agent, payload):
    ordinal = agent.result['model_calls']
    agent.result['model_calls'] += 1
    agent.result['curator_calls'] += 1
    response = agent.model.complete('curator', {'task': {}, **payload}, agent.seed,
                                    {**agent.context, 'call_index': ordinal})
    agent.result['input_tokens'] += response.input_tokens
    agent.result['output_tokens'] += response.output_tokens
    agent.result['model_wall_seconds'] += response.wall_seconds
    if response.gpu_seconds is None:
        agent.gpu_known = False
    data = response.data
    if not isinstance(data, dict) or '_response_error' in data:
        raise ValueError('invalid curator response')
    return data


def cleanup(library, cfg, report):
    age = library.meta.setdefault('age', {})
    for s in list(library.current()):
        reason = None if referenced(library, s.id) else weakness(library, cfg, s)
        if reason:
            library.retire(s.id, reason)
            report['retired'].append([s.id, reason])
        else:
            age[s.id] = age.get(s.id, 0) + 1


def compose(agent, report):
    library, meta = agent.library, agent.library.meta
    pairs, done = meta.get('pairs', {}), meta.setdefault('composed', [])
    made = 0
    for key in sorted(pairs, key=lambda k: (-pairs[k]['count'], k)):
        if made >= MAX_COMPOSES:
            break
        entry = pairs[key]
        if entry['count'] < agent.cfg.compose_min_count or key in done:
            continue
        a_id, b_id = key.split('>')
        a, b = library.skills.get(a_id), library.skills.get(b_id)
        if not a or not b or library.active.get(a.name) != a_id or library.active.get(b.name) != b_id:
            continue
        done.append(key)
        example = entry['example']
        # Parameters: a's, plus b's that are not the same concrete entity as one of a's.
        params, bindings, b_map = dict(a.parameters), dict(example['first']), {}
        by_value = {v: k for k, v in example['first'].items()}
        for name in b.parameters:
            value = example['second'][name]
            if value in by_value:
                b_map[name] = by_value[value]
            else:
                new = name if name not in params else f'{name}_2'
                params[new], bindings[new], b_map[name] = 'entity', value, new
        body = (f'call("{a_id}", ' + ', '.join(f'{p}={p}' for p in a.parameters) + ')\n'
                f'call("{b_id}", ' + ', '.join(f'{p}={b_map[p]}' for p in b.parameters) + ')')
        name = f'{a.name}_then_{b.name}'[:60]
        try:
            if name in library.active:
                raise ValueError('meta-skill name already active')
            skill = Skill(library.next_id(name), f'{a.description}; then {b.description}', params,
                          list(a.preconditions), [rename(p, b_map) for p in b.postconditions], body)
            test = {'snapshot': copy.deepcopy(example['snapshot']), 'bindings': bindings}
            if not library.admit(skill, test, agent._verify, updates=True):
                raise ValueError('meta-skill failed its replay test')
            report['composed'].append([skill.id, key])
            made += 1
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['rejected'].append(['compose', key, str(exc)[:200]])


def merge_groups(agent):
    library = agent.library
    skills = [s for s in library.current() if not referenced(library, s.id) and not s.id.split('@')[0].count('_then_')]
    buckets = {}
    for s in skills:
        buckets.setdefault(tuple(sorted({Predicate.parse(p).name for p in s.postconditions})), []).append(s)
    groups = []
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        parent = list(range(len(bucket)))
        def find(i):
            while parent[i] != i:
                i = parent[i]
            return i
        for i, s in enumerate(bucket):
            scores = agent.embedder.similarity(s.description, [t.description for t in bucket])
            for j, score in enumerate(scores):
                if j > i and score >= agent.cfg.merge_similarity:
                    parent[find(j)] = find(i)
        clusters = {}
        for i, s in enumerate(bucket):
            clusters.setdefault(find(i), []).append(s)
        for members in clusters.values():
            if len(members) >= 2:
                members = sorted(members, key=lambda s: (-s.uses, s.id))[:MAX_GROUP]
                groups.append(sorted(members, key=lambda s: s.id))
    grouped = {s.id for g in groups for s in g}
    # A too-specific skill with no near-duplicate is generalized on its own.
    groups += [[s] for s in skills if s.id not in grouped and too_specific(library, s)]
    return sorted(groups, key=lambda g: (-len(g), g[0].id))


def merge(agent, report):
    library = agent.library
    for members in merge_groups(agent)[:MAX_MERGES]:
        ids = [m.id for m in members]
        try:
            data = _ask(agent, {
                'instructions': MERGE_GUIDE, 'allowed_predicates': agent._predicates(),
                'skills': [{**agent._skill_payload(m), 'id': m.id} for m in members],
                'response_schema': {'candidate': {'name': 'lowercase_identifier', 'description': 'string',
                    'parameters': {'parameter': 'entity'}, 'preconditions': ['predicate(arguments)'],
                    'postconditions': ['predicate(arguments)'], 'body': 'safe Python subset string'},
                    'mappings': {'skill id': {'parameter': 'that skill\'s parameter, or an entity it hard-codes'}}}})
            c, mappings = data.get('candidate'), data.get('mappings')
            if not isinstance(c, dict) or not isinstance(mappings, dict):
                raise ValueError('invalid merge object')
            if set(c) != {'name', 'description', 'parameters', 'preconditions', 'postconditions', 'body'}:
                raise ValueError('invalid merge fields')
            if len(members) == 1 and not too_specific(library, members[0]):
                raise ValueError('nothing to generalize')
            if c['name'] in library.active and library.active[c['name']] not in ids:
                raise ValueError('merged name collides with another active skill')
            agent._validate_conditions(c['postconditions'])
            for condition in c['preconditions']:
                Predicate.parse(condition)
            draft = Skill(library.next_id(c['name']), c['description'], c['parameters'],
                          c['preconditions'], c['postconditions'], c['body'])
            tests = []
            for m in members:
                mapping = mappings.get(m.id)
                # Each merged parameter maps to a member parameter, or to a literal entity the
                # member hard-coded (how a too-specific skill is generalized).
                literals = set(literal_entities(m))
                if (not isinstance(mapping, dict) or set(mapping) != set(draft.parameters)
                        or not set(mapping.values()) <= set(m.parameters) | literals):
                    raise ValueError(f'mapping for {m.id} must cover every merged parameter')
                for t in m.tests[:TESTS_PER_MEMBER]:
                    bound = {p: t['bindings'][v] if v in m.parameters else v for p, v in mapping.items()}
                    if not concrete(m.postconditions, t['bindings']) <= concrete(draft.postconditions, bound):
                        raise ValueError(f'merged contract does not cover {m.id}')
                    tests.append({'snapshot': t['snapshot'], 'bindings': bound})
            if not tests:
                raise ValueError('members have no stored tests')
            if not all(agent._verify(draft, t) for t in tests):
                raise ValueError('merged skill failed a member replay test')
            for m in members:
                library.retire(m.id, f'merged into {draft.name}')
            if not library.admit(draft, tests[0], agent._verify, updates=True):
                for m in members:
                    library.unretire(m.id)
                raise ValueError('merged skill failed admission')
            library.skills[draft.id].tests = copy.deepcopy(tests[:agent.cfg.test_limit])
            report['merged'].append([draft.id, ids])
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['rejected'].append(['merge', ids, str(exc)[:200]])


def lessons_for(library, task_type):
    """Lessons shown to the actor: those for this task type or for all, best scored first."""
    lessons = [l for l in library.meta.get('lessons', []) if l['applies_to'] in (task_type, 'all')]
    return [l['text'] for l in sorted(lessons, key=lambda l: (-l['score'], l['id']))[:LESSONS_SHOWN]]


def _compact(agent):
    return {'task': copy.deepcopy(agent.task), 'goal': agent.result.get('goal', ''),
            'actions': [t['action'] for t in agent.result['trace'] if t.get('valid')][-40:],
            'final': (agent.result['trace'][-1]['after'] if agent.result['trace'] else '')[:400]}


def record_episode(agent):
    """After each E-plus episode: score the lessons shown, and keep material for the reflector."""
    meta, won = agent.library.meta, agent.result['success']
    shown = set(agent.lessons_shown)
    for lesson in meta.get('lessons', []):
        if lesson['text'] in shown:
            lesson['score'] += 1 if won else -1
            lesson['shown'] += 1
    kind = agent.task.get('task_type', 'all')
    if won:
        meta.setdefault('successes', {})[kind] = _compact(agent)
    else:
        meta['failures'] = (meta.get('failures', []) + [_compact(agent)])[-6:]


def _simulate(agent, task, lessons, tag, harvest=None):
    """One simulated episode with exactly these lessons; its tokens are charged to this episode.

    The simulation runs on a copy of the library. If it is won, the skills it wrote (from the whole
    winning game) are put in `harvest`; they enter the real library only if the lesson is admitted.
    """
    from .agents import Agent
    from .library import Library
    copy_library = Library.restore(agent.library.snapshot(), agent.cfg)
    sim = Agent(agent.cfg, 'E-plus', agent.model, copy_library, agent.embedder, agent.env_factory,
                lessons=lessons, simulation=True)
    result = sim.run(task, agent.seed, {**agent.context, 'simulation': tag})
    if harvest is not None and result['success']:
        known = set(agent.library.skills)
        harvest += [copy.deepcopy(s) for s in copy_library.current() if s.id not in known]
    for key in ('model_calls', 'input_tokens', 'output_tokens', 'model_wall_seconds'):
        agent.result[key] += result[key]
    agent.result['simulated_episodes'] = agent.result.get('simulated_episodes', 0) + 1
    if result.get('gpu_seconds') is None:
        agent.gpu_known = False
    return result['success']


def lessons(agent, report):
    meta = agent.library.meta
    failures, store = meta.get('failures', []), meta.setdefault('lessons', [])
    meta['failures'] = []
    for n, failure in enumerate(reversed(failures[-MAX_LESSONS:])):
        kind = failure['task'].get('task_type', 'all')
        success = meta.get('successes', {}).get(kind)
        try:
            data = _ask(agent, {'instructions': REFLECT_GUIDE, 'task_type': kind, 'failed_attempt': failure,
                                'successful_attempt': success, 'existing_lessons': [l['text'] for l in store],
                                'response_schema': {'lesson': 'string', 'applies_to': 'task type or all'}})
            text = data.get('lesson')
            if not isinstance(text, str) or not 5 <= len(text) <= 300 or text in [l['text'] for l in store]:
                raise ValueError('invalid or repeated lesson')
            if re.search(r'\b[a-z]+ \d+\b', text):
                raise ValueError('lesson names a numbered object')
            applies = data.get('applies_to') if data.get('applies_to') in (kind, 'all') else kind
            current = lessons_for(agent.library, kind)
            # Simulation: the lesson must turn the failed game into a win ...
            harvest = []
            if not _simulate(agent, failure['task'], current[:LESSONS_SHOWN - 1] + [text], f'lesson{n}-fail', harvest):
                raise ValueError('lesson did not fix the failed game in simulation')
            # ... and must not break a game of the same kind that was won.
            if success and not _simulate(agent, success['task'], current[:LESSONS_SHOWN - 1] + [text], f'lesson{n}-win'):
                raise ValueError('lesson broke a won game in simulation')
            store.append({'id': f"lesson{meta.get('consolidations', 0)}_{n}", 'text': text, 'applies_to': applies,
                          'score': 0, 'shown': 0})
            report['lessons'].append(text)
            # ... and the skills written from that now-winning game are kept ("what to do instead").
            for skill in harvest:
                if skill.name not in agent.library.active and skill.id not in agent.library.skills:
                    agent.library.skills[skill.id] = skill
                    agent.library.active[skill.name] = skill.id
                    report['harvested'].append(skill.id)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['rejected'].append(['lesson', kind, str(exc)[:200]])
    kept = [l for l in store if l['score'] > LESSON_DROP]
    report['lessons_dropped'] = [l['text'] for l in store if l['score'] <= LESSON_DROP]
    meta['lessons'] = sorted(kept, key=lambda l: (-l['score'], l['id']))[:LESSON_CAP]


def consolidate(agent):
    report = {'retired': [], 'composed': [], 'merged': [], 'lessons': [], 'harvested': [], 'rejected': []}
    library = agent.library
    before = len(library.current())
    cleanup(library, agent.cfg, report)
    compose(agent, report)
    merge(agent, report)
    lessons(agent, report)
    library.meta['consolidations'] = library.meta.get('consolidations', 0) + 1
    report['library_before'], report['library_after'] = before, len(library.current())
    return report
