import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from living_library.config import Settings
from living_library.environments import demo_manifest
from living_library.experiment import (GATE_MARGIN, Runner, baseline_probe, gate_decision, ordered, restart_library,
                                       stream_key)
from living_library.models import FixtureModel


def quiet(*args, **kwargs):
    pass


class ExperimentTests(unittest.TestCase):
    def cfg(self, **kwargs):
        return Settings(**{'practice_episodes': 2, 'evaluation_games': 2, 'step_budget': 15,
                           'bootstrap_samples': 20, **kwargs})

    def test_practice_replicates_frozen_evaluation_and_resume(self):
        cfg = self.cfg(practice_seeds=[0, 1], seeds=[11])
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp)
            records = runner.study(('C', 'D'), demo_count=2, log=quiet)
            keys = {stream_key(r['condition'], r['phase'], r['seed'], r['replicate']) for r in records}
            self.assertEqual({r['phase'] for r in records}, {'practice', 'evaluation'})
            self.assertTrue({'practice-D-0', 'practice-D-1', 'evaluation-D-r0-11', 'evaluation-D-r1-11',
                             'evaluation-C-11'} <= keys)
            practice = [r for r in records if r['phase'] == 'practice']
            self.assertEqual(sorted({r['replicate'] for r in practice}), [0, 1])
            self.assertTrue(all(r['replicate'] is None for r in records if r['condition'] == 'C'))
            # Each replicate practises its own game order.
            order = {rep: [r['task_id'] for r in practice if r['replicate'] == rep] for rep in (0, 1)}
            self.assertEqual(order[0], [t['id'] for t in ordered(demo_manifest()['splits']['practice'], 0, 2)])
            self.assertEqual(order[1], [t['id'] for t in ordered(demo_manifest()['splits']['practice'], 1, 2)])
            # Evaluation reads the replicate's final practice memory, frozen.
            final = json.loads((Path(tmp) / 'checkpoints' / 'practice-D-1' / '00001.json').read_text())['memory']
            saved = json.loads((Path(tmp) / 'checkpoints' / 'evaluation-D-r1-11' / '00000.json').read_text())
            self.assertEqual(saved['memory'], final)
            self.assertEqual(set(saved), {'stream_identity', 'previous_hash', 'memory', 'memory_hash', 'record',
                                          'record_hash'})
            with patch.object(FixtureModel, 'complete', side_effect=AssertionError('resume called model')):
                resumed = Runner(cfg, demo_manifest(), tmp).study(('C', 'D'), 2, log=quiet)
            self.assertEqual(records, resumed)

    def test_changed_config_and_checkpoint_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2, log=quiet)
            cfg = self.cfg(); cfg.top_k = 8
            with self.assertRaisesRegex(ValueError, 'different settings'):
                Runner(cfg, demo_manifest(), tmp)
            path = next((Path(tmp)/'checkpoints').rglob('00000.json'))
            data = json.loads(path.read_text()); data['record']['success'] = not data['record']['success']
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'corrupt checkpoint'):
                Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2, log=quiet)

    def test_extending_conditions_preserves_prior_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Runner(self.cfg(), demo_manifest(), tmp).study(('A',), 2, log=quiet)
            all_records = Runner(self.cfg(), demo_manifest(), tmp).study(('C',), 2, log=quiet)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(all_records), 8)
            self.assertEqual(sum(r['condition'] == 'A' for r in all_records), 2)

    def test_gate_decision(self):
        def rows(wins):
            return [{'task_id': f't{i}', 'success': w} for i, w in enumerate(wins)]
        practice = [{'manual': {'errors': ['builder: bad json', 'refiner: x']}}, {'manual': {'errors': []}}, {}]
        gate = gate_decision(rows([1, 1, 0, 0]), rows([1, 0, 1, 0]), [{}, {}, {}], practice)
        self.assertEqual((gate['E_wins'], gate['C_wins'], gate['paired_games']), (2, 2, 4))
        self.assertEqual((gate['E_won_C_lost'], gate['C_won_E_lost']), (1, 1))
        self.assertEqual((gate['rule_count'], gate['builder_errors'], gate['manual_errors']), (3, 1, 2))
        self.assertEqual(GATE_MARGIN, -3)
        self.assertTrue(gate['passed'])                                       # a tie passes
        # A bug detector: E may trail C by up to 3 games.
        self.assertTrue(gate_decision(rows([0, 0, 0, 0]), rows([1, 1, 1, 0]), [], [])['passed'])
        self.assertFalse(gate_decision(rows([0, 0, 0, 0]), rows([1, 1, 1, 1]), [], [])['passed'])
        self.assertFalse(gate_decision(rows([1, 1, 0, 0]), rows([1, 0, 1, 0]), [], [], margin=1)['passed'])
        self.assertFalse(gate_decision([], [], [], [])['passed'])           # no evidence never passes
        # only paired games count
        self.assertEqual(gate_decision(rows([1, 1, 1]), rows([0])[:1], [], [])['paired_games'], 1)

    def test_gate_specs_use_replicate_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(self.cfg(practice_seeds=[5, 6], seeds=[11]), demo_manifest(), tmp, probe=False)
            c, e = runner.gate_specs(75, 3)
            self.assertEqual((c['key'], e['key']), ('gate-C-11', 'gate-75-E-r5-11'))
            self.assertEqual((e['init'], e['init_position'], e['frozen'], e['replicate']), ('practice-E-5', 75, True, 5))
            self.assertEqual(c['tasks'], e['tasks'])
            self.assertFalse({t['id'] for t in c['tasks']} & {t['id'] for t in runner.id_evaluation_pool()})

    def test_early_gate_stops_then_continues_from_checkpoint(self):
        cfg = self.cfg(practice_episodes=4, practice_seeds=[0, 1], seeds=[11], conditions=['C', 'E'])
        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner(cfg, demo_manifest(), tmp)
            runner.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, gate_margin=99, log=quiet)
            self.assertFalse(runner.complete)
            self.assertFalse(runner.gate['passed'])
            gate = json.loads((Path(tmp) / 'gate.json').read_text())
            self.assertEqual(gate['paired_games'], 2)
            self.assertTrue((Path(tmp) / 'checkpoints' / 'gate-2-E-r0-11').exists())
            for replicate in (0, 1):                                        # every replicate stops there
                self.assertEqual(runner.count(f'practice-E-{replicate}'), 2)
            self.assertFalse((Path(tmp) / 'checkpoints' / 'evaluation-C-11').exists())
            first = (Path(tmp) / 'checkpoints' / 'practice-E-0' / '00001.json').read_text()
            go = Runner(cfg, demo_manifest(), tmp)
            records = go.study(('C', 'E'), demo_count=4, gate_at=2, gate_games=2, past_gate=True, log=quiet)
            self.assertTrue(go.complete)
            self.assertEqual(first, (Path(tmp) / 'checkpoints' / 'practice-E-0' / '00001.json').read_text())
            self.assertEqual(sum(r['phase'] == 'practice' for r in records), 8)
            self.assertTrue(json.loads((Path(tmp) / 'gate.json').read_text())['continued'])

    def test_restart_e_drops_every_replicate_and_keeps_e_minus(self):
        cfg = self.cfg(practice_seeds=[0, 1], seeds=[11], conditions=['C', 'E', 'E-minus'])
        with tempfile.TemporaryDirectory() as tmp:
            Runner(cfg, demo_manifest(), tmp).study(log=quiet, demo_count=2)
            restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E'])
            names = {d.name for d in (Path(tmp) / 'checkpoints').iterdir()}
            self.assertFalse([n for n in names if '-E-' in n and '-E-minus-' not in n], names)
            self.assertTrue({'practice-E-minus-0', 'practice-E-minus-1', 'evaluation-E-minus-r1-11',
                             'evaluation-C-11'} <= names)
            with self.assertRaisesRegex(ValueError, 'only these conditions'):
                restart_library(cfg, demo_manifest(), tmp, log=quiet, streams=['E-minus'])

    def test_restart_library_keeps_c_and_d(self):
        cfg = self.cfg(seeds=[11])
        conditions = ('C', 'D')

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
                Runner(cfg, demo_manifest(), tmp).study(conditions, 2, log=quiet)
            before = kept(tmp)
            self.assertTrue({'practice-D-0', 'evaluation-C-11', 'evaluation-D-r0-11'} <= set(before))
            a, b = version('m2', 'a1')                                      # only the manual changed
            with a, b:
                with self.assertRaisesRegex(ValueError, 'different settings'):
                    Runner(cfg, demo_manifest(), tmp)
                restart_library(cfg, demo_manifest(), tmp, log=quiet)
                self.assertEqual({d.name for d in (Path(tmp) / 'checkpoints').iterdir()}, set(before))
                runner = Runner(cfg, demo_manifest(), tmp)
                runner.study(conditions, 2, log=quiet)
                self.assertTrue(runner.complete)
                self.assertEqual(kept(tmp), before)                         # C and D games kept as they were
            restarts = json.loads((Path(tmp) / 'restarts.json').read_text())
            self.assertEqual(restarts[0]['changed_sources'], ['living_library/manual.py'])
            self.assertEqual(restarts[0]['restarted'], ['E', 'E-minus'])
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

    def test_c_and_d_behaviour_pinned(self):
        # Golden digest of every model request and record of a fixture C and D study, re-taken after the
        # 2026-11-20 redesign (code skills removed from the planner and actor prompts; replicate in the
        # context). If this fails, C or D changed.
        cfg = Settings(seeds=[11], conditions=['C', 'D'])
        self.assertEqual(baseline_probe(cfg), baseline_probe(cfg))                    # deterministic
        self.assertEqual(baseline_probe(cfg), 'c971eed1aae4fca226f922693df59f3142b3fd2065b78497675b9b2d85c6a70a')

    def test_order_is_seeded_without_mutating_manifest(self):
        tasks = demo_manifest()['splits']['evaluation']
        before = list(tasks)
        self.assertEqual(ordered(tasks, 11), ordered(tasks, 11))
        self.assertEqual(tasks, before)
        with self.assertRaises(ValueError):
            ordered(tasks, 11, 7)


if __name__ == '__main__':
    unittest.main()
