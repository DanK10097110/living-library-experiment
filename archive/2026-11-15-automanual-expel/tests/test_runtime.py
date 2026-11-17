import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from living_library.agents import Agent
from living_library.config import Settings, CONDITIONS
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding, Skill
from living_library.models import FixtureModel, HTTPModel, ModelResponse


TASK = {'object': 'apple 1', 'target': 'cabinet 1'}


class RuntimeTests(unittest.TestCase):
    def agent(self, condition, library=None, model=None, cfg=None):
        cfg = cfg or Settings()
        return Agent(cfg, condition, model or FixtureModel(), library or Library(cfg), LexicalEmbedding(), MiniWorld)

    def test_all_fixture_conditions_and_unknown_gpu(self):
        for condition in CONDITIONS:
            with self.subTest(condition=condition):
                result = self.agent(condition).run(TASK, 12, {'phase': 'practice'})
                self.assertTrue(result['success'], result['program_errors'])
                self.assertIsNone(result['gpu_seconds'])
                self.assertEqual(result['input_tokens'], 0)

    def test_append_only_and_text_preserve_existing_library(self):
        library = Library()
        learned = self.agent('E', library).run(TASK, 1, {})
        self.assertTrue(learned['success'])
        self.assertEqual(len(library.current()), 1)
        before = library.snapshot()
        self.assertTrue(self.agent('E-minus', library).run(TASK, 2, {})['success'])
        self.assertEqual(before, library.snapshot())
        result = self.agent('E-text', library).run(TASK, 3, {})
        self.assertTrue(result['success'])
        self.assertEqual(result['invocations'], [])
        self.assertEqual(before, library.snapshot())

    def test_precondition_failure_never_changes_counts(self):
        library = Library()
        self.agent('E', library).run(TASK, 1, {})
        sid = library.current()[0].id
        class InvalidCall(FixtureModel):
            # Leave the table first, then call the skill whose precondition is being at the table.
            def complete(self, role, payload, seed, context):
                offered = [a for a in payload.get('skills', []) if a.startswith(f'use skill {sid}')]
                if role == 'actor' and offered:
                    if 'At table 1.' in payload['prompt'].split('current observation is: ')[-1]:
                        return ModelResponse({'text': '<action>go to cabinet 1</action>'})
                    return ModelResponse({'text': f'<action>{offered[0]}</action>'})
                return super().complete(role, payload, seed, context)
        before = library.snapshot()
        result = self.agent('E-minus', library, InvalidCall(), Settings(repairs=0, replans=0)).run(TASK, 1, {})
        # Away from the table the skill's precondition fails, so it is not offered: the call is an
        # invalid action, never an invocation (precondition misses are covered in test_core).
        self.assertEqual(result['invocations'], [])
        self.assertEqual(before, library.snapshot())

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

    def test_failed_skill_repair_enters_admission_below_revision_threshold(self):
        library = Library()
        self.agent('E', library).run(TASK, 1, {})
        old = library.current()[0]
        # Simulate a stale stored implementation. One failure is below min_uses
        # and consecutive_failures, but a repair must still be replay-gated.
        old.body = 'act("look")'
        result = self.agent('E', library).run(TASK, 2, {})
        self.assertTrue(result['success'], result['program_errors'])
        self.assertEqual(old.failures, 1)
        self.assertEqual(result['revision_gate_count'], 0)
        self.assertEqual(library.current()[0].parent, old.id)
        self.assertGreaterEqual(result['candidate_attempts'], 1)
        self.assertEqual(result['program_failures'], 1)

    def test_failed_skill_is_refined_with_the_execution_error(self):
        seen = []

        class FirstTryBroken(FixtureModel):
            def complete(self, role, payload, seed, context):
                response = super().complete(role, payload, seed, context)
                if role == 'librarian':
                    seen.append(payload)
                    if 'error' not in payload:               # first round: code that does nothing
                        response.data['candidate']['body'] = 'act("look")\nact("look")'
                return response
        library = Library()
        result = self.agent('E', library, FirstTryBroken()).run(TASK, 1, {})
        self.assertTrue(result['success'])
        self.assertEqual(result['candidate_rejections'], 0)
        self.assertEqual(result['candidate_refinements'], 1)
        self.assertEqual(len(seen), 2)
        self.assertIn('replay', seen[1]['error'])             # the writer saw why it failed
        self.assertEqual(seen[1]['previous_attempt']['body'], 'act("look")\nact("look")')
        self.assertEqual(len(library.current()), 1)

    def test_skill_that_never_verifies_is_dropped_after_all_rounds(self):
        rounds = []

        class Hopeless(FixtureModel):
            def complete(self, role, payload, seed, context):
                response = super().complete(role, payload, seed, context)
                if role == 'librarian':
                    rounds.append(payload)
                    response.data['candidate']['postconditions'] = ['is_hot(object)']   # never achieved
                return response
        cfg = Settings()
        library = Library()
        result = self.agent('E', library, Hopeless(), cfg).run(TASK, 1, {})
        self.assertEqual(len(rounds), cfg.repairs + 1)
        self.assertEqual(result['candidate_rejections'], 1)
        self.assertEqual(library.current(), [])

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
                return json.dumps({'choices': [{'message': {'content': '{"program":"act(\\"look\\")"}'}}],
                                   'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/responses.sqlite'
            with patch('living_library.models.urlopen', return_value=Response()) as request:
                model = HTTPModel(Settings(), path)
                first = model.complete('executor', {'task': TASK}, 11, {'episode': 1})
                self.assertIsNone(first.gpu_seconds)
                model.close()
                model = HTTPModel(Settings(), path)
                self.assertTrue(model.complete('executor', {'task': TASK}, 11, {'episode': 1}).cached)
                model.complete('executor', {'task': TASK}, 12, {'episode': 1})
                model.complete('executor', {'task': TASK}, 11, {'episode': 2})
                self.assertEqual(request.call_count, 3)
                model.close()


if __name__ == '__main__':
    unittest.main()
