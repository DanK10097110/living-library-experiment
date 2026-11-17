from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path


CONDITIONS = ("A", "B", "C", "D", "E", "E-minus", "E-text", "E-plus")
# E-plus = E + periodic library consolidation (extension arm; see consolidation.py).
MEMORY = {"B", "D", "E", "E-minus", "E-plus"}
UPDATES = {"B", "E", "E-plus"}


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
    top_k: int = 3
    beta_alpha: float = 1.0
    beta_beta: float = 1.0
    reliability_percentile: float = 0.1
    similarity_weight: float = 1.0
    reliability_weight: float = 1.0
    low_reliability: float = 0.6
    min_uses: int = 5
    consecutive_failures: int = 3
    test_limit: int = 10
    step_budget: int = 100
    subgoal_step_budget: int = 20
    practice_batch: int = 1         # practice games run at once from the same memory (batching.py)
    react_demos: bool = True        # ReAct's two worked examples per task type in the actor prompt
    actor_brief: bool = False       # ask the actor for short reasoning (models that ramble)
    program_budget: int = 1000
    call_depth: int = 8
    repairs: int = 2
    replans: int = 2
    max_subgoals: int = 12
    max_model_calls: int = 100
    pilot_practice: int = 300
    practice_episodes: int = 500
    practice_seed: int = 0
    seeds: list[int] = field(default_factory=lambda: [11, 22, 33])
    conditions: list[str] = field(default_factory=lambda: list(CONDITIONS))   # study conditions
    consolidation_interval: int = 25     # E-plus: consolidate after every N episodes of a stream
    compose_min_count: int = 3           # E-plus: back-to-back skill pairs seen this often -> meta-skill
    merge_similarity: float = 0.75       # E-plus: description similarity for merge candidates
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
    text_rendering: str = "numbered-python-statements-v1"
    bootstrap_samples: int = 10000
    success_margin: float = 0.1
    cost_reduction: float = 0.3

    def __post_init__(self):
        positive = ("top_k", "beta_alpha", "beta_beta", "min_uses", "consecutive_failures", "subgoal_step_budget",
                    "test_limit", "step_budget", "program_budget", "call_depth", "max_subgoals",
                    "max_model_calls", "pilot_practice", "practice_episodes", "development_games",
                    "evaluation_games", "max_tokens", "bootstrap_samples", "consolidation_interval", "snapshot_games",
                    "compose_min_count", "practice_batch")
        for key in positive:
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        integer_fields = set(positive) - {"beta_alpha", "beta_beta"}
        integer_fields |= {"repairs", "replans", "practice_seed"}
        if any(type(getattr(self, key)) is not int for key in integer_fields):
            raise ValueError("episode counts, seeds and budgets must be integers")
        if self.repairs < 0 or self.replans < 0:
            raise ValueError("repair/replan budgets cannot be negative")
        if not 0 < self.reliability_percentile < 1 or not 0 < self.low_reliability < 1:
            raise ValueError("invalid probability")
        if len(set(self.seeds)) != len(self.seeds) or not self.seeds:
            raise ValueError("seeds must be nonempty and unique")
        if any(type(seed) is not int for seed in self.seeds):
            raise ValueError("seeds must be integers")
        if (not self.conditions or len(set(self.conditions)) != len(self.conditions)
                or any(c not in CONDITIONS for c in self.conditions)):
            raise ValueError("conditions must be unique valid condition IDs")
        if any(type(m) is not int or not 0 < m <= self.practice_episodes
               for m in self.snapshot_milestones + self.library_milestones):
            raise ValueError("snapshot milestones must be practice positions")
        if any(c not in self.conditions or c not in MEMORY or c == "E-text" for c in self.snapshot_conditions):
            raise ValueError("snapshot conditions must be study memory conditions")
        if "E-text" in self.conditions and "E" not in self.conditions:
            raise ValueError("E-text needs condition E as its source")
        for key in ("similarity_weight", "reliability_weight", "temperature"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        if not 0 < self.success_margin < 1 or not 0 < self.cost_reduction < 1:
            raise ValueError("study margins must be between zero and one")
        if self.text_rendering != "numbered-python-statements-v1":
            raise ValueError("unsupported text rendering rule")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))

    def to_dict(self):
        return asdict(self)
