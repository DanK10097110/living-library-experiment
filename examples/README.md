# Examples: real recorded episodes and libraries for the presentation

Everything in this folder was extracted read-only from real runs of the experiment (the saved run checkpoints); nothing is simulated or edited, except that internal paths are removed and long fields are trimmed. 60 examples in total, about 1051 KB.

## The experiment in one paragraph

A small local LLM (Qwen3.5-9B, 4-bit) plays ALFWorld, a text household game ("put a clean lettuce in countertop"): each game is one room, the agent has a budget of **30 steps**, and a game is won only when the simulator says the goal holds. There are six kinds of task: *pick and place*, *clean then place*, *heat then place*, *cool then place*, *look at an object under a lamp* and *two objects*. The agent is hierarchical: a **planner** call turns the goal into subgoals, an **actor** call picks one admissible command per step (ReAct style: `go to fridge 1`, `take lettuce 1 from fridge 1`, `heat mug 1 with microwave 1`). The question: does a *memory that is learned during practice games* make the same agent win more games, and which kind of memory?

## Conditions

| Cond | Memory | What the agent sees |
|---|---|---|
| **C** | none | goal + admissible commands + the last steps |
| **D** | trajectory memory | the 3 most similar *won* practice games as demonstrations (goal + valid action list) in the actor prompt |
| **E** | rule manual (library) | up to 8 short rules chosen from the goal, shown to the planner *and* the actor |
| **E-minus** | append-only manual | same practice as E, but rules can only be added, never updated, merged, refined or voted |
| E-text | E's rules as step lists | not in these examples |

### How the rule manual (E) is built (practice phase)
Every practice game, a **Builder** call (an LLM) reads the game and answers with JSON operations; code then enforces guards. Rule types (AutoManual / ExpeL / MACLA ideas): **Success Process** (a recipe: one per kind of task), **Special Phenomenon**, **Corrected Error** ("when X, do Y instead of X", written from a retry win), **Unresolved Error** (a Builder note from a game that never won: hidden), **Anti-Pattern** ("when X, do not Y", mined by code from pooled never-won games, only worded by the model) and **Failure Pool** (hidden bookkeeping used to mine Anti-Patterns). Each rule carries a **Beta(alpha, beta)** reliability (starts at (1,1), +1 alpha when a game where it was shown is won, +1 beta when lost). A lost practice game is **retried up to 3 times with Reflexion-style reflections** (ExpeL); a rule written from a game nobody won is a hidden, unconfirmed note until a later win confirms it. Rule text must be short and general: no numbered objects, no specific object kinds or rooms, no steps of another kind of task.

### What the agent sees
At game start code picks up to 8 visible rules by goal similarity and reliability (task-keyed retrieval; no extra LLM call). The **same set** goes to the planner (field `rules` of its prompt, before it writes subgoals) and to the actor (a block "Rules learned from earlier practice (follow them)" in every step prompt); each episode json lists them under `rules_shown`. The recorded runs do **not** store the model's free-text thoughts: the checkpoints keep the plan (subgoal descriptions), the actions, the observations and the validity of each command only.

## Folder layout

```
examples/
  README.md                this file
  replay.py                stdlib-only step-by-step replay for live demos
  episodes/
    c/  d/  e/  paired/    <name>.json (trimmed record) + <name>.md (readable transcript)
  library/
    builder/               one practice game each: retries, Builder report, rule changes (md + json)
    snapshots/             library snapshots and evolution (md + json)
```

Replay on a slide machine: `python replay.py episodes/paired/pair-heat-mug-cabinet.json --delay 1.5` (add `--only C` or `--only E`, `--step` to advance with Enter, `--no-obs`; `python replay.py --list` lists everything). It also replays builder examples and snapshots.

Episode json fields: `goal`, `task_type`, `condition`, `success`, `steps`, `invalid_actions`, `model_calls`, `input_tokens`, `output_tokens`, `plan` (planner subgoals, E), `rules_shown` (E: id, type, kind, alpha, beta, text, example, rendered text), `memory_shown` (D), `initial_observation`, `trace` (step, action, observation, valid), `shows` / `why_interesting` / `notes` (captions), `source` (run, stream, position: where it came from).

# Index

### 1. C (no memory) episodes (8)

