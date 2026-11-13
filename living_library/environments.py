"""Deterministic replay for regression tests and explicit split manifests."""
import copy
import json
from pathlib import Path

from .config import digest
from .domain import State


class MiniWorld:
    """A tiny fixture, NOT an ALFWorld substitute or a source of scientific results."""
    def reset(self, task):
        self.task = copy.deepcopy(task)
        self.actions = []
        self.location = "table 1"
        self.object = task.get("object", "apple 1")
        self.target = task.get("target", "cabinet 1")
        self.object_location = "table 1"
        self.open = False
        return self._state()

    def _state(self):
        commands = ["look", "go to table 1", f"go to {self.target}"]
        if self.location == "table 1" and self.object_location == "table 1":
            commands.append(f"take {self.object} from table 1")
        if self.location == self.target:
            if not self.open:
                commands.append(f"open {self.target}")
            elif self.object_location == "inventory":
                commands.append(f"move {self.object} to {self.target}")
        facts = {("at", self.location)}
        if self.open:
            facts.add(("is_open", self.target))
        if self.object_location == "inventory":
            facts.add(("holding", self.object))
        else:
            facts.add(("located", self.object, self.object_location))
        won = self.object_location == self.target
        observation = (f"Task: put {self.object} in {self.target}. At {self.location}. "
                       f"{self.object} is at {self.object_location}. "
                       f"{self.target} is {'open' if self.open else 'closed'}.")
        self.state = State(observation, commands, {self.object, self.target, "table 1"}, facts, won, won)
        return self.state

    def step(self, command):
        if command not in self.state.admissible:
            raise ValueError("invalid fixture command")
        self.actions.append(command)
        if command.startswith("go to "):
            self.location = command[6:]
        elif command.startswith("take "):
            self.object_location = "inventory"
        elif command.startswith("open "):
            self.open = True
        elif command.startswith("move "):
            self.object_location = self.target
        return self._state()

    def snapshot(self):
        return {"task": self.task, "actions": self.actions.copy()}

    def restore(self, snapshot):
        self.reset(snapshot["task"])
        for action in snapshot["actions"]:
            self.step(action)
        return self.state

    def close(self):
        pass


def normalize_alfworld(raw):
    """Map TextWorld's human-readable PDDL facts to the frozen predicate vocabulary."""
    facts = [(p.name.lower(), *(a.name.strip().lower() for a in p.arguments)) for p in raw["facts"]]
    entities = {a.name.strip().lower() for p in raw["facts"] for a in p.arguments
                if a.type in {"object", "receptacle"}}
    mapped = set()
    unary = {"opened": "is_open", "ishot": "is_hot", "iscool": "is_cold",
             "isclean": "is_clean", "ison": "is_on", "istoggled": "is_toggled"}
    for fact in facts:
        name, *args = fact
        if name in unary and len(args) == 1:
            mapped.add((unary[name], args[0]))
        if name in {"inreceptacle", "inreceptacleobject"} and len(args) == 2:
            mapped.add(("located", *args))
        if name == "holds" and len(args) == 2:
            mapped.add(("holding", args[1]))
    locations = {p[2] for p in facts if p[0] == "atlocation" and len(p) == 3}
    for p in facts:
        if p[0] == "receptacleatlocation" and len(p) == 3 and p[2] in locations:
            mapped.add(("at", p[1]))
    won = bool(raw["won"])
    return State(raw["feedback"], list(raw["admissible_commands"]), entities, mapped,
                 won, won or bool(raw.get("lost", False)))


class ALFWorld:
    def __init__(self):
        self.env = None

    def reset(self, task):
        import textworld
        from alfworld.agents.environment.alfred_tw_env import AlfredDemangler
        self.close()
        self.task = copy.deepcopy(task)
        self.actions = []
        path = Path(task["gamefile"])
        if digest(path.read_text()) != task["sha256"]:
            raise ValueError(f"game changed since manifest creation: {path}")
        infos = textworld.EnvInfos(facts=True, won=True, admissible_commands=True)
        # Explicit files avoid implicit shuffled Gym resets and accidental split leakage.
        self.env = textworld.start(str(path), request_infos=infos,
                                   wrappers=[AlfredDemangler(shuffle=False)])
        self.raw_state = self.env.reset()
        self.state = normalize_alfworld(self.raw_state)
        return self.state

    def step(self, command):
        raw, _, done = self.env.step(command)
        self.raw_state = raw
        self.actions.append(command)
        self.state = normalize_alfworld(raw)
        self.state.done = self.state.done or done
        return self.state

    def snapshot(self):
        return {"task": self.task, "actions": self.actions.copy()}

    def restore(self, snapshot):
        self.reset(snapshot["task"])
        for action in snapshot["actions"]:
            self.step(action)
        return self.state

    def close(self):
        if self.env is not None:
            self.env.close()
            self.env = None


def build_manifest(root):
    root = Path(root).resolve()
    splits = {}
    for split, directory in (("practice", "train"), ("development", "valid_seen"),
                             ("evaluation", "valid_unseen")):
        tasks = []
        for path in sorted((root / directory).rglob("game.tw-pddl")):
            if "movable" in str(path) or "Sliced" in str(path):
                continue
            metadata_path = path.parent / "traj_data.json"
            if not metadata_path.exists():
                continue
            metadata = json.loads(metadata_path.read_text())
            if not json.loads(path.read_text()).get("solvable", False):
                continue
            tasks.append({"id": str(path.relative_to(root)), "split": split,
                          "gamefile": str(path), "sha256": digest(path.read_text()),
                          "task_type": metadata["task_type"]})
        if not tasks:
            raise ValueError(f"no solvable games in {root / directory}")
        splits[split] = tasks
    return {"environment": "alfworld", "splits": splits}


def demo_manifest():
    return {"environment": "mini", "splits": {
        split: [{"id": f"{split}-{i}", "split": split, "object": f"apple {i % 2 + 1}",
                 "target": "cabinet 1"} for i in range(6)]
        for split in ("practice", "development", "evaluation")}}


def validate_manifest(manifest):
    if manifest["environment"] not in {"mini", "alfworld"}:
        raise ValueError("unsupported environment; ScienceWorld requires a new validated adapter")
    seen_ids, seen_files, seen_hashes = set(), set(), set()
    for split in ("practice", "development", "evaluation"):
        tasks = manifest["splits"][split]
        if not tasks:
            raise ValueError(f"empty split: {split}")
        for t in tasks:
            if t["split"] != split or t["id"] in seen_ids:
                raise ValueError("duplicate task or incorrect split")
            seen_ids.add(t["id"])
            if "gamefile" in t:
                path = str(Path(t["gamefile"]).resolve())
                if path in seen_files or t["sha256"] in seen_hashes:
                    raise ValueError("duplicate game content/path across manifest")
                seen_files.add(path)
                seen_hashes.add(t["sha256"])
