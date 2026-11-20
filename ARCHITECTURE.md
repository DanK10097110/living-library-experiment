# Living Library: architecture, decisions and logical gaps

Written 2026-11-20 from the code at commit `2a2e73f` (plus the uncommitted LOG/DECISIONS edits), the live study
folder `/root/ll-runs/study`, `results/DECISIONS.md`, `results/LOG.md`, `protocol.py` and `README.md`.

**Purpose.** Since 2026-11-19 the study's library streams were restarted 8 times (`restarts.json`). Each restart
followed the same loop: watch a practice window, see E behind E-minus, diagnose, patch one mechanism, restart.
This document lays out the whole system in one place and lists the logical gaps that are **still open**, so that
they can all be fixed in one pass before the next and last run. Sections 1-3 describe the system. Section 4
lists the gaps. Section 5 is a plan to get to one final run.

---

## 0. Summary

The rule-manual mechanics are now careful and well tested (254 unit tests). The things that keep forcing reruns
are mostly not in the rule mechanics. They are in the experimental design and in how decisions get made:

1. **The pre-registered tests no longer measure the rule manual.** H3 (E vs E-minus) is scored on *code-skill
   invocation success*, and H4 (E vs E-text) on rendering *code skills* as text. E's real library has been a
   rule manual since 2026-11-15. The success criterion requires H3 to be significant. As written, the study
   cannot answer its own main question about the library. (Gap A1)
2. **The old code-skill library still runs inside E and E-minus, and it behaves differently in the two.** E
   records skill reliability and repairs skills; E-minus does neither. In the current E-minus stream, skills are
   called in 43 of 104 games, and 51 of 78 calls fail. Every frozen 70-game check that justified the manual
   ran with an *empty* skill library, so the configuration being studied was never checked. (Gap A2)
3. **One practice run per condition.** Libraries from the same code differ a lot between runs (70-game checks of
   replicate libraries: 48, 49, 54 of 70; heat 4/9 vs 7/9). The final comparison will measure one library, but
   the bootstrap CIs only resample tasks, so they ignore library-to-library variance. (Gap A3)
4. **Restarts were triggered by differences inside the noise.** In paired practice windows, E and E-minus
   disagree on about 26-29% of games. Over 50 games that means about ±8 wins (2 SD) of pure noise, and the
   window was checked again and again. (Gap B1)
5. **Three rule-management thresholds still fire on rules that are fine.** In particular, recipe refinement has
   no cap and is close to a coin flip for a recipe that defines its own base rate. "Never won in 4" retires a
   *good* rule in a task kind with a 10% base rate 66% of the time. (Gaps C1-C3, simulated in section 4)

Section 5 lists what to decide (owner), what to fix (one batch, verified offline on CPU), and the freeze rules
that should make the next run the last one.

Current state: the study is paused (a `STOP` file from 15:48 is in the run folder). E restarted at 15:46 and has
1 practice game; E-minus has 104, D 240. C evaluation (134 OOD + 70 ID) and gate-C are done.

---

## 1. What the study asks

### Conditions (lean design, `experiment.REAL_DESIGN`)

| ID | Agent | Memory built in practice | Practice | Evaluation |
| --- | --- | --- | --- | --- |
| C | planner + ReAct actor | none | none | 134 OOD + 70 ID, seed 11 |
| D | same | successful practice trajectories; top-3 by goal similarity shown as examples | 300 | frozen, same games |
| E | same | rule manual (edits, merges, retires) **+ code-skill library (with repair)** | 300 + retries | frozen |
| E-minus | same | rule manual, append-only **+ code-skill library (no repair, no reliability counts)** | 300 + retries | frozen |
| E-text | same | reads E's library: **same rules**, code skills shown as text instead of callable | shares E's | frozen |

A and B were dropped. E-plus (consolidation of code skills) is still in the code but is not in `conditions`.

### Data
- Practice: 300 games drawn from the 3,553-game ALFWorld train split with `practice_seed` 0. Every memory
  condition gets the same games in the same order, so practice games are paired.
