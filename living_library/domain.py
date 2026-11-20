"""The only contract vocabulary. Hidden simulator facts never enter model prompts."""
from dataclasses import dataclass, field
import re
from typing import Protocol


ARITY = {"exists": 1, "findable": 1, "holding": 1, "located": 2, "at": 1,
         "is_open": 1, "is_hot": 1, "is_cold": 1, "is_clean": 1,
         "is_on": 1, "is_toggled": 1, "task_won": 0}


@dataclass(frozen=True)
class Predicate:
    name: str
    args: tuple[str, ...] = ()

    def __post_init__(self):
        if self.name not in ARITY or len(self.args) != ARITY[self.name]:
            raise ValueError(f"unknown predicate or wrong arity: {self.name}{self.args}")
        if any(not isinstance(x, str) or not x for x in self.args):
            raise ValueError("predicate arguments must be nonempty strings")

    @classmethod
    def parse(cls, text):
        match = re.fullmatch(r"([a-z_]+)\(([^()]*)\)", text.strip())
        if not match:
            raise ValueError(f"invalid predicate: {text}")
        return cls(match[1], tuple(x.strip() for x in match[2].split(",")) if match[2] else ())

    def bind(self, bindings):
        return Predicate(self.name, tuple(bindings.get(a, a) for a in self.args))

    def __str__(self):
        return f"{self.name}({', '.join(self.args)})"


@dataclass
class State:
    observation: str
    admissible: list[str]
    entities: set[str]
    facts: set[tuple[str, ...]] = field(default_factory=set)
    won: bool = False
    done: bool = False

    # Arguments may name an instance ("mug 1") or, before any instance is observed, a type ("mug"),
    # which matches every instance of that type. ALFWorld goals name types, not instances.
    def instances(self, value):
        if value in self.entities:
            return [value]
        return sorted(e for e in self.entities
                      if e.rsplit(" ", 1)[0] == value and e.rsplit(" ", 1)[-1].isdigit())

    def resolves(self, value):
        return bool(self.instances(value))

    def holds(self, predicate):
        if predicate.name == "task_won":
            return self.won
        if predicate.name in {"exists", "findable"}:
            return self.resolves(predicate.args[0])
        if (predicate.name, *predicate.args) in self.facts:
            return True
        options = [self.instances(a) or [a] for a in predicate.args]
        return any(f[0] == predicate.name and len(f) == len(options) + 1
                   and all(x in o for x, o in zip(f[1:], options)) for f in self.facts)

    def check(self, conditions, bindings=None):
        return all(self.holds(Predicate.parse(p).bind(bindings or {})) for p in conditions)

    def public(self):
        return {"observation": self.observation, "admissible_commands": self.admissible}


class Environment(Protocol):
    state: State

    def reset(self, task: dict) -> State: ...
    def step(self, command: str) -> State: ...
    def snapshot(self) -> dict: ...
    def restore(self, snapshot: dict) -> State: ...
    def close(self) -> None: ...


class ActionError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class Episode:
    def __init__(self, env, budget):
        self.env, self.budget = env, budget
        self.trace = []

    def act(self, command):
        if len(self.trace) >= self.budget:
            raise BudgetExceeded("episode action budget exhausted")
        if self.env.state.done:
            raise ActionError("episode already ended")
        before = self.env.state.observation
        valid = command in self.env.state.admissible
        # Invalid commands count, but need not enter an external simulator.
        if valid:
            self.env.step(command)
        self.trace.append({"action": command, "valid": valid, "before": before,
                           "after": self.env.state.observation})
        if not valid:
            raise ActionError(f"inadmissible command: {command}")
        return self.env.state.observation
