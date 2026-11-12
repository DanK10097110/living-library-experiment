import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from living_library.config import Settings
from living_library.environments import demo_manifest
from living_library.experiment import Runner, freeze, ordered, pilot_gate, verify_freeze
from living_library.models import FixtureModel


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

    def test_order_is_seeded_without_mutating_manifest(self):
        tasks = demo_manifest()['splits']['evaluation']
        before = list(tasks)
        self.assertEqual(ordered(tasks, 11), ordered(tasks, 11))
        self.assertEqual(tasks, before)
        with self.assertRaises(ValueError):
            ordered(tasks, 11, 7)


if __name__ == '__main__':
    unittest.main()
