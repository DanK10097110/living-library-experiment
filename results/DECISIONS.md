# Library decisions

Architectural and algorithmic decisions about condition E's library (rule manual), its retrieval and
its management, with the reason for each. Newest decisions are appended at the end of each section.
Run-level details and numbers live in `results/LOG.md`.

## History up to 2026-11-17

_Reconstructed on 2026-11-19 from git history, archive/, results/, the proposal, memory notes and session transcripts. Times in transcripts are UTC, so a date can be off by one. Items marked "(inferred)" are not stated explicitly in a source._

### 2026-10-20 — Original design: E is an executable code-skill library
- **Decision:** the proposal defines E as a library of generated Python skills with pre/postconditions in a fixed predicate vocabulary checked by the simulator, a Beta reliability score per skill, repair by a "librarian" (a repair must pass stored regression states; old versions kept for rollback), and admission only if a candidate replays successfully and its stated result matches what happened. E-minus is the append-only variant, E-text the same content as prose. Consolidation (merge/prune) stays out of the core study as an optional extension (E-plus, `extensions.py`).
- **Why:** the study asks whether an updating, verified, executable memory beats trajectory memory (D) and no memory (C), so every library operation had to be checkable without model judgement. Consolidation was kept out so that E vs E-minus measures updates only.

### 2026-11-12 — First implementation: planner plus actor with catalog and per-step skill retrieval
- **Decision:** the planner sees the whole skill catalog (names and signatures, no code); at each step the actor gets the top 3 skills whose preconditions hold right now, ranked by similarity to the subgoal plus reliability. No merging, meta-skills or pruning in the core run.
- **Why:** follows the proposal (a table of contents always loaded, details only when needed). On 2026-11-15 putting the whole library in the prompt was rejected as too costly (about 4x prompt tokens at 100+ skills, and this server cannot reuse cached prompts). The same day the early libraries already showed duplicates (four `take_object_from_*` skills after 15 episodes), and consolidation as a separate arm (E-plus) was recommended instead of folding it into E; the owner's choice is not recorded (inferred: left optional).

### 2026-11-14 — Lean design: cut conditions and practice length to fit local compute
- **Decision:** drop condition B (later also A), practice 500 -> 300 episodes (pilot 100), pilot development 140 -> 70 games, 3 seeds -> 1; D and all 134 OOD evaluation games stay. Practice runs in batches of 8.
- **Why:** one RTX 5070 made the full design about 60 hours or more; the proposal itself lists the cut order. It shaped the library work because libraries only see 100-300 practice games, so cheap checks (48-game practice plus a 30-game comparison with C) became the way to iterate on the library.

### 2026-11-14 — Executor replaced by the published ReAct loop; skills distilled as action-sequence code (AdaPlanner style)
- **Decision:** inside each subgoal the actor acts step by step with the ReAct loop (verl-agent prompt plus ReAct examples) instead of writing a whole program first. Library skills are distilled from successful subgoals as code over `goto/take/put/open/clean/heat/cool/turn_on` plus a search loop, verified by replay, then offered to the actor as actions. The merge of 2026-11-17 kept this pipeline and rejected the other contributor's executor-era changes.
- **Why:** the repo's own agent scored 0/17 with the large MoE model while the published ReAct loop solved 6/6: the executor wrote programs blind, before seeing the room, and ALFWorld requires looking around. Planner, library, admission, versioning and analysis were kept.

### 2026-11-15 — Code skills judged unworkable with the 9B model
- **Decision:** after the owner asked "is the skill-writing prompt bad or the checker too strict?", a Voyager-style loop was added that feeds the exact rejection error back to the writer for a repair. It was measured, and code skills as E's content were abandoned.
- **Why:** 81% of candidate skills were rejected; over 24 games none of about 60 rejected skills was fixed by the error feedback (rejections stayed at 81%). The writer described the whole task instead of the demonstrated subgoal (a fidelity problem). Conclusion: the 9B can write plausible code but not code that verifiably does what was demonstrated.