Condition C: hierarchy agent (planner + actor) with no memory. All from the 70 development games, run `old-pilot-9b-v1`, the reference run that every paired comparison uses.

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [c-quick-win-pick-place](episodes/c/c-quick-win-pick-place.md) ([json](episodes/c/c-quick-win-pick-place.json)) | C | WON in 5 steps | C: quick win, a simple pick and place in 5 steps | Baseline for "what the agent can already do alone": 5 steps, no invalid action. Pick-and-place is where C is strongest (17 of 22 dev games won). |
| [c-typical-win-clean](episodes/c/c-typical-win-clean.md) ([json](episodes/c/c-typical-win-clean.json)) | C | WON in 14 steps | C: typical clean-then-place win, with a few invalid commands on the way | Shows C is not hopeless on multi-step tasks and what its usual noise looks like: a missing `go to` before `move`. |
| [c-typical-win-cool](episodes/c/c-typical-win-cool.md) ([json](episodes/c/c-typical-win-cool.json)) | C | WON in 8 steps | C: typical cool-then-place win (8 steps) | Cooling is won about 58% of the time by C (7 of 12 dev games); this is the clean case. |
| [c-typical-win-look](episodes/c/c-typical-win-look.md) ([json](episodes/c/c-typical-win-look.json)) | C | WON in 14 steps | C: a look-at-object win that looks accidental | The agent wins without understanding the goal: the ALFWorld goal is "holding the object with the lamp on", so the `examine` spam was wasted effort. Good example of a win that does not show competence. |
| [c-typical-win-two-objects](episodes/c/c-typical-win-two-objects.md) ([json](episodes/c/c-typical-win-two-objects.json)) | C | WON in 19 steps | C: typical two-object win (19 steps) | Two-object tasks need the search done twice; C wins about half of them and needs many steps. |
| [c-loop-failure-pick-place](episodes/c/c-loop-failure-pick-place.md) ([json](episodes/c/c-loop-failure-pick-place.json)) | C | LOST in 30 steps | C: long failure by looping between receptacles | The typical failure of C on pick-and-place: revisiting receptacles it has already seen, with no record of what was checked (17 repeated commands). |
| [c-search-failure-pick-place](episodes/c/c-search-failure-pick-place.md) ([json](episodes/c/c-search-failure-pick-place.json)) | C | LOST in 30 steps | C: long failure while searching a big room | Search failure: the object was on a surface that was never visited because the agent opened every container first. This is exactly what the library rule "search surfaces first, then containers" targets. |
| [c-heat-failure-typical](episodes/c/c-heat-failure-typical.md) ([json](episodes/c/c-heat-failure-typical.json)) | C | LOST in 30 steps | C: the typical heat task, never solved by C | C won 0 of 9 heat tasks. The winning command is `heat <obj> with microwave 1`; C does not discover it. Compare with the paired heat examples, where the library supplies the missing step. |

### 2. D (trajectory memory) episodes (5)

Condition D: the actor additionally sees the 3 most similar *successful practice trajectories* (goal + valid actions). These are practice games (D has not been evaluated on the development games yet), run `old-study-9b-v1` (Qwen3.5-9B).

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [d-win-reuses-neighbour](episodes/d/d-win-reuses-neighbour.md) ([json](episodes/d/d-win-reuses-neighbour.json)) | D | WON in 6 steps | D: a win helped by a near-identical stored solution | Best case for trajectory memory: the stored game is the same kind of task with the same object. D copies a whole earlier action list as a demonstration in the actor prompt. |
| [d-win-one-near-example](episodes/d/d-win-one-near-example.md) ([json](episodes/d/d-win-one-near-example.json)) | D | WON in 13 steps | D: a win with a partly relevant example | Trajectory memory transfers the procedure, not the layout: the earlier solution came from another room. |
| [d-win-two-objects](episodes/d/d-win-two-objects.md) ([json](episodes/d/d-win-two-objects.json)) | D | WON in 17 steps | D: a two-object win that is messy but succeeds | Shows D noise: raw trajectories are long and are re-used for each subgoal, and the actor sometimes emits non-commands. |
| [d-lost-despite-example-heat](episodes/d/d-lost-despite-example-heat.md) ([json](episodes/d/d-lost-despite-example-heat.json)) | D | LOST in 30 steps | D: a loss despite stored heat examples | Memory only contains wins and only the exact commands; if the agent cannot find the object nothing in memory helps. |
| [d-lost-two-objects](episodes/d/d-lost-two-objects.md) ([json](episodes/d/d-lost-two-objects.json)) | D | LOST in 30 steps | D: a loss on a two-object task | Two-object tasks stay the hardest kind for every condition. |

