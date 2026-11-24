# Study2 observations (unexpected patterns, not bugs)

Notes taken during hourly monitoring when something unexpected shows up (e.g. E-minus ahead of E).
Each entry: time, what was seen, likely reason from the current library and recent games that one condition
won and the other lost (same game positions). Kept for the final write-up: may be a noteworthy feature or
just something to be aware of. Run events stay in LOG.md; design decisions in DECISIONS.md.

## 2026-11-23 12:30 — E-minus ahead of E in replicate 0's recent games (study2 ~1100/3104)

Paired first-attempt wins, same games:
- Replicate 0, all 147 games: E 95, E-minus 93, D 85. **Last 50 (97-146): E 32, E-minus 37, D 35**; only E-minus won 9 games, only E won 4.
- Replicate 1, all 120 games: E 67, E-minus 62, D 66. Last 50 (70-119): E 30, E-minus 22, D 27, so it goes the other way there.

In all 9 games E lost and E-minus won (107, 114, 123, 124, 129, 132, 139, 140, 145), E ran out the 30-step limit. E-minus usually finished in 4-20 steps. Likely causes, from E replicate 0's library at game 146:
1. **Overfit "search X first" in Success Process recipes** (the known weakness noted 2026-11-21): rule_7 (pick and place, "search drawers first"), rule_32 (cool, "search cabinets first"), rule_19 (look, "search dresser first"), rule_11 (clean, "search multiple places first, take the object from the target"). In 124, 129 and 139, E followed the recipe and searched drawers or cabinets while the object was on the diningtable, the sofa or a stoveburner. E-minus went to the likely surface first.
2. **Loops the recipes do not prevent**: 107 (examine desk repeated about 10 times after using the lamp); 132 (repeated failing "take peppershaker 4"). Rule_18/19 ("use the desklamp ... examine the object from the dresser") does not say to hold the object.
3. **Wrong object**: 140 took "towel" for "handtowel" (a lesson already listed as commonly missed on 2026-11-21).

Reading: the gap looks like a recipe-content effect, not a mechanism bug. E's Success Process recipes encode a search order learned from a few games, and when the object is elsewhere that order costs steps. Replicate 1 shows the opposite trend, so part of this is noise. Possibly noteworthy for the write-up: **procedural recipes help when the search order generalises and hurt when it overfits to where objects happened to be.** No action taken (evidence/retirement should demote recipes that keep failing). Watch whether rule_7/rule_32 get retired or refined in replicate 0.

## 2026-11-23 14:55 — E replicate 0's library stopped growing; E-minus's keeps growing (study2 ~1550/3104)

Paired first-attempt wins: replicate 0, all 180 games: E 120, E-minus 119, D 102. Last 50 (130-179): E 35, E-minus 39 (only E-minus won 7, only E won 3). Replicate 1, all 153 games: E 86, E-minus 82, D 87. Last 50: E 28, E-minus 29, D 32. Overall E is still level with E-minus or slightly ahead, and well above D in replicate 0. Replicate 0's recent dip continues at a smaller size.

From the library trend tables (results/library/TRENDS.md):
- E replicate 0: 26 rules at game 100, then 23, 21 and 20 at games 125, 150 and 175. **0 rules added in games 101-175** while 7 were retired; merges continue.
- E-minus replicate 0: 108 rules (101 visible), adding about 14 per 25 games and never retiring (as designed: E-minus has no management).

Possible reasons, not verified yet (no deep read, to save tokens): E's write gates (grounding, scope guard, refused-rule feedback, one-text-change rule) plus visible-rule rewrite limits mean that once the main recipes exist, the Builder's new rules are mostly refused or merged. The library has converged to about 20 rules, and the overfit search-order recipes from the 12:30 note are among them. E-minus keeps adding many specific rules (object-place facts), which help on recurring rooms and objects. If that holds, it fits the recent E-minus edge: **a small, curated library loses specific "where things are" knowledge that a large uncurated one keeps**. Worth checking at the end: (a) whether E's Builder refusal rate rose after game 100 (a stuck gate would be a bug); (b) whether E-minus's advantage is concentrated in pick-and-place and search-heavy tasks. No action taken.

