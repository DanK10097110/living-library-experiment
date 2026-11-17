"""Bounded flat/hierarchical execution and isolated skill admission."""
import copy
import re
import time

from . import consolidation, manual, react
from .config import CONDITIONS
from .domain import Episode, ActionError, BudgetExceeded, Predicate
from .library import Skill
from .program import Program, InvalidProgram


PREDICATES = ('Predicates: located(obj, place) obj is in/on place; at(place) you are at place; '
              'holding(obj) you carry obj; is_open/is_hot/is_cold/is_clean/is_on/is_toggled(x); '
              'exists(x); task_won(). ')
# Fixed role guides (one worked example each); part of the frozen settings. Acting itself uses the
# published ALFWorld ReAct prompt (react.py).
PLANNER_GUIDE = (
    PREDICATES + 'Split the task into 1-6 ordered subgoals. bindings map short parameter names (obj, place, '
    'sink, tool...) to entity names exactly as written in the observation (e.g. "sinkbasin 1"), or to '
    'the bare type (e.g. "mug") for an object whose instance you have not seen yet. postconditions use only '
    'allowed predicates; arguments may be parameter names or entity names. Example for "put a clean '
    'mug in coffeemachine": {"subgoals":[{"description":"find and take a mug","bindings":{"obj":"mug"},'
    '"postconditions":["holding(obj)"]},{"description":"clean the mug at the sink","bindings":'
    '{"obj":"mug","sink":"sinkbasin 1"},"postconditions":["is_clean(obj)"]},{"description":'
    '"put the mug in the coffeemachine","bindings":{"obj":"mug","place":"coffeemachine 1"},'
    '"postconditions":["located(obj, place)"]}]}')
LIBRARIAN_GUIDE = (
    PREDICATES + 'Turn the valid actions that achieved the goal, starting from start_observation, into a '
    'reusable skill. name: the general action, never specific object or receptacle types '
    '(e.g. put_object_in_receptacle, clean_object, heat_object, take_object_from_receptacle). '
    'parameters: one lowercase name per entity the body uses, each mapped to "entity"; reuse '
    "parameter_names for the goal's entities. arguments: the concrete entity each parameter had in "
    'these actions. The body copies the actions exactly (same command words, e.g. "move X to Y") as '
    'act(...) f-strings over the parameter names; keep every needed action (e.g. open before '
    'putting). preconditions and postconditions are allowed predicates over parameter '
    'names; preconditions must already hold in start_observation (use few); postconditions must '
    'include the goal postconditions. Example: '
    r'{"candidate":{"name":"clean_object","description":"take an object to a sink and clean it",'
    r'"parameters":{"obj":"entity","sink":"entity"},"preconditions":["holding(obj)"],'
    r'"postconditions":["is_clean(obj)"],"body":"act(f\"go to {sink}\")\nact(f\"clean {obj} with {sink}\")"},'
    r'"arguments":{"obj":"mug 1","sink":"sinkbasin 1"}}'
    ". For a revision, keep the parent's parameters and conditions and fix the body using its "
    'failure notes.')


WHOLE_GAME_NOTE = (
    ' whole_game shows every action of the complete game this subgoal belongs to, which was won. '
    'Write the skill so it is useful wherever this kind of subgoal comes up, not just in this game.')


REFINE_NOTE = (
    ' Your previous_attempt failed verification with the error shown in error (it was executed from '
    'start_observation with your arguments). Fix the skill so it works: keep the actions exactly as '
    'they were performed, and use only preconditions that hold in start_observation.')


