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

### 2026-11-19 — No full study until long-run library management is verified
- **Decision:** the study may run only up to its 75-game early gate. It continues past the gate only after
  the current retrieval/management has been tested at the library size of a long run (3000+ episodes,
  about 200-300+ rules). The current method stays if it holds up; extra structure (a tree, merging) comes
  only if it clearly degrades.
- **Why:** the real libraries so far are small (15-30 rules), where retrieval choices make no
  difference. A long run grows the library about 10x, and a management problem found late would waste
  the whole run. Owner's preference: keep it simple unless the evidence demands more.

### 2026-11-19 — Keep flat task-keyed retrieval for long runs (no tree, merging or MMR)
- **Decision:** keep `for_agent` in 'task' mode (SHOWN 8, CAPACITY 200) for the long study. The owner's tree
  idea, merging and MMR were not built.
- **Why:** lab benchmark (`results/lab/REPORT.md`): a long run reaches about 150-200 rules (growth 0.2-0.3
  rules per game, capped at 200). At 200-270 rules the current retrieval has P@8 0.80-0.82 and nDCG@8
  0.87-0.88, the same as at 50 rules, with about 0 duplicates and 3-5% wrong-kind rules, at 20-40 ms per
  query with no model calls. The owner asked to keep it simple when it is good enough.
- **Open issue found:** junk accumulation, not size, is the long-run risk. Retrieval screens junk out
  only if its win/loss counts are worse. But every rule shown in a game gets the same credit, and no real
  run has retired a rule yet. So credit assignment and retirement are the next things to fix before the
  full study.

### 2026-11-19 — Usage-based credit: only rules the agent followed get win/loss credit
- **Decision:** after each practice game the Builder (already called once per game) also lists which of the
  shown rules the agent's actions actually followed. Only those get the Beta win/loss update. Recipes
  shown to the planner always count as followed. A rule shown at least 8 times and followed in under 20%
  of them is retired as useless (recipes and Anti-Patterns exempt). If the list is missing, every shown
  rule is credited as before.
- **Why:** the lab found junk accumulation to be the long-run risk. With all co-shown rules getting the
  same credit, junk inherits the wins of good rules, is never retired (no real run had retired a rule),
  and retrieval cannot screen it out. MACLA itself updates a procedure's reliability only when it was
  executed. Using the existing Builder call adds no model calls and leaves the play prompts (and C/D)
  unchanged.
- **Risk to watch:** a Builder that under-reports "followed" starves good rules of credit. Checked on a
  live practice (practice-f) before the study's E library is restarted.

### 2026-11-19 — Tree-structured library dropped
- **Decision:** the hierarchical (tree) library idea is dropped for good; it was never implemented.
- **Why:** the current flat retrieval holds at long-run size (lab benchmark at 200-270 rules) and on a real
  71-rule union library (50/70 vs C 39/70). A tree would add model routing calls and routing errors with no
  measured benefit. The owner agreed to drop it if retrieval was good enough.

### 2026-11-19 — Periodic consolidation of underused rules (fold into well-used rules)
- **Decision:** every 25 practice games, if at least 3 underused rules exist, fold each underused rule into
  the most similar well-used rule of the same task type and rule type. The model rewrites the absorbing
  rule to also cover it, still at most 25 words and passing all live text checks. A quick model check
  skips rules that give conflicting advice. Recipes and Anti-Patterns are never merged. Underused means few
  credited games but decent reliability. Merging underused rules only with each other (variant A) was
  rejected.