## 2026-11-24 — Final: why E-minus varies so much between replicates; library construction

Final first-attempt success (study2 complete, 3104 episodes; 20 ID-evaluation checkpoints of E-minus r1 that the 22:00 sleep left empty were deleted and replayed from the model cache):

| | C | D | E r0 | E r1 | E-minus r0 | E-minus r1 |
|---|---|---|---|---|---|---|
| OOD (134) | 70 | 82 | 98 | 90 | 96 | 93 |
| ID (70) | 40 | 46 | 50 | 49 | 52 | 44 |
| Practice (300) | - | 180 | 199 | 192 | 208 | 183 |

E and E-minus are tied on average (OOD 94 vs 94.5; ID 49.5 vs 48); both are clearly above D and C.

**Why the replicates vary.** The replicates disagree on 137-143 of 300 practice games (E vs E-minus in the same replicate: 67-97), so the agent is very noisy per game. Most of the gap between replicates comes from **one recipe per task type**. Each library has exactly 6 Success Process rules (one per task type), written early from a few games. Which version the Builder happened to write sets that task type's success rate:
- Heat, OOD: E-minus r0 8/10 vs r1 3/10. r1's heat recipe (rule_69) is "search the target container first ... move the object to it [the microwave], heat it, take it back", which adds wrong extra steps: evidence 5 positive vs 18 negative over 33 showings. E-minus has no management, so it can neither retire it nor rewrite it. r0's recipe (rule_27, "heat it with a microwave ... move the object there") is clean: 22 positive vs 8 negative.
- Look, OOD: E-minus r0 9/18 vs r1 17/18. r0's look recipe (rule_43) says "move the object to the shelf with the desklamp ... examine the shelf", which is wrong. r1's (rule_25) is clean.
- E shows the same pattern at a smaller size: E r1's look recipe (rule_54, "take the object from the desk") is overfit (look OOD 7/18 vs E r0 11/18), and its heat recipe rule_25 has 20 positive vs 18 negative but was never retired, because the evidence was mixed rather than bad.
So with only 10-18 games of each type in evaluation, one good or bad recipe swings a condition by 5-8 games, about the size of the E vs E-minus difference. This is a recipe-lottery effect, not a management effect.

**Construction at game 300:**
- E (managed: evidence from plan citations and trace harm, retirement, merging, refinement with trial games, write gates): 32 rules (r0) and 40 (r1), about 26-34 visible. 6 Success Process, 16-20 Corrected Error, 4-5 Special Phenomenon, 6 Failure Pool, 0-3 Anti-Pattern. Grew to about 26 by game 100, then stayed flat; refusals, merges and retirements balance new rules.
- E-minus (same Builder, no management): 173 (r0) and 190 (r1) rules, 159-170 visible. 6 Success Process, 96-107 Corrected Error, 52-55 Special Phenomenon, 8-14 Unresolved Error. About one new rule every 1.7 games, many near-duplicates. Retrieval still shows only a handful per game, so the size does not hurt it.
- Which looks better: E reaches the same accuracy with about 5x fewer rules and is readable and auditable. E-minus is a large pile of specific notes. Its success depends on its 6 recipes, which it can never fix. E's management could fix a bad recipe in principle, but in practice it did not repair the mixed-evidence ones (r1 heat, r1 look). Possible improvement (not done): let the refiner act on a recipe once its evidence is mixed (e.g. neg/shown > 0.4), not only when it is clearly bad.

Learning curve check (snapshot at practice game 150, 40 OOD + 40 ID games): E 24-25/40 OOD, 24-25 ID; E-minus 20-23 OOD, 26 ID. Neither condition keeps improving strongly from game 150 to game 300, since the recipes were mostly fixed early.
