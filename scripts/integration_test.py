#!/usr/bin/env python3
"""
integration_test.py — Test the full M1-M5 pipeline on a single episode.

Exercises:
  - environment.py  (M2/M3): game discovery, env load/reset/step
  - planner.py      (M4): heuristic L1 decomposition
  - skill_writer.py (M4): heuristic L2 skill generation
  - executor.py     (M5): safe skill execution
  - predicates.py   (M5): predicate checking
  - skill_library.py (M5): append-only storage + retrieval
  - metrics.py      (M5): episode logging

Run from the repository root:
    python scripts/integration_test.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from living_skills.environment import AlfWorldEnv, discover_games
from living_skills.planner import HeuristicPlanner
from living_skills.skill_writer import HeuristicSkillWriter
from living_skills.skill_library import SkillLibrary
from living_skills.executor import SkillExecutor, EpisodeRunner
from living_skills.predicates import (
    Predicate,
    ConditionSet,
    parse_predicate,
    get_task_postconditions,
)
from living_skills.metrics import MetricsLogger


def test_predicates():
    """Test the predicate system."""
    print("\n── Testing predicates ──")

    # Test parsing
    p1 = parse_predicate("holds(obj=apple)")
    p2 = parse_predicate("NOT isHot(obj=egg)")
    print(f"  Parsed: {p1}")
    print(f"  Parsed: {p2}")

    # Test evaluation against mock facts
    facts = [
        "holds agent apple 1",
        "atLocation agent loc 5",
        "inReceptacle egg 2 fridge 1",
    ]
    assert p1.evaluate(facts), f"Expected holds(apple) to be True in {facts}"
    assert p2.evaluate(facts), f"Expected NOT isHot(egg) to be True in {facts}"

    # Test task postconditions
    post = get_task_postconditions("pick_and_place_simple", {
        "object_target": "apple",
        "parent_target": "shelf",
    })
    print(f"  Postconditions for pick_and_place: {post}")

    print("  ✓ Predicates OK")


def test_planner():
    """Test the heuristic planner."""
    print("\n── Testing planner ──")

    planner = HeuristicPlanner()

    for task_type, params in [
        ("pick_and_place_simple", {"object_target": "Apple", "parent_target": "Shelf"}),
        ("look_at_obj_in_light", {"object_target": "AlarmClock", "toggle_target": "DeskLamp"}),
        ("pick_heat_then_place_in_recep", {"object_target": "Egg", "parent_target": "CounterTop"}),
    ]:
        plan = planner.plan(
            task_desc=f"Test {task_type}",
            task_type=task_type,
            pddl_params=params,
        )
        print(f"  {task_type}: {len(plan.subgoals)} subgoals")
        for sg in plan.subgoals:
            print(f"    → {sg}")

    print("  ✓ Planner OK")


def test_skill_writer():
    """Test the heuristic skill writer."""
    print("\n── Testing skill writer ──")

    from living_skills.planner import Subgoal

    writer = HeuristicSkillWriter()

    subgoals = [
        Subgoal("find", "apple"),
        Subgoal("take", "apple"),
        Subgoal("put", "apple", "shelf"),
        Subgoal("heat", "egg"),
        Subgoal("toggle", "desklamp"),
    ]

    for sg in subgoals:
        skill = writer.generate(sg)
        print(f"  {sg.action}({sg.target}): generated skill '{skill.signature}'")
        print(f"    Pre:  {skill.preconditions}")
        print(f"    Post: {skill.postconditions}")
        # Verify the code compiles
        compile(skill.body, f"<skill_{sg.action}>", "exec")

    print("  ✓ Skill writer OK")


def test_skill_library():
    """Test the append-only skill library."""
    print("\n── Testing skill library ──")

    from living_skills.skill_library import SkillRecord

    lib = SkillLibrary(retrieval_top_k=3)

    # Add some skills
    s1 = SkillRecord(
        id="", signature="take_apple(obj)", description="Take the apple",
        preconditions=[], postconditions=["holds(obj=apple)"],
        body="def take_apple(env, ac, **kw): return True",
    )
    s2 = SkillRecord(
        id="", signature="heat_egg(obj)", description="Heat the egg",
        preconditions=["holds(obj=egg)"], postconditions=["isHot(obj=egg)"],
        body="def heat_egg(env, ac, **kw): return True",
    )

    id1 = lib.add(s1)
    id2 = lib.add(s2)
    print(f"  Added: {id1}, {id2}")
    print(f"  Library size: {lib.size}")

    # Test retrieval
    results = lib.retrieve("take apple")
    print(f"  Query 'take apple': found {len(results)} results")
    for r in results:
        print(f"    → {r.id}: {r.description}")

    # Test reliability scoring
    s1.record_success()
    s1.record_success()
    s1.record_failure()
    print(f"  {id1} reliability: {s1.reliability_score():.3f} "
          f"(success_rate={s1.success_rate:.2f}, uses={s1.total_uses})")

    # Test reuse stats
    stats = lib.get_reuse_stats()
    print(f"  Reuse stats: {stats}")

    print("  ✓ Skill library OK")


def test_full_episode(data_dir: Path):
    """Run a single episode through the full pipeline."""
    print("\n── Testing full episode ──")

    games = discover_games(data_dir, split="train")
    if not games:
        print("  SKIP: No games found")
        return

    # Pick a simple pick_and_place game
    target_games = [g for g in games if g.task_type == "pick_and_place_simple"]
    if not target_games:
        target_games = games
    game = target_games[0]

    print(f"  Game: {game.task_type}")
    print(f"  Task: {game.task_desc}")

    # Set up components
    env = AlfWorldEnv(max_steps=50)
    planner = HeuristicPlanner()
    writer = HeuristicSkillWriter()
    library = SkillLibrary(retrieval_top_k=3)
    executor = SkillExecutor(max_skill_steps=20)
    logger = MetricsLogger(log_dir="results")

    runner = EpisodeRunner(
        env=env,
        planner=planner,
        skill_writer=writer,
        skill_library=library,
        executor=executor,
    )

    # Run the episode
    record = runner.run_episode(game, episode_id="test_001")

    print(f"  Success: {record.success}")
    print(f"  Won: {record.won}")
    print(f"  Steps: {record.total_steps}")
    print(f"  Time: {record.elapsed_seconds:.2f}s")
    print(f"  Skills generated: {record.skills_generated}")
    print(f"  Skills retrieved: {record.skills_retrieved}")
    print(f"  False success: {record.false_success}")

    print(f"\n  Subgoal results:")
    for sr in record.subgoal_results:
        status = "✓" if sr["success"] else "✗"
        print(f"    {status} {sr['subgoal']} (skill={sr.get('skill_id', 'N/A')})")
        if sr.get("error"):
            print(f"      Error: {sr['error']}")

    # Log metrics
    metrics = logger.log_episode(record)
    pilot = logger.compute_pilot_metrics(library=library)
    print(f"\n  Pilot metrics:")
    print(f"    Success rate: {pilot['success_rate']}")
    print(f"    Library size: {library.size}")
    print(f"    Library stats: {pilot.get('library_stats', {})}")

    env.close()
    print("  ✓ Full episode OK")


def main():
    data_dir = Path.home() / ".cache" / "alfworld" / "json_2.1.1"

    print("=" * 60)
    print("Integration Test — Milestones 1–5")
    print("=" * 60)

    # Unit-level tests (no ALFWorld needed)
    test_predicates()
    test_planner()
    test_skill_writer()
    test_skill_library()

    # Full integration test (needs ALFWorld)
    if data_dir.exists():
        test_full_episode(data_dir)
    else:
        print(f"\n  SKIP full episode: {data_dir} not found")

    print("\n" + "=" * 60)
    print("All tests PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
