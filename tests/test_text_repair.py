"""Rule text is repaired instead of discarded (shared by E and E-minus; writes, note updates and refinements),
and the retry judge that guards a note's conversion into a Corrected Error. (The young-recipe and hidden-guess
paths were removed by the redesign of 2026-11-20.)"""
import types
import unittest

from living_library import manual

HEAT = 'pick_heat_then_place_in_recep'



def host(ask):
    """An agent for manage/refine: `ask` answers the refiner; a trial game uses the candidate without harm."""
    costs = {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'model_wall_seconds': 0.0}

    def trial_agent(rules, pinned):
        return types.SimpleNamespace(run=lambda task, seed, context: {
            **costs, 'success': True, 'goal': 'g', 'rules_used': [pinned], 'gpu_seconds': 0.0,
            'trace': [{'action': 'look', 'valid': True, 'after': 'You see nothing.'}]})
    return types.SimpleNamespace(_ask=ask, trial_agent=trial_agent, seed=1, context={'position': 0},
                                 result=dict(costs), gpu=0.0, gpu_known=True)

class Asker:
    """A model call that answers every rewrite with the next scripted text and records the requests."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, role, payload):
        self.calls.append((role, payload))
        return {'rule': self.answers.pop(0)} if self.answers else {}


def ids(start=10):
    n = [start]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


class InstanceNumberTests(unittest.TestCase):
    def test_instance_numbers_of_alfworld_nouns_are_stripped(self):
        self.assertEqual(manual.strip_instances('heat it with microwave 1'), 'heat it with the microwave')
        self.assertEqual(manual.strip_instances('open the drawer 3, then a cabinet 2'), 'open the drawer, then a cabinet')
        self.assertEqual(manual.strip_instances('on floor 3, step 2'), 'on floor 3, step 2')    # not ALFWorld nouns
        self.assertEqual(manual.checked('Special Phenomenon', 'When heating, heat it with microwave 1.'),
                         'When heating, heat it with the microwave.')
        self.assertEqual(manual.checked('Special Phenomenon', 'Microwave 1 heats things.'), 'The microwave heats things.')

    def test_no_model_call_when_stripping_suffices(self):
        ask = Asker()
        self.assertEqual(manual.checked('Success Process', 'When an object must be heated: take it, heat it with '
                                        'microwave 1, put it in the target.', ask, HEAT),
                         'When an object must be heated: take it, heat it with the microwave, put it in the target.')
        self.assertEqual(ask.calls, [])

    def test_stripped_portable_objects_still_get_the_specificity_rewrite(self):
        ask = Asker('When placing: go to the countertop and take the object, put it in the target.')
        text = manual.checked('Success Process', 'When placing: go to countertop 2 and take apple 1, put it in '
                              'the target.', ask, 'pick_and_place_simple')
        self.assertEqual(text, 'When placing: go to the countertop and take the object, put it in the target.')
        self.assertEqual(len(ask.calls), 1)                             # one rewrite: the specificity one
        self.assertEqual(ask.calls[0][1]['rule'], 'When placing: go to the countertop and take the apple, put it in '
                                                  'the target.')
        self.assertEqual(ask.calls[0][1]['offending_words'], ['apple'])
        # the rewrite's own instance numbers are stripped too
        ask = Asker('When placing: take the object from countertop 1, put it in the target.')
        self.assertEqual(manual.checked('Success Process', 'When placing: take apple 1, put it in the target.', ask,
                                        'pick_and_place_simple'),
                         'When placing: take the object from the countertop, put it in the target.')
        # a rewrite that is still specific is rejected, as before
        with self.assertRaisesRegex(ValueError, 'names specific objects'):
            manual.checked('Success Process', 'When placing: take apple 1, put it.', Asker('Take the apple.'),
                           'pick_and_place_simple')

    def test_other_failures_get_one_rewrite_told_the_problems(self):
        long = 'When the target is full, ' + 'try another place and open it, ' * 8
        ask = Asker('When the target is full, put the object in another open place.')
        self.assertEqual(manual.checked('Corrected Error', long, ask, HEAT),
                         'When the target is full, put the object in another open place.')
        self.assertEqual(len(ask.calls), 1)
        self.assertIn('too long', ask.calls[0][1]['problems'][0])
        self.assertIn('too long', ask.calls[0][1]['instructions'])
        # a numbered word that is no ALFWorld noun is repaired the same way
        ask = Asker('When upstairs, open the door first.')
        self.assertEqual(manual.checked('Special Phenomenon', 'When on floor 3, open the door first.', ask),
                         'When upstairs, open the door first.')
        # still failing after the one rewrite (or no answer): rejected, naming the original problems
        with self.assertRaisesRegex(ValueError, r'too long .*still after one rewrite'):
            manual.checked('Corrected Error', long, Asker(long), HEAT)
        with self.assertRaisesRegex(ValueError, 'still after one rewrite'):
            manual.checked('Corrected Error', long, Asker(), HEAT)
        # without a model call nothing is rewritten
        with self.assertRaisesRegex(ValueError, 'too long'):
            manual.checked('Corrected Error', long)

    def test_write_update_note_and_refine_use_the_repair(self):
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Success Process',
                              'rule': 'When an object must be heated: take it, heat it with microwave 1, put it.'}],
                     'direct success', False, ids(), log, HEAT, ask=Asker())
        self.assertEqual(rules[0]['rule'], 'When an object must be heated: take it, heat it with the microwave, put it.')
        note = manual.new_rule('rule_2', 'Unresolved Error', 'When a container was closed, nothing was found.', '', HEAT)
        manual.apply([note], [{'op': 'update_note', 'id': 'rule_2', 'rule': 'When fridge 1 was closed, nothing was found.'}],
                     'failure', False, ids(), log, HEAT, ask=Asker())
        self.assertEqual(note['rule'], 'When the fridge was closed, nothing was found.')
        tip = manual.new_rule('rule_3', 'Special Phenomenon', 'If a container is closed, open it first.', '', HEAT)
        tip['ev'] = {**manual.empty_evidence(), 'shown': 6, 'followed': 6, 'sum': -6, 'neg': 6}
        tip['contexts'] = [{'task': 't', 'score': -1, 'steps': ['open fridge 1'], 'reason': 'r',
                            'task_ref': {'id': 't', 'task_type': HEAT}}]
        report = {'operations': [], 'errors': []}
        manual.manage(host(Asker('If fridge 1 is closed, open the fridge first.')), [tip], report)
        self.assertEqual(tip['rule'], 'If the fridge is closed, open the fridge first.')


class RetryCheckTests(unittest.TestCase):
    def test_a_note_stays_hidden_when_the_retry_shows_harm_from_it(self):
        note = manual.new_rule('rule_1', 'Unresolved Error', 'When looking around, nothing changes.', '', 'pick')
        op = {'op': 'update_note', 'id': 'rule_1', 'type': 'Corrected Error',
              'rule': 'When the object is in view, take it at once instead of looking around.'}
        rules, log = [note], []
        manual.apply(rules, [op], 'corrected failure', False, None, log, 'pick', trace=[],
                     retry_check=lambda r: False)
        self.assertEqual((note['type'], note['hidden']), ('Unresolved Error', True))
        self.assertEqual(note['rule'], op['rule'])                       # reworded, still a hidden note
        self.assertIn('rule_1 stays a hidden note (the winning retry shows harm from it)', log)
        rules = [manual.new_rule('rule_1', 'Unresolved Error', 'When looking around, nothing changes.', '', 'pick')]
        applied = manual.apply(rules, [op], 'corrected failure', False, None, [], 'pick', trace=[],
                               retry_check=lambda r: True)
        self.assertEqual((rules[0]['type'], rules[0]['hidden']), ('Corrected Error', False))
        self.assertEqual(applied[0]['type'], 'Corrected Error')
        self.assertEqual(len(manual.for_agent(rules, 'pick', manual.SHOWN)), 1)


if __name__ == '__main__':
    unittest.main()
