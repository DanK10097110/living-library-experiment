# Living skill library experiment

A Python implementation of the revised proposal in this repository: a pilot-first
comparison of local agents with executable skill memory, trajectory memory, and
no memory. The implementation includes all seven core conditions. It does **not**
include benchmark results: only deterministic CPU fixtures have been run.

Run the inexpensive smoke test from the repository root:

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 -m living_library demo --output runs/demo --sample-count 3
```

The demo uses a tiny handwritten environment and policy, lexical retrieval, and
three games per stream. It makes no model-server requests or model downloads.
Its output is marked `toy: true`; its success rates are plumbing checks. Repeat
the same command to resume committed episodes without calling the model again.

The core is in `living_library/`:

| Module | Responsibility |
| --- | --- |
| `domain.py`, `environments.py` | Fixed predicates, simulator actions, ALFWorld adapter and replayable start states |
| `program.py` | Bounded interpreter for generated Python skills |
| `library.py` | Contracts, Beta reliability, retrieval, admission, fallback and rollback |
| `models.py`, `agents.py` | Local inference/cache, flat and hierarchical execution, repair and replanning |
| `experiment.py`, `protocol.py` | Split guards, pilot gates, freezing, checkpoints and pre-registered expectations |
| `analysis.py` | Paired task-cluster bootstrap, Holm correction and secondary metrics |
| `extensions.py` | Optional conservative consolidation, separate from core runs |

The experimental conditions are:

| ID | Agent and memory | Practice | Evaluation seeds |
| --- | --- | --- | --- |
| A | Flat ReAct, no memory | None | 1 |
| B | Flat agent, updating code library | 500 | 1 |
| C | Hierarchy, no memory | None | 3 |
| D | Hierarchy, successful practice trajectories | 500 | 3 |
| E | Hierarchy, updating code library | 500 | 3 |
| E-minus | Hierarchy, append-only code library | 500 | 3 |
| E-text | Hierarchy, E's exact pre-task library rendered as steps | Shares E's | 3 |

Practice uses one fixed seed per condition. Each evaluation seed starts from an
independent copy of that practice memory, then updates over its own task stream.
This resolves the proposal's practice-budget ambiguity in favor of its 2,000
practice-episode total. D stores only successful **practice** trajectories.
E-text receives the same seed, task order, and library content as E before each
task; its own outcomes cannot change that content.

To prepare a real pilot, install the optional dependencies in an environment
appropriate for ALFWorld:

```bash
python3 -m pip install -e '.[alfworld,embeddings]'
python3 -m living_library manifest \
  --data-root /path/to/alfworld/json_2.1.1 --output runs/manifest.json
```

Use locally downloaded data and model weights. The embedding adapter requests
local files only. Model serving is external: configure two local HTTP servers
supporting `/v1/chat/completions`, JSON output, and token usage, such as a
[vLLM compatible server](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/).
The default endpoints are ports 8000 and 8001. The program does not launch servers
or choose/download a quantized model for you.

`configs/pilot.json` is a **draft**, not frozen experimental settings. Before the
pilot, record actual model revisions, embedding revision, quantization and
hardware there. Use immutable model commit IDs or local artifact checksums and
the actual served model names. The proposal's
[Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B) and
[Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)
model cards identify Apache-2.0 licenses; the
[BGE embedding model](https://huggingface.co/BAAI/bge-small-en-v1.5) identifies MIT.
Operator-supplied revision metadata must match the external server's weights;
this client cannot attest those weights remotely.

The following commands opt into the real workload. They have not been run:

```bash
python3 -m living_library pilot --config configs/pilot.json \
  --manifest runs/manifest.json --output runs/pilot
python3 -m living_library freeze --config configs/pilot.json \
  --manifest runs/manifest.json --pilot-dir runs/pilot --output runs/frozen.json
python3 -m living_library study --config configs/pilot.json \
  --manifest runs/manifest.json --freeze runs/frozen.json --output runs/study
