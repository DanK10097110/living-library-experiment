# Rule library spec (redesign of 2026-11-20)

This replaces the rule-management part of `living_library/manual.py` and removes the code-skill library
everywhere. The reasons are in `ARCHITECTURE.md` section 4. Every threshold below has its reasoning next to it.
Change a number only together with its reasoning and the simulator check (section 7).

## 1. Principles

1. **Rules start decent.** All quality control on text happens when a rule is written: text checks, plus a
   check that every command the rule instructs actually worked in the won game it came from.
2. **The text of a rule the agent sees never changes because of one game.** No Builder rewrites of visible
   rules, no "young rule" exceptions, no edits on a single win.
3. **Changes need evidence about the rule itself.** A rule counts only in games where the planner says it
   used it, and harm is read from the trace (rejected prescribed commands, loops, empty search places), so a
   rule is not blamed for games it played no part in (section 4).
4. **One way to change a text** (evidence-triggered refinement) and **two ways to remove a rule** (it is shown
   but not followed, or it stays harmful after its revisions are used up). Plus capacity pruning, which should
   never fire in 300 games.
5. **E and E-minus share everything except management.** Both write, assess and rank the same way. E-minus never
   changes or removes anything.

## 2. Rule record

```
id, type, rule, example, validation, task_type ('<kind>' | 'all'), hidden (bool: Unresolved Error notes),
sources [ {task, task_type} ] (<= 15), created (practice position), revisions (int, text changes since written),
ev    = {shown, followed, sum, pos, neg, won, lost}   # evidence about the CURRENT text (reset on a text change)
total = {shown, followed, sum, pos, neg, won, lost}   # lifetime, reports only
contexts = [ {task, task_type, won, steps (last 12 valid actions), plan, score, reason} ]
           # last 6 with score > 0 and last 6 with score < 0, current text only; the refiner's evidence
last_used (practice position)
pattern (Anti-Patterns only, as now)
```

Removed: alpha/beta, base, base_types, credits, unused, importance and votes, verified/confirmations/
guess_credits (hidden guesses), refined_at, rewrites, commands, violations, lift and expected wins, MACLA
expected utility, risk and entropy terms, consolidation (folding), dead/young recipe rules, retrieval modes.

`m(rule) = ev.sum / (ev.followed + PRIOR)` with **PRIOR = 2**: the shrunk mean usefulness of the current text.
A new rule has m = 0. Two pseudo-games at 0 mean one or two harsh scores cannot make a rule look bad.

## 3. Writing (Builder, after every practice game)

Cases, as now: direct success, indirect success, failure, corrected failure (lost, then won on a retry).

| Case | May write | Max writes |
| --- | --- | --- |
| direct success | Success Process, Special Phenomenon | 2 |
| indirect success | Success Process, Special Phenomenon, Corrected Error | 2 |
| corrected failure | Corrected Error, Success Process, Special Phenomenon | 2 |
| failure | Unresolved Error (hidden note) only | 1 |

A lost game writes no visible rule. The old "hidden guess, promoted after 2 followed wins" path is removed: won
games rediscover anything true, and promotion was a fragile threshold of its own.

**Write gate**, in order. Any failure gets one model repair told the problem, then rejection:
1. The existing text checks (`checked`): instance numbers stripped, length, steps outside a recipe,
   object/room names, another kind's actions.
2. **Trace check** (new; visible types only): every instructed command (`instructed_commands`, e.g.
   `take lamp`) must have been accepted at least once in the won trace it was written from (the first attempt
   if it was won, else the winning retry). "take the lamp" can no longer enter the manual.
3. One Success Process per kind: if one exists, the write is refused.
4. Near-duplicate (similarity >= 0.85, same type, same kind or a general rule) → merged: the existing rule
   gains the source; no text change.

**Builder operations** (`write_rule`, `note`, `update_note`):
- `write_rule {type, rule, example, scope}` as above.
- `note {id, validation}`: append a validation note (the last 3 are kept) to any rule it sees. Notes never
  change the text, but the refiner reads them.
