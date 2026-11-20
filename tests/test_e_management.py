"""E's rule management after the recipe-drift diagnosis (2026-11-19): recipe stability, the evidence check
of instructed commands against game traces, one text change per rule per batch, the E-only restart with
its E-minus probe, and the shared two-object subgoal issue (recorded, not fixed)."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from living_library import avoid, manual
from living_library.batching import merge_memory
from living_library.config import Settings, digest
from living_library.domain import Predicate, State
from living_library.environments import demo_manifest
from living_library.experiment import (Runner, e_minus_probe, e_minus_replay_check, load_json, restart_library,
                                       stored_e_minus_probe)

ROOT = Path(__file__).resolve().parent.parent
STUDY = Path('/root/ll-runs/study')


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
    def test_builder_cannot_rewrite_a_verified_recipe(self):
        rules, log = [rule('rule_1', 'Success Process', RECIPE)], []
        applied = manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1',
                                        'rule': 'When an object must be examined: search shelves first, take it, '
                                                'use the desklamp.', 'example': 'go to shelf 1'}],
                               'direct success', False, ids(), log)
        self.assertEqual(rules[0]['rule'], RECIPE)
        self.assertEqual(applied, [])
        self.assertIn('rule_1 keeps its text (a verified Success Process changes only by contrastive refinement)', log)
        # A validation note is still allowed (and counts as agreement).
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'x', 'validation': 'confirmed again'}],
                     'indirect success', False, ids(), log)
        self.assertEqual((rules[0]['rule'], rules[0]['validation']), (RECIPE, 'confirmed again'))
        self.assertEqual(rules[0]['importance'], manual.NEW_IMPORTANCE + 1)

    def test_recipe_text_changes_through_refinement(self):
        recipe = rule('rule_1', 'Success Process', RECIPE, alpha=1 + manual.MIN_CONTRAST,
                      beta=1 + manual.MIN_CONTRAST,
                      contexts=[{'task': 'look', 'won': w} for w in [True, False] * manual.MIN_CONTRAST])
        new = 'When an object must be examined under a light: search desks first, take it, use the lamp.'

        class Agent:
            def _ask(self, role, payload):
                return {'rule': new}
        report = {'operations': [], 'errors': []}
        manual.refine(Agent(), [recipe], [recipe], report)
        self.assertEqual(recipe['rule'], new)
        self.assertEqual(report['operations'][0]['op'], 'refine')
        fresh = rule('rule_2', 'Success Process', RECIPE, alpha=3, beta=1 + manual.MIN_CONTRAST)   # 2 wins only
        self.assertFalse(manual.refinable(fresh))

    def test_corrected_failure_writes_but_does_not_rewrite_visible_rules(self):
        tip = rule('rule_1', 'Special Phenomenon', 'If a container is closed, open it before looking inside.')
        note = rule('rule_2', 'Unresolved Error', 'When the lamp was off, the task failed.')
        rules, log = [tip, note], []
        manual.apply(rules, [
            {'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it first.'},
            {'op': 'update_rule', 'id': 'rule_2', 'type': 'Corrected Error',
             'rule': 'When the lamp is off, use it instead of taking it.'},
            {'op': 'write_rule', 'type': 'Corrected Error', 'rule': 'When a target is full, use another one.'}],
            'corrected failure', False, ids(), log)
        self.assertEqual(tip['rule'], 'If a container is closed, open it before looking inside.')
        self.assertTrue(any('rule_1 keeps its text (a corrected failure' in line for line in log))
        self.assertEqual(note['type'], 'Corrected Error')          # a hidden note may still become a rule
        self.assertEqual(len(rules), 3)

    def test_other_visible_rules_still_update_after_a_won_game(self):
        tip = rule('rule_1', 'Special Phenomenon', 'If a container is closed, open it before looking inside.')
        manual.apply([tip], [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it first.'}],
                     'direct success', False, ids(), [])
        self.assertEqual(tip['rule'], 'If a drawer is closed, open it first.')

    def test_append_only_is_unchanged(self):
        rules, log = [rule('rule_1', 'Success Process', RECIPE)], []
        manual.apply(rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'x'}], 'direct success', True, ids(), log)
        self.assertEqual(log, ['append-only manual: rules cannot be changed'])


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

    def game(self, rules, won, trace, followed=('rule_1',), position=0):
        return manual.observe(rules, ['rule_1'], won, {'task': 'look at book under the desklamp',
                                                      'task_type': 'look_at_obj_in_light'},
                              position, followed=list(followed), trace=trace)

    def test_rule_whose_command_is_always_rejected_is_retired(self):
        rules = [rule('rule_1', 'Special Phenomenon', TAKE_LAMP)]
        bad = [step('take desklamp 1 from desk 1', False, 'Nothing happens.'), step('use desklamp 1')]
        first = self.game(rules, True, bad)
        self.assertEqual(first['commands'], {'rule_1': {'take lamp': 'rejected'}})
        report = {'operations': [], 'errors': []}
        manual.retire(rules, report)
        self.assertEqual(len(rules), 1)                                  # one rejection is not enough
        self.game(rules, False, bad, position=1)
        self.assertEqual(rules[0]['commands'], {'take lamp': [2, 0]})
        manual.retire(rules, report)
        self.assertEqual(rules, [])
        self.assertEqual(report['errors'], ['retired rule_1 (instructed command always rejected: take lamp)'])
        self.assertEqual(report['operations'][0]['reason'], 'instructed command always rejected: take lamp')

    def test_command_accepted_in_a_won_game_keeps_the_rule(self):
        rules = [rule('rule_1', 'Special Phenomenon', TAKE_LAMP)]
        bad = [step('take desklamp 1 from desk 1', False, 'Nothing happens.')]
        self.game(rules, True, [step('take desklamp 1 from desk 1', True, 'You pick up the desklamp 1.')])
        self.game(rules, False, bad, position=1)
        self.game(rules, False, bad, position=2)
        self.assertEqual(rules[0]['commands'], {'take lamp': [2, 1]})
        self.assertIsNone(manual.rejected_command(rules[0]))

    def test_only_followed_rules_and_not_anti_patterns(self):
        bad = [step('take desklamp 1 from desk 1', False, 'Nothing happens.')]
        rules = [rule('rule_1', 'Special Phenomenon', TAKE_LAMP)]
        for position in range(3):
            op = self.game(rules, False, bad, followed=(), position=position)
            self.assertNotIn('commands', op)
        self.assertNotIn('commands', rules[0])
        none = manual.observe(rules, ['rule_1'], False, {'task': 'x', 'task_type': 'look_at_obj_in_light'}, 3,
                              followed=None, trace=bad)                  # judge failed: no evidence
        self.assertNotIn('commands', none)
        anti = [rule('rule_1', avoid.TYPE, 'Never take the lamp; take the lamp is rejected.')]
        self.assertNotIn('commands', self.game(anti, False, bad))
        self.assertIsNone(manual.rejected_command({**anti[0], 'commands': {'take lamp': [5, 0]}}))

    def test_replayed_outcome_counts_commands(self):
        rules = [rule('rule_1', 'Special Phenomenon', TAKE_LAMP)]
        live = copy.deepcopy(rules)
        op = self.game(rules, False, [step('take desklamp 1 from desk 1', False, 'Nothing happens.')])
        self.assertEqual(manual.replay(live, [op], [], copy.deepcopy(live)), rules)


class BatchMergeTests(unittest.TestCase):
    def base(self):
        return [rule('rule_1', 'Special Phenomenon', 'If a container is closed, open it first.'),
                rule('rule_2', 'Special Phenomenon', 'If a target is full, use another one.')]

    def test_first_text_change_in_position_order_wins(self):
        base = self.base()
        first = [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it first.'}]
        second = [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a cabinet is closed, open it first.',
                   'validation': 'seen again'},
                  {'op': 'update_rule', 'id': 'rule_2', 'rule': 'If a shelf is full, use another one.'}]
        log = []
        live = manual.replay(base, first, log, base)
        live = manual.replay(live, second, log, base)
        self.assertEqual(live[0]['rule'], 'If a drawer is closed, open it first.')
        self.assertEqual(live[0]['validation'], 'seen again')            # the rest of the update still applies
        self.assertEqual(live[1]['rule'], 'If a shelf is full, use another one.')
        self.assertEqual(log, [['text change dropped (already changed in this batch)', 'update_rule', 'rule_1']])
        # Without the batch's starting rules (the old replay), the last edit won.
        old = manual.replay(manual.replay(base, first, [], None), second, [], None)
        self.assertEqual(old[0]['rule'], 'If a cabinet is closed, open it first.')

    def test_one_refine_or_consolidate_per_rule_per_batch(self):
        base = self.base()
        refine = {'op': 'refine', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.', 'refined_at': [3, 3]}
        again = {'op': 'refine', 'id': 'rule_1', 'rule': 'If a box is closed, open it.', 'refined_at': [3, 3]}
        fold = {'op': 'consolidate', 'id': 'rule_1', 'absorbed': ['rule_2'], 'rule': 'If closed, open it.',
                'old_rule': '', 'absorbed_rules': []}
        log = []
        live = manual.replay(base, [refine], log, base)
        live = manual.replay(live, [again], log, base)
        live = manual.replay(live, [fold], log, base)
        self.assertEqual(live[0]['rule'], 'If a drawer is closed, open it.')
        self.assertEqual(len(live), 2)
        self.assertEqual([entry[1] for entry in log], ['refine', 'consolidate'])
        within = manual.replay(base, [{'op': 'update_rule', 'id': 'rule_2', 'rule': 'If a shelf is full, skip it.'},
                                      {'op': 'refine', 'id': 'rule_2', 'rule': 'Other.', 'refined_at': [3, 3]}],
                               [], base)                                 # also within one game
        self.assertEqual(within[1]['rule'], 'If a shelf is full, skip it.')

    def test_merge_memory_passes_the_batch_start(self):
        base_rules = self.base()
        empty = {'skills': [], 'active': {}}
        base = {'library': empty, 'trajectories': [], 'rules': base_rules}
        live = {'library': empty, 'trajectories': [], 'rules': manual.replay(
            base_rules, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'If a drawer is closed, open it.'}], [],
            base_rules)}
        log = []
        merged = merge_memory(live, base, base, log, [{'op': 'update_rule', 'id': 'rule_1', 'rule': 'Later.'}])
        self.assertEqual(merged['rules'][0]['rule'], 'If a drawer is closed, open it.')
        self.assertEqual(log, [['text change dropped (already changed in this batch)', 'update_rule', 'rule_1']])


class RestartETests(unittest.TestCase):
    def cfg(self):
        return Settings(practice_episodes=4, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                        practice_batch=2, seeds=[11])

    def test_e_minus_probe_is_deterministic_and_sees_append_only_prompts(self):
        cfg = Settings(seeds=[11], conditions=['E-minus'], practice_batch=2)
        # Golden digest taken with the code the study ran (7da1ecf, before this change): E-minus unchanged.
        self.assertEqual(e_minus_probe(cfg), '6617ccc62328f7611004fd2908d64beeefd80cc5e4af6de5b12fa48acf62545a')
        with patch.object(manual, 'APPEND_ONLY_NOTE', manual.APPEND_ONLY_NOTE + ' Be brief.'):
            self.assertNotEqual(e_minus_probe(cfg), '6617ccc62328f7611004fd2908d64beeefd80cc5e4af6de5b12fa48acf62545a')

    def test_probe_tool_measures_a_tree_with_the_current_probe(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        try:
            import e_minus_probe as tool
        finally:
            sys.path.remove(str(ROOT / 'tools'))
        cfg = Settings(seeds=[11], conditions=['E-minus'])
        found = tool.probe_tree(ROOT, cfg)
        self.assertEqual(found['probe'], e_minus_probe(cfg))
        self.assertEqual(found['settings'], digest(cfg.to_dict()))

    def test_restart_e_keeps_c_d_and_e_minus(self):
        cfg = self.cfg()
        conditions = ('C', 'D', 'E', 'E-minus', 'E-text')

        def version(manual_hash):
            hashes = {'living_library/manual.py': manual_hash, 'living_library/cli.py': 'cli'}
            return (patch('living_library.experiment.source_fingerprint', return_value=manual_hash),
                    patch('living_library.experiment.source_hashes', return_value=hashes))

        def kept(tmp):          # C, D and E-minus streams: every stream not of E or E-text
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
            self.assertTrue({'practice-D-0', 'practice-E-minus-0', 'evaluation-E-minus-11'} <= set(before))
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
                self.assertEqual(names, set(before))                    # E, E-text, gate-E gone; E-minus kept
                self.assertFalse((Path(tmp) / 'gate.json').exists())
                runner = Runner(cfg, demo_manifest(), tmp)
                runner.study(conditions, 4, gate_at=2, gate_games=2, gate_margin=-99, log=quiet)
                self.assertTrue(runner.complete)
                self.assertEqual(kept(tmp), before)                         # C, D, E-minus games as they were
                self.assertEqual(runner.count('practice-E-0'), 4)
            restarts = load_json(Path(tmp) / 'restarts.json')
            self.assertEqual(restarts[0]['restarted'], ['E'])
            self.assertEqual(restarts[0]['changed_sources'], ['living_library/manual.py'])
            self.assertIn('evaluation-E-text-11', restarts[0]['discarded'])
            self.assertNotIn('practice-E-minus-0', restarts[0]['discarded'])
            self.assertIn('practice-E-minus-0', restarts[0]['kept'])

    def test_restart_e_refuses_when_e_minus_cannot_be_shown_unchanged(self):
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
            original = path.read_text()
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'E-minus probe failed: practice-E-minus-0 game 3'):
                restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E'])
            path.write_text(original)
            # Sources changed and no E-minus probe recorded for the run's sources.
            probe = load_json(Path(tmp) / 'probe.json')
            (Path(tmp) / 'probe.json').write_text(json.dumps({k: v for k, v in probe.items() if k != 'e_minus'}))
            run = load_json(Path(tmp) / 'run.json')
            with patch('living_library.experiment.source_fingerprint', return_value='new'), \
                    patch('living_library.experiment.source_hashes',
                          return_value={**load_json(Path(tmp) / 'sources.json'), 'living_library/manual.py': 'new'}), \
                    patch('living_library.experiment.E_MINUS_PROBES', Path(tmp) / 'none'):
                with self.assertRaisesRegex(ValueError, 'no E-minus probe for its recorded sources'):
                    restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E'])
            self.assertEqual(load_json(Path(tmp) / 'run.json'), run)

    def test_reference_probe_file_is_found(self):
        cfg = self.cfg()
        recorded = {'living_library/manual.py': 'old'}
        with tempfile.TemporaryDirectory() as tmp:
            probes = Path(tmp) / 'probes'
            probes.mkdir()
            (probes / 'e-minus-x.json').write_text(json.dumps(
                {'sources': digest(recorded), 'settings': digest(cfg.to_dict()), 'probe': 'p'}))
            with patch('living_library.experiment.E_MINUS_PROBES', probes):
                self.assertEqual(stored_e_minus_probe(cfg, tmp, recorded), 'p')
                self.assertIsNone(stored_e_minus_probe(cfg, tmp, {'other': 'x'}))

    @unittest.skipUnless((STUDY / 'sources.json').exists(), 'the study run is not on this machine')
    def test_study_e_minus_unchanged(self):
        """The paused study's E-minus practice replays exactly under the current code, and the current code's
        E-minus fixture probe equals the one taken with the code the study recorded (read only)."""
        cfg = Settings.load(ROOT / 'configs' / 'pilot.json')
        games, problem = e_minus_replay_check(cfg, STUDY)
        self.assertIsNone(problem)
        self.assertGreater(games, 0)
        stored = stored_e_minus_probe(cfg, STUDY, load_json(STUDY / 'sources.json'))
        if stored is None:
            self.skipTest('no E-minus probe recorded for the study sources')
        self.assertEqual(e_minus_probe(cfg), stored)


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
