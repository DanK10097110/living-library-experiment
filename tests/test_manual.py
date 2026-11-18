import json
import tempfile
import unittest
from pathlib import Path

from living_library import manual
from living_library.agents import Agent
from living_library.config import Settings
from living_library.environments import MiniWorld, demo_manifest
from living_library.experiment import Runner
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1'}


def quiet(*args, **kwargs):
    pass


def ids():
    n = [0]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


class RuleOperationTests(unittest.TestCase):
    def test_case_comes_from_the_game(self):
        self.assertEqual(manual.case_of({'success': True, 'trace': [{'valid': True}]}), 'direct success')
        self.assertEqual(manual.case_of({'success': True, 'trace': [{'valid': False}, {'valid': True}]}),
                         'indirect success')
        self.assertEqual(manual.case_of({'success': False, 'trace': []}), 'failure')

    def test_case_limits_are_enforced(self):
        rules, log = [], []
        ops = [{'op': 'write_rule', 'type': 'Success Process', 'rule': 'When x, do y.'},
               {'op': 'write_rule', 'type': 'Unresolved Error', 'rule': 'When a, b happened.'},
               {'op': 'write_rule', 'type': 'Unresolved Error', 'rule': 'When c, d happened.'}]
        applied = manual.apply(rules, ops, 'failure', False, ids(), log)
        self.assertEqual([r['type'] for r in rules], ['Unresolved Error'])      # one, and no recipe
        self.assertEqual(len(applied), 1)
        self.assertTrue(any('may not write a Success Process' in e for e in log))
        self.assertTrue(any('at most 1' in e for e in log))

    def test_general_scope_is_refused_for_kind_specific_text(self):
        text = 'When an object must be cooled and placed, search kitchen areas first, cool with fridge if closed.'
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Corrected Error', 'rule': text, 'scope': 'all'}],
                     'indirect success', False, ids(), log, task_type='pick_cool_then_place_in_recep')
        self.assertEqual(rules[0]['task_type'], 'pick_cool_then_place_in_recep')
        self.assertTrue(any('limited to' in e for e in log))
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Corrected Error',
                              'rule': 'When a door is closed, open it first.', 'scope': 'all'}],
                     'indirect success', False, ids(), log, task_type='heat')
        self.assertEqual(rules[0]['task_type'], 'all')

    def test_update_and_merge_narrow_kind_specific_general_rules(self):
        rule = {'id': 'rule_1', 'type': 'Corrected Error', 'rule': 'When a door is closed, open it first.',
                'example': '', 'validation': '', 'task_type': 'all', 'verified': True}
        applied = manual.apply([rule], [{'op': 'update_rule', 'id': 'rule_1',
                                         'rule': 'When an item is hot, heat it in the microwave.'}],
                               'indirect success', False, ids(), [], task_type='heat')
        self.assertEqual(rule['task_type'], 'heat')
        self.assertEqual(applied[0]['task_type'], 'heat')
        twin = {'id': 'rule_2', 'type': 'Corrected Error', 'rule': 'Use the fridge.', 'task_type': 'all'}
        self.assertTrue(manual.narrowed(twin, 'cool', []))
        self.assertEqual(twin['task_type'], 'cool')

    def test_append_only_cannot_change_rules_and_validation_keeps_three_notes(self):
        rules = [{'id': 'rule_1', 'type': 'Success Process', 'rule': 'When x, do y.', 'example': '', 'validation': ''}]
        log = []
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'changed'},
                             {'op': 'downvote_rule', 'id': 'rule_1'}], 'direct success', True, ids(), log)
        self.assertEqual(rules[0]['rule'], 'When x, do y.')
        self.assertEqual(len(log), 2)
        for note in ('a', 'b', 'c', 'd'):
            manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'validation': note}], 'direct success',
                         False, ids(), [])
        self.assertEqual(rules[0]['validation'], 'b | c | d')
        self.assertNotIn('b | c | d', ' '.join(manual.render(rules)))          # never shown to the agent

    def test_rule_text_must_be_short_and_general(self):
        long = 'When the task is to put two objects in a container, ' + 'pick up the object and move it, ' * 6
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Corrected Error', 'rule': long},
                             {'op': 'write_rule', 'type': 'Special Phenomenon',
                              'rule': 'When at drawer 3, open drawer 3 first.'}], 'indirect success', False, ids(), log)
        self.assertEqual(rules, [])
        self.assertIn('too long', log[0])
        self.assertIn("numbered object ('drawer 3')", log[1])
        # a short general rule passes; a type label and repeated words are tidied away
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon',
                              'rule': 'Special Phenomenon: When when a container is closed, open it first.',
                              'example': 'open drawer 3; ' * 40}], 'direct success', False, ids(), log)
        self.assertEqual(rules[0]['rule'], 'When a container is closed, open it first.')
        self.assertLessEqual(len(rules[0]['example']), manual.MAX_EXAMPLE)    # examples may quote real steps
        # list numbering in a recipe is not a numbered object; updates are checked too
        self.assertEqual(manual.rule_problems('Success Process', 'When placing: 1. take it, 2. go there, 3. put it.'), [])
        log = []
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': long}], 'direct success', False, ids(), log)
        self.assertEqual(rules[0]['rule'], 'When a container is closed, open it first.')
        self.assertIn('too long', log[0])

    def test_builder_is_told_its_types_and_the_existing_recipe(self):
        recipe = {'id': 'rule_4', 'type': 'Success Process', 'rule': 'r', 'task_type': 'pick'}
        guide = manual.builder_guide('failure', False, 'pick', [recipe])
        self.assertIn('only these types here: Unresolved Error, Special Phenomenon', guide)
        self.assertNotIn('already has a Success Process', guide)              # it may not write one anyway
        guide = manual.builder_guide('direct success', False, 'pick', [recipe])
        self.assertIn('already has a Success Process (rule_4)', guide)
        self.assertIn('at most 25 words', guide)

    def test_one_success_process_per_task_type(self):
        rules, log = [], []
        recipe = {'op': 'write_rule', 'type': 'Success Process', 'rule': 'When putting, take then move.'}
        manual.apply(rules, [recipe], 'direct success', False, ids(), log, 'pick_and_place_simple')
        manual.apply(rules, [{**recipe, 'rule': 'When putting in a drawer, open it first.'}], 'direct success',
                     False, ids(), log, 'pick_and_place_simple')
        manual.apply(rules, [{**recipe, 'rule': 'When cleaning, use the sinkbasin.'}], 'direct success',
                     False, ids(), log, 'pick_clean_then_place_in_recep')
        self.assertEqual([r['task_type'] for r in rules], ['pick_and_place_simple', 'pick_clean_then_place_in_recep'])
        self.assertIn('update it instead', log[0])

    def test_no_cap_but_each_game_sees_only_its_relevant_rules(self):
        kinds = ['heat', 'clean']
        rules = [{'id': f'rule_{i}', 'type': 'Unresolved Error', 'rule': f'r{i}', 'example': '', 'validation': '',
                  'task_type': kinds[i % 2] if i % 5 else 'all'} for i in range(1, 60)]
        rules.append({'id': 'rule_60', 'type': 'Success Process', 'rule': 'heat recipe', 'example': '',
                      'validation': '', 'task_type': 'heat'})
        self.assertEqual(len(rules), 60)                                   # nothing was dropped
        shown = manual.relevant(rules, 'heat', manual.SHOWN)
        self.assertEqual(len(shown), manual.SHOWN)
        self.assertEqual(shown[0]['rule'], 'heat recipe')                  # its recipe first
        self.assertTrue(all(r['task_type'] in ('heat', 'all') for r in shown))
        self.assertEqual(shown[1]['id'], 'rule_58')                        # then newest relevant first (59 is 'clean')

    def test_builder_may_only_change_rules_it_was_shown(self):
        rules = [{'id': 'rule_1', 'type': 'Corrected Error', 'rule': 'x', 'example': '', 'validation': '',
                  'task_type': 'clean'}]
        log = []
        manual.apply(rules, [{'op': 'downvote_rule', 'id': 'rule_1'}], 'direct success', False, ids(), log,
                     'heat', visible=[])
        self.assertEqual(len(rules), 1)
        self.assertIn('unknown rule id', log[0])

    def test_batch_replay_reissues_ids_and_skips_stale_edits(self):
        live = [{'id': 'rule_1', 'type': 'Success Process', 'rule': 'A', 'example': '', 'validation': ''}]
        log = []
        live = manual.replay(live, [{'op': 'write_rule', 'type': 'Corrected Error', 'rule': 'B', 'example': ''},
                                    {'op': 'downvote_rule', 'id': 'rule_1'},
                                    {'op': 'downvote_rule', 'id': 'rule_1'}], log)   # ExpeL: removed at 0
        live = manual.replay(live, [{'op': 'write_rule', 'type': 'Corrected Error', 'rule': 'B', 'example': ''},
                                    {'op': 'update_rule', 'id': 'rule_1', 'rule': 'A2'}], log)
        self.assertEqual([(r['id'], r['rule']) for r in live], [('rule_2', 'B')])
        self.assertEqual([entry[0] for entry in log], ['duplicate rule', 'rule already gone'])