class Agent:
    def __init__(self, cfg, condition, model, library, embedder, env_factory, trajectories=None, frozen=False,
                 lessons=None, simulation=False, rules=None):
        if condition not in CONDITIONS:
            raise ValueError('unknown experimental condition')
        self.cfg, self.condition, self.model = cfg, condition, model
        self.library, self.embedder, self.env_factory = library, embedder, env_factory
        self.trajectories = trajectories if trajectories is not None else []
        # AutoManual-style rule manual (manual.py): E and E-minus build it in practice; E-text reads E's.
        self.rules = rules if rules is not None else []
        self.uses_rules = condition in {'E', 'E-minus', 'E-text'}
        self.memory = condition in {'B', 'E', 'E-minus', 'E-text', 'E-plus'}
        # frozen: read the memory as it is (snapshot evaluations); learn nothing, change nothing.
        self.frozen = frozen
        # simulation: an E-plus lesson check; it may write skills (harvested only if the lesson is
        # admitted) but records no usage evidence and never consolidates.
        self.simulation = simulation
        self.live = condition == 'E-plus' and not frozen and not simulation
        self.unbudgeted = False
        self.forced_lessons = lessons   # lesson validation runs supply the exact lessons to show
        self.updates = condition in {'B', 'E', 'E-plus'} and not frozen

    def _ask(self, role, payload):
        if self.result['model_calls'] >= self.cfg.max_model_calls and not self.unbudgeted:
            raise BudgetExceeded('model call budget exhausted')
        ordinal = self.result['model_calls']
        self.result['model_calls'] += 1
        try:
            response = self.model.complete(role, {'task': self.public_task, **payload}, self.seed,
                                           {**self.context, 'call_index': ordinal})
        except Exception:
            # A missing response is unknown cost, never a zero-cost inference.
            self.gpu_known = False
            raise
        self.result['input_tokens'] += response.input_tokens
        self.result['output_tokens'] += response.output_tokens
        self.result['model_wall_seconds'] += response.wall_seconds
        if response.gpu_seconds is None:
            self.gpu_known = False
        else:
            self.gpu += response.gpu_seconds
        if isinstance(response.data, dict) and '_response_error' in response.data:
            raise ValueError(response.data['_response_error'])
        if not isinstance(response.data, dict):
            raise ValueError('model response must be an object')
        return response.data

    def _goals(self, state):
        whole = [{'description': 'complete the task', 'bindings': self._task_bindings(), 'postconditions': ['task_won()']}]
        if self.condition in {'A', 'B'}:
            return whole
        try:
            return self._plan(state)
        except BudgetExceeded:
            raise
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.result['program_errors'].append('planner: ' + str(exc))
            self.result['planner_fallbacks'] += 1
            return whole

    def _plan(self, state):
        data = self._ask('planner', {'instructions': PLANNER_GUIDE, 'state': state.public(),
            'catalog': self.library.catalog() if self.memory else [],
            **({'rules': manual.render(self.shown_rules)} if self.shown_rules else {}),
            'allowed_predicates': self._predicates(),
            'response_schema': {'subgoals': [{'description': 'string', 'bindings': {'parameter': 'entity string'}, 'postconditions': ['predicate(arguments)']}]}})
        if set(data) != {'subgoals'} or not isinstance(data['subgoals'], list) or not 1 <= len(data['subgoals']) <= self.cfg.max_subgoals:
            raise ValueError('invalid bounded subgoal list')
        for goal in data['subgoals']:
            if set(goal) != {'description', 'bindings', 'postconditions'} or not isinstance(goal['description'], str) or not goal['description']:
                raise ValueError('invalid subgoal')
            self._validate_bindings(goal['bindings'], state)
            self._validate_conditions(goal['postconditions'])
        return data['subgoals']

    @staticmethod
    def _predicates():
        from .domain import ARITY
        return ARITY

    @staticmethod
    def _validate_conditions(conditions):
        if not isinstance(conditions, list) or not 1 <= len(conditions) <= 20:
            raise ValueError('nonempty bounded postcondition list required')
        for condition in conditions:
            if not isinstance(condition, str):
                raise ValueError('predicates must be strings')
            Predicate.parse(condition)

    @staticmethod
    def _validate_bindings(bindings, state):
        if not isinstance(bindings, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not state.resolves(v) for k, v in bindings.items()):
            raise ValueError('bindings must name present entities or their types')

    def _task_bindings(self):
        return {k: self.task[k] for k in ('object', 'target') if k in self.task}

    def _invoke(self, sid, bindings, episode, depth=0, record=True):
        self.invocation_steps += 1
        if depth >= self.cfg.call_depth or self.invocation_steps > self.cfg.program_budget:
            raise BudgetExceeded('skill invocation budget exhausted')
        if sid not in self.library.skills or self.library.skills[sid].status not in {'active', 'fallback', 'candidate'}:
            raise InvalidProgram('call requires a known immutable, admitted version id')
        skill = self.library.skills[sid]
        if skill.status == 'candidate' and record:
            raise InvalidProgram('unadmitted skill cannot be invoked')
        self._validate_bindings(bindings, episode.env.state)
        if set(bindings) != set(skill.parameters):
            raise InvalidProgram('skill arguments must match signature exactly')
        pre = episode.env.state.check(skill.preconditions, bindings)
        before = copy.deepcopy(episode.env.snapshot())
        success, error = False, ''
        try:
            if not pre:
                raise ActionError('skill preconditions do not hold')
            Program(skill.body, skill.parameters).run(episode, bindings,
                lambda child, args: self._invoke(child, args, episode, depth + 1, record), self.cfg.program_budget)
            success = episode.env.state.check(skill.postconditions, bindings)
            if not success:
                raise ActionError('skill postconditions do not hold')
        except (ValueError, RuntimeError, KeyError) as exc:
            error = str(exc)
            raise
        finally:
            if record:
                test = {'snapshot': before, 'bindings': copy.deepcopy(bindings)}
                low = skill.reliability(self.cfg) < self.cfg.low_reliability
                outcome = self.library.record(sid, success, pre, test, error, updates=self.updates)
                event = {'skill_id': sid, 'success': success, 'preconditions_held': pre,
                         'retrieval_error': not pre, 'low_reliability': low, 'outcome': outcome,
                         'error': error}
                self.result['invocations'].append(event)
                self.result['reused_skills'] += 1
                if outcome == 'revision_due':
                    self.result['revision_gate_count'] += 1
                    self.revision_due.add(sid)
                    self.repair_tests[sid] = test
                if pre and not success and self.updates:
                    self.repair_tests[sid] = test
                    self.revision_due.add(sid)
                if self.live and depth == 0:
                    consolidation.track_pair(self, sid, before, bindings, success,
                                             len(episode.env.snapshot()['actions']))
        return success

    def _verify(self, candidate, test):
        env = self.env_factory()
        saved_steps = self.invocation_steps
        try:
            env.restore(copy.deepcopy(test['snapshot']))
            bindings = test['bindings']
            self._validate_bindings(bindings, env.state)
            if not env.state.check(candidate.preconditions, bindings):
                false = [p for p in candidate.preconditions if not env.state.check([p], bindings)]
                self.verify_reason = f'precondition false at start: {", ".join(false)[:80]}'
                return False
            episode = Episode(env, self.cfg.step_budget)
            self.invocation_steps = 0
            Program(candidate.body, candidate.parameters).run(episode, bindings,
                lambda sid, args: self._invoke(sid, args, episode, 1, False), self.cfg.program_budget)
            if not env.state.check(candidate.postconditions, bindings):
                missed = [p for p in candidate.postconditions if not env.state.check([p], bindings)]
                self.verify_reason = f'result not reached: {", ".join(missed)[:80]}'
                return False
            return True
        except (ValueError, RuntimeError, KeyError) as exc:
            self.verify_reason = str(exc)[:100]
            return False
        finally:
            self.invocation_steps = saved_steps
            env.close()

    def _candidate(self, goal, snapshot, parent=None, captured=None):
        if self.frozen or self.condition not in {'B', 'E', 'E-minus', 'E-plus'} or not goal['bindings']:
            return  # nothing to parameterize (e.g. the whole-task fallback)
        if captured is None and parent is None and self.condition == 'E-plus':
            # E-plus writes skills only from games it wins, at the end, seeing the whole game.
            self.deferred.append((goal, copy.deepcopy(snapshot), {
                'start': self.subgoal_start,
                'actions': [t['action'] for t in self.episode.trace[self.subgoal_step:] if t['valid']]}))
            return
        # Skills and their replay tests use concrete instances ("mug 1"), never bare types.
        state = self.episode.env.state
        goal = {**goal, 'bindings': {k: state.ground(v) for k, v in goal['bindings'].items()}}
        self.result['candidate_attempts'] += 1
        extra = {}
        if captured is not None:
            extra = {'whole_game': {'task': self.public_task.get('goal', ''), 'won': True,
                                    'actions': [t['action'] for t in self.episode.trace if t['valid']]}}
        payload = {'instructions': LIBRARIAN_GUIDE + (WHOLE_GAME_NOTE if captured else ''),
            'goal': goal, 'start_observation': captured['start'] if captured else self.subgoal_start,
            'parameter_names': sorted(goal['bindings']),
            'actions': captured['actions'] if captured else [t['action'] for t in self.episode.trace[self.subgoal_step:] if t['valid']],
            'parent': self._skill_payload(parent) if parent else None, **extra,
            'allowed_predicates': self._predicates(),
            'response_schema': {'candidate': {'name': 'lowercase_identifier', 'description': 'string',
                'parameters': {'parameter': 'entity'}, 'preconditions': ['predicate(arguments)'],
                'postconditions': ['predicate(arguments)'], 'body': 'safe Python subset string'},
                'arguments': {'parameter': 'concrete entity used in the actions'}}}
        # Iterative refinement as in Voyager (Wang et al. 2023, section 2.2): the skill is executed
        # (replayed from where the subgoal started); a failure goes back to the writer with the exact
        # error for another round; after cfg.repairs + 1 rounds an unverified skill is dropped.
        rounds = self.cfg.repairs + 1
        feedback = None
        for round_index in range(rounds):
            attempt = None
            try:
                if round_index:
                    self.unbudgeted = True     # refinement rounds are charged, not capped
                data = self._ask('librarian', payload if feedback is None else
                                 {**payload, 'instructions': payload['instructions'] + REFINE_NOTE, **feedback})
                if not {'candidate'} <= set(data) <= {'candidate', 'arguments'} or not isinstance(data['candidate'], dict):
                    raise ValueError('invalid candidate object')
                c = attempt = data['candidate']
                if set(c) != {'name', 'description', 'parameters', 'preconditions', 'postconditions', 'body'}:
                    raise ValueError('invalid candidate fields')
                # Concrete values for the replay test: stated arguments, else the subgoal's own bindings.
                arguments = {**goal['bindings'], **(data.get('arguments') if isinstance(data.get('arguments'), dict) else {})}
                if (not all(isinstance(c[k], str) for k in ('name', 'description', 'body'))
                        or not isinstance(c['parameters'], dict)
                        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in c['parameters'].items())):
                    raise ValueError('invalid candidate field types')
                self._validate_conditions(c['postconditions'])
                if not isinstance(c['preconditions'], list) or len(c['preconditions']) > 20:
                    raise ValueError('invalid candidate preconditions')
                for condition in c['preconditions']:
                    if not isinstance(condition, str):
                        raise ValueError('predicate must be a string')
                    Predicate.parse(condition)
                name = parent.name if parent else c['name']
                if parent is None and name in self.library.active:
                    # Same skill already stored: a duplicate, not a broken program.
                    self.result['candidate_duplicates'] += 1
                    self.result['candidate_attempts'] -= 1
                    return
                skill = Skill(self.library.next_id(name), c['description'], c['parameters'], c['preconditions'],
                              c['postconditions'], c['body'], parent=parent.id if parent else None)
                bound = {k: state.ground(arguments[k]) for k in skill.parameters}
                self._validate_bindings(bound, state)
                if parent is None:
                    # Compare on concrete instances: the subgoal may name a type ("mug"), the skill "mug 1".
                    def concrete(text, values):
                        p = Predicate.parse(text).bind(values)
                        return Predicate(p.name, tuple(state.ground(a) for a in p.args))
                    promised = {concrete(p, bound) for p in skill.postconditions}
                    required = {concrete(p, goal['bindings']) for p in goal['postconditions']}
                    if not required <= promised:
                        raise ValueError('new skill contract must cover the accomplished subgoal: postconditions '
                                         f'must include {", ".join(sorted(map(str, required - promised)))} '
                                         f'(written over your parameters; arguments were {bound})')
                test = self.repair_tests.get(parent.id) if parent else None
                if test is None:
                    test = {'snapshot': copy.deepcopy(snapshot), 'bindings': bound}
                if not self._verify(skill, test):
                    raise ValueError(f'candidate failed replay tests ({self.verify_reason})')
                if not self.library.admit(skill, test, self._verify, updates=self.updates):
                    raise ValueError(f'candidate failed replay tests ({self.verify_reason})')
                if round_index:
                    self.result['candidate_refinements'] = self.result.get('candidate_refinements', 0) + 1
                return
            except BudgetExceeded as exc:
                self.result['candidate_rejections'] += 1
                self.result['program_errors'].append('candidate: ' + str(exc))
                return
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                feedback = {'previous_attempt': attempt, 'error': str(exc)}
                if round_index == rounds - 1:
                    self.result['candidate_rejections'] += 1
                    self.result['program_errors'].append('candidate: ' + str(exc))
            finally:
                self.unbudgeted = False

    @staticmethod
    def _skill_payload(skill):
        return {**skill.text(), 'parameters': skill.parameters, 'body': skill.body}

    def _process_revisions(self, goal, snapshot):
        pending = sorted(self.revision_due)
        self.revision_due.clear()
        for sid in pending:
            if self.updates and self.library.active.get(self.library.skills[sid].name) == sid:
                self._candidate(goal, snapshot, self.library.skills[sid])

    def _retrieved(self, goal, count=True):
        skills = []
        if self.memory:
            skills = self.library.retrieve(goal['description'], goal['bindings'], self.episode.env.state, self.embedder)
            if count:  # metrics count one retrieval per subgoal, not per refresh
                self.result['retrievals'] += 1
                self.result['retrieved_skill_count'] += len(skills)
                self.result['low_reliability_retrievals'] += sum(s.reliability(self.cfg) < self.cfg.low_reliability for s in skills)
        return skills

    def _examples(self, goal):
        """D: the top-k most similar successful practice trajectories (goal + valid actions)."""
        if self.condition != 'D' or not self.trajectories:
            return []
        self.result['retrievals'] += 1
        descriptions = [' '.join([str(t.get('goal', '')), str(t.get('task', {}).get('task_type', ''))])
                        for t in self.trajectories]
        scores = self.embedder.similarity(' '.join([str(self.public_task.get('goal', '')), goal['description']]),
                                          descriptions)
        indexes = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:self.cfg.top_k]
        return [{'goal': self.trajectories[i].get('goal', ''),
                 'actions': [s['action'] for s in self.trajectories[i].get('trace', []) if s.get('valid')]}
                for i in indexes]

    @staticmethod
    def _skill_action(skill, goal):
        """The action that calls a skill; known arguments pre-filled, the rest as <name>."""
        values = ', '.join(f"{k}={goal['bindings'].get(k, '<' + k + '>')}" for k in skill.parameters)
        return f'use skill {skill.id} {values}'.strip()

    @staticmethod
    def _skill_arguments(action, skill, goal, state):
        """Arguments for a chosen skill action: the actor's values, else the subgoal's bindings."""
        given = dict(part.split('=', 1) for part in
                     (x.strip() for x in action[len(f'use skill {skill.id}'):].split(',')) if '=' in part)
        values = {k: given.get(k, goal['bindings'].get(k, '')).strip() for k in skill.parameters}
        return {k: state.ground(v) for k, v in values.items()}

    def _execute(self, goal, step_cap):
        """Act step by step (published ALFWorld ReAct loop) until the subgoal's predicates hold."""
        snapshot = copy.deepcopy(self.episode.env.snapshot())
        # Skills are replayed from this state, so the librarian sees it and only this subgoal's steps.
        self.subgoal_start = self.episode.env.state.public()
        self.subgoal_step = len(self.episode.trace)
        initial_invocations = len(self.result['invocations'])
        text = self.condition == 'E-text'
        examples = self._examples(goal)
        flat = self.condition in {'A', 'B'}
        start = len(self.episode.trace)
        failed = set()   # a skill that fails is not offered again within this subgoal
        offered = set()  # E-plus usage evidence: skills shown to the actor in this subgoal
        first = True
        while True:
            if self.episode.env.state.check(goal['postconditions'], goal['bindings']):
                if len(self.result['invocations']) == initial_invocations:
                    self._candidate(goal, snapshot)
                return True
            if self.episode.env.state.done or len(self.episode.trace) - start >= step_cap:
                return False
            # Retrieval is refreshed every step: a skill becomes usable once its preconditions hold.
            skills = self._retrieved(goal, count=first)
            first = False
            callable_skills = {} if text else {s.id: s for s in skills if s.id not in failed}
            if self.live:
                for sid in set(callable_skills) - offered:
                    consolidation.note(self.library, sid, 'offered')
                offered |= set(callable_skills)
            prompt = react.build(
                self.public_task.get('goal', ''),
                self.task.get('task_type') if self.cfg.react_demos else None, self.episode.trace,
                self.initial_observation, self.episode.env.state.admissible,
                subgoal=None if flat else goal['description'],
                skills=[(self._skill_action(s, goal), s.description) for s in callable_skills.values()],
                skill_texts=[s.text() for s in skills] if text else (), examples=examples,
                lessons=self.lessons_shown or manual.render(self.shown_rules),
                brief=self.cfg.actor_brief)
            data = self._ask('actor', {'prompt': prompt, 'admissible': list(self.episode.env.state.admissible),
                                       'skills': [self._skill_action(s, goal) for s in callable_skills.values()]})
            text_reply = data.get('text', '')
            if not react.has_action(text_reply):
                self.result['actor_followups'] += 1
                data = self._ask('actor', {'prompt': prompt, 'admissible': list(self.episode.env.state.admissible),
                                           'skills': [self._skill_action(s, goal) for s in callable_skills.values()],
                                           'partial': text_reply, 'followup': react.FOLLOWUP,
                                           'followup_tokens': react.FOLLOWUP_TOKENS})
                text_reply = data.get('text', '')
            action = react.parse_action(text_reply)
            try:
                called = action.split()[2] if action.startswith('use skill ') and len(action.split()) > 2 else None
                if called in callable_skills:
                    skill = callable_skills[called]
                    failed.add(skill.id)
                    arguments = self._skill_arguments(action, skill, goal, self.episode.env.state)
                    if self._invoke(skill.id, arguments, self.episode):
                        failed.discard(skill.id)
                else:
                    self.episode.act(action)
            except BudgetExceeded:
                raise
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                # An invalid command already appears in the trace and reads "Nothing happens."
                self.result['program_errors'].append(str(exc))
            self._process_revisions(goal, snapshot)

    def _history(self):
        # Each step's 'before' equals the previous step's 'after'; send it once.
        return [{'action': step['action'], 'valid': step['valid'], 'after': step['after']}
                for step in self.episode.trace]

    @staticmethod
    def _public_task(task, env):
        # Models see the natural-language goal, never manifest paths/hashes that encode the answer.
        goal = getattr(env, 'goal', None)
        if goal:
            return {'goal': goal}
        return {k: task[k] for k in ('goal', 'object', 'target') if k in task}

    def run(self, task, seed, context):
        started = time.monotonic()
        self.task, self.seed, self.context = copy.deepcopy(task), seed, dict(context)
        self.gpu, self.gpu_known, self.invocation_steps = 0.0, True, 0
        self.revision_due = set()
        self.repair_tests = {}
        self.last_call = None
        self.lessons_shown = []
        self.shown_rules, self.rules_shown = [], []
        self.deferred = []
        self.result = {'success': False, 'invocations': [], 'trace': [], 'subgoals_passed': False,
            'program_attempts': 0, 'program_failures': 0, 'program_errors': [], 'candidate_attempts': 0, 'candidate_rejections': 0, 'candidate_duplicates': 0, 'actor_followups': 0, 'curator_calls': 0,
            'input_tokens': 0, 'output_tokens': 0, 'wall_seconds': 0.0, 'model_wall_seconds': 0.0,
            'gpu_seconds': None, 'model_calls': 0, 'retrievals': 0,
            'low_reliability_retrievals': 0, 'retrieved_skill_count': 0, 'reused_skills': 0, 'revision_gate_count': 0,
            'subgoal_count': 0, 'planner_fallbacks': 0, 'library_size': len(self.library.current())}
        env = self.env_factory()
        self.episode = Episode(env, self.cfg.step_budget)
        self.public_task = self._public_task(self.task, env)
        try:
            env.reset(task)
            self.initial_observation = env.state.observation
            self.public_task = self._public_task(self.task, env)
            self.result['goal'] = self.public_task.get('goal', '')
            # The rules this game sees, chosen once (MACLA expected utility; rules do not change mid-game).
            self.shown_rules = (manual.relevant(self.rules, self.task.get('task_type'), manual.SHOWN,
                                                self.result['goal'], self.embedder.similarity)
                                if self.uses_rules and self.rules else [])
            self.rules_shown = [r['id'] for r in self.shown_rules]
            self.result['rules_shown'] = list(self.rules_shown)
            if self.condition == 'E-plus':
                self.lessons_shown = (list(self.forced_lessons) if self.forced_lessons is not None
                                      else consolidation.lessons_for(self.library, self.task.get('task_type')))
                self.result['lessons_shown'] = len(self.lessons_shown)
            for replan in range(self.cfg.replans + 1):
                try:
                    goals = self._goals(env.state)
                    self.result['subgoal_count'] += len(goals) if self.condition not in {'A', 'B'} else 0
                    passed = True
                    for goal in goals:
                        flat = self.condition in {'A', 'B'} or goal['postconditions'] == ['task_won()']
                        cap = self.cfg.step_budget if flat else self.cfg.subgoal_step_budget
                        if not self._execute(goal, cap):
                            passed = False
                            break
                    self.result['subgoals_passed'] = passed
                    if env.state.won or env.state.done:
                        break
                except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                    self.result['program_errors'].append(str(exc))
                    if isinstance(exc, BudgetExceeded):
                        break
            self.result['success'] = bool(env.state.won)
            position = self.context.get('position')
            if self.deferred and self.result['success']:
                # End of a won E-plus game: write skills for its subgoals with the whole game in view.
                self.unbudgeted = True
                try:
                    for goal, snapshot, captured in self.deferred:
                        self._candidate(goal, snapshot, captured=captured)
                finally:
                    self.unbudgeted = False
            self.result['deferred_subgoals'] = len(self.deferred)
            if self.live:
                consolidation.record_episode(self)
            if (self.uses_rules and self.condition != 'E-text' and not self.frozen
                    and self.context.get('phase') == 'practice'):
                # AutoManual Builder: update the manual from this game (charged, not capped).
                self.unbudgeted = True
                try:
                    self.result['manual'] = manual.build(self)
                finally:
                    self.unbudgeted = False
            if (self.live and isinstance(position, int)
                    and (position + 1) % self.cfg.consolidation_interval == 0):
                self.result['consolidation'] = consolidation.consolidate(self)
        finally:
            self.result['library_size'] = len(self.library.current())
            # L2 code = skills: written candidates plus executed skill calls; failures = rejected or crashed.
            calls = self.result['invocations']
            self.result['program_attempts'] = self.result['candidate_attempts'] + len(calls)
            self.result['program_failures'] = (self.result['candidate_rejections']
                                               + sum(not c['success'] and c['preconditions_held'] for c in calls))
            self.result['trace'] = copy.deepcopy(self.episode.trace)
            self.result['wall_seconds'] = time.monotonic() - started
            self.result['gpu_seconds'] = self.gpu if self.gpu_known and self.result['model_calls'] else None
            env.close()
        return self.result
