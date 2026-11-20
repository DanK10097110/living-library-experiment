"""2026-11-20 changes: rule text is repaired instead of discarded (shared by E and E-minus), young or
demonstrably wrong recipes stay correctable (E), and hidden guesses are shown only after two won games
whose actions followed them (E)."""
import copy
import unittest

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

RECIPE = 'When an object must be examined under a light: search desks first, take it, use the desklamp.'
HEAT = 'pick_heat_then_place_in_recep'


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


def recipe(credits=0, **extra):
    return {**manual.new_rule('rule_1', 'Success Process', RECIPE, '', 'look_at_obj_in_light'),
            'alpha': 1 + credits, **extra}


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

    def test_write_update_and_refine_use_the_repair(self):
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Success Process',
                              'rule': 'When an object must be heated: take it, heat it with microwave 1, put it.'}],
                     'direct success', False, ids(), log, HEAT, ask=Asker())
        self.assertEqual(rules[0]['rule'], 'When an object must be heated: take it, heat it with the microwave, put it.')
        tip = manual.new_rule('rule_2', 'Special Phenomenon', 'If a container is closed, open it first.', '', HEAT)
        manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_2', 'rule': 'If fridge 1 is closed, open it first.'}],
                     'direct success', False, ids(), log, HEAT, ask=Asker())
        self.assertEqual(tip['rule'], 'If the fridge is closed, open it first.')


class YoungRecipeTests(unittest.TestCase):
    NEW = 'When an object must be examined under a light: take it first, then use the desklamp.'

    def update(self, rule, case='direct success', **extra):
        log = []
        applied = manual.apply([rule], [{'op': 'update_rule', 'id': 'rule_1', 'rule': self.NEW}], case, False,
                               ids(), log, **extra)
        return applied, log

    def test_a_young_recipe_may_be_rewritten_by_a_won_game(self):
        for credits in range(manual.YOUNG_CREDITS):
            young = recipe(credits)
            applied, log = self.update(young)
            self.assertEqual(young['rule'], self.NEW, credits)
            self.assertEqual(applied[0]['rule'], self.NEW)
            self.assertTrue(any('young recipe' in line for line in log))
        old = recipe(manual.YOUNG_CREDITS - 1, beta=2)                     # credits count wins and losses
        self.update(old)
        self.assertEqual(old['rule'], RECIPE)

    def test_a_young_recipe_is_not_rewritten_by_a_lost_game_or_a_retry_win(self):
        for case in ('failure', 'corrected failure'):
            young = recipe(0)
            self.update(young, case)
            self.assertEqual(young['rule'], RECIPE, case)

    def test_a_followed_recipe_with_a_rejected_step_may_be_rewritten(self):
        trace = [{'action': 'go to desk 1', 'valid': True, 'after': 'You see a desklamp 1.'},
                 {'action': 'take desklamp 1 from desk 1', 'valid': False, 'after': 'Nothing happens.'},
                 {'action': 'use desklamp 1', 'valid': True, 'after': 'You turn on the desklamp 1.'}]
        lamp = recipe(5)
        lamp['rule'] = 'When an object must be examined under a light: take the desklamp, use it.'
        self.assertEqual(manual.rejected_steps([lamp], ['rule_1'], trace), ['rule_1'])
        self.assertEqual(manual.rejected_steps([lamp], [], trace), [])          # not followed: no evidence
        self.assertEqual(manual.rejected_steps([lamp], None, trace), [])        # judge failed: no evidence
        self.assertEqual(manual.rejected_steps([recipe(5)], ['rule_1'], trace[:1] + trace[2:]), [])
        for case in ('indirect success', 'corrected failure'):
            old = copy.deepcopy(lamp)
            applied, log = self.update(old, case, correctable=['rule_1'])
            self.assertEqual(old['rule'], self.NEW, case)
            self.assertTrue(any('a step it instructs was rejected' in line for line in log))
        old = copy.deepcopy(lamp)                                       # a lost game still may not
        self.update(old, 'failure', correctable=['rule_1'])
        self.assertEqual(old['rule'], lamp['rule'])
        old = copy.deepcopy(lamp)                                       # nor a game without the evidence
        self.update(old, 'indirect success')
        self.assertEqual(old['rule'], lamp['rule'])

    def test_e_minus_cannot_update(self):
        young = recipe(0)
        manual.apply([young], [{'op': 'update_rule', 'id': 'rule_1', 'rule': self.NEW}], 'direct success', True,
                     ids(), [])
        self.assertEqual(young['rule'], RECIPE)


class Judging(FixtureModel):
    """The fixture policy; the outcome-blind judge says `followed` (ids) and records its payloads."""
    def __init__(self, followed, retry_followed=()):
        self.followed, self.retry_followed, self.judged, self.calls = list(followed), retry_followed, [], []

    def complete(self, role, payload, seed, context):
        self.calls.append((role, payload))
        if role == 'builder' and 'followed' in payload.get('response_schema', {}):
            self.judged.append(payload)
            return ModelResponse({'followed': [r['id'] for r in payload['rules'] if r['id'] in self.followed]})
        if role == 'builder':
            return ModelResponse({'diagnosis': 'imperfect agent', 'operations': []})
        return super().complete(role, payload, seed, context)


TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}


