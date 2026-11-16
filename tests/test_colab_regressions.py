"""Recorded requests test validation only, not counterfactual LLM success."""
import json
from pathlib import Path
import unittest

from living_library.agents import Agent
from living_library.config import Settings
from living_library.domain import Predicate, State
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse


class ColabRegressions(unittest.TestCase):
    def test_recorded_planner_navigation_contracts(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/colab_light_plans.json').read_text())
        rejected = []
        for row in rows:
            for goal in row['response']['subgoals']:
                args = {a for p in goal['postconditions']
                        for a in Predicate.parse(p).bind(goal['bindings']).args}
                # Include guessed names deliberately: existence alone used to pass.
                state = State(row['state']['observation'], row['state']['admissible_commands'], args,
                              {('at', row['current_location'])} if row['current_location'] else set())
                invalid = any(Predicate.parse(p).bind(goal['bindings']).name == 'at'
                              and Predicate.parse(p).bind(goal['bindings']).args[0].startswith('desklamp')
                              for p in goal['postconditions'])
                if invalid:
                    with self.assertRaisesRegex(ValueError, 'Invalid navigation goal'):
                        Agent._validate_conditions(goal['postconditions'], state, goal['bindings'])
                    rejected.append(row['call_index'])
                else:
                    Agent._validate_conditions(goal['postconditions'], state, goal['bindings'])
        self.assertEqual(rejected, [8, 9, 13, 17, 21, 25, 29, 33, 37])

    def test_repeated_impossible_plan_stops_without_executor_calls(self):
        class RepeatingModel:
            def complete(self, role, payload, seed, context):
                assert role == 'planner', 'Impossible goal reached executor'
                return ModelResponse({'subgoals': [{
                    'description': f'Changing wording {context["call_index"]}',
                    'bindings': {}, 'postconditions': ['at(desklamp 1)']}]})
        cfg = Settings(replans=15, max_model_calls=40)
        agent = Agent(cfg, 'C', RepeatingModel(), Library(cfg), LexicalEmbedding(), MiniWorld)
        result = agent.run({}, 11, {})
        self.assertFalse(result['success'])
        self.assertEqual(result['model_calls'], 3)
        self.assertEqual(result['trace'], [])
        self.assertIn('same plan returned three times', result['program_errors'][-1])

    def test_successful_fixture_still_completes(self):
        cfg = Settings()
        agent = Agent(cfg, 'C', FixtureModel(), Library(cfg), LexicalEmbedding(), MiniWorld)
        result = agent.run({'object': 'apple 1', 'target': 'cabinet 1'}, 11, {})
        self.assertTrue(result['success'], result['program_errors'])


if __name__ == '__main__':
    unittest.main()
