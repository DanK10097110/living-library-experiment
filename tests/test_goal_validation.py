import unittest

from living_library.agents import Agent
from living_library.domain import State


class GoalValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = State('', [], {'alarmclock 1', 'desk 1'})

    def test_empty_bindings_cannot_hide_invalid_literal(self):
        with self.assertRaisesRegex(ValueError, 'Invalid postcondition entity'):
            Agent._validate_conditions(['located(alarmclock, desk 1)'], self.state, {})

    def test_literals_bound_parameters_and_terminal_goal(self):
        for conditions, bindings in [
            (['located(alarmclock 1, desk 1)'], {}),
            (['located(object, target)'], {'object': 'alarmclock 1', 'target': 'desk 1'}),
            (['task_won()'], {}),
        ]:
            Agent._validate_conditions(conditions, self.state, bindings)

    def test_unbound_parameter_rejected(self):
        with self.assertRaises(ValueError):
            Agent._validate_conditions(['holding(object)'], self.state, {})

    def test_skill_contract_syntax_still_accepts_parameters(self):
        Agent._validate_conditions(['holding(object)'])

    def test_navigation_rejects_existing_lamp(self):
        state = State('', ['go to shelf 1'], {'desk 1', 'shelf 1', 'desklamp 1'},
                      {('at', 'desk 1')})
        with self.assertRaisesRegex(ValueError, 'Invalid navigation goal'):
            Agent._validate_conditions(['at(desklamp 1)'], state, {})
        Agent._validate_conditions(['at(desk 1)'], state, {})
        Agent._validate_conditions(['at(destination)'], state, {'destination': 'shelf 1'})
