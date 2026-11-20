from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path


CONDITIONS = ("A", "C", "D", "E", "E-minus")
# A = flat ReAct without planner or memory (kept in code, not in the study). C = planner + ReAct actor.
# D = C + successful practice trajectories; E = C + rule manual (managed); E-minus = the same manual, append-only.
MEMORY = {"D", "E", "E-minus"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    """Atomic checkpoint replacement; a crash cannot leave half an episode committed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.replace(path)


@dataclass
class Settings:
    top_k: int = 3                  # D: similar successful practice trajectories shown
    step_budget: int = 100
    subgoal_step_budget: int = 20
    practice_batch: int = 1         # practice games run at once from the same memory (batching.py)
    react_demos: bool = True        # ReAct's two worked examples per task type in the actor prompt
    actor_brief: bool = False       # ask the actor for short reasoning (models that ramble)
    replans: int = 2
    max_subgoals: int = 12
    max_model_calls: int = 100
    practice_episodes: int = 500
    # Practice replicates: every memory condition practises once per seed, each with its own game order.
    practice_seeds: list[int] = field(default_factory=lambda: [0])
    seeds: list[int] = field(default_factory=lambda: [11, 22, 33])
    conditions: list[str] = field(default_factory=lambda: list(CONDITIONS))   # study conditions
    # Practice-length curve: the library after N practice episodes, frozen (read-only), is tested
    # on fixed subsets of in- and out-of-distribution games (seed[0] order).
    snapshot_milestones: list[int] = field(default_factory=list)
    # Library snapshots kept for analysis (library-over-time figures); replay only at snapshot_milestones.
    library_milestones: list[int] = field(default_factory=list)
    snapshot_games: int = 40
    snapshot_conditions: list[str] = field(default_factory=list)
    development_games: int = 140
    evaluation_games: int = 134
    embedding: str = "BAAI/bge-small-en-v1.5"
    embedding_revision: str = "main"
    planner_model: str = "Qwen/Qwen3-14B"
    executor_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    planner_revision: str = "unverified"
    executor_revision: str = "unverified"
    quantization: str = "4-bit-unverified"
    hardware: str = "unrecorded"
    planner_url: str = "http://127.0.0.1:8000/v1"
    executor_url: str = "http://127.0.0.1:8001/v1"
    temperature: float = 0.2
    max_tokens: int = 2048
    bootstrap_samples: int = 10000
    success_margin: float = 0.1
    cost_reduction: float = 0.3

    def __post_init__(self):
        positive = ("top_k", "subgoal_step_budget", "step_budget", "max_subgoals", "max_model_calls",
                    "practice_episodes", "development_games", "evaluation_games", "max_tokens",
                    "bootstrap_samples", "snapshot_games", "practice_batch")
        for key in positive:
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if any(type(getattr(self, key)) is not int for key in positive + ("replans",)):
            raise ValueError("episode counts, seeds and budgets must be integers")
        if self.replans < 0:
            raise ValueError("replan budget cannot be negative")
        for name in ("seeds", "practice_seeds"):
            values = getattr(self, name)
            if not values or len(set(values)) != len(values) or any(type(v) is not int for v in values):
                raise ValueError(f"{name} must be nonempty, unique integers")
        if (not self.conditions or len(set(self.conditions)) != len(self.conditions)
                or any(c not in CONDITIONS for c in self.conditions)):
            raise ValueError("conditions must be unique valid condition IDs")
        if any(type(m) is not int or not 0 < m <= self.practice_episodes
               for m in self.snapshot_milestones + self.library_milestones):
            raise ValueError("snapshot milestones must be practice positions")
        if any(c not in self.conditions or c not in MEMORY for c in self.snapshot_conditions):
            raise ValueError("snapshot conditions must be study memory conditions")
        if not math.isfinite(self.temperature) or self.temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if not 0 < self.success_margin < 1 or not 0 < self.cost_reduction < 1:
            raise ValueError("study margins must be between zero and one")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))

    def to_dict(self):
        return asdict(self)
