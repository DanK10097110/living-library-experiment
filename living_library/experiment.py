"""Opt-in experiment orchestration with split guards and atomic episode checkpoints."""
import copy
import json
from pathlib import Path
import random

from .config import CONDITIONS, MEMORY, Settings, digest, write_json
from .environments import ALFWorld, MiniWorld, demo_manifest, validate_manifest
from .library import Library, LexicalEmbedding, SentenceEmbedding
from .protocol import PREREGISTRATION


def source_fingerprint():
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root / 'living_library').glob('*.py'))
    if (root / 'pyproject.toml').exists():
        paths.append(root / 'pyproject.toml')
    return digest({str(p.relative_to(root)): p.read_text() for p in paths})


def identity(cfg, manifest):
    return {'settings': digest(cfg.to_dict()), 'manifest': digest(manifest),
            'source': source_fingerprint()}


def load_json(path):
    return json.loads(Path(path).read_text())


def ordered(tasks, seed, count=None, repeat=False):
    tasks = list(tasks)
    random.Random(seed).shuffle(tasks)
    count = len(tasks) if count is None else count
    if count > len(tasks) and not repeat:
        raise ValueError(f'need {count} games but manifest has only {len(tasks)}')
    return [copy.deepcopy(tasks[i % len(tasks)]) for i in range(count)]


def validate_real_design(cfg, manifest):
    if manifest['environment'] != 'alfworld':
        raise ValueError('pilot/study require an ALFWorld manifest; use demo for fixture data')
    if (cfg.pilot_practice, cfg.practice_episodes, cfg.development_games,
            cfg.evaluation_games, len(cfg.seeds)) != (300, 500, 140, 134, 3):
        raise ValueError('real design requires 300 pilot / 500 practice / 140 development / 134 evaluation games and 3 seeds')
    for split, count in [('development', 140), ('evaluation', 134)]:
        if len(manifest['splits'][split]) != count:
            raise ValueError(f'{split} manifest must contain exactly {count} games')


