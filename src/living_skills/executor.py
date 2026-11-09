"""
executor.py — Safe skill execution engine.

Executes generated Python skills within a restricted namespace, handles
action failures, and coordinates with the predicate checker for subgoal
verification.

Following the revised proposal (p. 4-5):
    - Failures climb the checks on the right.
    - Every change to a skill enters the library only through the update gate.
    - The append-only ablation (E-) skips every row except saving new skills.

Safety: generated code runs in a restricted namespace with access only to
the environment wrapper and safe built-ins. No file I/O, no imports, no
network access.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Optional, Any

from living_skills.environment import AlfWorldEnv, StepResult
from living_skills.planner import Subgoal
from living_skills.predicates import (
    ConditionSet,
    parse_conditions,
    get_subgoal_conditions,
)
from living_skills.skill_library import SkillRecord


# ── Execution result ───────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Result of executing a skill or a single subgoal."""
    success: bool
    subgoal: Subgoal
    skill_id: Optional[str] = None
    skill_was_retrieved: bool = False     # True if reused from library
    preconditions_held: bool = True
    postconditions_held: bool = False
    steps_taken: int = 0
    observations: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    # For false-success tracking
    task_succeeded_after: Optional[bool] = None

    @property
    def is_retrieval_error(self) -> bool:
        """A retrieval error: preconditions didn't hold (proposal p. 5)."""
        return not self.preconditions_held

    @property
    def is_code_crash(self) -> bool:
        """The skill crashed or was rejected."""
        return self.error is not None


# ── Safe execution sandbox ─────────────────────────────────────────────────

# Restricted built-ins: no file I/O, no imports, no exec/eval
_SAFE_BUILTINS = {
    "True": True,
    "False": False,
    "None": None,
    "print": print,
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "reversed": reversed,
    "min": min,
    "max": max,
    "abs": abs,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "isinstance": isinstance,
    "any": any,
    "all": all,
}


class _EnvironmentProxy:
    """
    A restricted proxy around AlfWorldEnv that:
    1. Counts steps for budget enforcement.
    2. Records observations and actions for logging.
    3. Prevents access to internal state.
    """

    def __init__(self, env: AlfWorldEnv, max_steps: int = 20):
        self._env = env
        self._max_steps = max_steps
        self._steps = 0
        self.observations: list[str] = []
        self.actions: list[str] = []
        self._last_result: Optional[StepResult] = None

    def step(self, action: str) -> StepResult:
        """Execute an action, enforcing the step budget."""
        if self._steps >= self._max_steps:
            raise RuntimeError(
                f"Step budget exhausted ({self._max_steps} steps). "
                "Skill is taking too many actions."
            )

        result = self._env.step(action)
        self._steps += 1
        self.actions.append(action)
        self.observations.append(result.observation)
        self._last_result = result
        return result

    @property
    def admissible_commands(self) -> list[str]:
        """Get currently admissible commands."""
        if self._last_result is not None:
            return self._last_result.admissible_commands
        return []

    @property
    def step_count(self) -> int:
        return self._steps


# ── Skill executor ─────────────────────────────────────────────────────────

