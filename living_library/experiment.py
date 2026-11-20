"""Opt-in experiment orchestration with split guards and atomic episode checkpoints."""
import copy
import json
from pathlib import Path
import random
import time

from .config import CONDITIONS, MEMORY, Settings, digest, write_json
from .embedding import LexicalEmbedding, SentenceEmbedding
from .environments import ALFWorld, MiniWorld, demo_manifest, validate_manifest


def source_files():
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root / 'living_library').glob('*.py'))
    # Vendored prompts are part of the agent and of the frozen settings.
    paths += sorted(p for p in (root / 'living_library' / 'prompts').glob('*') if p.suffix in {'.py', '.json'})
    if (root / 'pyproject.toml').exists():
        paths.append(root / 'pyproject.toml')
    return {p.relative_to(root).as_posix(): p.read_text() for p in paths}


def source_fingerprint():
    return digest(source_files())


def source_hashes():
    """Per-file digests, so a library restart can tell which files changed."""
    return {path: digest(text) for path, text in source_files().items()}


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


# The study design (redesign 2026-11-20, protocol.py): C, D, E, E-minus; 300 practice games per memory
# condition and practice replicate (two replicates, own game orders); one evaluation seed; OOD test = the 134
# unseen-room games (primary), ID test = the 70 seen-room games outside the development set (secondary).
REAL_DESIGN = {'practice_episodes': 300, 'development_games': 70, 'evaluation_games': 134, 'seeds': 1,
               'practice_seeds': 2, 'conditions': ['C', 'D', 'E', 'E-minus']}
# Conditions built on the library code: a library restart discards their streams and everything
# derived from them, keeping C's and D's games (amended 2026-11-17, early gate).
LIBRARY_CONDITIONS = ('E', 'E-minus')
# Source files only the library conditions use; a change anywhere else invalidates C and D too.
LIBRARY_SOURCES = ('living_library/manual.py', 'living_library/avoid.py')
# Shared files a restart may also accept changed (amended 2026-11-17, practice retries; protocol.py holds
# only the pre-registration text): only when the baseline probe (every model request and every record of
# a fixture C and D study) is identical to the probe taken with the run's recorded sources (probe.json).
# Any other changed file still refuses.
PROBED_SOURCES = ('living_library/agents.py', 'living_library/experiment.py', 'living_library/protocol.py',
                  'living_library/batching.py')
# Command-line parsing only (amended 2026-11-19, --restart-streams): never changes an episode.
ENTRY_SOURCES = ('living_library/cli.py',)
# Streams a partial restart may discard (amended 2026-11-19): E alone (every replicate), keeping C, D and E-minus.
RESTARTABLE = ('E',)
# Conditions whose batched practice runs the deterministic manual upkeep (useless retirement, near-duplicate
# merge, capacity pruning) at the end of each batch (LIBRARY-SPEC.md section 5). Not E-minus: it never manages.
UPKEEP_CONDITIONS = ('E',)
# Early gate (a bug detector, not evidence): stop if E wins - C wins < GATE_MARGIN on the gate games.
GATE_MARGIN = -3


def stream_key(condition, phase, seed, replicate=None):
    """practice-{condition}-{practice seed}; {phase}-{condition}-r{replicate}-{seed} for a stream that reads a
    replicate's memory; {phase}-{condition}-{seed} otherwise (C, A). Records carry all four fields."""
    tag = f'r{replicate}-' if replicate is not None and phase != 'practice' else ''
    return f'{phase}-{condition}-{tag}{seed}'


def practice_key(condition, pseed):
    return stream_key(condition, 'practice', pseed, pseed)


