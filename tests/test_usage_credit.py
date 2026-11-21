"""Usage-based evidence (redesign of 2026-11-20): a shown rule is used when the planner cites it; only used
rules get scores, the others count as shown; bad citations are ignored; no judge call; useless rules
(recipes and Anti-Patterns included) are retired."""
import copy
import unittest

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.models import FixtureModel, ModelResponse

from living_library.embedding import LexicalEmbedding

TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}


def rule(i, text, kind='Corrected Error', **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', 'pick')
    r.update(extra)
    return r


def context():
    return {'task': 'put apple in cabinet', 'task_type': 'pick', 'steps': []}


def verdict(r, followed, score=0):
    return {r['id']: {'followed': followed, 'usefulness': score, 'reason': '', 'rule': r['rule']}}


class Reporting(FixtureModel):
    """A citer that lists the shown rules whose text is in `followed`; `followed` None: it cites nonsense."""
    def __init__(self, followed):
        self.followed, self.citer_payloads, self.roles = followed, [], []

    def complete(self, role, payload, seed, context):
        self.roles.append(role)
        if role == 'citer':
            self.citer_payloads.append(payload)
            if self.followed is None:
                return ModelResponse({'used_rules': ['99', 'zero', None]})
            return ModelResponse({'used_rules': [line.split('.')[0] for line in payload['rules']
                                                 if any(text in line for text in self.followed)]})
        if role == 'builder':
            return ModelResponse({'diagnosis': 'imperfect agent', 'operations': []})
        return super().complete(role, payload, seed, context)


def play(rules, model):
    agent = Agent(Settings(), 'E', model, LexicalEmbedding(), MiniWorld, rules=rules)
    return agent.run(TASK, 1, {'phase': 'practice', 'position': 4})


class UsageCreditInGames(unittest.TestCase):
    def two_rules(self):
        return [rule(1, 'When putting an apple, open the cabinet first.'),
                rule(2, 'When putting an apple, open the cabinet before anything else.')]

    def test_only_followed_rules_get_scores_the_others_count_as_shown(self):
        rules = self.two_rules()
        live = copy.deepcopy(rules)
        model = Reporting([rules[0]['rule']])
        result = play(rules, model)
        self.assertEqual(set(result['rules_shown']), {'rule_1', 'rule_2'})
        self.assertEqual(result['rules_used'], ['rule_1'])
        self.assertNotIn('judge', model.roles)                            # no model call for evidence
        self.assertTrue(all(line[0].isdigit() for line in model.citer_payloads[0]['rules']))     # numbered
        self.assertEqual(model.citer_payloads[0]['plan'], ['put object in target'])             # the plan only
        self.assertNotIn('trace', model.citer_payloads[0])
        self.assertEqual((rules[0]['ev']['followed'], rules[0]['ev']['sum']), (1, 1))            # used, won
        self.assertEqual((rules[1]['ev']['shown'], rules[1]['ev']['followed']), (1, 0))
        self.assertEqual(manual.replay(live, result['manual']['operations'], []), rules)

    def test_bad_citations_are_ignored(self):
        rules = self.two_rules()
        result = play(rules, Reporting(None))
        self.assertEqual(result['rules_used'], [])
        self.assertEqual([(r['ev']['shown'], r['ev']['followed']) for r in rules if r['type'] != 'Failure Pool'],
                         [(1, 0), (1, 0)])


class UsageCreditTests(unittest.TestCase):
    def test_a_followed_loss_counts_as_followed_with_its_score(self):
        lost = [rule(1, 'a'), rule(2, 'b')]
        manual.observe(lost, {**verdict(lost[0], True, -1), **verdict(lost[1], False)}, context(), 0, False)
        self.assertEqual((lost[0]['ev']['followed'], lost[0]['ev']['lost'], lost[0]['ev']['sum']), (1, 1, -1))
        self.assertEqual((lost[1]['ev']['shown'], lost[1]['ev']['followed'], lost[1]['ev']['lost']), (1, 0, 0))

    def test_recipe_is_counted_only_when_it_was_used(self):
        recipe = rule(1, 'Take, go, put.', kind='Success Process')
        manual.observe([recipe], verdict(recipe, False), context(), 0, True)
        self.assertEqual((recipe['ev']['shown'], recipe['ev']['followed']), (1, 0))
        manual.observe([recipe], verdict(recipe, True, 2), context(), 1, True)
        self.assertEqual((recipe['ev']['followed'], recipe['ev']['sum']), (1, 2))

    def test_useless_rule_is_retired_including_recipes_and_anti_patterns(self):
        def shown(i, followed, times, kind='Corrected Error'):
            return rule(i, chr(96 + i), kind, ev={**manual.empty_evidence(), 'shown': times, 'followed': followed})
        n = manual.USELESS_MIN
        borderline = shown(1, 4, n + 2)                              # used 4 of 18 = 22%
        junk = shown(2, 1, n)                                        # used 1 of 16
        few = shown(3, 0, n - 1)                                     # shown 15 times only
        recipe = shown(4, 0, 20, 'Success Process')
        anti = shown(5, 1, 20, 'Anti-Pattern')
        note = shown(6, 0, 20, 'Unresolved Error')
        self.assertEqual([manual.useless(r) for r in (borderline, junk, few, recipe, anti, note)],
                         [False, True, False, True, True, False])
        rules = [borderline, junk, few, recipe]
        ops = manual.batch_upkeep(rules, set(), None)
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_3'])
        self.assertTrue(all('useless' in op['reason'] for op in ops))


if __name__ == '__main__':
    unittest.main()
