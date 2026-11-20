import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from living_library.agents import Agent
from living_library.config import Settings
from living_library.embedding import LexicalEmbedding
from living_library.environments import MiniWorld, demo_manifest
from living_library.experiment import Runner, memoryless
from living_library.models import FixtureModel, HTTPModel

TIMING = ('wall_seconds', 'model_wall_seconds')


def quiet(*args, **kwargs):
    pass


def stable(records):
    return [{k: v for k, v in r.items() if k not in TIMING} for r in records]


def load(root, key, position):
    return json.loads((root / 'checkpoints' / key / f'{position:05d}.json').read_text())


class ParallelChunkTests(unittest.TestCase):
    def cfg(self):
        return Settings(practice_episodes=3, evaluation_games=3, step_budget=15, bootstrap_samples=20,
                        conditions=['C', 'D', 'E'], practice_seeds=[0, 1])

    def run_study(self, directory, **kwargs):
        runner = Runner(self.cfg(), demo_manifest(), directory)
        records = runner.study(demo_count=3, log=quiet, **kwargs)
        return runner, records

    def test_parallel_workers_match_sequential(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, sequential = self.run_study(a)
            runner, parallel = self.run_study(b, workers=3)
            self.assertTrue(runner.complete)
            self.assertEqual(stable(sequential), stable(parallel))

    def test_chunked_sessions_resume_to_same_result(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, whole = self.run_study(a)
            sessions = 0
            while True:
                sessions += 1
                runner, chunked = self.run_study(b, max_episodes=4)
                if runner.complete:
                    break
                self.assertLessEqual(len(chunked), 4 * sessions)
            self.assertGreater(sessions, 5)
            self.assertEqual(stable(whole), stable(chunked))
            with patch.object(FixtureModel, 'complete', side_effect=AssertionError('resume called model')):
                _, again = self.run_study(b)
            self.assertEqual(chunked, again)

    def test_zero_hour_budget_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, records = self.run_study(tmp, max_hours=0)
            self.assertFalse(runner.complete)
            self.assertEqual(records, [])

    def test_evaluation_reads_frozen_practice_memory_in_parallel(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(self.cfg(), demo_manifest(), tmp)
            specs = {s['key']: s for s in runner.study_specs(('C', 'D'), 3)}
            for replicate in (0, 1):
                e = specs[f'evaluation-D-r{replicate}-11']
                self.assertEqual((e['init'], e['frozen'], e['replicate']), (f'practice-D-{replicate}', True, replicate))
                self.assertTrue(memoryless(e))
                self.assertEqual(runner.ready(e, specs), 0)                 # waits for its practice only
            self.assertTrue(runner.execute(list(specs.values()), workers=4, log=quiet))
            for replicate in (0, 1):
                final = load(Path(tmp), f'practice-D-{replicate}', 2)['memory']
                saved = load(Path(tmp), f'evaluation-D-r{replicate}-11', 2)
                self.assertEqual(saved['memory'], final)                   # nothing learned at test time
                self.assertEqual(saved['record']['replicate'], replicate)


class PromptHygieneTests(unittest.TestCase):
    def test_model_sees_goal_not_manifest_paths(self):
        seen = []

        class GoalWorld(MiniWorld):
            def reset(self, task):
                self.goal = 'put an apple in cabinet'
                return super().reset(task)

        class Spy(FixtureModel):
            def complete(self, role, payload, seed, context):
                seen.append(payload['task'])
                return super().complete(role, {**payload, 'task': {'object': 'apple 1', 'target': 'cabinet 1'}}, seed, context)

        cfg = Settings()
        task = {'object': 'apple 1', 'target': 'cabinet 1', 'gamefile': '/data/pick_and_place-Apple-Cabinet/game.tw-pddl',
                'sha256': 'x', 'id': 'secret/path'}
        result = Agent(cfg, 'C', Spy(), LexicalEmbedding(), GoalWorld).run(task, 1, {})
        self.assertTrue(seen)
        self.assertTrue(all(t == {'goal': 'put an apple in cabinet'} for t in seen))
        self.assertEqual(result['goal'], 'put an apple in cabinet')

    def test_context_addresses_cache_but_is_not_in_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            model = HTTPModel(Settings(), directory + '/cache.sqlite')
            request = model.request('builder', {'task': {'goal': 'g'}, 'instructions': 'static',
                                                'response_schema': {'a': 1}, 'state': {'x': 1}}, 3)
            model.close()
        system, user = request['messages'][0]['content'], request['messages'][1]['content']
        self.assertIn('static', system)
        self.assertNotIn('static', user)
        self.assertTrue(user.startswith('{"task":'))
        self.assertNotIn('position', json.dumps(request))


class LeanDesignTests(unittest.TestCase):
    def test_memoryless_stream_runs_episodes_concurrently_and_verifies(self):
        cfg = Settings(practice_episodes=3, evaluation_games=6, step_budget=15, bootstrap_samples=20,
                       conditions=['C'])
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            seq = Runner(cfg, demo_manifest(), a).study(demo_count=6, log=quiet)
            runner = Runner(cfg, demo_manifest(), b)
            specs = runner.study_specs(demo_count=6)
            self.assertTrue(all(memoryless(s) for s in specs))
            par = runner.study(demo_count=6, workers=4, log=quiet)
            self.assertTrue(runner.complete)
            self.assertEqual(stable(seq), stable(par))
            for spec in specs:          # the hash chain of in-order commits is intact
                self.assertEqual(len(runner.verify(spec, {s['key']: s for s in specs})), 6)

    def test_config_conditions_select_study_streams(self):
        cfg = Settings(practice_episodes=2, evaluation_games=2, seeds=[11, 22], practice_seeds=[0, 1],
                       conditions=['A', 'C', 'D', 'E', 'E-minus'])
        with tempfile.TemporaryDirectory() as tmp:
            keys = [s['key'] for s in Runner(cfg, demo_manifest(), tmp, probe=False).study_specs(demo_count=2)]
        self.assertEqual(sum(k.startswith('practice-') for k in keys), 6)        # 3 memory conditions x 2
        self.assertEqual(sum(k.startswith('evaluation-C-') for k in keys), 2)
        self.assertEqual(sum(k.startswith('evaluation-A-') for k in keys), 1)
        self.assertEqual(sum(k.startswith('evaluation-E-r') for k in keys), 4)  # 2 replicates x 2 seeds
        self.assertIn('evaluation-E-minus-r1-22', keys)
        for removed in ('B', 'E-text', 'E-plus'):
            with self.assertRaises(ValueError):
                Settings(conditions=[removed])

    def test_real_config_matches_lean_design(self):
        from living_library.experiment import REAL_DESIGN, validate_real_design
        cfg = Settings.load('configs/pilot.json')
        manifest = {'environment': 'alfworld', 'splits': {'development': [0] * 140, 'evaluation': [0] * 134}}
        validate_real_design(cfg, manifest)
        self.assertEqual(REAL_DESIGN['seeds'], len(cfg.seeds))
        self.assertEqual(cfg.practice_seeds, [0, 1])
        self.assertEqual(cfg.conditions, ['C', 'D', 'E', 'E-minus'])


class SnapshotCurveTests(unittest.TestCase):
    def test_frozen_milestone_streams_read_practice_memory_without_changing_it(self):
        cfg = Settings(practice_episodes=4, evaluation_games=3, step_budget=15, bootstrap_samples=20,
                       seeds=[11], conditions=['C', 'D'], snapshot_milestones=[2, 4],
                       snapshot_games=2, snapshot_conditions=['D'], practice_seeds=[0, 1])
        manifest = demo_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, manifest, tmp)
            specs = runner.study_specs()
            snaps = [s for s in specs if s['phase'].startswith('snapshot-')]
            self.assertTrue({'snapshot-2-ood-D-r0-11', 'snapshot-4-ood-D-r1-11'} <= {s['key'] for s in snaps})
            self.assertTrue(all(s['frozen'] and s['init'] == f"practice-D-{s['replicate']}" for s in snaps))
            self.assertTrue(runner.execute(specs, workers=3, log=quiet))
            keyed = {s['key']: s for s in specs}
            for s in snaps:
                initial = runner._initial(s, keyed)
                expected = load(Path(tmp), s['init'], s['init_position'] - 1)['memory']
                self.assertEqual(initial, expected)
                for position in range(runner.count(s['key'])):
                    self.assertEqual(load(Path(tmp), s['key'], position)['memory'], expected)   # frozen


if __name__ == '__main__':
    unittest.main()
