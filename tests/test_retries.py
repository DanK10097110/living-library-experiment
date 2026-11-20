"""ExpeL-style practice retries (Reflexion), contrastive Corrected Error rules, hidden Builder notes,
recipe-shaped notes, and reliability-based retirement."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld, demo_manifest
from living_library.experiment import Runner
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1', 'task_type': 'pick'}
CORRECTED = 'When the object is in view, take it at once instead of looking around.'


def quiet(*args, **kwargs):
    pass


class Retrying(FixtureModel):
    """The fixture policy, except that the actor only looks around in the attempts listed in `fail`
    (0 = the first attempt), for practice games whose position is in `positions` (all if None)."""
    def __init__(self, fail=(0,), positions=None):
        self.fail, self.positions, self.calls = set(fail), positions, []

    def complete(self, role, payload, seed, context):
        self.calls.append((role, payload, dict(context)))
        attempt = context.get('attempt', 0)
        if (role == 'actor' and context.get('phase') == 'practice' and attempt in self.fail
                and (self.positions is None or context.get('position') in self.positions)):
            return ModelResponse({'text': '<action>look</action>'}, input_tokens=7, output_tokens=1)
        if role == 'reflector':
            return ModelResponse({'reflection': 'I only looked around. Take the apple first, then move it.'},
                                 input_tokens=11, output_tokens=5)
        if role == 'builder' and 'successful_retry' in payload:
            return ModelResponse({'diagnosis': 'imperfect rules', 'operations': [
                {'op': 'write_rule', 'type': 'Corrected Error', 'rule': CORRECTED, 'example': ''}]})
        response = super().complete(role, payload, seed, context)
        response.input_tokens, response.output_tokens = 3, 1
        return response


def cfg(**extra):
    return Settings(step_budget=12, subgoal_step_budget=6, replans=0, **extra)


def run(model, condition='E', rules=None, context=None, library=None, frozen=False):
    agent = Agent(cfg(), condition, model, library or Library(), LexicalEmbedding(), MiniWorld,
                  rules=[] if rules is None else rules, frozen=frozen)
    return agent.run(TASK, 1, {'phase': 'practice', 'position': 0, **(context or {})})


class RetryTests(unittest.TestCase):
    def test_failed_game_is_retried_until_won_and_builder_contrasts_the_attempts(self):
        model, rules, library = Retrying(fail=(0, 1)), [], Library()
        before = library.snapshot()
        result = run(model, rules=rules, library=library)
        self.assertFalse(result['success'])                                # the practice metric: first attempt
        retries = result['retries']
        self.assertEqual([a['success'] for a in retries['attempts']], [False, True])   # stops at the win
        self.assertTrue(retries['won'])
        self.assertEqual(result['manual']['case'], 'corrected failure')
        self.assertEqual([(r['type'], r['rule']) for r in rules if r['type'] != 'Failure Pool'], [('Corrected Error', CORRECTED)])
        builder = [p for role, p, _ in model.calls if role == 'builder'][0]
        self.assertFalse(builder['game']['won'])
        self.assertTrue(builder['successful_retry']['won'])
        self.assertEqual(len(builder['reflections']), 2)
        self.assertIn('Corrected Error rule', builder['instructions'])
        # Retry 2 saw both reflections; the first attempt saw none; retries have their own cache keys.
        prompts = {c.get('attempt', 0): p['prompt'] for role, p, c in model.calls if role == 'actor'}
        self.assertNotIn('Your attempt 1', prompts[0])
        self.assertIn('Your attempt 2 at this same task failed', prompts[2])
        reflector = [p for role, p, _ in model.calls if role == 'reflector']
        self.assertEqual(reflector[1]['previous_reflections'], [retries['attempts'][0]['reflection']])
        # Costs: the record's totals include the retries; the breakdown is kept separately.
        self.assertEqual(result['model_calls'], len(model.calls))
        self.assertEqual(result['input_tokens'], sum(7 if r == 'actor' and c.get('attempt', 0) in (0, 1) else
                                                     11 if r == 'reflector' else 0 if r == 'builder' else 3
                                                     for r, _, c in model.calls))
        retry_calls = sum(1 for _, _, c in model.calls if c.get('attempt')) + len(reflector)
        self.assertEqual(retries['model_calls'], retry_calls)
        self.assertEqual(library.snapshot(), before)                       # retries change no memory

    def test_all_retries_fail_gives_an_unresolved_note_hidden_from_the_agent(self):
        model, rules = Retrying(fail=range(manual.RETRIES + 1)), []
        result = run(model, rules=rules)
        self.assertEqual(len(result['retries']['attempts']), manual.RETRIES)
        self.assertFalse(result['retries']['won'])
        self.assertEqual(result['manual']['case'], 'failure')
        builder = [p for role, p, _ in model.calls if role == 'builder'][0]
        self.assertEqual(len(builder['failed_retries']), manual.RETRIES)
        self.assertEqual([r['type'] for r in rules if r['type'] != 'Failure Pool'], ['Unresolved Error'])
        self.assertEqual(manual.for_agent(rules, 'pick', manual.SHOWN), [])
        # The note is not shown to the agent in the next game, but the Builder still sees it.
        spy = Retrying(fail=())
        nxt = run(spy, rules=rules, context={'position': 1})
        self.assertEqual(nxt['rules_shown'], [])
        self.assertNotIn('Rules learned from earlier practice', [p for r, p, _ in spy.calls if r == 'actor'][0]['prompt'])
        self.assertIn(rules[0]['id'], [r['id'] for r in [p for r, p, _ in spy.calls if r == 'builder'][0]['rules']])

    def test_no_retries_outside_library_practice(self):
        for condition, frozen, phase in (('C', False, 'practice'), ('D', False, 'practice'),
                                         ('E-text', False, 'practice'), ('E', True, 'evaluation')):
            model = Retrying(fail=range(5))
            model_phase = {'phase': phase}
            result = run(model, condition=condition, context=model_phase, frozen=frozen)
            self.assertNotIn('retries', result, condition)
            self.assertFalse(any(role == 'reflector' or c.get('attempt') for role, _, c in model.calls), condition)
        model = Retrying(fail=range(5))                    # a game won at once is not retried
        self.assertNotIn('retries', run(Retrying(fail=()), condition='E-minus'))
        # E-minus retries too (the ablation differs from E only in rule management)
        self.assertIn('retries', run(model, condition='E-minus'))

    def test_a_note_becomes_a_corrected_error_only_after_a_retry_success(self):
        note = manual.new_rule('rule_1', 'Unresolved Error', 'When looking around, nothing changes.', '', 'pick')
        op = {'op': 'update_rule', 'id': 'rule_1', 'type': 'Corrected Error', 'rule': CORRECTED}
        rules, log = [copy.deepcopy(note)], []
        manual.apply(rules, [op], 'failure', False, None, log, 'pick')
        self.assertEqual(rules[0]['type'], 'Unresolved Error')
        self.assertIn('keeps its type', log[0])
        # (2026-11-20) only if the winning retry followed the corrected text (outcome-blind judge)
        applied = manual.apply(rules, [op], 'corrected failure', False, None, [], 'pick',
                               retry_followed=lambda text: text == CORRECTED)
        self.assertEqual((rules[0]['type'], rules[0]['rule']), ('Corrected Error', CORRECTED))
        self.assertEqual(manual.replay([note], applied, [])[0]['type'], 'Corrected Error')
        self.assertEqual(len(manual.for_agent(rules, 'pick', manual.SHOWN)), 1)

    def test_batched_practice_with_retries_is_deterministic_and_resumable(self):
        settings = Settings(practice_episodes=4, evaluation_games=2, step_budget=12, subgoal_step_budget=6,
                            replans=0, bootstrap_samples=20, seeds=[11], conditions=['C', 'E'], practice_batch=2)
        timing = ('wall_seconds', 'model_wall_seconds', 'gpu_seconds')
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                runner = Runner(settings, demo_manifest(), tmp, model=Retrying(positions={0, 2}))
                records = runner.study(('C', 'E'), demo_count=4, log=quiet)
                practice = [r for r in records if r['phase'] == 'practice']
                self.assertEqual([r['success'] for r in practice], [False, True, False, True])
                self.assertTrue(all(practice[i]['retries']['won'] for i in (0, 2)))
                self.assertFalse(any('retries' in r for r in records if r['phase'] != 'practice'))
                with patch.object(Retrying, 'complete', side_effect=AssertionError('resume called model')):
                    again = Runner(settings, demo_manifest(), tmp, model=Retrying()).study(('C', 'E'), 4, log=quiet)
                self.assertEqual(records, again)
                final = json.loads((Path(tmp) / 'checkpoints' / 'practice-E-0' / '00003.json').read_text())
                outputs.append(([{k: v for k, v in r.items() if k not in timing} for r in records],
                                final['memory']['rules']))
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn('Corrected Error', [r['type'] for r in outputs[0][1]])


class RuleFormTests(unittest.TestCase):
    def test_recipe_shaped_notes_are_rejected(self):
        # Real rules from the study gate library (rule_6, 7, 9, 3) were recipes written as errors.
        recipes = ['When an object must be cleaned and placed, the agent must first locate the object and a '
                   'sinkbasin, then clean the object at the sinkbasin before moving to the target.',
                   'If an object must be cleaned and placed, take it from its current location, clean it at the '
                   'sinkbasin, then move it to the target.',
                   'When an object must be cooled and placed: take it from the source, cool it with the fridge, '
                   'go to the target, move it there.',
                   'If two objects must be placed in a target, find and take the first object, go to the target, '
                   'move it there, then find and take the second object and move it to the target.']
        for text in recipes:
            self.assertIn('lists steps', ' '.join(manual.rule_problems('Unresolved Error', text)), text)
        fine = ['When a container is closed, open it before taking things from it or putting things in it.',
                'When the target object is not found in any searched location, keep searching the remaining ones.',
                'When examining an object under a light source, turn on the light source first.']
        for text in fine:
            self.assertEqual(manual.rule_problems('Unresolved Error', text), [], text)
        self.assertEqual(manual.rule_problems('Success Process', recipes[2]), [])


class RetirementTests(unittest.TestCase):
    def rule(self, won, lost, base):
        r = manual.new_rule('rule_1', 'Special Phenomenon', 'When x, do y.', '', 'heat')
        r.update(alpha=1 + won, beta=1 + lost, base=base)
        return r

    def test_rule_clearly_below_its_task_base_rate_is_retired_and_logged(self):
        self.assertTrue(manual.retirable(self.rule(0, 5, [6, 10])))
        self.assertFalse(manual.retirable(self.rule(1, 5, [0, 10])))      # hard task: no worse than base
        self.assertFalse(manual.retirable(self.rule(0, 3, [9, 10])))      # too few games shown
        self.assertFalse(manual.retirable(self.rule(2, 3, [5, 10])))      # not clearly worse
        rules, report = [self.rule(0, 5, [6, 10]), self.rule(3, 2, [6, 10])], {'operations': [], 'errors': []}
        rules[1]['id'] = 'rule_2'
        live = copy.deepcopy(rules)
        manual.retire(rules, report)
        self.assertEqual([r['id'] for r in rules], ['rule_2'])
        self.assertEqual(report['operations'][0]['op'], 'retire')
        self.assertIn('retired rule_1 (won 0 of 5', report['errors'][0])
        self.assertEqual([r['id'] for r in manual.replay(live, report['operations'], [])], ['rule_2'])

    def test_base_rate_counts_every_game_of_the_rules_kind(self):
        rules = [manual.new_rule('rule_1', 'Special Phenomenon', 'a', '', 'heat'),
                 manual.new_rule('rule_2', 'Special Phenomenon', 'b', '', 'all'),
                 manual.new_rule('rule_3', 'Special Phenomenon', 'c', '', 'clean')]
        context = {'task': 't', 'task_type': 'heat', 'steps': []}
        manual.observe(rules, [], True, context, 0)
        manual.observe(rules, ['rule_1'], False, context, 1)
        self.assertEqual([r['base'] for r in rules], [[1, 2], [1, 2], [0, 0]])
        self.assertEqual(manual.observed(rules[0]), [0, 1])                # shown once, lost

    def test_build_records_an_outcome_every_game_and_retires(self):
        bad = self.rule(0, 5, [6, 10])
        bad['task_type'] = 'pick'
        rules = [bad]
        result = run(Retrying(fail=()), rules=rules)
        ops = result['manual']['operations']
        self.assertIn('outcome', [o['op'] for o in ops])
        self.assertIn({'op': 'retire', 'id': 'rule_1', 'won': 1, 'lost': 5, 'base': [7, 11]}, ops)
        self.assertNotIn('rule_1', [r['id'] for r in rules])


if __name__ == '__main__':
    unittest.main()