def e_minus_probe(cfg, games=4):
    """Digest of E-minus's behaviour under `cfg` on the fixture world (practice of every replicate, batched as
    configured, then its frozen evaluations): every model request, every record (timings removed), the final
    rules, the Builder instructions E-minus gets for every case and the shared rule-text check."""
    import tempfile
    from . import manual
    from .models import FixtureModel
    requests = []

    class Recorder:
        def __init__(self):
            self.inner = FixtureModel()

        def complete(self, role, payload, seed, context):
            requests.append(digest([role, payload, seed, context]))
            return self.inner.complete(role, payload, seed, context)

        def close(self):
            pass

    def untimed(value):
        if isinstance(value, dict):
            return {k: untimed(v) for k, v in value.items()
                    if k not in ('wall_seconds', 'model_wall_seconds', 'gpu_seconds')}
        if isinstance(value, list):
            return [untimed(v) for v in value]
        return value
    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(cfg, demo_manifest(), tmp, model=Recorder(), embedder=LexicalEmbedding(), probe=False)
        records = runner.study(('E-minus',), demo_count=games, log=lambda *a, **k: None)
        rules = {}
        for pseed in cfg.practice_seeds:
            last = sorted((Path(tmp) / 'checkpoints' / practice_key('E-minus', pseed)).glob('*.json'))
            rules[pseed] = load_json(last[-1])['memory']['rules'] if last else []
    guides = {case: manual.builder_guide(case, True, 'pick_and_place_simple', [])
              for case in sorted(manual.CASE_TYPES)}
    guides['retry'] = manual.RETRY_NOTE
    guides['reflect'] = manual.REFLECT_GUIDE
    # The shared rule-text check (amended 2026-11-20): the fixture Builder never writes text it would change,
    # so it is probed directly, with a fixed model rewrite, on texts that name numbered objects, are too long
    # or list steps.
    asked = []

    def ask(role, payload):
        asked.append(digest([role, payload]))
        return {'rule': 'When an object must be heated, heat it with the appliance before placing it.'}
    checks = []
    for kind, text in (('Special Phenomenon', 'When heating, heat it with microwave 1.'),
                       ('Special Phenomenon', 'When at drawer 3, open drawer 3 first.'),
                       ('Success Process', 'When placing: go to countertop 2, take apple 1, put it in the target.'),
                       ('Corrected Error', 'When the target is full, ' + 'try another place and open it, ' * 8),
                       ('Special Phenomenon', 'When cooling: take it, go to the fridge, open it, then cool it.'),
                       ('Special Phenomenon', 'If a container is closed, open it before putting things in it.')):
        try:
            checks.append(manual.checked(kind, text, ask, 'pick_heat_then_place_in_recep'))
        except ValueError as exc:
            checks.append(f'rejected: {exc}')
    return digest({'requests': requests, 'records': untimed(records), 'rules': rules, 'guides': guides,
                   'checks': checks, 'check_requests': asked})


def e_minus_replay_check(cfg, output):
    """The stored E-minus practice of a run (every replicate), replayed: every checkpoint's rules must equal the
    current code's replay of that game's stored manual operations onto the previous checkpoint's rules (batched
    practice). Returns (games checked, None) or (games checked, the first mismatch)."""
    from .manual import replay
    k, checked = cfg.practice_batch, 0
    if k <= 1:
        return 0, None
    for pseed in cfg.practice_seeds:
        key = practice_key('E-minus', pseed)
        root = Path(output) / 'checkpoints' / key
        memories, position = [], 0
        while (root / f'{position:05d}.json').exists():
            saved = load_json(root / f'{position:05d}.json')
            rules = lambda p: [] if p < 0 else memories[p]
            live, base = rules(position - 1), rules(position - position % k - 1)
            ops = saved['record'].get('manual', {}).get('operations', [])
            got = json.loads(json.dumps(replay(live, ops, [], base)))
            if got != saved['memory']['rules']:
                return checked, f'{key} game {position}: replaying its stored operations gives different rules'
            memories.append(saved['memory']['rules'])
            position += 1
            checked += 1
    return checked, None


def stored_e_minus_probe(cfg, output, recorded_sources):
    """The E-minus probe taken with the run's recorded sources and settings (probe.json); None if there is none."""
    path = Path(output) / 'probe.json'
    saved = load_json(path).get('e_minus') if path.exists() else None
    want = {'sources': digest(recorded_sources), 'settings': digest(cfg.to_dict())}
    if saved and {k: saved.get(k) for k in want} == want:
        return saved['probe']
    return None


def baseline_probe(cfg, games=4):
    """Digest of C's and D's behaviour under `cfg` on the fixture world (practice D, evaluation C and
    D, batched as configured): every request sent to the model and every record (timings removed).
    The fixture model ignores most of a prompt, so the requests are what catch prompt changes."""
    import tempfile
    from .models import FixtureModel
    requests = []

    class Recorder:
        def __init__(self):
            self.inner = FixtureModel()

        def complete(self, role, payload, seed, context):
            requests.append(digest([role, payload, seed, context]))
            return self.inner.complete(role, payload, seed, context)

        def close(self):
            pass
    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(cfg, demo_manifest(), tmp, model=Recorder(), embedder=LexicalEmbedding(), probe=False)
        records = runner.study(('C', 'D'), demo_count=games, log=lambda *a, **k: None)
    timing = {'wall_seconds', 'model_wall_seconds', 'gpu_seconds'}
    return digest({'requests': requests,
                   'records': [{k: v for k, v in r.items() if k not in timing} for r in records]})


