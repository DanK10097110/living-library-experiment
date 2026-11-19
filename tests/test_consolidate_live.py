"""Periodic consolidation of underused rules in the live manual (manual.consolidate)."""
import copy
import unittest
from unittest import mock

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

COOL = 'pick_cool_then_place_in_recep'
HEAT = 'pick_heat_then_place_in_recep'
NEW = 'When cooling, open the fridge first, then put the object in it.'


def rule(i, text, task=COOL, kind='Corrected Error', won=0, lost=0, **extra):
    r = manual.new_rule(f'rule_{i}', kind, text, '', task)
    r.update(alpha=1 + won, beta=1 + lost, **extra)
    return r


def library():
    return [
        rule(1, 'When cooling an object, use the fridge.', won=6, lost=2),
        rule(2, 'When cooling, open the fridge before putting the object in it.', won=5, lost=1),
        rule(3, 'When cooling, open the fridge first.', won=1, unused=2),
        rule(4, 'When cooling, open the fridge door first.', won=1, unused=1),
        rule(5, 'Cool it.', kind='Success Process'),
        rule(6, 'When heating, use the microwave.', HEAT, won=4, lost=1),
        rule(7, 'When heating, open the microwave first.', HEAT),
        rule(8, 'When cooling, scan surfaces first.', won=4, lost=1),
        rule(9, 'When cooling, search every surface first.', won=3, lost=2),
        rule(10, 'Never cool in the sink.', kind='Anti-Pattern'),
    ]


class FakeAgent:
    def __init__(self, conflict='no', text=NEW, covers=True):
        self.conflict, self.text, self.covers, self.calls = conflict, text, covers, []
        self.embedder = LexicalEmbedding()

    def _ask(self, role, payload):
        self.calls.append(payload)
        if 'conflict' in payload['response_schema']:
            return {'conflict': self.conflict}
        return {'rule': self.text, 'covers_all': self.covers}


def report():
    return {'operations': [], 'errors': []}


class ConsolidateTests(unittest.TestCase):
    def test_underused_selection_skips_recipes_and_anti_patterns(self):
        under, well, _ = manual.underused(library())
        self.assertTrue({'rule_3', 'rule_4', 'rule_7'} <= set(under))
        self.assertTrue(set(under).isdisjoint(well))
        self.assertIn('rule_1', well)
        for i in ('rule_5', 'rule_10'):
            self.assertNotIn(i, under + well)

    def test_fold_keeps_bookkeeping_and_replay_equals_live(self):
        rules, live = library(), library()
        rep, agent = report(), FakeAgent()
        manual.consolidate(agent, rules, rep)
        ops = rep['operations']
        self.assertTrue(ops and all(o['op'] == 'consolidate' for o in ops))
        op = ops[0]
        by_id = {r['id']: r for r in rules}
        old = {r['id']: r for r in live}
        absorber = by_id[op['id']]
        self.assertEqual(absorber['rule'], NEW)
        self.assertEqual(op['old_rule'], old[op['id']]['rule'])
        self.assertTrue(op['absorbed'] and all(i not in by_id for i in op['absorbed']))
        n = len(op['absorbed'])
        self.assertEqual(absorber['alpha'], sum(old[i]['alpha'] for i in [op['id']] + op['absorbed']) - n)
        self.assertEqual(absorber['beta'], sum(old[i]['beta'] for i in [op['id']] + op['absorbed']) - n)
        self.assertEqual(absorber.get('unused', 0), sum(old[i].get('unused', 0) for i in [op['id']] + op['absorbed']))
        self.assertEqual(by_id['rule_5']['rule'], 'Cool it.')
        self.assertEqual(by_id['rule_10']['rule'], 'Never cool in the sink.')
        self.assertIn('rule_7', by_id)                 # no well-used partner of its own scope
        self.assertEqual(manual.replay(live, ops, []), rules)

    def test_conflict_guard_skips_the_merge(self):
        rules, rep = library(), report()
        before = copy.deepcopy(rules)
        manual.consolidate(FakeAgent(conflict='yes'), rules, rep)
        self.assertEqual((rules, rep['operations']), (before, []))
        self.assertTrue(any('conflicting' in e for e in rep['errors']))

    def test_failed_checks_keep_originals(self):
        for agent in (FakeAgent(text='When cooling a tomato, use the fridge.'), FakeAgent(covers=False)):
            rules, rep = library(), report()
            before = copy.deepcopy(rules)
            manual.consolidate(agent, rules, rep)
            self.assertEqual((rules, rep['operations']), (before, []))

    def test_fewer_than_three_underused_does_nothing(self):
        rules = library()[:2] + library()[5:6]
        agent = FakeAgent()
        manual.consolidate(agent, rules, report())
        self.assertEqual(agent.calls, [])


class Judge(FixtureModel):
    def complete(self, role, payload, seed, context):
        if role == 'builder':
            if 'followed' in payload.get('response_schema', {}):
                return ModelResponse({'followed': []})
            return ModelResponse({'diagnosis': 'imperfect agent', 'operations': []})
        return super().complete(role, payload, seed, context)


class CadenceTests(unittest.TestCase):
    def run_game(self, condition, position):
        task = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}
        agent = Agent(Settings(), condition, Judge(), Library(), LexicalEmbedding(), MiniWorld, rules=[])
        with mock.patch.object(manual, 'consolidate') as m:
            agent.run(task, 1, {'phase': 'practice', 'position': position})
        return m.call_count

    def test_every_25th_game_but_never_for_e_minus(self):
        self.assertEqual([self.run_game('E', p) for p in (0, 23, 24, 25, 49)], [0, 0, 1, 0, 1])
        self.assertEqual(self.run_game('E-minus', 24), 0)


if __name__ == '__main__':
    unittest.main()
