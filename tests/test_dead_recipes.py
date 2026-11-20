"""2026-11-20 (results/DECISIONS.md, "Dead recipes can be rewritten from a winning game"): a verified recipe
followed in at least DEAD_MIN games without a win may be rewritten by a won game or a retry win of its kind of
task (within MAX_REWRITES), and a dead recipe at that cap is retired even as its kind's only recipe. E only."""
import copy
import unittest

from living_library import manual

HEAT = 'pick_heat_then_place_in_recep'
OLD = ('When an object must be heated and placed: search fridge first, take the object, go to microwave, open it, '
       'move the object to microwave, close microwave, heat the object with microwave.')
NEW = ('When an object must be heated and placed: find and take the object, go to the microwave, heat the object '
       'with the microwave, go to the target, put the object in or on it.')


def ids(start=10):
    n = [start]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


def recipe(won=0, lost=manual.DEAD_MIN, task_type=HEAT, **extra):
    return {**manual.new_rule('rule_1', 'Success Process', OLD, '', task_type), 'alpha': 1 + won, 'beta': 1 + lost,
            'credits': {task_type: [won, won + lost]}, 'base': [0, 8], 'base_types': {task_type: [0, 8]}, **extra}


def update(rule, case, task_type=HEAT, rules=None):
    log = []
    applied = manual.apply(rules or [rule], [{'op': 'update_rule', 'id': 'rule_1', 'rule': NEW}], case, False, ids(),
                           log, task_type)
    return applied, log


class DeadRecipeRewrite(unittest.TestCase):
    def test_dead_recipe_is_rewritten_by_a_retry_win_and_replay_reproduces_it(self):
        dead = recipe()
        self.assertTrue(manual.dead_recipe(dead))
        live = [copy.deepcopy(dead)]
        applied, log = update(dead, 'corrected failure')
        self.assertEqual(dead['rule'], NEW)
        self.assertEqual((dead['alpha'], dead['beta'], dead['rewrites']), (1, 1, 1))     # fresh counters, counted
        self.assertNotIn('credits', dead)
        self.assertEqual((applied[0]['rewrite'], applied[0]['fresh'], applied[0]['dead']), (True, True, 4))
        self.assertTrue(any('dead recipe rewritten from a won game' in line for line in log), log)
        self.assertEqual(manual.replay(live, applied, [], copy.deepcopy(live)), [dead])

    def test_dead_recipe_is_rewritten_by_a_first_attempt_win(self):
        for case in ('direct success', 'indirect success'):
            dead = recipe()
            update(dead, case)
            self.assertEqual(dead['rule'], NEW, case)

    def test_not_rewritten_when_it_has_wins_or_too_few_games(self):
        for rule in (recipe(won=1, lost=5), recipe(lost=manual.DEAD_MIN - 1)):
            self.assertFalse(manual.dead_recipe(rule))
            for case in ('corrected failure', 'direct success'):
                old = copy.deepcopy(rule)
                applied, log = update(old, case)
                self.assertEqual(old['rule'], OLD, case)
                self.assertTrue(any('keeps its text' in line for line in log), log)

    def test_not_rewritten_by_a_lost_game_or_a_game_of_another_kind(self):
        dead = recipe()
        update(dead, 'failure')
        self.assertEqual(dead['rule'], OLD)
        update(dead, 'corrected failure', task_type='pick_cool_then_place_in_recep')
        self.assertEqual(dead['rule'], OLD)
        update(dead, 'corrected failure', task_type=None)
        self.assertEqual(dead['rule'], OLD)

    def test_only_recipes_can_be_dead(self):
        tip = {**recipe(), 'type': 'Special Phenomenon', 'rule': 'If the microwave is closed, open it first.'}
        self.assertFalse(manual.dead_recipe(tip))

    def test_the_rewrite_cap_is_respected(self):
        capped = recipe(rewrites=manual.MAX_REWRITES)
        applied, log = update(capped, 'corrected failure')
        self.assertEqual((capped['rule'], capped['rewrites']), (OLD, manual.MAX_REWRITES))
        self.assertIn('rule_1 keeps its text (a verified Success Process rewritten 2 times changes only by '
                      'contrastive refinement)', log)
        once = recipe(rewrites=manual.MAX_REWRITES - 1)                    # one dead rewrite left
        update(once, 'corrected failure')
        self.assertEqual((once['rule'], once['rewrites']), (NEW, manual.MAX_REWRITES))


class DeadRecipeRetirement(unittest.TestCase):
    def test_dead_and_capped_sole_recipe_is_retired_and_replayed(self):
        dead = recipe(rewrites=manual.MAX_REWRITES)
        self.assertTrue(manual.shown_to_agent(dead))                        # its kind's only recipe
        self.assertFalse(manual.retirable(dead))          # its kind never won: the normal test would keep it
        rules, report = [dead], {'operations': [], 'errors': []}
        live = copy.deepcopy(rules)
        manual.retire(rules, report)
        self.assertEqual(rules, [])
        self.assertEqual(report['operations'][0]['op'], 'retire')
        self.assertIn('dead recipe retired', report['errors'][0])
        self.assertEqual(manual.replay(live, report['operations'], [], copy.deepcopy(live)), [])
        # A new recipe of that kind can now be written from the next won game.
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Success Process', 'rule': NEW}], 'direct success',
                     False, ids(), log, HEAT)
        self.assertEqual([r['rule'] for r in rules], [NEW])

    def test_a_dead_sole_recipe_below_the_cap_is_kept(self):
        for rule in (recipe(rewrites=manual.MAX_REWRITES - 1), recipe(won=1, lost=6, rewrites=manual.MAX_REWRITES)):
            rules, report = [rule], {'operations': [], 'errors': []}
            manual.retire(rules, report)
            self.assertEqual(rules, [rule])


class EMinusUnchanged(unittest.TestCase):
    def test_e_minus_never_rewrites_a_dead_recipe(self):
        dead = recipe()
        log = []
        applied = manual.apply([dead], [{'op': 'update_rule', 'id': 'rule_1', 'rule': NEW}], 'corrected failure',
                               True, ids(), log, HEAT)
        self.assertEqual((dead['rule'], applied), (OLD, []))
        self.assertTrue(any('append-only manual' in line for line in log))


if __name__ == '__main__':
    unittest.main()