class Runner:
    def __init__(self, cfg, manifest, output, model=None, embedder=None):
        validate_manifest(manifest)
        self.cfg, self.manifest, self.output = cfg, manifest, Path(output)
        self.toy = manifest['environment'] == 'mini'
        self.env_factory = MiniWorld if self.toy else ALFWorld
        self.identity = identity(cfg, manifest)
        marker = self.output / 'run.json'
        expected = {'identity': self.identity, 'toy': self.toy, 'environment': manifest['environment']}
        if marker.exists() and load_json(marker) != expected:
            raise ValueError('output belongs to different settings, sources or manifest; choose a new output directory')
        self.output.mkdir(parents=True, exist_ok=True)
        if model is None:
            from .models import FixtureModel, HTTPModel
            model = FixtureModel() if self.toy else HTTPModel(cfg, self.output / "model-cache.sqlite")
        self.model = model
        self.embedder = embedder or (LexicalEmbedding() if self.toy else
                                    SentenceEmbedding(cfg.embedding, cfg.embedding_revision))
        self.records = load_json(self.output / 'records.json') if (self.output / 'records.json').exists() else []
        write_json(marker, expected)
        write_json(self.output / 'settings.json', cfg.to_dict())

    def stream(self, condition, phase, seed, tasks, library=None, trajectories=None, snapshots=None):
        from .agents import Agent
        library = library or Library(self.cfg)
        trajectories = copy.deepcopy(trajectories or [])
        initial_library, initial_trajectories = library.snapshot(), copy.deepcopy(trajectories)
        stream_key = f'{phase}-{condition}-{seed}'
        stream_identity = digest({'identity': self.identity, 'tasks': tasks, 'condition': condition,
                                  'phase': phase, 'seed': seed, 'initial_library': initial_library,
                                  'initial_trajectories': initial_trajectories, 'snapshots': snapshots})
        before = []
        records = []
        for position, task in enumerate(tasks):
            if snapshots is not None:
                library = Library.restore(copy.deepcopy(snapshots[position]), self.cfg)
            pre = library.snapshot()
            checkpoint = self.output / 'checkpoints' / stream_key / f'{position:05d}.json'
            previous_hash = digest(records[-1]) if records else None
            if checkpoint.exists():
                saved = load_json(checkpoint)
                if (saved['stream_identity'] != stream_identity or saved['previous_hash'] != previous_hash
                        or saved['pre_library_hash'] != digest(pre)
                        or saved['record_hash'] != digest(saved['record'])
                        or saved['memory_hash'] != digest(saved['memory'])
                        or saved['pre_library_hash'] != digest(saved['pre_library'])):
                    raise ValueError(f'incompatible/corrupt checkpoint {checkpoint}; choose a fresh output directory')
                record = saved['record']
                library = Library.restore(saved['memory']['library'], self.cfg)
                trajectories = saved['memory']['trajectories']
            else:
                context = {'condition': condition, 'phase': phase, 'seed': seed,
                           'task_id': task['id'], 'position': position, 'toy': self.toy}
                result = Agent(self.cfg, condition, self.model, library, self.embedder,
                               self.env_factory, trajectories=trajectories).run(task, seed, context)
                record = {**result, **context}
                if condition == 'E-text' and library.snapshot() != pre:
                    raise ValueError('E-text mutated its supplied read-only library')
                if condition == 'D' and phase == 'practice' and record['success']:
                    trajectories.append({'task': task, 'trace': record['trace'], 'success': True})
                memory = {'library': library.snapshot(), 'trajectories': copy.deepcopy(trajectories)}
                write_json(checkpoint, {'stream_identity': stream_identity, 'previous_hash': previous_hash,
                                       'pre_library': pre, 'pre_library_hash': digest(pre),
                                       'memory': memory, 'memory_hash': digest(memory),
                                       'record': record, 'record_hash': digest(record)})
            before.append(pre)
            records.append(record)
        self.records = [r for r in self.records if (r['condition'], r['phase'], r['seed']) !=
                        (condition, phase, seed)] + records
        write_json(self.output / 'records.json', self.records)
        return library, trajectories, before

    def workflow(self, name):
        marker = self.output / 'workflow.json'
        if marker.exists() and load_json(marker) != {'workflow': name}:
            raise ValueError('pilot and study require separate output directories')
        write_json(marker, {'workflow': name})

    def study(self, conditions=CONDITIONS, demo_count=None, freeze_path=None):
        if not self.toy:
            if freeze_path is None:
                raise ValueError("real study requires --freeze from a passing real pilot")
            verify_freeze(self.cfg, self.manifest, freeze_path)
        self.workflow('study')
        conditions = tuple(conditions)
        if any(c not in CONDITIONS for c in conditions) or len(set(conditions)) != len(conditions):
            raise ValueError('conditions must be unique valid condition IDs')
        if not self.toy and demo_count is not None:
            raise ValueError('sample count overrides are available only in demo')
        # E is a required source for the task-matched E-text snapshot comparison.
        run_conditions = set(conditions) | ({'E'} if 'E-text' in conditions else set())
        practice = ordered(self.manifest['splits']['practice'], self.cfg.practice_seed,
                           demo_count or self.cfg.practice_episodes, repeat=True)
        practiced = {}
        for condition in CONDITIONS:
            if condition in run_conditions and condition in MEMORY:
                lib, trajectories, _ = self.stream(condition, 'practice', self.cfg.practice_seed, practice)
                practiced[condition] = (lib.snapshot(), trajectories)
        e_snapshots = {}
        for condition in CONDITIONS:
            if condition not in run_conditions:
                continue
            seeds = self.cfg.seeds[:1] if condition in {'A', 'B'} else self.cfg.seeds
            for seed in seeds:
                evaluation_pool = self.manifest['splits']['evaluation']
                if demo_count is not None:
                    evaluation_pool = evaluation_pool[:demo_count]
                tasks = ordered(evaluation_pool, seed, demo_count or self.cfg.evaluation_games)
                initial, trajectories = practiced.get(condition, (Library(self.cfg).snapshot(), []))
                _, _, snapshots = self.stream(condition, 'evaluation', seed, tasks,
                    Library.restore(copy.deepcopy(initial), self.cfg), trajectories,
                    e_snapshots[seed] if condition == 'E-text' else None)
                if condition == 'E':
                    e_snapshots[seed] = snapshots
        write_json(self.output / 'cost_attribution.json', {
            'E-text': {'practice_source': 'E', 'charge_full_E_practice_cost': True},
            'practice_shared_across_evaluation_seeds': True, 'practice_seed': self.cfg.practice_seed})
        return self.records

    def pilot(self):
        self.workflow('pilot')
        validate_real_design(self.cfg, self.manifest)
        practice = ordered(self.manifest['splits']['practice'], self.cfg.practice_seed,
                           self.cfg.pilot_practice, repeat=True)
        lib, _, _ = self.stream('E-minus', 'practice', self.cfg.practice_seed, practice)
        dev = ordered(self.manifest['splits']['development'], self.cfg.seeds[0], self.cfg.development_games)
        self.stream('C', 'development', self.cfg.seeds[0], dev)
        self.stream('E-minus', 'development', self.cfg.seeds[0], dev, lib)
        evidence = {'identity': self.identity, 'toy': False, 'records_hash': digest(self.records),
                    'gate': pilot_gate(self.records, self.cfg)}
        write_json(self.output / 'pilot-evidence.json', evidence)
        return evidence


