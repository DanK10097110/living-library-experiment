"""Usage-based evidence (redesign of 2026-11-20): one outcome-blind judge call per shown rule; only followed
rules get usefulness scores, the others count as shown; a judge failure gives no evidence; useless rules
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
    """Per-rule judge that says the rules with text in `followed` were followed (usefulness 1); None: broken."""
    def __init__(self, followed):
        self.followed, self.judge_payloads = followed, []

    def complete(self, role, payload, seed, context):
        if role == 'judge':
            self.judge_payloads.append(payload)
            if self.followed is None:
                raise RuntimeError('down')
            hit = payload['rule']['rule'] in self.followed
            return ModelResponse({'followed': 'yes' if hit else 'no', 'usefulness': int(hit), 'reason': 'r'})
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
        self.assertEqual(len(model.judge_payloads), 2)                   # one call per shown rule
        self.assertEqual((rules[0]['ev']['followed'], rules[0]['ev']['sum']), (1, 1))
        self.assertEqual((rules[1]['ev']['shown'], rules[1]['ev']['followed']), (1, 0))
        self.assertEqual(manual.replay(live, result['manual']['operations'], []), rules)

    def test_judge_failure_gives_no_evidence(self):
        rules = self.two_rules()
        result = play(rules, Reporting(None))
        self.assertEqual([r['ev'] for r in rules if r['type'] != 'Failure Pool'], [manual.empty_evidence()] * 2)
        self.assertTrue(any('no evidence' in e for e in result['manual']['errors']))


class UsageCreditTests(unittest.TestCase):
    def test_a_followed_loss_counts_as_followed_with_its_score(self):
        lost = [rule(1, 'a'), rule(2, 'b')]
        manual.observe(lost, {**verdict(lost[0], True, -1), **verdict(lost[1], False)}, context(), 0, False)
        self.assertEqual((lost[0]['ev']['followed'], lost[0]['ev']['lost'], lost[0]['ev']['sum']), (1, 1, -1))
        self.assertEqual((lost[1]['ev']['shown'], lost[1]['ev']['followed'], lost[1]['ev']['lost']), (1, 0, 0))

    def test_recipe_is_counted_only_when_the_judge_says_it_was_followed(self):
        recipe = rule(1, 'Take, go, put.', kind='Success Process')
        manual.observe([recipe], verdict(recipe, False), context(), 0, True)
        self.assertEqual((recipe['ev']['shown'], recipe['ev']['followed']), (1, 0))
        manual.observe([recipe], verdict(recipe, True, 2), context(), 1, True)
        self.assertEqual((recipe['ev']['followed'], recipe['ev']['sum']), (1, 2))

    def test_useless_rule_is_retired_including_recipes_and_anti_patterns(self):
        def shown(i, followed, times, kind='Corrected Error'):
            return rule(i, chr(96 + i), kind, ev={**manual.empty_evidence(), 'shown': times, 'followed': followed})
        borderline = shown(1, 3, 14)                                 # followed 3 of 14 = 21%
        junk = shown(2, 1, 12)                                       # followed 1 of 12
        few = shown(3, 0, 11)                                        # judged 11 times only
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
