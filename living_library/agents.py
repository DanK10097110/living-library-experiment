"""Bounded flat/hierarchical execution and isolated skill admission."""
import copy
import json
import time

from .config import CONDITIONS
from .domain import Episode, ActionError, BudgetExceeded, Predicate
from .library import Skill
from .program import Program, InvalidProgram


class Agent:
    def __init__(self, cfg, condition, model, library, embedder, env_factory, trajectories=None):
        if condition not in CONDITIONS:
            raise ValueError('unknown experimental condition')
        self.cfg, self.condition, self.model = cfg, condition, model
        self.library, self.embedder, self.env_factory = library, embedder, env_factory
        self.trajectories = trajectories if trajectories is not None else []
        self.memory = condition in {'B', 'E', 'E-minus', 'E-text'}
        self.updates = condition in {'B', 'E'}

    def _ask(self, role, payload):
        if self.result['model_calls'] >= self.cfg.max_model_calls:
            raise BudgetExceeded('model call budget exhausted')
        ordinal = self.result['model_calls']
        self.result['model_calls'] += 1
        try:
            response = self.model.complete(role, {'task': self.task,
                                           'initial_observation': self.initial_observation, **payload}, self.seed,
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
        if self.condition in {'A', 'B'}:
            return [{'description': 'complete task', 'bindings': self._task_bindings(), 'postconditions': ['task_won()']}]
        data = self._ask('planner', {'state': state.public(),
            'history': self.episode.trace,
            'previous_errors': list(dict.fromkeys(self.result['program_errors']))[-5:],
            'instructions': (
                'Plan for the ALFWorld text simulator, not real-world household actions. '
                'Bindings must use exact numbered entity names observed in public text, '
                'such as desk 1; never use an object type such as alarmclock as an entity. '
                'If the requested object has not been observed, first plan exploration '
                'of a visible receptacle with bindings {} and postcondition at(receptacle). '
                'Do not invent the hidden object instance or its location. '
                'Use at(desk 1) for agent location, located(object, receptacle) for '
                'object placement, and holding(object) for inventory. '
                'exists/findable are entity-existence checks, not evidence of discovery. '
                'Each predicate must have the arity specified in allowed_predicates. '
                'Return a short executable plan based on current knowledge; replanning '
                'can follow exploration. Correct previous_errors rather than repeating them.'),
            'catalog': self.library.catalog() if self.memory else [],
            'allowed_predicates': self._predicates(),
            'response_schema': {'subgoals': [{'description': 'string', 'bindings': {'parameter': 'entity string'}, 'postconditions': ['predicate(arguments)']}]}})
        if set(data) != {'subgoals'} or not isinstance(data['subgoals'], list) or not 1 <= len(data['subgoals']) <= self.cfg.max_subgoals:
            raise ValueError('invalid bounded subgoal list')
        # Ignore description wording when detecting repeated contracts. Only public
        # state is used: this is a retry guard, not a source of hidden knowledge.
        contracts = []
        for goal in data['subgoals']:
            if set(goal) != {'description', 'bindings', 'postconditions'} or not isinstance(goal['description'], str) or not goal['description']:
                raise ValueError('invalid subgoal')
            if not isinstance(goal['bindings'], dict):
                raise ValueError('bindings must be an object')
            self._validate_conditions(goal['postconditions'])
            contracts.append(sorted(str(Predicate.parse(p).bind(goal['bindings']))
                                    for p in goal['postconditions']))
        public_state = json.dumps(state.public(), sort_keys=True)
        if public_state != self.last_plan_state:
            self.plan_stalls.clear()
            self.last_plan_state = public_state
        signature = json.dumps(contracts, sort_keys=True)
        self.plan_stalls[signature] = self.plan_stalls.get(signature, 0) + 1
        if self.plan_stalls[signature] >= 3:
            raise BudgetExceeded('stopped: same plan returned three times in unchanged public state')
        for goal in data['subgoals']:
            self._validate_bindings(goal['bindings'], state)
            self._validate_conditions(goal['postconditions'], state, goal['bindings'])
        return data['subgoals']

    @staticmethod
    def _predicates():
        from .domain import ARITY
        return ARITY

    @staticmethod
    def _validate_conditions(conditions, state=None, bindings=None):
        if not isinstance(conditions, list) or not 1 <= len(conditions) <= 20:
            raise ValueError('nonempty bounded postcondition list required')
        for condition in conditions:
            if not isinstance(condition, str):
                raise ValueError('predicates must be strings')
            predicate = Predicate.parse(condition).bind(bindings or {})
            if state is not None:
                if predicate.name == 'at':
                    destinations = {c[6:] for c in state.admissible if c.startswith('go to ')}
                    destinations.update(f[1] for f in state.facts if f[0] == 'at')
                    if predicate.args[0] not in destinations:
                        raise ValueError(
                            f'Invalid navigation goal: {predicate}. at() requires a '
                            'receptacle from go to commands or the current location. '
                            'Objects and lamps are not navigation destinations. '
                            'If the lamp location is unknown, explore an unsearched '
                            'receptacle; do not guess its location.')
                for entity in predicate.args:
                    if entity not in state.entities:
                        raise ValueError(
                            f'Invalid postcondition entity: {entity!r}. Use exact observed '
                            'entity names, including their numbers. If the target object '
                            'has not been observed, explore an unvisited visible receptacle '
                            'with at(receptacle) before planning object manipulation.')

    @staticmethod
    def _validate_bindings(bindings, state):
        if not isinstance(bindings, dict) or any(not isinstance(k, str) or not isinstance(v, str) or v not in state.entities for k, v in bindings.items()):
            raise ValueError('bindings must name present entities')

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
        return success

    def _verify(self, candidate, test):
        env = self.env_factory()
        saved_steps = self.invocation_steps
        try:
            env.restore(copy.deepcopy(test['snapshot']))
            bindings = test['bindings']
            self._validate_bindings(bindings, env.state)
            if not env.state.check(candidate.preconditions, bindings):
                return False
            episode = Episode(env, self.cfg.step_budget)
            self.invocation_steps = 0
            Program(candidate.body, candidate.parameters).run(episode, bindings,
                lambda sid, args: self._invoke(sid, args, episode, 1, False), self.cfg.program_budget)
            return env.state.check(candidate.postconditions, bindings)
        except (ValueError, RuntimeError, KeyError):
            return False
        finally:
            self.invocation_steps = saved_steps
            env.close()

    def _candidate(self, goal, snapshot, parent=None):
        if self.condition not in {'B', 'E', 'E-minus'}:
            return
        self.result['candidate_attempts'] += 1
        try:
            data = self._ask('librarian', {'goal': goal, 'snapshot_observation': self.episode.env.state.public(),
                'trace': self.episode.trace, 'parent': self._skill_payload(parent) if parent else None,
                'allowed_predicates': self._predicates(),
                'response_schema': {'candidate': {'name': 'lowercase_identifier', 'description': 'string',
                    'parameters': {'argument': 'entity'}, 'preconditions': ['predicate(arguments)'],
                    'postconditions': ['predicate(arguments)'], 'body': 'safe Python subset string'}}})
            if set(data) != {'candidate'} or not isinstance(data['candidate'], dict):
                raise ValueError('invalid candidate object')
            c = data['candidate']
            if set(c) != {'name', 'description', 'parameters', 'preconditions', 'postconditions', 'body'}:
                raise ValueError('invalid candidate fields')
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
            skill = Skill(self.library.next_id(name), c['description'], c['parameters'], c['preconditions'],
                          c['postconditions'], c['body'], parent=parent.id if parent else None)
            if parent is None:
                bound = {k: goal['bindings'][k] for k in skill.parameters}
                promised = {Predicate.parse(p).bind(bound) for p in skill.postconditions}
                required = {Predicate.parse(p).bind(goal['bindings']) for p in goal['postconditions']}
                if not required <= promised:
                    raise ValueError('new skill contract must cover the accomplished subgoal')
            test = self.repair_tests.get(parent.id) if parent else None
            if test is None:
                test = {'snapshot': copy.deepcopy(snapshot), 'bindings': {k: goal['bindings'][k] for k in skill.parameters}}
            if not self.library.admit(skill, test, self._verify, updates=self.updates):
                raise ValueError('candidate failed replay tests')
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.result['candidate_rejections'] += 1
            self.result['program_errors'].append('candidate: ' + str(exc))

    @staticmethod
    def _skill_payload(skill):
        return {**skill.text(), 'parameters': skill.parameters, 'body': skill.body}

    def _process_revisions(self, goal, snapshot):
        pending = sorted(self.revision_due)
        self.revision_due.clear()
        for sid in pending:
            if self.updates and self.library.active.get(self.library.skills[sid].name) == sid:
                self._candidate(goal, snapshot, self.library.skills[sid])

    def _retrieved(self, goal):
        skills = []
        if self.memory:
            self.result['retrievals'] += 1
            skills = self.library.retrieve(goal['description'], goal['bindings'], self.episode.env.state, self.embedder)
            self.result['retrieved_skill_count'] += len(skills)
            self.result['low_reliability_retrievals'] += sum(s.reliability(self.cfg) < self.cfg.low_reliability for s in skills)
        return skills

    def _execute(self, goal):
        snapshot = copy.deepcopy(self.episode.env.snapshot())
        errors = []
        initial_invocations = len(self.result['invocations'])
        # Text ablation emits primitive commands only; no stored/generated code executes.
        text = self.condition == 'E-text'
        flat = self.condition in {'A', 'B'}
        attempts = self.cfg.step_budget + self.cfg.repairs + 1 if text or flat else self.cfg.repairs + 1
        for attempt in range(attempts):
            if self.episode.env.state.check(goal['postconditions'], goal['bindings']):
                return True
            skills = self._retrieved(goal)
            examples = []
            if self.condition == 'D' and self.trajectories:
                self.result['retrievals'] += 1
                descriptions = [' '.join([str(t.get('task', {}).get('goal', '')), str(t.get('task', {}).get('task_type', '')), str(t.get('initial_observation', '')), str(t.get('trace', [{}])[0].get('before', '') if t.get('trace') else '')]) for t in self.trajectories]
                scores = self.embedder.similarity(goal['description'], descriptions)
                indexes = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:self.cfg.top_k]
                examples = [self.trajectories[i] for i in indexes]
            if self.result['model_calls'] >= self.cfg.max_model_calls:
                raise BudgetExceeded('model call budget exhausted')
            self.result['program_attempts'] += 1
            try:
                data = self._ask('executor', {'state': self.episode.env.state.public(), 'goal': goal,
                    'skills': [s.text() if text else self._skill_payload(s) for s in skills], 'trajectories': examples,
                    'catalog': self.library.catalog() if flat and self.memory else [],
                    'flat': flat, 'history': self.episode.trace[-20:],
                    'text_only': text, 'errors': errors, 'allowed_predicates': self._predicates(),
                    'instructions': ('Return one primitive action or one retrieved skill call. Optionally return only bindings to retrieve applicable skills. Use current observation/history; do not emit a plan or code.' if flat else 'Return only primitive admissible commands. Numbered library steps are reference text. Never call a skill or emit code.' if text else 'Use act(command), check(predicate), call(exact_version_id, named=entity). No imports. Repair the previous failure using the CURRENT observation.'),
                    'response_schema': ({'one_of': [{'action': 'one admissible command', 'bindings': 'optional entity mapping'}, {'skill_id': 'retrieved immutable version id', 'bindings': 'exact argument mapping'}, {'bindings': 'entity mapping to enable retrieval before acting'}]} if flat else {'actions': ['admissible command']}) if text or flat else {'program': 'safe Python subset', 'bindings': 'optional entity argument mapping for flat execution'}})
                if flat:
                    if set(data) == {'bindings'}:
                        self._validate_bindings(data['bindings'], self.episode.env.state)
                        goal['bindings'] = data['bindings']
                        continue
                    if 'action' in data and set(data) <= {'action', 'bindings'}:
                        if 'bindings' in data:
                            self._validate_bindings(data['bindings'], self.episode.env.state)
                            goal['bindings'] = data['bindings']
                        if not isinstance(data['action'], str):
                            raise ValueError('flat action must be a string')
                        self.episode.act(data['action'])
                    elif set(data) == {'skill_id', 'bindings'} and self.memory:
                        if data['skill_id'] not in {s.id for s in skills}:
                            raise ValueError('flat skill calls require a retrieved version')
                        self._invoke(data['skill_id'], data['bindings'], self.episode)
                    else:
                        raise ValueError('flat response requires one primitive action or skill call')
                elif text:
                    if set(data) != {'actions'} or not isinstance(data['actions'], list) or not 1 <= len(data['actions']) <= self.cfg.step_budget:
                        raise ValueError('invalid primitive action list')
                    for command in data['actions']:
                        if not isinstance(command, str):
                            raise ValueError('command must be a string')
                        self.episode.act(command)
                        if self.episode.env.state.done:
                            break
                else:
                    if 'program' not in data or set(data) - {'program', 'bindings'}:
                        raise ValueError('invalid program response')
                    if 'bindings' in data:
                        self._validate_bindings(data['bindings'], self.episode.env.state)
                        goal['bindings'] = data['bindings']
                    Program(data['program']).run(self.episode, {},
                        lambda sid, args: self._invoke(sid, args, self.episode), self.cfg.program_budget)
                self._process_revisions(goal, snapshot)
                if self.episode.env.state.check(goal['postconditions'], goal['bindings']):
                    if len(self.result['invocations']) == initial_invocations:
                        self._candidate(goal, snapshot)
                    return True
                if text or flat:
                    continue
                raise ActionError('subgoal postconditions do not hold')
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                self.result['program_failures'] += 1
                errors.append(str(exc))
                self.result['program_errors'].append(str(exc))
                self._process_revisions(goal, snapshot)
                if isinstance(exc, BudgetExceeded) or self.episode.env.state.done or ((flat or text) and len(errors) > self.cfg.repairs):
                    break
        return False

    def run(self, task, seed, context):
        started = time.monotonic()
        self.task, self.seed, self.context = copy.deepcopy(task), seed, dict(context)
        self.gpu, self.gpu_known, self.invocation_steps = 0.0, True, 0
        self.revision_due = set()
        self.repair_tests = {}
        self.plan_stalls = {}
        self.last_plan_state = None
        self.result = {'success': False, 'invocations': [], 'trace': [], 'subgoals_passed': False,
            'program_attempts': 0, 'program_failures': 0, 'program_errors': [], 'candidate_attempts': 0, 'candidate_rejections': 0,
            'input_tokens': 0, 'output_tokens': 0, 'wall_seconds': 0.0, 'model_wall_seconds': 0.0,
            'gpu_seconds': None, 'model_calls': 0, 'retrievals': 0,
            'low_reliability_retrievals': 0, 'retrieved_skill_count': 0, 'reused_skills': 0, 'revision_gate_count': 0,
            'subgoal_count': 0, 'library_size': len(self.library.current())}
        env = self.env_factory()
        self.episode = Episode(env, self.cfg.step_budget)
        try:
            env.reset(task)
            self.initial_observation = env.state.observation
            for replan in range(self.cfg.replans + 1):
                try:
                    goals = self._goals(env.state)
                    self.result['subgoal_count'] += len(goals) if self.condition not in {'A', 'B'} else 0
                    passed = True
                    for goal in goals:
                        if not self._execute(goal):
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
        finally:
            self.result['library_size'] = len(self.library.current())
            self.result['trace'] = copy.deepcopy(self.episode.trace)
            self.result['wall_seconds'] = time.monotonic() - started
            self.result['gpu_seconds'] = self.gpu if self.gpu_known and self.result['model_calls'] else None
            env.close()
        return self.result