class ManualInGamesTests(unittest.TestCase):
    def test_practice_builds_rules_and_the_actor_sees_them(self):
        seen = []

        class Spy(FixtureModel):
            def complete(self, role, payload, seed, context):
                if role == 'actor':
                    seen.append(payload['prompt'])
                return super().complete(role, payload, seed, context)
        rules = []
        agent = Agent(Settings(), 'E', Spy(), Library(), LexicalEmbedding(), MiniWorld, rules=rules)
        result = agent.run(TASK, 1, {'phase': 'practice'})
        self.assertTrue(result['success'])
        self.assertEqual(result['manual']['case'], 'direct success')
        self.assertEqual([r['type'] for r in rules if r['type'] != 'Failure Pool'], ['Success Process'])
        Agent(Settings(), 'E', Spy(), Library(), LexicalEmbedding(), MiniWorld, rules=rules).run(
            TASK, 1, {'phase': 'practice'})
        self.assertIn('Rules learned from earlier practice', seen[-1])
        self.assertEqual(len([r for r in rules if r['type'] != 'Failure Pool']), 1)                                     # duplicate not written twice

    def test_tests_and_etext_only_read_rules(self):
        rules = [{'id': 'rule_1', 'type': 'Success Process', 'rule': 'When x, do y.', 'example': '', 'validation': ''}]
        for condition, context, frozen in (('E', {'phase': 'evaluation'}, True), ('E-text', {'phase': 'practice'}, False),
                                           ('C', {'phase': 'practice'}, False)):
            before = json.dumps(rules)
            result = Agent(Settings(), condition, FixtureModel(), Library(), LexicalEmbedding(), MiniWorld,
                           rules=rules, frozen=frozen).run(TASK, 1, context)
            self.assertNotIn('manual', result, condition)
            self.assertEqual(json.dumps(rules), before)

    def test_batched_study_practice_keeps_rules_and_etext_reads_es(self):
        cfg = Settings(practice_episodes=4, evaluation_games=2, step_budget=15, bootstrap_samples=20, seeds=[11],
                       conditions=['C', 'E', 'E-minus', 'E-text'], practice_batch=2)
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp)
            specs = runner.study_specs(demo_count=4)
            self.assertTrue(runner.execute(specs, workers=4, log=quiet))
            final = json.loads((Path(tmp) / 'checkpoints' / 'practice-E-0' / '00003.json').read_text())['memory']
            self.assertEqual([r['type'] for r in final['rules'] if r['type'] != 'Failure Pool'], ['Success Process'])
            text = json.loads((Path(tmp) / 'checkpoints' / 'evaluation-E-text-11' / '00000.json').read_text())
            self.assertEqual(text['memory']['rules'], final['rules'])


if __name__ == '__main__':
    unittest.main()