### 2026-11-15 — Switch E's library from code skills to a plain-language rule manual (AutoManual)
- **Decision:** E's library becomes a rule manual after AutoManual: each rule has a type (Success Process, Special Phenomenon, Corrected Error, Unresolved Error), text starting with when it applies, an example and a validation log; a case-conditioned Builder runs after every practice game, there is one Success Process per task type, and a lost game may update but not write a recipe. The first version was capped at 12 rules.
- **Why:** rules in plain language remove the code-fidelity failure. First real check (offline Builder over 40 archived practice games, then 30 dev games, frozen manual vs C on the same games): capped manual 23/30 vs C 19/30, with about 30% fewer model calls per game. A Builder token-limit fix removed 11 cut-off answers.

### 2026-11-15 — Uncap the manual and manage it ExpeL-style
- **Decision:** no rule cap. Each rule has an importance count (start 2, upvote or edit +1, downvote -1, removed at 0) as in ExpeL, and each game shows only the 8 most relevant rules. The result was saved as `archive/2026-11-15-automanual-expel/`.
- **Why:** a cap drops rules arbitrarily; ExpeL (AAAI 2024, also on ALFWorld) is the closest tested way to let wrong rules die as later games contradict them. The uncapped version scored 21/30 vs 23/30 capped (C 19/30), a gap within noise at 30 games, so principle decided. The vote version was unit-tested but never run on real games before MACLA was considered.

### 2026-11-15 — Look for newer methods: MACLA chosen, then found not to match its released code
- **Decision:** after reading newer work (including EvoLib and SkillSmith, cited by the proposal) the owner chose MACLA (AAMAS 2026, arXiv 2512.18950) as the method for E. Reading its released code showed it does not implement the paper (accuracy from dataset labels fed into memory, segmentation by thirds, refinement output never read, no embedding retrieval, crashing `main`; the paper itself is inconsistent on thresholds and pruning). Recommendation accepted: keep AutoManual+ExpeL as the baseline and add MACLA ideas one at a time, each tested by the 30-game check.
- **Why:** MACLA reports 90.3% on unseen ALFWorld with a frozen 4-bit 7B-class model (our size), stores abstract procedures instead of code, uses Beta reliability (which the proposal already took from it) and contrastive refinement; AutoManual, ExpeL and ACE relied on GPT-4-class models. The owner wanted published, tested methods ("don't reinvent the wheel").

### 2026-11-16 — MACLA ideas added from the paper on top of AutoManual+ExpeL
- **Decision:** Beta(1,1) reliability per rule, updated by the outcome of each game where the rule was shown; selection by expected utility (R_max 1, C_fail 0.5, lambda 0.1) combining relevance, reliability and failures on this task type; contrastive refinement once a rule has at least 3 new wins and 3 new losses (a refiner role); merge of near-duplicates at similarity >= 0.85; utility pruning above 200 rules. MACLA meta-procedures not taken.
- **Why:** these target weaknesses of the ExpeL-only manual: rules never credited with outcomes, per-object near-duplicates, no correction by evidence. Our rules have no end conditions to check, so the game result is the credit signal. Meta-procedures were skipped because the paper and its code give no usable detail (inferred).

### 2026-11-17 — Builder must see the game trace; one short general rule form
- **Decision:** fix the "trace fix" bug (the Builder saw no game steps) and rewrite the Builder and refiner prompts to one rule form, "If/When <condition>, <action>.", at most 25 words (Success Process: 5 generic steps, 40 words), no numbered objects, no type label in the text. Updates and refinements rewrite the whole rule instead of appending cases. A code check rejects text over 35 words (45 for Success Process) or naming numbered objects. The response schema lists only the types allowed in the current case, and the prompt names the existing recipe.
- **Why:** `results/library-comparison.md`: AutoManual+ExpeL rules averaged 45-60 words with up to 84% instance-specific; MACLA versions had a "when When" bug and appended cases (a 115-word rule); rules written from empty games were meaningless ("no steps recorded"). Of 29 rejected Builder operations, 18 were a failure writing a Success Process and 11 a duplicate recipe. The causes were prompts shared by all versions, not MACLA.