- OOD test: the 134 unseen-room games (primary). ID test: the 70 seen-room development games the pilot never used.
- Development (tuning) set: the other 70 seen-room games (`pilot_development()`). The gate uses the first 30 of
  these. Every frozen library check in `tools/manual_check.py` also used this set.
- Evaluation reads every memory **frozen** (amended 2026-11-15). Nothing is learned at test time.
  `README.md` still says evaluation seeds update their memory, which is stale.

### Hypotheses (`protocol.py`, unchanged since the proposal)
| | Comparison | Primary metric | Status vs the current design |
| --- | --- | --- | --- |
| H1 | E − D | task success | valid |
| H2 | E − D | amortized weighted tokens | valid (practice retries are charged) |
| H3 | E − E-minus | **skill invocation success** | measures the code-skill side channel, not the rules |
| H4 | E − E-text | task success | E and E-text see identical rules; differs only in code-skill presentation |

Success criterion: (E−D ≥ 10 pp, or 0 inside the CI with ≥ 30% lower cost) **and** H3 > 0 with Holm p ≤ .05.

---

## 2. Architecture

### 2.1 Run orchestration (`experiment.py`, `batching.py`, `cli.py`, `tools/run.ps1`)

```
manifest ─► study_specs ─► streams (practice-{D,E,E-minus}-0, gate-*, evaluation-*, id-evaluation-*, snapshot-*)
                              │
Runner.execute (process pool, 24 workers)
  ├─ batched practice streams (critical path): 8 games at a time, all 8 run on the memory as it was
  │    at the start of the batch (run_game) and are committed in position order (commit_game):
  │      skills  -> merge_library (counters add, first writer of a name wins)
  │      rules   -> manual.replay of each game's applied operations (a rule's text changes at most once
  │                 per batch; first in position order wins), then batch_dedupe for E
  │      D       -> successful traces appended
  ├─ memoryless / frozen streams (C, all evaluations): episodes run in parallel, committed in order
  └─ every episode = atomic checkpoint (pre-library, memory, record, hashes); response cache per stream
early_gate: practice capped at 75 -> E frozen at 75 vs C on 30 dev games -> gate.json (pass if E−C ≥ 0)
restart_library / --restart-streams E: drop library streams, keep C/D if only library files changed, or if the
   fixture C/D probe (every model request + record) is unchanged; E-minus kept only if its replay check and
   fixture probe pass
analysis.py: paired task bootstrap, Holm over H1-H4
```

The protections around resuming are solid: hashes, probes, replay checks and atomic writes. They are why C and D
survived 8 restarts.

### 2.2 One game (`agents.py`, `react.py`)

1. **Select rules once** (`_select` → `manual.for_agent`, at most `SHOWN` = 8): the task kind's Success Process
   first, then the other candidates ranked by MACLA expected utility. Rules do not change during a game.
2. **Planner**: 1-12 subgoals with bindings and predicate postconditions. It sees the rules, the code-skill
   catalog (memory conditions) and Reflexion reflections (retries only).
3. **Actor**: the published ALFWorld ReAct prompt (verl-agent + ReAct demos). Each step it sees the rules, D's
   examples, and the **callable code skills** whose preconditions hold (top 3; E-text sees them as text). Step
   caps: 15 per subgoal, 30 per game, 60 model calls.
4. **Code-skill writing** (E, E-minus, practice only): when a subgoal finishes without a skill call, the
   librarian writes a Python skill and it is replay-verified (up to 3 rounds). A failed skill call in E triggers
   a repair; E-minus never repairs.
5. **After a practice game** (E, E-minus): `manual.build` (2.3).

### 2.3 The rule manual (`manual.py`, `avoid.py`)

**Rule record.** `id, type, rule, example, validation, scope (task_type | 'all'), verified, importance,
alpha/beta, credits{kind:[w,l]}, unused, base, base_types{kind:[w,g]}, contexts (≤15 won + ≤15 lost),
sources, commands{cmd:[rejected, accepted-in-win]}, rewrites, confirmations, guess_credits, refined_at`.

