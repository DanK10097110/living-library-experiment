# Large-library lab: report (2026-11-19)

**Verdict: keep the current flat task-keyed retrieval** (`manual.for_agent`, mode 'task', `SHOWN = 8`,
`CAPACITY = 200`). At the size a long run reaches (about 150-200 rules, capped at 200), it does not get
worse. The one thing that lowers top-k quality is **junk in the library, not its size**, and retrieval can
only screen junk out when the junk rules' win/loss counts are worse. The lever is library management
(credit assignment, retirement), not retrieval. Per the owner's priorities, no tree, merging, MMR or
reranking was built.

## 1. Expected long-run size (`tools/lab_growth.py`)
| run | games | rules (shown to agent) | added / removed | 2nd-half growth | fit at 3000 games |
|---|---|---|---|---|---|
| practice-b | 48 | 16 (14) | 16 / 0 | 0.21/game | 200 (cap) |
| practice-d | 48 | 22 (16) | 22 / 0 | 0.29/game | 200 (cap) |
| practice-e | 48 | 16 (13) | 16 / 0 | 0.21/game | 143 |
| mini-macla | 48 | 20 (15) | 20 / 0 | 0.25/game | 178 |

No real run has removed a rule yet. The merge gate (similarity >= 0.85) and pruning above `CAPACITY = 200`
bound the growth. The estimate is 150-200 rules, about 25-35 per task kind.

## 2. Benchmark (`tools/lab_bench.py`, `living_library/lab/`)
- **Real data:** 113 distinct real rules shown to the agent, from all libraries so far. Keeping one Success
  Process per kind leaves 71. Queries are 91 real games: 70 seen-room dev games and 21 unseen-room games,
  each with its goal, task type and plan.
- **Synthetic growth:** for 65 non-recipe rules, the model wrote paraphrases, near-duplicates, more
  general and more specific versions, versions for another task kind, and junk (vague, wrong,
  instance-specific). That is 195 cached calls and 2298 candidates. Every candidate must pass the live
  merge gate. Win/loss counts are drawn from the real counts for every class, junk included (as in the
  live system, where all rules shown in a game get the same credit).
- **Settings:**
  - Main: the junk share is held at 20% for every N. Distinct non-junk variants run out at about 267 rules.
  - Stress ("natural"): junk accumulates as generated, reaching 56% at 470 rules.
- **Methods:** the baseline is `manual.for_agent(mode='task')`, imported unchanged. `random` is the same
  candidate set in random order.
- **Metrics (k = 3, 5, 8):**
  - P@k: the relevant share of the rules shown;
  - nDCG@k: gain 2 for the kind's recipe, 1 for any other relevant rule;
  - useful@8: distinct relevant rules shown;
  - duplicate, junk and wrong-kind shares of the top-k;
  - time per query.
- **Labels** (deterministic, `synth.label`):
  - junk: the junk variants and 14 hand-flagged real rules (`synth.HAND_JUNK`);
  - wrong kind: the rule's scope is another kind, or its text uses another kind's action words;
  - object-named rules are relevant only if the goal names that object;
  - otherwise relevant.
  - Spot check: 40 labels read by hand. The noisiest class is rules written for another task kind; a
    sensitivity run labels all of them junk, and the verdict holds.

## 3. Results (5 seeds, 91 queries)
**Main setting (20% junk).** All columns after "method" are means over seeds.
| N (built) | method | candidates/kind | useful@8 | P@3 | P@8 | nDCG@8 | dup@8 | junk@8 | wrong@8 | ms/query |
|---|---|---|---|---|---|---|---|---|---|---|
| 15 | baseline | 3 | 2.08 | 0.79 | 0.77 | 0.98 | 0 | 0.10 | 0.11 | 3 |
| 50 | baseline | 10 | 5.55 | 0.76 | 0.72 | 0.89 | 0 | 0.12 | 0.12 | 5 |
| 50 | random | 10 | 5.23 | 0.74 | 0.68 | 0.86 | 0 | 0.15 | 0.14 | 0 |
| 100 | baseline | 24 | 5.36 | 0.86 | 0.67 | 0.79 | 0.003 | 0.12 | 0.09 | 9 |
| 100 | random | 24 | 5.66 | 0.79 | 0.71 | 0.80 | 0.005 | 0.15 | 0.07 | 0 |
| **200** | **baseline** | 55 | **6.37** | **0.91** | **0.80** | **0.87** | **0** | **0.09** | **0.03** | 20 |
| 200 | random | 55 | 5.84 | 0.80 | 0.73 | 0.82 | 0.005 | 0.13 | 0.03 | 1 |
| 300 (267) | baseline | 77 | 6.53 | 0.89 | 0.82 | 0.88 | 0 | 0.09 | 0.05 | 26 |
| 300 (267) | random | 77 | 6.04 | 0.82 | 0.76 | 0.83 | 0.004 | 0.11 | 0.04 | 1 |

