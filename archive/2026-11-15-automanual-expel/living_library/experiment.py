"""Opt-in experiment orchestration with split guards and atomic episode checkpoints."""
import copy
import json
from pathlib import Path
import random
import time

from .config import CONDITIONS, MEMORY, Settings, digest, write_json
from .environments import ALFWorld, MiniWorld, demo_manifest, validate_manifest
from .library import Library, LexicalEmbedding, SentenceEmbedding
from .protocol import PREREGISTRATION


def source_fingerprint():
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root / 'living_library').glob('*.py'))
    # Vendored prompts are part of the agent and of the frozen settings.
    paths += sorted(p for p in (root / 'living_library' / 'prompts').glob('*') if p.suffix in {'.py', '.json'})
    if (root / 'pyproject.toml').exists():
        paths.append(root / 'pyproject.toml')
    return digest({p.relative_to(root).as_posix(): p.read_text() for p in paths})


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


# The lean design (amended 2026-11-14/15 for local compute, following the proposal's cut order):
# condition B dropped, 300 practice episodes (was 500), 2 evaluation seeds (was 3), and a short
# development pilot (100 practice episodes, 70 of the 140 seen-room games). D is never cut.
# Extension arm E-plus (E + library consolidation) runs alongside, outside the H1-H4 family.
# Held-out data: out-of-distribution = the 134 unseen-room games (whole split held back, primary);
# in-distribution = the 70 seen-room games the pilot never touches (secondary).
# Trimmed 2026-11-15 for compute: one seed everywhere, condition A dropped (the PDF's cut order:
# B, then A); every remaining condition answers H1-H4 or the E-plus extension.
REAL_DESIGN = {'pilot_practice': 100, 'practice_episodes': 300, 'development_games': 70,
               'evaluation_games': 134, 'seeds': 1,
               'conditions': ['C', 'D', 'E', 'E-minus', 'E-text']}
PILOT_CONDITIONS = ('E-minus', 'E')   # memory arms the pilot builds and checks (amended 2026-11-15)


def validate_real_design(cfg, manifest):
    if manifest['environment'] != 'alfworld':
        raise ValueError('pilot/study require an ALFWorld manifest; use demo for fixture data')
    actual = {'pilot_practice': cfg.pilot_practice, 'practice_episodes': cfg.practice_episodes,
              'development_games': cfg.development_games, 'evaluation_games': cfg.evaluation_games,
              'seeds': len(cfg.seeds), 'conditions': list(cfg.conditions)}
    if actual != REAL_DESIGN:
        raise ValueError(f'real design requires {REAL_DESIGN}; got {actual}')
    for split, count in [('development', 140), ('evaluation', 134)]:
        if len(manifest['splits'][split]) != count:
            raise ValueError(f'{split} manifest must contain exactly {count} games')


def stream_spec(condition, phase, seed, tasks, init=None, source=None, init_position=None, frozen=False):
    """One sequential episode stream. `init` names the stream whose final memory (or, with
    `init_position`, its memory after that many episodes) seeds this one; `source` (E-text only)
    names the stream whose per-position pre-task library it reads. A `frozen` stream reads its
    memory without changing it, so its episodes are independent."""
    spec = {'key': f'{phase}-{condition}-{seed}', 'condition': condition, 'phase': phase,
            'seed': seed, 'tasks': tasks, 'init': init, 'source': source}
    if init_position is not None or frozen:
        spec.update(init_position=init_position, frozen=frozen)
    return spec


def memoryless(spec):
    """Streams whose episodes do not depend on each other (no memory, no source): their
    episodes may run in parallel; checkpoints are still committed in order."""
    if spec['source'] is not None:
        return False
    return spec.get('frozen', False) or (spec['condition'] not in MEMORY and spec['init'] is None)


