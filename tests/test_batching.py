import json
import tempfile
import unittest
from pathlib import Path

from living_library.batching import merge_memory
from living_library.config import Settings
from living_library.environments import demo_manifest
from living_library.experiment import Runner


def quiet(*args, **kwargs):
    pass


class MergeTests(unittest.TestCase):
    def test_trajectories_append_in_order_and_one_game_merge_is_that_games_memory(self):
        base = {'trajectories': [{'goal': 'a'}], 'rules': []}
        game1 = {'trajectories': [{'goal': 'a'}, {'goal': 'b'}], 'rules': []}
        game2 = {'trajectories': [{'goal': 'a'}, {'goal': 'c'}], 'rules': []}
        live = merge_memory(base, base, game1, [])
        self.assertEqual(live, game1)
        live = merge_memory(live, base, game2, [])
        self.assertEqual([t['goal'] for t in live['trajectories']], ['a', 'b', 'c'])


class BatchedPracticeTests(unittest.TestCase):
    def cfg(self, batch, conditions=('C', 'D')):
        return Settings(practice_episodes=6, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                        seeds=[11], conditions=list(conditions), practice_batch=batch)

    def run_practice(self, directory, batch, workers, conditions):
        runner = Runner(self.cfg(batch, conditions), demo_manifest(), directory)
        specs = [s for s in runner.study_specs(demo_count=6) if s['phase'] == 'practice']
        self.assertTrue(runner.execute(specs, workers=workers, log=quiet))
        return runner, specs

    def test_batched_practice_is_deterministic_and_verifiable(self):
        self.check_deterministic(('C', 'D'), {'practice-D-0'})

    def test_batched_rule_practice_is_deterministic_and_verifiable(self):
        self.check_deterministic(('C', 'E'), {'practice-E-0'})     # E: batch-end upkeep included

    def check_deterministic(self, conditions, keys):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra, specs = self.run_practice(a, 4, 1, conditions)
            rb, _ = self.run_practice(b, 4, 4, conditions)
            keyed = {s['key']: s for s in specs}
            self.assertEqual({s['key'] for s in specs}, keys)
            for spec in specs:
                self.assertTrue(ra.batched(spec))
                for position in range(6):
                    sa = json.loads((Path(a) / 'checkpoints' / spec['key'] / f'{position:05d}.json').read_text())
                    sb = json.loads((Path(b) / 'checkpoints' / spec['key'] / f'{position:05d}.json').read_text())
                    self.assertEqual(sa['memory'], sb['memory'])
                    self.assertEqual(sa['record']['success'], sb['record']['success'])
                    self.assertEqual(set(sa['memory']), {'trajectories', 'rules'})
                self.assertEqual(len(rb.verify(spec, keyed)), 6)

    def test_batch_of_one_is_the_sequential_path(self):
        with tempfile.TemporaryDirectory() as a:
            runner = Runner(self.cfg(1), demo_manifest(), a)
            practice = [s for s in runner.study_specs(demo_count=6) if s['phase'] == 'practice']
            self.assertTrue(practice and not any(runner.batched(s) for s in practice))


if __name__ == '__main__':
    unittest.main()