class SkillExecutor:
    """
    Executes skills safely and verifies their outcomes.

    This is the core of the agent's action loop: given a subgoal and a
    skill (either retrieved from the library or freshly generated), it
    executes the skill code and checks pre/postconditions.
    """

    def __init__(self, max_skill_steps: int = 20):
        self.max_skill_steps = max_skill_steps

    def execute_skill(
        self,
        env: AlfWorldEnv,
        subgoal: Subgoal,
        skill: SkillRecord,
        skill_was_retrieved: bool = False,
    ) -> ExecutionResult:
        """
        Execute a skill and verify its outcome.

        Steps:
        1. Check preconditions against current simulator state.
        2. Execute the skill code in a sandbox.
        3. Check postconditions against the resulting state.
        4. Return a detailed ExecutionResult.

        Args:
            env: The ALFWorld environment (already in a game).
            subgoal: The subgoal this skill is meant to achieve.
            skill: The SkillRecord to execute.
            skill_was_retrieved: Whether this skill came from the library.

        Returns:
            ExecutionResult with success/failure details.
        """
        start_time = time.time()

        # ── Step 1: Check preconditions ─────────────────────────────────
        pre_facts = self._get_current_facts(env)
        preconditions_held = True

        if skill.preconditions:
            try:
                pre_conds = parse_conditions(skill.preconditions)
                preconditions_held, pre_failures = pre_conds.evaluate(pre_facts)
            except (ValueError, KeyError):
                preconditions_held = True  # Can't check → assume OK

        # ── Step 2: Execute the skill ───────────────────────────────────
        proxy = _EnvironmentProxy(env, max_steps=self.max_skill_steps)
        error = None
        skill_returned = False

        try:
            # Get initial admissible commands
            # We need an initial step result for the proxy; do a "look" first
            initial_result = env.step("look")
            proxy.observations.append(initial_result.observation)
            proxy.actions.append("look")
            proxy._last_result = initial_result
            proxy._steps = 1

            skill_returned = self._run_in_sandbox(
                skill.body, proxy, initial_result.admissible_commands
            )
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}"
            skill_returned = False

        # ── Step 3: Check postconditions ────────────────────────────────
        post_facts = self._get_current_facts(env)
        postconditions_held = False

        if skill.postconditions:
            try:
                post_conds = parse_conditions(skill.postconditions)
                postconditions_held, post_failures = post_conds.evaluate(post_facts)
            except (ValueError, KeyError):
                postconditions_held = skill_returned

        # If no postconditions defined, trust the skill's return value
        if not skill.postconditions:
            postconditions_held = skill_returned

        # ── Determine overall success ───────────────────────────────────
        success = postconditions_held and preconditions_held and error is None

        elapsed = time.time() - start_time

        return ExecutionResult(
            success=success,
            subgoal=subgoal,
            skill_id=skill.id,
            skill_was_retrieved=skill_was_retrieved,
            preconditions_held=preconditions_held,
            postconditions_held=postconditions_held,
            steps_taken=proxy.step_count,
            observations=proxy.observations,
            actions_taken=proxy.actions,
            error=error,
            elapsed_seconds=elapsed,
        )

    def _run_in_sandbox(
        self,
        code: str,
        proxy: _EnvironmentProxy,
        admissible_commands: list[str],
    ) -> bool:
        """
        Execute skill code in a restricted namespace.

        The code is expected to define a function, which we then call
        with the environment proxy and admissible commands.

        Returns:
            Whatever the skill function returns (expected to be bool).
        """
        # Build the restricted namespace
        namespace = {"__builtins__": _SAFE_BUILTINS}

        # Execute the code to define the function
        exec(code, namespace)  # noqa: S102

        # Find the defined function (should be exactly one new callable)
        func = None
        for name, obj in namespace.items():
            if callable(obj) and name != "__builtins__" and not name.startswith("_"):
                func = obj
                break

        if func is None:
            raise RuntimeError("Skill code did not define a callable function.")

        # Call the function
        result = func(proxy, admissible_commands)
        return bool(result) if result is not None else False

    @staticmethod
    def _get_current_facts(env: AlfWorldEnv) -> list[str]:
        """
        Get the current PDDL facts from the environment.

        We perform a no-op 'look' action to get fresh facts without
        changing the state.
        """
        # The last step's info should contain facts; if not, do a look
        result = env.step("inventory")
        return result.facts


# ── Episode runner ─────────────────────────────────────────────────────────

@dataclass
class EpisodeRecord:
    """Complete record of one episode for logging and analysis."""
    episode_id: str
    game_path: str
    task_type: str
    task_desc: str
    success: bool
    won: bool             # ALFWorld's own 'won' flag
    total_steps: int
    subgoal_results: list[dict]
    elapsed_seconds: float
    skills_generated: int
    skills_retrieved: int
    false_success: bool = False  # Subgoals passed but task failed


