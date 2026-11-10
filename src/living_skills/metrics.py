"""
metrics.py — Episode logging and pilot metrics computation.

Records per-episode data and computes the five pilot decision-rule
metrics from the revised proposal (p. 3):

1. System C task success (no memory) — above 85% → switch to ScienceWorld
2. System E- task success (append-only) — above 85% → switch to ScienceWorld
3. Skills reused at least 5 times — fewer than 10 → switch to ScienceWorld
4. False-success rate — above 10% → tighten verification
5. Rejected/crashing L2 programs — above 40% → improve skill generation
"""

from __future__ import annotations

import json
import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class EpisodeMetrics:
    """Metrics for a single episode."""
    episode_id: str
    game_path: str
    task_type: str
    success: bool
    won: bool
    total_steps: int
    elapsed_seconds: float
    skills_generated: int
    skills_retrieved: int
    num_subgoals: int
    subgoals_succeeded: int
    subgoals_failed: int
    false_success: bool
    code_crashes: int
    retrieval_errors: int


class MetricsLogger:
    """
    Logs episode metrics and computes pilot summary statistics.
    """

    def __init__(self, log_dir: str | Path = "results"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._episodes: list[EpisodeMetrics] = []
        self._episode_details: list[dict] = []

    def log_episode(self, record) -> EpisodeMetrics:
        """
        Extract metrics from an EpisodeRecord and store them.

        Args:
            record: An EpisodeRecord from executor.py.

        Returns:
            The extracted EpisodeMetrics.
        """
        subgoals_succeeded = sum(
            1 for sr in record.subgoal_results if sr.get("success", False)
        )
        subgoals_failed = sum(
            1 for sr in record.subgoal_results if not sr.get("success", True)
        )
        code_crashes = sum(
            1 for sr in record.subgoal_results if sr.get("error") is not None
        )
        retrieval_errors = sum(
            1 for sr in record.subgoal_results
            if not sr.get("preconditions_held", True)
        )

        metrics = EpisodeMetrics(
            episode_id=record.episode_id,
            game_path=record.game_path,
            task_type=record.task_type,
            success=record.success,
            won=record.won,
            total_steps=record.total_steps,
            elapsed_seconds=record.elapsed_seconds,
            skills_generated=record.skills_generated,
            skills_retrieved=record.skills_retrieved,
            num_subgoals=len(record.subgoal_results),
            subgoals_succeeded=subgoals_succeeded,
            subgoals_failed=subgoals_failed,
            false_success=record.false_success,
            code_crashes=code_crashes,
            retrieval_errors=retrieval_errors,
        )

        self._episodes.append(metrics)
        self._episode_details.append({
            "episode_id": record.episode_id,
            "task_type": record.task_type,
            "task_desc": record.task_desc,
            "success": record.success,
            "subgoal_results": record.subgoal_results,
        })

        return metrics

    def compute_pilot_metrics(self, library=None) -> dict:
        """
        Compute the five pilot decision-rule metrics.

        Args:
            library: Optional SkillLibrary for reuse stats.

        Returns:
            Dictionary with all pilot metrics and pass/fail decisions.
        """
        total = len(self._episodes)
        if total == 0:
            return {"error": "No episodes logged"}

        # ── Metric 1 & 2: Task success rate ────────────────────────────
        successes = sum(1 for e in self._episodes if e.success)
        success_rate = successes / total

        # ── Metric 3: Skills reused ≥5 times ──────────────────────────
        skills_5plus = 0
        reuse_stats = {}
        if library is not None:
            reuse_stats = library.get_reuse_stats()
            skills_5plus = reuse_stats.get("skills_used_5plus", 0)

        # ── Metric 4: False-success rate ───────────────────────────────
        false_successes = sum(1 for e in self._episodes if e.false_success)
        false_success_rate = false_successes / total if total > 0 else 0.0

        # ── Metric 5: L2 crash/reject rate ─────────────────────────────
        total_skill_invocations = sum(e.num_subgoals for e in self._episodes)
        total_crashes = sum(e.code_crashes for e in self._episodes)
        crash_rate = (
            total_crashes / total_skill_invocations
            if total_skill_invocations > 0 else 0.0
        )

        # ── Decision rules ─────────────────────────────────────────────
        pilot_decisions = {
            "success_above_85pct": {
                "value": round(success_rate, 4),
                "threshold": 0.85,
                "triggered": success_rate > 0.85,
                "action": "Switch to ScienceWorld" if success_rate > 0.85
                          else "ALFWorld is suitable",
            },
            "false_success_rate": {
                "value": round(false_success_rate, 4),
                "threshold": 0.10,
                "triggered": false_success_rate > 0.10,
                "action": "Tighten verification" if false_success_rate > 0.10
                          else "Verification is adequate",
            },
            "l2_crash_rate": {
                "value": round(crash_rate, 4),
                "threshold": 0.40,
                "triggered": crash_rate > 0.40,
                "action": "Improve skill generation" if crash_rate > 0.40
                          else "Skill generation is adequate",
            },
        }

        if library is not None:
            pilot_decisions["skills_reused_5plus"] = {
                "value": skills_5plus,
                "threshold": 10,
                "triggered": skills_5plus < 10,
                "action": "Switch to ScienceWorld" if skills_5plus < 10
                          else "Sufficient skill reuse",
            }
        else:
            pilot_decisions["skills_reused_5plus"] = {
                "value": "N/A",
                "threshold": 10,
                "triggered": False,
                "action": "Not applicable to System C (no memory)",
            }

        metrics = {
            "total_episodes": total,
            "successes": successes,
            "success_rate": round(success_rate, 4),

            # Per task type
            "by_task_type": self._by_task_type(),

            # Pilot decision rules
            "pilot_decisions": pilot_decisions,

            # Additional stats
            "avg_steps_per_episode": round(
                sum(e.total_steps for e in self._episodes) / total, 2
            ),
            "avg_elapsed_seconds": round(
                sum(e.elapsed_seconds for e in self._episodes) / total, 4
            ),
            "total_skills_generated": sum(e.skills_generated for e in self._episodes),
            "total_skills_retrieved": sum(e.skills_retrieved for e in self._episodes),

            # Library stats
            "library_stats": reuse_stats,
        }

        return metrics

    def _by_task_type(self) -> dict:
        """Break down success by task type."""
        type_counts: dict[str, dict] = {}
        for e in self._episodes:
            if e.task_type not in type_counts:
                type_counts[e.task_type] = {"total": 0, "success": 0}
            type_counts[e.task_type]["total"] += 1
            if e.success:
                type_counts[e.task_type]["success"] += 1

        result = {}
        for tt, counts in sorted(type_counts.items()):
            rate = counts["success"] / counts["total"] if counts["total"] > 0 else 0
            result[tt] = {
                "total": counts["total"],
                "success": counts["success"],
                "rate": round(rate, 4),
            }
        return result

    # ── Persistence ────────────────────────────────────────────────────

    def save_episode_log(self, filename: str = "episode_log.jsonl"):
        """Save per-episode detail log as JSONL."""
        path = self.log_dir / filename
        with open(path, "w") as f:
            for detail in self._episode_details:
                f.write(json.dumps(detail) + "\n")

    def save_metrics_csv(self, filename: str = "episode_metrics.csv"):
        """Save per-episode metrics as CSV."""
        if not self._episodes:
            return

        path = self.log_dir / filename
        fieldnames = list(asdict(self._episodes[0]).keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for ep in self._episodes:
                writer.writerow(asdict(ep))

    def save_pilot_report(self, library=None, filename: str = "pilot_metrics.json"):
        """Save the pilot summary metrics as JSON."""
        metrics = self.compute_pilot_metrics(library=library)
        path = self.log_dir / filename
        with open(path, "w") as f:
            json.dump(metrics, f, indent=2)
        return metrics
