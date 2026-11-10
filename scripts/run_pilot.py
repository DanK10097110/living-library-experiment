#!/usr/bin/env python3
"""
run_pilot.py — Run the Phase 1 ALFWorld pilot experiments.

Runs practice and evaluation episodes for:
  - System C: Hierarchical agent without memory (fresh empty library per episode)
  - System E-: Hierarchical agent with append-only skill library

Measures and reports the 5 pilot decision rules:
  1. System C task success rate (above 85% -> switch to ScienceWorld)
  2. System E- task success rate (above 85% -> switch to ScienceWorld)
  3. Skills reused >= 5 times (fewer than 10 -> switch to ScienceWorld)
  4. False-success rate (above 10% -> tighten verification rules)
  5. Rejected or crashing L2 programs (above 40% -> improve skill generation)

Usage:
  python scripts/run_pilot.py --condition E- --episodes 300
  python scripts/run_pilot.py --condition C --episodes 140 --split valid_seen
  python scripts/run_pilot.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from living_skills.environment import AlfWorldEnv, discover_games, GameInfo
from living_skills.planner import create_planner
from living_skills.skill_writer import create_skill_writer
from living_skills.skill_library import SkillLibrary
from living_skills.executor import SkillExecutor, EpisodeRunner
from living_skills.metrics import MetricsLogger


def load_config(config_path: str | Path) -> dict:
    """Load pilot YAML configuration."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_pilot_condition(
    condition: str,
    games: list[GameInfo],
    config: dict,
    num_episodes: int,
    output_dir: Path,
    seed: int = 42,
) -> dict:
    """
    Run pilot episodes under a specific condition (C or E-).

    Args:
        condition: 'C' (no memory) or 'E-' (append-only library).
        games: List of available GameInfo objects.
        config: Configuration dictionary.
        num_episodes: Number of episodes to run.
        output_dir: Output directory for results.
        seed: Random seed for episode sampling.

    Returns:
        Summary metrics dictionary.
    """
    random.seed(seed)
    sampled_games = random.choices(games, k=num_episodes) if len(games) < num_episodes else random.sample(games, num_episodes)

    output_dir.mkdir(parents=True, exist_ok=True)
    logger = MetricsLogger(log_dir=output_dir)

    # Initialize shared library for E-, or None for C
    library_path = output_dir / f"library_{condition}.json"
    lib_cfg = config.get("skill_library", {})
    shared_library = None
    if condition == "E-":
        shared_library = SkillLibrary(
            retrieval_top_k=lib_cfg.get("retrieval_top_k", 3),
            similarity_threshold=lib_cfg.get("similarity_threshold", 0.4),
            reliability_percentile=lib_cfg.get("reliability_percentile", 10) / 100.0,
            persist_path=library_path,
        )

    # Planners and writers
    l1_cfg = config.get("l1_planner", {})
    l2_cfg = config.get("l2_skill_writer", {})
    planner = create_planner(mode=l1_cfg.get("mode", "heuristic"))
    skill_writer = create_skill_writer(mode=l2_cfg.get("mode", "heuristic"))

    exec_cfg = config.get("executor", {})
    executor = SkillExecutor(max_skill_steps=exec_cfg.get("max_skill_steps", 20))
    env = AlfWorldEnv(max_steps=config.get("environment", {}).get("max_steps_per_episode", 50))

    print(f"\n{'='*70}")
    print(f"Starting Pilot Run: System {condition}")
    print(f"Episodes: {num_episodes} | Output: {output_dir}")
    print(f"{'='*70}\n")

    start_wall_time = time.time()
    for idx, game in enumerate(sampled_games, 1):
        ep_id = f"{condition}_{idx:04d}"

        # System C gets a fresh empty library for every episode
        if condition == "C":
            ep_library = SkillLibrary(
                retrieval_top_k=lib_cfg.get("retrieval_top_k", 3),
                similarity_threshold=lib_cfg.get("similarity_threshold", 0.4),
            )
        else:
            ep_library = shared_library

        runner = EpisodeRunner(
            env=env,
            planner=planner,
            skill_writer=skill_writer,
            skill_library=ep_library,
            executor=executor,
        )

        record = runner.run_episode(game, episode_id=ep_id)
        metrics = logger.log_episode(record)

        # Progress output
        status = "✓ WON " if record.won else "✗ FAIL"
        lib_size = ep_library.size if ep_library else 0
        print(
            f"[{idx:3d}/{num_episodes}] {ep_id} | {status} | "
            f"Steps: {record.total_steps:2d} | Time: {record.elapsed_seconds:4.1f}s | "
            f"Gen: {record.skills_generated} Ret: {record.skills_retrieved} | "
            f"Lib: {lib_size:2d} | {game.task_type}"
        )

    total_wall_time = time.time() - start_wall_time
    env.close()

    # Save detailed outputs
    logger.save_episode_log(f"episode_log_{condition}.jsonl")
    logger.save_metrics_csv(f"episode_metrics_{condition}.csv")

    summary_metrics = logger.save_pilot_report(
        library=shared_library if condition == "E-" else None,
        filename=f"pilot_metrics_{condition}.json",
    )
    summary_metrics["wall_clock_seconds"] = round(total_wall_time, 2)
    summary_metrics["condition"] = condition

    # Generate Markdown Summary
    report_md = generate_markdown_report(condition, summary_metrics, num_episodes, output_dir)
    with open(output_dir / f"pilot_report_{condition}.md", "w") as f:
        f.write(report_md)

    print(f"\nCompleted {num_episodes} episodes in {total_wall_time:.1f}s.")
    return summary_metrics


