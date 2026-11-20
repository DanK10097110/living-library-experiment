import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import compare_snapshots  # noqa: E402
import snapshot_eval  # noqa: E402
from living_library.config import Settings  # noqa: E402
from living_library.environments import demo_manifest  # noqa: E402
from living_library.experiment import Runner  # noqa: E402


class SnapshotEvalTest(unittest.TestCase):
    def test_toy_snapshots_match_study_and_compare(self):
        cfg = Settings(practice_episodes=4, evaluation_games=4, development_games=3, step_budget=15, bootstrap_samples=20,
                       conditions=['C', 'E'])
        with tempfile.TemporaryDirectory() as tmp:
            study, manifest = Path(tmp) / 'study', demo_manifest()
            Runner(cfg, manifest, study).study(('C', 'E'), demo_count=4)
            with self.assertRaisesRegex(ValueError, 'need 5'):
                snapshot_eval.prepare(study, 5, ['ood'], Path(tmp) / 'x', manifest, probe=False)
            outs = {}
            for n in (2, 4):
                out = outs[n] = Path(tmp) / f'snap-{n}'
                runner, specs, tests = snapshot_eval.prepare(study, n, ['ood', 'id'], out, manifest, probe=False)
                self.assertTrue(runner.execute(specs, workers=1, log=lambda *a: None))
            # the 4-game snapshot is the study's own final evaluation, game by game
            snap = compare_snapshots.stream_results(outs[4], 'evaluation-E-r0-11')
            self.assertEqual(snap, compare_snapshots.stream_results(study, 'evaluation-E-r0-11'))
            self.assertEqual(len(snap), 4)
            md = Path(tmp) / 'out.md'
            compare_snapshots.main([str(study), str(outs[2]), str(outs[4]), '--output', str(md)])
            text = md.read_text()
            for label in ('| C |', '| E@2 |', '| E@4 |', '| E@4 (final) |', 'OOD', 'ID'):
                self.assertIn(label, text)


if __name__ == '__main__':
    unittest.main()
