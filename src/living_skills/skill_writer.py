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

def _make_find_skill(target: str, exclude_recep: str = "") -> str:
    """Generate a skill that navigates to a location containing target (object or receptacle)."""
    return textwrap.dedent(f'''\
    def find_{_safe_name(target)}(env, admissible_commands=None, **kwargs):
        """Find and navigate to target: {target}"""
        target = "{target}".lower()
        exclude = "{exclude_recep}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        # If target is already accessible right here (takeable or usable)
        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if not cmd_l.startswith("go to ") and target in tokens:
                if exclude and f"from {{exclude}}" in cmd_l:
                    continue
                return True

        # If target is a receptacle itself (e.g., 'desk', 'shelf', 'microwave', 'fridge', 'sinkbasin')
        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if cmd_l.startswith("go to ") and target in tokens:
                res = env.step(cmd)
                return True

        # Otherwise target is an object; search across receptacles
        goto_cmds = [c for c in commands if c.lower().startswith("go to ")]
        for cmd in goto_cmds:
            if exclude and f"go to {{exclude}}" in cmd.lower():
                continue
            res = env.step(cmd)
            obs_l = res.observation.lower()
            for ac in res.admissible_commands:
                ac_l = ac.lower()
                ac_tokens = ac_l.replace('.', ' ').replace(',', ' ').split()
                if not ac_l.startswith("go to ") and target in ac_tokens:
                    if exclude and f"from {{exclude}}" in ac_l:
                        continue
                    return True
            if target in obs_l.replace('.', ' ').replace(',', ' ').split():
                return True

            open_cmds = [c for c in res.admissible_commands if c.lower().startswith("open ")]
            for o_cmd in open_cmds:
                o_res = env.step(o_cmd)
                for ac in o_res.admissible_commands:
                    ac_l = ac.lower()
                    ac_tokens = ac_l.replace('.', ' ').replace(',', ' ').split()
                    if not ac_l.startswith("go to ") and target in ac_tokens:
                        if exclude and f"from {{exclude}}" in ac_l:
                            continue
                        return True
                if target in o_res.observation.lower().replace('.', ' ').replace(',', ' ').split():
                    return True

        return False
    ''')


def _make_take_skill(obj: str, exclude_recep: str = "") -> str:
    """Generate a skill that picks up an object."""
    return textwrap.dedent(f'''\
    def take_{_safe_name(obj)}(env, admissible_commands=None, **kwargs):
        """Take the {obj} from its current location."""
        target = "{obj}".lower()
        exclude = "{exclude_recep}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        take_cmd = None
        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if cmd_l.startswith("take ") and target in tokens:
                if exclude and f"from {{exclude}}" in cmd_l:
                    continue
                take_cmd = cmd
                break

        if not take_cmd:
            open_cmds = [c for c in commands if c.lower().startswith("open ")]
            for o_cmd in open_cmds:
                if exclude and f" {{exclude}}" in o_cmd.lower():
                    continue
                res = env.step(o_cmd)
                for ac in res.admissible_commands:
                    ac_tokens = ac.lower().replace('.', ' ').replace(',', ' ').split()
                    if ac.lower().startswith("take ") and target in ac_tokens:
                        if exclude and f"from {{exclude}}" in ac.lower():
                            continue
                        take_cmd = ac
                        break
                if take_cmd:
                    break

        if take_cmd:
            res = env.step(take_cmd)
            obs_l = res.observation.lower()
            if "pick up" in obs_l or "you pick" in obs_l or "take" in obs_l:
                return True
            return not ("nothing" in obs_l or "can't" in obs_l)

        return False
    ''')


def _make_put_skill(obj: str, recep: str) -> str:
    """Generate a skill that puts/moves an object in/on a receptacle."""
    return textwrap.dedent(f'''\
    def put_{_safe_name(obj)}_in_{_safe_name(recep)}(env, admissible_commands=None, **kwargs):
        """Put/move the {obj} in/on the {recep}."""
        target_obj = "{obj}".lower()
        target_recep = "{recep}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        # Check if we are already at the target receptacle
        put_cmd = None
        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if (cmd_l.startswith("move ") or cmd_l.startswith("put ")) and target_obj in tokens and target_recep in tokens:
                put_cmd = cmd
                break

        # If not at target receptacle, go there
        if not put_cmd:
            for cmd in commands:
                cmd_l = cmd.lower()
                tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
                if cmd_l.startswith("go to ") and target_recep in tokens:
                    res = env.step(cmd)
                    commands = res.admissible_commands
                    break

        # Check if receptacle needs to be opened
        open_cmds = [c for c in commands if c.lower().startswith("open ") and target_recep in c.lower().replace('.', ' ').replace(',', ' ').split()]
        for o_cmd in open_cmds:
            res = env.step(o_cmd)
            commands = res.admissible_commands

        # Find the put/move command at the target receptacle
        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if (cmd_l.startswith("move ") or cmd_l.startswith("put ")) and target_obj in tokens and target_recep in tokens:
                put_cmd = cmd
                break

        # Fallback if target_recep was generic
        if not put_cmd:
            for cmd in commands:
                cmd_l = cmd.lower()
                tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
                if (cmd_l.startswith("move ") or cmd_l.startswith("put ")) and target_obj in tokens:
                    put_cmd = cmd
                    break

        if put_cmd:
            res = env.step(put_cmd)
            obs_l = res.observation.lower()
            if "move" in obs_l or "put" in obs_l or "place" in obs_l:
                return True
            return not ("nothing" in obs_l or "can't" in obs_l)

        return False
    ''')