def pilot_gate(records, cfg):
    from .analysis import pilot_report
    practice = [r for r in records if r['phase'] == 'practice' and r['condition'] == 'E-minus']
    baseline = [r for r in records if r['phase'] == 'development' and r['condition'] == 'C']
    memory = [r for r in records if r['phase'] == 'development' and r['condition'] == 'E-minus']
    complete = (len(records) == 580 and len(practice) == 300 and len(baseline) == 140
                and len(memory) == 140 and not any(r.get('toy', True) for r in records)
                and len({r['task_id'] for r in baseline}) == 140
                and {r['task_id'] for r in baseline} == {r['task_id'] for r in memory})
    report = pilot_report(practice, baseline, memory, cfg)
    return {'passed': complete and report['ready'], 'complete_real_pilot': complete, 'report': report}


def freeze(cfg, manifest, pilot_dir, destination):
    validate_manifest(manifest)
    validate_real_design(cfg, manifest)
    for field in ('embedding_revision', 'planner_revision', 'executor_revision', 'quantization', 'hardware'):
        value = getattr(cfg, field, '')
        if not value or value in {'main', 'unverified', '4-bit-unverified', 'unrecorded'}:
            raise ValueError(f'freeze requires an explicit verified {field}; update settings and rerun pilot')
    evidence = load_json(Path(pilot_dir) / 'pilot-evidence.json')
    records = load_json(Path(pilot_dir) / 'records.json')
    current = identity(cfg, manifest)
    marker = load_json(Path(pilot_dir) / 'run.json')
    if marker != {'identity': current, 'toy': False, 'environment': 'alfworld'}:
        raise ValueError('pilot run metadata does not match current real experiment')
    for record in records:
        if record['phase'] not in {'practice', 'development'}:
            raise ValueError('pilot evidence contains an unauthorized split')
        split = 'practice' if record['phase'] == 'practice' else 'development'
        ids = {t['id'] for t in manifest['splits'][split]}
        if record['task_id'] not in ids:
            raise ValueError('pilot evidence has a task outside its authorized split')
        stream = f"{record['phase']}-{record['condition']}-{record['seed']}"
        checkpoint = load_json(Path(pilot_dir) / 'checkpoints' / stream / f"{record['position']:05d}.json")
        if (checkpoint.get('record') != record or checkpoint.get('record_hash') != digest(record)
                or checkpoint.get('memory_hash') != digest(checkpoint.get('memory'))
                or checkpoint.get('pre_library_hash') != digest(checkpoint.get('pre_library'))):
            raise ValueError('pilot checkpoint evidence is missing or corrupt')
    gate = pilot_gate(records, cfg)
    if (evidence['identity'] != current or evidence['toy'] or evidence['records_hash'] != digest(records)
            or evidence['gate'] != gate or not gate['passed']):
        raise ValueError('freeze requires complete real pilot evidence passing every gate with matching sources/settings/data')
    artifact = {'identity': current, 'settings': cfg.to_dict(), 'manifest_hash': digest(manifest),
                'preregistration': PREREGISTRATION,
                'pilot_records_hash': digest(records), 'pilot_gate': gate, 'toy': False}
    artifact['freeze_hash'] = digest(artifact)
    write_json(destination, artifact)
    return artifact


def verify_freeze(cfg, manifest, path):
    validate_real_design(cfg, manifest)
    artifact = load_json(path)
    payload = {k: v for k, v in artifact.items() if k != 'freeze_hash'}
    if (artifact.get('freeze_hash') != digest(payload) or artifact.get('identity') != identity(cfg, manifest)
            or artifact.get('toy') is not False or not artifact.get('pilot_gate', {}).get('passed')):
        raise ValueError('freeze is missing/invalid or sources/settings/data changed; rerun the real pilot and freeze')
    return artifact
