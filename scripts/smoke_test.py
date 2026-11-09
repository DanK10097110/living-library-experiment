#!/usr/bin/env python3
"""
smoke_test.py — Verify ALFWorld integration works end-to-end.

This script:
1. Discovers training games using the environment module.
2. Loads one game and resets the environment.
3. Prints the task description, initial observation, and admissible actions.
4. Executes a few actions and shows the results.
5. Extracts and displays PDDL facts for predicate checking.

Run from the repository root with the ALFWorld venv activated:
    python scripts/smoke_test.py
"""

import sys
from pathlib import Path

# Add src/ to the path so we can import living_skills
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from living_skills.environment import AlfWorldEnv, discover_games


def main():
    data_dir = Path.home() / ".cache" / "alfworld" / "json_2.1.1"

    print("=" * 60)
    print("ALFWorld Smoke Test")
    print("=" * 60)

    # ── Step 1: Discover games ──────────────────────────────────────────
    print(f"\n[1] Discovering games in {data_dir}/train ...")
    games = discover_games(data_dir, split="train")
    print(f"    Found {len(games)} playable training games.")

    if not games:
        print("ERROR: No games found! Check your ALFWorld data installation.")
        sys.exit(1)

    # Show a few examples
    print("\n    First 5 games:")
    for g in games[:5]:
        print(f"      - {g.task_type}: {g.task_desc}")

    # ── Step 2: Load and reset a game ───────────────────────────────────
    game = games[0]
    print(f"\n[2] Loading game: {game.task_type}")
    print(f"    Task: {game.task_desc}")
    print(f"    Object target: {game.object_target}")
    print(f"    Parent target: {game.parent_target}")
    print(f"    Toggle target: {game.toggle_target}")

    env = AlfWorldEnv(max_steps=50)
    env.load(game)
    result = env.reset()

    print(f"\n[3] Initial observation:")
    print(f"    {result.observation[:500]}")
    print(f"\n    Admissible actions ({len(result.admissible_commands)}):")
    for cmd in result.admissible_commands[:10]:
        print(f"      - {cmd}")
    if len(result.admissible_commands) > 10:
        print(f"      ... and {len(result.admissible_commands) - 10} more")

    # ── Step 3: Extract facts ───────────────────────────────────────────
    print(f"\n[4] PDDL facts ({len(result.facts)} total):")
    for fact in result.facts[:15]:
        print(f"      - {fact}")
    if len(result.facts) > 15:
        print(f"      ... and {len(result.facts) - 15} more")

    # ── Step 4: Execute a few actions ───────────────────────────────────
    print("\n[5] Executing actions:")
    test_actions = ["look", "inventory"]
    for action in test_actions:
        if action in result.admissible_commands or action in ("look", "inventory"):
            result = env.step(action)
            obs_preview = result.observation[:200]
            print(f"\n    Action: '{action}'")
            print(f"    Observation: {obs_preview}")
            print(f"    Done: {result.done}  Won: {result.won}")

    # Try a "go to" action if available
    goto_cmds = [c for c in result.admissible_commands if c.startswith("go to")]
    if goto_cmds:
        action = goto_cmds[0]
        result = env.step(action)
        print(f"\n    Action: '{action}'")
        print(f"    Observation: {result.observation[:200]}")
        print(f"    New admissible commands: {len(result.admissible_commands)}")

    # ── Step 5: Also check valid_seen split ─────────────────────────────
    print("\n[6] Checking data splits:")
    for split in ["train", "valid_seen", "valid_unseen"]:
        try:
            split_games = discover_games(data_dir, split=split)
            print(f"    {split}: {len(split_games)} games")
        except FileNotFoundError:
            print(f"    {split}: NOT FOUND")

    env.close()

    print("\n" + "=" * 60)
    print("Smoke test PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