### 3. E (rule-manual library) episodes (6)

Condition E on development games with a frozen library: the rules shown (same set to planner and actor), the plan and the play. Run `check-e`.

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [e-win-clean-fast](episodes/e/e-win-clean-fast.md) ([json](episodes/e/e-win-clean-fast.json)) | E | WON in 6 steps | E: clean task won in 6 steps (C needed 18) | The rule pins the recipe: "clean it with the sinkbasin, then move it to the target", which is the order C often gets wrong. Paired comparison: same game, C also won but with 18 steps. |
| [e-win-cool-fast](episodes/e/e-win-cool-fast.md) ([json](episodes/e/e-win-cool-fast.json)) | E | WON in 7 steps | E: cool task won in 7 steps (C needed 26) | Shows the plan the Success Process gives the planner: search -> fridge -> target, no wasted stops. |
| [e-win-look-3-steps](episodes/e/e-win-look-3-steps.md) ([json](episodes/e/e-win-look-3-steps.json)) | E | WON in 3 steps | E: look-at-object solved in 3 steps (C needed 14) | Shortest E episode. The look kind has a 4-of-4 record in this check. Compare with the C look example that spammed `examine`. |
| [e-win-two-objects](episodes/e/e-win-two-objects.md) ([json](episodes/e/e-win-two-objects.json)) | E | WON in 6 steps | E: two-object task in 6 steps (C needed 13) | The recipe tells the planner to take each object and move it before the second; the plan lists the second CD as its own subgoal. |
| [e-win-pick-place-with-antipattern](episodes/e/e-win-pick-place-with-antipattern.md) ([json](episodes/e/e-win-pick-place-with-antipattern.json)) | E | WON in 4 steps | E: simple task won in 4 steps with an Anti-Pattern rule on screen | Shows what an Anti-Pattern looks like in the prompt, and honestly shows its cost: it occupies prompt space in all 22 simple dev games although only a few agents loop on `examine`. |
| [e-win-but-slower-than-c](episodes/e/e-win-but-slower-than-c.md) ([json](episodes/e/e-win-but-slower-than-c.json)) | E | WON in 28 steps | E: a win that is slower than C (28 steps vs 10) | Honest counter-example: the rules cannot fix a search problem when the object is hidden; E can be slower. Win rate hides step count. |

### 4. Paired comparisons: same game, C vs E (11)

