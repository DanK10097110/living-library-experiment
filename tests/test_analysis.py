import unittest
from living_library.analysis import analyze, pilot_report
from living_library.config import Settings


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Settings(seeds=[11, 22], bootstrap_samples=1000, pilot_practice=2,
                            evaluation_games=3, development_games=20)

    def records(self):
        return [dict(condition=c, phase='evaluation', task_id=str(t), seed=s, position=t,
                     success=c == 'E', invocations=[{'success': c == 'E', 'skill_id': 'x@v1', 'preconditions_held': True}],
                     subgoals_passed=True, gpu_seconds=1 if c == 'E' else 2,
                     input_tokens=2, output_tokens=3)
                for c in ['C', 'D', 'E', 'E-minus', 'E-text']
                for t in range(3) for s in self.cfg.seeds]

    def test_primary_gpu_and_paired_holm(self):
        costs = {c: {11: 0, 22: 0} for c in ['D', 'E']}
        result = analyze(self.records(), self.cfg, costs)
        self.assertEqual(result['primary']['H1']['estimate'], 1)
        self.assertEqual(result['primary']['H2']['estimate'], -1)
        self.assertEqual(result['primary']['H3']['estimate'], 1)
        self.assertEqual(result['primary']['H4']['ci95'], [1, 1])
        self.assertTrue(result['study_success'])
        self.assertEqual(result['secondary']['conditions']['E']['weighted_tokens_per_task'], 14)
        self.assertEqual(result['secondary']['break_even']['11']['first_task'], 1)

    def test_missing_gpu_never_uses_wall_time(self):
        rows = self.records()
        for r in rows:
            r['gpu_seconds'] = None
            r['wall_seconds'] = 100
        result = analyze(rows, self.cfg)
        self.assertEqual(result['primary']['H2']['status'], 'unavailable')
        self.assertIsNone(result['amortized_gpu_cost_ratio_E_D'])

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

    def test_zero_invocations_unavailable(self):
        rows = self.records()
        next(r for r in rows if r['condition'] == 'E')['invocations'] = []
        # The other seed in this task contributes one invocation: pooled denominator remains one.
        self.assertEqual(analyze(rows, self.cfg)['primary']['H3']['status'], 'available')
        for r in rows:
            if r['condition'] == 'E' and r['task_id'] == '0':
                r['invocations'] = []
        self.assertEqual(analyze(rows, self.cfg)['primary']['H3']['status'], 'available')
        for r in rows:
            if r['condition'] == 'E':
                r['invocations'] = []
        self.assertEqual(analyze(rows, self.cfg)['primary']['H3']['status'], 'unavailable')

    def test_pilot_thresholds_and_zero_evidence(self):
        result = pilot_report([], [], [], self.cfg)
        self.assertFalse(result['ready'])
        self.assertTrue(all(g['status'] == 'unavailable' for g in result['gates'].values()))
        rows = [dict(condition=c, success=i < 17, subgoals_passed=False)
                for c in ['C', 'E-minus'] for i in range(20)]
        practice = [dict(invocations=[], program_attempts=5, program_errors=['bad', 'crash']) for _ in range(2)]
        result = pilot_report(practice, rows, [], self.cfg)
        self.assertEqual(result['gates']['baseline_ceiling']['status'], 'pass')  # exactly .85
        self.assertEqual(result['gates']['program_failure']['status'], 'pass')  # exactly .40
        self.assertEqual(result['gates']['repeated_skills']['status'], 'fail')
        self.assertTrue(result['switch_domain'])
        rows[17]['success'] = True
        self.assertEqual(pilot_report(practice, rows, [], self.cfg)['gates']['baseline_ceiling']['status'], 'fail')

    def test_truncated_study_rejected_and_partial_false_success_unknown(self):
        rows = [r for r in self.records() if r['task_id'] != '2']
        with self.assertRaisesRegex(ValueError, 'every configured evaluation task'):
            analyze(rows, self.cfg)
        report = pilot_report([], [{'condition': 'C', 'success': True, 'subgoals_passed': False},
                                   {'condition': 'C', 'success': False}], [], self.cfg)
        self.assertEqual(report['gates']['false_success']['status'], 'unavailable')

    def test_invocation_ratio_pools_counts_but_resamples_tasks(self):
        rows = self.records()
        for r in rows:
            if r['condition'] == 'E':
                r['invocations'] = [{'success': r['task_id'] == '0', 'preconditions_held': True}] * (100 if r['task_id'] == '0' else 1)
        result = analyze(rows, self.cfg)
        self.assertAlmostEqual(result['primary']['H3']['estimate'], 100/102)


if __name__ == '__main__':
    unittest.main()