### 2026-11-17 — ExpeL/Reflexion retries of lost practice games
- **Decision:** a lost practice game of E or E-minus is replayed with a short reflection, up to 3 retries; the Builder contrasts the failed and the won attempt into a Corrected Error rule. Success counts the first attempt only; retry cost is added to the totals.
- **Why:** a win that contrasts a loss yields the "do this instead" rules ExpeL reports. `results/mini-macla-retries`: 28/48 first-attempt practice wins (21-23 before), 23/30 vs C 19/30 (7 games won over C, 3 lost), 16.7 calls per game, 5 of 18 lost games won on a retry.

### 2026-11-17 — Hide unconfirmed rules, retire losers, no scope widening, task-keyed retrieval
- **Decision:** (1) a rule written from a never-won game stays a hidden Builder note until a win confirms it, whatever its type; (2) a rule shown in 4 or more games with no win, or below the base rate of its task type, is retired; (3) merging can no longer widen a rule's scope to all task types; (4) retrieval ranks rules by similarity of the current task to the tasks in which the rule won, falls back to rule text for new rules and unseen tasks, and still lets strong general rules from other task types in.
- **Why:** problems found in the retry run: a wrong heat recipe (W0 L4, "turn on the stoveburner first") was shown because it came from a failed-retry game; it could not be retired by a base-rate comparison since heat was never won; a cleaning-specific rule was merged and widened to every task. Task-keyed retrieval shows rules only where they have evidence. `results/mini-macla-retrieval`: manual 24/30 vs C 19/30.

### 2026-11-17 — Pilot removed; early gate with library restart
- **Decision:** the separate pilot is dropped. The study runs library practice to 75 games, then plays E with frozen rules against C on 30 paired dev games (`gate.json`). If E wins minus C wins is below the margin (default 0) it stops with exit code 3; `--past-gate` continues; `--restart-library` redoes the library practice and keeps C and D games, but only if just `manual.py`, `library.py` or `consolidation.py` changed, or the C/D behaviour probe is unchanged. D's practice starts only after the gate passes.
- **Why:** the pilot checked plumbing (program failures, skill reuse) but not whether the library helps, and cost compute. An early check on the library itself, with a cheap restart that preserves the expensive C and D streams, lets library bugs be fixed without paying for the study twice. The gate then failed with the older library (20 vs 21; `results/study-E-library-at-gate.txt`: 37/80 wins, 18 rules, mostly clean-task variants), which is why the library work continued (inferred link).

### 2026-11-17 — Anti-Pattern ("avoid") rules from pooled failures
- **Decision:** add `avoid.py`: never-won failures are pooled by task type, a deterministic miner finds repeated failing patterns, the model words a "don't do X" rule, and post-checks reject bad wording. Synthetic check 60/60.
- **Why:** rules came only from single games, and heat tasks were never won, so no positive rule existed there; negative knowledge from pooled failures was the missing channel (inferred). Its live behaviour was judged on 2026-11-18 (see below).

## 2026-11-18 onward (autonomous session)