Eight games where C lost and E won, three honest ones where E lost and C won. Both transcripts are in one file; E libraries come from `check-e`, `check-d` or `check-avoid70` (noted per example).

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [pair-heat-mug-cabinet](episodes/paired/pair-heat-mug-cabinet.md) ([json](episodes/paired/pair-heat-mug-cabinet.json)) | C vs E | C lost, E won (C lost in 30, E won in 8) | Heat a mug: C stuck at the stoveburner, E uses the microwave | The clearest C-lost / E-won pattern: C never learns the `heat ... with microwave` command; E wins 8-step heat games repeatedly. |
| [pair-clean-cloth-cabinet](episodes/paired/pair-clean-cloth-cabinet.md) ([json](episodes/paired/pair-clean-cloth-cabinet.json)) | C vs E | C lost, E won (C lost in 30, E won in 7) | Clean a cloth: C grabs a towel and never recovers, E finds the cloth | A win that depends partly on a lucky rule: the Corrected Error mentions the bathtubbasin, which happens to be right for this room. Good example for discussing room-specific rules. |
| [pair-two-tissuebox-toilet](episodes/paired/pair-two-tissuebox-toilet.md) ([json](episodes/paired/pair-two-tissuebox-toilet.json)) | C vs E | C lost, E won (C lost in 30, E won in 8) | Two tissueboxes: C opens drawers for 30 steps, E checks the countertop first | Shows the most common useful rule of the manual: surfaces before containers. |
| [pair-cool-lettuce-countertop](episodes/paired/pair-cool-lettuce-countertop.md) ([json](episodes/paired/pair-cool-lettuce-countertop.json)) | C vs E | C lost, E won (C lost in 30, E won in 8) | Cool a lettuce: C searches cabinets, E searches surfaces | Same game, same object; only the search order differs. |
| [pair-look-cd-desklamp](episodes/paired/pair-look-cd-desklamp.md) ([json](episodes/paired/pair-look-cd-desklamp.json)) | C vs E | C lost, E won (C lost in 30, E won in 17) | Look at a CD under the desklamp: C loops, E wins after a slow start | Shows E is not clean: it also stalls, but the rule "find the light source first, then move the object under it" breaks the loop. |
| [pair-cool-mug-coffeemachine](episodes/paired/pair-cool-mug-coffeemachine.md) ([json](episodes/paired/pair-cool-mug-coffeemachine.json)) | C vs E | C lost, E won (C lost in 30, E won in 6) | Cool a mug: E finishes in 6 steps, C searches cabinets for 30 | Fastest cool win; caveat to mention in the talk: for some "in coffeemachine/stoveburner" goals ALFWorld declares success right after cooling. |
| [pair-heat-tomato-diningtable](episodes/paired/pair-heat-tomato-diningtable.md) ([json](episodes/paired/pair-heat-tomato-diningtable.json)) | C vs E | C lost, E won (C lost in 30, E won in 23) | Heat a tomato: E wins after a long microwave open/close loop | A win that took 23 steps: the manual gave the right appliance and the agent eventually used the right command. Shows E is still sloppy even when it wins. |
| [pair-pick-place-watch-sidetable](episodes/paired/pair-pick-place-watch-sidetable.md) ([json](episodes/paired/pair-pick-place-watch-sidetable.json)) | C vs E | C lost, E won (C lost in 30, E won in 8) | Pick and place a watch: C searches 30 steps, E finds it on the coffeetable | A different library (check-d) with a "search surfaces first, then containers" recipe produces the same behaviour change. |
| [pair-LOST-pick-place-mug-dresser](episodes/paired/pair-LOST-pick-place-mug-dresser.md) ([json](episodes/paired/pair-LOST-pick-place-mug-dresser.json)) | C vs E | C won, E lost (C won in 11, E lost in 30) | HONEST LOSS: C won in 11 steps, E lost with an Anti-Pattern in the prompt | E is not strictly better than C. The recipe "search the area first, open any closed containers" is consistent with what E did, but the extra rules did not prevent a search loop. A fair example of paired losses (E lost where C won 4 of 70 games in this library). |
| [pair-LOST-clean-ladle-diningtable](episodes/paired/pair-LOST-clean-ladle-diningtable.md) ([json](episodes/paired/pair-LOST-clean-ladle-diningtable.json)) | C vs E | C won, E lost (C won in 8, E lost in 30) | HONEST LOSS: C won in 8 steps, E searched everything but the dining table | Shows a failure of the actor to follow the planner's first subgoal, not a bad rule: the rules shown (clean recipe, open-before-place, scan bathtubbasin) are layout-specific noise here. |
| [pair-LOST-two-creditcard-safe](episodes/paired/pair-LOST-two-creditcard-safe.md) ([json](episodes/paired/pair-LOST-two-creditcard-safe.json)) | C vs E | C won, E lost (C won in 25, E lost in 30) | HONEST LOSS: both agents find the cards, E mis-sequences the two-object task | Shows a failure mode in which the model emits text instead of a legal command; two-object tasks are the weakest kind for E (7 of 12). |

### 5. Practice-time library management (Builder reports, retries, rejections, Anti-Patterns) (22)