def generate_markdown_report(condition: str, metrics: dict, num_episodes: int, output_dir: Path) -> str:
    """Generate a clean markdown report of the pilot run."""
    decisions = metrics.get("pilot_decisions", {})

    lines = [
        f"# Pilot Evaluation Report: System {condition}",
        f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"- **Episodes:** {num_episodes}",
        f"- **Overall Success Rate:** {metrics.get('success_rate', 0.0) * 100:.1f}% ({metrics.get('successes', 0)}/{metrics.get('total_episodes', 0)})",
        f"- **Avg Steps / Episode:** {metrics.get('avg_steps_per_episode', 0.0)}",
        f"- **Avg Elapsed Time / Episode:** {metrics.get('avg_elapsed_seconds', 0.0):.2f}s",
        "",
        "## 1. Pilot Decision Rules Evaluation",
        "",
        "| Check | Current Value | Threshold | Status / Triggered | Decision |",
        "|---|---|---|---|---|",
    ]

    rule_names = {
        "success_above_85pct": ("Task Success Rate", "> 85%"),
        "skills_reused_5plus": ("Skills Reused ≥ 5 times", "< 10 skills"),
        "false_success_rate": ("False Success Rate", "> 10%"),
        "l2_crash_rate": ("L2 Crash / Reject Rate", "> 40%"),
    }

    for key, (label, thresh_str) in rule_names.items():
        if key in decisions:
            d = decisions[key]
            val = d.get("value")
            val_str = f"{val * 100:.1f}%" if isinstance(val, float) and val <= 1.0 else str(val)
            trig = "⚠️ YES (Triggered)" if d.get("triggered") else "✅ NO (Passed)"
            action = d.get("action", "")
            lines.append(f"| **{label}** | {val_str} | {thresh_str} | {trig} | {action} |")

    lines.extend([
        "",
        "## 2. Performance by Task Type",
        "",
        "| Task Type | Total Episodes | Successes | Success Rate |",
        "|---|---|---|---|",
    ])

    for tt, stats in sorted(metrics.get("by_task_type", {}).items()):
        rate = stats.get("rate", 0.0) * 100
        lines.append(f"| `{tt}` | {stats.get('total', 0)} | {stats.get('success', 0)} | {rate:.1f}% |")

    lib_stats = metrics.get("library_stats", {})
    if lib_stats:
        lines.extend([
            "",
            "## 3. Skill Library Reuse Statistics",
            "",
            f"- **Total Stored Skills:** {lib_stats.get('total_skills', 0)}",
            f"- **Skills Used at least Once:** {lib_stats.get('skills_used', 0)}",
            f"- **Skills Reused ≥ 5 Times:** {lib_stats.get('skills_used_5plus', 0)}",
            f"- **Total Skill Invocations:** {lib_stats.get('total_invocations', 0)}",
            f"- **Average Uses per Active Skill:** {lib_stats.get('avg_uses', 0.0):.2f}",
        ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run ALFWorld Pilot Experiments")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/pilot.yaml",
        help="Path to pilot YAML configuration",
    )
    parser.add_argument(
        "--condition",
        type=str,
        choices=["C", "E-", "both"],
        default="E-",
        help="Condition to run: C (no memory), E- (append-only), or both",
    )
    parser.add_argument(
        "--split",
        type=str,
        default=None,
        help="Split to use (defaults to config: train for practice, valid_seen for eval)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=None,
        help="Override number of episodes to run",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to save logs, metrics, and reports",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run 5 test episodes for quick verification",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    env_cfg = config.get("environment", {})
    pilot_cfg = config.get("pilot", {})

    data_dir = Path(os.path.expanduser(env_cfg.get("data_dir", "~/.cache/alfworld/json_2.1.1")))
    split = args.split or pilot_cfg.get("split", "train")
    num_episodes = 5 if args.dry_run else (args.episodes or pilot_cfg.get("num_practice_episodes", 300))
    output_dir = Path(args.output_dir)

    print("Discovering playable games...")
    games = discover_games(
        data_dir=data_dir,
        split=split,
        task_types=set(config.get("task_types", [])),
        excluded_patterns=set(env_cfg.get("excluded_patterns", [])),
    )
    print(f"Discovered {len(games)} games in split '{split}'.")

    if not games:
        print("ERROR: No games found for the specified split!")
        sys.exit(1)

    conditions_to_run = ["C", "E-"] if args.condition == "both" else [args.condition]

    for cond in conditions_to_run:
        cond_dir = output_dir / f"pilot_{cond}"
        metrics = run_pilot_condition(
            condition=cond,
            games=games,
            config=config,
            num_episodes=num_episodes,
            output_dir=cond_dir,
            seed=args.seed,
        )

        print("\n" + "=" * 70)
        print(f"Pilot Summary for System {cond}:")
        print(f"Success Rate: {metrics['success_rate'] * 100:.1f}%")
        print("Decisions:")
        for rule, data in metrics["pilot_decisions"].items():
            print(f"  - {rule}: {data['value']} (Threshold: {data['threshold']}) -> {data['action']}")
        print("=" * 70)


if __name__ == "__main__":
    main()
