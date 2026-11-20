"""Guesses from lost games stay hidden until confirmed, never-won rules retire, merging never widens
scope, and task-keyed retrieval (ExpeL/Memp-style evidence from the tasks a rule came from / won)."""
import copy
import unittest

from living_library import manual

PHENOMENON = 'When heating a container, turn on the stoveburner first.'


def write(rules, case, kind='Special Phenomenon', text=PHENOMENON, task_type='heat', goal='heat some egg'):
    log = []
    applied = manual.apply(rules, [{'op': 'write_rule', 'type': kind, 'rule': text}], case, False,
                           lambda: f'rule_{len(rules) + 1}', log, task_type, goal=goal)
    return applied, log


def rule(i, text, task_type='heat', kind='Special Phenomenon', wins=0, won_goals=(), source=None, **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', task_type,
                        sources=[{'task': source, 'task_type': task_type}] if source else [])
    r['alpha'] = 1 + wins
    r['contexts'] = [{'task': g, 'task_type': task_type, 'won': True} for g in won_goals]
    r.update(extra)
    return r


def table(scores, default=0.1):
    """A deterministic similarity function: text -> score."""
    return lambda query, texts: [scores.get(t, default) for t in texts]


class HiddenGuessTests(unittest.TestCase):
    def test_a_rule_written_from_a_lost_game_is_hidden_until_a_won_game_confirms_it(self):
        rules = []
        applied, log = write(rules, 'failure')
        self.assertFalse(rules[0]['verified'])
        self.assertIn('hidden Builder note', log[0])
        self.assertEqual(manual.for_agent(rules, 'heat', manual.SHOWN), [])
        self.assertEqual(manual.relevant(rules, 'heat', manual.BUILDER_SEES), rules)   # the Builder sees it
        self.assertFalse(manual.replay([], applied, [])[0]['verified'])
        # (2026-11-20) no Builder upvote confirms it, lost or won
        manual.apply(rules, [{'op': 'upvote_rule', 'id': 'rule_1'}], 'failure', False, None, [], 'heat')
        manual.apply(rules, [{'op': 'upvote_rule', 'id': 'rule_1'}], 'direct success', False, None, [], 'heat')
        self.assertFalse(rules[0]['verified'])
        # two won games whose actions the outcome-blind judge says followed it do; replay agrees
        live, ops = copy.deepcopy(rules), []
        for won in (True, False, True):
            ops.append(manual.observe(rules, [], won, {'task': 'heat some egg', 'task_type': 'heat'}, 0,
                                      followed=None, guesses=['rule_1']))
            self.assertEqual(rules[0]['verified'], ops[-1]['won'] and len(ops) == 3)
        self.assertNotIn('confirms', ops[1])                         # a lost game is no confirmation
        self.assertEqual([r['id'] for r in manual.for_agent(rules, 'heat', manual.SHOWN)], ['rule_1'])
        self.assertTrue(manual.replay(live, ops, [])[0]['verified'])
        self.assertEqual(rules[0]['alpha'], 1)                       # not shown: no Beta credit

    def test_won_games_and_retry_successes_write_visible_rules(self):
        for case in ('direct success', 'indirect success', 'corrected failure'):
            rules = []
            applied, _ = write(rules, case)
            self.assertTrue(rules[0]['verified'], case)
            self.assertEqual(len(manual.for_agent(rules, 'heat', manual.SHOWN)), 1, case)
            self.assertEqual(applied[0]['sources'], [{'task': 'heat some egg', 'task_type': 'heat'}])

    def test_a_lost_game_cannot_rewrite_a_rule_the_agent_sees(self):
        rules = [rule(1, 'When x, do y.')]
        log = []
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'When x, do z.',
                                        'example': 'z', 'validation': 'lost once'}],
                               'failure', False, None, log, 'heat')
        self.assertEqual((rules[0]['rule'], rules[0]['example'], rules[0]['validation']),
                         ('When x, do y.', '', 'lost once'))
        self.assertTrue(rules[0]['verified'])
        self.assertIn('keeps its text', log[0])
        self.assertNotIn('rule', applied[0])
        # a pure rewrite is dropped entirely (no vote)
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'When x, do z.'}],
                               'failure', False, None, [], 'heat')
        self.assertEqual((applied, rules[0]['importance']), ([], manual.NEW_IMPORTANCE + 1))
        # a won game may rewrite it
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'When x, do z.'}],
                     'direct success', False, None, [], 'heat')
        self.assertEqual(rules[0]['rule'], 'When x, do z.')

    def test_a_hidden_guess_may_be_rewritten_but_a_won_update_does_not_confirm_it(self):
        rules = []
        write(rules, 'failure')
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'When heating, use the microwave.'}],
                     'failure', False, None, [], 'heat')
        self.assertEqual((rules[0]['rule'], rules[0]['verified']), ('When heating, use the microwave.', False))
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'validation': 'won with it'}],
                               'indirect success', False, None, [], 'heat')
        self.assertFalse(rules[0]['verified'])                       # (2026-11-20) only followed wins confirm
        self.assertNotIn('verified', applied[0])

    def test_a_won_game_never_merges_into_a_hidden_guess(self):
        # (2026-11-20) the won game's rule is written visibly; the guess stays hidden and is not confirmed
        rules = []
        write(rules, 'failure')
        applied = manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                                        'rule': 'When heating a container, turn on the stoveburner first!'}],
                               'direct success', False, lambda: 'rule_9', [], 'heat',
                               similarity=lambda q, texts: [0.95 for _ in texts], goal='heat some mug')
        self.assertEqual([(r['id'], r['verified']) for r in rules], [('rule_1', False), ('rule_9', True)])
        self.assertEqual(applied[0]['op'], 'write_rule')