class Runner:
    """Runs independent streams in parallel worker processes, one committed episode at a time
    (memoryless streams run several episodes at once and commit them in order).

    Every finished episode is an atomic checkpoint, so a run can stop at any point (episode or
    hour budget, a STOP file in the output directory, Ctrl-C, a server outage) and resume later.
    Interrupted episodes replay their model calls from the per-stream response cache.
    """
    def __init__(self, cfg, manifest, output, model=None, embedder=None, worker=False):
        validate_manifest(manifest)
        self.cfg, self.manifest, self.output = cfg, manifest, Path(output)
        self.toy = manifest['environment'] == 'mini'
        self.env_factory = MiniWorld if self.toy else ALFWorld
        self.identity = identity(cfg, manifest)
        marker = self.output / 'run.json'
        expected = {'identity': self.identity, 'toy': self.toy, 'environment': manifest['environment']}
        if marker.exists() and load_json(marker) != expected:
            raise ValueError('output belongs to different settings, sources or manifest; choose a new output directory')
        if not worker:
            self.output.mkdir(parents=True, exist_ok=True)
            write_json(marker, expected)
            write_json(self.output / 'settings.json', cfg.to_dict())
        self.fixed_model = model
        self._embedder = embedder
        self.records = []
        self.complete = False

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = (LexicalEmbedding() if self.toy else
                              SentenceEmbedding(self.cfg.embedding, self.cfg.embedding_revision))
        return self._embedder

    def _model(self, key):
        if self.fixed_model is not None:
            return self.fixed_model, False
        from .models import FixtureModel, HTTPModel
        if self.toy:
            return FixtureModel(), True
        return HTTPModel(self.cfg, self.output / 'model-cache' / f'{key}.sqlite'), True

    # -- checkpoints -------------------------------------------------------------------
    def _checkpoint(self, key, position):
        return self.output / 'checkpoints' / key / f'{position:05d}.json'

    def count(self, key):
        """Committed episodes of a stream (contiguous checkpoints from position 0)."""
        directory = self.output / 'checkpoints' / key
        if not directory.exists():
            return 0
        names = {p.name for p in directory.glob('*.json')}
        n = 0
        while f'{n:05d}.json' in names:
            n += 1
        return n

    def _initial(self, spec, specs):
        if spec['init'] is None:
            return {'library': Library(self.cfg).snapshot(), 'trajectories': [], 'rules': []}
        dep = specs[spec['init']]
        needed = spec.get('init_position') or len(dep['tasks'])
        if self.count(dep['key']) < needed:
            raise ValueError(f"{spec['key']} needs {needed} episodes of {dep['key']}")
        return load_json(self._checkpoint(dep['key'], needed - 1))['memory']

    def _stream_identity(self, spec, initial):
        return digest({'identity': self.identity, 'tasks': spec['tasks'], 'condition': spec['condition'],
                       'phase': spec['phase'], 'seed': spec['seed'], 'initial': digest(initial),
                       'source': spec['source']})

    @staticmethod
    def _check(saved, stream_identity, path):
        if (saved['stream_identity'] != stream_identity
                or saved['record_hash'] != digest(saved['record'])
                or saved['memory_hash'] != digest(saved['memory'])
                or saved['pre_library_hash'] != digest(saved['pre_library'])):
            raise ValueError(f'incompatible/corrupt checkpoint {path}; choose a fresh output directory')

    # -- one stream --------------------------------------------------------------------
    def advance(self, spec, specs, max_new=None, should_stop=None):
        """Commit up to `max_new` further episodes of one stream; returns the new records."""
        from .agents import Agent
        if self.batched(spec):      # same games and merge order as the parallel scheduler
            new = []
            while self.count(spec['key']) < len(spec['tasks']):
                if (max_new is not None and len(new) >= max_new) or (should_stop and should_stop()):
                    break
                position = self.count(spec['key'])
                new.append(self.commit_game(spec, specs, position, self.run_game(spec, specs, position)))
            return new
        cfg, key, tasks = self.cfg, spec['key'], spec['tasks']
        initial = self._initial(spec, specs)
        sid = self._stream_identity(spec, initial)
        start = self.count(key)
        if start:
            path = self._checkpoint(key, start - 1)
            saved = load_json(path)
            self._check(saved, sid, path)
            memory, previous_hash = saved['memory'], digest(saved['record'])
        else:
            memory, previous_hash = initial, None
        library = Library.restore(copy.deepcopy(memory['library']), cfg)
        trajectories = copy.deepcopy(memory['trajectories'])
        rules = copy.deepcopy(memory.get('rules', []))
        limit = len(tasks) if spec['source'] is None else min(len(tasks), self.count(spec['source']))
        model, owned = self._model(key)
        new = []
        try:
            for position in range(start, limit):
                if (max_new is not None and len(new) >= max_new) or (should_stop and should_stop()):
                    break
                task = tasks[position]
                source_hash = None
                if spec['source'] is not None:
                    source = load_json(self._checkpoint(spec['source'], position))
                    if source['record']['task_id'] != task['id']:
                        raise ValueError(f"{key} is not task-matched with {spec['source']}")
                    library = Library.restore(copy.deepcopy(source['pre_library']), cfg)
                    source_hash = source['pre_library_hash']
                pre = library.snapshot()
                context = {'condition': spec['condition'], 'phase': spec['phase'], 'seed': spec['seed'],
                           'task_id': task['id'], 'position': position, 'toy': self.toy}
                result = Agent(cfg, spec['condition'], model, library, self.embedder,
                               self.env_factory, trajectories=trajectories, rules=rules,
                               frozen=spec.get('frozen', False)).run(task, spec['seed'], context)
                record = {**result, **context}
                if (spec['condition'] == 'E-text' or spec.get('frozen')) and library.snapshot() != pre:
                    raise ValueError(f"{key} mutated its read-only library")
                if spec['condition'] == 'D' and spec['phase'] == 'practice' and record['success']:
                    trajectories.append({'task': task, 'goal': record.get('goal', ''),
                                         'trace': record['trace'], 'success': True})
                memory = {'library': library.snapshot(), 'trajectories': copy.deepcopy(trajectories),
                          'rules': copy.deepcopy(rules)}
                write_json(self._checkpoint(key, position), {
                    'stream_identity': sid, 'previous_hash': previous_hash, 'source_hash': source_hash,
                    'pre_library': pre, 'pre_library_hash': digest(pre),
                    'memory': memory, 'memory_hash': digest(memory),
                    'record': record, 'record_hash': digest(record)})
                previous_hash = digest(record)
                new.append(record)
        finally:
            if owned:
                model.close()
        return new

    def run_at(self, spec, specs, position):
        """Run one episode of a memoryless stream without committing it (parallel workers)."""
        from .agents import Agent
        if not memoryless(spec):
            raise ValueError(f"{spec['key']} has memory; its episodes must run in order")
        initial = self._initial(spec, specs)
        library = Library.restore(copy.deepcopy(initial['library']), self.cfg)
        pre = library.snapshot()
        task = spec['tasks'][position]
        context = {'condition': spec['condition'], 'phase': spec['phase'], 'seed': spec['seed'],
                   'task_id': task['id'], 'position': position, 'toy': self.toy}
        model, owned = self._model(spec['key'])
        try:
            result = Agent(self.cfg, spec['condition'], model, library, self.embedder,
                           self.env_factory, trajectories=copy.deepcopy(initial['trajectories']),
                           frozen=spec.get('frozen', False),
                           rules=copy.deepcopy(initial.get('rules', []))).run(task, spec['seed'], context)
        finally:
            if owned:
                model.close()
        if library.snapshot() != pre:
            raise ValueError(f"memoryless/frozen stream {spec['key']} changed its library")
        return {**result, **context}

    # -- batched practice (cfg.practice_batch games at once; see batching.py) -------------
    def batched(self, spec):
        return (self.cfg.practice_batch > 1 and spec['phase'] == 'practice'
                and spec['condition'] in MEMORY and not spec.get('frozen') and spec['source'] is None)

    def _memory_after(self, spec, specs, position):
        """Memory after `position` episodes of the stream (0 = its initial memory)."""
        if position == 0:
            return self._initial(spec, specs)
        return load_json(self._checkpoint(spec['key'], position - 1))['memory']

    def run_game(self, spec, specs, position):
        """One game of a batch, run on the memory as it was at the start of its batch."""
        from .agents import Agent
        k = self.cfg.practice_batch
        base = self._memory_after(spec, specs, position - position % k)
        library = Library.restore(copy.deepcopy(base['library']), self.cfg)
        trajectories = copy.deepcopy(base['trajectories'])
        rules = copy.deepcopy(base.get('rules', []))
        task = spec['tasks'][position]
        context = {'condition': spec['condition'], 'phase': spec['phase'], 'seed': spec['seed'],
                   'task_id': task['id'], 'position': position, 'toy': self.toy}
        model, owned = self._model(spec['key'])
        try:
            result = Agent(self.cfg, spec['condition'], model, library, self.embedder, self.env_factory,
                           trajectories=trajectories, rules=rules).run(task, spec['seed'], context)
        finally:
            if owned:
                model.close()
        record = {**result, **context}
        if spec['condition'] == 'D' and record['success']:
            trajectories.append({'task': task, 'goal': record.get('goal', ''),
                                 'trace': record['trace'], 'success': True})
        return {'record': record, 'base': base,
                'end': {'library': library.snapshot(), 'trajectories': trajectories, 'rules': rules}}

    def commit_game(self, spec, specs, position, game):
        """Merge one finished game into the live memory (fixed position order) and checkpoint it."""
        from .batching import merge_memory
        key = spec['key']
        if self.count(key) != position:
            raise ValueError(f'{key}: commit of position {position} out of order')
        initial = self._initial(spec, specs)
        sid = self._stream_identity(spec, initial)
        live = self._memory_after(spec, specs, position)
        previous_hash = None
        if position:
            path = self._checkpoint(key, position - 1)
            self._check(load_json(path), sid, path)
            previous_hash = digest(load_json(path)['record'])
        merge_log = []
        memory = merge_memory(live, game['base'], game['end'], merge_log,
                              game['record'].get('manual', {}).get('operations', []))
        record = {**game['record'], 'batch_merge': merge_log}
        pre = game['base']['library']
        write_json(self._checkpoint(key, position), {
            'stream_identity': sid, 'previous_hash': previous_hash, 'source_hash': None,
            'pre_library': pre, 'pre_library_hash': digest(pre),
            'memory': memory, 'memory_hash': digest(memory),
            'record': record, 'record_hash': digest(record)})
        return record

    def commit(self, spec, specs, position, record):
        """Append a memoryless episode computed by run_at; positions must arrive in order."""
        key = spec['key']
        if self.count(key) != position:
            raise ValueError(f'{key}: commit of position {position} out of order')
        initial = self._initial(spec, specs)
        sid = self._stream_identity(spec, initial)
        previous_hash = None
        if position:
            path = self._checkpoint(key, position - 1)
            saved = load_json(path)
            self._check(saved, sid, path)
            previous_hash = digest(saved['record'])
        memory = copy.deepcopy(initial)
        write_json(self._checkpoint(key, position), {
            'stream_identity': sid, 'previous_hash': previous_hash, 'source_hash': None,
            'pre_library': memory['library'], 'pre_library_hash': digest(memory['library']),
            'memory': memory, 'memory_hash': digest(memory),
            'record': record, 'record_hash': digest(record)})

    def verify(self, spec, specs):
        """Full chain check of a stream's checkpoints; returns its records in order."""
        sid = self._stream_identity(spec, self._initial(spec, specs))
        records, previous_hash = [], None
        for position in range(self.count(spec['key'])):
            path = self._checkpoint(spec['key'], position)
            saved = load_json(path)
            self._check(saved, sid, path)
            if (saved['previous_hash'] != previous_hash
                    or saved['record']['task_id'] != spec['tasks'][position]['id']):
                raise ValueError(f'incompatible/corrupt checkpoint {path}; choose a fresh output directory')
            if spec['source'] is not None:
                source = load_json(self._checkpoint(spec['source'], position))
                if saved['source_hash'] != source['pre_library_hash'] or saved['pre_library'] != source['pre_library']:
                    raise ValueError(f'incompatible/corrupt checkpoint {path}; choose a fresh output directory')
            records.append(saved['record'])
            previous_hash = digest(saved['record'])
        return records

    # -- scheduling --------------------------------------------------------------------
    def _plan(self, specs):
        """Remember every stream this output directory has run, so records accumulate."""
        path = self.output / 'plan.json'
        plan = load_json(path) if path.exists() else []
        known = {s['key'] for s in plan}
        plan += [s for s in specs if s['key'] not in known]
        write_json(path, plan)
        return {s['key']: s for s in plan}

    def ready(self, spec, specs):
        """Episodes this stream can run right now (0 if finished or blocked)."""
        done = self.count(spec['key'])
        if done >= len(spec['tasks']):
            return 0
        if spec['init'] is not None and self.count(spec['init']) < (
                spec.get('init_position') or len(specs[spec['init']]['tasks'])):
            return 0
        if spec['source'] is not None:
            return max(0, min(len(spec['tasks']), self.count(spec['source'])) - done)
        return len(spec['tasks']) - done

    def execute(self, specs, workers=1, max_episodes=None, max_hours=None, log=print):
        """Run streams until done or a budget/STOP file ends this session. True if all done."""
        specs = self._plan(specs)
        order = list(specs)
        stop_file = self.output / 'STOP'
        if stop_file.exists():
            stop_file.unlink()
        started = time.monotonic()
        state = {'new': 0, 'error': None}

        def stopping():
            return (state['error'] is not None or stop_file.exists()
                    or (max_hours is not None and time.monotonic() - started >= max_hours * 3600)
                    or (max_episodes is not None and state['new'] >= max_episodes))

        def report(key, records):
            state['new'] += len(records)
            for r in records:
                rate = state['new'] / max(1e-9, (time.monotonic() - started) / 3600)
                log(f"{time.strftime('%H:%M:%S')} {key} {r['position'] + 1}/{len(specs[key]['tasks'])} "
                    f"{'WIN ' if r['success'] else 'fail'} calls={r['model_calls']} "
                    f"| session {state['new']} eps, {rate:.0f}/h")

        def priority(key):
            # Streams others wait on first (practice, E before E-text), then the longest.
            waiting = sum(s['init'] == key or s['source'] == key for s in specs.values())
            return (-waiting, -(len(specs[key]['tasks']) - self.count(key)), order.index(key))

        if workers <= 1:
            while not stopping():
                runnable = [k for k in order if self.ready(specs[k], specs)]
                if not runnable:
                    break
                remaining = None if max_episodes is None else max_episodes - state['new']
                key = runnable[0]
                report(key, self.advance(specs[key], specs, remaining, stopping))
        else:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
            running = {}                      # future -> (key, position or None)
            pending = {}                      # memoryless key -> {position: record} awaiting commit
            # Batched practice streams (the critical path) fill workers first, then memoryless ones.
            batched = [k for k in order if self.batched(specs[k])]
            parallel = batched + [k for k in order if memoryless(specs[k])]
            next_position = {k: self.count(k) for k in parallel}

            def limit(key):
                """Positions dispatchable now: a memoryless stream all; a batched one its round."""
                n = len(specs[key]['tasks'])
                if key not in batched:
                    return n
                k = self.cfg.practice_batch
                return min(n, (self.count(key) // k) * k + k)

            def flush(key):
                buffer, committed = pending.get(key, {}), []
                while self.count(key) in buffer:
                    position = self.count(key)
                    result = buffer.pop(position)
                    if key in batched:
                        record = self.commit_game(specs[key], specs, position, result)
                    else:
                        record = result
                        self.commit(specs[key], specs, position, record)
                    committed.append(record)
                if committed:
                    report(key, committed)

            with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context('spawn'),
                                     initializer=_worker_init,
                                     initargs=(self.cfg.to_dict(), self.manifest, str(self.output))) as pool:
                try:
                    while True:
                        if not stopping():
                            # Streams with memory run one episode at a time and go first: they are
                            # the critical path. Memoryless streams fill the remaining workers.
                            busy = {k for k, _ in running.values()}
                            candidates = [k for k in order if k not in busy and k not in parallel
                                          and self.ready(specs[k], specs)]
                            for key in sorted(candidates, key=priority):
                                if len(running) >= workers:
                                    break
                                running[pool.submit(_worker_advance, specs[key], specs)] = (key, None)
                            filling = True
                            while filling and len(running) < workers:
                                filling = False
                                for key in parallel:
                                    if len(running) >= workers:
                                        break
                                    budget = (None if max_episodes is None else
                                              max_episodes - state['new'] - len(running))
                                    if (next_position[key] < limit(key)
                                            and (budget is None or budget > 0)
                                            and self.ready(specs[key], specs)):   # e.g. milestone reached
                                        work = _worker_run_game if key in batched else _worker_run_at
                                        running[pool.submit(work, specs[key], specs,
                                                            next_position[key])] = (key, next_position[key])
                                        next_position[key] += 1
                                        filling = True
                        if not running:
                            break
                        finished, _ = wait(running, return_when=FIRST_COMPLETED)
                        for future in finished:
                            key, position = running.pop(future)
                            try:
                                if position is None:
                                    report(key, future.result())
                                else:
                                    pending.setdefault(key, {})[position] = future.result()
                                    flush(key)
                            except Exception as exc:  # stop scheduling; let in-flight episodes commit
                                state['error'] = state['error'] or exc
                                log(f'{key} stopped: {exc!r}')
                except KeyboardInterrupt:
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
        if state['error'] is not None:
            raise state['error']
        complete = all(self.count(k) >= len(specs[k]['tasks']) for k in order)
        if complete:
            self.records = [r for key in order for r in self.verify(specs[key], specs)]
        else:
            self.records = [r for key in order for r in self._records(key)]
        write_json(self.output / 'records.json', self.records)
        log(f"session: {state['new']} new episodes in {(time.monotonic() - started) / 60:.1f} min; "
            f"{sum(min(self.count(k), len(specs[k]['tasks'])) for k in order)}/"
            f"{sum(len(specs[k]['tasks']) for k in order)} episodes done"
            + ('' if complete else ' (run the same command again to continue)'))
        return complete

    def _records(self, key):
        return [load_json(self._checkpoint(key, i))['record'] for i in range(self.count(key))]

    def status(self):
        path = self.output / 'plan.json'
        rows = []
        for spec in (load_json(path) if path.exists() else []):
            records = self._records(spec['key'])
            rows.append({'stream': spec['key'], 'done': len(records), 'total': len(spec['tasks']),
                         'success': sum(r['success'] for r in records)})
        return rows

    def workflow(self, name):
        marker = self.output / 'workflow.json'
        if marker.exists() and load_json(marker) != {'workflow': name}:
            raise ValueError('pilot and study require separate output directories')
        write_json(marker, {'workflow': name})

    def study_specs(self, conditions=None, demo_count=None):
        conditions = tuple(self.cfg.conditions if conditions is None else conditions)
        if any(c not in CONDITIONS for c in conditions) or len(set(conditions)) != len(conditions):
            raise ValueError('conditions must be unique valid condition IDs')
        # E is a required source for the task-matched E-text snapshot comparison.
        run_conditions = set(conditions) | ({'E'} if 'E-text' in conditions else set())
        pseed = self.cfg.practice_seed
        practice = ordered(self.manifest['splits']['practice'], pseed,
                           demo_count or self.cfg.practice_episodes, repeat=True)
        specs = [stream_spec(c, 'practice', pseed, practice)
                 for c in CONDITIONS if c in run_conditions and c in MEMORY]
        id_pool = self.id_evaluation_pool()
        for phase, full in (('evaluation', self.manifest['splits']['evaluation']), ('id-evaluation', id_pool)):
            if not full:
                continue
            for condition in CONDITIONS:
                if condition not in run_conditions:
                    continue
                for seed in (self.cfg.seeds[:1] if condition in {'A', 'B'} else self.cfg.seeds):
                    pool = full if demo_count is None else full[:demo_count]
                    count = (demo_count or self.cfg.evaluation_games) if phase == 'evaluation' else (demo_count or len(pool))
                    tasks = ordered(pool, seed, min(count, len(pool)) if phase == 'id-evaluation' else count)
                    # Evaluation reads each condition's practice memory frozen (amended 2026-11-15):
                    # every test episode is independent, so they all run in parallel. E-text reads
                    # E's frozen practice library rendered as text.
                    source_memory = 'E' if condition == 'E-text' else condition
                    has_memory = condition in MEMORY or condition == 'E-text'
                    specs.append(stream_spec(condition, phase, seed, tasks,
                        init=f'practice-{source_memory}-{pseed}' if has_memory else None,
                        frozen=has_memory))
        # Practice-length curve: frozen libraries at milestones on fixed ID/OOD subsets.
        seed = self.cfg.seeds[0]
        subsets = [('ood', self.manifest['splits']['evaluation']), ('id', id_pool)]
        for milestone in ([] if demo_count is not None else self.cfg.snapshot_milestones):
            for condition in self.cfg.snapshot_conditions:
                if condition not in run_conditions:
                    continue
                for name, pool in subsets:
                    if pool:
                        tasks = ordered(pool, seed, min(self.cfg.snapshot_games, len(pool)))
                        specs.append(stream_spec(condition, f'snapshot-{milestone}-{name}', seed, tasks,
                                                 init=f'practice-{condition}-{pseed}', init_position=milestone,
                                                 frozen=True))
        return specs

    def pilot_development(self):
        games = self.manifest['splits'].get('development', [])
        return ordered(games, self.cfg.seeds[0], min(self.cfg.development_games, len(games)))

    def id_evaluation_pool(self):
        """Seen-room games the pilot never touched: the in-distribution test set."""
        used = {t['id'] for t in self.pilot_development()}
        pool = [t for t in self.manifest['splits'].get('development', []) if t['id'] not in used]
        assert not used & {t['id'] for t in pool}
        return pool

    def study(self, conditions=None, demo_count=None, freeze_path=None, workers=1,
              max_episodes=None, max_hours=None, reuse_pilot=None, log=print):
        if not self.toy:
            if freeze_path is None:
                raise ValueError("real study requires --freeze from a passing real pilot")
            verify_freeze(self.cfg, self.manifest, freeze_path)
        self.workflow('study')
        if not self.toy and demo_count is not None:
            raise ValueError('sample count overrides are available only in demo')
        specs = self.study_specs(conditions, demo_count)
        if reuse_pilot is not None:
            self._reuse_pilot_cache(Path(reuse_pilot), log)
        write_json(self.output / 'cost_attribution.json', {
            'E-text': {'practice_source': 'E', 'charge_full_E_practice_cost': True},
            'practice_shared_across_evaluation_seeds': True, 'practice_seed': self.cfg.practice_seed})
        self.complete = self.execute(specs, workers, max_episodes, max_hours, log)
        return self.records

    def _reuse_pilot_cache(self, pilot_dir, log):
        """Study E-minus / E-plus practice begins with the pilot's practice episodes (same seed,
        order, settings and code), so their model responses replay from the pilot's cache."""
        import shutil
        for condition in PILOT_CONDITIONS:
            key = f'practice-{condition}-{self.cfg.practice_seed}'
            source = pilot_dir / 'model-cache' / f'{key}.sqlite'
            target = self.output / 'model-cache' / f'{key}.sqlite'
            if source.exists() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                log(f'reusing pilot model responses for {key}')

    def pilot_specs(self):
        pseed, seed = self.cfg.practice_seed, self.cfg.seeds[0]
        practice = ordered(self.manifest['splits']['practice'], pseed, self.cfg.pilot_practice, repeat=True)
        dev = self.pilot_development()
        specs = [stream_spec('C', 'development', seed, dev)]
        for c in PILOT_CONDITIONS:
            specs += [stream_spec(c, 'practice', pseed, practice),
                      # Frozen: the development test reads the practice library without learning,
                      # so all its games run in parallel.
                      stream_spec(c, 'development', seed, dev, init=f'practice-{c}-{pseed}', frozen=True)]
        return specs

    def pilot(self, workers=1, max_episodes=None, max_hours=None, log=print):
        self.workflow('pilot')
        validate_real_design(self.cfg, self.manifest)
        self.complete = self.execute(self.pilot_specs(), workers, max_episodes, max_hours, log)
        if not self.complete:
            return None
        evidence = {'identity': self.identity, 'toy': False, 'records_hash': digest(self.records),
                    'gate': pilot_gate(self.records, self.cfg)}
        write_json(self.output / 'pilot-evidence.json', evidence)
        return evidence


_WORKER = None


def _worker_init(cfg, manifest, output):
    global _WORKER
    _WORKER = Runner(Settings(**cfg), manifest, output, worker=True)


def _worker_advance(spec, specs):
    return _WORKER.advance(spec, specs, max_new=1)


def _worker_run_at(spec, specs, position):
    return _WORKER.run_at(spec, specs, position)


def _worker_run_game(spec, specs, position):
    return _WORKER.run_game(spec, specs, position)


def pilot_gate(records, cfg):
    from .analysis import pilot_report
    practice = [r for r in records if r['phase'] == 'practice' and r['condition'] == 'E-minus']
    baseline = [r for r in records if r['phase'] == 'development' and r['condition'] == 'C']
    memory = [r for r in records if r['phase'] == 'development' and r['condition'] == 'E-minus']
    n_dev = cfg.development_games
    plus = [r for r in records if r['condition'] == 'E-plus']
    complete = (len(records) == len(PILOT_CONDITIONS) * (cfg.pilot_practice + n_dev) + n_dev
                and len(plus) == cfg.pilot_practice + n_dev and len(practice) == cfg.pilot_practice
                and len(baseline) == n_dev and len(memory) == n_dev
                and not any(r.get('toy', True) for r in records)
                and len({r['task_id'] for r in baseline}) == n_dev
                and {r['task_id'] for r in baseline} == {r['task_id'] for r in memory})
    report = pilot_report(practice, baseline, memory, cfg)
    # E-plus is an extension arm: reported with the same measures, never part of the gate.
    extension = pilot_report([r for r in plus if r['phase'] == 'practice'], baseline,
                             [r for r in plus if r['phase'] == 'development'], cfg)
    return {'passed': complete and report['ready'], 'complete_real_pilot': complete, 'report': report,
            'extension_E_plus': extension}


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