The unseen-room games show the same pattern: P@8 0.80 and 0.82, nDCG@8 0.87 and 0.88, at N = 200 and 267.

**Stress setting** (junk accumulates as generated):
| N | junk in library | baseline P@8 | baseline junk@8 | random P@8 | P@8 among non-junk shown |
|---|---|---|---|---|---|
| 50 | 0.18 | 0.72 | 0.12 | 0.68 | 0.82 |
| 100 | 0.30 | 0.56 | 0.25 | 0.64 | 0.75 |
| 200 | 0.45 | 0.50 | 0.37 | 0.57 | 0.79 |
| 300 | 0.50 | 0.52 | 0.40 | 0.55 | 0.86 |
| 470 | 0.56 | 0.49 | 0.44 | 0.50 | 0.88 |

**Sensitivity (3 seeds):**
| variant | N | baseline P@8 / junk@8 | random P@8 / junk@8 |
|---|---|---|---|
| junk mostly lost while shown | 200 | 0.84 / 0.04 | 0.72 / 0.14 |
| junk mostly lost while shown | 271 | 0.88 / 0.03 | 0.75 / 0.12 |
| all rules written for another kind labeled junk | 190 | 0.73 / 0.15 | 0.75 / 0.10 |

## 4. Findings
1. **Size alone does not hurt retrieval, up to about 270 rules (about 77 per kind).**
   - P@8 is 0.80-0.82 at N = 200-270, against 0.72 at 50.
   - Duplicates stay at about 0, because the merge gate removes them; MMR would have nothing to do.
   - Wrong-kind rules fall to 3-5%.
   - No drop near 50 rules.
2. **The ranking adds about 0.07 P@8 over random order at N >= 200, and nothing below about 10
   candidates per kind** (everything is shown anyway).
3. **Junk is the real risk.** When junk accumulates, junk in the top-8 follows the library's junk share,
   and the ranking can't help: the non-junk rules shown are still 80-88% relevant, so the problem is the
   library's content. If junk loses more often than it wins, MACLA's expected utility screens it out
   (3-4% junk in the top-8 vs 12-14% in random order). In the live system, however, all rules shown in a
   game get the same credit, so junk counts look like everything else unless retirement acts.
4. **Cost:** 20-40 ms per query, no model calls.

## 5. Recommendation
- Adopt no new retrieval method.
- Don't add a tree, a model router or reranker, merging or MMR for retrieval, or a cap below 200.
- Watch and fix library management:
  - the share of junk rules shown to the agent;
  - whether retirement ever fires;
  - per-rule credit assignment (co-shown rules get identical win/loss counts).
- Re-run `tools/lab_bench.py` if one kind ever holds far more than about 80 candidates.

## 6. Optional real check (Phase 3)
Union of all real libraries (`tools/lab_union.py` -> `results/lab/data/union-rules-full.json`): 71 rules shown
to the agent, about 20% hand-flagged junk, run frozen on the 70 dev games. Expect about 45-54/70 (C 39/70,
noise about ±4).

## 7. Files
- Code: `living_library/lab/` (data, client, synth, metrics, methods; outside the run source fingerprint).
- Tools: `tools/lab_bench.py`, `tools/lab_summary.py`, `tools/lab_growth.py`, `tools/lab_union.py`.
- Tests: `tests/test_lab_bench.py` (155 tests pass).
- Data: `results/lab/data/`.

## 8. Phase 3 result (real games, 2026-11-19)
Union library (71 visible real rules, about 20% junk), frozen, on the 70 dev games: **50/70 vs C 39/70** (17 won
where C lost, 6 lost where C won). Small libraries scored 47-54/70 on the same games. A 3-5x larger real
library does not hurt with the current retrieval. By type: look 3/4, simple 18/22, clean 7/11, cool 9/12,
heat 4/9, two 9/12.
