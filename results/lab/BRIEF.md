# Large-library management lab: brief

Goal: find out how E's rule library should be managed and retrieved when it grows (tens to hundreds of
rules), by testing methods ONE AT A TIME on synthetic libraries built from real data, against the
current implementation. Output a clear comparison and a recommendation. Do not change the live
library code (`living_library/manual.py`, `agents.py`): a study is running from this tree. Put all new
code under `living_library/lab/` (new package) and `tools/lab_*.py`, with unit tests in
`tests/test_lab_*.py`. All 150 existing tests must keep passing, including the C/D probe test.

## Background (read)
- `results/DECISIONS.md` (history and reasons), `HANDOFF.md`, `results/LOG.md` (latest numbers).
- Current retrieval: `manual.for_agent` / `relevant` / `relevance` in `living_library/manual.py`.
  Rules are filtered by task type (or 'all'), then ranked by similarity of the game goal to the goals of
  games each rule won ("task-keyed"; fallback: rule text), combined with Beta reliability (MACLA expected
  utility). k is about 3-8 per game. Placeholder/plan/steps variants exist behind `--retrieval`.
- Finding so far: with real libraries (15-30 rules, about 3 per task type) every retrieval variant shows the
  same rules, so retrieval has not mattered yet. It will matter for larger libraries.

## Data (real)
- Real rule libraries (with contexts = won tasks, plans, steps): `results/*/rules-full.json`,
  `results/mini-macla-*/rules.json`; WSL `/root/ll-runs/{practice-b,practice-d,practice-e,mini-macla}/rules-full.json`;
  archived runs `/root/ll-runs/old-*`. Checkpoints contain per-game records (goal, task type, plan, trace,
  rules shown, success): `/root/ll-runs/<run>/checkpoints/<stream>/NNNNN.json`.
- Real queries: game goals, task types and planner plans from checkpoint records (practice and dev games).

## Phase 1: benchmark
Build `tools/lab_bench.py`, which creates synthetic libraries of N = 15, 50, 100, 250, 500 rules from the real
rule pool: real rules, plus model-written paraphrases and variants (more specific or general wording, other
objects/places), near-duplicates, plausible junk (vague, wrong, instance-specific) and rules of other task
types. Each query (a real game: goal, task type, plan) gets relevance labels: which rules truly apply
(task kind + situation). Label deterministically where possible (task type, kind words, recipe steps).
Use the model only where needed, then spot-check by hand and write the labeling rules down. Generation may
use the model server (http://127.0.0.1:8000, OpenAI-style `/v1/chat/completions`, model alias
`qwen3.5-9b-q4_k_m`), but the study is using it: keep at most 4 concurrent requests and cache all
responses on disk (the repo has a model cache class in `living_library/models.py`; reuse it if practical).
Metrics per method and N: recall@k and precision@k (k = 3, 5, 8), nDCG@k, duplicate rate in top-k,
junk rate in top-k, wrong-kind rate in top-k, model calls and latency per query, build/maintenance cost.

## Phase 2: methods (one at a time, each vs the current baseline)
1. Baseline: current flat task-keyed retrieval (import from manual.py, don't copy-modify it).
2. Size cap: keep the best M rules by MACLA utility (M = 25, 50, 100). Is there a size beyond which
   quality drops with the current retrieval? (The owner's hypothesis is about 50.)
3. Periodic merging/consolidation: cluster similar rules (embedding similarity), merge each cluster into
   one more general rule with the model (AutoManual/ExpeL-style), and keep provenance and Beta counts.
   Measure size reduction, retrieval quality, and whether the merged rules lose details (recipe steps).
4. Redundancy-aware top-k (MMR) on top of the baseline.
5. Tree / hierarchical library (owner's idea; compare RAPTOR, MemTree, H-MEM): leaves are rules, inner
   nodes are 1-2 sentence descriptions of their subtree (model-written), and nodes split when they exceed a
   size. Retrieval descends the tree: (a) embedding routing (beam over nodes), (b) model routing (the model
   picks the child(ren)). Top-k comes from the reached leaves. Measure routing errors (relevant rule
   in an unvisited subtree), calls per query, and the split threshold.
6. Anything else clearly promising from the literature (e.g. task-type-first two-stage retrieval, rerank
   with the model). Keep it to 1-2 extra ideas.

## Phase 3: real check (only the best 1-2 methods)
Union of the real libraries from several practices (about 80-120 real rules with contexts) -> one large frozen
library. Compare the baseline against the best method with `tools/manual_check.py`-style 70-game runs. Do not
start these yourself: write the exact commands (and any needed `--retrieval`-style switch, implemented
in the lab package plus a minimal opt-in hook) into the report. The architect will run them when GPU time allows.

## Rules
- No commits are needed from you; the architect commits. Don't touch `manual.py` / `agents.py` / `experiment.py`
  except for a minimal opt-in hook in Phase 3 if unavoidable (default behaviour byte-identical; tests prove it).
- No `find` over drives, never print passwords; run Python in WSL (`/root/venvs/living/bin/python`).
- Keep the model load small (<= 4 concurrent requests); the study has priority.
- Report results in `results/lab/REPORT.md`: tables per method x N, the main findings in plain words,
  a recommendation (what to adopt, at what library size, and what not to do), and the Phase 3 commands.
