"""Training-only oracle smoke checks; these are NOT agent performance results."""
import argparse
import copy
import json
from pathlib import Path

from .config import digest, write_json
from .domain import Episode
from .environments import ALFWorld


FAMILIES = (
    "pick_and_place_simple", "pick_clean_then_place_in_recep",
    "pick_heat_then_place_in_recep", "pick_cool_then_place_in_recep",
    "pick_two_obj_and_place", "look_at_obj_in_light",
)


def require(value, message):
    if not value:
        raise AssertionError(message)


def replay(env):
    expected = copy.deepcopy(env.state)
    restored = env.restore(env.snapshot())
    for field in ("facts", "entities", "observation", "won", "done"):
        require(getattr(restored, field) == getattr(expected, field),
                f"Replay differs: {field}")
    require(set(restored.admissible) == set(expected.admissible),
            "Replay differs: admissible commands")


def run_game(game, root, result):
    metadata = json.loads((game.parent / "traj_data.json").read_text())
    params = metadata["pddl_params"]
    family = metadata["task_type"]
    task = {"id": str(game.relative_to(root)), "split": "practice",
            "gamefile": str(game), "sha256": digest(game.read_text())}
    result["task"] = task["id"]
    env = ALFWorld()
    episode = Episode(env, 100)
    result["trace"] = episode.trace
    try:
        env.reset(task)
        require(not env.state.won, "Task already won at reset")

        def check(predicate):
            require(env.state.check([predicate]), f"Missing fact: {predicate}")

        def act(command):
            require(command in env.state.admissible,
                    f"Unavailable: {command}; allowed: {env.state.admissible}")
            episode.act(command)

        def names(kind):
            # Hidden facts are deliberately used by this diagnostic oracle.
            all_names = {x for f in env.state.facts for x in f[1:]}
            all_names.update(env.state.entities)
            return sorted(x for x in all_names
                          if x.rsplit(" ", 1)[0] == kind.lower())

        def location(obj):
            return next(f[2] for f in sorted(env.state.facts)
                        if f[0] == "located" and f[1] == obj)

        def go(target):
            act(f"go to {target}")
            check(f"at({target})")

        def open_if_needed(target):
            command = f"open {target}"
            if command in env.state.admissible:
                act(command)
                check(f"is_open({target})")

        objects = names(params["object_target"])
        count = 2 if family == "pick_two_obj_and_place" else 1
        require(len(objects) >= count, "Not enough target object instances")
        objects = objects[:count]

        for index, obj in enumerate(objects):
            source = location(obj)
            go(source)
            open_if_needed(source)
            act(f"take {obj} from {source}")
            check(f"holding({obj})")
            require(not env.state.check([f"located({obj}, {source})"]),
                    "Object still located at source after taking")
            replay(env)  # Replay a nonterminal state, as repairs need to do.

            treatments = {
                "pick_clean_then_place_in_recep": ("clean", "sinkbasin", "is_clean"),
                "pick_heat_then_place_in_recep": ("heat", "microwave", "is_hot"),
                "pick_cool_then_place_in_recep": ("cool", "fridge", "is_cold"),
            }
            if family in treatments:
                verb, appliance, predicate = treatments[family]
                before = {f for f in env.state.facts if f[0] == predicate}
                require((predicate, obj) not in before,
                        f"Selected object already satisfies {predicate}")
                devices = names(appliance)
                require(devices, f"No {appliance} found in normalized facts")
                device = devices[0]
                go(device)
                command = f"{verb} {obj} with {device}"
                if command not in env.state.admissible:
                    open_if_needed(device)
                act(command)
                check(f"{predicate}({obj})")
                after = {f for f in env.state.facts if f[0] == predicate}
                require(after - before == {(predicate, obj)},
                        "Treatment changed facts for unexpected object instances")

            if family == "look_at_obj_in_light":
                lamps = names(params["toggle_target"])
                require(lamps, "No target light found")
                lamp = lamps[0]
                go(location(lamp))
                require(not env.state.check([f"is_toggled({lamp})"]),
                        "Selected lamp already toggled before use")
                act(f"use {lamp}")
                # ALFWorld's goal uses toggle history, not current power state.
                check(f"is_toggled({lamp})")
                check(f"holding({obj})")
            else:
                targets = names(params["parent_target"])
                require(targets, "No destination found")
                target = targets[0]
                go(target)
                open_if_needed(target)
                act(f"move {obj} to {target}")
                check(f"located({obj}, {target})")
                require(not env.state.check([f"holding({obj})"]),
                        "Still holding object after placement")
                if count == 2 and index == 0:
                    require(not env.state.won, "Two-object task won after only one object")

        require(env.state.won, "Simulator did not report victory")
        replay(env)
        result["status"] = "PASS"
    finally:
        if hasattr(env, "state"):
            result["won"] = env.state.won
            result["facts"] = sorted(env.state.facts)
        if hasattr(env, "raw_state"):
            result["raw_facts"] = sorted(str(f) for f in env.raw_state["facts"])
            if family == "look_at_obj_in_light":
                print("Simulator won:", env.state.won, flush=True)
                print("Raw lamp facts:", [f for f in result["raw_facts"]
                                          if "lamp" in f.lower()], flush=True)
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path.home() / ".cache/alfworld/json_2.1.1")
    parser.add_argument("--output", type=Path,
                        default=Path("runs/simulator_checks.json"))
    parser.add_argument("--family", choices=FAMILIES)
    args = parser.parse_args()
    results = []
    for family in ([args.family] if args.family else FAMILIES):
        result = {"family": family, "status": "FAIL"}
        results.append(result)
        try:
            games = sorted((args.root / "train").glob(
                f"{family}-*/trial_*/game.tw-pddl"))
            game = next((p for p in games
                         if "Sliced" not in str(p)
                         and (p.parent / "traj_data.json").exists()
                         and json.loads(p.read_text()).get("solvable")), None)
            require(game is not None, "No matching solvable training game")
            run_game(game, args.root, result)
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"{result['status']}: {family}", flush=True)
        if "error" in result:
            print("  " + result["error"], flush=True)
        write_json(args.output, {"diagnostic_only": True, "results": results})
    passed = sum(r["status"] == "PASS" for r in results)
    print(f"\n{passed}/{len(results)} passed. Details: {args.output}")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