def validate_real_design(cfg, manifest):
    if manifest['environment'] != 'alfworld':
        raise ValueError('the study requires an ALFWorld manifest; use demo for fixture data')
    actual = {'practice_episodes': cfg.practice_episodes, 'development_games': cfg.development_games,
              'evaluation_games': cfg.evaluation_games, 'seeds': len(cfg.seeds),
              'practice_seeds': len(cfg.practice_seeds), 'conditions': list(cfg.conditions)}
    if actual != REAL_DESIGN:
        raise ValueError(f'real design requires {REAL_DESIGN}; got {actual}')
    for split, count in [('development', 140), ('evaluation', 134)]:
        if len(manifest['splits'][split]) != count:
            raise ValueError(f'{split} manifest must contain exactly {count} games')


def stream_spec(condition, phase, seed, tasks, init=None, init_position=None, frozen=False, replicate=None):
    """One sequential episode stream. `init` names the stream whose final memory (or, with
    `init_position`, its memory after that many episodes) seeds this one. A `frozen` stream reads its
    memory without changing it, so its episodes are independent. `replicate` is the practice seed whose
    library (or trajectories) the stream builds or reads; None for memoryless conditions (key: stream_key)."""
    spec = {'key': stream_key(condition, phase, seed, replicate), 'condition': condition, 'phase': phase,
            'seed': seed, 'replicate': replicate, 'tasks': tasks, 'init': init}
    if init_position is not None or frozen:
        spec.update(init_position=init_position, frozen=frozen)
    return spec


def memoryless(spec):
    """Streams whose episodes do not depend on each other (frozen memory or no memory): their
    episodes may run in parallel; checkpoints are still committed in order."""
    return spec.get('frozen', False) or (spec['condition'] not in MEMORY and spec['init'] is None)


EMPTY = {'trajectories': [], 'rules': []}


