import unittest
from living_library.analysis import analyze
from living_library.config import Settings


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Settings(seeds=[11, 22], practice_seeds=[0, 1], bootstrap_samples=1000,
                            evaluation_games=3, development_games=20)

    def records(self, e_success=None):
        """E wins everything, the others nothing; memory conditions have two replicates."""
        e_success = e_success or (lambda task, replicate: True)
        rows = []
        for c in ['C', 'D', 'E', 'E-minus']:
            for replicate in ([None] if c == 'C' else self.cfg.practice_seeds):
                for t in range(3):
                    for s in self.cfg.seeds:
                        rows.append(dict(condition=c, phase='evaluation', task_id=str(t), seed=s, replicate=replicate,
                                         position=t, success=c == 'E' and e_success(t, replicate),
                                         subgoals_passed=True, gpu_seconds=None,
                                         input_tokens=2, output_tokens=3 if c == 'E' else 6))
        return rows

    def costs(self, value=0):
        return {c: {0: value, 1: value} for c in ['D', 'E', 'E-minus']}

    def test_primary_holm_and_criterion(self):
        result = analyze(self.records(), self.cfg, self.costs())
        self.assertEqual(result['primary']['H1']['estimate'], 1)
        self.assertEqual(result['primary']['H2']['estimate'], -12)   # 14 vs 26 weighted tokens
        self.assertEqual(result['primary']['H3']['estimate'], 1)
        self.assertEqual(result['primary']['H3']['ci95'], [1, 1])
        self.assertEqual(result['primary']['H1']['replicates'], [2, 2])
        self.assertNotIn('H4', result['primary'])
        self.assertTrue(result['primary']['H3']['reject_holm_05'])
        self.assertTrue(result['study_success'])
        self.assertEqual(result['secondary']['E_minus_C']['estimate'], 1)
        self.assertEqual(result['secondary']['conditions']['E']['weighted_tokens_per_task'], 14)

    def test_practice_cost_amortized_per_replicate(self):
        costs = self.costs()
        costs['E'] = {0: 30, 1: 90}          # mean 60 over 3 tasks = +20 per task
        result = analyze(self.records(), self.cfg, costs)
        self.assertAlmostEqual(result['primary']['H2']['estimate'], -12 + 20)
        self.assertAlmostEqual(result['secondary']['conditions']['E']['amortized_weighted_tokens_per_task'], 34)
        self.assertAlmostEqual(result['amortized_cost_ratio_E_D'], 34 / 26)

    def test_replicate_variance_widens_the_interval(self):
        # Replicate 0 of E wins everything, replicate 1 nothing: the point estimate is the mean, and resampling
        # replicates puts both extremes into the interval although every task agrees.
        rows = self.records(lambda task, replicate: replicate == 0)
        h3 = analyze(rows, self.cfg, self.costs())['primary']['H3']
        self.assertAlmostEqual(h3['estimate'], .5)
        self.assertEqual(h3['ci95'], [0, 1])
        self.assertFalse(h3['reject_holm_05'])

    def test_missing_tokens_never_uses_wall_time(self):
        rows = self.records()
        for r in rows:
            r['output_tokens'] = None
            r['wall_seconds'] = 100
        result = analyze(rows, self.cfg, self.costs())
        self.assertEqual(result['primary']['H2']['status'], 'unavailable')
        self.assertIsNone(result['amortized_cost_ratio_E_D'])
        # practice cost is required to amortize
        self.assertEqual(analyze(self.records(), self.cfg)['primary']['H2']['status'], 'unavailable')
        costs = self.costs()
        del costs['E'][1]
        self.assertEqual(analyze(self.records(), self.cfg, costs)['primary']['H2']['status'], 'unavailable')

    def test_missing_seed_or_task_and_duplicate_raise(self):
        rows = self.records()
        rows.remove(next(r for r in rows if r['condition'] == 'D'))
        with self.assertRaisesRegex(ValueError, 'different task/seed'):
            analyze(rows, self.cfg)
        rows = self.records()
        rows.append(dict(next(r for r in rows if r['condition'] == 'E')))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            analyze(rows, self.cfg)
        rows = [r for r in self.records() if r['seed'] == 11]
        with self.assertRaisesRegex(ValueError, 'every configured seed'):
            analyze(rows, self.cfg)

    def test_truncated_study_rejected_and_false_success(self):
        rows = [r for r in self.records() if r['task_id'] != '2']
        with self.assertRaisesRegex(ValueError, 'every configured evaluation task'):
            analyze(rows, self.cfg)
        result = analyze(self.records(), self.cfg, self.costs())
        self.assertEqual(result['secondary']['conditions']['C']['false_success'], 1)
        self.assertEqual(result['secondary']['conditions']['E']['false_success'], 0)


if __name__ == '__main__':
    unittest.main()
