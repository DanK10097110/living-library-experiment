import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from living_library.agents import Agent
from living_library.config import Settings, CONDITIONS
from living_library.embedding import LexicalEmbedding
from living_library.environments import MiniWorld
from living_library.models import FixtureModel, HTTPModel, ModelResponse


TASK = {'object': 'apple 1', 'target': 'cabinet 1'}
KIND = 'pick_and_place_simple'
KIND_TASK = {**TASK, 'task_type': KIND}
RULE = {'id': 'rule_1', 'type': 'Success Process', 'task_type': KIND,
        'rule': 'When the task is to put an object somewhere: 1. take it, 2. go there, 3. open it, 4. move it in.',
        'example': '', 'sources': [], 'contexts': []}


class RuntimeTests(unittest.TestCase):
    def agent(self, condition, model=None, cfg=None, **kwargs):
        return Agent(cfg or Settings(), condition, model or FixtureModel(), LexicalEmbedding(), MiniWorld, **kwargs)

    def test_all_fixture_conditions_and_unknown_gpu(self):
        for condition in CONDITIONS:
            with self.subTest(condition=condition):
                result = self.agent(condition).run(TASK, 12, {})
                self.assertTrue(result['success'], result['program_errors'])
                self.assertIsNone(result['gpu_seconds'])
                self.assertEqual(result['input_tokens'], 0)

    def test_prompts_carry_no_skill_channel(self):
        seen = []

        class Spy(FixtureModel):
            def complete(self, role, payload, seed, context):
                seen.append((role, payload))
                return super().complete(role, payload, seed, context)
        self.agent('E', Spy(), rules=[RULE], frozen=True).run(KIND_TASK, 1, {'phase': 'evaluation'})
        planner = [p for r, p in seen if r == 'planner']
        actor = [p for r, p in seen if r == 'actor']
        self.assertTrue(planner and actor)
        self.assertNotIn('catalog', planner[0])
        self.assertEqual(planner[0]['rules'], ['[Success Process] ' + RULE['rule']])
        self.assertTrue(all(set(p) == {'task', 'prompt', 'admissible'} for p in actor))
        self.assertIn(RULE['rule'], actor[0]['prompt'])
        self.assertNotIn('use skill', actor[0]['prompt'])

    def test_frozen_rules_shown_once_and_never_changed(self):
        rules = [copy.deepcopy(RULE)]
        agent = self.agent('E', rules=rules, frozen=True)
        result = agent.run(KIND_TASK, 1, {'phase': 'practice'})
        self.assertEqual(result['rules_shown'], ['rule_1'])
        self.assertEqual(agent.rules_shown, ['rule_1'])
        self.assertEqual(rules, [RULE])
        self.assertNotIn('manual', result)                                   # frozen: no Builder
        self.assertEqual(agent.plan_text, 'put object in target')
        self.assertEqual(result['plan'], 'put object in target')

    def test_retry_agent_is_a_frozen_copy_with_reflections(self):
        rules, trajectories = [copy.deepcopy(RULE)], [{'goal': 'g', 'trace': []}]
        agent = self.agent('E-minus', rules=rules, trajectories=trajectories)
        retry = agent.retry_agent(['look first'])
        self.assertIsInstance(retry, Agent)
        self.assertTrue(retry.frozen)
        self.assertEqual((retry.cfg, retry.condition, retry.model, retry.embedder, retry.env_factory),
                         (agent.cfg, agent.condition, agent.model, agent.embedder, agent.env_factory))
        self.assertIs(retry.rules, rules)
        self.assertIs(retry.trajectories, trajectories)
        self.assertEqual(retry.reflections, ['look first'])
        self.assertEqual(agent.reflections, [])
        seen = []

        class Spy(FixtureModel):
            def complete(self, role, payload, seed, context):
                seen.append((role, payload))
                return super().complete(role, payload, seed, context)
        retry.model = Spy()
        result = retry.run(KIND_TASK, 1, {'phase': 'practice', 'attempt': 1})
        self.assertTrue(result['success'])
        self.assertEqual(rules, [RULE])
        self.assertEqual(next(p for r, p in seen if r == 'planner')['reflections'], ['look first'])
        self.assertIn('Your reflection on it: look first', next(p for r, p in seen if r == 'actor')['prompt'])

    def test_fixture_planner_cites_shown_rules_and_unknown_roles(self):
        model = FixtureModel()
        cited = model.complete('citer', {'task': TASK, 'rules': ['1. a', '2. b'], 'plan': ['p']}, 1, {}).data
        self.assertEqual(cited['used_rules'], ['1', '2'])
        self.assertEqual(set(model.complete('planner', {'task': TASK}, 1, {}).data), {'subgoals'})
        for role in ('librarian', 'reflector', 'refiner', 'judge'):
            with self.assertRaises(KeyError):
                model.complete(role, {'task': TASK}, 1, {})

    def test_environment_closed_on_model_error(self):
        class Broken(FixtureModel):
            def complete(self, *args):
                raise ValueError('bad JSON')
        class Tracked(MiniWorld):
            closed = False
            def close(self):
                self.closed = True
        env = Tracked()
        agent = self.agent('C', model=Broken())
        agent.env_factory = lambda: env
        result = agent.run(TASK, 1, {})
        self.assertFalse(result['success'])
        self.assertTrue(env.closed)
        self.assertIsNone(result['gpu_seconds'])

    def test_transport_failure_stops_without_scoring_episode(self):
        class Offline(FixtureModel):
            def complete(self, *args):
                raise OSError('local model server unavailable')
        with self.assertRaisesRegex(OSError, 'unavailable'):
            self.agent('C', model=Offline()).run(TASK, 1, {})

    def test_symbolic_goals_and_flat_observation_steps(self):
        class Symbolic(FixtureModel):
            def __init__(self):
                self.flat_observations = []
            def complete(self, role, payload, seed, context):
                response = super().complete(role, payload, seed, context)
                if role == 'planner':
                    response.data['subgoals'][0]['postconditions'] = ['located(object, target)']
                if role == 'actor' and context.get('flat'):
                    # The flat actor must see the CURRENT observation at every step.
                    self.flat_observations.append(payload['prompt'].split('current observation is: ')[1])
                return response
        model = Symbolic()
        self.assertTrue(self.agent('C', model=model).run(TASK, 1, {})['success'])
        self.assertTrue(self.agent('A', model=model).run(TASK, 1, {'flat': True})['success'])
        self.assertEqual(len(model.flat_observations), 4)
        self.assertEqual(len(set(model.flat_observations)), 4)

    def test_runaway_actor_reply_gets_one_followup(self):
        class Rambler(FixtureModel):
            def __init__(self):
                self.followups = []
            def complete(self, role, payload, seed, context):
                if role == 'actor' and 'partial' not in payload and context.get('call_index') == 1:
                    return ModelResponse({'text': 'Let me think about this at great length...'}, 10, 512)
                if role == 'actor' and 'partial' in payload:
                    self.followups.append(payload)
                return super().complete(role, payload, seed, context)
        model = Rambler()
        result = self.agent('C', model=model).run(TASK, 1, {})
        self.assertTrue(result['success'], result['program_errors'])
        self.assertEqual(result['actor_followups'], 1)
        self.assertEqual(model.followups[0]['partial'], 'Let me think about this at great length...')
        # The follow-up is a three-turn chat with a short token cap.
        with tempfile.TemporaryDirectory() as directory:
            http = HTTPModel(Settings(), directory + '/c.sqlite')
            request = http.request('actor', {'prompt': 'P', 'partial': 'thinking', 'followup': 'act now',
                                             'followup_tokens': 64}, 1)
            http.close()
        self.assertEqual([m['role'] for m in request['messages']], ['user', 'assistant', 'user'])
        self.assertEqual(request['max_tokens'], 64)

    def test_judge_is_a_json_role(self):
        with tempfile.TemporaryDirectory() as directory:
            http = HTTPModel(Settings(), directory + '/c.sqlite')
            request = http.request('judge', {'task': {'goal': 'g'}, 'instructions': 'judge it', 'rule': RULE,
                                             'response_schema': {'followed': 'yes|no'}}, 1)
            http.close()
        self.assertEqual(request['response_format'], {'type': 'json_object'})
        self.assertIn('judge it', request['messages'][0]['content'])
        self.assertEqual(request['max_tokens'], Settings().max_tokens)

    def test_malformed_http_response_is_cached_with_cost(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps({'choices': [{'message': {'content': 'not JSON'}}],
                                   'usage': {'prompt_tokens': 12, 'completion_tokens': 3}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            with patch('living_library.models.urlopen', return_value=Response()) as request:
                model = HTTPModel(Settings(), directory + '/cache.sqlite')
                first = model.complete('planner', {'task': TASK}, 1, {'n': 1})
                self.assertIn('_response_error', first.data)
                self.assertEqual((first.input_tokens, first.output_tokens), (12, 3))
                again = model.complete('planner', {'task': TASK}, 1, {'n': 1})
                self.assertTrue(again.cached)
                self.assertEqual(again.input_tokens, 12)
                self.assertEqual(request.call_count, 1)
                # The plain-text actor role keeps the raw text; it is parsed for an <action> tag.
                self.assertEqual(model.complete('actor', {'prompt': 'p'}, 1, {'n': 2}).data, {'text': 'not JSON'})
                model.close()

    def test_http_durable_cache_has_seed_and_context(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps({'choices': [{'message': {'content': '{"subgoals":[]}'}}],
                                   'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/responses.sqlite'
            with patch('living_library.models.urlopen', return_value=Response()) as request:
                model = HTTPModel(Settings(), path)
                first = model.complete('builder', {'task': TASK}, 11, {'episode': 1})
                self.assertIsNone(first.gpu_seconds)
                model.close()
                model = HTTPModel(Settings(), path)
                self.assertTrue(model.complete('builder', {'task': TASK}, 11, {'episode': 1}).cached)
                model.complete('builder', {'task': TASK}, 12, {'episode': 1})
                model.complete('builder', {'task': TASK}, 11, {'episode': 2})
                self.assertEqual(request.call_count, 3)
                model.close()


if __name__ == '__main__':
    unittest.main()
