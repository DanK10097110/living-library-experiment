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
            def complete(self, role, payload, seed, context):
                if role == 'executor':
                    return ModelResponse({'program': f'act("go to cabinet 1")\ncall({sid!r}, object="apple 1", target="cabinet 1")'})
                return super().complete(role, payload, seed, context)
        before = library.snapshot()
        result = self.agent('E-minus', library, InvalidCall(), Settings(repairs=0, replans=0)).run(TASK, 1, {})
        self.assertFalse(result['success'])
        self.assertTrue(result['invocations'][0]['retrieval_error'])
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
                if payload.get('flat'):
                    self.flat_observations.append(payload['state']['observation'])
                return response
        model = Symbolic()
        self.assertTrue(self.agent('C', model=model).run(TASK, 1, {})['success'])
        self.assertTrue(self.agent('A', model=model).run(TASK, 1, {})['success'])
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

    def test_weak_candidate_contract_is_rejected(self):
        class Weak(FixtureModel):
            def complete(self, role, payload, seed, context):
                response = super().complete(role, payload, seed, context)
                if role == 'librarian':
                    response.data['candidate']['postconditions'] = ['exists(object)']
                    response.data['candidate']['body'] = 'act("look")'
                return response
        library = Library()
        result = self.agent('E', library, Weak()).run(TASK, 1, {})
        self.assertTrue(result['success'])
        self.assertEqual(result['candidate_rejections'], 1)
        self.assertEqual(library.current(), [])

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
                model = HTTPModel(Settings(replans=0, repairs=0), directory + '/cache.sqlite')
                agent = self.agent('A', model=model, cfg=Settings(replans=0, repairs=0))
                result = agent.run(TASK, 1, {})
                self.assertEqual(result['input_tokens'], 12)
                self.assertEqual(result['output_tokens'], 3)
                self.assertEqual(result['program_failures'], 1)
                agent.run(TASK, 1, {})
                self.assertEqual(request.call_count, 1)
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
