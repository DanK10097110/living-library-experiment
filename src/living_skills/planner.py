"""
planner.py — L1 high-level planner.

Decomposes a household task into an ordered sequence of subgoals.

The revised proposal (p. 4):
    "L1 sees only skill names and signatures; L2 sees full skill code
     and failure notes for the subgoal at hand."

For the Phase 1 pilot, L1 operates in "heuristic" mode: it uses the task
type and PDDL parameters to produce a deterministic subgoal sequence that
mirrors ALFWorld's expert agent decomposition. This lets us validate the
full pipeline without requiring a running LLM.

When mode="llm", L1 will call a local model to decompose novel tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Subgoal:
    """A single subgoal produced by the L1 planner."""
    action: str        # e.g., "find", "take", "heat", "put", "toggle"
    target: str        # primary object or receptacle
    secondary: str = ""  # secondary argument (e.g., receptacle for "put")
    description: str = ""  # human-readable description

    def signature(self) -> str:
        """Return a canonical signature for skill matching."""
        parts = [self.action, self.target]
        if self.secondary:
            parts.append(self.secondary)
        return "_".join(parts)

    def __str__(self):
        if self.description:
            return self.description
        if self.secondary:
            return f"{self.action}({self.target}, {self.secondary})"
        return f"{self.action}({self.target})"


@dataclass
class Plan:
    """A sequence of subgoals produced by the L1 planner."""
    task_desc: str
    task_type: str
    subgoals: list[Subgoal]

    def __str__(self):
        lines = [f"Plan for: {self.task_desc}"]
        for i, sg in enumerate(self.subgoals, 1):
            lines.append(f"  {i}. {sg}")
        return "\n".join(lines)


# ── Heuristic planner ──────────────────────────────────────────────────────
#
# Mirrors the subgoal decomposition from ALFWorld's handcoded expert
# (see alfworld/agents/expert/handcoded_expert.py). This produces
# deterministic plans that are known to be solvable.

_TASK_SUBGOALS = {
    "pick_and_place_simple": lambda p: [
        Subgoal("find", p["object_target"],
                description=f"Find the {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the {p['object_target']}"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']}"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the {p['object_target']} in/on the {p['parent_target']}"),
    ],

    "look_at_obj_in_light": lambda p: [
        Subgoal("find", p["object_target"],
                description=f"Find the {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the {p['object_target']}"),
        Subgoal("find", p["toggle_target"],
                description=f"Find the {p['toggle_target']}"),
        Subgoal("toggle", p["toggle_target"],
                description=f"Turn on the {p['toggle_target']}"),
    ],

    "pick_heat_then_place_in_recep": lambda p: [
        Subgoal("find", p["object_target"],
                description=f"Find the {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the {p['object_target']}"),
        Subgoal("find", "microwave",
                description="Go to the microwave"),
        Subgoal("heat", p["object_target"], "microwave",
                description=f"Heat the {p['object_target']} in the microwave"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']}"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the {p['object_target']} in/on the {p['parent_target']}"),
    ],

    "pick_cool_then_place_in_recep": lambda p: [
        Subgoal("find", p["object_target"],
                description=f"Find the {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the {p['object_target']}"),
        Subgoal("find", "fridge",
                description="Go to the fridge"),
        Subgoal("cool", p["object_target"], "fridge",
                description=f"Cool the {p['object_target']} in the fridge"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']}"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the {p['object_target']} in/on the {p['parent_target']}"),
    ],

    "pick_clean_then_place_in_recep": lambda p: [
        Subgoal("find", p["object_target"],
                description=f"Find the {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the {p['object_target']}"),
        Subgoal("find", "sinkbasin",
                description="Go to the sink"),
        Subgoal("clean", p["object_target"], "sinkbasin",
                description=f"Clean the {p['object_target']} in the sink"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']}"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the {p['object_target']} in/on the {p['parent_target']}"),
    ],

    "pick_two_obj_and_place": lambda p: [
        # First object
        Subgoal("find", p["object_target"],
                description=f"Find the first {p['object_target']}"),
        Subgoal("take", p["object_target"],
                description=f"Take the first {p['object_target']}"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']}"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the first {p['object_target']} in/on the {p['parent_target']}"),
        # Second object
        Subgoal("find", p["object_target"], secondary=p["parent_target"],
                description=f"Find the second {p['object_target']}"),
        Subgoal("take", p["object_target"], secondary=p["parent_target"],
                description=f"Take the second {p['object_target']}"),
        Subgoal("find", p["parent_target"],
                description=f"Find the {p['parent_target']} again"),
        Subgoal("put", p["object_target"], p["parent_target"],
                description=f"Put the second {p['object_target']} in/on the {p['parent_target']}"),
    ],
}


class HeuristicPlanner:
    """
    Deterministic L1 planner based on ALFWorld's task-type structure.

    Uses the task type and PDDL parameters to produce a fixed subgoal
    decomposition. This mirrors the expert agent and is used during the
    pilot to validate the pipeline without needing an LLM.
    """

    def plan(
        self,
        task_desc: str,
        task_type: str,
        pddl_params: dict,
    ) -> Plan:
        """
        Decompose a task into subgoals.

        Args:
            task_desc: Human-readable task description.
            task_type: ALFWorld task type string.
            pddl_params: Task parameters (object_target, parent_target, etc.).

        Returns:
            A Plan with ordered subgoals.
        """
        # Normalize params to lowercase
        params = {k: v.lower() for k, v in pddl_params.items() if isinstance(v, str)}

        if task_type not in _TASK_SUBGOALS:
            raise ValueError(
                f"Unknown task type: '{task_type}'. "
                f"Known types: {sorted(_TASK_SUBGOALS.keys())}"
            )

        subgoals = _TASK_SUBGOALS[task_type](params)
        return Plan(
            task_desc=task_desc,
            task_type=task_type,
            subgoals=subgoals,
        )


# ── LLM-based planner stub ────────────────────────────────────────────────

class LLMPlanner:
    """
    LLM-based L1 planner. Calls a local model to decompose tasks.

    Not implemented in Phase 1; will be added when LLM serving is set up.
    """

    def __init__(self, model: str, temperature: float = 0.3, max_tokens: int = 512):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def plan(
        self,
        task_desc: str,
        task_type: str,
        pddl_params: dict,
    ) -> Plan:
        raise NotImplementedError(
            "LLM planner is not yet implemented. "
            "Use HeuristicPlanner for the pilot."
        )


# ── Factory ────────────────────────────────────────────────────────────────

def create_planner(mode: str = "heuristic", **kwargs) -> HeuristicPlanner | LLMPlanner:
    """Create a planner instance based on the configuration mode."""
    if mode == "heuristic":
        return HeuristicPlanner()
    elif mode == "llm":
        return LLMPlanner(**kwargs)
    else:
        raise ValueError(f"Unknown planner mode: '{mode}'")