def _make_heat_skill(obj: str) -> str:
    """Generate a skill that heats an object using the microwave."""
    return textwrap.dedent(f'''\
    def heat_{_safe_name(obj)}(env, admissible_commands=None, **kwargs):
        """Heat the {obj} using the microwave."""
        target = "{obj}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        for cmd in commands:
            cmd_l = cmd.lower()
            if cmd_l.startswith("go to ") and "microwave" in cmd_l:
                res = env.step(cmd)
                commands = res.admissible_commands
                break

        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if cmd_l.startswith("heat ") and target in tokens:
                res = env.step(cmd)
                return True

        return False
    ''')


def _make_cool_skill(obj: str) -> str:
    """Generate a skill that cools an object using the fridge."""
    return textwrap.dedent(f'''\
    def cool_{_safe_name(obj)}(env, admissible_commands=None, **kwargs):
        """Cool the {obj} using the fridge."""
        target = "{obj}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        for cmd in commands:
            cmd_l = cmd.lower()
            if cmd_l.startswith("go to ") and "fridge" in cmd_l:
                res = env.step(cmd)
                commands = res.admissible_commands
                break

        for cmd in commands:
            cmd_l = cmd.lower()
            tokens = cmd_l.replace('.', ' ').replace(',', ' ').split()
            if cmd_l.startswith("cool ") and target in tokens:
                res = env.step(cmd)
                return True

        return False
    ''')


def _make_clean_skill(obj: str) -> str:
    """Generate a skill that cleans an object using the sink."""
    return textwrap.dedent(f'''\
    def clean_{_safe_name(obj)}(env, admissible_commands=None, **kwargs):
        """Clean the {obj} using the sink."""
        target = "{obj}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        for cmd in commands:
            cmd_l = cmd.lower()
            if cmd_l.startswith("go to ") and ("sink" in cmd_l or "basin" in cmd_l):
                res = env.step(cmd)
                commands = res.admissible_commands
                break

        for cmd in commands:
            if cmd.lower().startswith("clean ") and target in cmd.lower():
                res = env.step(cmd)
                return True

        return False
    ''')


def _make_toggle_skill(obj: str) -> str:
    """Generate a skill that toggles an object (e.g., turns on a lamp)."""
    return textwrap.dedent(f'''\
    def toggle_{_safe_name(obj)}(env, admissible_commands=None, **kwargs):
        """Turn on/toggle the {obj}."""
        target = "{obj}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        for cmd in commands:
            if cmd.lower().startswith("use ") and target in cmd.lower():
                res = env.step(cmd)
                return True

        goto_cmds = [c for c in commands if c.lower().startswith("go to ")]
        for cmd in goto_cmds:
            res = env.step(cmd)
            for ac in res.admissible_commands:
                if ac.lower().startswith("use ") and target in ac.lower():
                    res2 = env.step(ac)
                    return True

        return False
    ''')


def _make_open_skill(recep: str) -> str:
    """Generate a skill that opens a receptacle."""
    return textwrap.dedent(f'''\
    def open_{_safe_name(recep)}(env, admissible_commands=None, **kwargs):
        """Open the {recep}."""
        target = "{recep}".lower()
        commands = env.admissible_commands if hasattr(env, "admissible_commands") else admissible_commands

        for cmd in commands:
            if cmd.lower().startswith("open ") and target in cmd.lower():
                res = env.step(cmd)
                return True

        return False
    ''')


_SKILL_GENERATORS = {
    "find": lambda sg: _make_find_skill(sg.target, sg.secondary),
    "take": lambda sg: _make_take_skill(sg.target, sg.secondary),
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
