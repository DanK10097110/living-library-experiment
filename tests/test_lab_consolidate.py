"""Consolidation of underused rules (living_library/lab/consolidate.py): selection, merging, live checks."""
import unittest

from living_library import manual
from living_library.lab import consolidate as C
from living_library.library import LexicalEmbedding

SIM = LexicalEmbedding().similarity
COOL = 'pick_cool_then_place_in_recep'
HEAT = 'pick_heat_then_place_in_recep'


def rule(i, text, task=COOL, kind='Corrected Error', won=0, lost=0, **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', task)
    r.update(alpha=1 + won, beta=1 + lost, **extra)
    return r


class FakeChat:
    def __init__(self, text, covers=True):
        self.text, self.covers, self.prompts = text, covers, []

    def ask_json(self, system, user, **kw):
        self.prompts.append(user)
        return {'rule': self.text, 'covers_all': self.covers}

    def map(self, fn, items):
        return [fn(i) for i in items]


def library():
    return [
        rule(1, 'When cooling an object, use the fridge.', won=6, lost=2),           # well-used
        rule(2, 'When cooling, open the fridge before putting the object in it.', won=5, lost=1),
        rule(3, 'When cooling, open the fridge first.', won=1),                      # underused, no losses
        rule(4, 'When cooling, open the fridge door first.', won=1),    # underused, no losses
        rule(5, 'Cool it.', kind='Success Process', won=0),
        rule(6, 'When heating, use the microwave.', HEAT, won=4, lost=1),
        rule(7, 'When heating, open the microwave first.', HEAT, won=0),
        rule(8, 'failure pool', kind='Failure Pool'),
        rule(9, 'When cooling, scan surfaces first.', won=4, lost=1),
        rule(10, 'When cooling, search every surface first.', won=3, lost=2),
    ]


class SelectionTests(unittest.TestCase):
    def test_underused_and_well_used(self):
        under, well, info = C.select(library())
        self.assertIn('rule_3', under)
        self.assertIn('rule_7', under)
        self.assertNotIn('rule_5', under + well)        # recipes never
        self.assertNotIn('rule_8', under + well)        # hidden pool never
        self.assertTrue(set(under).isdisjoint(well))
        self.assertIn('rule_1', well)

    def test_unreliable_rule_is_not_underused(self):
        rules = library() + [rule(11, 'When cooling, do a thing.', won=0, lost=5)]
        # shown often and bad: neither underused (too many games) nor decent
        self.assertNotIn('rule_11', C.select(rules)[0])
        few_bad = library() + [rule(12, 'When cooling, wait.', won=0, lost=1)]
        self.assertNotIn('rule_12', C.select(few_bad)[0])      # few games but below its type's base rate

    def test_percentile(self):
        self.assertEqual(C.percentile([0, 10], 0.4), 4.0)
        self.assertEqual(C.percentile([], 0.4), 0.0)


class MergeTests(unittest.TestCase):
    def test_merged_record_sums_beta_minus_prior_and_unions(self):
        a = rule(1, 'x', won=3, lost=1, contexts=[{'task': 'g1', 'won': True}], sources=[{'task': 's1'}])
        b = rule(2, 'y', won=1, lost=0, contexts=[{'task': 'g1', 'won': True}, {'task': 'g2', 'won': False}],
                 sources=[{'task': 's1'}, {'task': 's2'}])
        m = C.merged_record(a, [b], 'When z, do w.')
        self.assertEqual((m['id'], m['rule'], m['alpha'], m['beta']), ('rule_1', 'When z, do w.', 5, 2))
        self.assertEqual([c['task'] for c in m['contexts']], ['g1', 'g2'])
        self.assertEqual(len(m['sources']), 2)
        self.assertEqual(a['alpha'], 4)                  # input not mutated

    def test_problems_are_the_live_checks(self):
        self.assertEqual(C.problems('Corrected Error', 'When cooling, open the fridge first.', COOL), [])
        self.assertTrue(C.problems('Corrected Error', 'Open the fridge first.', COOL))
        self.assertTrue(C.problems('Corrected Error', 'When cooling a tomato, open the fridge.', COOL))
        self.assertTrue(C.problems('Corrected Error', 'When cooling, clean it with the sinkbasin first.', COOL))
        self.assertTrue(C.problems('Corrected Error', 'When cooling, open drawer 3 first.', COOL))
        self.assertTrue(C.problems('Corrected Error', 'When cooling, ' + 'open the fridge ' * 12, COOL))

    def test_variant_a_merges_cluster_and_keeps_rest(self):
        rules = library()
        chat = FakeChat('When cooling, open the fridge first and close it afterwards.')
        out, merges, rejected, info = C.variant_a(rules, chat, SIM)
        by_id = {r['id']: r for r in out}
        self.assertEqual(len(merges), 1)
        self.assertEqual(len(out), len(rules) - 1)
        kept = merges[0]['kept_id']
        self.assertEqual(by_id[kept]['rule'], chat.text)
        self.assertEqual(sorted(merges[0]['sources']), ['rule_3', 'rule_4'])
        self.assertEqual((by_id[kept]['alpha'], by_id[kept]['beta']), (3, 1))   # counts summed minus one prior
        self.assertEqual(by_id['rule_5']['rule'], 'Cool it.')                         # recipe untouched

    def test_variant_a_rejects_failed_checks_and_keeps_originals(self):
        rules = library()
        out, merges, rejected, _ = C.variant_a(rules, FakeChat('When cooling a tomato, use the fridge.'), SIM)
        self.assertEqual((merges, len(out)), ([], len(rules)))
        self.assertEqual(len(rejected), 1)
        out, merges, rejected, _ = C.variant_a(rules, FakeChat('When cooling, open the fridge.', covers=False), SIM)
        self.assertEqual((merges, len(out)), ([], len(rules)))

    def test_variant_b_folds_into_well_used_same_scope_and_type(self):
        rules = library()
        chat = FakeChat('When cooling, open the fridge first, then put the object in it.')
        out, merges, rejected, info = C.variant_b(rules, chat, SIM)
        self.assertTrue(merges)
        for m in merges:
            absorber = {r['id']: r for r in rules}[m['kept_id']]
            self.assertEqual(absorber['task_type'], COOL)
            self.assertNotEqual(absorber['type'], 'Success Process')
            self.assertNotIn(m['kept_id'], info and C.select(rules)[0])        # absorber is not underused
        ids = {r['id'] for r in out}
        self.assertTrue(all(i not in ids for m in merges for i in m['sources'][1:]))
        self.assertIn('rule_7', ids)       # the heat rule has no well-used partner of its own scope+type


if __name__ == '__main__':
    unittest.main()
