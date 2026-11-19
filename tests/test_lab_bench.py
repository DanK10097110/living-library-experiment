"""Lab benchmark (living_library/lab): labels, metrics, synthetic library building, baseline wrapper."""
import unittest

from living_library import manual
from living_library.lab import metrics, methods, synth
from living_library.library import LexicalEmbedding

SIM = LexicalEmbedding().similarity
COOL = 'pick_cool_then_place_in_recep'
HEAT = 'pick_heat_then_place_in_recep'
QUERY = {'id': 'q1', 'goal': 'cool some tomato and put it in countertop.', 'task_type': COOL, 'plan': '', 'split': 'id'}


def rule(i, text, task_type=COOL, kind='Corrected Error', wins=0):
    r = manual.new_rule(f'rule_{i}', kind, text, '', task_type)
    r['alpha'] = 1 + wins
    return r


def info(group, cls='real', junk=False, objects=()):
    return {'cls': cls, 'group': group, 'junk': junk, 'objects': list(objects)}


class LabelTests(unittest.TestCase):
    def test_kind_scope_junk_and_objects(self):
        self.assertEqual(synth.label(rule(1, 'When cooling, use the fridge.'), info('a'), QUERY), (1, False, False))
        self.assertEqual(synth.label(rule(2, 'Recipe', kind='Success Process'), info('b'), QUERY)[0], 2)
        self.assertEqual(synth.label(rule(3, 'When heating, use the microwave.', HEAT), info('c'), QUERY),
                         (0, False, True))
        # scope matches but the text uses another kind's action word
        self.assertEqual(synth.label(rule(4, 'When cooling, clean it first.'), info('d'), QUERY)[2], True)
        self.assertEqual(synth.label(rule(5, 'Be careful.'), info('e', 'vague', junk=True), QUERY), (0, True, False))
        self.assertEqual(synth.label(rule(6, 'When the task object is a mug, cool it.'),
                                     info('f', 'more_specific', objects=['mug']), QUERY)[0], 0)
        self.assertEqual(synth.label(rule(7, 'When the task object is a tomato, cool it.'),
                                     info('g', 'more_specific', objects=['tomato']), QUERY)[0], 1)
        # an appliance noun alone is not another kind's action
        self.assertEqual(synth.label(rule(8, 'When the target is the microwave, open it.'), info('h'), QUERY)[0], 1)


class MetricTests(unittest.TestCase):
    def test_duplicates_earn_nothing(self):
        rules = [rule(1, 'a'), rule(2, 'b'), rule(3, 'c'), rule(4, 'junk')]
        meta = {'rule_1': info('g1'), 'rule_2': info('g1'), 'rule_3': info('g2'), 'rule_4': info('g4', junk=True)}
        by_id = {r['id']: r for r in rules}
        rel = metrics.relevant_groups(rules, meta, QUERY, synth.label)
        self.assertEqual(rel, {'g1': 1, 'g2': 1})
        s = metrics.score(['rule_1', 'rule_2', 'rule_4'], by_id, meta, QUERY, rel, synth.label)[3]
        self.assertAlmostEqual(s['dup'], 1 / 3)
        self.assertAlmostEqual(s['junk'], 1 / 3)
        self.assertAlmostEqual(s['recall'], 1 / 2)
        self.assertAlmostEqual(s['precision'], 2 / 3)
        best = metrics.score(['rule_1', 'rule_3'], by_id, meta, QUERY, rel, synth.label)[3]
        self.assertAlmostEqual(best['ndcg'], 1.0)
        self.assertAlmostEqual(best['recall'], 1.0)


class BuildTests(unittest.TestCase):
    def pool(self):
        recipe = rule(1, 'When an object must be cooled: take it, cool it with fridge, move it.', kind='Success Process', wins=3)
        other = rule(2, 'When a container is closed, open it before moving objects into it.', wins=2)
        return [recipe, other]

    def test_merge_gate_size_and_groups(self):
        pool = self.pool()
        cands = [{'cls': 'near_duplicates', 'text': pool[1]['rule'], 'parent': pool[1]},          # merged away
                 {'cls': 'paraphrases', 'text': 'Open closed receptacles first, then put things in them.',
                  'parent': pool[1]},
                 {'cls': 'vague', 'text': 'When in doubt, be careful and think about the task.', 'parent': pool[1]}]
        goals = {k: [f'cool some apple and put it in {k}.'] for k in synth.KINDS}
        rules, meta, stats = synth.build(pool, cands, 10, 0, SIM, goals, junk_share=None)
        self.assertEqual(stats['merge_gate_skipped'], {'near_duplicates': 1})
        self.assertEqual(len(rules), 4)
        by_cls = {m['cls']: m for m in meta.values()}
        self.assertEqual(by_cls['paraphrases']['group'], meta['rule_2']['group'])    # shares its parent's group
        self.assertTrue(by_cls['vague']['junk'])
        self.assertEqual(rules[0]['type'], 'Success Process')
        small, _, _ = synth.build(pool, cands, 2, 0, SIM, goals)
        self.assertEqual(len(small), 2)

    def test_baseline_is_the_live_for_agent(self):
        rules = self.pool()
        for i, r in enumerate(rules):
            r['id'] = f'rule_{i + 1}'
        self.assertEqual(methods.baseline(rules, QUERY, 8, SIM),
                         [r['id'] for r in manual.for_agent(rules, COOL, 8, QUERY['goal'], SIM, 'task')])
        self.assertEqual(methods.random_pick(rules, QUERY, 8, SIM)[0], 'rule_1')     # recipe first


if __name__ == '__main__':
    unittest.main()


class JunkShareTests(unittest.TestCase):
    def test_fixed_junk_share_defers_junk(self):
        pool = [rule(1, 'When an object must be cooled: take it, cool it with fridge, move it.', kind='Success Process')]
        parent = rule(2, 'When a container is closed, open it before moving objects into it.')
        pool.append(parent)
        words = ['apple', 'bread', 'lettuce', 'potato', 'egg', 'tomato', 'mug', 'cup']
        good = [{'cls': 'more_specific', 'text': f'{w} {w} {w} {w} {w} first.',
                 'parent': parent} for w in words]
        junk = [{'cls': 'vague', 'text': f'{w} {w} {w} {w} {w} junk.', 'parent': parent}
                for w in ('odd', 'strange', 'unusual', 'weird', 'rare', 'new')]
        goals = {k: ['cool some apple and put it in countertop.'] for k in synth.KINDS}
        rules, meta, _ = synth.build(pool, junk + good, 10, 0, SIM, goals, junk_share=0.2)
        self.assertEqual(len(rules), 10)
        self.assertLessEqual(sum(m['junk'] for m in meta.values()), 2)
        natural, meta2, _ = synth.build(pool, junk + good, 10, 0, SIM, goals, junk_share=None)
        self.assertGreater(sum(m['junk'] for m in meta2.values()), 2)
