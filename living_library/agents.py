"""One game: planner subgoals, then the published ALFWorld ReAct actor step by step."""
import copy
import os
import time

from . import manual, react
from .config import CONDITIONS
from .domain import Episode, BudgetExceeded, Predicate


PREDICATES = ('Predicates: located(obj, place) obj is in/on place; at(place) you are at place; '
              'holding(obj) you carry obj; is_open/is_hot/is_cold/is_clean/is_on/is_toggled(x); '
              'exists(x); task_won(). ')
# Fixed role guide (one worked example); part of the frozen settings. Acting itself uses the
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
# Which shown rules a plan follows (manual.assess: "used"): a separate short call after each plan, from the plan
# and the numbered rules only (no trace, no outcome). Asking the planner itself to list them broke its subgoals
# (a subgoal without postconditions in 5 of 30 games vs 1 in 280 before; DECISIONS 2026-11-20).
CITE_GUIDE = ('An agent in a household text game made this plan (subgoals) after reading these numbered rules. '
              'List the numbers of the rules the plan follows: a subgoal does what the rule says, or the plan is '
              'shaped by it. A rule the plan does not act on is not listed. Output {"used_rules": [numbers]}; '
              '[] if none.')
# Conditions that read the rule manual; both build it in practice (manual.build), E also manages it.
RULE_CONDITIONS = ('E', 'E-minus')