```

The pilot runs 300 E-minus training episodes and C/E-minus on the 140 seen
development games. It does not execute unseen evaluation games. Freezing requires
complete, matching real pilot evidence and every gate to pass: neither development
success rate above 85%, at least ten skills used five times, false-success rate at
most 10%, and rejected/crashing program rate at most 40%. Missing measurements
cannot pass. Failed headroom or reuse gates recommend ScienceWorld; a
ScienceWorld adapter is not implemented, so this outcome stops the study until
the domain is ported and validated. Predicate/program failures require another
pilot after correction.

The freeze records settings, source and dataset fingerprints, pilot evidence, and
the pre-registration. Changed settings, code or manifest require a new pilot and
freeze. Commit the resulting freeze artifact before starting unseen evaluation.
The full study runs the 134 unseen games per evaluation stream. To run a subset,
use `--conditions C D E E-minus`; requesting E-text also runs E. Extending a run
preserves existing condition records. Use separate output directories for pilot
and study; never run two writers against one output directory.

Each episode checkpoint includes the pre-task library, resulting memory,
trajectory, invocation outcomes, cost metrics and integrity hashes. `records.json`
collects completed episodes; `analysis.json` reports comparisons. Inference
responses use a SQLite cache keyed by request, seed and episode context. A cache
replay retains the original measured usage for reproducible accounting. These
are experiment charges, not newly consumed compute during a resumed run.
Connection failures stop the run before committing the current episode, so a
server outage is not scored as an agent failure. Resume after restoring the
server. The effective configuration is also saved as `settings.json`.

GPU-seconds are deliberately separate from elapsed request/episode time. Ordinary
compatible servers do not supply this metric: the client accepts an optional
`measured_gpu_seconds` response field from an instrumented server, otherwise logs
`null`. Until genuine measurements exist, H2 and break-even results are
**unavailable**. No wall-clock proxy is labeled as GPU time. Token counts remain
available, with the proposal's input + 4 × output weighting. Practice charges
are included for each independently reported evaluation seed, including E-text.

For statistical analysis, every paired comparison must contain the same tasks and
all configured seeds. Bootstrap units are tasks, with seed-averaged task success
and cost. Skill success uses pooled invocation counts, resampling whole tasks;
zero-invocation tasks remain in the sampling frame. Retrieval errors are reported
separately from eligible skill outcomes. Four primary tests receive Holm
correction. The success criterion is E beating D by 10 percentage points, or zero
within the success-difference interval at 30% lower amortized GPU cost, **and** a
positive H3 effect with Holm-adjusted p ≤ .05. This last significance convention
is an explicit implementation choice to freeze after the pilot, not a result.

Generated skills can call `act`, `check`, and other immutable skill versions;
use string bindings, f-strings, `if`/`else`, and bounded `for range` loops.
Arbitrary Python execution, imports, attributes and unbounded loops are rejected.
Action, model-call, instruction and nesting budgets bound execution. Preconditions
and postconditions are simulator predicates, never model judgments. The adapter
maps [ALFWorld's PDDL facts](https://github.com/alfworld/alfworld/blob/master/alfworld/data/alfred.pddl)
to this fixed vocabulary; `findable(x)` currently means the physical entity exists
in the simulator, not that the agent has observed it. Hidden fact tables stay out
of prompts. A revision preserves its contract and must pass all stored regression
states; the old version remains available for rollback. E-minus keeps existing
counters, notes and tests unchanged; invocation logs still measure its outcomes.
Failure notes currently preserve concrete executor errors, avoiding an additional
model call just to paraphrase an error. Repairs receive those notes. This is a
deliberate low-compute simplification of the proposal's L2-written failure notes.

Optional consolidation is a separate library API that proposes conservative
merges and verifies source regression states before activation. It never runs
automatically in the seven-condition study. Imagined practice is deferred: its
learned world model and real-scenario verification need their own validation,
which would add work beyond the low-compute core implementation.

The ALFWorld adapter and real model integration still need a real pilot. The
current validation covers fixtures, adapter fact translation, model protocol
mocks, update/rollback behavior, paired analysis and resume integrity. Execution
is intentionally sequential to keep the initial implementation inexpensive;
the proposal's high-throughput batching remains a future optimization.
