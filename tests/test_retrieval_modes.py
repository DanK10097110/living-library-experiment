"""Switchable rule retrieval (task / placeholder / plan / steps): only which rules are shown changes."""
import unittest

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel

SIM = LexicalEmbedding().similarity
GOAL = 'heat some egg and put it in countertop'


def rule(i, text, goals=(), plans=(), task_type='heat'):
    r = manual.new_rule(f'rule_{i}', 'Special Phenomenon', text, '', task_type)
    r['alpha'] = 1 + len(goals)
    r['contexts'] = [{'task': g, 'task_type': task_type, 'won': True, **({'plan': p} if p else {})}
                     for g, p in zip(goals, plans or [None] * len(goals))]
    return r


def shown(rules, mode, probe='', goal=GOAL, k=1):
    return [r['id'] for r in manual.for_agent(rules, 'heat', k, goal, SIM, mode, probe)]


class MaskTests(unittest.TestCase):
    def test_objects_and_receptacles_become_placeholders(self):
        self.assertEqual(manual.mask('heat some apple and put it in fridge'), 'heat some OBJ and put it in RECEP')
        self.assertEqual(manual.mask('put two pillows in sofa.'), 'put two OBJ in RECEP.')
        self.assertEqual(manual.mask('look at mug under the desklamp'), 'look at OBJ under the desklamp')


class PlaceholderTests(unittest.TestCase):
    def test_matches_by_task_structure_not_object(self):
        by_task = rule(1, 'When a, b.', goals=['heat some apple and put it in fridge'])
        by_object = rule(2, 'When c, d.', goals=['clean some egg and put it in countertop'])
        rules = [by_task, by_object]
        self.assertEqual(shown(rules, 'task'), ['rule_2'])           # the shared object wins
        self.assertEqual(shown(rules, 'placeholder'), ['rule_1'])    # the shared structure wins


class PlanTests(unittest.TestCase):
    PLAN_A = 'find and take the egg ; heat the egg with the microwave ; put the egg in the countertop'
    PLAN_B = 'open the drawer ; take the spoon ; clean the spoon'

    def rules(self):
        return [rule(1, 'When a, b.', goals=['x'], plans=[self.PLAN_A]),
                rule(2, 'When c, d.', goals=['y'], plans=[self.PLAN_B])]

    def test_plan_is_the_query_against_plans_of_won_games(self):
        self.assertEqual(shown(self.rules(), 'plan', 'take the egg and heat the egg in the microwave'), ['rule_1'])
        self.assertEqual(shown(self.rules(), 'plan', 'take the spoon and clean the spoon in the drawer'), ['rule_2'])

    def test_rule_without_a_stored_plan_falls_back_to_task_and_coverage_is_reported(self):
        old = rule(3, 'When e, f.', goals=[GOAL])                 # frozen rule: goals only
        rules = [old, rule(2, 'When c, d.', goals=['y'], plans=[self.PLAN_B])]
        self.assertEqual(shown(rules, 'plan', 'take the egg and heat the egg in the microwave'), ['rule_3'])
        self.assertEqual(manual.plan_coverage(rules + [rule(4, 'When g, h.')]), (1, 3))

    def test_no_plan_means_task_mode(self):
        rules = self.rules()
        self.assertEqual(shown(rules, 'plan', ''), shown(rules, 'task'))

    def test_steps_match_a_single_subgoal_of_a_plan(self):
        rules = self.rules()
        probe = 'heat the egg with the microwave. take egg'
        self.assertEqual(shown(rules, 'steps', probe), ['rule_1'])


class AgentTests(unittest.TestCase):
    TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}

    def play(self, mode, rules):
        agent = Agent(Settings(), 'E', FixtureModel(), Library(), LexicalEmbedding(), MiniWorld, rules=rules,
                      retrieval=mode)
        return agent, agent.run(self.TASK, 1, {'phase': 'practice', 'position': 0})

    def test_every_mode_runs_records_the_plan_and_credits_the_shown_rules(self):
        for mode in manual.MODES:
            rules = [rule(1, 'When putting an apple, open the cabinet first.', task_type='pick')]
            agent, result = self.play(mode, rules)
            self.assertEqual(result['rules_shown'], ['rule_1'], mode)
            self.assertTrue(result['plan'], mode)
            self.assertEqual(rules[0]['contexts'][-1]['plan'], result['plan'], mode)   # stored with the win
            self.assertEqual(rules[0]['alpha'], 2, mode)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            Agent(Settings(), 'E', FixtureModel(), Library(), LexicalEmbedding(), MiniWorld, retrieval='bogus')


if __name__ == '__main__':
    unittest.main()
