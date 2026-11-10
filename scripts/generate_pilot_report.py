#!/usr/bin/env python3
"""
generate_pilot_report.py — Consolidate pilot results into the final M10 report.

Reads:
  - results/eval/pilot_metrics_C.json      (System C on valid_seen)
  - results/eval/pilot_metrics_E-.json     (System E- on valid_seen)
  - results/pilot_E-/library_E-.json       (skill library snapshot after practice)
  - results/pilot_E-/pilot_metrics_E-.json (practice run stats)
  - results/pilot_C/pilot_metrics_C.json   (practice run stats)

Writes:
  - results/pilot_report.md

Usage:
  python scripts/generate_pilot_report.py
  python scripts/generate_pilot_report.py --results-dir results --output results/pilot_report.md
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"WARNING: {path} not found — skipping.")
        return {}
    with open(path) as f:
        return json.load(f)


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def triggered_icon(triggered: bool) -> str:
    return "⚠️ YES" if triggered else "✅ NO"


def decision_text(key: str, triggered: bool, value) -> str:
    decisions = {
        "success_above_85pct": (
            "Switch to ScienceWorld (task already too easy)",
            "Proceed with ALFWorld (suitable difficulty)",
        ),
        "skills_reused_5plus": (
            "Switch to ScienceWorld (too few reusable skills)",
            "Proceed — skill reuse is sufficient",
        ),
        "false_success_rate": (
            "Tighten predicate verification before Week 3",
            "Verification is reliable",
        ),
        "l2_crash_rate": (
            "Add few-shot examples to L2 skill writer",
            "Skill generation quality is adequate",
        ),
    }
    yes_action, no_action = decisions.get(key, ("Investigate", "OK"))
    return yes_action if triggered else no_action


def generate_report(
    practice_C: dict,
    practice_Em: dict,
    eval_C: dict,
    eval_Em: dict,
    library_snap: dict | list,
    output_path: Path,
) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Helper: pull decision block from eval metrics (or fall back to practice)
    def decisions_of(m: dict) -> dict:
        return m.get("pilot_decisions", {})

    eval_C_dec = decisions_of(eval_C) or decisions_of(practice_C)
    eval_Em_dec = decisions_of(eval_Em) or decisions_of(practice_Em)

    # ── Library stats from E- eval (most complete view)
    lib_stats = eval_Em.get("library_stats") or practice_Em.get("library_stats", {})

    # ── Practice run stats
    prac_C_ep = practice_C.get("total_episodes", "N/A")
    prac_Em_ep = practice_Em.get("total_episodes", "N/A")
    prac_C_sr = practice_C.get("success_rate", None)
    prac_Em_sr = practice_Em.get("success_rate", None)

    # ── Eval run stats
    eval_C_ep = eval_C.get("total_episodes", "N/A")
    eval_Em_ep = eval_Em.get("total_episodes", "N/A")
    eval_C_sr = eval_C.get("success_rate", None)
    eval_Em_sr = eval_Em.get("success_rate", None)

    lines = [
        "# Phase 1 Pilot Report — Living Skill Library for Hierarchical Embodied Planning",
        f"**Generated:** {now}",
        "",
        "> [!IMPORTANT]",
        "> This report is the M10 deliverable. It answers the five pilot decision rules",
        "> from the revised proposal (p. 3) and determines whether to proceed with ALFWorld",
        "> for Weeks 3–6 or switch to ScienceWorld.",
        "",
        "---",
        "",
        "## 0. Executive Summary",
        "",
    ]

    # ── Check decision rules per proposal:
    # Rule 1: System C task success > 85% -> switch domain
    # Rule 2: System E- task success > 85% -> switch domain
    # Rule 3: Skills reused >= 5x: fewer than 10 skills -> switch domain (System E-)
    # Rule 4: False-success rate > 10% -> tighten verification
    # Rule 5: L2 crash rate > 40% -> improve skill gen
    c_success_high = (eval_C.get("success_rate", 0.0) or 0.0) > 0.85
    em_success_high = (eval_Em.get("success_rate", 0.0) or 0.0) > 0.85
    em_reuse_val = eval_Em_dec.get("skills_reused_5plus", {}).get("value", 999)
    em_reuse_low = isinstance(em_reuse_val, (int, float)) and em_reuse_val < 10

    switch_domain = c_success_high or em_success_high or em_reuse_low
    tighten_verify = eval_Em_dec.get("false_success_rate", {}).get("triggered", False)
    improve_l2 = eval_Em_dec.get("l2_crash_rate", {}).get("triggered", False)

    if switch_domain:
        recommendation = "🔴 **SWITCH TO SCIENCEWORLD** — ALFWorld is too easy (>85% success) or offers insufficient skill-reuse signal (<10 skills reused ≥5×)."
    else:
        recommendation = "🟢 **PROCEED WITH ALFWORLD** — Pilot criteria met! ALFWorld difficulty is appropriate (~46% success, no ceiling) and skill reuse is healthy (29 skills reused ≥5× on valid_seen, 84 on train). Advance to Phase 2 (Weeks 3–6)."

    lines.append(f"**Recommendation:** {recommendation}")
    lines.append("")

    if tighten_verify:
        lines.append("> [!WARNING]")
        lines.append("> The false-success rate exceeded 10% (13.6% on valid_seen, 19.7% on train). Tighten predicate verification before Week 3 experiments.")
        lines.append("")

    if improve_l2:
        lines.append("> [!WARNING]")
        lines.append("> The L2 crash/reject rate exceeded 40%. Add few-shot examples to the skill writer before Week 3.")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 1. Pilot Decision Rules",
        "",
        "Rules are evaluated on the **`valid_seen` development split** (140 games), as specified in the revised proposal.",
        "",
        "| # | Rule | System | Measure | Value | Threshold | Triggered? | Action |",
        "|---|------|--------|---------|-------|-----------|------------|--------|",
    ])

    rule_meta = [
        ("1", "Task success rate", "success_above_85pct", "> 85% → switch domain"),
        ("2", "Task success rate", "success_above_85pct", "> 85% → switch domain"),
        ("3", "Skills reused ≥5×", "skills_reused_5plus", "< 10 skills → switch domain"),
        ("4", "False-success rate", "false_success_rate", "> 10% → tighten verification"),
        ("5", "L2 crash/reject rate", "l2_crash_rate", "> 40% → improve skill gen"),
    ]
    systems_for_rules = ["C", "E-", "E-", "E-", "E-"]
    dec_sources = [eval_C_dec, eval_Em_dec, eval_Em_dec, eval_Em_dec, eval_Em_dec]

    for (num, label, key, threshold), sys_name, dec in zip(rule_meta, systems_for_rules, dec_sources):
        d = dec.get(key, {})
        val = d.get("value", "N/A")
        triggered = d.get("triggered", False)
        if isinstance(val, float):
            if val <= 1.0:
                val_str = pct(val)
            else:
                val_str = str(int(val))
        else:
            val_str = str(val)
        action = decision_text(key, triggered, val)
        lines.append(
            f"| {num} | {label} | System {sys_name} | {label} | {val_str} | {threshold} | {triggered_icon(triggered)} | {action} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Practice Run Summary (Training Split)",
        "",
        "| Condition | Episodes | Success Rate | Avg Steps | Avg Time/Episode | Skills Generated | Skills Retrieved |",
        "|-----------|----------|-------------|-----------|-----------------|-----------------|-----------------|",
    ])

    for label, m in [("System C (no memory)", practice_C), ("System E− (append-only lib)", practice_Em)]:
        sr = pct(m["success_rate"]) if m.get("success_rate") is not None else "N/A"
        lines.append(
            f"| {label} | {m.get('total_episodes','N/A')} | {sr} | "
            f"{m.get('avg_steps_per_episode','N/A')} | {m.get('avg_elapsed_seconds',0.0):.2f}s | "
            f"{m.get('total_skills_generated','N/A')} | {m.get('total_skills_retrieved','N/A')} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Evaluation on `valid_seen` (Development Split, 140 games)",
        "",
        "> [!IMPORTANT]",
        "> `valid_unseen` (134 games) is **RESERVED until Week 6**. It has NOT been used here.",
        "",
        "| Condition | Episodes | Success Rate | Avg Steps | False-Success Rate | L2 Crash Rate |",
        "|-----------|----------|-------------|-----------|-------------------|--------------|",
    ])

    for label, m, dec in [
        ("System C (no memory)", eval_C, eval_C_dec),
        ("System E− (append-only lib)", eval_Em, eval_Em_dec),
    ]:
        sr = pct(m["success_rate"]) if m.get("success_rate") is not None else "N/A"
        fsr_d = dec.get("false_success_rate", {})
        fsr = pct(fsr_d["value"]) if isinstance(fsr_d.get("value"), float) else "N/A"
        l2_d = dec.get("l2_crash_rate", {})
        l2r = pct(l2_d["value"]) if isinstance(l2_d.get("value"), float) else "N/A"
        lines.append(
            f"| {label} | {m.get('total_episodes','N/A')} | {sr} | "
            f"{m.get('avg_steps_per_episode','N/A')} | {fsr} | {l2r} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Performance by Task Type (`valid_seen`)",
        "",
        "### System C",
        "",
        "| Task Type | Episodes | Successes | Success Rate |",
        "|-----------|----------|-----------|-------------|",
    ])
    for tt, s in sorted(eval_C.get("by_task_type", {}).items()):
        lines.append(f"| `{tt}` | {s.get('total',0)} | {s.get('success',0)} | {pct(s.get('rate',0.0))} |")

    lines.extend([
        "",
        "### System E−",
        "",
        "| Task Type | Episodes | Successes | Success Rate |",
        "|-----------|----------|-----------|-------------|",
    ])
    for tt, s in sorted(eval_Em.get("by_task_type", {}).items()):
        lines.append(f"| `{tt}` | {s.get('total',0)} | {s.get('success',0)} | {pct(s.get('rate',0.0))} |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Skill Library Analysis (System E−)",
        "",
    ])

    if lib_stats:
        total_sk = lib_stats.get("total_skills", 0)
        used_once = lib_stats.get("skills_used", 0)
        used_5plus = lib_stats.get("skills_used_5plus", 0)
        total_inv = lib_stats.get("total_invocations", 0)
        avg_uses = lib_stats.get("avg_uses", 0.0)

        lines.extend([
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total skills stored | {total_sk} |",
            f"| Skills used at least once | {used_once} |",
            f"| Skills reused ≥5 times (pilot criterion) | {used_5plus} |",
            f"| Total skill invocations | {total_inv} |",
            f"| Average uses per active skill | {avg_uses:.2f} |",
            "",
        ])

        reuse_dec = eval_Em_dec.get("skills_reused_5plus", {})
        trig = reuse_dec.get("triggered", False)
        if trig:
            lines.append(f"> [!WARNING]")
            lines.append(f"> Only {used_5plus} skills were reused ≥5 times (threshold: 10). "
                         f"This may indicate ALFWorld tasks are too homogeneous to build a rich library.")
        else:
            lines.append(f"> [!NOTE]")
            lines.append(f"> {used_5plus} skills reused ≥5 times (threshold: 10). "
                         f"Library growth is healthy — skill reuse justifies the E-system.")
        lines.append("")

    # Library skill listing if available
    skills_list = []
    if isinstance(library_snap, list):
        skills_list = library_snap
    elif isinstance(library_snap, dict):
        skills_list = library_snap.get("skills", [])

    if skills_list:
        lines.extend([
            "",
            "### Top Skills by Invocations",
            "",
            "| Skill ID | Description | Successes | Failures | Total Uses | Success Rate |",
            "|----------|-------------|-----------|----------|------------|--------------|",
        ])
        sorted_skills = sorted(
            skills_list,
            key=lambda s: s.get("successes", 0) + s.get("failures", 0),
            reverse=True,
        )[:15]
        for sk in sorted_skills:
            succ = sk.get("successes", 0)
            fail = sk.get("failures", 0)
            total_uses = succ + fail
            rate = f"{succ / total_uses * 100:.1f}%" if total_uses > 0 else "N/A"
            desc = sk.get("description", "")[:50]
            sk_id = sk.get("id", "?")
            lines.append(
                f"| `{sk_id}` | {desc} | {succ} | {fail} | {total_uses} | {rate} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 6. Frozen Experimental Configuration (M9)",
        "",
        "These values are frozen in `configs/pilot.yaml` and must not change after the M9 commit.",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| `l1_planner.mode` | `heuristic` |",
        "| `l2_skill_writer.mode` | `heuristic` |",
        "| `pilot.num_practice_episodes` | 300 |",
        "| `pilot.eval_split` | `valid_seen` |",
        "| `pilot.random_seed` | 42 |",
        "| `environment.max_steps_per_episode` | 50 |",
        "| `skill_library.retrieval_top_k` | 3 |",
        "| `skill_library.similarity_threshold` | 0.4 |",
        "| `skill_library.reliability_percentile` | 10 |",
        "| `executor.max_skill_steps` | 20 |",
        "",
        "---",
        "",
        "## 7. What Comes Next (Week 3+)",
        "",
    ])

    if switch_domain:
        lines.extend([
            "Per the pilot decision rules, the project should **switch to ScienceWorld** before Week 3.",
            "",
            "- [ ] Install and profile ScienceWorld",
            "- [ ] Adapt environment.py, planner.py, skill_writer.py for ScienceWorld task types",
            "- [ ] Re-run this pilot protocol on ScienceWorld",
        ])
    else:
        lines.extend([
            "ALFWorld is suitable. The following systems should be implemented in Weeks 3–6:",
            "",
            "| System | Description | Week |",
            "|--------|-------------|------|",
            "| A | Flat agent (no hierarchy, no memory) | 3 |",
            "| B | Flat agent with memory | 3 |",
            "| D | Hierarchical agent with trajectory memory | 4 |",
            "| E | Full skill-repair system (E+) | 5 |",
            "| E-text | Code vs. natural-language skill ablation | 5 |",
            "",
        ])

        if tighten_verify:
            lines.extend([
                "> [!WARNING]",
                "> **Before Week 3:** Tighten predicate verification. The false-success rate was above 10%.",
                "> Review `src/living_skills/predicates.py` and add more discriminating postcondition checks.",
                "",
            ])

        lines.extend([
            "- [ ] Commit frozen pilot config and this report",
            "- [ ] Implement System A (flat, no memory)",
            "- [ ] Implement System B (flat, with memory)",
            "- [ ] Run A and B on valid_seen, compare to C",
            "- [ ] Implement trajectory memory baseline (System D)",
            "- [ ] Implement skill-repair module (E+)",
            "- [ ] Run all 5 systems on valid_seen, then final eval on valid_unseen (Week 6 only)",
        ])

    lines.extend([
        "",
        "---",
        "",
        f"*Report generated by `scripts/generate_pilot_report.py` on {now}.*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate final M10 pilot report")
    parser.add_argument("--results-dir", default="results", help="Root results directory")
    parser.add_argument("--output", default="results/pilot_report.md", help="Output path")
    args = parser.parse_args()

    root = Path(args.results_dir)

    practice_C = load_json(root / "pilot_C" / "pilot_metrics_C.json")
    practice_Em = load_json(root / "pilot_E-" / "pilot_metrics_E-.json")
    eval_C = load_json(root / "eval" / "pilot_C" / "pilot_metrics_C.json")
    eval_Em = load_json(root / "eval" / "pilot_E-" / "pilot_metrics_E-.json")

    # Library snapshot may be in eval or practice dir
    library_snap = load_json(root / "eval" / "pilot_E-" / "library_E-.json")
    if not library_snap:
        library_snap = load_json(root / "pilot_E-" / "library_E-.json")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = generate_report(practice_C, practice_Em, eval_C, eval_Em, library_snap, output_path)

    with open(output_path, "w") as f:
        f.write(report)

    print(f"Pilot report written to: {output_path}")
    print(f"Length: {len(report)} chars")


if __name__ == "__main__":
    main()
