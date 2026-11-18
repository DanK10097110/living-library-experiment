import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from living_library.config import Settings
from living_library.environments import demo_manifest
from living_library.experiment import (Runner, baseline_probe, freeze, gate_decision, ordered, pilot_gate,
                                       restart_library, verify_freeze)
from living_library.models import FixtureModel


def quiet(*args, **kwargs):
    pass


class ExperimentTests(unittest.TestCase):
    def cfg(self):
        return Settings(practice_episodes=2, evaluation_games=2, step_budget=15,
                        bootstrap_samples=20)

    def test_practice_shared_snapshots_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(self.cfg(), demo_manifest(), tmp)
            records = runner.study(('D', 'E', 'E-text'), demo_count=2)
            self.assertEqual(len([r for r in records if r['phase'] == 'practice']), 4)
            self.assertEqual(len([r for r in records if r['phase'] == 'evaluation']), 18)
            for seed in self.cfg().seeds:
                e = sorted((Path(tmp)/'checkpoints'/f'evaluation-E-{seed}').glob('*.json'))
                text = sorted((Path(tmp)/'checkpoints'/f'evaluation-E-text-{seed}').glob('*.json'))
                for ep, tp in zip(e, text):
                    a, b = json.loads(ep.read_text()), json.loads(tp.read_text())
                    self.assertEqual(a['pre_library'], b['pre_library'])
                    self.assertEqual(b['pre_library'], b['memory']['library'])
                    self.assertEqual(a['record']['task_id'], b['record']['task_id'])
            with patch.object(FixtureModel, 'complete', side_effect=AssertionError('resume called model')):
                resumed = Runner(self.cfg(), demo_manifest(), tmp).study(('D', 'E', 'E-text'), 2)
            self.assertEqual(records, resumed)

    def test_changed_config_and_checkpoint_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2)
            cfg = self.cfg(); cfg.top_k = 8
            with self.assertRaisesRegex(ValueError, 'different settings'):
                Runner(cfg, demo_manifest(), tmp)
            path = next((Path(tmp)/'checkpoints').rglob('00000.json'))
            data = json.loads(path.read_text()); data['record']['success'] = not data['record']['success']
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'corrupt checkpoint'):
                Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2)

    def test_no_fixture_freeze_or_real_sample_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'ALFWorld'):
                freeze(self.cfg(), demo_manifest(), tmp, Path(tmp)/'freeze.json')
            with self.assertRaisesRegex(ValueError, 'ALFWorld'):
                verify_freeze(self.cfg(), demo_manifest(), Path(tmp)/'missing.json')
            self.assertFalse(pilot_gate([], self.cfg())['passed'])

    def test_extending_conditions_preserves_prior_records_and_blocks_mixing(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Runner(self.cfg(), demo_manifest(), tmp).study(('A',), 2)
            all_records = Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(all_records), 8)
            self.assertEqual(sum(r['condition'] == 'A' for r in all_records), 2)
            with self.assertRaisesRegex(ValueError, 'separate output'):
                Runner(self.cfg(), demo_manifest(), tmp).pilot()

    def test_gate_decision(self):
        def rows(wins):
            return [{'task_id': f't{i}', 'success': w} for i, w in enumerate(wins)]
        practice = [{'manual': {'errors': ['builder: bad json', 'refiner: x']}}, {'manual': {'errors': []}}, {}]
        gate = gate_decision(rows([1, 1, 0, 0]), rows([1, 0, 1, 0]), [{}, {}, {}], practice)
        self.assertEqual((gate['E_wins'], gate['C_wins'], gate['paired_games']), (2, 2, 4))
        self.assertEqual((gate['E_won_C_lost'], gate['C_won_E_lost']), (1, 1))
        self.assertEqual((gate['rule_count'], gate['builder_errors'], gate['manual_errors']), (3, 1, 2))
        self.assertTrue(gate['passed'])                                       # a tie passes by default
        self.assertFalse(gate_decision(rows([1, 1, 0, 0]), rows([1, 0, 1, 0]), [], [], margin=1)['passed'])
        self.assertFalse(gate_decision(rows([0, 0]), rows([1, 0]), [], [])['passed'])
        self.assertFalse(gate_decision([], [], [], [])['passed'])           # no evidence never passes
        # only paired games count
        self.assertEqual(gate_decision(rows([1, 1, 1]), rows([0])[:1], [], [])['paired_games'], 1)

    def test_early_gate_stops_then_continues_from_checkpoint(self):
        cfg = Settings(practice_episodes=4, evaluation_games=2, step_budget=15, bootstrap_samples=20)
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp)
            runner.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, gate_margin=99, log=quiet)
            self.assertFalse(runner.complete)
            self.assertFalse(runner.gate['passed'])
            gate = json.loads((Path(tmp) / 'gate.json').read_text())
            for field in ('E_wins', 'C_wins', 'E_won_C_lost', 'C_won_E_lost', 'rule_count', 'builder_errors'):
                self.assertIn(field, gate)
            self.assertEqual(gate['paired_games'], 2)
            self.assertEqual(runner.count('practice-E-0'), 2)              # stopped at the checkpoint
            self.assertFalse((Path(tmp) / 'checkpoints' / 'evaluation-C-11').exists())
            first = (Path(tmp) / 'checkpoints' / 'practice-E-0' / '00001.json').read_text()
            again = Runner(cfg, demo_manifest(), tmp)                       # rerun: still stopped
            again.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, gate_margin=99, log=quiet)
            self.assertFalse(again.complete)
            go = Runner(cfg, demo_manifest(), tmp)
            records = go.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, past_gate=True, log=quiet)
            self.assertTrue(go.complete)
            self.assertEqual(first, (Path(tmp) / 'checkpoints' / 'practice-E-0' / '00001.json').read_text())
            self.assertEqual(sum(r['phase'] == 'practice' for r in records), 4)
            self.assertTrue(json.loads((Path(tmp) / 'gate.json').read_text())['continued'])
        with tempfile.TemporaryDirectory() as tmp:                         # a passing gate runs straight on
            runner = Runner(cfg, demo_manifest(), tmp)
            runner.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, gate_margin=-99, log=quiet)
            self.assertTrue(runner.complete and runner.gate['passed'])

    def test_restart_library_keeps_c_and_d(self):
        cfg = self.cfg()
        conditions = ('C', 'D', 'E', 'E-text')

        def version(manual, agents):
            hashes = {'living_library/manual.py': manual, 'living_library/agents.py': agents}
            return (patch('living_library.experiment.source_fingerprint', return_value=manual + agents),
                    patch('living_library.experiment.source_hashes', return_value=hashes))

        def kept(tmp):
            root = Path(tmp) / 'checkpoints'
            return {d.name: [json.loads(p.read_text())['record'] for p in sorted(d.glob('*.json'))]
                    for d in root.iterdir() if '-E' not in d.name}

        with tempfile.TemporaryDirectory() as tmp:
            a, b = version('m1', 'a1')
            with a, b:
                Runner(cfg, demo_manifest(), tmp).study(conditions, 2, gate_at=1, gate_games=2,
                                                       gate_margin=-99, log=quiet)
            before = kept(tmp)
            self.assertTrue({'practice-D-0', 'gate-C-11', 'evaluation-C-11', 'evaluation-D-11'} <= set(before))
            a, b = version('m2', 'a1')                                      # only the manual changed
            with a, b:
                with self.assertRaisesRegex(ValueError, 'different settings'):
                    Runner(cfg, demo_manifest(), tmp)
                restart_library(cfg, demo_manifest(), tmp, log=quiet)
                names = {d.name for d in (Path(tmp) / 'checkpoints').iterdir()}
                self.assertEqual(names, set(before))                        # E, E-text, gate-E gone
                self.assertFalse((Path(tmp) / 'gate.json').exists())
                runner = Runner(cfg, demo_manifest(), tmp)
                runner.study(conditions, 2, gate_at=1, gate_games=2, gate_margin=-99, log=quiet)
                self.assertTrue(runner.complete)
                self.assertEqual(kept(tmp), before)                         # C and D games kept as they were
                self.assertEqual(runner.count('practice-E-0'), 2)
            restarts = json.loads((Path(tmp) / 'restarts.json').read_text())
            self.assertEqual(restarts[0]['changed_sources'], ['living_library/manual.py'])
            self.assertIn('practice-E-0', restarts[0]['discarded'])
            self.assertIn('evaluation-E-text-11', restarts[0]['discarded'])
            a, b = version('m3', 'a2')                       # agent code changed, C/D behaviour did not
            with a, b, patch('living_library.experiment.baseline_probe', return_value='other'):
                with self.assertRaisesRegex(ValueError, "changed C's or D's behaviour"):
                    restart_library(cfg, demo_manifest(), tmp, log=quiet)
            with a, b:
                restart_library(cfg, demo_manifest(), tmp, log=quiet)      # same probe: C and D kept
                self.assertEqual(kept(tmp), before)
            self.assertEqual(json.loads((Path(tmp) / 'restarts.json').read_text())[-1]['changed_sources'],
                             ['living_library/agents.py', 'living_library/manual.py'])
            hashes = {'living_library/manual.py': 'm3', 'living_library/agents.py': 'a2', 'living_library/react.py': 'r'}
            with patch('living_library.experiment.source_fingerprint', return_value='m3a2r'), \
                    patch('living_library.experiment.source_hashes', return_value=hashes):
                with self.assertRaisesRegex(ValueError, 'outside the library'):
                    restart_library(cfg, demo_manifest(), tmp, log=quiet)
            (Path(tmp) / 'probe.json').unlink()                              # no probe: refuse
            a, b = version('m3', 'a3')
            with a, b:
                with self.assertRaisesRegex(ValueError, 'no C/D probe'):
                    restart_library(cfg, demo_manifest(), tmp, log=quiet)

    def test_c_and_d_behaviour_unchanged_by_practice_retries(self):
        # Golden digest of every model request and record of a fixture C and D study, taken with the
        # code before practice retries were added (2026-11-17). If this fails, C or D changed.
        cfg = Settings(seeds=[11], conditions=['C', 'D'])
        self.assertEqual(baseline_probe(cfg), '2ec5b588e620f73ab06d34576c864ee310ed0723380d8c1e8e9493fad73cc3b5')
        self.assertEqual(baseline_probe(cfg), baseline_probe(cfg))                    # deterministic

    def test_order_is_seeded_without_mutating_manifest(self):
        tasks = demo_manifest()['splits']['evaluation']
        before = list(tasks)
        self.assertEqual(ordered(tasks, 11), ordered(tasks, 11))
        self.assertEqual(tasks, before)
        with self.assertRaises(ValueError):
            ordered(tasks, 11, 7)


if __name__ == '__main__':
    unittest.main()