class Runner:
    """Runs independent streams in parallel worker processes, one committed episode at a time
    (memoryless streams run several episodes at once and commit them in order).

    Every finished episode is an atomic checkpoint, so a run can stop at any point (episode or
    hour budget, a STOP file in the output directory, Ctrl-C, a server outage) and resume later.
    Interrupted episodes replay their model calls from the per-stream response cache.
    """
    def __init__(self, cfg, manifest, output, model=None, embedder=None, worker=False, probe=True):
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
            sources = source_hashes()
            write_json(self.output / 'sources.json', sources)
            path = self.output / 'probe.json'
            if probe and (not path.exists() or load_json(path).get('sources') != digest(sources)):
                saved = {'sources': digest(sources), 'probe': baseline_probe(cfg)}
                if 'E-minus' in cfg.conditions:     # lets a later E-only restart keep E-minus (restart_library)
                    saved['e_minus'] = {'sources': digest(sources), 'settings': digest(cfg.to_dict()),
                                        'probe': e_minus_probe(cfg)}
                write_json(path, saved)
        self.fixed_model = model
        self._embedder = embedder
        self.records = []
        self.complete = False
        self.gate = None
        self._caps = {}

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

    def _agent(self, spec, model, memory, frozen):
        from .agents import Agent
        return Agent(self.cfg, spec['condition'], model, self.embedder, self.env_factory,
                     trajectories=memory['trajectories'], rules=memory['rules'], frozen=frozen)

    def _context(self, spec, position):
        return {'condition': spec['condition'], 'phase': spec['phase'], 'seed': spec['seed'],
                'replicate': spec['replicate'], 'task_id': spec['tasks'][position]['id'],
                'position': position, 'toy': self.toy}

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
            return copy.deepcopy(EMPTY)
        dep = specs[spec['init']]
        needed = spec.get('init_position') or len(dep['tasks'])
        if self.count(dep['key']) < needed:
            raise ValueError(f"{spec['key']} needs {needed} episodes of {dep['key']}")
        return load_json(self._checkpoint(dep['key'], needed - 1))['memory']

    def _stream_identity(self, spec, initial):
        return digest({'identity': self.identity, 'tasks': spec['tasks'], 'condition': spec['condition'],
                       'phase': spec['phase'], 'seed': spec['seed'], 'replicate': spec['replicate'],
                       'initial': digest(initial)})

    @staticmethod
    def _check(saved, stream_identity, path):
        if (saved['stream_identity'] != stream_identity
                or saved['record_hash'] != digest(saved['record'])
                or saved['memory_hash'] != digest(saved['memory'])):
            raise ValueError(f'incompatible/corrupt checkpoint {path}; choose a fresh output directory')

    def _write(self, key, position, sid, previous_hash, memory, record):
        write_json(self._checkpoint(key, position), {
            'stream_identity': sid, 'previous_hash': previous_hash,
            'memory': memory, 'memory_hash': digest(memory), 'record': record, 'record_hash': digest(record)})

    def hold(self, spec, memory, note):
        """Commit a one-game holder stream that only carries `memory` (offline checks read it frozen with
        init_position=1). False if the stream already holds a different memory."""
        path = self._checkpoint(spec['key'], 0)
        if path.exists():
            return load_json(path)['memory_hash'] == digest(memory)
        record = {'success': False, 'task_id': spec['tasks'][0]['id'], 'position': 0, 'note': note}
        sid = self._stream_identity(spec, self._initial(spec, {spec['key']: spec}))
        self._write(spec['key'], 0, sid, None, memory, record)
        return True

    # -- one stream --------------------------------------------------------------------
    def advance(self, spec, specs, max_new=None, should_stop=None):
        """Commit up to `max_new` further episodes of one stream; returns the new records."""
        if self.batched(spec):      # same games and merge order as the parallel scheduler
            new = []
            while self.count(spec['key']) < len(spec['tasks']):
                if (max_new is not None and len(new) >= max_new) or (should_stop and should_stop()):
                    break
                position = self.count(spec['key'])
                new.append(self.commit_game(spec, specs, position, self.run_game(spec, specs, position)))
            return new
        key, tasks, frozen = spec['key'], spec['tasks'], spec.get('frozen', False)
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
        memory = copy.deepcopy(memory)
        model, owned = self._model(key)
        new = []
        try:
            for position in range(start, len(tasks)):
                if (max_new is not None and len(new) >= max_new) or (should_stop and should_stop()):
                    break
                task = tasks[position]
                context = self._context(spec, position)
                result = self._agent(spec, model, memory, frozen).run(task, spec['seed'], context)
                record = {**result, **context}
                if frozen and memory != initial:
                    raise ValueError(f"{key} mutated its read-only memory")
                if spec['condition'] == 'D' and spec['phase'] == 'practice' and record['success']:
                    memory['trajectories'].append({'task': task, 'goal': record.get('goal', ''),
                                                   'trace': record['trace'], 'success': True})
                self._write(key, position, sid, previous_hash, memory, record)
                previous_hash = digest(record)
                new.append(record)
        finally:
            if owned:
                model.close()
        return new

    def run_at(self, spec, specs, position):
        """Run one episode of a memoryless stream without committing it (parallel workers)."""
        if not memoryless(spec):
            raise ValueError(f"{spec['key']} has memory; its episodes must run in order")
        initial = self._initial(spec, specs)
        memory = copy.deepcopy(initial)
        context = self._context(spec, position)
        model, owned = self._model(spec['key'])
        try:
            result = self._agent(spec, model, memory, spec.get('frozen', False)).run(
                spec['tasks'][position], spec['seed'], context)
        finally:
            if owned:
                model.close()
        if memory != initial:
            raise ValueError(f"memoryless/frozen stream {spec['key']} changed its memory")
        return {**result, **context}

    # -- batched practice (cfg.practice_batch games at once; see batching.py) -------------
    def batched(self, spec):
        return (self.cfg.practice_batch > 1 and spec['phase'] == 'practice'
                and spec['condition'] in MEMORY and not spec.get('frozen'))

    def _memory_after(self, spec, specs, position):
        """Memory after `position` episodes of the stream (0 = its initial memory)."""
        if position == 0:
            return self._initial(spec, specs)
        return load_json(self._checkpoint(spec['key'], position - 1))['memory']

    def run_game(self, spec, specs, position):
        """One game of a batch, run on the memory as it was at the start of its batch."""
        k = self.cfg.practice_batch
        base = self._memory_after(spec, specs, position - position % k)
        memory = copy.deepcopy(base)
        task = spec['tasks'][position]
        context = self._context(spec, position)
        model, owned = self._model(spec['key'])
        try:
            result = self._agent(spec, model, memory, False).run(task, spec['seed'], context)
        finally:
            if owned:
                model.close()
        record = {**result, **context}
        if spec['condition'] == 'D' and record['success']:
            memory['trajectories'].append({'task': task, 'goal': record.get('goal', ''),
                                           'trace': record['trace'], 'success': True})
        return {'record': record, 'base': base, 'end': memory}

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
        if (spec['condition'] in UPKEEP_CONDITIONS
                and ((position + 1) % self.cfg.practice_batch == 0 or position + 1 == len(spec['tasks']))):
            # End of a batch: the deterministic upkeep (useless retirement, near-duplicate merge of rules that
            # games of the batch wrote without seeing each other's, capacity pruning) on the live rules. The ops
            # join this game's manual operations, so replaying a game's operations reproduces its checkpoint.
            from .manual import batch_upkeep
            ops = batch_upkeep(memory['rules'], {r['id'] for r in game['base']['rules']},
                               self.embedder.similarity)
            if ops:
                manual_report = dict(record.get('manual', {}))
                manual_report['operations'] = list(manual_report.get('operations', [])) + ops
                record['manual'] = manual_report
                merge_log.extend(['batch upkeep', op.get('op'), op.get('id')] for op in ops)
        self._write(key, position, sid, previous_hash, memory, record)
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
        self._write(key, position, sid, previous_hash, initial, record)

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

    def _cap(self, key, specs):
        """Positions this session may reach (execute's `caps` stop practice at the early gate)."""
        n = len(specs[key]['tasks'])
        return min(n, self._caps.get(key, n))

    def ready(self, spec, specs):
        """Episodes this stream can run right now (0 if finished or blocked)."""
        done = self.count(spec['key'])
        cap = self._cap(spec['key'], specs)
        if done >= cap:
            return 0
        if spec['init'] is not None and self.count(spec['init']) < (
                spec.get('init_position') or len(specs[spec['init']]['tasks'])):
            return 0
        return cap - done

    def execute(self, specs, workers=1, max_episodes=None, max_hours=None, log=print, caps=None):
        """Run streams until done or a budget/STOP file ends this session. True if all done.
        `caps` ({key: n}) stops those streams after n episodes (they count as done there) and
        limits the session to the given streams; without caps every stream of the plan runs."""
        given = [s['key'] for s in specs]
        specs = self._plan(specs)
        order = given if caps is not None else list(specs)
        self._caps = dict(caps or {})
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
            # Streams others wait on first (practice), then the longest.
            waiting = sum(s['init'] == key for s in specs.values())
            return (-waiting, -(len(specs[key]['tasks']) - self.count(key)), order.index(key))

        if workers <= 1:
            while not stopping():
                runnable = [k for k in order if self.ready(specs[k], specs)]
                if not runnable:
                    break
                key = runnable[0]
                remaining = self._cap(key, specs) - self.count(key)
                if max_episodes is not None:
                    remaining = min(remaining, max_episodes - state['new'])
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
                n = self._cap(key, specs)
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
        complete = all(self.count(k) >= self._cap(k, specs) for k in order)
        if complete:
            self.records = [r for key in order for r in self.verify(specs[key], specs)]
        else:
            self.records = [r for key in order for r in self._records(key)]
        write_json(self.output / 'records.json', self.records)
        log(f"session: {state['new']} new episodes in {(time.monotonic() - started) / 60:.1f} min; "
            f"{sum(min(self.count(k), self._cap(k, specs)) for k in order)}/"
            f"{sum(self._cap(k, specs) for k in order)} episodes done"
            + ('' if complete else ' (run the same command again to continue)'))
        self._caps = {}
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

    def study_specs(self, conditions=None, demo_count=None):
        conditions = tuple(self.cfg.conditions if conditions is None else conditions)
        if any(c not in CONDITIONS for c in conditions) or len(set(conditions)) != len(conditions):
            raise ValueError('conditions must be unique valid condition IDs')
        memory = [c for c in CONDITIONS if c in conditions and c in MEMORY]
        specs = []
        # Practice replicates: each practice seed has its own game order, shared by every memory condition, so
        # practice games are paired within a replicate.
        for pseed in self.cfg.practice_seeds:
            practice = ordered(self.manifest['splits']['practice'], pseed,
                               demo_count or self.cfg.practice_episodes, repeat=True)
            specs += [stream_spec(c, 'practice', pseed, practice, replicate=pseed) for c in memory]
        id_pool = self.id_evaluation_pool()
        for phase, full in (('evaluation', self.manifest['splits']['evaluation']), ('id-evaluation', id_pool)):
            if not full:
                continue
            for condition in CONDITIONS:
                if condition not in conditions:
                    continue
                for seed in (self.cfg.seeds[:1] if condition == 'A' else self.cfg.seeds):
                    pool = full if demo_count is None else full[:demo_count]
                    count = (demo_count or self.cfg.evaluation_games) if phase == 'evaluation' else (demo_count or len(pool))
                    tasks = ordered(pool, seed, min(count, len(pool)) if phase == 'id-evaluation' else count)
                    # Evaluation reads each replicate's practice memory frozen (amended 2026-11-15): every
                    # test episode is independent, so they all run in parallel.
                    if condition in MEMORY:
                        specs += [stream_spec(condition, phase, seed, tasks, init=practice_key(condition, pseed),
                                              frozen=True, replicate=pseed) for pseed in self.cfg.practice_seeds]
                    else:
                        specs.append(stream_spec(condition, phase, seed, tasks))
        # Practice-length curve: frozen libraries at milestones on fixed ID/OOD subsets.
        seed = self.cfg.seeds[0]
        subsets = [('ood', self.manifest['splits']['evaluation']), ('id', id_pool)]
        for milestone in ([] if demo_count is not None else self.cfg.snapshot_milestones):
            for condition in self.cfg.snapshot_conditions:
                if condition not in conditions:
                    continue
                for pseed in self.cfg.practice_seeds:
                    for name, pool in subsets:
                        if pool:
                            tasks = ordered(pool, seed, min(self.cfg.snapshot_games, len(pool)))
                            specs.append(stream_spec(condition, f'snapshot-{milestone}-{name}', seed, tasks,
                                                     init=practice_key(condition, pseed), init_position=milestone,
                                                     frozen=True, replicate=pseed))
        return specs

    def development_set(self):
        """The 70 seen-room development (tuning) games: early gate and offline library checks."""
        games = self.manifest['splits'].get('development', [])
        return ordered(games, self.cfg.seeds[0], min(self.cfg.development_games, len(games)))

    def id_evaluation_pool(self):
        """Seen-room games outside the development set: the in-distribution test set."""
        used = {t['id'] for t in self.development_set()}
        pool = [t for t in self.manifest['splits'].get('development', []) if t['id'] not in used]
        assert not used & {t['id'] for t in pool}
        return pool

    def study(self, conditions=None, demo_count=None, workers=1, max_episodes=None, max_hours=None,
              gate_at=None, gate_games=30, gate_margin=GATE_MARGIN, past_gate=False, log=print):
        """The study. With `gate_at`, the library practice first stops after that many games and
        E's rules (replicate 0) are checked against C on `gate_games` development games (early_gate); the
        study stops there if E is clearly behind (or `past_gate` continues anyway)."""
        if not self.toy:
            validate_real_design(self.cfg, self.manifest)
            check_revisions(self.cfg)
            if demo_count is not None:
                raise ValueError('sample count overrides are available only in demo')
        specs = self.study_specs(conditions, demo_count)
        write_json(self.output / 'cost_attribution.json', {
            'practice_shared_across_evaluation_seeds': True, 'practice_seeds': self.cfg.practice_seeds,
            'practice_cost_amortized_per_replicate': True})
        self.complete = False
        if gate_at and any(s['key'] == practice_key('E', self.cfg.practice_seeds[0]) for s in specs):
            started, before = time.monotonic(), self._committed()
            self.gate = self.early_gate(specs, gate_at, gate_games, gate_margin, past_gate,
                                        workers, max_episodes, max_hours, log)
            if self.gate is None or not (self.gate['passed'] or self.gate.get('continued')):
                return self.records
            if max_episodes is not None:
                max_episodes = max(0, max_episodes - (self._committed() - before))
            if max_hours is not None:
                max_hours = max(0.0, max_hours - (time.monotonic() - started) / 3600)
        self.complete = self.execute(specs, workers, max_episodes, max_hours, log)
        return self.records

    def _committed(self):
        root = self.output / 'checkpoints'
        return sum(1 for _ in root.glob('*/*.json')) if root.exists() else 0

    # -- early gate: a bug detector (amended 2026-11-17, redesign 2026-11-20) ------------------
    def gate_specs(self, gate_at, games):
        """C and E (replicate 0, rules frozen after `gate_at` practice games) on the first `games`
        development games, disjoint from the ID evaluation pool."""
        seed, replicate = self.cfg.seeds[0], self.cfg.practice_seeds[0]
        dev = self.development_set()[:games]
        return [stream_spec('C', 'gate', seed, dev),
                stream_spec('E', f'gate-{gate_at}', seed, dev, init=practice_key('E', replicate),
                            init_position=gate_at, frozen=True, replicate=replicate)]

    def early_gate(self, specs, gate_at, games, margin, past_gate, workers, max_episodes, max_hours, log):
        """Library practice (every replicate) up to `gate_at` games plus the gate games, then the gate
        report (gate.json). Returns None while unfinished; the decision is kept, so later sessions
        skip straight to the rest of the study."""
        path = self.output / 'gate.json'
        if path.exists():
            gate = load_json(path)
            if gate['checkpoint'] != gate_at:
                log(f"gate already decided at {gate['checkpoint']} practice games; ignoring --gate-at {gate_at}")
        else:
            practice = [s for s in specs if s['phase'] == 'practice' and s['condition'] in LIBRARY_CONDITIONS]
            if gate_at > len(practice[0]['tasks']):
                raise ValueError(f'gate checkpoint {gate_at} is beyond the practice length')
            gate_streams = self.gate_specs(gate_at, games)
            if not self.execute(practice + gate_streams, workers, max_episodes, max_hours, log,
                                caps={s['key']: gate_at for s in practice}):
                return None
            c_key, e_key = (s['key'] for s in gate_streams)
            p_key = gate_streams[1]['init']
            rules = load_json(self._checkpoint(p_key, gate_at - 1))['memory']['rules']
            gate = {'checkpoint': gate_at, **gate_decision(
                self._records(e_key), self._records(c_key), rules,
                self._records(p_key)[:gate_at], margin)}
            write_json(path, gate)
            log(f"early gate at {gate_at} practice games: E won {gate['E_wins']}/{gate['paired_games']}, "
                f"C won {gate['C_wins']}/{gate['paired_games']} -> {'PASSED' if gate['passed'] else 'FAILED'}")
        if not gate['passed'] and not gate.get('continued'):
            if past_gate:
                gate['continued'] = True
                write_json(path, gate)
                log('continuing past the failed early gate (--past-gate)')
            else:
                log(f"STOP: E is clearly behind C at the early gate (E {gate['E_wins']} vs C {gate['C_wins']} "
                    f"of {gate['paired_games']} paired games; needs E - C >= {gate['margin']}): look for a bug. "
                    f"Report: {path}\n"
                    f"  continue anyway from the checkpoint: rerun with --past-gate (run.ps1 study -PastGate)\n"
                    f"  or fix the library and restart its practice, keeping C and D: --restart-library "
                    f"(run.ps1 study -RestartLibrary)")
        return gate

    def restamp(self, spec, specs):
        """Re-sign a kept stream's checkpoints after a library restart changed the run identity."""
        if not self.count(spec['key']):
            return
        sid = self._stream_identity(spec, self._initial(spec, specs))
        for position in range(self.count(spec['key'])):
            path = self._checkpoint(spec['key'], position)
            saved = load_json(path)
            self._check(saved, saved['stream_identity'], path)    # integrity hashes still hold
            saved['stream_identity'] = sid
            write_json(path, saved)


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


