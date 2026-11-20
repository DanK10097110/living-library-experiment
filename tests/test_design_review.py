"""The 2026-11-20 design review (results/DECISIONS.md, "Design review: stabilise all rules, fair E vs E-minus,
evidence-only deletion"): one focused test class per decision, with fake models and judges, and a replay ==
live check of batched E practice with the new rules."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld, demo_manifest
from living_library.experiment import Runner, load_json
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

LOOK = 'look_at_obj_in_light'
PICK = 'pick'
TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': PICK}
TIP = 'If a container is closed, open it before looking inside.'


def rule(i, kind, text, task_type=LOOK, **extra):
    return {**manual.new_rule(f'rule_{i}', kind, text, '', task_type), **extra}


def ids(start=10):
    n = [start]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


def step(action, valid=True, after='You do it.'):
    return {'action': action, 'valid': valid, 'after': after, 'before': ''}


def context(task_type=LOOK, task='look at book under the desklamp'):
    return {'task': task, 'task_type': task_type, 'steps': []}


def quiet(*args, **kwargs):
    pass


class Judging(FixtureModel):
    """The fixture policy; the outcome-blind judge says `followed` (default: every rule it is shown); the
    Builder answers `operations` and records what it was shown."""
    def __init__(self, followed=None, operations=()):
        self.followed, self.operations, self.builder_rules, self.judged = followed, list(operations), [], []

    def complete(self, role, payload, seed, context):
        if role == 'builder' and 'followed' in payload.get('response_schema', {}):
            self.judged.append(payload)
            listed = [r['id'] for r in payload['rules']]
            return ModelResponse({'followed': listed if self.followed is None else list(self.followed)})
        if role == 'builder' and 'game' in payload:
            self.builder_rules.append([r['id'] for r in payload['rules']])
            return ModelResponse({'diagnosis': 'imperfect rules', 'operations': copy.deepcopy(self.operations)})
        return super().complete(role, payload, seed, context)


def play(condition, rules, model, position=4, task=TASK):
    agent = Agent(Settings(), condition, model, Library(), LexicalEmbedding(), MiniWorld, rules=rules)
    return agent.run(task, 1, {'phase': 'practice', 'position': position})


class D1FreezeAllVisibleRules(unittest.TestCase):
    def test_a_verified_rule_of_any_type_is_frozen(self):
        for kind in ('Special Phenomenon', 'Corrected Error', 'Success Process'):
            tip = rule(1, kind, TIP, alpha=1 + manual.YOUNG_CREDITS)
            log = []
            manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.'}],
                         'direct success', False, ids(), log)
            self.assertEqual(tip['rule'], TIP, kind)
            self.assertIn(f'rule_1 keeps its text (a verified {kind} changes only by contrastive refinement)', log)

    def test_a_young_rewrite_starts_fresh_counters_and_logs_the_old_text(self):
        tip = rule(1, 'Special Phenomenon', TIP, alpha=2, beta=2, unused=4, confirmations=1, refined_at=[1, 1],
                   contexts=[{'task': 'x', 'won': True}], credits={LOOK: [1, 1]}, importance=3,
                   sources=[{'task': 'look at x', 'task_type': LOOK}], base=[5, 9], base_types={LOOK: [5, 9]})
        self.assertLess(manual.credited(tip), manual.YOUNG_CREDITS)
        applied = manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.'}],
                               'direct success', False, ids(), [])
        self.assertEqual(tip['rule'], 'If a drawer is closed, open it.')
        self.assertEqual({k: tip[k] for k in manual.FRESH}, manual.FRESH)
        self.assertNotIn('credits', tip)
        self.assertEqual((tip['id'], tip['type'], tip['task_type'], tip['sources'], tip['base']),
                         ('rule_1', 'Special Phenomenon', LOOK, [{'task': 'look at x', 'task_type': LOOK}], [5, 9]))
        self.assertEqual(tip['importance'], 4)                                  # kept (+1: an edit is agreement)
        self.assertEqual((applied[0]['old_rule'], applied[0]['fresh']), (TIP, True))

    def test_a_followed_rule_whose_command_was_rejected_may_be_corrected(self):
        tip = rule(1, 'Special Phenomenon', 'When looking at an object under a light, take the lamp first.',
                   alpha=1 + manual.YOUNG_CREDITS)
        trace = [step('take desklamp 1 from desk 1', False, 'Nothing happens.')]
        self.assertEqual(manual.rejected_steps([tip], ['rule_1'], trace), ['rule_1'])
        self.assertEqual(manual.rejected_steps([tip], [], trace), [])          # not followed: frozen
        anti = rule(2, manual.avoid.TYPE, 'Never take the lamp; take the lamp is rejected.')
        self.assertEqual(manual.rejected_steps([anti], ['rule_2'], trace), [])
        new = 'When looking at an object under a light, use the desklamp.'
        manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_1', 'rule': new}], 'indirect success', False,
                     ids(), [], correctable=['rule_1'])
        self.assertEqual((tip['rule'], tip['alpha']), (new, 1))

    def test_the_game_that_changed_a_text_gives_it_no_credit(self):
        rules = [rule(1, 'Special Phenomenon', TIP), rule(2, 'Special Phenomenon', 'If a target is full, use another.')]
        op = manual.observe(rules, ['rule_1', 'rule_2'], True, context(), 0, followed=['rule_1', 'rule_2'],
                            changed=['rule_1'])
        self.assertEqual(op['ids'], ['rule_2'])
        self.assertEqual((rules[0]['alpha'], rules[1]['alpha']), (1, 2))
        self.assertEqual(rules[0]['base'], [1, 1])                          # the base rate still counts

    def test_replay_of_a_fresh_text_change_equals_live(self):
        tip = rule(1, 'Special Phenomenon', TIP, alpha=2, contexts=[{'task': 'x', 'won': True}])
        live = [copy.deepcopy(tip)]
        rules = [tip]
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.'}],
                               'direct success', False, ids(), [])
        self.assertEqual(manual.replay(live, applied, [], copy.deepcopy(live)), rules)


class D1RewriteLimit(unittest.TestCase):
    TEXTS = ('If a drawer is closed, open it.', 'If a shelf is closed, open it.', 'If a safe is closed, open it.')

    def test_a_third_young_rewrite_is_refused_and_logged_and_replay_counts_rewrites(self):
        tip = rule(1, 'Special Phenomenon', TIP)
        rules, live, log, ops = [tip], [copy.deepcopy(tip)], [], []
        for text in self.TEXTS:
            ops += manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': text}], 'direct success',
                                False, ids(), log)
        self.assertEqual((tip['rule'], tip['rewrites']), (self.TEXTS[1], manual.MAX_REWRITES))
        self.assertLess(manual.credited(tip), manual.YOUNG_CREDITS)          # still young: fresh counters
        self.assertIn('rule_1 keeps its text (a verified Special Phenomenon rewritten 2 times changes only by '
                      'contrastive refinement)', log)
        self.assertEqual([op.get('rewrite') for op in ops], [True, True])
        replayed = live
        for op in ops:                                                   # one game per op, separate batches
            replayed = manual.replay(replayed, [op], [], copy.deepcopy(replayed))
        self.assertEqual(replayed, rules)

    def test_the_rejected_step_exception_also_ends(self):
        tip = rule(1, 'Special Phenomenon', TIP, rewrites=manual.MAX_REWRITES)
        manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_1', 'rule': self.TEXTS[0]}], 'indirect success',
                     False, ids(), [], correctable=['rule_1'])
        self.assertEqual(tip['rule'], TIP)

    def test_a_hidden_note_rewrite_is_not_counted(self):
        note = {**rule(1, 'Unresolved Error', 'When the lamp was off, the task failed.'), 'verified': False}
        applied = manual.apply([note], [{'op': 'update_rule', 'id': 'rule_1',
                                         'rule': 'When the lamp is off, nothing is seen.'}], 'failure', False, ids(), [])
        self.assertNotIn('rewrites', note)
        self.assertNotIn('rewrite', applied[0])

    def test_refine_still_rewrites_below_the_base_rate_and_counts(self):
        tip = rule(1, 'Special Phenomenon', TIP, alpha=4, beta=4, rewrites=manual.MAX_REWRITES,
                   base_types={LOOK: [9, 10]}, contexts=[{'task': 'g', 'won': w} for w in (True, False) * 3])
        new = 'If a container is shut, open it before looking inside.'

        class Refiner:
            def _ask(self, role, payload):
                return {'rule': new}
        live, report = [copy.deepcopy(tip)], {'operations': [], 'errors': []}
        manual.refine(Refiner(), [tip], [tip], report)
        self.assertEqual((tip['rule'], tip['rewrites'], tip['alpha']), (new, manual.MAX_REWRITES + 1, 1))
        self.assertEqual(manual.replay(live, report['operations'], [], copy.deepcopy(live)), [tip])

    def test_a_fold_counts_as_a_rewrite_of_the_absorber(self):
        keeper = rule(1, 'Corrected Error', TIP, alpha=5, rewrites=1)
        other = rule(2, 'Corrected Error', 'If a box is shut, open it.', alpha=2)
        rules = [keeper, other]
        manual._consolidate(rules, {'op': 'consolidate', 'id': 'rule_1', 'absorbed': ['rule_2'],
                                    'rule': 'If a container is shut, open it first.'})
        self.assertEqual((len(rules), rules[0]['rewrites'], rules[0]['alpha']), (1, 2, 5))


class D2RefineBelowBase(unittest.TestCase):
    def test_refine_fires_only_below_the_base_rate_and_starts_fresh(self):
        good = rule(1, 'Special Phenomenon', TIP, alpha=4, beta=4, base_types={LOOK: [3, 10]})   # 3/6 vs base 1/3
        bad = rule(2, 'Special Phenomenon', TIP, alpha=4, beta=4, base_types={LOOK: [9, 10]})    # 3/6 vs base 5/6
        self.assertFalse(manual.refinable(good))
        self.assertTrue(manual.refinable(bad))
        bad['contexts'] = [{'task': 'g', 'won': w} for w in (True, False) * 3]
        new = 'If a container is shut, open it before looking inside.'

        class Refiner:
            def _ask(self, role, payload):
                return {'rule': new}
        live, report = [copy.deepcopy(bad)], {'operations': [], 'errors': []}
        manual.refine(Refiner(), [bad], [bad], report)
        op = report['operations'][0]
        self.assertEqual((bad['rule'], bad['alpha'], bad['beta'], bad['contexts'], bad['refined_at']), (new, 1, 1, [], [0, 0]))
        self.assertEqual((op['old_rule'], op['fresh']), (TIP, True))
        self.assertEqual(manual.replay(live, [op], [], copy.deepcopy(live)), [bad])


class D3RecipeCreditAndRetirement(unittest.TestCase):
    def test_a_recipe_not_followed_is_not_credited(self):
        recipe = rule(1, 'Success Process', 'When looking: take it, use the desklamp.')
        op = manual.observe([recipe], ['rule_1'], True, context(), 0, followed=[])
        self.assertEqual((op['ids'], recipe['alpha'], recipe['unused']), ([], 1, 1))

    def test_never_won_retirement_needs_wins_of_its_kind(self):
        lost = rule(1, 'Special Phenomenon', TIP, beta=1 + manual.RETIRE_MIN,
                    credits={LOOK: [0, manual.RETIRE_MIN]}, base_types={LOOK: [0, 8]}, base=[0, 8])
        self.assertFalse(manual.retirable(lost))
        lost['base_types'][LOOK] = [1, 9]
        self.assertTrue(manual.retirable(lost))

    def test_the_only_recipe_of_a_kind_can_be_retired_and_pruned(self):
        recipe = rule(1, 'Success Process', 'When looking: take it, use the desklamp.', beta=1 + 2 * manual.RETIRE_MIN,
                      base=[5, 10], base_types={LOOK: [5, 10]})
        self.assertTrue(manual.retirable(recipe))
        live = [copy.deepcopy(recipe)]
        rules, report = [recipe], {'operations': [], 'errors': []}
        manual.retire(rules, report)
        self.assertEqual(rules, [])
        self.assertEqual(manual.replay(live, report['operations'], [], copy.deepcopy(live)), [])
        rules = copy.deepcopy(live)
        with patch.object(manual, 'CAPACITY', 0):                                # capacity pruning too
            manual.prune(rules, 0, [])
        self.assertEqual(rules, [])


class D4EMinusBookkeeping(unittest.TestCase):
    def test_e_minus_credits_judged_rules_and_promotes_guesses_but_never_edits(self):
        shown = rule(1, 'Special Phenomenon', 'When putting an object away, open the target first.', PICK)
        guess = {**rule(2, 'Special Phenomenon', 'When putting an object away, look at the target first.', PICK),
                 'verified': False}
        rules = [shown, guess]
        model = Judging(operations=[{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If the target is closed, open it.'},
                                    {'op': 'downvote_rule', 'id': 'rule_1'}])
        first = play('E-minus', rules, model, position=0)
        self.assertTrue(first['success'])
        self.assertEqual([r['id'] for r in model.judged[0]['rules']], ['rule_1', 'rule_2'])   # guess judged
        self.assertEqual(first['manual']['followed'], ['rule_1'])
        self.assertEqual(first['manual']['guesses_followed'], ['rule_2'])
        self.assertEqual((shown['alpha'], shown['rule'], shown['importance']),
                         (2, 'When putting an object away, open the target first.', manual.NEW_IMPORTANCE))
        self.assertEqual(guess['confirmations'], 1)
        live = copy.deepcopy(rules)
        second = play('E-minus', rules, model, position=1)
        self.assertTrue(guess['verified'])                                       # promoted: now visible
        self.assertEqual(manual.replay(live, second['manual']['operations'], [], copy.deepcopy(live)), rules)
        self.assertTrue(any('append-only manual' in e for e in second['manual']['errors']))
        kinds = {op['op'] for op in second['manual']['operations']}
        self.assertFalse(kinds & {'retire', 'refine', 'prune', 'consolidate', 'update_rule', 'merge_rule'})

    def test_e_minus_never_retires(self):
        never = rule(1, 'Special Phenomenon', 'When putting an object away, open the target first.', PICK,
                     beta=1 + manual.RETIRE_MIN, credits={PICK: [0, manual.RETIRE_MIN]},
                     base=[3, 6], base_types={PICK: [3, 6]})
        self.assertTrue(manual.retirable(never))
        rules = [never]
        play('E-minus', rules, Judging(followed=[]), position=0)
        self.assertIn('rule_1', [r['id'] for r in rules])


class D5RareSlotAndLift(unittest.TestCase):
    def pool(self, n=10):
        rules = [rule(i, 'Special Phenomenon', f'When looking at the object, check place {chr(96 + i)} first.',
                      alpha=5, beta=2, unused=2, sources=[{'task': 'look at book under the desklamp'}])
                 for i in range(1, n + 1)]
        rare = rule(n + 1, 'Special Phenomenon', 'When nothing else helps, wait.', sources=[{'task': 'unrelated'}])
        return rules, rare

    def test_one_slot_is_kept_for_the_best_rarely_shown_rule(self):
        rules, rare = self.pool()
        similarity = LexicalEmbedding().similarity
        shown = manual.for_agent(rules + [rare], LOOK, manual.SHOWN, 'look at book under the desklamp', similarity)
        self.assertEqual(len(shown), manual.SHOWN)
        self.assertEqual(shown[-1]['id'], rare['id'])
        rarer = rule(20, 'Special Phenomenon', 'When looking at the object, check the desk.', unused=1)
        shown = manual.for_agent(rules + [rare, rarer], LOOK, manual.SHOWN, 'look at book under the desklamp',
                                 similarity)
        self.assertEqual(shown[-1]['id'], 'rule_20')                         # the best-matching rare rule
        shown = manual.for_agent(rules[:3] + [rare], LOOK, manual.SHOWN, 'look at book', similarity)
        self.assertEqual(len(shown), 4)                                      # fewer candidates than slots
        recipe = rule(30, 'Success Process', 'When looking: take it, use the desklamp.')
        shown = manual.for_agent(rules + [rare, recipe], LOOK, manual.SHOWN, 'look at book under the desklamp',
                                 similarity)
        self.assertEqual((shown[0]['id'], shown[-1]['id']), ('rule_30', rare['id']))   # the recipe stays first

    def test_ranking_uses_lift_over_the_base_rate(self):
        hard = rule(1, 'Special Phenomenon', TIP, alpha=3, beta=3, credits={LOOK: [2, 2]}, base_types={LOOK: [2, 18]})
        easy = rule(2, 'Special Phenomenon', TIP, alpha=7, beta=3, credits={LOOK: [6, 2]}, base_types={LOOK: [18, 20]})
        self.assertGreater(manual.lift(hard), 0)                    # 2/4 where the kind wins ~1/7
        self.assertLess(manual.lift(easy), 0)                       # 6/8 where the kind wins ~6/7
        self.assertGreater(manual.reliability(easy), manual.reliability(hard))   # raw wins would rank easy first
        self.assertGreater(manual.expected_utility(hard, 0.8, LOOK), manual.expected_utility(easy, 0.8, LOOK))
        self.assertEqual(manual.lift(rule(3, 'Special Phenomenon', TIP)), 0.0)


class D6GuessPromotion(unittest.TestCase):
    def guess(self, base):
        return {**rule(1, 'Special Phenomenon', TIP), 'verified': False, 'base_types': {LOOK: base}}

    def test_followed_losses_count_and_the_rate_must_reach_the_base_rate(self):
        guess = self.guess([16, 18])                                # the kind is won ~85%
        for won in (True, False, True, False):
            manual.observe([guess], [], won, context(), 0, followed=[], guesses=['rule_1'])
        self.assertEqual((guess['confirmations'], guess['guess_credits']), (2, {LOOK: [2, 2]}))
        self.assertFalse(guess['verified'])                         # 2 of 4 < expected 3.4
        easy = self.guess([2, 18])                                  # the kind is won ~20%
        for won in (True, False, True):
            manual.observe([easy], [], won, context(), 0, followed=[], guesses=['rule_1'])
        self.assertTrue(easy['verified'])

    def test_a_text_change_resets_the_guess(self):
        guess = self.guess([0, 0])
        manual.observe([guess], [], True, context(), 0, followed=[], guesses=['rule_1'])
        self.assertEqual(guess['confirmations'], 1)
        manual.apply([guess], [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a box is closed, open it first.'}],
                     'direct success', False, ids(), [])
        self.assertEqual(guess['confirmations'], 0)
        self.assertNotIn('guess_credits', guess)
        self.assertFalse(guess['verified'])


class D7BuilderViewAndVotes(unittest.TestCase):
    def library(self, n=30):
        # rules 1-9 match the goal "put some apple in cabinet" best (a new rule is ranked by its text)
        return [rule(i, 'Special Phenomenon', f'When you put some apple in cabinet, check spot {i}.' if i < 10 else
                     f'When cleaning, try place {chr(96 + i % 26)}{i}.', PICK) for i in range(1, n + 1)]

    def test_e_and_e_minus_builders_see_the_same_relevant_and_newest_rules(self):
        seen = {}
        for condition in ('E', 'E-minus'):
            model = Judging(followed=[])
            play(condition, self.library(), model, position=0)
            seen[condition] = model.builder_rules[0]
        self.assertEqual(seen['E'], seen['E-minus'])
        self.assertEqual(len(seen['E']), manual.BUILDER_SEES)
        self.assertTrue({'rule_29', 'rule_30'} <= set(seen['E']))           # the newest two

    def test_for_builder_ranks_by_relevance_and_adds_the_newest(self):
        rules = self.library(30) + [{**rule(31, 'Unresolved Error', 'When looking, nothing happened.', PICK),
                                     'verified': False}]
        view = [r['id'] for r in manual.for_builder(rules, PICK, manual.BUILDER_SEES, 'put some apple in cabinet',
                                                    LexicalEmbedding().similarity)]
        self.assertEqual(len(view), manual.BUILDER_SEES)
        self.assertTrue({'rule_30', 'rule_31'} <= set(view))                # the newest two (a note included)
        self.assertTrue({f'rule_{i}' for i in range(1, 10)} <= set(view))   # keyed by this game's task
        small = manual.for_builder(rules[:5], PICK, manual.BUILDER_SEES, 'x', LexicalEmbedding().similarity)
        self.assertEqual(len(small), 5)

    def test_votes_never_delete(self):
        rules = [rule(1, 'Special Phenomenon', TIP)]
        log = []
        manual.apply(rules, [{'op': 'downvote_rule', 'id': 'rule_1'}] * 5, 'direct success', False, ids(), log)
        self.assertEqual((len(rules), rules[0]['importance']), (1, 0))
        self.assertFalse(any('removed' in line for line in log))


class D8CorrectedErrorShape(unittest.TestCase):
    def test_a_corrected_error_may_not_list_steps(self):
        recipe_like = 'When heating: take the object, go to the microwave, heat it, then put it in the target.'
        self.assertIn('lists steps (only a Success Process may)', manual.rule_problems('Corrected Error', recipe_like))
        self.assertEqual(manual.rule_problems('Corrected Error', 'When the target is closed, open it instead of '
                                              'putting the object on top.'), [])
        self.assertEqual(manual.rule_problems('Success Process', recipe_like), [])


class D9BatchDedupe(unittest.TestCase):
    def test_new_near_duplicates_of_a_batch_merge_into_the_older_rule(self):
        old = rule(1, 'Special Phenomenon', TIP, alpha=3, sources=[{'task': 'a'}])
        base = [old]
        new1 = {**rule(2, 'Special Phenomenon', TIP.replace('looking', 'peeking')), 'sources': [{'task': 'b'}]}
        new2 = rule(3, 'Special Phenomenon', 'If a target is full, use another one.')
        guess = {**rule(4, 'Special Phenomenon', TIP.replace('inside', 'in')), 'verified': False}
        rules = base + [new1, new2, guess]
        live = copy.deepcopy(rules)
        similarity = LexicalEmbedding().similarity
        ops = manual.batch_dedupe(rules, ['rule_1'], similarity)
        self.assertEqual([(o['id'], o['absorbed']) for o in ops], [('rule_1', 'rule_2'), ('rule_1', 'rule_4')])
        self.assertEqual([r['id'] for r in rules], ['rule_1', 'rule_3'])
        self.assertEqual((rules[0]['alpha'], rules[0]['rule'], rules[0]['sources']),
                         (3, TIP, [{'task': 'a'}, {'task': 'b'}]))
        self.assertEqual(manual.replay(live, ops, []), rules)

    def test_a_verified_rule_is_never_merged_into_a_hidden_guess(self):
        guess = {**rule(1, 'Special Phenomenon', TIP), 'verified': False}
        new = rule(2, 'Special Phenomenon', TIP.replace('looking', 'peeking'))
        rules = [guess, new]
        self.assertEqual(manual.batch_dedupe(rules, ['rule_1'], LexicalEmbedding().similarity), [])


class D10Folds(unittest.TestCase):
    def test_absorbed_rules_need_a_won_credited_game(self):
        cool = 'pick_cool_then_place_in_recep'
        rules = [rule(1, 'Corrected Error', 'When cooling an object, use the fridge.', cool, alpha=7, beta=3),
                 rule(2, 'Corrected Error', 'When cooling, open the fridge before putting the object in it.', cool,
                      alpha=6, beta=2),
                 rule(3, 'Corrected Error', 'When cooling, open the fridge before putting an object in it.', cool),
                 rule(4, 'Corrected Error', 'When cooling, open the fridge before putting the object in.', cool,
                      alpha=2)]                                         # rule_3 never credited, rule_4 won once
        plans = manual.fold_plans(rules, LexicalEmbedding().similarity)
        absorbed = {r['id'] for _, extras in plans for r in extras}
        self.assertNotIn('rule_3', absorbed)
        self.assertIn('rule_4', absorbed)


class D11ExpectedWins(unittest.TestCase):
    def test_a_general_rule_is_compared_with_the_kinds_it_was_followed_in(self):
        general = rule(1, 'Special Phenomenon', TIP, 'all', alpha=3, beta=3,
                       credits={'easy': [1, 1], 'hard': [1, 1]},
                       base_types={'easy': [8, 8], 'hard': [0, 8]})
        self.assertAlmostEqual(manual.expected_wins(general), 2 * 0.9 + 2 * 0.1)
        self.assertAlmostEqual(manual.expected_rate(general), 0.5)
        only_easy = rule(2, 'Special Phenomenon', TIP, 'all', alpha=3, beta=3, credits={'easy': [2, 2]},
                         base_types={'easy': [8, 8], 'hard': [0, 8]})
        self.assertAlmostEqual(manual.expected_rate(only_easy), 0.9)
        self.assertGreater(manual.lift(general), manual.lift(only_easy))

    def test_observe_counts_base_and_credit_per_kind(self):
        general = rule(1, 'Special Phenomenon', TIP, 'all')
        manual.observe([general], ['rule_1'], True, context('easy'), 0, followed=['rule_1'])
        manual.observe([general], [], False, context('hard'), 1)
        self.assertEqual(general['base_types'], {'easy': [1, 1], 'hard': [0, 1]})
        self.assertEqual(general['credits'], {'easy': [1, 0]})
        self.assertEqual(general['base'], [1, 2])


class ReplayKeepsTypeAndVerifiedConsistent(unittest.TestCase):
    def test_a_dropped_type_change_does_not_leave_a_hidden_note_verified(self):
        note = {**rule(1, 'Unresolved Error', 'When the lamp was off, the task failed.'), 'verified': False}
        base = [note]
        first = [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'When the lamp is off, nothing is seen.'}]
        second = [{'op': 'update_rule', 'id': 'rule_1', 'type': 'Corrected Error', 'verified': True, 'fresh': True,
                   'rule': 'When the lamp is off, use it instead of taking it.'}]
        log = []
        live = manual.replay(base, first, log, base)
        live = manual.replay(live, second, log, base)
        self.assertEqual((live[0]['type'], live[0]['verified']), ('Unresolved Error', False))
        self.assertFalse(manual.shown_to_agent(live[0]))


class Rephrasing(Judging):
    """A Builder that writes a near-copy of one tip in every won game (lexically ~0.9 similar), so games of one
    batch write near-duplicates that only the end-of-batch merge can catch."""
    WORDS = ('now', 'first', 'always', 'carefully', 'quickly', 'again', 'there', 'then')

    def complete(self, role, payload, seed, context):
        if role == 'builder' and 'game' in payload:
            word = self.WORDS[context.get('position', 0) % len(self.WORDS)] if isinstance(context, dict) else 'now'
            self.operations = [{'op': 'write_rule', 'type': 'Special Phenomenon', 'scope': 'all',
                                'rule': f'When a container is closed, open it before putting the object inside {word}.'}]
        return super().complete(role, payload, seed, context)


class BatchedReplayEqualsLive(unittest.TestCase):
    def test_batched_e_practice_replays_exactly_with_the_new_rules(self):
        cfg = Settings(practice_episodes=6, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                       practice_batch=3, seeds=[11])
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp, model=Rephrasing(), embedder=LexicalEmbedding(), probe=False)
            runner.study(('E',), demo_count=6, log=quiet)
            root = Path(tmp) / 'checkpoints' / f'practice-E-{cfg.practice_seed}'
            saved = [load_json(p) for p in sorted(root.glob('*.json'))]
        self.assertEqual(len(saved), 6)
        memories, k, kinds = [], cfg.practice_batch, []
        for position, checkpoint in enumerate(saved):
            live = memories[position - 1] if position else []
            start = position - position % k
            base = memories[start - 1] if start else []
            ops = checkpoint['record']['manual']['operations']
            kinds += [op['op'] for op in ops]
            got = json.loads(json.dumps(manual.replay(live, ops, [], base)))
            self.assertEqual(got, checkpoint['memory']['rules'], f'game {position}')
            memories.append(checkpoint['memory']['rules'])
        self.assertIn('dedupe', kinds)                       # the end-of-batch merge ran and is replayable
        self.assertIn('outcome', kinds)
        texts = [r['rule'] for r in memories[-1] if r['type'] == 'Special Phenomenon']
        self.assertEqual(len(texts), 1, texts)               # near-copies of one batch merged into one rule


if __name__ == '__main__':
    unittest.main()