Each file is one practice game: first attempt, ExpeL retries with reflections, the Builder report (operations and log lines with plain-language glosses) and the resulting manual changes.

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [bx-01-first-win-writes-recipe](library/builder/bx-01-first-win-writes-recipe.md) ([json](library/builder/bx-01-first-win-writes-recipe.json)) | E | game won; write_rule | Builder after the first win: write the Success Process (recipe) | The origin of every recipe in the manual. Its text is checked by code (<= 45 words, no numbered objects, no steps of other task kinds). |
| [bx-02-retry-win-writes-recipe](library/builder/bx-02-retry-win-writes-recipe.md) ([json](library/builder/bx-02-retry-win-writes-recipe.json)) | E | game lost, 1 retry (won); write_rule | ExpeL retry: loss -> reflection -> retry win -> recipe | The complete retry sequence in one example. Note the cost: the retry used 12 model calls and 23k tokens, charged to the condition's compute. |
| [bx-03-retry-corrected-error-and-rejected-recipe](library/builder/bx-03-retry-corrected-error-and-rejected-recipe.md) ([json](library/builder/bx-03-retry-corrected-error-and-rejected-recipe.json)) | E | game lost, 1 retry (won); write_rule | Retry win writes a Corrected Error; a recipe naming a numbered object is rejected | Shows the two kinds of rule writes in one game and the deterministic reject-and-log guard. A Corrected Error is the "when X, do Y instead of X" contrastive rule from the ExpeL idea. |
| [bx-04-three-retries-win-on-third](library/builder/bx-04-three-retries-win-on-third.md) ([json](library/builder/bx-04-three-retries-win-on-third.json)) | E | game lost, 3 retries (won); write_rule | Three retries, win on the third: the reflection repeats itself | Why the retry loop was kept as is: 4 of the 9 retry wins in the check came on attempts 2-3 even though the reflections repeat (the replay itself varies). Also shows the cost: 89 model calls and 270k tokens for this one game. |
| [bx-05-two-objects-merge-refine-and-recipe](library/builder/bx-05-two-objects-merge-refine-and-recipe.md) ([json](library/builder/bx-05-two-objects-merge-refine-and-recipe.json)) | E | game lost, 1 retry (won); merge_rule, refine, write_rule | Merge a near-duplicate and refine another rule in the same game | Shows merge + refine together, which are the MACLA-style rule management operations (E only; E-minus cannot do either). |
| [bx-06-lost-game-writes-hidden-note](library/builder/bx-06-lost-game-writes-hidden-note.md) ([json](library/builder/bx-06-lost-game-writes-hidden-note.json)) | E | game lost, 3 retries (all lost); write_rule | A lost game: any rule written is a hidden, unconfirmed note | The protection against learning wrong lessons from failure: guesses stay hidden until a later win confirms them. |
| [bx-07-hidden-note-confirmed-by-retry-win](library/builder/bx-07-hidden-note-confirmed-by-retry-win.md) ([json](library/builder/bx-07-hidden-note-confirmed-by-retry-win.json)) | E | game lost, 3 retries (won); update_rule | The hidden note becomes visible: confirmed by a later retry win | Closes the loop started in bx-06. Compare visible=False before and visible=True after. |
| [bx-08-lost-game-cannot-rewrite-visible-rule](library/builder/bx-08-lost-game-cannot-rewrite-visible-rule.md) ([json](library/builder/bx-08-lost-game-cannot-rewrite-visible-rule.json)) | E | game lost, 3 retries (all lost); update_rule | A lost game cannot rewrite a rule the agent sees | Prevents a single bad game from corrupting a good recipe. |
| [bx-09-reject-numbered-object](library/builder/bx-09-reject-numbered-object.md) ([json](library/builder/bx-09-reject-numbered-object.json)) | E | game lost, 2 retries (won); write_rule | Rejected: a recipe that names a numbered object | Numbered objects are instance specific ("fridge 1" exists in one room only), so they are rejected deterministically. |
| [bx-10-reject-specific-object-names](library/builder/bx-10-reject-specific-object-names.md) ([json](library/builder/bx-10-reject-specific-object-names.json)) | E | game lost, 3 retries (all lost); no rule change | Rejected: rule names specific objects after one rewrite attempt | The specificity check from DECISIONS 2026-11-18: rules like "When searching for a tomato to cool..." do not transfer, so they are rewritten or rejected. |
| [bx-11-reject-room-name](library/builder/bx-11-reject-room-name.md) ([json](library/builder/bx-11-reject-room-name.json)) | E | game won; no rule change | Rejected: a recipe that tells the agent to search "the room" | A game in ALFWorld is one room, so "search all rooms" is wrong advice; the check removes such wording. |
| [bx-12-reject-note-that-lists-steps](library/builder/bx-12-reject-note-that-lists-steps.md) ([json](library/builder/bx-12-reject-note-that-lists-steps.json)) | E | game lost, 3 retries (all lost); no rule change | Rejected: an Unresolved Error that lists steps | Keeps the manual from filling with duplicate step lists. |
| [bx-13-reject-too-long](library/builder/bx-13-reject-too-long.md) ([json](library/builder/bx-13-reject-too-long.json)) | E | game lost, 1 retry (won); write_rule | Rejected: a Success Process that is too long | Rules are kept short so up to 8 of them fit in the planner and actor prompts. |
| [bx-14-anti-pattern-written](library/builder/bx-14-anti-pattern-written.md) ([json](library/builder/bx-14-anti-pattern-written.json)) | E | game lost, 3 retries (all lost); refine, write_rule | Anti-Pattern written: "do not use the command done" | The Anti-Pattern pipeline: mined by code from pooled failures (never from one game), worded by the model, checked against wins. This one is legitimate (the agent really emits `done`) but low value. |
| [bx-15-anti-pattern-wording-rejected](library/builder/bx-15-anti-pattern-wording-rejected.md) ([json](library/builder/bx-15-anti-pattern-wording-rejected.json)) | E | game lost, 3 retries (all lost); write_rule | Anti-Pattern: model wording rejected twice, then accepted | The code check that the model may only word the measured pattern. Also: a hidden Special Phenomenon is stored from the same lost game. |
| [bx-16-anti-pattern-examine-loop](library/builder/bx-16-anti-pattern-examine-loop.md) ([json](library/builder/bx-16-anti-pattern-examine-loop.json)) | E | game lost, 3 retries (all lost); refine, update_rule, write_rule | Anti-Pattern written from 2 of 3 lost tasks (examine loop) | Same kind of Anti-Pattern that the frozen check later shows on every simple game. |
| [bx-17-refine-contrastive-rewrite](library/builder/bx-17-refine-contrastive-rewrite.md) ([json](library/builder/bx-17-refine-contrastive-rewrite.json)) | E | game lost, 1 retry (won); refine, update_rule | MACLA contrastive refinement of a rule | The mechanism that changes rule text over time; also why recipe text can oscillate (see library/snapshots/evolution-study-E.md). |
| [bx-18-upvote-after-win](library/builder/bx-18-upvote-after-win.md) ([json](library/builder/bx-18-upvote-after-win.json)) | E | game won; update_rule, upvote_rule | Builder vote: upvote after a win | Shows the two reliability channels: the automatic Beta update (credit to all rules shown) and the Builder's explicit votes. |
| [bx-19-merge-near-duplicate](library/builder/bx-19-merge-near-duplicate.md) ([json](library/builder/bx-19-merge-near-duplicate.json)) | E | game lost, 3 retries (all lost); merge_rule, refine, update_rule | A new rule merged into an existing one | Keeps the manual small. Merging never widens a rule's scope (a rule for one kind of task is never merged into another kind). |
| [bx-20-e-minus-append-only-refusals](library/builder/bx-20-e-minus-append-only-refusals.md) ([json](library/builder/bx-20-e-minus-append-only-refusals.json)) | E-minus | game won; no rule change | E-minus: append-only, refused edits | The ablation shows what rule management buys: E-minus keeps adding rules (26 after 40 games, 8 of them hidden Unresolved Errors) while E rewrites and merges (16 after 35). |
| [bx-21-retirement-test-demo](library/builder/bx-21-retirement-test-demo.md) ([json](library/builder/bx-21-retirement-test-demo.json)) | E | demo (computed on saved rules) | Retirement test on real saved rules (no recorded retirement yet) | Honest gap: the retire mechanism exists and is unit-tested but has never fired in a live run (rules stay below the 4-game shown threshold or above the base rate). |
| [bx-22-specificity-and-cross-kind-checks](library/builder/bx-22-specificity-and-cross-kind-checks.md) ([json](library/builder/bx-22-specificity-and-cross-kind-checks.json)) | E | demo (computed on saved rules) | Text checks: no specific objects, no steps of another task kind | The rewrite step leaves no record in checkpoints, so this reconstructs it from the check code and the model cache; includes the study incident where a cooling recipe contained "clean it with sinkbasin". |