**Types.** Success Process (the recipe, one per task kind), Special Phenomenon, Corrected Error, Unresolved Error
(hidden note), Anti-Pattern (mined from pooled failures), Failure Pool (hidden bookkeeping).

**Per practice game, in order (`build`):**

| Step | What | E | E-minus |
| --- | --- | --- | --- |
| 1 Retry | lost game → Reflexion reflection + replay, up to 3, stop at first win (memory read-only) | ✓ | ✓ |
| 2 Case | direct success / indirect success / failure / corrected failure (retry won) | ✓ | ✓ |
| 3 Judge | separate outcome-blind call: which shown rules and hidden guesses did the actions follow? On failure: credit every shown rule | ✓ | ✓ |
| 4 Builder | one call; sees ≤ 24 relevant rules + 2 newest; returns write/update/upvote/downvote ops | all ops | write only |
| 5 Apply | case limits on types and write counts; text checks (strip "microwave 1", length, steps outside a recipe, object/room names, another kind's actions; one model repair each, else reject); similarity merge at 0.85; text freeze | ✓ | writes, checks |
| 6 Observe | Beta update of followed rules, `unused` for shown-not-followed, base rates for every rule of this kind, command evidence, guess promotion (≥ 2 followed wins and ≥ expected wins) | ✓ | ✓ |
| 7 Retire | useless (≥ 8 shown, < 20% followed); instructed command rejected in ≥ 2 followed games and never accepted in a win; never won in ≥ 4 followed (if the kind had wins); Beta P(rate < expected) ≥ 0.9; dead recipe at the rewrite cap | ✓ | – |
| 8 Anti-Patterns | pool never-won games per kind; deterministic miner; model words it; code checks | ✓ | write only |
| 9 Refine | one shown rule with ≥ 3 new W and ≥ 3 new L and wins < expected → contrastive rewrite, fresh counters | ✓ | – |
| 10 Prune | above 200 rules, drop the lowest MACLA utility | ✓ | – |
| 11 Consolidate | every 25 games, if ≥ 3 underused rules: fold each into the most similar well-used rule of the same kind and type (with a contradiction check) | ✓ | – |
| batch end | batch_dedupe of near-duplicates written in parallel games | ✓ | – |

**Text-change rules for verified rules (E).** A Builder update may rewrite a verified rule only if (a) it is
young (< 3 credited games), or (b) the judge says this game followed it while the game rejected one of its
commands, or (c) it is a dead recipe (≥ 4 followed games, 0 wins) and this game was won, and in every case
only while `rewrites` < 2. A lost game never rewrites visible text. Any text change resets the counters.
**Refinement and folding are not limited by the cap.**

**Retrieval** (`ranked`/`take`). Candidates are the kind's rules plus general rules (other kinds only for an
unseen kind with evidence ≥ 0.85). Relevance = w·evidence + (1−w)·text, with w = wins/(wins+2), evidence =
similarity of the goal to tasks the rule was written from or won, text = similarity of the goal to the rule text.
Utility = Rel·(0.5+lift) − risk·(0.5−lift)·0.5 + 0.1·H[Beta]. One slot is kept for a rarely shown rule.

### 2.4 Thresholds in play (each is a tunable that can misfire)

`SHOWN 8, BUILDER_SEES 24, NEWEST_SLOTS 2, RARE_SHOWINGS 3, EVIDENCE_PRIOR 2, CROSS_TYPE_EVIDENCE 0.85,
DUP_SIMILARITY 0.85, RETIRE_MIN 4, RETIRE_CONFIDENCE 0.9, USELESS_MIN 8, USELESS_FOLLOWED 0.2, REJECTED_MIN 2,
YOUNG_CREDITS 3, MAX_REWRITES 2, DEAD_MIN 4, CONFIRM_WINS 2, MIN_CONTRAST 3, K_CONTEXTS 15, CAPACITY 200,
CONSOLIDATE_EVERY 25, CONSOLIDATE_MIN 3, CONSOLIDATE_SHARE 0.4, FOLD_SIM 0.6, MAX_FOLD 3, BASE_PRIOR 2, RETRIES 3,
MAX_WRITES {2,2,1,2}, word limits 35/45/25`, plus 9 Anti-Pattern mining constants. That is about 40 constants.
None was tuned on data. Most were set from the paper or from one anecdote.

