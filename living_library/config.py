from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path


CONDITIONS = ("A", "B", "C", "D", "E", "E-minus", "E-text")
MEMORY = {"B", "D", "E", "E-minus"}
UPDATES = {"B", "E"}


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
        positive = ("top_k", "beta_alpha", "beta_beta", "min_uses", "consecutive_failures",
                    "test_limit", "step_budget", "program_budget", "call_depth", "max_subgoals",
                    "max_model_calls", "pilot_practice", "practice_episodes", "development_games",
                    "evaluation_games", "max_tokens", "bootstrap_samples")
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