### 6. Library snapshots and evolution (8)

Rules with type, kind of task, Beta(alpha, beta), visibility and text.

| Example | Cond | Outcome | What it shows | Why it is interesting |
|---|---|---|---|---|
| [snap-early-study-E-after-3-games](library/snapshots/snap-early-study-E-after-3-games.md) ([json](library/snapshots/snap-early-study-E-after-3-games.json)) | E | 7 rules | Early library: study E after 4 practice games | The starting point of a library. |
| [snap-early-study-E-after-9-games](library/snapshots/snap-early-study-E-after-9-games.md) ([json](library/snapshots/snap-early-study-E-after-9-games.json)) | E | 11 rules | Small library: study E after 10 practice games | The size at which retrieval is trivial (fewer rules than the 8 shown per game). |
| [snap-mature-study-E-after-35-games](library/snapshots/snap-mature-study-E-after-35-games.md) ([json](library/snapshots/snap-mature-study-E-after-35-games.json)) | E | 16 rules | Study E library after 35 practice games (current code, still growing) | The live library of the running study with the current code. |
| [snap-mature-practice-b-after-48-games](library/snapshots/snap-mature-practice-b-after-48-games.md) ([json](library/snapshots/snap-mature-practice-b-after-48-games.json)) | E | 22 rules | Mature library: practice-b after 48 practice games (stores plans, 1 Anti-Pattern) | Mature library with the full mix of rule types. |
| [snap-mature-practice-d-after-48-games](library/snapshots/snap-mature-practice-d-after-48-games.md) ([json](library/snapshots/snap-mature-practice-d-after-48-games.json)) | E | 28 rules | Mature library: practice-d after 48 practice games (current code, no object names) | Shows quality variation within one library: good recipes next to odd rules left to Beta to retire. |
| [snap-best-check-library-26-rules](library/snapshots/snap-best-check-library-26-rules.md) ([json](library/snapshots/snap-best-check-library-26-rules.json)) | E | 26 rules | Best library so far: the frozen avoid-rules practice library that won 54/70 dev games | The library behind the biggest measured gain over C (39/70). |
| [evolution-study-E](library/snapshots/evolution-study-E.md) ([json](library/snapshots/evolution-study-E.json)) | E | 35 games | Library evolution game by game (study E, 35 games) | Shows text oscillation of rule_7 (drawers/cabinets/target surface first), a hidden note being confirmed (rule_3) and Beta counts moving. |
| [snap-e-minus-after-40-games](library/snapshots/snap-e-minus-after-40-games.md) ([json](library/snapshots/snap-e-minus-after-40-games.json)) | E-minus | 26 rules | Append-only library (E-minus) after 40 games | The append-only ablation keeps growing and keeps hidden notes forever. |


