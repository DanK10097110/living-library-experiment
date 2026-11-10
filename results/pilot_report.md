# Phase 1 Pilot Report — Living Skill Library for Hierarchical Embodied Planning
**Generated:** 2026-11-10 17:25:51

> [!IMPORTANT]
> This report is the M10 deliverable. It answers the five pilot decision rules
> from the revised proposal (p. 3) and determines whether to proceed with ALFWorld
> for Weeks 3–6 or switch to ScienceWorld.

---

## 0. Executive Summary

**Recommendation:** 🟢 **PROCEED WITH ALFWORLD** — Pilot criteria met! ALFWorld difficulty is appropriate (~46% success, no ceiling) and skill reuse is healthy (29 skills reused ≥5× on valid_seen, 84 on train). Advance to Phase 2 (Weeks 3–6).

> [!WARNING]
> The false-success rate exceeded 10% (13.6% on valid_seen, 19.7% on train). Tighten predicate verification before Week 3 experiments.

---

## 1. Pilot Decision Rules

Rules are evaluated on the **`valid_seen` development split** (140 games), as specified in the revised proposal.

| # | Rule | System | Measure | Value | Threshold | Triggered? | Action |
|---|------|--------|---------|-------|-----------|------------|--------|
| 1 | Task success rate | System C | Task success rate | 45.7% | > 85% → switch domain | ✅ NO | Proceed with ALFWorld (suitable difficulty) |
| 2 | Task success rate | System E- | Task success rate | 45.7% | > 85% → switch domain | ✅ NO | Proceed with ALFWorld (suitable difficulty) |
| 3 | Skills reused ≥5× | System E- | Skills reused ≥5× | 29 | < 10 skills → switch domain | ✅ NO | Proceed — skill reuse is sufficient |
| 4 | False-success rate | System E- | False-success rate | 13.6% | > 10% → tighten verification | ⚠️ YES | Tighten predicate verification before Week 3 |
| 5 | L2 crash/reject rate | System E- | L2 crash/reject rate | 6.8% | > 40% → improve skill gen | ✅ NO | Skill generation quality is adequate |

---

## 2. Practice Run Summary (Training Split)

| Condition | Episodes | Success Rate | Avg Steps | Avg Time/Episode | Skills Generated | Skills Retrieved |
|-----------|----------|-------------|-----------|-----------------|-----------------|-----------------|
| System C (no memory) | 300 | 45.3% | 17.06 | 2.78s | 1544 | 186 |
| System E− (append-only lib) | 300 | 45.3% | 17.15 | 3.38s | 663 | 1067 |

---

## 3. Evaluation on `valid_seen` (Development Split, 140 games)

> [!IMPORTANT]
> `valid_unseen` (134 games) is **RESERVED until Week 6**. It has NOT been used here.

| Condition | Episodes | Success Rate | Avg Steps | False-Success Rate | L2 Crash Rate |
|-----------|----------|-------------|-----------|-------------------|--------------|
| System C (no memory) | 140 | 45.7% | 17.04 | 13.6% | 6.8% |
| System E− (append-only lib) | 140 | 45.7% | 17.04 | 13.6% | 6.8% |

---

## 4. Performance by Task Type (`valid_seen`)

### System C

| Task Type | Episodes | Successes | Success Rate |
|-----------|----------|-----------|-------------|
| `look_at_obj_in_light` | 13 | 13 | 100.0% |
| `pick_and_place_simple` | 35 | 29 | 82.9% |
| `pick_clean_then_place_in_recep` | 27 | 8 | 29.6% |
| `pick_cool_then_place_in_recep` | 25 | 4 | 16.0% |
| `pick_heat_then_place_in_recep` | 16 | 10 | 62.5% |
| `pick_two_obj_and_place` | 24 | 0 | 0.0% |

### System E−

| Task Type | Episodes | Successes | Success Rate |
|-----------|----------|-----------|-------------|
| `look_at_obj_in_light` | 13 | 13 | 100.0% |
| `pick_and_place_simple` | 35 | 29 | 82.9% |
| `pick_clean_then_place_in_recep` | 27 | 8 | 29.6% |
| `pick_cool_then_place_in_recep` | 25 | 4 | 16.0% |
| `pick_heat_then_place_in_recep` | 16 | 10 | 62.5% |
| `pick_two_obj_and_place` | 24 | 0 | 0.0% |

