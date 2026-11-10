"""
environment.py — ALFWorld environment wrapper.

Provides a clean Python API over the TextWorld-based ALFWorld simulator.
Handles game discovery, environment creation, stepping, and state extraction.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import textworld
import textworld.gym

from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """Result of a single environment step."""
    observation: str
    reward: float
    done: bool
    won: bool
    admissible_commands: list[str]
    facts: list[str]
    raw_info: dict = field(default_factory=dict, repr=False)


@dataclass
class GameInfo:
    """Metadata for an ALFWorld game file."""
    game_path: str
    task_type: str
    object_target: str
    parent_target: str
    toggle_target: str
    mrecep_target: str
    task_desc: str
    trial_dir: str


# ── Game discovery ──────────────────────────────────────────────────────────

TASK_TYPES = {
    "pick_and_place_simple",
    "look_at_obj_in_light",
    "pick_clean_then_place_in_recep",
    "pick_heat_then_place_in_recep",
    "pick_cool_then_place_in_recep",
    "pick_two_obj_and_place",
}

EXCLUDED_PATTERNS = {"Sliced", "movable_recep"}


def discover_games(
    data_dir: str | Path,
    split: str = "train",
    task_types: set[str] | None = None,
    excluded_patterns: set[str] | None = None,
) -> list[GameInfo]:
    """
    Discover all playable ALFWorld game files in a given split.

    Args:
        data_dir: Root ALFWorld data directory (e.g. ~/.cache/alfworld/json_2.1.1).
        split: One of 'train', 'valid_seen', 'valid_unseen'.
        task_types: If given, only include these task types.
        excluded_patterns: Substrings to exclude from game paths.

    Returns:
        Sorted list of GameInfo objects.
    """
    if task_types is None:
        task_types = TASK_TYPES
    if excluded_patterns is None:
        excluded_patterns = EXCLUDED_PATTERNS

    split_dir = Path(data_dir).expanduser() / split
    if not split_dir.exists():
        raise FileNotFoundError(f"Split directory not found: {split_dir}")

    games: list[GameInfo] = []

    for task_dir in sorted(split_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        # Skip excluded patterns
        task_dir_name = task_dir.name
        if any(pat in task_dir_name for pat in excluded_patterns):
            continue

        # Each task directory contains one or more trial subdirectories
        for trial_dir in sorted(task_dir.iterdir()):
            if not trial_dir.is_dir():
                continue

            game_file = trial_dir / "game.tw-pddl"
            traj_file = trial_dir / "traj_data.json"

            if not game_file.exists() or not traj_file.exists():
                continue

            # Read trajectory data for task metadata
            with open(traj_file) as f:
                traj_data = json.load(f)

            task_type = traj_data.get("task_type", "")
            if task_type not in task_types:
                continue

            pddl_params = traj_data.get("pddl_params", {})

            # Extract a human-readable task description
            task_desc = _extract_task_desc(traj_data)

            games.append(GameInfo(
                game_path=str(game_file),
                task_type=task_type,
                object_target=pddl_params.get("object_target", ""),
                parent_target=pddl_params.get("parent_target", ""),
                toggle_target=pddl_params.get("toggle_target", ""),
                mrecep_target=pddl_params.get("mrecep_target", ""),
                task_desc=task_desc,
                trial_dir=str(trial_dir),
            ))

    return games


def _extract_task_desc(traj_data: dict) -> str:
    """Extract a human-readable task description from trajectory data."""
    # Try turk annotations first
    try:
        anns = traj_data["turk_annotations"]["anns"]
        if anns:
            return anns[0].get("task_desc", "")
    except (KeyError, IndexError):
        pass
    return ""


# ── Environment wrapper ────────────────────────────────────────────────────

class AlfWorldEnv:
    """
    Wrapper around ALFWorld's TextWorld-based environment.

    Provides a clean step/reset interface and extracts structured state
    information including PDDL facts for predicate checking.

    Usage:
        env = AlfWorldEnv(max_steps=50)
        env.load(game_info)
        result = env.reset()
        while not result.done:
            result = env.step("go to dresser 1")
        env.close()
    """

    def __init__(self, max_steps: int = 50):
        self.max_steps = max_steps
        self._env = None
        self._env_id: Optional[str] = None
        self._game_info: Optional[GameInfo] = None
        self._step_count = 0

    @property
    def game_info(self) -> Optional[GameInfo]:
        return self._game_info

    def load(self, game_info: GameInfo) -> None:
        """Load a game file and create the Gym environment."""
        self.close()  # clean up any previous environment

        self._game_info = game_info

        request_infos = textworld.EnvInfos(
            won=True,
            admissible_commands=True,
            facts=True,          # needed for predicate checking
            extras=["gamefile"],
        )

        self._env_id = textworld.gym.register_game(
            game_info.game_path,
            request_infos,
            max_episode_steps=self.max_steps,
            wrappers=[AlfredDemangler(), AlfredInfos],
        )

        self._env = textworld.gym.make(self._env_id)

    def reset(self) -> StepResult:
        """Reset the environment and return the initial observation."""
        if self._env is None:
            raise RuntimeError("No game loaded. Call load() first.")

        obs, info = self._env.reset()
        self._step_count = 0
        self._last_result = self._make_result(obs, reward=0.0, done=False, info=info)
        return self._last_result

    def step(self, action: str) -> StepResult:
        """Execute an action and return the result."""
        if self._env is None:
            raise RuntimeError("No game loaded. Call load() first.")

        obs, reward, done, info = self._env.step(action)
        self._step_count += 1
        self._last_result = self._make_result(obs, reward, done, info)
        return self._last_result

    @property
    def last_result(self) -> Optional[StepResult]:
        """Return the most recent StepResult."""
        return self._last_result

    @property
    def last_facts(self) -> list[str]:
        """Return the PDDL facts from the most recent step."""
        if self._last_result is not None:
            return self._last_result.facts
        return []

    @property
    def last_admissible_commands(self) -> list[str]:
        """Return admissible commands from the most recent step."""
        if self._last_result is not None:
            return self._last_result.admissible_commands
        return []

    def close(self) -> None:
        """Close the environment and free resources."""
        if self._env is not None:
            try:
                self._env.close()
            except Exception:
                pass
            self._env = None
            self._env_id = None

    @property
    def step_count(self) -> int:
        return self._step_count

    def _make_result(self, obs: str, reward: float, done: bool, info: dict) -> StepResult:
        """Build a StepResult from raw Gym outputs."""
        # Extract facts as strings (e.g., "holds agent apple 1")
        raw_facts = info.get("facts", [])
        facts = self._format_facts(raw_facts)

        return StepResult(
            observation=obs if isinstance(obs, str) else str(obs),
            reward=reward,
            done=done,
            won=info.get("won", False),
            admissible_commands=info.get("admissible_commands", []),
            facts=facts,
            raw_info=info,
        )

    @staticmethod
    def _format_facts(raw_facts) -> list[str]:
        """Convert TextWorld Proposition objects to readable strings."""
        facts = []
        if raw_facts is None:
            return facts
        for fact in raw_facts:
            try:
                # TextWorld Proposition: fact.name + fact.names (arguments)
                name = fact.name
                args = " ".join(n.strip() for n in fact.names)
                facts.append(f"{name} {args}".strip())
            except AttributeError:
                # If it's already a string
                facts.append(str(fact))
        return facts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        game = self._game_info.task_type if self._game_info else "none"
        return f"AlfWorldEnv(game={game}, step={self._step_count})"