class RetirementTests(unittest.TestCase):
    def test_a_rule_never_won_in_four_games_is_retired_even_at_a_zero_base_rate(self):
        never = rule(1, 'a', wins=0, beta=1 + manual.RETIRE_MIN, base=[0, 4])
        self.assertTrue(manual.retirable(never))
        self.assertFalse(manual.retirable(rule(2, 'b', wins=0, beta=manual.RETIRE_MIN, base=[0, 4])))  # 3 games
        self.assertFalse(manual.retirable(rule(3, 'c', wins=1, beta=1 + manual.RETIRE_MIN, base=[0, 4])))
        report = {'operations': [], 'errors': []}
        rules = [never]
        manual.retire(rules, report)
        self.assertEqual(rules, [])
        self.assertIn('retired rule_1 (won 0 of 4 games shown, never won; base 0 of 4)', report['errors'])


class MergeScopeTests(unittest.TestCase):
    def test_a_clean_rule_is_never_widened_by_another_kinds_near_copy(self):
        clean = rule(9, 'When an object must be cleaned, rinse it in the sinkbasin.', task_type='clean')
        rules, log = [clean], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                              'rule': 'When an object must be cleaned, rinse it in a sinkbasin.'}],
                     'direct success', False, lambda: 'rule_10', log, 'heat',
                     similarity=lambda q, texts: [0.99 for _ in texts])
        self.assertEqual([(r['id'], r['task_type']) for r in rules], [('rule_9', 'clean'), ('rule_10', 'heat')])
        self.assertFalse(any('merged' in line for line in log))


class RetrievalTests(unittest.TestCase):
    GOAL = 'heat some apple and put it in fridge.'

    def test_evidence_from_similar_won_tasks_outranks_text_similarity(self):
        # Same text relevance; rule_2 was won on a task like this one, rule_1 on an unlike one.
        unlike = rule(1, 'When a, b.', wins=3, won_goals=['heat some egg and put it in countertop.'])
        like = rule(2, 'When c, d.', wins=3, won_goals=['heat some apple and put it in garbagecan.'])
        sims = table({'When a, b.': 0.5, 'When c, d.': 0.5, 'heat some egg and put it in countertop.': 0.2,
                      'heat some apple and put it in garbagecan.': 0.9})
        shown = manual.for_agent([unlike, like], 'heat', 2, self.GOAL, sims)
        self.assertEqual([r['id'] for r in shown], ['rule_2', 'rule_1'])
        rel, evidence = manual.relevance(like, {'When c, d.': 0.5, 'heat some apple and put it in garbagecan.': 0.9})
        self.assertAlmostEqual(evidence, 0.9)
        self.assertAlmostEqual(rel, 0.6 * 0.9 + 0.4 * 0.5)          # w = 3 / (3 + 2)

    def test_without_wins_relevance_is_the_text_similarity(self):
        new = rule(1, 'When a, b.', source='heat some apple and put it in garbagecan.')
        rel, evidence = manual.relevance(new, {'When a, b.': 0.3, 'heat some apple and put it in garbagecan.': 0.9})
        self.assertEqual((rel, evidence), (0.3, 0.9))
        self.assertEqual(manual.evidence_tasks(new), ['heat some apple and put it in garbagecan.'])

    def test_other_kinds_rules_join_only_for_an_unseen_kind_with_strong_evidence(self):
        recipe = rule(1, 'When heating: take it, heat it with the microwave, put it.', kind='Success Process')
        general = rule(2, 'If a container is closed, open it first.', task_type='all')
        clean_close = rule(3, 'When an object must be cleaned, use the sinkbasin.', task_type='clean',
                           source='clean some apple and put it in fridge.')
        clean_far = rule(4, 'When cleaning, rinse first.', task_type='clean', source='clean some mug.')
        hidden = rule(5, 'When cooling, use the fridge.', task_type='cool', verified=False,
                      source='cool some apple and put it in fridge.')
        rules = [recipe, general, clean_close, clean_far, hidden]
        sims = table({'clean some apple and put it in fridge.': 0.97, 'clean some mug.': 0.5,
                      'cool some apple and put it in fridge.': 0.97})
        # a known kind (heat): its recipe first, then general rules; never other kinds' rules
        self.assertEqual([r['id'] for r in manual.for_agent(rules, 'heat', 8, self.GOAL, sims)], ['rule_1', 'rule_2'])
        # an unseen kind: general rules plus other kinds' visible rules with strong task evidence
        shown = [r['id'] for r in manual.for_agent(rules, 'slice', 8, 'slice some apple and put it in fridge.', sims)]
        self.assertEqual(sorted(shown), ['rule_2', 'rule_3'])
        # deterministic
        self.assertEqual(shown, [r['id'] for r in manual.for_agent(rules, 'slice', 8,
                                                                  'slice some apple and put it in fridge.', sims)])

    def test_success_process_is_keyed_to_its_kind_and_first(self):
        recipe = rule(1, 'When heating: take it, heat it with the microwave, put it.', kind='Success Process')
        other = rule(2, 'When cleaning: take it, clean it with the sinkbasin, put it.', kind='Success Process',
                     task_type='clean', source=self.GOAL)
        strong = rule(3, 'When a, b.', wins=9, won_goals=[self.GOAL])
        shown = manual.for_agent([strong, other, recipe], 'heat', 8, self.GOAL, table({self.GOAL: 1.0}))
        self.assertEqual([r['id'] for r in shown], ['rule_1', 'rule_3'])
        self.assertEqual([r['id'] for r in manual.for_agent([other, strong], 'slice', 8, self.GOAL,
                                                             table({self.GOAL: 1.0}))], ['rule_3'])


if __name__ == '__main__':
    unittest.main()