def paired_comparison(records, baseline):
    """Wins of `records` vs `baseline` on the games both played (paired by task id)."""
    mine = {r['task_id']: bool(r['success']) for r in records}
    base = {r['task_id']: bool(r['success']) for r in baseline}
    paired = [t for t in mine if t in base]
    return {'games': len(paired), 'wins': sum(mine[t] for t in paired),
            'baseline_wins': sum(base[t] for t in paired),
            'won_where_baseline_lost': sum(mine[t] and not base[t] for t in paired),
            'lost_where_baseline_won': sum(base[t] and not mine[t] for t in paired)}


def gate_decision(e_records, c_records, rules, practice_records, margin=GATE_MARGIN):
    """Early gate: E (frozen rules at the checkpoint) vs C on paired development games.
    Passes when E wins - C wins >= margin (default: E at most 3 games behind C)."""
    pair = paired_comparison(e_records, c_records)
    errors = [e for r in practice_records for e in r.get('manual', {}).get('errors', [])]
    return {'paired_games': pair['games'], 'E_wins': pair['wins'], 'C_wins': pair['baseline_wins'],
            'E_won_C_lost': pair['won_where_baseline_lost'], 'C_won_E_lost': pair['lost_where_baseline_won'],
            'rule_count': len(rules), 'builder_errors': sum(e.startswith('builder') for e in errors),
            'manual_errors': len(errors), 'margin': margin,
            'passed': pair['games'] > 0 and pair['wins'] - pair['baseline_wins'] >= margin}