---

## 3. Decision history (condensed; full log in `results/DECISIONS.md`)

| Date | Decision | Why |
| --- | --- | --- |
| 10-20 | E = verified executable code skills; E-minus append-only; E-text same content as text | the proposal: memory checkable without model judgement |
| 11-14 | lean design (B, later A, dropped; 300 practice; 1 seed; batches of 8) | one RTX 5070 |
| 11-14 | executor replaced by the published ReAct loop | own executor 0/17, ReAct 6/6 |
| 11-15 | code skills judged unworkable with the 9B (81% rejected, error feedback fixed none) | fidelity failure |
| 11-15 | E becomes an AutoManual rule manual, then uncapped with ExpeL votes | plain-language rules avoid code fidelity; 23/30 vs C 19/30 |
| 11-15 | MACLA chosen; its code doesn't match the paper → add its ideas one at a time | strongest small-model result; "don't reinvent" |
| 11-16 | Beta reliability, expected-utility selection, contrastive refine, 0.85 merge, 200 cap | credit, duplicates, correction |
| 11-17 | Builder sees the trace; one short rule form; code length/number checks | 45-60-word, instance-specific rules |
| 11-17 | Reflexion retries (E, E-minus) | contrastive "do Y instead of X" rules; 28/48 vs 21-23 |
| 11-17 | hidden guesses, retirement, no scope widening, task-keyed retrieval | wrong heat recipe shown from a lost game |
| 11-17 | early gate at 75 replaces the pilot; cheap library restart keeps C/D | check usefulness, not plumbing |
| 11-17 | Anti-Patterns from pooled failures | no positive rules for never-won kinds |
| 11-18 | object/room names rejected; kind-specific text can't be scoped "all"; frozen checks use rules-full | non-transferable rules; retrieval silently degraded |
| 11-18 | retrieval variants moot (identical selections at ≤ k rules per kind) | 44-51/70 spread was noise |
| 11-19 | cross-kind actions rejected | cooling recipe said "clean it" |
| 11-19 | flat retrieval kept for long runs (lab, 200-270 rules) | P@8 0.80, same as at 50 |
| 11-19 | usage-based credit, then an outcome-blind judge | junk inherited wins; the Builder's "followed" was outcome-biased |
| 11-19 | consolidation variant B (fold underused into well-used) | owner's idea; read-through review |
| 11-19 | gate passed (25 vs 21); continue | — |
| 11-19 | recipe drift fix (freeze, command evidence, 1 change/batch); restart E | E 47 vs E-minus 61 of 94; 44 recipe versions |
| 11-20 | strip instance numbers, young recipes correctable, stricter guess promotion; restart E + E-minus | heat recipe discarded for "microwave 1" |
| 11-20 | design review: freeze all visible rules, fresh counters, E-minus same bookkeeping, lift ranking, exploration slot, evidence-only deletion, batch dedupe, per-kind base rates; restart E + E-minus | 11 problems found by review |
| 11-20 | games 51-72 dip: no change | judged chance |
| 11-20 | dead recipes rewritable from wins; then only-recipe protection removed and retry wins may rewrite; restart E twice | heat recipe 0/5 and locked |

The pattern: from 11-19 on, every change was triggered by one practice window or one rule seen in a library
snapshot. Changes were then judged by reading rules and by the next practice window, not by frozen checks.

---

## 4. Logical gaps (ranked)

### A. Design gaps: these decide what the final result can mean

