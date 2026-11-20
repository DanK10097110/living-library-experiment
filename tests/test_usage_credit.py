"""Usage-based credit: only rules the Builder says were followed get Beta updates."""
import copy
import unittest

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}


def rule(i, text, kind='Corrected Error', **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', 'pick')
    r.update(extra)
    return r


def context():
    return {'task': 'put apple in cabinet', 'task_type': 'pick', 'steps': []}


class Reporting(FixtureModel):
    """Builder that reports which shown rules the actions followed (None: leaves the key out)."""
    def __init__(self, followed):
        self.followed = followed

    def complete(self, role, payload, seed, context):
        if role == 'builder':
            if 'followed' in payload.get('response_schema', {}):     # the separate outcome-blind judge
                self.judge_payloads = getattr(self, 'judge_payloads', []) + [payload]
                return ModelResponse({} if self.followed is None else {'followed': self.followed})
            return ModelResponse({'diagnosis': 'imperfect agent', 'operations': []})
        return super().complete(role, payload, seed, context)


def play(followed, rules, model=None):
    agent = Agent(Settings(), 'E', model or Reporting(followed), Library(), LexicalEmbedding(), MiniWorld,
                  rules=rules)
    return agent.run(TASK, 1, {'phase': 'practice', 'position': 4})


class UsageCreditTests(unittest.TestCase):
    def two_rules(self):
        return [rule(1, 'When putting an apple, open the cabinet first.'),
                rule(2, 'When putting an apple, open the cabinet before anything else.')]

    def test_only_followed_rules_get_credit_the_others_count_unused(self):
        rules = self.two_rules()
        live = copy.deepcopy(rules)
        result = play(['rule_1', 'rule_99'], rules)
        self.assertEqual(set(result['rules_shown']), {'rule_1', 'rule_2'})
        self.assertEqual(result['manual']['followed'], ['rule_1'])
        self.assertEqual(rules[0]['alpha'], 2)
        self.assertEqual((rules[1].get('alpha', 1), rules[1].get('unused')), (1, 1))
        self.assertEqual(manual.replay(live, result['manual']['operations'], []), rules)

    def test_missing_followed_credits_every_shown_rule_and_logs_it(self):
        rules = self.two_rules()
        result = play(None, rules)
        self.assertEqual([r['alpha'] for r in rules[:2]], [2, 2])
        self.assertTrue(any('no followed list' in e for e in result['manual']['errors']))

    def test_judge_is_outcome_blind_and_a_followed_loss_counts_as_a_loss(self):
        model = Reporting(['rule_1'])
        rules = self.two_rules()
        result = play(None, rules, model)
        payload = model.judge_payloads[0]
        self.assertEqual(set(payload), {'instructions', 'goal', 'rules', 'steps', 'response_schema', 'task'})
        self.assertNotIn('success', repr(payload['task']))
        self.assertTrue(all(set(s) <= {'action', 'observation'} for s in payload['steps']))
        self.assertNotIn('observation', payload['steps'][-1])       # the final message would reveal the win
        self.assertEqual({r['id'] for r in payload['rules']}, {'rule_1', 'rule_2'})
        # the same judge answer in a lost game: followed rule gets beta + 1, the other only unused
        lost = [rule(1, 'a'), rule(2, 'b')]
        manual.observe(lost, ['rule_1', 'rule_2'], False, context(), 0, followed=['rule_1'])
        self.assertEqual((lost[0]['beta'], lost[1].get('beta', 1), lost[1]['unused']), (2, 1, 1))
        self.assertIn(result['success'], (True, False))

    def test_judge_failure_credits_all_shown_rules(self):
        class Broken(Reporting):
            def complete(self, role, payload, seed, context):
                if 'followed' in payload.get('response_schema', {}):
                    raise RuntimeError('down')
                return super().complete(role, payload, seed, context)
        rules = self.two_rules()
        result = play(None, rules, Broken(None))
        self.assertEqual([r['alpha'] + r['beta'] for r in rules[:2]], [3, 3])
        self.assertTrue(any('followed judge' in e for e in result['manual']['errors']))

    def test_recipe_is_credited_only_when_the_judge_says_it_was_followed(self):
        # (2026-11-20 design review) no circular credit: a recipe shapes the plan, but counts only if followed
        recipe, other = rule(1, 'Take, go, put.', kind='Success Process'), rule(2, 'x')
        op = manual.observe([recipe, other], ['rule_1', 'rule_2'], True, context(), 0, followed=[])
        self.assertEqual((op['ids'], op['unused']), ([], ['rule_1', 'rule_2']))
        self.assertEqual((recipe['alpha'], recipe['unused'], other.get('alpha', 1)), (1, 1, 1))
        op = manual.observe([recipe, other], ['rule_1', 'rule_2'], True, context(), 1, followed=['rule_1'])
        self.assertEqual((op['ids'], recipe['alpha']), (['rule_1'], 2))

    def test_useless_rule_is_retired_but_recipes_and_anti_patterns_are_exempt(self):
        borderline = rule(1, 'a', alpha=3, beta=1, unused=8)     # followed 3 of 12 = 25%
        junk = rule(2, 'b', alpha=1, beta=2, unused=8)           # followed 1 of 9
        few = rule(3, 'c', unused=7)                              # shown 7 times only
        recipe = rule(4, 'd', kind='Success Process', unused=20)
        anti = rule(5, 'e', kind='Anti-Pattern', unused=20)
        self.assertEqual([manual.useless(r) for r in (borderline, junk, few, recipe, anti)],
                         [False, True, False, False, False])
        rules, report = [borderline, junk, few, recipe], {'operations': [], 'errors': []}
        manual.retire(rules, report)
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_3', 'rule_4'])
        self.assertIn('useless', report['errors'][0])


if __name__ == '__main__':
    unittest.main()