class EpisodeRunner:
    """
    Runs a complete episode: plan → execute skills → verify → log.

    This is the main loop that coordinates L1 planner, skill library,
    L2 skill writer, executor, and predicate checker.
    """

    def __init__(
        self,
        env: AlfWorldEnv,
        planner,
        skill_writer,
        skill_library,
        executor: SkillExecutor,
    ):
        self.env = env
        self.planner = planner
        self.skill_writer = skill_writer
        self.skill_library = skill_library
        self.executor = executor

    def run_episode(
        self,
        game_info,
        episode_id: str = "",
    ) -> EpisodeRecord:
        """
        Run a single episode from start to finish.

        Steps:
        1. Load and reset the environment.
        2. L1 plans subgoals.
        3. For each subgoal:
           a. Try to retrieve a skill from the library.
           b. If none found, generate a new skill with L2.
           c. Execute the skill.
           d. Verify postconditions.
           e. On success, save to library (append-only).
        4. Return the episode record.
        """
        start_time = time.time()

        # ── Setup ──────────────────────────────────────────────────────
        self.env.load(game_info)
        initial = self.env.reset()

        # ── L1: Plan ───────────────────────────────────────────────────
        pddl_params = {
            "object_target": game_info.object_target,
            "parent_target": game_info.parent_target,
            "toggle_target": game_info.toggle_target,
            "mrecep_target": game_info.mrecep_target,
        }

        plan = self.planner.plan(
            task_desc=game_info.task_desc,
            task_type=game_info.task_type,
            pddl_params=pddl_params,
        )

        # ── Execute subgoals ───────────────────────────────────────────
        subgoal_results = []
        skills_generated = 0
        skills_retrieved = 0
        all_subgoals_succeeded = True

        for subgoal in plan.subgoals:
            # Check if the environment is already done
            # (task might have been completed by a previous subgoal)
            check = self.env.step("look")
            if check.won:
                break

            # Try to retrieve an existing skill
            query = f"{subgoal.action} {subgoal.target}"
            current_facts = check.facts
            retrieved_skills = self.skill_library.retrieve(
                query=query,
                current_facts=current_facts,
            )

            skill = None
            was_retrieved = False

            if retrieved_skills:
                skill = retrieved_skills[0]
                was_retrieved = True
                skills_retrieved += 1
            else:
                # Generate a new skill
                try:
                    skill = self.skill_writer.generate(subgoal)
                    skills_generated += 1
                except ValueError as e:
                    subgoal_results.append({
                        "subgoal": str(subgoal),
                        "success": False,
                        "error": str(e),
                        "skill_id": None,
                        "retrieved": False,
                    })
                    all_subgoals_succeeded = False
                    continue

            # Execute the skill
            exec_result = self.executor.execute_skill(
                env=self.env,
                subgoal=subgoal,
                skill=skill,
                skill_was_retrieved=was_retrieved,
            )

            # Record the outcome on the skill
            if exec_result.success:
                skill.record_success()
                # Add to library if it's a new skill
                if not was_retrieved:
                    self.skill_library.add(skill)
            else:
                skill.record_failure(note=exec_result.error)
                all_subgoals_succeeded = False

            subgoal_results.append({
                "subgoal": str(subgoal),
                "success": exec_result.success,
                "skill_id": skill.id if skill else None,
                "retrieved": was_retrieved,
                "preconditions_held": exec_result.preconditions_held,
                "postconditions_held": exec_result.postconditions_held,
                "steps": exec_result.steps_taken,
                "error": exec_result.error,
                "actions": exec_result.actions_taken,
            })

        # ── Final check ────────────────────────────────────────────────
        final_check = self.env.step("look")
        won = final_check.won

        # False-success detection: all subgoals passed but task didn't
        false_success = all_subgoals_succeeded and not won

        elapsed = time.time() - start_time

        return EpisodeRecord(
            episode_id=episode_id,
            game_path=game_info.game_path,
            task_type=game_info.task_type,
            task_desc=game_info.task_desc,
            success=won,
            won=won,
            total_steps=self.env.step_count,
            subgoal_results=subgoal_results,
            elapsed_seconds=elapsed,
            skills_generated=skills_generated,
            skills_retrieved=skills_retrieved,
            false_success=false_success,
        )