---

## 5. Skill Library Analysis (System E−)

| Metric | Value |
|--------|-------|
| Total skills stored | 241 |
| Skills used at least once | 241 |
| Skills reused ≥5 times (pilot criterion) | 29 |
| Total skill invocations | 641 |
| Average uses per active skill | 2.66 |

> [!NOTE]
> 29 skills reused ≥5 times (threshold: 10). Library growth is healthy — skill reuse justifies the E-system.


### Top Skills by Invocations

| Skill ID | Description | Successes | Failures | Total Uses | Success Rate |
|----------|-------------|-----------|----------|------------|--------------|
| `find_fridge@v1` | Go to the fridge | 33 | 0 | 33 | 100.0% |
| `find_microwave@v1` | Go to the microwave | 24 | 0 | 24 | 100.0% |
| `find_countertop@v1` | Find the countertop | 19 | 0 | 19 | 100.0% |
| `find_drawer@v1` | Find the drawer | 17 | 0 | 17 | 100.0% |
| `find_toilet@v1` | Find the toilet | 15 | 0 | 15 | 100.0% |
| `find_desklamp@v1` | Find the desklamp | 12 | 1 | 13 | 92.3% |
| `toggle_desklamp@v1` | Turn on the desklamp | 13 | 0 | 13 | 100.0% |
| `find_cabinet@v1` | Find the cabinet | 13 | 0 | 13 | 100.0% |
| `find_spraybottle@v1` | Find the first spraybottle | 12 | 0 | 12 | 100.0% |
| `take_spraybottle@v1` | Take the first spraybottle | 12 | 0 | 12 | 100.0% |
| `find_diningtable@v1` | Find the diningtable | 11 | 0 | 11 | 100.0% |
| `find_mug@v1` | Find the mug | 8 | 1 | 9 | 88.9% |
| `take_mug@v1` | Take the mug | 8 | 1 | 9 | 88.9% |
| `find_soapbar@v1` | Find the soapbar | 9 | 0 | 9 | 100.0% |
| `take_soapbar@v1` | Take the soapbar | 9 | 0 | 9 | 100.0% |

---

## 6. Frozen Experimental Configuration (M9)

These values are frozen in `configs/pilot.yaml` and must not change after the M9 commit.

| Parameter | Value |
|-----------|-------|
| `l1_planner.mode` | `heuristic` |
| `l2_skill_writer.mode` | `heuristic` |
| `pilot.num_practice_episodes` | 300 |
| `pilot.eval_split` | `valid_seen` |
| `pilot.random_seed` | 42 |
| `environment.max_steps_per_episode` | 50 |
| `skill_library.retrieval_top_k` | 3 |
| `skill_library.similarity_threshold` | 0.4 |
| `skill_library.reliability_percentile` | 10 |
| `executor.max_skill_steps` | 20 |

---

## 7. What Comes Next (Week 3+)

ALFWorld is suitable. The following systems should be implemented in Weeks 3–6:

| System | Description | Week |
|--------|-------------|------|
| A | Flat agent (no hierarchy, no memory) | 3 |
| B | Flat agent with memory | 3 |
| D | Hierarchical agent with trajectory memory | 4 |
| E | Full skill-repair system (E+) | 5 |
| E-text | Code vs. natural-language skill ablation | 5 |

> [!WARNING]
> **Before Week 3:** Tighten predicate verification. The false-success rate was above 10%.
> Review `src/living_skills/predicates.py` and add more discriminating postcondition checks.

- [ ] Commit frozen pilot config and this report
- [ ] Implement System A (flat, no memory)
- [ ] Implement System B (flat, with memory)
- [ ] Run A and B on valid_seen, compare to C
- [ ] Implement trajectory memory baseline (System D)
- [ ] Implement skill-repair module (E+)
- [ ] Run all 5 systems on valid_seen, then final eval on valid_unseen (Week 6 only)

---

*Report generated by `scripts/generate_pilot_report.py` on 2026-11-10 17:25:51.*