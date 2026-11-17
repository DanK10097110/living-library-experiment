import json
import tempfile
import unittest
from pathlib import Path

from living_library.agents import Agent
from living_library.batching import merge_library
from living_library.config import Settings
from living_library.environments import MiniWorld, demo_manifest
from living_library.experiment import Runner
from living_library.library import Library, LexicalEmbedding
from living_library.models import FixtureModel, ModelResponse

TASK = {'object': 'apple 1', 'target': 'cabinet 1'}


def quiet(*args, **kwargs):
    pass


def skill(sid, successes=0, failures=0, status='active', parent=None):
    return {'id': sid, 'description': 'd', 'parameters': {}, 'preconditions': [], 'postconditions': ['task_won()'],
            'body': 'act("look")', 'parent': parent, 'successes': successes, 'failures': failures, 'streak': 0,
            'failure_notes': [], 'tests': [], 'status': status}


def lib(*skills):
    return {'skills': list(skills), 'active': {s['id'].split('@')[0]: s['id'] for s in skills if s['status'] == 'active'}}


class MergeTests(unittest.TestCase):
    def test_counters_add_and_same_skill_written_twice_is_kept_once(self):
        base = lib(skill('go@v1', 1, 0))
        game1 = lib(skill('go@v1', 3, 1), skill('clean@v1'))
        game2 = lib(skill('go@v1', 2, 0), skill('clean@v1'))
        log = []
        live = merge_library(base, base, game1, log)
        live = merge_library(live, base, game2, log)
        go = next(s for s in live['skills'] if s['id'] == 'go@v1')
        self.assertEqual((go['successes'], go['failures']), (4, 1))        # 1 + 2 + 1, 0 + 1 + 0
        self.assertEqual([s['id'] for s in live['skills']].count('clean@v1'), 1)
        self.assertEqual(log, [['duplicate', 'clean@v1']])

    def test_competing_revisions_keep_the_first_and_status_stays_consistent(self):
        base = lib(skill('go@v1'))
        r1 = lib(skill('go@v1', status='fallback'), skill('go@v2', parent='go@v1'))
        r1['active'] = {'go': 'go@v2'}
        log = []
        live = merge_library(base, base, r1, log)
        r2 = lib(skill('go@v1', status='fallback'), skill('go@v3', parent='go@v1'))
        r2['active'] = {'go': 'go@v3'}
        live = merge_library(live, base, r2, log)
        self.assertEqual(live['active'], {'go': 'go@v2'})
        self.assertEqual(log, [['superseded', 'go@v3']])
        status = {s['id']: s['status'] for s in live['skills']}
        self.assertEqual(status, {'go@v1': 'fallback', 'go@v2': 'active'})

    def test_one_game_merge_is_that_games_memory(self):
        base = lib(skill('go@v1'))
        end = lib(skill('go@v1', 2, 1), skill('clean@v1'))
        self.assertEqual(merge_library(base, base, end, []), end)


class BatchedPracticeTests(unittest.TestCase):
    def cfg(self, batch):
        return Settings(practice_episodes=6, evaluation_games=2, step_budget=15, bootstrap_samples=20,
                        seeds=[11], conditions=['C', 'E', 'D', 'E-plus'], practice_batch=batch, consolidation_interval=3)

    def run_practice(self, directory, batch, workers):
        runner = Runner(self.cfg(batch), demo_manifest(), directory)
        specs = [s for s in runner.study_specs(demo_count=6) if s['phase'] == 'practice']
        self.assertTrue(runner.execute(specs, workers=workers, log=quiet))
        return runner, specs

    def test_batched_practice_is_deterministic_and_verifiable(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra, specs = self.run_practice(a, 4, 1)
            rb, _ = self.run_practice(b, 4, 4)
            keyed = {s['key']: s for s in specs}
            for spec in specs:
                self.assertTrue(ra.batched(spec))
                for position in range(6):
                    sa = json.loads((Path(a) / 'checkpoints' / spec['key'] / f'{position:05d}.json').read_text())
                    sb = json.loads((Path(b) / 'checkpoints' / spec['key'] / f'{position:05d}.json').read_text())
                    self.assertEqual(sa['memory'], sb['memory'])
                    self.assertEqual(sa['record']['success'], sb['record']['success'])
                # Games 0-3 all saw the initial memory; games 4-5 saw the memory after game 3.
                pre = [json.loads((Path(a) / 'checkpoints' / spec['key'] / f'{p:05d}.json').read_text())['pre_library']
                       for p in range(6)]
                self.assertTrue(pre[0] == pre[1] == pre[2] == pre[3])
                after3 = json.loads((Path(a) / 'checkpoints' / spec['key'] / '00003.json').read_text())['memory']
                self.assertEqual(pre[4], after3['library'])
                self.assertEqual(len(rb.verify(spec, keyed)), 6)

    def test_batch_of_one_is_the_sequential_path(self):
        with tempfile.TemporaryDirectory() as a:
            runner = Runner(self.cfg(1), demo_manifest(), a)
            practice = [s for s in runner.study_specs(demo_count=6) if s['phase'] == 'practice']
            self.assertTrue(practice and not any(runner.batched(s) for s in practice))


class EPlusSkillWritingTests(unittest.TestCase):
    def test_eplus_writes_skills_only_at_the_end_of_won_games(self):
        seen = []

        class Spy(FixtureModel):
            def __init__(self, win=True):
                self.win = win

            def complete(self, role, payload, seed, context):
                if role == 'librarian':
                    seen.append(payload)
                if role == 'actor' and not self.win:
                    return ModelResponse({'text': '<action>look</action>'})
                return super().complete(role, payload, seed, context)

        cfg = Settings(step_budget=12, max_model_calls=30)
        library = Library(cfg)
        won = Agent(cfg, 'E-plus', Spy(), library, LexicalEmbedding(), MiniWorld).run(TASK, 1, {})
        self.assertTrue(won['success'])
        self.assertEqual(won['deferred_subgoals'], 1)
        self.assertEqual(len(seen), 1)
        self.assertIn('whole_game', seen[0])
        self.assertTrue(seen[0]['whole_game']['won'])
        self.assertEqual(len(library.current()), 1)

        seen.clear()
        library = Library(cfg)
        lost = Agent(cfg, 'E-plus', Spy(win=False), library, LexicalEmbedding(), MiniWorld).run(TASK, 1, {})
        self.assertFalse(lost['success'])
        self.assertEqual(seen, [])
        self.assertEqual(library.current(), [])
        # E itself is unchanged: it still writes when the subgoal succeeds.
        library = Library(cfg)
        Agent(cfg, 'E', Spy(), library, LexicalEmbedding(), MiniWorld).run(TASK, 1, {})
        self.assertNotIn('whole_game', seen[-1])


if __name__ == '__main__':
    unittest.main()
