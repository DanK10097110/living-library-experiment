"""Anti-Pattern rules (living_library/avoid.py): mining from pooled never-won attempts, post-checks, the
write/re-check/retire life cycle, batching replay, and the fixture scenarios with known answers."""
import copy
import json
import unittest
from pathlib import Path

from living_library import avoid, manual

FIXTURES = Path(__file__).parent / 'fixtures' / 'avoid_scenarios.json'
HEAT = 'pick_heat_then_place_in_recep'


def attempt(*steps):
    return [[s[1:], 0] if s.startswith('!') else [s, 1] for s in steps]


def loop(n=4):
    return ['open microwave 1', 'close microwave 1'] * n


def lost(tid, extra, attempts=4):
    return {'task_id': tid, 'task': f'put a hot thing in {tid}.',
            'attempts': [attempt('go to countertop 1', *extra) for _ in range(attempts)]}


def asker(text, calls=None):
    def ask(role, payload):
        if calls is not None:
            calls.append(payload)
        return {'rule': text}
    return ask


def counter():
    n = [0]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


class CommandFormTests(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(avoid.skeleton('place mug 1 on stoveburner 2'), 'place <X> on <X>')
        self.assertEqual(avoid.family('move mug 1 to stoveburner 2'), 'move <object> to stoveburner')
        self.assertEqual(avoid.family('go to microwave 1'), 'go to microwave')
        self.assertFalse(avoid.usable('The current subgoal is to open the dresser if it is closed, so first look'))

    def test_loops_need_the_same_command_not_the_same_kind_of_place(self):
        search = [[f'go to drawer {i}', 1] if k % 2 == 0 else [f'open drawer {i}', 1]
                  for k, i in enumerate([1, 1, 2, 2, 3, 3, 4, 4])]
        self.assertEqual(avoid.loops(search), set())                     # a systematic search is not a loop
        self.assertEqual(avoid.loops(attempt(*loop(3))), {('cycle', 'close microwave', 'open microwave')})
        self.assertEqual(avoid.loops(attempt('examine lamp 1', 'examine lamp 1', 'examine lamp 1')),
                         {('repeat', 'examine lamp')})
        self.assertEqual(avoid.loops(attempt('examine lamp 1', 'examine lamp 1')), set())


class MiningTests(unittest.TestCase):
    def pool(self, games, won=()):
        entry = avoid.new_entry(HEAT)
        for g in games:
            avoid.add_game(entry, g)
        for w in won:
            avoid.add_won(entry, w)
        return entry

    def test_pattern_across_games_is_mined(self):
        entry = self.pool([lost(f'g{i}', loop()) for i in range(3)])
        found = avoid.mine(entry)
        self.assertEqual([(c['kind'], c['games'], c['attempts']) for c in found], [('cycle', 3, 12)])

    def test_one_game_or_one_instance_is_not_enough(self):
        self.assertEqual(avoid.mine(self.pool([lost('g0', loop(), attempts=4)])), [])
        same = [lost('g0', loop()) for _ in range(3)]          # the same task three times is one instance
        entry = self.pool(same)
        self.assertEqual(len(entry['games']), 1)
        self.assertEqual(avoid.mine(entry), [])

    def test_a_pattern_in_a_won_attempt_is_not_an_anti_pattern(self):
        games = [lost(f'g{i}', loop()) for i in range(3)]
        self.assertEqual(avoid.mine(self.pool(games, [attempt(*loop(4), 'heat mug 1 with microwave 1')])), [])
        self.assertNotEqual(avoid.mine(self.pool(games, [attempt('heat mug 1 with microwave 1')])), [])

    def test_invalid_form_must_never_be_accepted_by_the_game(self):
        games = [lost(f'g{i}', ['!heat mug 1 with microwave 1']) for i in range(3)]
        self.assertEqual([c['sig'] for c in avoid.mine(self.pool(games))], [['invalid', 'heat <X> with <X>']])
        entry = self.pool(games, [attempt('heat egg 1 with microwave 1')])         # the game accepts it elsewhere
        self.assertEqual(avoid.mine(entry), [])

    def test_task_command_unused_in_wins_needs_enough_wins(self):
        games = [lost(f'g{i}', ['move mug 1 to stoveburner 1']) for i in range(3)]
        wins = [attempt('go to microwave 1', 'heat mug 1 with microwave 1')] * avoid.MIN_WON
        self.assertEqual([c['sig'] for c in avoid.mine(self.pool(games, wins))],
                         [['used', 'move <object> to stoveburner']])
        self.assertEqual(avoid.mine(self.pool(games, wins[:avoid.MIN_WON - 1])), [])

    def test_scenarios_with_known_answers(self):
        for s in json.loads(FIXTURES.read_text()):
            if s['expect'] == 'report':
                continue
            entry = avoid.new_entry(s['task_type'])
            conv = lambda rows: [[r[1:], 0] if isinstance(r, str) and r.startswith('!')
                                 else [r, 1] if isinstance(r, str) else list(r) for r in rows]
            for g in s['games']:
                avoid.add_game(entry, {'task_id': g['task_id'], 'task': g['task'],
                                       'attempts': [conv(a) for a in g['attempts']]})
            for w in s['won']:
                avoid.add_won(entry, conv(w))
            found = avoid.mine(entry)
            self.assertEqual(bool(found), s['expect'] == 'create', s['name'])
            if found:
                self.assertIn(found[0]['kind'], s['note'].split('|'), s['name'])
            for text in s['good_outputs']:
                self.assertEqual(avoid.judge(text, found[0], s['task_type'], entry['accepted']), [], (s['name'], text))
            for text in s['bad_outputs']:
                self.assertNotEqual(avoid.judge(text, found[0], s['task_type'], entry['accepted']), [],
                                    (s['name'], text))


class JudgeTests(unittest.TestCase):
    CYCLE = {'sig': ['cycle', 'close microwave', 'open microwave']}

    def problems(self, text, cand=None):
        return avoid.judge(text, cand or self.CYCLE, HEAT, [])

    def test_good_rule(self):
        self.assertEqual(self.problems('When heating an object, do not open and close the microwave over and over.'), [])

    def test_guessed_cause_fix_or_foreign_command_is_rejected(self):
        for text in ('When heating an object, do not open and close the microwave over and over because it wastes steps.',
                     'When heating an object, do not open the microwave; use the stove instead.',
                     'When heating an object, do not open and close the fridge over and over.',
                     'When heating a mug, do not open and close the microwave over and over.',
                     'Never open and close the microwave over and over.',
                     'When heating an object, open and close the microwave over and over.',
                     'When heating an object, do not open or close the microwave <X> over and over.',
                     'When heating an object, do not open and close the microwave over and over, then take it out and '
                     'put it on the counter and move it to the target and place it there for good measure now.'):
            self.assertNotEqual(self.problems(text), [], text)

    def test_every_word_the_pattern_consists_of_must_be_named(self):
        self.assertNotEqual(self.problems('When heating an object, do not repeat the microwave.'), [])
        self.assertNotEqual(self.problems('When heating an object, do not open the microwave over and over.'), [])

    def test_wording_asks_once_more_with_the_reasons_then_gives_up(self):
        entry = avoid.new_entry(HEAT)
        avoid.add_game(entry, lost('g0', loop()))
        cand = {'sig': ['cycle', 'close microwave', 'open microwave'], 'kind': 'cycle', 'games': 3, 'of_games': 3,
                'attempts': 12, 'of_attempts': 12, 'wins_checked': 0, 'example': ''}
        calls = []
        answers = iter(['When heating, do not repeat things because it is slow.',
                        'When heating an object, do not open and close the microwave over and over.'])
        text, notes = avoid.write(lambda role, payload: (calls.append(payload) or {'rule': next(answers)}), entry, cand)
        self.assertEqual(text, 'When heating an object, do not open and close the microwave over and over.')
        self.assertEqual(len(calls), 2)
        self.assertIn('problems', calls[1]['rejected'][0])
        self.assertIsNone(avoid.write(asker('When heating, do not do it.'), entry, cand)[0])
        self.assertIsNone(avoid.write(asker(None), entry, cand)[0])


class LifeCycleTests(unittest.TestCase):
    TEXT = 'When heating an object, do not open and close the microwave over and over.'

    def feed(self, rules, tids, ask=None, log=None):
        ops, nid = [], counter()
        for tid in tids:
            game = lost(tid, loop())
            ops += avoid.update(ask or asker(self.TEXT), rules, HEAT, game['task'], tid, game['attempts'], False,
                                nid, log if log is not None else [])
        return ops

    def test_rule_is_written_only_from_pooled_games_and_is_visible_and_retrievable(self):
        rules = []
        ops = self.feed(rules, ['g0'])
        self.assertEqual([r['type'] for r in rules], [avoid.POOL])             # one game: pooled, no rule
        calls = []
        ops += self.feed(rules, ['g1'], asker(self.TEXT, calls))
        written = [r for r in rules if r['type'] == avoid.TYPE]
        self.assertEqual(len(written), 1)
        self.assertEqual(len(calls), 1)
        rule = written[0]
        self.assertTrue(manual.shown_to_agent(rule))
        self.assertEqual(rule['pattern']['sig'], ['cycle', 'close microwave', 'open microwave'])
        harmful = {**rule, 'ev': {**manual.empty_evidence(), 'shown': 8, 'followed': 8, 'sum': -8, 'neg': 8}}
        self.assertEqual(manual.decisions([harmful]), (None, [harmful]))           # bad: retired, never refined
        self.assertEqual([r['id'] for r in manual.for_agent(rules, HEAT, 8)], [rule['id']])
        self.assertEqual([r for r in manual.relevant(rules, HEAT, 8) if r['type'] == avoid.POOL], [])
        self.assertEqual(manual.for_agent(rules, 'pick_and_place_simple', 8), [])
        # Not written twice: the pattern is known, so the model is not even asked.
        calls.clear()
        self.feed(rules, ['g2'], asker(self.TEXT, calls))
        self.assertEqual(calls, [])
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in rules), 1)

    def test_a_declined_pattern_is_not_asked_again_until_more_games_show_it(self):
        rules, calls = [], []
        self.feed(rules, ['g0', 'g1'], asker(None, calls))
        self.assertEqual(len(calls), 1)
        self.feed(rules, ['g2'], asker(None, calls))
        self.assertEqual(len(calls), 2)                                           # 3 games now: asked again
        self.assertEqual([r for r in rules if r['type'] == avoid.TYPE], [])

    def test_replay_gives_the_same_manual(self):
        rules, log = [], []
        ops = self.feed(rules, ['g0', 'g1', 'g2'], log=log)
        replayed = manual.replay([], ops, [])
        strip = lambda rs: sorted((r['type'], r['rule'], json.dumps(r.get('pool', r.get('pattern')), sort_keys=True))
                                  for r in rs)
        self.assertEqual(strip(replayed), strip(rules))
        # Two games of one batch writing the same pattern leave one rule.
        twice = manual.replay([], ops + [op for op in ops if op['op'] == 'write_rule'], [])
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in twice), 1)

    def test_a_won_attempt_with_the_pattern_retires_the_rule_and_it_is_not_rewritten(self):
        rules, log = [], []
        ops = self.feed(rules, ['g0', 'g1'])
        won_keep = attempt('go to microwave 1', 'heat mug 1 with microwave 1')
        won_bad = attempt(*loop(3), 'heat mug 1 with microwave 1')
        nid = counter()
        ops += avoid.update(asker(self.TEXT), rules, HEAT, 'g', 'w0', [won_keep], True, nid, log)
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in rules), 1)           # kept (evidence refreshed)
        self.assertEqual([r for r in rules if r['type'] == avoid.TYPE][0]['pattern']['wins_checked'], 1)
        ops += avoid.update(asker(self.TEXT), rules, HEAT, 'g', 'w1', [won_bad], True, nid, log)
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in rules), 0)
        self.assertTrue(any('contradicted by a won attempt' in e for e in log))
        self.assertEqual(len(avoid.pool_entry(rules, HEAT)['pool']['retired']), 1)
        calls = []
        self.feed(rules, ['g3'], asker(self.TEXT, calls))
        self.assertEqual(calls, [])                                                # the contradicted pattern stays dead
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in manual.replay([], ops, [])), 0)

    def test_append_only_writes_but_never_retires(self):
        rules, nid = [], counter()
        for tid in ('g0', 'g1'):
            game = lost(tid, loop())
            avoid.update(asker(self.TEXT), rules, HEAT, game['task'], tid, game['attempts'], False, nid, [],
                         append_only=True)
        avoid.update(asker(self.TEXT), rules, HEAT, 'g', 'w', [attempt(*loop(3))], True, nid, [], append_only=True)
        self.assertEqual(sum(r['type'] == avoid.TYPE for r in rules), 1)

    def test_judged_like_other_rules_useless_when_broken_but_not_for_merely_never_winning(self):
        rules = []
        self.feed(rules, ['g0', 'g1'])
        rule = next(r for r in rules if r['type'] == avoid.TYPE)
        complied = {rule['id']: {'followed': True, 'usefulness': 0, 'rule': rule['rule']}}
        for _ in range(12):                                                        # complied with, every game lost
            op = manual.observe(rules, complied, {'task': 't', 'task_type': HEAT}, 0, False)
        self.assertFalse(manual.useless(rule) or manual.bad(rule))
        self.assertEqual(manual.replay(copy.deepcopy(rules), [op], [])[-1]['ev']['followed'], 13)
        broken = {rule['id']: {'followed': False, 'usefulness': 0, 'rule': rule['rule']}}
        fresh = manual.fresh_evidence(copy.deepcopy(rule))
        for _ in range(10):                                                        # the agent did it anyway
            manual.observe([fresh], broken, {'task': 't', 'task_type': HEAT}, 0, False)
        self.assertTrue(manual.useless(fresh))
        ops = manual.batch_upkeep([fresh, *[r for r in rules if r['type'] == avoid.POOL]], set(), None)
        self.assertEqual([o['op'] for o in ops], ['retire'])

    def test_builder_cannot_rewrite_an_anti_pattern(self):
        rules = []
        self.feed(rules, ['g0', 'g1'])
        rule = next(r for r in rules if r['type'] == avoid.TYPE)
        log = []
        manual.apply(rules, [{'op': 'update_note', 'id': rule['id'], 'rule': 'When x, do not y.'},
                             {'op': 'update_rule', 'id': rule['id'], 'rule': 'When x, do not y.'}], 'failure', False,
                     counter(), log, HEAT)
        self.assertEqual(rule['rule'], self.TEXT)
        self.assertTrue(any('is not a hidden note' in e for e in log))
        self.assertTrue(any("unknown operation 'update_rule'" in e for e in log))


if __name__ == '__main__':
    unittest.main()
