"""
skill_writer.py — L2 skill generator.

Generates executable Python skills for individual subgoals. Each skill is
a Python function that interacts with the ALFWorld environment through a
restricted set of allowed actions.

The revised proposal (p. 4):
    "L2 sees full skill code and failure notes for the subgoal at hand."

For Phase 1, L2 operates in "heuristic" mode: it generates deterministic
skills based on the subgoal type, mimicking what ALFWorld's expert agent
does. This validates the pipeline without requiring an LLM.

When mode="llm", L2 will call a local code model to write novel skills.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Optional

from living_skills.planner import Subgoal
from living_skills.skill_library import SkillRecord


# ── Allowed ALFWorld actions ───────────────────────────────────────────────
#
# These are the action verbs the simulator accepts. Generated skills
# may only use these.

ALLOWED_ACTIONS = [
    "go to {recep}",
    "take {obj} from {recep}",
    "put {obj} in/on {recep}",
    "open {recep}",
    "close {recep}",
    "use {lamp}",
    "clean {obj} with {recep}",
    "heat {obj} with {recep}",
    "cool {obj} with {recep}",
    "examine {obj_or_recep}",
    "look",
    "inventory",
]


# ── Heuristic skill templates ─────────────────────────────────────────────
#
# Each template generates a Python function body that uses the env.step()
# API. The function signature is always:
#
#   def skill_fn(env, admissible_commands, **kwargs) -> bool:
#       ...
#       return success
#
# These are deterministic skills that mirror the expert agent's behaviour.

def _make_find_skill(target: str) -> str:
    """Generate a skill that navigates to a receptacle containing the target."""
    return textwrap.dedent(f'''\
    def find_{_safe_name(target)}(env, admissible_commands, **kwargs):
        """Find and go to a location containing: {target}"""
        # Look for 'go to' commands that reference receptacles
        # where the target object might be found
        target = "{target}"

        # First, check if target is already visible
        for cmd in admissible_commands:
            if "take " + target in cmd.lower() or "use " + target in cmd.lower():
                return True  # Already at location with target

        # Try going to receptacles to find the target
        goto_cmds = [c for c in admissible_commands if c.startswith("go to ")]
        for cmd in goto_cmds:
            result = env.step(cmd)
            obs = result.observation.lower()
            if target in obs:
                return True
            # Check if object is in admissible commands after going there
            for ac in result.admissible_commands:
                if target in ac.lower():
                    return True

        return False
    ''')


def _make_take_skill(obj: str) -> str:
    """Generate a skill that picks up an object."""
    return textwrap.dedent(f'''\
    def take_{_safe_name(obj)}(env, admissible_commands, **kwargs):
        """Take the {obj} from its current location."""
        target = "{obj}"

        # Find the 'take' command for this object
        for cmd in admissible_commands:
            if cmd.lower().startswith("take ") and target in cmd.lower():
                result = env.step(cmd)
                if "pick up" in result.observation.lower() or "you pick" in result.observation.lower():
                    return True
                return not ("nothing" in result.observation.lower() or "can\\'t" in result.observation.lower())

        return False
    ''')


def _make_put_skill(obj: str, recep: str) -> str:
    """Generate a skill that puts an object in/on a receptacle."""
    return textwrap.dedent(f'''\
    def put_{_safe_name(obj)}_in_{_safe_name(recep)}(env, admissible_commands, **kwargs):
        """Put the {obj} in/on the {recep}."""
        target_obj = "{obj}"
        target_recep = "{recep}"

        # Check if we need to open the receptacle first
        for cmd in admissible_commands:
            if cmd.lower().startswith("open ") and target_recep in cmd.lower():
                env.step(cmd)
                break

        # Find the 'put' command
        for cmd in admissible_commands:
            if cmd.lower().startswith("put ") and target_obj in cmd.lower():
                result = env.step(cmd)
                if "put" in result.observation.lower() or "you put" in result.observation.lower():
                    return True
                return not ("nothing" in result.observation.lower() or "can\\'t" in result.observation.lower())

        return False
    ''')


def _make_heat_skill(obj: str) -> str:
    """Generate a skill that heats an object in the microwave."""
    return textwrap.dedent(f'''\
    def heat_{_safe_name(obj)}(env, admissible_commands, **kwargs):
        """Heat the {obj} using the microwave."""
        target = "{obj}"

        # Open microwave if needed
        for cmd in admissible_commands:
            if "open" in cmd.lower() and "microwave" in cmd.lower():
                env.step(cmd)
                break

        # Put object in microwave if we're holding it
        for cmd in admissible_commands:
            if cmd.lower().startswith("put ") and target in cmd.lower() and "microwave" in cmd.lower():
                env.step(cmd)
                break

        # Heat the object
        for cmd in admissible_commands:
            if cmd.lower().startswith("heat ") and target in cmd.lower():
                result = env.step(cmd)
                return "heat" in result.observation.lower() or "you heat" in result.observation.lower()

        return False
    ''')


def _make_cool_skill(obj: str) -> str:
    """Generate a skill that cools an object in the fridge."""
    return textwrap.dedent(f'''\
    def cool_{_safe_name(obj)}(env, admissible_commands, **kwargs):
        """Cool the {obj} using the fridge."""
        target = "{obj}"

        # Open fridge if needed
        for cmd in admissible_commands:
            if "open" in cmd.lower() and "fridge" in cmd.lower():
                env.step(cmd)
                break

        # Put object in fridge if we're holding it
        for cmd in admissible_commands:
            if cmd.lower().startswith("put ") and target in cmd.lower() and "fridge" in cmd.lower():
                env.step(cmd)
                break

        # Cool the object
        for cmd in admissible_commands:
            if cmd.lower().startswith("cool ") and target in cmd.lower():
                result = env.step(cmd)
                return "cool" in result.observation.lower() or "you cool" in result.observation.lower()

        return False
    ''')


def _make_clean_skill(obj: str) -> str:
    """Generate a skill that cleans an object in the sink."""
    return textwrap.dedent(f'''\
    def clean_{_safe_name(obj)}(env, admissible_commands, **kwargs):
        """Clean the {obj} using the sink."""
        target = "{obj}"

        # Clean the object
        for cmd in admissible_commands:
            if cmd.lower().startswith("clean ") and target in cmd.lower():
                result = env.step(cmd)
                return "clean" in result.observation.lower() or "you clean" in result.observation.lower()

        return False
    ''')


def _make_toggle_skill(obj: str) -> str:
    """Generate a skill that toggles an object (e.g., turns on a lamp)."""
    return textwrap.dedent(f'''\
    def toggle_{_safe_name(obj)}(env, admissible_commands, **kwargs):
        """Turn on/toggle the {obj}."""
        target = "{obj}"

        for cmd in admissible_commands:
            if cmd.lower().startswith("use ") and target in cmd.lower():
                result = env.step(cmd)
                if "turn" in result.observation.lower() or "you turn" in result.observation.lower():
                    return True
                return not ("nothing" in result.observation.lower() or "can\\'t" in result.observation.lower())

        return False
    ''')


def _make_open_skill(recep: str) -> str:
    """Generate a skill that opens a receptacle."""
    return textwrap.dedent(f'''\
    def open_{_safe_name(recep)}(env, admissible_commands, **kwargs):
        """Open the {recep}."""
        target = "{recep}"

        for cmd in admissible_commands:
            if cmd.lower().startswith("open ") and target in cmd.lower():
                result = env.step(cmd)
                return "open" in result.observation.lower() or "you open" in result.observation.lower()

        return False
    ''')


_SKILL_GENERATORS = {
    "find": lambda sg: _make_find_skill(sg.target),
    "take": lambda sg: _make_take_skill(sg.target),
    "put": lambda sg: _make_put_skill(sg.target, sg.secondary),
    "heat": lambda sg: _make_heat_skill(sg.target),
    "cool": lambda sg: _make_cool_skill(sg.target),
    "clean": lambda sg: _make_clean_skill(sg.target),
    "toggle": lambda sg: _make_toggle_skill(sg.target),
    "open": lambda sg: _make_open_skill(sg.target),
}


# ── Heuristic skill writer ────────────────────────────────────────────────

class HeuristicSkillWriter:
    """
    Deterministic L2 skill generator for Phase 1 pilot.

    Generates skills from templates based on the subgoal type.
    """

    def generate(
        self,
        subgoal: Subgoal,
        failure_notes: Optional[list[str]] = None,
        existing_skills: Optional[list[SkillRecord]] = None,
    ) -> SkillRecord:
        """
        Generate a skill for the given subgoal.

        Args:
            subgoal: The subgoal to generate a skill for.
            failure_notes: Notes from previous failures (for repair; ignored in Phase 1).
            existing_skills: Existing skills to consider (for dedup; ignored in Phase 1).

        Returns:
            A new SkillRecord with the generated code.
        """
        generator = _SKILL_GENERATORS.get(subgoal.action)
        if generator is None:
            raise ValueError(
                f"No skill template for subgoal action: '{subgoal.action}'. "
                f"Known actions: {sorted(_SKILL_GENERATORS.keys())}"
            )

        body = generator(subgoal)
        signature = subgoal.signature()
        description = str(subgoal)

        # Build pre/postcondition specs from subgoal templates
        preconditions = _get_condition_specs(subgoal, "preconditions")
        postconditions = _get_condition_specs(subgoal, "postconditions")

        return SkillRecord(
            id="",  # will be assigned by the library
            signature=signature,
            description=description,
            preconditions=preconditions,
            postconditions=postconditions,
            body=body,
        )


def _get_condition_specs(subgoal: Subgoal, phase: str) -> list[str]:
    """Build condition specification strings for a subgoal."""
    from living_skills.predicates import get_subgoal_conditions
    try:
        kwargs = {"obj": subgoal.target}
        if subgoal.secondary:
            kwargs["recep"] = subgoal.secondary
        cond_set = get_subgoal_conditions(subgoal.action, phase, **kwargs)
        return [str(p) for p in cond_set.predicates]
    except (ValueError, TypeError):
        return []


# ── LLM-based skill writer stub ───────────────────────────────────────────

class LLMSkillWriter:
    """
    LLM-based L2 skill generator. Calls a local code model.

    Not implemented in Phase 1; will be added when LLM serving is set up.
    """

    def __init__(self, model: str, temperature: float = 0.2, max_tokens: int = 1024):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        subgoal: Subgoal,
        failure_notes: Optional[list[str]] = None,
        existing_skills: Optional[list[SkillRecord]] = None,
    ) -> SkillRecord:
        raise NotImplementedError(
            "LLM skill writer is not yet implemented. "
            "Use HeuristicSkillWriter for the pilot."
        )


# ── Factory ────────────────────────────────────────────────────────────────

def create_skill_writer(mode: str = "heuristic", **kwargs):
    """Create a skill writer based on the configuration mode."""
    if mode == "heuristic":
        return HeuristicSkillWriter()
    elif mode == "llm":
        return LLMSkillWriter(**kwargs)
    else:
        raise ValueError(f"Unknown skill writer mode: '{mode}'")


# ── Utilities ──────────────────────────────────────────────────────────────

def _safe_name(s: str) -> str:
    """Convert a string to a valid Python identifier fragment."""
    import re
    s = re.sub(r"[^a-z0-9]", "_", s.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"