**A1. H3 and H4 test the vestigial code-skill channel.**
- `analysis.analyze`: H3 = `('E-minus', 'invocation_success')`; the success criterion requires H3 Holm p ≤ .05.
  `invocation_success` counts *code-skill* calls. H4 compares E and E-text, which see the **same rules**
  (`agents.uses_rules` includes E-text, which is initialised from E's practice memory); only code skills are
  rendered differently.
- Consequence: even a perfect run cannot show that rule management helps. A significant H3 would be about skill
  repair, and H4 is close to a replicate of E.
- Fix (owner decision): amend the protocol. H3 = E − E-minus on **task success** (rule management with
  everything else equal). H4 = drop E-text, or redefine it as a real question (for example "manual vs no manual
  with skills equal", which C vs E already covers). Write this amendment before running.

**A2. Code skills still run in E and E-minus, differ between them, and were never in the checks.**
- `agents._candidate` runs for E and E-minus; skills are offered as callable actions. `Library.record` returns
  `'append_only'` *before* counting for E-minus, so E-minus skills keep their prior reliability forever. E counts
  successes and failures, rolls back and repairs (`updates = condition in {B, E, E-plus}`).
- Live data, E-minus practice (104 games): 25 active skills, 155 candidates (126 rejected = 81%), 78 calls in 43
  games, **27 succeeded (35%)**. A failed call uses steps out of a 15-step subgoal budget.
- `tools/manual_check.py`: "condition E with an **empty skill library**". All the evidence that the manual helps
  (54/70, 49/70, 48/70 vs C 39/70) comes from a configuration without skills.
- Consequence: E vs E-minus mixes rule management with skill repair. E vs C/D includes a skill channel that fails
  65% of the time and was never measured. Some of the E < E-minus windows may come from here: E's skill
  repairs and rollbacks change which skills the actor is offered. Nobody has looked at this.
- Fix (owner decision): (a) turn code skills off for E, E-minus and E-text (recommended; it matches the checks,
  matches the 11-15 decision, and saves the librarian calls, about 2-7% of all calls), or (b) keep them but make both conditions identical
  (same `updates` for the skill library), and check that configuration with frozen checks.

**A3. One library per condition; CIs ignore library variance.**
- `practice_seed` is single. `analysis` bootstraps tasks only. Replicate libraries from the same code scored
  48, 49, 54 of 70 (`LOG` 11-19). Per-kind quality swings (heat 4/9 vs 7/9, two-object 5/12 vs 9/12). The
  diagnosis of 11-20 found 7 E runs disagreeing on about 14 of 48 games.
- Consequence: "E beats D by 10 pp" could come from one lucky or unlucky library and still look significant.
- Fix: at least 2-3 practice replicates of E and E-minus (different practice orders), with the library as a
  random effect, or report the replicate spread next to the CI. If compute is fixed, 3 × 150 games tells you
  more than 1 × 300. Owner decision.

**A4. Retries give E/E-minus practice content that D cannot get.** E and E-minus learn from retry wins; D stores
first-attempt wins only. That is fine *if stated* (retry cost is charged to H2), but H1 then compares "rules +
retries" with "trajectories, no retries". Options: give D retry-won trajectories too, or state it as part of the
method.

**A5. Stale documentation.** `README.md` describes code skills as the library, updating evaluations and 2 seeds.
`protocol.py`'s amendments mention batches of 4 and E-plus. Anyone (human or agent) who reads them reasons from
the wrong system. Rewrite the README after section 5's decisions.

### B. Process gaps: these cause the restart loop

**B1. Restart triggers sat inside the noise floor, and the window was looked at repeatedly.**
Paired practice games: E and E-minus disagree on d ≈ 0.26-0.29 of games (15/57, 14/48). The SD of (E wins −
E-minus wins) over n games is about √(n·d):

| games in window | 2-SD noise band on the win difference |
| --- | --- |
| 25 | ±5 |
| 50 | ±8 |
| 100 | ±11 |
| 300 | ±19 |

E 24 vs E-minus 28 of 50 and E 38 vs 41 of 80 are noise. E 25 vs 34 of 57 (3 vs 12 discordant, p ≈ 0.035) was the
one borderline case, after about 10 looks. With that many looks it is not significant. The LOG says this itself
("mostly chance", "this E run lowest of 7, this E- run high"), but the restart happened anyway because a real
defect was also found. Real defects can be found and fixed without a win-rate trigger (B2).

**B2. Mechanisms were validated on anecdotes, not on known ground truth.** Each fix added a threshold and a code
path (about 40 constants, section 2.4). Interactions were found live (the freeze locked a wrong recipe → dead
recipe → the cap → only-recipe protection → removed). Every one of these is a deterministic function of
(judge verdict, game outcome, base rate). They can be simulated on CPU with synthetic rules of known quality in
seconds, without the model. Section 4C shows such a simulation.

**B3. The gate is weak and sits on the tuning set.** 30 games, margin 0: if E = C, it passes about 50%+ of the
time. It uses the first 30 of the 70 dev games that every library check also used. Its record (`restarts.json`) is
20-21 failed, 25-21 passed, 24-21 passed: all within ±4 of a tie, which says little. Either drop it (the decision to continue is made on
other grounds anyway), or make it a bug detector (E ≥ C − 3, for example) and stop reading it as evidence.

### C. Rule-management gaps still in `manual.py`

Simulation (CPU, 20,000 trials): a rule whose true win rate **equals** its kind's base rate (neither helps nor
hurts), followed in every game of its kind, 50 games of that kind (about one kind's share of 300 practice games):

| kind's base rate | refinements triggered | "dead recipe" events | P(good rule retired by "never won in 4") |
| --- | --- | --- | --- |
| 0.10 (heat-like) | 0.8 | 3.0 | 0.66 |
| 0.25 | 1.7 | 1.2 | 0.32 |
| 0.50 | 1.5 | 0.2 | 0.06 |
| 0.75 | 0.1 | 0.0 | 0.00 |

**C1. The base rate is not a counterfactual.** `base_types` counts every game of the kind since the rule was
written, *including the games where the rule itself was shown and followed*. A recipe is shown first in every
game of its kind, so the base rate mostly **is** the recipe's own win rate. Lift ≈ 0 by construction. The
retirement test (P(rate < expected) ≥ 0.9) can never fire on a mediocre recipe. A wrong recipe is caught only by
"0 wins", and a merely bad one never. The same holds to a lesser degree for any rule shown in most games of its
kind.
- Fix options: (a) **randomised withholding**: in practice, withhold each eligible non-recipe rule with
  probability ~0.2 and the recipe with ~0.1, and compare the win rate shown vs withheld. This is the only clean
  per-rule effect estimate. It costs a few practice wins and no extra calls. (b) Use C's per-kind win rate as
  the fixed reference (C has 204 evaluated games; per-kind rates are available). Weaker, but cheap.

**C2. Contrastive refinement is an uncapped drift channel.** `refinable` needs ≥ 3W, ≥ 3L since the last change
and wins < expected. Per C1, for a recipe that is about 50/50. `refine` is **not** limited by `MAX_REWRITES`
(`text_frozen`'s docstring: after the cap, "only contrastive refinement changes the text"), and every refinement
resets the counters, so the next trigger can come a few games later. Simulated: about 1.5 random rewrites per
recipe per 50 games at base rates of 0.25-0.5. This is the same drift that was "fixed" on 11-19, through a side
door. Fix: count refinements against the cap, and require statistical evidence of underperformance (the Beta
test against a real counterfactual, C1), not wins < expected.

**C3. "Never won" rules misfire in hard kinds.** `retirable`: won == 0 after ≥ 4 followed games retires the rule
if the kind had *any* win. `dead_recipe`: 0 wins in ≥ 4 → rewrite from the next win, and at the cap → retire.
With a 10% base rate, a rule that is fine dies 66% of the time, and a fine heat recipe goes "dead" about 3
times in 50 games. This is why heat recipes keep being rewritten, retired and rewritten. Fix: replace the hard
"0 of 4" rules with the Beta test against the (counterfactual) base rate, so 0/4 means nothing at p = 0.1 and
a lot at p = 0.6.

**C4. Judge failures silently switch credit regimes.** `judge_followed` returns None on any error and every shown
rule is credited. That happened in **16 of 104** E-minus games (15%). Those games put wins and losses on rules
that were not followed and skip `unused`, which pushes up "followed" shares for the useless test. Fix: on judge
failure give no credit (skip the Beta update for that game, log it) instead of crediting everything. Also check
why 15% fail (schema? truncation at 512 tokens?).

**C5. Builder votes are inert.** `importance` is used for ranking only when no similarity function is given
(`ranked`), and the study always passes one. Upvotes and downvotes cost Builder tokens and appear in the
prompt and docs, but change nothing. Either drop them from the schema, or note that they are logging only.

**C6. The deferred change is not implemented.** DECISIONS 11-20 deferred "promote a guess only if followed wins ≥
expected wins + 1, and demote it if it later fails". `promoted()` still uses `wins >= expected_wins`, and
there is no demotion. Decide: implement it in the fix batch, or drop it from the log.

**C7. Retirement and edits use partial evidence in batches.** A game's `retire` op is decided on its private copy
(pre-batch rules + its own outcome) and replayed onto the live library, where 7 other outcomes may have changed
the picture. Minor at the current thresholds, but it compounds C3. Better: run `retire` once at commit time on
the live library (as `batch_dedupe` already does).

**C8. Known and accepted.** The two-object subgoal check can pass with one object placed (shared by all
conditions; fixing it would invalidate C/D). Retrieval choices are moot at the current size, and the
exploration slot never fires; don't spend time there.

---

## 5. Plan: one batch of fixes, then one run

### Step 1: owner decisions (before any code)
1. **What is E?** Recommended: the rule manual only, with code skills off for E, E-minus and E-text (A2).
2. **Protocol amendment** (A1): H3 = E − E-minus task success; H4 dropped or redefined; success criterion
   restated without invocation success.
3. **Replicates** (A3): how many practice replicates per library condition, and at what length.
4. **D and retries** (A4): give D retry-won trajectories, or state the asymmetry.
5. **Gate** (B3): drop it, or recast it as a bug detector with a stated margin.

### Step 2: fix batch (one commit, verified offline)
- C1 counterfactual (randomised withholding or C's per-kind rates) → C2 refinement under the cap with a real test
  → C3 hard "0 of 4" rules replaced by the Beta test → C4 no credit on judge failure → C5 votes removed or
  marked → C6 decided → C7 retire at commit.
- **Mechanism simulator** (new, CPU only, `tools/sim_mechanisms.py` + tests). It feeds synthetic rules with
  known true effects (helpful, neutral, harmful) through `observe`/`retirable`/`refinable`/`text_frozen` at base
  rates 0.1-0.8 over 300 games, with a noisy judge (e.g. 85% accuracy, 15% failures). Acceptance criteria,
  written down before running it, for example:
  - neutral or helpful rule falsely retired ≤ 5%;
  - text changes of a neutral recipe ≤ 0.3 per 50 games;
  - a clearly harmful rule (−20 pp) retired or rewritten within 30 followed games ≥ 80%.
  This replaces "run practice and watch the window" as the test of a mechanism.
- One frozen 70-game check of a library built with the final code, **in the exact study configuration**
  (skills on or off as decided), against C on the same games. That checks the configuration, not the
  mechanisms, and it runs once.

### Step 3: freeze rules for the run
- Record the commit hash in `settings.json`/DECISIONS. From then on, only **crash bugs** and **implementation
  bugs that a unit test reproduces** (code doing something other than what the spec says) may trigger a
  restart.
- **Win-rate windows never trigger a restart.** Monitoring reads them against the noise table in B1 and logs
  them; nothing more.
- Library oddities seen in snapshots (a wrong step in a winning recipe, an overfit rule) are logged as
  findings about the method at the 9B ceiling. They are part of the result, not a reason to restart.
- The analysis script and the amended hypotheses are committed before the first evaluation game.

### Step 4: run
Restart E and E-minus (and the replicates) with `-RestartLibrary`. C stays. D stays unless step 1.4 changes it.
Snapshots every 25 games stay for tracking.

### Expected cost of the plan
The fixes and the simulator are CPU work (a few hours of agent time, no GPU). The frozen 70-game check takes
about 1 GPU hour. Replicates are the only large cost, and that is the owner's call in step 1.3.