- **Why:** the owner's idea. Narrow but correct rules rarely fire; folding them into a rule that already
  fires makes it more complete. In a review of real merges, B kept concrete commands ("search countertops
  first, then use the fridge instead of the sinkbasin") and absorbed junk. A produced vague text ("cool it
  with the appliance"). B once merged two contradictory rules, hence the conflict check. The effect is small
  (about 3-5% of rules), so it adds little complexity. Judged by reading the merges, not by 70-game runs (the
  owner's call: start the study soon).

### 2026-11-19 — "Followed" is judged blind to the game outcome
- **Decision:** which shown rules were followed is decided by a separate model call that sees the goal, the
  rules and the actions, but not the outcome. The Builder no longer decides it.
- **Why:** in practice-f the Builder (which knows the outcome) said "not followed" in lost games where the
  agent clearly did what the rule said, and "followed" in won games. Rules would then collect only wins and
  never be retired, which is worse than crediting all shown rules.

### 2026-11-19 — Study continues past the 75-game gate
- **Decision:** let the study continue past its passed gate (E 25/30 vs C 21/30, 4 games won where C lost, 0 the
  reverse) with the current library management.
- **Why:** long-run management is in place and verified live. Retrieval holds at long-run size, credit is
  outcome-blind, and retirement and consolidation fire (1 retirement, 1 fold and 2 merges in 76 games; the log shows the retirement 8 times, once per game of its parallel batch). The remaining
  wrong rules ("take the lamp", "leave it on the surface to cool") survive only because the wrong step is
  harmless in won games. Fixing them by hand would inject ALFWorld knowledge into a learning condition, and
  a new mechanism would add complexity near the model's ceiling.

### 2026-11-19 — Measure library improvement over time with 3 frozen snapshots
- **Decision:** evaluate E's library frozen after 100, 200 and 300 practice games (1/3, 2/3, full) on the same
  evaluation games (134 unseen-room plus 70 seen-room) as the study's final evaluation. The 300 point is the
  study's own evaluation. The 100 and 200 points get extra frozen runs after the study (tools/snapshot_eval.py),
  compared game by game with C and with each other (tools/compare_snapshots.py).
- **Why:** the owner wants to know whether and how much the library improves with more practice. Checkpoints
  store the library after every game, so the snapshots need no extra practice, only about 400 extra
  evaluation games.

### 2026-11-19 — Stop recipe drift; check instructed commands against game traces; restart only E
- **Decision:**
  1. A verified Success Process recipe may change only through contrastive refinement (at least 3 new wins and
     at least 3 new losses), never through a single game's update. A retry win may write new rules but not
     rewrite visible ones.
  2. A rule whose instructed command (e.g. "take the lamp") was rejected by the game in at least 2 games where it
     was followed, and never succeeded in a won game, is retired. This is evidence-based management, E only.
  3. At most one text change per rule per parallel batch.
  4. The study restarts only E (and E-text, which uses E's library). C, D and E-minus games are kept. E-minus is
     kept only if a probe shows its append-only path is unchanged.
  - The shared two-object subgoal check (a step can pass with only the first object placed) is left as it is:
    it affects all conditions equally, and changing it would invalidate the finished C/D games.
- **Why:** in the study, E won 47/94 practice games against E-minus's 61/94 on the same games. The diagnosis
  (LOG 2026-11-19) traced it to recipe drift. E's 6 recipes went through 44 versions as the Builder rewrote
  "search X first" to wherever the last object happened to be. In the games E lost and E-minus won, E made
  263 cabinet and drawer moves against E-minus's 64. A never-checked impossible step ("take the lamp") sank
  look-at-light tasks (3/7 vs 6/7). Retrieval and the new credit/retire/fold machinery were ruled out. The
  owner asked to salvage the run, so only E is redone (about 94 games).

### 2026-11-20 — Repair (don't discard) rule text; young recipes stay correctable; stricter promotion of guesses
- **Decision:**
  1. Shared text check (both conditions): instance numbers are stripped deterministically ("microwave 1" ->
     "the microwave") before the numbered-object check. Other failures (e.g. length) get one model rewrite.
     A rule is dropped only if it still fails after that.
  2. E only: a verified recipe may still be rewritten from a single game while it has fewer than 3 credited
     games, or when a step it instructs was rejected in a game where it was followed. After that the drift
     freeze applies.
  3. E only: a hidden guess (rule from a lost game) is shown only after at least 2 won games where the
     outcome-blind judge says it was followed (was: one win).
  - E and E-minus are both rebuilt, because (1) changes a check they share. C and D are kept.
- **Why:** second diagnosis of E < E-minus (25 vs 34 of 57 paired games after the drift fix). The drift fix
  worked, and most of the gap was chance in which first recipe got written. But E's heat recipe had been
  thrown away for naming "microwave 1", leaving E without a heat recipe (heat 0/6 vs 4/6). Its first
  accepted heat recipe had a wrong step order that the freeze then locked in. A weak "check inventory"
  guess was shown in 24 games after a single win. A filter that randomly discards recipes adds noise to the
  main E vs E-minus comparison, so it is fixed for both.

### 2026-11-20 — Design review: stabilise all rules, fair E vs E-minus, evidence-only deletion
Owner asked for a full review ("changing a rule after every use is stupid"). An independent review found:
1. **Drift in non-recipe rules.** Corrected Error and Special Phenomenon rules were still rewritten by single
   won games, keeping the old text's credit (a rule flipped A->B->A; one changed topic entirely).
   **Decision:** the text freeze applies to every visible rule, with the young-rule (< 3 credited games) and
   rejected-step exceptions. Any text change of a verified rule starts fresh counters (alpha/beta, contexts,
   confirmations).
2. **Refinement as a drift channel.** **Decision:** contrastive refine only for rules whose followed-win rate is
   below their task type's base rate, with fresh counters for the new text.
3. **Circular recipe credit and unlucky retirement.** **Decision:** recipes are credited only when the judge says
   they were followed. Never-won retirement only if the type has had wins. A task type's only recipe is never
   retired.
4. **Confound.** E-minus had no evidence bookkeeping, so its retrieval was text-only and its guesses could never
   be shown. **Decision:** E-minus gets the same bookkeeping (Beta, contexts, base rates, judge, guess promotion)
   for retrieval and visibility. E and E-minus now differ only in that E may edit, delete, merge and fold
   rules.
5. **Starvation of new rules.** **Decision:** one of the shown slots is kept for rarely shown rules, and ranking
   uses lift over the base rate instead of raw wins.
6. **Guess promotion on wins only.** **Decision:** count followed losses too, require a followed-win rate >= the
   base rate, and reset on a text change.
7. **Outcome-aware deletion by Builder votes and different Builder views.** **Decision:** rules are removed only
   by statistical retirement, never by votes. Both conditions' Builders see rules ranked by relevance, with
   slots for new rules.
8. **Corrected Error used as a second recipe.** **Decision:** the recipe-shape check applies to Corrected Errors.
9. **Near-duplicates across a batch.** **Decision:** E re-runs the similarity merge after replaying a batch.
10. **Folds double-count credit and fold unevidenced rules.** **Decision:** a fold keeps the stronger rule's
    counts, and an absorbed rule needs at least one won credited game.
11. **Base rate for general rules.** **Decision:** expected wins = the sum of the base rates of the followed games'
    task types.
- E and E-minus are restarted again (fix 4 changes E-minus). C and D are kept.
- **Why overall:** each mechanism could make a 300-game library worse or the comparison unfair. Fixing them
  costs only a few minutes of already-paused E/E-minus practice.