## Provenance and caveats (read before presenting)

- **C reference**: all C games and the C side of every pair come from run `old-pilot-9b-v1` (70 development games, 39 won). E libraries: `check-e` (practice-e library, 48/70), `check-d` (49/70) and `check-avoid70` (54/70, the best; still has a tomato-specific rule from before the specificity check). Frozen checks: the same 70 games, run-to-run noise is about +-4 games.
- **C and E use the same game and the same start state**, but are separate runs: E's wins also differ in randomness. Paired win counts in these libraries are 13-18 E wins vs 3-5 E losses out of 70.
- **D** examples are practice games (no D evaluation exists yet) from `old-study-9b-v1`. The exact per-subgoal retrieval is not stored; `memory_shown` ranks the stored trajectories with the same embedder by goal only, as a typical retrieval.
- **Study E / E-minus** examples (`study`) come from the live long run: they are frozen at the first 35 / 40 practice games, so numbers in these files will not match a later look at the run. The run is on the current code (specificity and cross-kind checks).
- **Not recorded in any run**: model thoughts, the planner/actor prompts, the exact rewrite before a Builder rewrite (only rejections are logged), and **retirements** (no rule has been retired yet; `bx-21` shows the test on real rules). `bx-22` and `bx-21` are computed with the repo's own check functions on real or quoted texts and say so.
- **Quirks seen while extracting** (worth knowing before someone asks): (1) a log line in the first lost games says "rule_1 is a hidden Builder note" while the new rule has id rule_3 (`bx-06`); (2) for goals such as "put a cool mug in coffeemachine" the simulator reports a win right after `cool` without the final `move` (`pair-cool-mug-coffeemachine`); (3) look-at-object tasks are won as soon as the agent holds the object with the lamp on, `examine` is unnecessary; (4) Anti-Pattern `rule_18` of `check-e` is shown in every pick-and-place game, including ones where it is irrelevant; (5) recipe text of a rule changes with each won game (see `library/snapshots/evolution-study-E.md`), so wording drifts.
