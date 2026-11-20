# Rule library spec (redesign of 2026-11-20)

This replaces the rule-management part of `living_library/manual.py` and removes the code-skill library
everywhere. The reasons are in `ARCHITECTURE.md` section 4. Every threshold below has its reasoning next to it.
Change a number only together with its reasoning and the simulator check (section 7).

## 1. Principles

1. **Rules start decent.** All quality control on text happens when a rule is written: text checks, plus a
   check that every command the rule instructs actually worked in the won game it came from.
2. **The text of a rule the agent sees never changes because of one game.** No Builder rewrites of visible
   rules, no "young rule" exceptions, no edits on a single win.
3. **Changes need evidence about the rule itself, not about the game outcome.** The evidence is a
   per-rule usefulness score from a separate, outcome-blind judge call. Each shown rule is judged on its own,
   one call per rule.
4. **One way to change a text** (evidence-triggered refinement) and **two ways to remove a rule** (it is shown
   but not followed, or it stays harmful after its revisions are used up). Plus capacity pruning, which should
   never fire in 300 games.
5. **E and E-minus share everything except management.** Both write, judge and rank the same way. E-minus never
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
  `type: "Corrected Error"` turns the note into a visible rule only if (a) the per-rule judge, run on the
  winning retry's trace, says the retry followed the new text with usefulness >= 1, and (b) the new text
  passes the write gate (trace check against the winning retry). The converted rule starts with empty
  evidence.
- E-minus (append-only): `write_rule` only.
- Removed: `update_rule` of visible rules, `upvote_rule`, `downvote_rule`.

## 4. Evidence (after every practice game, E and E-minus)

For each rule shown in the game, one judge call (role `judge`), outcome-blind:

```
payload: {instructions: JUDGE_GUIDE, goal, rule: {type, rule},
          steps: last 40 valid actions with <= 100-char observations (the last observation removed),
          response_schema: {followed: "yes|no", usefulness: "-2|-1|0|1|2", reason: "one short sentence"}}
JUDGE_GUIDE: Did the agent's actions follow this rule, and how useful was the rule in this game? You are not
told how the game ended; do not guess it. usefulness: 2 = following it clearly moved the agent toward the
goal (something it prescribes was needed and worked); 1 = it helped a little; 0 = not followed, or followed
but made no difference; -1 = following it wasted steps; -2 = following it misled the agent (a prescribed
command failed, or it pointed away from the goal). If not followed, usefulness is 0.
```

- followed = yes → `ev.followed += 1, ev.sum += score, pos/neg += 1, won/lost += 1` (outcome kept for
  reports only), context stored. followed = no → `ev.shown += 1` only (shown counts every judged showing).
- **Judge failure for a rule** (error, no JSON, bad value) → no evidence at all for that rule from that game,
  logged. Never "credit all" (that is what happened in 15% of games before).
- Anti-Patterns are judged the same way ("followed" = complied with it).
- Hidden notes are never shown, so never judged.
- Cost: at most 8 short calls per practice game (about +12% calls). Evaluation, gate and retries are not judged
  (except the one retry check in `update_note`).

**Why a judge score and not ablation.** Withholding a rule at random gives a clean counterfactual, but not
enough of it. A rule is eligible in about 50 of 300 practice games. Withheld in 20% of them, that is 10
withheld vs 40 shown. The standard error of the win-rate difference is about 0.18, so only effects above
about 35 pp could be detected, and withholding also costs practice wins. The per-rule judge gives a signal
in every game the rule is followed. Its noise is averaged by the thresholds below and stress-tested in the
simulator (section 7).

## 5. Management (E only)

Decisions use the evidence of the current text (`ev`).

**Bad.** `ev.followed >= MIN_EVIDENCE (6)` and `m <= BAD_MEAN (-0.5)`.
- With PRIOR 2, that needs a net score of about −4 over 6 followed games (e.g. four −1s and two 0s).
  A harmful rule (mean about −1) is bad after about 6 followed games. A neutral rule (mostly 0, judge noise ±1)
  almost never gets there (simulated, section 7).
- 6 followed games is about 36 practice games for a recipe (one kind gets about 1/6 of the games).

**On bad:** if `revisions < MAX_REVISIONS (2)` and the type is not Anti-Pattern → **refine** (at most one per
game, the rule with the lowest m). Otherwise → **retire**.
- The refiner gets the rule, its contexts with score > 0 (where it helped) and < 0 (where it misled, with the
  judge's reasons) and its validation notes, and returns one rewritten rule (not longer than the original).
- The new text must pass the write gate's text checks, and its instructed commands must appear in the
  actions of a stored context. Failure (model error, checks) → the bad rule is **retired**, not kept for
  another try every game.
- New text → `revisions += 1`, `ev` and `contexts` reset. `total` is kept.
- MAX_REVISIONS 2 → at most 3 texts per rule in a run. That is the hard cap on drift. Refinement counts
  toward it (it did not before).

**Useless.** `ev.shown >= USELESS_MIN (10)` and `ev.followed < 0.2 * ev.shown` → retire. All types, recipes
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
- Rank = relevance + 0.1·m. A rule judged clearly helpful (m ≈ +1.5) gains 0.15, a misleading one loses 0.05-0.1;
  relevance differences between kinds are larger, so usefulness reorders rules within a kind but does not pull
  in unrelated ones.
- One of the 8 slots is kept for the most relevant rarely shown rule (< 3 showings) when none made the cut, so
  new rules get evidence.
- The Builder sees up to 24 relevant rules (hidden notes included) plus the 2 newest.

## 7. Mechanism simulator (`tools/sim_mechanisms.py`, CPU only, plus a unit test)

Synthetic rules with known usefulness distributions, followed with probability f, through the real
`observe`/bad/useless/refine-decision code with a noisy judge (each score swapped for a random one with
probability 0.15, failures with probability 0.1), 300 practice games. Acceptance (the test asserts these):
- helpful rule (scores +1/+2) revised or retired in ≤ 2% of runs;
- neutral rule (mostly 0) revised or retired in ≤ 5% of runs;
- harmful rule (mostly −1/−2) revised or retired within 15 followed games in ≥ 90% of runs;
- rule followed with f = 0.1 retired as useless in ≥ 90% of runs; with f = 0.6 in ≤ 1%.

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