def check_e_minus_kept(cfg, output, before, changed, log=print):
    """An E-only restart keeps E-minus only if its behaviour is unchanged: its stored practice replays
    exactly under the current code (e_minus_replay_check) and, when sources changed, the fixture E-minus
    probe of the current code equals the one taken with the run's recorded sources. ValueError otherwise."""
    games, problem = e_minus_replay_check(cfg, output)
    if problem:
        raise ValueError(f'E-minus probe failed: {problem}; E-minus cannot be kept (use --restart-library)')
    if changed:
        stored = stored_e_minus_probe(cfg, output, before)
        if stored is None:
            raise ValueError('E-minus probe failed: the run has no E-minus probe for its recorded sources '
                             '(probe.json); E-minus cannot be kept (use --restart-library)')
        if stored != e_minus_probe(cfg):
            raise ValueError(f'E-minus probe failed: {", ".join(changed)} changed E-minus\'s behaviour (fixture '
                             'probe differs); E-minus cannot be kept (use --restart-library)')
    log(f'E-minus probe passed: {games} stored practice games replay exactly'
        + ('; fixture probe unchanged' if changed else '; sources unchanged'))


def restart_library(cfg, manifest, output, log=print, streams=None):
    """Discard the library conditions' streams (every replicate, and anything initialised from them) and
    the gate decision; keep C's and D's games. If sources changed since the run started, only
    LIBRARY_SOURCES may differ: the kept checkpoints are then re-signed with the new identity.
    `streams` (amended 2026-11-19): conditions to restart instead of all library conditions; only
    ('E',) is allowed, which keeps E-minus too when its probe passes (check_e_minus_kept)."""
    import shutil
    output = Path(output)
    conditions = LIBRARY_CONDITIONS
    if streams is not None:
        if tuple(sorted(set(streams))) not in [(s,) for s in RESTARTABLE]:
            raise ValueError(f'only these conditions can be restarted alone: {", ".join(RESTARTABLE)}')
        conditions = tuple(set(streams))
    marker = output / 'run.json'
    if not marker.exists():
        raise ValueError(f'{output} has no run to restart')
    run = load_json(marker)
    old, new = run['identity'], identity(cfg, manifest)
    if old['settings'] != new['settings'] or old['manifest'] != new['manifest']:
        raise ValueError('settings or manifest changed since this run started; C and D cannot be kept '
                         '(use a new output directory)')
    changed, before = [], None
    if old['source'] != new['source']:
        if not (output / 'sources.json').exists():
            raise ValueError('run has no sources.json; cannot tell which files changed (use a new output directory)')
        before, now = load_json(output / 'sources.json'), source_hashes()
        changed = sorted(p for p in set(before) | set(now) if before.get(p) != now.get(p))
        outside = [p for p in changed if p not in LIBRARY_SOURCES + PROBED_SOURCES + ENTRY_SOURCES]
        if outside:
            raise ValueError(f'files outside the library code changed ({", ".join(outside)}); '
                             'C and D cannot be kept (use a new output directory)')
        probed = [p for p in changed if p in PROBED_SOURCES]
        if probed:
            saved = load_json(output / 'probe.json') if (output / 'probe.json').exists() else {}
            if saved.get('sources') != digest(before):
                raise ValueError(f'{", ".join(probed)} changed and the run has no C/D probe for its recorded '
                                 'sources; C and D cannot be kept (use a new output directory)')
            if saved['probe'] != baseline_probe(cfg):
                raise ValueError(f'{", ".join(probed)} changed C\'s or D\'s behaviour (baseline probe differs); '
                                 'C and D cannot be kept (use a new output directory)')
    if 'E-minus' not in conditions:
        check_e_minus_kept(cfg, output, before, changed, log)
    plan = load_json(output / 'plan.json') if (output / 'plan.json').exists() else []
    dropped = {s['key'] for s in plan if s['condition'] in conditions}
    grew = True
    while grew:
        extra = {s['key'] for s in plan if s['init'] in dropped} - dropped
        dropped |= extra
        grew = bool(extra)
    for key in sorted(dropped):
        shutil.rmtree(output / 'checkpoints' / key, ignore_errors=True)
        for cache in (output / 'model-cache').glob(f'{key}.sqlite*'):
            cache.unlink()
    kept = [s for s in plan if s['key'] not in dropped]
    write_json(output / 'plan.json', kept)
    gate = load_json(output / 'gate.json') if (output / 'gate.json').exists() else None
    for name in ('gate.json', 'records.json'):
        (output / name).unlink(missing_ok=True)
    write_json(marker, {**run, 'identity': new})
    runner = Runner(cfg, manifest, output)          # identity matches again; writes sources.json
    specs = {s['key']: s for s in kept}
    for spec in kept:
        runner.restamp(spec, specs)
    history = load_json(output / 'restarts.json') if (output / 'restarts.json').exists() else []
    history.append({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'restarted': sorted(conditions),
                    'discarded': sorted(dropped),
                    'kept': [s['key'] for s in kept], 'changed_sources': changed, 'previous_gate': gate})
    write_json(output / 'restarts.json', history)
    log(f"library restart: discarded {len(dropped)} streams ({', '.join(sorted(dropped)) or 'none'}); "
        f"kept {len(kept)} ({', '.join(s['key'] for s in kept) or 'none'})")
    return runner


def check_revisions(cfg):
    for field in ('embedding_revision', 'planner_revision', 'executor_revision', 'quantization', 'hardware'):
        value = getattr(cfg, field, '')
        if not value or value in {'main', 'unverified', '4-bit-unverified', 'unrecorded'}:
            raise ValueError(f'real runs require an explicit verified {field}; update settings')