def play(model, rules, position=4):
    agent = Agent(Settings(), 'E', model, Library(), LexicalEmbedding(), MiniWorld, rules=rules)
    return agent.run(TASK, 1, {'phase': 'practice', 'position': position})


class HiddenGuessTests(unittest.TestCase):
    def guess(self):
        return {**manual.new_rule('rule_7', 'Special Phenomenon', 'When putting an object away, open the target first.',
                                  '', 'pick', verified=False)}

    def test_two_won_games_that_followed_a_hidden_guess_show_it(self):
        rules = [self.guess(), manual.new_rule('rule_8', 'Unresolved Error', 'When looking around, nothing changed.',
                                               '', 'pick', verified=False)]
        model = Judging(['rule_7', 'rule_8'])
        first = play(model, rules)
        self.assertTrue(first['success'])
        self.assertEqual(first['rules_shown'], [])                      # never shown to the agent
        judged = model.judged[0]
        self.assertEqual([r['id'] for r in judged['rules']], ['rule_7'])   # notes are not candidates
        self.assertEqual(first['manual']['guesses_followed'], ['rule_7'])
        self.assertFalse(rules[0]['verified'])
        self.assertEqual(rules[0]['confirmations'], 1)
        live = copy.deepcopy(rules)
        second = play(model, rules, position=5)
        self.assertTrue(rules[0]['verified'])
        self.assertIn('rule_7 confirmed by 2 won games that followed it (now shown to the agent)',
                      second['manual']['errors'])
        self.assertEqual(manual.replay(live, second['manual']['operations'], []), rules)
        self.assertFalse(rules[1]['verified'])                          # the note stays hidden
        third = play(model, rules, position=6)
        self.assertEqual(third['rules_shown'], ['rule_7'])

    def test_a_guess_the_judge_did_not_see_followed_is_not_confirmed(self):
        rules = [self.guess()]
        for position in (4, 5):
            play(Judging([]), rules, position)
        self.assertEqual((rules[0]['verified'], rules[0].get('confirmations')), (False, None))

    def test_the_judge_runs_before_the_builder_on_the_rules_the_agent_saw(self):
        model = Judging([])
        play(model, [manual.new_rule('rule_1', 'Special Phenomenon', 'If a container is closed, open it first.', '',
                                     'pick')])
        builder = [i for i, (role, p) in enumerate(model.calls) if role == 'builder']
        self.assertIn('followed', model.calls[builder[0]][1]['response_schema'])


class RetryJudgeTests(unittest.TestCase):
    class Agent:
        def __init__(self, answer):
            self.answer, self.payloads = answer, []
            self.public_task, self.rules_shown = {'goal': 'put an apple in the cabinet'}, ['rule_1']
            self.result = {'trace': [{'action': 'look', 'valid': True, 'after': 'You see nothing.'}]}

        def _ask(self, role, payload):
            self.payloads.append(payload)
            return {'followed': self.answer}

    def test_the_retry_judge_sees_only_the_note_and_the_retry_trace(self):
        retried = {'trace': [{'action': 'take apple 1', 'valid': True, 'after': 'You pick up the apple 1.'},
                             {'action': 'move apple 1 to cabinet 1', 'valid': True, 'after': 'You won.'}]}
        agent = self.Agent(['note'])
        self.assertTrue(manual.retry_judge(agent, retried, [])('When the object is in view, take it at once.'))
        payload = agent.payloads[0]
        self.assertEqual(payload['rules'], [{'id': 'note', 'rule': 'When the object is in view, take it at once.'}])
        self.assertEqual([s['action'] for s in payload['steps']], ['take apple 1', 'move apple 1 to cabinet 1'])
        self.assertNotIn('observation', payload['steps'][-1])
        self.assertFalse(manual.retry_judge(self.Agent([]), retried, [])('x'))

    def test_a_note_stays_hidden_when_the_retry_did_not_follow_it(self):
        note = manual.new_rule('rule_1', 'Unresolved Error', 'When looking around, nothing changes.', '', 'pick',
                               verified=False)
        op = {'op': 'update_rule', 'id': 'rule_1', 'type': 'Corrected Error',
              'rule': 'When the object is in view, take it at once instead of looking around.'}
        rules, log = [note], []
        manual.apply(rules, [op], 'corrected failure', False, None, log, 'pick', retry_followed=lambda text: False)
        self.assertEqual((note['type'], note['verified']), ('Unresolved Error', False))
        self.assertEqual(note['rule'], op['rule'])                       # reworded, still a hidden note
        self.assertIn('rule_1 keeps its type Unresolved Error (the winning retry did not follow it)', log)
        rules = [manual.new_rule('rule_1', 'Unresolved Error', 'When looking around, nothing changes.', '', 'pick',
                                 verified=False)]
        applied = manual.apply(rules, [op], 'corrected failure', False, None, [], 'pick',
                               retry_followed=lambda text: True)
        self.assertEqual((rules[0]['type'], rules[0]['verified']), ('Corrected Error', True))
        self.assertEqual((applied[0]['type'], applied[0]['verified']), ('Corrected Error', True))
        self.assertEqual(len(manual.for_agent(rules, 'pick', manual.SHOWN)), 1)


if __name__ == '__main__':
    unittest.main()