- `update_note {id, rule, type?}`: rewrite a **hidden** Unresolved Error note. On a corrected failure,
  `type: "Corrected Error"` turns the note into a visible rule only if (a) the winning retry's trace shows no
  harm from the new text (`harms`; this replaced the per-rule judge's check), and (b) the new text
  passes the write gate (trace check against the winning retry). The converted rule starts with empty
  evidence.
- E-minus (append-only): `write_rule` only.
- Removed: `update_rule` of visible rules, `upvote_rule`, `downvote_rule`.

## 4. Evidence (after every practice game, E and E-minus; no model call)

Amended 2026-11-20 (evening). The per-rule LLM judge of the first version was measured on archived games and
removed: on 90 cases gold-labelled by Claude it agreed on "followed" in 59-63% of cases, flagged 0-2 of 18 harmful
uses, gave +2 to nearly every followed rule (41 times in lost games), and a yes/no "used" variant inferred use from
the agent's progress (outcome leak). Data and tool: `results/judge-eval/`, `tools/judge_eval.py`; DECISIONS.

**Used.** After each plan, one short call (role `citer`, `Agent._cite`) gets the plan's subgoal descriptions and
the shown rules numbered (no trace, no outcome) and lists the numbers the plan follows (`used_rules`; replans add
to `rules_used`). A shown rule is used iff it was cited. Bad citations (out of range, not a number) are ignored; a
failed call records nothing. Only practice games and trial games cite (evaluation and retries do not;
`LL_CITE_FROZEN=1` turns it on for measurement). Asking the planner itself for the list broke its subgoals (a
missing postconditions field in 5 of 30 games vs 1 in 280 before).

**Harm** (`manual.harms`, from the trace of the first attempt), for a used rule:
- commands of a verb the rule prescribes (on the appliance or place it names, if any) rejected at least
  REJECTED_REPEATS = 2 times (one rejection is ordinary noise). This catches "heat X with the microwave" after
  X was put inside it;
- one command it prescribes repeated STUCK_REPEATS = 3 times (stuck in what it says);
- the agent went to / opened the places the rule says to search first, and the object was taken elsewhere or
  never found (`search_places`; "table" and "surfaces" stand for their place kinds).
On the 55 gold-used archived cases: 15 of 18 harmful uses flagged, 7 of 37 others (`judge_eval.py harm`).

**Score** of a used rule in a game: −1 on harm; else +1 if the game was won or the object was taken from a place
the rule says to search first; else 0. `ev.followed += 1, ev.sum += score, pos/neg, won/lost`, context stored
(won or lost). Not used → `ev.shown += 1` only.

- Contexts: the last K_CONTEXTS used games with score ≥ 0 and the last K_CONTEXTS with score < 0, each with its
  task (`task_ref`, for trial replays), the plan, the last 16 steps (rejected ones marked) and the harm reason.
- Anti-Patterns are assessed the same way (used = cited).
- Hidden notes are never shown, so never assessed.
- Cost: one short call per plan in practice (about +6% calls).

**Why not ablation.** Withholding a rule at random gives a clean counterfactual, but not enough of it. A rule is
eligible in about 50 of 300 practice games. Withheld in 20% of them, that is 10 withheld vs 40 shown. The standard
error of the win-rate difference is about 0.18, so only effects above about 35 pp could be detected, and
withholding also costs practice wins.

## 5. Management (E only)

Decisions use the evidence of the current text (`ev`).

**Bad.** `ev.followed >= MIN_EVIDENCE (6)` and `m <= BAD_MEAN (-0.4)` (−0.5 until the simulator was re-run with
the measured evidence noise; −0.5 caught harmful rules within 15 followed games in only 86% of runs).
- With PRIOR 2, that needs a net score of −4 over 6 used games (e.g. four −1s and two 0s), −4 over 7, −4 over 8.
  A harmful rule (harm flagged in about 77% of its uses) is bad after 6-10 used games. A rule that does no harm
  but is used in lost games (false harm signals 19%, no +1s) rarely gets there (simulated, section 7).
- 6 followed games is about 36 practice games for a recipe (one kind gets about 1/6 of the games).

**On bad:** if `revisions < MAX_REVISIONS (2)` and the type is not Anti-Pattern → **refine** (at most one per
game, the rule with the lowest m). Otherwise → **retire**.
- The refiner gets the rule, its harmful games (with what went wrong) and its other used games, won and lost
  (`harmful_games`, `used_games`: task, plan, last steps with rejected ones marked, reason), and its validation
  notes, and returns one rewritten rule (not longer than the original).
- The new text must pass the write gate's text checks, and its instructed commands must have been accepted in a
  stored context.
- **Trial games** (`manual.trial`): the candidate is played, frozen, on up to TRIAL_GAMES = 3 stored tasks of the
  rule (the ones it harmed first, then other used ones), shown for certain (`Agent.pinned`). It passes if the
  planner used it in at least one and no trial game shows harm. Cost: at most 3 games per refinement, charged to
  the practice game; refinements are rare. Only then does the text change.
- Any failure (model error, checks, trial) → the bad rule is **retired**, not kept for another try every game.
- New text → `revisions += 1`, `ev` and `contexts` reset. `total` is kept.
- MAX_REVISIONS 2 → at most 3 texts per rule in a run. That is the hard cap on drift. Refinement counts
  toward it (it did not before).

**Useless.** `ev.shown >= USELESS_MIN (16)` and `ev.followed < 0.2 * ev.shown` → retire. All types, recipes
included: a recipe followed in under 1 of 5 games is not working as a recipe, and the next won game of its
kind writes a new one. For an Anti-Pattern this means the agent did the avoided thing anyway.

**Neutral rules** (followed, m about 0) are kept. They rank low and only capacity pruning removes them.

**Anti-Patterns** also keep avoid.py's deterministic contradiction check: retired when a won attempt of the
kind contains the pattern.

**Capacity** (CAPACITY 200 rules, Failure Pools excluded): drop hidden notes oldest first, then visible rules
by lowest m, then least recently used. Expected never to fire at 300 games (the lab measured 0.2-0.3 rules per
game).

**Batches** (8 games run on the start-of-batch library):
- Refinement and bad-retirement happen inside a game (they need a model call). Their ops are applied in
  replay only if the rule is still bad on the live library (the batch-mates' evidence is already replayed),
  and only one text change per rule per batch (first in position order). Otherwise the op is dropped and
  logged.
- Useless retirement, near-duplicate merge (`batch_dedupe`) and capacity pruning are deterministic. They run
  once at the end of each batch on the live library, in the main process (`manual.batch_upkeep(rules,
  base_ids, similarity) -> ops`). The ops are appended to the batch's last game, so replay reproduces every
  checkpoint.
- With `practice_batch == 1`, `build` runs `batch_upkeep` itself after each game.

## 6. Retrieval (both conditions)

- Candidates: the kind's Success Process (always first), the kind's other visible rules and the general rules.
  Other kinds' rules join only for an unseen kind with task evidence >= 0.85 (unchanged).
- Relevance = w·evidence + (1−w)·text, w = h/(h+2), h = number of followed games with score > 0 (lifetime).
  Evidence = max similarity of the goal to the rule's source tasks and to the tasks of its contexts with score > 0.
- Rank = relevance + 0.1·m. A rule that is reliably +1 (m ≈ +0.8) gains about 0.08, a harmful one loses 0.04-0.08;
  relevance differences between kinds are larger, so usefulness reorders rules within a kind but does not pull
  in unrelated ones.
- One of the 8 slots is kept for the most relevant rarely shown rule (< 3 showings) when none made the cut, so
  new rules get evidence.
- The Builder sees up to 24 relevant rules (hidden notes included) plus the 2 newest.

## 7. Mechanism simulator (`tools/sim_mechanisms.py`, CPU only, plus a unit test)

Synthetic rules, followed with probability f, through the real `observe`/bad/useless/refine-decision code
with evidence as noisy as the real one, 300 practice games: the citation names a followed rule w.p. 0.8 and an
unfollowed one w.p. 0.1 (assumed, checked on real games: DECISIONS); harm is flagged in 15/18 of really harmful
uses and 7/37 of the others (measured); otherwise +1 for a won game. Acceptance (the test asserts these, for
a kind's share of games and for a rule shown in every game):
- helpful rule (no harm, wins 70%) revised or retired in ≤ 2% of runs;
- neutral rule (no harm, wins 50%) in ≤ 5%; neutral in a hard kind (wins 20%) in ≤ 10%;
- harmful rule (harmful in 90% of its uses, wins 30%) revised or retired within 15 followed games in ≥ 90%;
- rule followed with f = 0.1 retired as useless in ≥ 85% of runs; with f = 0.6 in ≤ 1%. (No USELESS_MIN meets
  90% and 1% together under citation noise; wrongly retiring a working rule is the worse error.)
Measured: 0.5%, 1.3%, 3.3%, 94%, 90%, 0.9% (one kind's share); 0.5%, 1.3%, 3.6%, 95%, 99%, 0.5% (every game).

## 8. Experimental design (outside manual.py)

- Code skills removed everywhere (library, interpreter, librarian, skill actions, E-plus, B, E-text,
  invocation metrics). Embeddings move to `embedding.py`. Memory = `{trajectories, rules}`.
- Conditions: C, D, E, E-minus (A kept in code, unused).
- Hypotheses: H1 E−D task success, H2 E−D amortized weighted tokens, H3 E−E-minus task success; E−C secondary;
  Holm over H1-H3. Success criterion: (E−D ≥ 10 pp, or 0 inside its CI with ≥ 30% lower amortized cost) and
  H3 > 0 at Holm p ≤ .05.
- Practice replicates: `practice_seeds` (study config: [0, 1]). Every memory condition practises once per seed
  (its own game order). Each replicate's library is evaluated on the same test games. The bootstrap resamples
  tasks and, within each condition, replicates, so library-to-library variance is in the intervals.
- Retries stay for E and E-minus (ExpeL experience gathering, charged in cost). D stores first-attempt wins
  only. This asymmetry is part of the method and is stated in the protocol.
- Early gate: a bug detector, not evidence. E (replicate 0, frozen at 75) vs C on 30 dev games; stop if
  E < C − 3.
- A fresh output directory; C and D are re-run, because removing the skill channel changes the planner and
  actor prompts.
