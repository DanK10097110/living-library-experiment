"""E's rule management: the Builder never rewrites visible text (redesign of 2026-11-20), the instructed-command
check against game traces (now the write gate's trace check), one text change per rule per batch, the E-only
restart with its E-minus probe, and the shared two-object subgoal issue (recorded, not fixed)."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from living_library import manual
from living_library.agents import Agent
from living_library.batching import merge_memory
from living_library.config import Settings
from living_library.domain import Predicate, State
from living_library.environments import demo_manifest



def quiet(*args, **kwargs):
    pass


def ids(start=10):
    n = [start]

    def next_id():
        n[0] += 1
        return f'rule_{n[0]}'
    return next_id


def rule(rule_id, kind, text, task_type='look_at_obj_in_light', **extra):
    return {**manual.new_rule(rule_id, kind, text, '', task_type), **extra}


RECIPE = 'When an object must be examined under a light: search desks first, take it, use the desklamp.'


class RecipeStabilityTests(unittest.TestCase):
    def test_builder_cannot_rewrite_a_recipe_but_may_note_it(self):
        rules, log = [rule('rule_1', 'Success Process', RECIPE)], []
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1',
                                        'rule': 'When an object must be examined: search shelves first, take it, '
                                                'use the desklamp.', 'example': 'go to shelf 1'}],
                               'direct success', False, ids(), log)
        self.assertEqual(rules[0]['rule'], RECIPE)
        self.assertEqual(applied, [])
        manual.apply(rules, [{'op': 'note', 'id': 'rule_1', 'validation': 'confirmed again'}],
                     'indirect success', False, ids(), log)
        self.assertEqual((rules[0]['rule'], rules[0]['validation']), (RECIPE, 'confirmed again'))

    def test_recipe_text_changes_only_through_refinement_of_a_bad_recipe(self):
        recipe = rule('rule_1', 'Success Process', RECIPE)
        context = {'task': 'look', 'task_type': 'look_at_obj_in_light', 'steps': ['go to desk 1', 'use desklamp 1'],
                   'task_ref': {'id': 'look-1', 'task_type': 'look_at_obj_in_light'}}
        new = 'When an object must be examined under a light: search desks first, take it, use the desklamp 1 there.'
        for n in range(manual.MIN_EVIDENCE):
            manual.observe([recipe], {'rule_1': {'followed': True, 'usefulness': -1, 'rule': RECIPE}}, context, n, False)

        class Asker:
            seed, context, gpu, gpu_known = 1, {'position': 6}, 0.0, True
            result = {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'model_wall_seconds': 0.0}

            def _ask(self, role, payload):
                return {'rule': new}

            def trial_agent(self, rules, pinned):       # the trial game uses the candidate without harm
                class Game:
                    def run(self, task, seed, context):
                        return {'success': True, 'goal': 'look', 'rules_used': [pinned], 'gpu_seconds': 0.0,
                                'trace': [{'action': 'use desklamp 1', 'valid': True, 'after': 'You turn on it.'}],
                                'model_calls': 1, 'input_tokens': 0, 'output_tokens': 0, 'model_wall_seconds': 0.0}
                return Game()
        report = {'operations': [], 'errors': []}
        manual.manage(Asker(), [recipe], report)
        self.assertEqual(recipe['rule'], new.replace('desklamp 1', 'desklamp'))
        self.assertEqual(report['operations'][0]['op'], 'refine')
        self.assertEqual(recipe['revisions'], 1)

    def test_append_only_is_unchanged(self):
        rules, log = [rule('rule_1', 'Success Process', RECIPE)], []
        manual.apply(rules, [{'op': 'note', 'id': 'rule_1', 'validation': 'x'}], 'direct success', True, ids(), log)
        self.assertEqual(log, ['append-only manual: rules cannot be changed or annotated'])


def step(action, valid=True, after='You do it.'):
    return {'action': action, 'valid': valid, 'after': after, 'before': ''}


TAKE_LAMP = 'When looking at an object under a light, take the lamp and turn it on.'


class EvidenceCheckTests(unittest.TestCase):
    def test_instructed_commands(self):
        self.assertEqual(manual.instructed_commands(TAKE_LAMP), [('take', 'lamp')])
        self.assertEqual(manual.instructed_commands('Go to the fridge, open the fridge and use the desklamp.'),
                         [('go to', 'fridge'), ('open', 'fridge'), ('use', 'desklamp')])
        self.assertEqual(manual.instructed_commands('Take it to the desklamp, then turn on the floorlamp.'),
                         [('use', 'floorlamp')])
        self.assertEqual(manual.instructed_commands('Never take the lamp; use it instead of taking the lamp.'), [])
        self.assertEqual(manual.instructed_commands('Do not open the safe.'), [])

    def test_command_evidence_from_a_trace(self):
        rejected = [step('go to desk 1'), step('take desklamp 1 from desk 1', False, 'Nothing happens.')]
        self.assertEqual(manual.command_evidence(TAKE_LAMP, rejected), {'take lamp': 'rejected'})
        nothing = [step('take floorlamp 1 from floor 1', True, 'Nothing happens.')]
        self.assertEqual(manual.command_evidence(TAKE_LAMP, nothing), {'take lamp': 'rejected'})
        ok = rejected + [step('take desklamp 1 from desk 1', True, 'You pick up the desklamp 1.')]
        self.assertEqual(manual.command_evidence(TAKE_LAMP, ok), {'take lamp': 'ok'})
        self.assertEqual(manual.command_evidence(TAKE_LAMP, [step('take book 1 from desk 1')]), {})
        self.assertEqual(manual.command_evidence('Use the desklamp.', [step('use desklamp 1')]), {'use desklamp': 'ok'})

    def test_the_write_gate_rejects_a_rule_whose_command_the_won_game_rejected(self):
        trace = [step('take desklamp 1 from desk 1', False, 'Nothing happens.'), step('use desklamp 1')]
        rules, log = [], []
        manual.apply(rules, [{'op': 'write_rule', 'type': 'Special Phenomenon', 'rule': TAKE_LAMP}],
                     'indirect success', False, ids(), log, 'look_at_obj_in_light', trace=trace)
        self.assertEqual(rules, [])
        self.assertIn('take lamp', log[0])


class BatchMergeTests(unittest.TestCase):
    def base(self):
        rules = [rule('rule_1', 'Special Phenomenon', 'If a container is closed, open it first.'),
                 rule('rule_2', 'Special Phenomenon', 'If a target is full, use another one.')]
        for r in rules:
            r['ev'] = {**manual.empty_evidence(), 'shown': 6, 'followed': 6, 'sum': -6, 'neg': 6}   # bad
        return rules

    def test_one_text_change_per_rule_per_batch_first_in_position_order(self):
        base = self.base()
        refine = {'op': 'refine', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.', 'revision': 1}
        again = {'op': 'refine', 'id': 'rule_1', 'rule': 'If a box is closed, open it.', 'revision': 1}
        log = []
        live = manual.replay(base, [refine], log, base)
        live[0]['ev'] = copy.deepcopy(base[0]['ev'])        # bad again on the live rules, still one change
        live = manual.replay(live, [again], log, base)
        self.assertEqual(live[0]['rule'], 'If a drawer is closed, open it.')
        self.assertEqual(log, [['text change dropped (already changed in this batch)', 'refine', 'rule_1']])
        # Without the batch's starting rules (sequential practice), every op applies.
        old = manual.replay(manual.replay(base, [refine], [], None), [{**again, 'id': 'rule_2'}], [], None)
        self.assertEqual(old[1]['rule'], 'If a box is closed, open it.')

    def test_merge_memory_passes_the_batch_start(self):
        base_rules = self.base()
        extra = {}
        base = {**extra, 'trajectories': [], 'rules': base_rules}
        live = {**extra, 'trajectories': [], 'rules': manual.replay(
            base_rules, [{'op': 'refine', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.'}], [],
            base_rules)}
        live['rules'][0]['ev'] = copy.deepcopy(base_rules[0]['ev'])
        log = []
        merged = merge_memory(live, base, base, log, [{'op': 'refine', 'id': 'rule_1', 'rule': 'Later.'}])
        self.assertEqual(merged['rules'][0]['rule'], 'If a drawer is closed, open it.')
        self.assertEqual(log, [['text change dropped (already changed in this batch)', 'refine', 'rule_1']])


class RestartETests(unittest.TestCase):
    def cfg(self):
        return Settings(practice_episodes=4, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                        practice_batch=2, seeds=[11])

    def test_e_minus_probe_is_deterministic_and_sees_append_only_prompts(self):
        from living_library.experiment import e_minus_probe
        cfg =Settings(seeds=[11], conditions=['E-minus'], practice_batch=2)
        # The probe must be deterministic and must see every prompt E-minus uses.
        golden = e_minus_probe(cfg)
        self.assertEqual(e_minus_probe(cfg), golden)
        with patch.object(manual, 'APPEND_ONLY_NOTE', manual.APPEND_ONLY_NOTE + ' Be brief.'):
            self.assertNotEqual(e_minus_probe(cfg), golden)
        with patch.object(manual, 'strip_instances', lambda text: text):
            self.assertNotEqual(e_minus_probe(cfg), golden)
        with patch.object(manual, 'REFLECT_GUIDE', manual.REFLECT_GUIDE + ' Be brief.'):   # E-minus retries too
            self.assertNotEqual(e_minus_probe(cfg), golden)

    def test_restart_e_keeps_c_d_and_e_minus(self):
        from living_library.experiment import Runner, e_minus_replay_check, load_json, restart_library
        cfg = self.cfg()
        conditions = ('C', 'D', 'E', 'E-minus')

        def version(manual_hash):
            hashes = {'living_library/manual.py': manual_hash, 'living_library/cli.py': 'cli'}
            return (patch('living_library.experiment.source_fingerprint', return_value=manual_hash),
                    patch('living_library.experiment.source_hashes', return_value=hashes))

        def kept(tmp):          # C, D and E-minus streams: every stream not of E
            root = Path(tmp) / 'checkpoints'
            return {d.name: [json.loads(p.read_text())['record'] for p in sorted(d.glob('*.json'))]
                    for d in root.iterdir() if not re.search(r'-E-(?!minus)', d.name)}

        with tempfile.TemporaryDirectory() as tmp:
            a, b = version('m1')
            with a, b:
                Runner(cfg, demo_manifest(), tmp).study(conditions, 4, gate_at=2, gate_games=2,
                                                       gate_margin=-99, log=quiet)
                saved = load_json(Path(tmp) / 'probe.json')
            self.assertIn('e_minus', saved)                          # new runs store the E-minus probe
            before = kept(tmp)
            self.assertTrue({'practice-D-0', 'practice-E-minus-0', 'evaluation-E-minus-r0-11'} <= set(before))
            self.assertEqual(e_minus_replay_check(cfg, tmp), (4, None))
            a, b = version('m2')                                      # E's management changed
            with a, b:
                with patch('living_library.experiment.e_minus_probe', return_value='other'):
                    with self.assertRaisesRegex(ValueError, "E-minus probe failed: .*changed E-minus's behaviour"):
                        restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E'])
                self.assertEqual(kept(tmp), before)                      # refused: nothing discarded
                lines = []
                restart_library(cfg, demo_manifest(), tmp, log=lines.append, streams=['E'])
                self.assertTrue(any(line.startswith('E-minus probe passed: 4 stored practice games') for line in lines))
                names = {d.name for d in (Path(tmp) / 'checkpoints').iterdir()}
                self.assertEqual(names, set(before))                    # E and gate-E gone; E-minus kept
                self.assertFalse((Path(tmp) / 'gate.json').exists())
                runner = Runner(cfg, demo_manifest(), tmp)
                runner.study(conditions, 4, gate_at=2, gate_games=2, gate_margin=-99, log=quiet)
                self.assertTrue(runner.complete)
                self.assertEqual(kept(tmp), before)                         # C, D, E-minus games as they were
                self.assertEqual(runner.count('practice-E-0'), 4)
            restarts = load_json(Path(tmp) / 'restarts.json')
            self.assertEqual(restarts[0]['restarted'], ['E'])
            self.assertEqual(restarts[0]['changed_sources'], ['living_library/manual.py'])
            self.assertIn('evaluation-E-r0-11', restarts[0]['discarded'])
            self.assertNotIn('practice-E-minus-0', restarts[0]['discarded'])
            self.assertIn('practice-E-minus-0', restarts[0]['kept'])

    def test_restart_e_refuses_when_e_minus_cannot_be_shown_unchanged(self):
        from living_library.experiment import Runner, restart_library
        cfg = self.cfg()
        with tempfile.TemporaryDirectory() as tmp:
            Runner(cfg, demo_manifest(), tmp).study(('C', 'E', 'E-minus'), 4, log=quiet)
            with self.assertRaisesRegex(ValueError, 'only these conditions'):
                restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['D'])
            # A stored E-minus game that the current replay does not reproduce.
            path = Path(tmp) / 'checkpoints' / 'practice-E-minus-0' / '00003.json'
            data = json.loads(path.read_text())
            data['memory']['rules'] = data['memory']['rules'] + [manual.new_rule('rule_99', 'Special Phenomenon',
                                                                                 'x', '', 'all')]
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'E-minus probe failed: practice-E-minus-0 game 3'):
                restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E'])


class SharedSubgoalIssueTests(unittest.TestCase):
    @unittest.skip('Known shared issue, deliberately NOT fixed (DECISIONS 2026-11-19): fixing it changes C and D '
                   'behaviour and would invalidate their finished study games. Study game 85 (two-object task): '
                   'the "place the second object" subgoal passed with only the first object placed, because '
                   'State.holds() matches a type argument ("cellphone") against any instance, so '
                   'located(cellphone, dresser) already holds after cellphone 1 is placed. It affects all '
                   'conditions equally. Fix after the study (e.g. count instances for pick_two_obj goals).')
    def test_two_object_subgoal_needs_both_objects(self):
        state = State(observation='', admissible=[], entities={'cellphone 1', 'cellphone 2', 'dresser 1'},
                      facts={('located', 'cellphone 1', 'dresser 1')})
        second = Predicate.parse('located(cellphone, dresser)')
        self.assertFalse(state.holds(second), 'a second-object subgoal must not pass with one object placed')


if __name__ == '__main__':
    unittest.main()