### 2026-11-18 — Keep Anti-Pattern ("avoid") rules, but treat them as unproven
- **Decision:** keep the avoid-rule mechanism (pooled never-won failures → "don't do X" rules) switched on.
- **Why:** in the first live 48-game run it wrote no rules at all. Real failure pools rarely share one
  mined pattern, so it is cheap and harmless. In the next practice it wrote one ("when cooling, don't
  use the command 'done'"). That reflects a real agent habit (emitting an invalid "done"), so it
  is not wrong. Fixing the habit in the shared prompt would change conditions C/D, so it stays a rule.

### 2026-11-18 — Keep task-keyed retrieval; retrieval variants are moot at the current library size
- **Decision:** keep the current task-keyed retrieval (the game's goal is matched to tasks where the
  rule won, with fallback to the rule text) as the default. Placeholder-goal, planner-plan (HyDE) and
  per-subgoal "steps" retrieval stay available behind a switch (`--retrieval`, `LL_RETRIEVAL`).
- **Why:** on 70 dev games with frozen rules, every variant showed the *identical* set of rules in every
  game. The library holds at most about k rules per task type, so ranking never changes the
  selection. The 44–51/70 spread between variants is therefore pure run-to-run noise (about ±4 games
  in 70), not a retrieval effect. Revisit this only when libraries grow beyond k rules per task type.

### 2026-11-18 — Rules must not name specific objects or rooms
- **Decision:** a deterministic post-check flags rule text that names a portable ALFWorld object (plate,
  tomato, fork, mug, …) or "room(s)". The Builder gets one rewrite attempt ("use 'the object' / 'the
  target'"). If the rewrite is still specific, the rule is rejected and logged. The builder guide
  also says so. Appliances and fixtures (sinkbasin, fridge, microwave, desklamp, cabinets, …) are allowed.
- **Why:** inspection of live libraries showed many Corrected/Unresolved Error rules tied to one game's
  object ("When searching for a tomato to cool…", "cool plate … cabinet"). Such rules don't transfer
  and waste prompt space. "Search all rooms" is wrong for ALFWorld, where a game is a single room.
  Following AutoManual's "general, reusable rules" principle.

### 2026-11-18 — Kind-specific rules may not be scoped "all"
- **Decision:** a rule the Builder scopes to all task types is narrowed to the game's task type if its
  text mentions a kind-specific action or appliance (cool/fridge, heat/microwave, clean/sink,
  lamp/light, two/multiple objects). This applies on write, update and merge.
- **Why:** a cooling recipe was scoped "all" and shown in every game of every task type (Beta 24/10,
  inflated by unrelated wins). That is retrieval noise and misleading credit assignment.

### 2026-11-18 — Frozen checks must use the full rules (with their evidence)
- **Decision:** usefulness checks load `rules-full.json` (rules with their won-game contexts: tasks,
  plans, steps), not the stripped `rules.json`.
- **Why:** the stripped export dropped the evidence that task-keyed retrieval uses. Every earlier
  frozen check had silently fallen back to matching rule text, and plan retrieval could not be tested.

### 2026-11-18 — Keep ExpeL retries as they are
- **Decision:** no change to the retry loop (up to 3 retries of a lost practice game, with accumulated
  Reflexion reflections).
- **Why:** the reflections often repeat almost word for word, which looked like waste. But 4 of the 9
  retry wins came on attempts 2–3, because the replays differ, so the extra attempts do pay off.

### 2026-11-19 — Run hygiene (affects how the library is evaluated, not its design)
- **Decision:** run at most about 3 experiment processes at once, and drop the WSL page cache when free
  RAM falls below 12 GB. Library checks use 70 games (all dev games), not 30.
- **Why:** five parallel runs exhausted RAM and the runs were killed. With run-to-run noise of about
  ±4 games in 70, 30-game checks cannot separate library variants.

### 2026-11-19 — Start the study with the current library code
- **Decision:** start the long study (`run.ps1 study -RestartLibrary`), which rebuilds E's library from scratch with the current code. It stops at the 75-game gate unless E >= C.
- **Why:** frozen libraries from the current code clearly beat C on all 70 dev games (49/70 and, for the
  best library from almost the same code, 54/70, vs C 39/70, with paired wins 15-18 vs losses 3-5). Rules
  are now general (no object names, no wrong scope). The remaining junk rules are rare and are left to
  Beta retirement over 300 practice games. Known weak spots to watch at the gate are two-object and
  clean tasks.

### 2026-11-19 — Rules may not contain another task kind's action
- **Decision:** a rule scoped to one task type must not contain the action of another kind (clean,
  cool or heat, using a lamp, handling two objects). One Builder rewrite ("remove steps of another kind of
  task"), else the rule is rejected. Appliance names used only as places to search are allowed.
- **Why:** Success Process recipes copy every step of the winning game. In the restarted study's
  library a cooling recipe said "clean it with sinkbasin, cool it with fridge". The game won
  anyway, so Beta reliability can never catch such a wrong step, and it would teach a wrong recipe.
  The E library of the study was restarted after this fix (C/D games kept).
