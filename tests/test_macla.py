"""MACLA mechanisms in the rule manual (Bayesian reliability, expected utility, contrastive
refinement, merging, pruning) and their batching replay."""
import copy
import unittest
from unittest.mock import patch

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}


def rule(i, text, kind='Corrected Error', task_type='pick', **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', task_type)
    r.update(extra)
    return r


def context(won, task_type='pick'):
    return {'task': 'put apple in cabinet', 'task_type': task_type, 'steps': []}


class BayesTests(unittest.TestCase):
    def test_wins_raise_alpha_losses_raise_beta_and_contexts_are_capped(self):
        rules = [rule(1, 'When x, do y.')]
        for i in range(20):
            manual.observe(rules, ['rule_1'], True, context(True), i)
        manual.observe(rules, ['rule_1'], False, context(False), 20)
        r = rules[0]
        self.assertEqual((r['alpha'], r['beta']), (21, 2))
        self.assertEqual(sum(c['won'] for c in r['contexts']), manual.K_CONTEXTS)
        self.assertEqual(sum(not c['won'] for c in r['contexts']), 1)
        self.assertEqual(manual.observed(r), [20, 1])               # counts are not capped
        self.assertEqual(r['last_used'], 20)

    def test_expected_utility_prefers_reliable_and_penalises_risk(self):
        good = rule(1, 'a', alpha=9, beta=1)
        bad = rule(2, 'b', alpha=1, beta=9, contexts=[{'task_type': 'pick', 'won': False}] * 5)
        self.assertGreater(manual.expected_utility(good, 0.8, 'pick'), manual.expected_utility(bad, 0.8, 'pick'))
        # Risk only counts failures on this kind of task.
        other_kind = rule(3, 'c', alpha=1, beta=9, contexts=[{'task_type': 'heat', 'won': False}] * 5)
        self.assertGreater(manual.expected_utility(other_kind, 0.8, 'pick'), manual.expected_utility(bad, 0.8, 'pick'))
        # Uncertainty bonus: an untried rule is not ranked last just for being new.
        self.assertGreater(manual.expected_utility(rule(4, 'd'), 0.8, 'pick'), manual.expected_utility(bad, 0.8, 'pick'))

    def test_relevant_ranks_by_utility_but_keeps_the_recipe_first(self):
        recipe = rule(9, 'recipe', kind='Success Process')
        weak = rule(1, 'open the cabinet first', alpha=1, beta=6)
        strong = rule(2, 'open the cabinet first', alpha=6, beta=1)
        shown = manual.relevant([weak, strong, recipe], 'pick', 3, 'put apple in cabinet',
                                LexicalEmbedding().similarity)
        self.assertEqual([r['id'] for r in shown], ['rule_9', 'rule_2', 'rule_1'])


class Refiner(FixtureModel):
    def __init__(self):
        self.calls = []

    def complete(self, role, payload, seed, context):
        if role == 'refiner':
            self.calls.append(payload)
            return ModelResponse({'rule': 'When x and the cabinet is closed, open it first.', 'not_when': 'x is held'})
        return super().complete(role, payload, seed, context)


def agent(rules, model):
    a = Agent(Settings(), 'E', model, Library(), LexicalEmbedding(), MiniWorld, rules=rules)
    a.result = {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'model_wall_seconds': 0.0}
    a.seed, a.context, a.gpu_known, a.public_task = 1, {}, True, {}
    return a


class RefinePruneMergeTests(unittest.TestCase):
    def test_refinement_needs_three_new_wins_and_losses(self):
        rules = [rule(1, 'When x, do y.')]
        for won in (True, True, True, False, False):
            manual.observe(rules, ['rule_1'], won, context(won), 0)
        model = Refiner()
        report = {'operations': [], 'errors': []}
        manual.refine(agent(rules, model), rules, rules, report)
        self.assertEqual(model.calls, [])                                # only 2 losses so far
        manual.observe(rules, ['rule_1'], False, context(False), 1)
        manual.refine(agent(rules, model), rules, rules, report)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(len(model.calls[0]['won_games']), 3)
        self.assertEqual(rules[0]['rule'], 'When x and the cabinet is closed, open it first. Do not use it when x is held.')
        self.assertEqual(rules[0]['refined_at'], [3, 3])
        manual.refine(agent(rules, model), rules, rules, report)
        self.assertEqual(len(model.calls), 1)                            # not again until 3 more of each

    def test_near_duplicate_is_merged_not_added(self):
        rules = [rule(1, 'when the drawer is closed open it before putting things in')]
        log = []
        applied = manual.apply(rules, [{'op': 'write_rule', 'type': 'Corrected Error',
                                        'rule': 'when the drawer is closed open it before putting things in'}],
                               'indirect success', False, lambda: 'rule_2', log, 'pick',
                               similarity=LexicalEmbedding().similarity)
        # (identical text is caught as a duplicate before merging; use a near-copy instead)
        log = []
        applied = manual.apply(rules, [{'op': 'write_rule', 'type': 'Corrected Error',
                                        'rule': 'when the drawer is closed open it before putting things in it'}],
                               'indirect success', False, lambda: 'rule_2', log, 'pick',
                               similarity=lambda q, texts: [0.9 for _ in texts])
        self.assertEqual(len(rules), 1)
        self.assertEqual(applied, [{'op': 'upvote_rule', 'id': 'rule_1'}])
        self.assertEqual(rules[0]['importance'], manual.NEW_IMPORTANCE + 1)
        # append-only never merges
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Unresolved Error', 'rule': 'When z, w.'}],
                     'failure', True, lambda: 'rule_3', [], 'pick', similarity=lambda q, texts: [0.99 for _ in texts])
        self.assertEqual(len(rules), 2)

    def test_pruning_drops_the_lowest_utility_above_capacity(self):
        rules = [rule(1, 'a', alpha=8, beta=1, last_used=99), rule(2, 'b', alpha=1, beta=8, last_used=0),
                 rule(3, 'c', alpha=4, beta=4, last_used=98)]
        log = []
        with patch.object(manual, 'CAPACITY', 2):
            manual.prune(rules, 100, log)
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_3'])
        self.assertIn('rule_2', log[0])


class GameAndBatchTests(unittest.TestCase):
    def test_build_records_outcomes_for_shown_rules_and_replay_matches(self):
        rules = [rule(1, 'When putting an apple, open the cabinet first.', task_type='pick')]
        live = copy.deepcopy(rules)
        model = Refiner()
        a = Agent(Settings(), 'E', model, Library(), LexicalEmbedding(), MiniWorld, rules=rules)
        result = a.run(TASK, 1, {'phase': 'practice', 'position': 4})
        self.assertEqual(result['rules_shown'], ['rule_1'])
        ops = result['manual']['operations']
        self.assertEqual(ops[0]['op'], 'outcome')
        self.assertEqual(rules[0]['alpha'], 2)                            # the won game counted
        # Batching: replaying the game's operations on the live manual gives the same manual.
        self.assertEqual(manual.replay(live, ops, []), rules)

    def test_append_only_records_no_outcomes(self):
        rules = [rule(1, 'When putting an apple, open the cabinet first.', task_type='pick')]
        a = Agent(Settings(), 'E-minus', FixtureModel(), Library(), LexicalEmbedding(), MiniWorld, rules=rules)
        result = a.run(TASK, 1, {'phase': 'practice', 'position': 0})
        self.assertFalse(any(op['op'] == 'outcome' for op in result['manual']['operations']))
        self.assertEqual((rules[0]['alpha'], rules[0]['beta']), (1, 1))


if __name__ == '__main__':
    unittest.main()