class Agent:
    # Frozen games (evaluation, retries) need no citations; LL_CITE_FROZEN=1 turns them on to measure them.
    CITE_FROZEN = os.environ.get('LL_CITE_FROZEN') == '1'

    def __init__(self, cfg, condition, model, embedder, env_factory, trajectories=None, frozen=False,
                 rules=None, reflections=None):
        if condition not in CONDITIONS:
            raise ValueError('unknown experimental condition')
        self.cfg, self.condition, self.model = cfg, condition, model
        self.embedder, self.env_factory = embedder, env_factory
        self.trajectories = trajectories if trajectories is not None else []
        # The rule manual (manual.py): E and E-minus build it in practice and read it frozen in tests.
        self.rules = rules if rules is not None else []
        # Reflexion retry of a lost practice game (manual.retry): reflections on the earlier attempts.
        self.reflections = list(reflections or [])
        self.uses_rules = condition in RULE_CONDITIONS
        # frozen: read the memory as it is (evaluations, gate, snapshots, retries); learn nothing.
        self.frozen = frozen
        self.unbudgeted = False
        self.plan_text = ''
        self.pinned = None      # a rule id always shown (manual.trial: a candidate refinement under test)

    def retry_agent(self, reflections):
        """A frozen copy for a Reflexion retry of this game: same memory (read only), these reflections."""
        return type(self)(self.cfg, self.condition, self.model, self.embedder, self.env_factory,
                          trajectories=self.trajectories, frozen=True, rules=self.rules,
                          reflections=reflections)

    def trial_agent(self, rules, pinned):
        """A frozen agent for a refinement trial game (manual.trial): these rules, `pinned` always shown."""
        agent = type(self)(self.cfg, self.condition, self.model, self.embedder, self.env_factory,
                           trajectories=self.trajectories, frozen=True, rules=rules)
        agent.pinned = pinned
        return agent

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
        if self.condition == 'A':
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
            **({'rules': manual.render(self.shown_rules)} if self.shown_rules else {}),
            **({'reflections': self.reflections} if self.reflections else {}),
            'allowed_predicates': self._predicates(),
            'response_schema': {'subgoals': [{'description': 'string', 'bindings': {'parameter': 'entity string'}, 'postconditions': ['predicate(arguments)']}]}})
        if set(data) != {'subgoals'} or not isinstance(data['subgoals'], list) or not 1 <= len(data['subgoals']) <= self.cfg.max_subgoals:
            raise ValueError('invalid bounded subgoal list')
        for goal in data['subgoals']:
            if set(goal) != {'description', 'bindings', 'postconditions'} or not isinstance(goal['description'], str) or not goal['description']:
                raise ValueError('invalid subgoal')
            self._validate_bindings(goal['bindings'], state)
            self._validate_conditions(goal['postconditions'])
        self._cite(data['subgoals'])
        return data['subgoals']

    def _cite(self, subgoals):
        """Record the shown rules this plan follows (manual.assess: "used"): one short call with the plan and
        the numbered rules. A failed call records nothing (the game goes on; the rules get no use from it)."""
        if not (self.uses_rules and self.shown_rules) or self.frozen and self.pinned is None and not self.CITE_FROZEN:
            return
        try:
            data = self._ask('citer', {'instructions': CITE_GUIDE,
                                       'plan': [g['description'] for g in subgoals],
                                       'rules': [f'{i}. {text}' for i, text in enumerate(manual.render(self.shown_rules), 1)],
                                       'response_schema': {'used_rules': ['rule number']}})
            numbers = data.get('used_rules')
        except BudgetExceeded:
            raise
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.result['program_errors'].append('citer: ' + str(exc))
            return
        if not isinstance(numbers, list):
            return
        for n in numbers:
            try:
                i = int(str(n).strip().lstrip('#').split('.')[0]) - 1
            except ValueError:
                continue
            if 0 <= i < len(self.shown_rules) and self.shown_rules[i]['id'] not in self.rules_used:
                self.rules_used.append(self.shown_rules[i]['id'])
        self.result['rules_used'] = list(self.rules_used)

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

    def _execute(self, goal, step_cap):
        """Act step by step (published ALFWorld ReAct loop) until the subgoal's predicates hold."""
        examples = self._examples(goal)
        flat = self.condition == 'A'
        start = len(self.episode.trace)
        lessons = manual.render(self.shown_rules) + self._reflection_notes()
        while True:
            if self.episode.env.state.check(goal['postconditions'], goal['bindings']):
                return True
            if self.episode.env.state.done or len(self.episode.trace) - start >= step_cap:
                return False
            prompt = react.build(
                self.public_task.get('goal', ''),
                self.task.get('task_type') if self.cfg.react_demos else None, self.episode.trace,
                self.initial_observation, self.episode.env.state.admissible,
                subgoal=None if flat else goal['description'], examples=examples, lessons=lessons,
                brief=self.cfg.actor_brief)
            admissible = list(self.episode.env.state.admissible)
            data = self._ask('actor', {'prompt': prompt, 'admissible': admissible})
            text_reply = data.get('text', '')
            if not react.has_action(text_reply):
                self.result['actor_followups'] += 1
                data = self._ask('actor', {'prompt': prompt, 'admissible': admissible,
                                           'partial': text_reply, 'followup': react.FOLLOWUP,
                                           'followup_tokens': react.FOLLOWUP_TOKENS})
                text_reply = data.get('text', '')
            try:
                self.episode.act(react.parse_action(text_reply))
            except BudgetExceeded:
                raise
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                # An invalid command already appears in the trace and reads "Nothing happens."
                self.result['program_errors'].append(str(exc))

    def _select(self):
        """Choose the rules this game shows (once, at the start; rules do not change during a game)."""
        if not (self.uses_rules and self.rules):
            return
        self.shown_rules = manual.for_agent(self.rules, self.task.get('task_type'), manual.SHOWN,
                                            self.result['goal'], self.embedder.similarity)
        pinned = next((r for r in self.rules if r['id'] == self.pinned), None)
        if pinned is not None and pinned not in self.shown_rules:
            self.shown_rules = self.shown_rules[:manual.SHOWN - 1] + [pinned]
        self.rules_shown = [r['id'] for r in self.shown_rules]
        self.result['rules_shown'] = list(self.rules_shown)

    def _after_plan(self, goals):
        """Remember the plan (the Builder and the rule contexts read it). Skipped when the planner fell back
        to the whole task."""
        if not self.uses_rules or goals[0]['postconditions'] == ['task_won()']:
            return
        self.plan_text = ' ; '.join(g['description'] for g in goals)
        self.result['plan'] = self.plan_text

    def _reflection_notes(self):
        """Reflexion memory for a retried practice game (empty otherwise)."""
        return [f'Your attempt {i} at this same task failed. Your reflection on it: {text}'
                for i, text in enumerate(self.reflections, 1)]

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
        self.gpu, self.gpu_known = 0.0, True
        self.shown_rules, self.rules_shown, self.plan_text, self.rules_used = [], [], '', []
        self.result = {'success': False, 'trace': [], 'subgoals_passed': False, 'program_errors': [],
            'actor_followups': 0, 'input_tokens': 0, 'output_tokens': 0, 'wall_seconds': 0.0,
            'model_wall_seconds': 0.0, 'gpu_seconds': None, 'model_calls': 0, 'retrievals': 0,
            'subgoal_count': 0, 'planner_fallbacks': 0, 'rules_shown': [], 'rules_used': []}
        env = self.env_factory()
        self.episode = Episode(env, self.cfg.step_budget)
        self.public_task = self._public_task(self.task, env)
        try:
            env.reset(task)
            self.initial_observation = env.state.observation
            self.public_task = self._public_task(self.task, env)
            self.result['goal'] = self.public_task.get('goal', '')
            self._select()
            for replan in range(self.cfg.replans + 1):
                try:
                    goals = self._goals(env.state)
                    self.result['subgoal_count'] += len(goals) if self.condition != 'A' else 0
                    self._after_plan(goals)
                    passed = True
                    for goal in goals:
                        flat = self.condition == 'A' or goal['postconditions'] == ['task_won()']
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
            # The Builder reads the trace: fill it first.
            self.result['trace'] = copy.deepcopy(self.episode.trace)
            if self.uses_rules and not self.frozen and self.context.get('phase') == 'practice':
                # AutoManual Builder: update the manual from this game (charged, not capped).
                self.unbudgeted = True
                try:
                    self.result['manual'] = manual.build(self)
                finally:
                    self.unbudgeted = False
        finally:
            self.result['trace'] = copy.deepcopy(self.episode.trace)
            self.result['wall_seconds'] = time.monotonic() - started
            self.result['gpu_seconds'] = self.gpu if self.gpu_known and self.result['model_calls'] else None
            env.close()
        return self.result
