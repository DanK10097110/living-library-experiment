# Living library experiment

Does a small local model (Qwen3.5-9B) solve ALFWorld household tasks better when it keeps a managed
manual of plain-language rules learned in practice, compared with keeping example trajectories, keeping
the same manual append-only, or keeping nothing? This repository holds the agent, the rule manual, the
experiment runner and the pre-registered analysis.

- `ARCHITECTURE.md`: the whole system, its decision history and the gaps that led to the 2026-11-20 redesign.
- `LIBRARY-SPEC.md`: the rule manual (writing, the per-rule judge, management, retrieval) with the reasoning
  behind every threshold.
- `living_library/protocol.py`: the pre-registration and its amendment history.
- `results/`: logs (`LOG.md`), design decisions (`DECISIONS.md`) and library snapshots of earlier runs.

## Conditions

| ID | Agent | Memory built in practice |
| --- | --- | --- |
| C | planner + ReAct actor | none |
| D | same | successful first-attempt practice trajectories; the top 3 by goal similarity shown as examples |
| E | same | rule manual with evidence-based management (refine or retire rules the judge finds harmful or unfollowed) |
| E-minus | same | the same manual, append-only |
| A | flat ReAct, no planner, no memory | kept in the code, not in the study |

One game (`agents.py`): the rules (E, E-minus) are chosen once at the start (`manual.for_agent`, at most 8);
the planner splits the task into subgoals with predicate postconditions (`domain.py`); the actor is the
published ALFWorld ReAct prompt (`react.py`, `prompts/`) and acts step by step until each subgoal's
predicates hold. After a practice game of E or E-minus, `manual.build` retries a lost game with Reflexion
reflections (up to 3, memory read-only), judges each shown rule, and lets the Builder write rules
(`manual.py`, `avoid.py`).

## Design

- Practice: 300 games per memory condition and **practice replicate** (`practice_seeds` [0, 1]; each replicate
  has its own game order, shared by D, E and E-minus). Batches of 8 games run on the memory at the start of
  the batch and are merged in position order (`batching.py`); E's deterministic upkeep runs at each batch end.
- Tests read every replicate's memory **frozen**: OOD = the 134 unseen-room games (primary), ID = the 70
  seen-room games outside the development set (secondary). One evaluation seed (11).
- Hypotheses (Holm over H1-H3): H1 E−D task success, H2 E−D amortized weighted tokens (input + 4 × output,
  practice and retries included, amortized per replicate), H3 E−E-minus task success; E−C secondary.
  Success: (E−D ≥ 10 pp, or 0 inside its 95% CI with ≥ 30% lower cost) and H3 > 0 at Holm p ≤ .05.
- Statistics (`analysis.py`): hierarchical paired bootstrap; each sample resamples tasks and, within each
  condition, its replicates, so library-to-library variance is inside the intervals.
- Early gate: a bug detector, not evidence. Library practice stops at 75 games, then E (replicate 0, frozen)
  plays 30 development games against C; the study stops if E wins − C wins < −3 (`gate.json`).

## Running

Smoke test (CPU only, a tiny handwritten world and fixture model, no model server):

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
python3 -m living_library demo --output runs/demo --sample-count 3
```

On this machine the study runs through `tools\run.ps1` (header lists every option; output
`/root/ll-runs/study2`, WSL). The equivalent commands:

```bash
python3 -m living_library manifest --data-root /path/to/alfworld/json_2.1.1 --output runs/manifest.json
python3 -m living_library study --config configs/pilot.json --manifest runs/manifest.json --output runs/study2
python3 -m living_library study ... --past-gate           # continue past a failed gate
python3 -m living_library study ... --restart-library     # redo E and E-minus practice, keep C and D
python3 -m living_library study ... --restart-streams E   # redo E only, keep E-minus if its probe passes
python3 -m living_library status --output runs/study2
python3 -m living_library analyze --records runs/study2/records.json --output runs/study2/analysis.json
python3 tools/plots.py runs/study2                        # figures + report.html
```

`configs/pilot.json` holds the study settings (the name is historical) with the served model files and
revisions. Model serving is external: an OpenAI-compatible local server (`tools/serve-model.ps1`, llama.cpp).

Runs are resumable: every finished episode is an atomic checkpoint (memory, record, hashes) and model calls
are cached per stream, so rerunning the same command continues where it stopped (Ctrl-C or a `STOP` file in
the run folder ends a session). Stream keys: `practice-{condition}-{practice seed}`,
`{phase}-{condition}-r{replicate}-{seed}` for tests of a memory condition, `{phase}-C-{seed}` for C. Changed
settings, code or manifest need a new output directory, except a library restart: it keeps C's and D's games
when only `manual.py`/`avoid.py` changed, or when a fixture probe shows C and D (and, for `--restart-streams E`,
E-minus) unchanged (`probe.json`, `restarts.json`).

## Code

| Module | Responsibility |
| --- | --- |
| `domain.py`, `environments.py`, `validate_simulator.py` | Predicates, ALFWorld adapter, fixture world |
| `agents.py`, `react.py`, `models.py` | One game: rules, planner, ReAct actor; local model client and cache, fixture model |
| `manual.py`, `avoid.py` | The rule manual (`LIBRARY-SPEC.md`) |
| `embedding.py` | Text similarity for retrieval (sentence embeddings; lexical for fixtures) |
| `experiment.py`, `batching.py`, `cli.py` | Streams, replicates, checkpoints, early gate, restarts, batched practice |
| `analysis.py`, `protocol.py` | Pre-registered statistics and pre-registration |

Offline tools in `tools/`: `manual_check.py` (a rule file vs C on development games), `mini_practice.py`
(a short live practice with a readable report), `snapshot_eval.py` and `compare_snapshots.py` (a replicate's
library after N games on the study's test games), `plots.py`.
