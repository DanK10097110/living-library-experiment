"""LIBRARY-SPEC.md section 7: the management thresholds meet the acceptance criteria in the mechanism simulator
(tools/sim_mechanisms.py), which drives the real manual functions with a noisy synthetic judge."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import sim_mechanisms  # noqa: E402


class AcceptanceTests(unittest.TestCase):
    def test_acceptance_criteria(self):
        # One kind of task's share of practice (about 50 of 300 games) and a general rule shown in every game.
        for eligible in (sim_mechanisms.ELIGIBLE, 1.0):
            for name, (share, limit, passed) in sim_mechanisms.simulate(runs=3000, seed=0, eligible=eligible).items():
                self.assertTrue(passed, f'{name}: {share:.3f}, needs {limit} (eligible {eligible:.2f})')


if __name__ == '__main__':
    unittest.main()
