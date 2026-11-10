"""
predicates.py — Simulator-grounded predicate checking.

Provides a fixed set of predicates that can be evaluated against ALFWorld's
PDDL state (available as facts from the TextWorld engine). Pre/postconditions
come ONLY from this list, so the planner can't grade itself with vague
conditions.

Following the revised proposal (p. 4):
    "Pre- and postconditions come only from a fixed list of predicates
     the simulator can check."
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ── Fixed predicate catalogue ──────────────────────────────────────────────
#
# Each predicate maps to a pattern that is matched against the list of
# PDDL fact strings extracted from the TextWorld engine.
#
# Fact strings look like:
#   "holds agent apple 1"
#   "inReceptacle apple 1 fridge 1"
#   "isHot egg 2"
#   "atLocation agent loc 5"
#   "isToggled desklamp 1"
#   "opened fridge 1"
#
# We strip trailing digits for matching when `strip_ids=True`.

PREDICATE_CATALOGUE = {
    # Agent state
    "holds":          "holds agent {obj}",
    "holdsAny":       "holdsAny agent",

    # Object location / containment
    "inReceptacle":   "inReceptacle {obj} {recep}",
    "atLocation":     "atLocation agent {loc}",

    # Object properties
    "isHot":          "isHot {obj}",
    "isCool":         "isCool {obj}",
    "isClean":        "isClean {obj}",
    "isToggled":      "isToggled {obj}",
    "isSliced":       "isSliced {obj}",
    "isOn":           "isOn {obj}",

    # Receptacle state
    "opened":         "opened {recep}",
    "checked":        "checked {recep}",

    # Object affordances (static, but useful for preconditions)
    "openable":       "openable {recep}",
    "pickupable":     "pickupable {obj}",
    "heatable":       "heatable {obj}",
    "coolable":       "coolable {obj}",
    "cleanable":      "cleanable {obj}",
    "toggleable":     "toggleable {obj}",
    "sliceable":      "sliceable {obj}",
}


@dataclass
class Predicate:
    """
    A grounded predicate that can be evaluated against simulator facts.

    Examples:
        Predicate("holds", {"obj": "apple"})
        Predicate("isHot", {"obj": "egg"})
        Predicate("inReceptacle", {"obj": "cup", "recep": "shelf"})
    """
    name: str
    bindings: dict[str, str]
    negated: bool = False

    def to_pattern(self) -> str:
        """Generate the fact-string pattern for matching."""
        if self.name not in PREDICATE_CATALOGUE:
            raise ValueError(
                f"Unknown predicate '{self.name}'. "
                f"Valid predicates: {sorted(PREDICATE_CATALOGUE.keys())}"
            )
        template = PREDICATE_CATALOGUE[self.name]
        try:
            return template.format(**self.bindings)
        except KeyError as e:
            raise ValueError(
                f"Missing binding {e} for predicate '{self.name}'. "
                f"Template: '{template}', given: {self.bindings}"
            )

    def evaluate(self, facts: list[str]) -> bool:
        """
        Check whether this predicate holds in the given fact list.

        Uses substring matching with stripped numeric IDs to handle
        ALFWorld's numbered entity instances (e.g., "apple 1", "fridge 2").
        Also handles TextWorld's 'not_' fact prefixes.
        """
        pattern = self.to_pattern().lower()
        pattern_stripped = _strip_numeric_ids(pattern)

        positive_found = False
        negative_found = False

        for fact in facts:
            fact_lower = fact.lower().strip()
            is_negated_fact = fact_lower.startswith("not_")
            cleaned_fact = fact_lower[4:] if is_negated_fact else fact_lower
            fact_stripped = _strip_numeric_ids(cleaned_fact)

            if pattern in cleaned_fact or pattern_stripped in fact_stripped:
                if is_negated_fact:
                    negative_found = True
                else:
                    positive_found = True

        if self.negated:
            return (not positive_found) or negative_found
        else:
            return positive_found and not negative_found

    def __str__(self):
        prefix = "NOT " if self.negated else ""
        args = ", ".join(f"{k}={v}" for k, v in self.bindings.items())
        return f"{prefix}{self.name}({args})"


# ── Condition sets ─────────────────────────────────────────────────────────

@dataclass
class ConditionSet:
    """A conjunction of predicates (all must hold)."""
    predicates: list[Predicate]

    def evaluate(self, facts: list[str]) -> tuple[bool, list[str]]:
        """
        Evaluate all predicates.

        Returns:
            (all_hold, list of failure messages for predicates that didn't hold)
        """
        failures = []
        for pred in self.predicates:
            if not pred.evaluate(facts):
                failures.append(f"  {'MISSING' if not pred.negated else 'PRESENT'}: {pred}")

        return len(failures) == 0, failures

    def __str__(self):
        return " AND ".join(str(p) for p in self.predicates)


# ── Parsing helpers ────────────────────────────────────────────────────────

def parse_predicate(spec: str) -> Predicate:
    """
    Parse a predicate specification string.

    Formats:
        "holds(obj=apple)"
        "NOT isHot(obj=egg)"
        "inReceptacle(obj=cup, recep=shelf)"

    Returns:
        A Predicate instance.
    """
    spec = spec.strip()
    negated = False
    if spec.upper().startswith("NOT "):
        negated = True
        spec = spec[4:].strip()

    # Match "name(key=val, key=val, ...)"
    match = re.match(r"(\w+)\(([^)]*)\)", spec)
    if not match:
        # Try simple "name" with no args (e.g., "holdsAny")
        if spec in PREDICATE_CATALOGUE:
            return Predicate(name=spec, bindings={}, negated=negated)
        raise ValueError(f"Cannot parse predicate: '{spec}'")

    name = match.group(1)
    args_str = match.group(2).strip()

    bindings = {}
    if args_str:
        for pair in args_str.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                bindings[k.strip()] = v.strip()
            else:
                raise ValueError(f"Expected key=value in predicate args, got: '{pair}'")

    return Predicate(name=name, bindings=bindings, negated=negated)


def parse_conditions(specs: list[str]) -> ConditionSet:
    """Parse a list of predicate specification strings into a ConditionSet."""
    return ConditionSet([parse_predicate(s) for s in specs])


# ── Task-type predicate templates ──────────────────────────────────────────
#
# These define the standard postconditions for each ALFWorld task type,
# grounded by the task's pddl_params.

def get_task_postconditions(task_type: str, pddl_params: dict) -> ConditionSet:
    """
    Return the postconditions that must hold when a task is complete.

    These are derived from ALFWorld's task semantics and the expert agent's
    completion checks.
    """
    obj = pddl_params.get("object_target", "").lower()
    parent = pddl_params.get("parent_target", "").lower()
    toggle = pddl_params.get("toggle_target", "").lower()

    conditions = {
        "pick_and_place_simple": [
            Predicate("inReceptacle", {"obj": obj, "recep": parent}),
        ],
        "look_at_obj_in_light": [
            Predicate("holds", {"obj": obj}),
            Predicate("isToggled", {"obj": toggle}),
        ],
        "pick_heat_then_place_in_recep": [
            Predicate("isHot", {"obj": obj}),
            Predicate("inReceptacle", {"obj": obj, "recep": parent}),
        ],
        "pick_cool_then_place_in_recep": [
            Predicate("isCool", {"obj": obj}),
            Predicate("inReceptacle", {"obj": obj, "recep": parent}),
        ],
        "pick_clean_then_place_in_recep": [
            Predicate("isClean", {"obj": obj}),
            Predicate("inReceptacle", {"obj": obj, "recep": parent}),
        ],
        "pick_two_obj_and_place": [
            # For pick_two, we need two instances in the receptacle.
            # The postcondition check uses the 'won' flag as the primary
            # signal, since the exact object IDs vary.
            Predicate("inReceptacle", {"obj": obj, "recep": parent}),
        ],
    }

    preds = conditions.get(task_type, [])
    if not preds:
        raise ValueError(f"Unknown task type: {task_type}")

    return ConditionSet(preds)


# ── Subgoal predicate templates ────────────────────────────────────────────
#
# Standard subgoal pre/postconditions, used by L1 planner output.

SUBGOAL_TEMPLATES = {
    "find": {
        "preconditions": [],
        "postconditions": lambda obj, **_: [
            # Object is visible at current location (checked via admissible commands)
        ],
    },
    "take": {
        "preconditions": [],
        "postconditions": lambda obj, **_: [
            Predicate("holds", {"obj": obj}),
        ],
    },
    "put": {
        "preconditions": lambda obj, **_: [
            Predicate("holds", {"obj": obj}),
        ],
        "postconditions": lambda obj, recep, **_: [
            Predicate("inReceptacle", {"obj": obj, "recep": recep}),
            Predicate("holds", {"obj": obj}, negated=True),
        ],
    },
    "heat": {
        "preconditions": lambda obj, **_: [
            Predicate("holds", {"obj": obj}),
        ],
        "postconditions": lambda obj, **_: [
            Predicate("isHot", {"obj": obj}),
        ],
    },
    "cool": {
        "preconditions": lambda obj, **_: [
            Predicate("holds", {"obj": obj}),
        ],
        "postconditions": lambda obj, **_: [
            Predicate("isCool", {"obj": obj}),
        ],
    },
    "clean": {
        "preconditions": lambda obj, **_: [
            Predicate("holds", {"obj": obj}),
        ],
        "postconditions": lambda obj, **_: [
            Predicate("isClean", {"obj": obj}),
        ],
    },
    "toggle": {
        "preconditions": [],
        "postconditions": lambda obj, **_: [
            Predicate("isToggled", {"obj": obj}),
        ],
    },
    "open": {
        "preconditions": [],
        "postconditions": lambda recep, **_: [
            Predicate("opened", {"recep": recep}),
        ],
    },
}


def get_subgoal_conditions(
    subgoal_type: str,
    phase: str,
    **kwargs,
) -> ConditionSet:
    """
    Get pre- or postconditions for a standard subgoal type.

    Args:
        subgoal_type: One of the keys in SUBGOAL_TEMPLATES.
        phase: 'preconditions' or 'postconditions'.
        **kwargs: Bindings like obj='apple', recep='shelf'.

    Returns:
        ConditionSet for the requested phase.
    """
    if subgoal_type not in SUBGOAL_TEMPLATES:
        return ConditionSet([])

    template = SUBGOAL_TEMPLATES[subgoal_type]
    cond_spec = template.get(phase, [])

    if callable(cond_spec):
        predicates = cond_spec(**kwargs)
    else:
        predicates = list(cond_spec)

    return ConditionSet(predicates)


# ── Utilities ──────────────────────────────────────────────────────────────

def _strip_numeric_ids(s: str) -> str:
    """Remove numeric IDs from entity names (e.g., 'apple 1' -> 'apple', 'agent1' -> 'agent')."""
    return " ".join(re.sub(r"\d+", "", s).split())


def check_won(facts: list[str]) -> bool:
    """Check if the 'won' fact is present (TextWorld's own completion signal)."""
    for fact in facts:
        if "won" in fact.lower():
            return True
    return False
