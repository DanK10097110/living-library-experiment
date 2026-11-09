"""
skill_library.py — Append-only skill library (Phase 1 / E-minus).

Stores verified skills as executable Python code with typed contracts,
outcome counts, and regression tests. Skills are retrieved by description
similarity and reliability scoring.

Following the revised proposal (p. 4-5):
    - Each skill has: id, signature, description, pre/postconditions,
      body (code), successes, failures, failure_notes, tests, embedding.
    - Retrieval drops skills whose preconditions can't hold, ranks rest
      by description similarity + Beta reliability score.
    - The append-only ablation (E-) skips every row except saving new skills.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from living_skills.predicates import ConditionSet, parse_conditions


@dataclass
class SkillRecord:
    """
    A single skill stored in the library.

    Following the proposal's JSON schema (p. 4):
        id, parent, signature, description, preconditions, postconditions,
        body, successes, failures, failure_notes, tests, embedding
    """
    id: str                               # e.g., "take_apple@v1"
    signature: str                        # e.g., "take_object(obj, recep)"
    description: str                      # human-readable
    preconditions: list[str]              # parseable predicate specs
    postconditions: list[str]             # parseable predicate specs
    body: str                             # executable Python source
    successes: int = 0
    failures: int = 0
    failure_notes: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)   # saved start states
    embedding: Optional[list[float]] = field(default=None, repr=False)
    parent: Optional[str] = None          # id of the previous version
    created_at: float = field(default_factory=time.time)

    # ── Reliability scoring (Beta posterior) ────────────────────────────

    def reliability_score(self, percentile: float = 0.10) -> float:
        """
        Compute the reliability score as a low percentile of the
        Beta(1 + successes, 1 + failures) posterior.

        From the revised proposal (p. 5):
            "a low percentile (10th, fixed at the freeze) of the
             Beta(1 + successes, 1 + failures) posterior"

        Uses a normal approximation for the Beta quantile when
        alpha + beta > 2; otherwise falls back to the mean.
        """
        alpha = 1 + self.successes
        beta_param = 1 + self.failures
        mean = alpha / (alpha + beta_param)

        if alpha + beta_param <= 2:
            return mean

        # Normal approximation of Beta quantile
        variance = (alpha * beta_param) / ((alpha + beta_param) ** 2 * (alpha + beta_param + 1))
        std = math.sqrt(variance)

        # z-score for the given percentile (using a simple lookup)
        z_scores = {0.10: -1.2816, 0.05: -1.6449, 0.25: -0.6745}
        z = z_scores.get(percentile, -1.2816)

        score = mean + z * std
        return max(0.0, min(1.0, score))

    @property
    def total_uses(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total_uses == 0:
            return 0.0
        return self.successes / self.total_uses

    def record_success(self, test_state: Optional[dict] = None, max_tests: int = 10):
        """Record a successful invocation."""
        self.successes += 1
        if test_state is not None and len(self.tests) < max_tests:
            self.tests.append(test_state)

    def record_failure(self, note: Optional[str] = None):
        """Record a failed invocation."""
        self.failures += 1
        if note and note not in self.failure_notes:
            self.failure_notes.append(note)

    def to_dict(self) -> dict:
        """Serialize to a dictionary (for JSON storage)."""
        d = asdict(self)
        d.pop("embedding", None)  # embeddings stored separately
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SkillRecord:
        """Deserialize from a dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Skill Library ──────────────────────────────────────────────────────────

class SkillLibrary:
    """
    Append-only skill library for Phase 1 (E-minus).

    Stores skills in memory with optional persistence to a JSON file.
    Retrieval uses description-based matching and reliability scoring.
    """

    def __init__(
        self,
        retrieval_top_k: int = 3,
        similarity_threshold: float = 0.4,
        reliability_percentile: float = 0.10,
        persist_path: Optional[str | Path] = None,
    ):
        self.retrieval_top_k = retrieval_top_k
        self.similarity_threshold = similarity_threshold
        self.reliability_percentile = reliability_percentile
        self.persist_path = Path(persist_path) if persist_path else None

        self._skills: dict[str, SkillRecord] = {}  # id -> SkillRecord
        self._version_counter: dict[str, int] = {}  # base_name -> latest version

        if self.persist_path and self.persist_path.exists():
            self._load()

    @property
    def size(self) -> int:
        return len(self._skills)

    @property
    def all_skills(self) -> list[SkillRecord]:
        return list(self._skills.values())

    def add(self, skill: SkillRecord) -> str:
        """
        Add a new skill to the library. Returns the assigned ID.

        This is append-only: existing skills are never modified or removed
        through this method.
        """
        # Generate a versioned ID if not already set
        if not skill.id or skill.id in self._skills:
            base_name = self._make_base_name(skill.signature)
            version = self._version_counter.get(base_name, 0) + 1
            self._version_counter[base_name] = version
            skill.id = f"{base_name}@v{version}"

        self._skills[skill.id] = skill
        self._save()
        return skill.id

    def get(self, skill_id: str) -> Optional[SkillRecord]:
        """Get a skill by its ID."""
        return self._skills.get(skill_id)

    def retrieve(
        self,
        query: str,
        current_facts: Optional[list[str]] = None,
        top_k: Optional[int] = None,
    ) -> list[SkillRecord]:
        """
        Retrieve the top-k matching skills for a query.

        From the revised proposal (p. 5):
            "Retrieval drops skills whose preconditions can't hold in the
             current state. It ranks the rest by description similarity
             plus a reliability score."

        Args:
            query: Description of the needed capability (e.g., "take apple").
            current_facts: Current simulator facts for precondition filtering.
            top_k: Override the default top-k.

        Returns:
            Ranked list of matching skills.
        """
        if top_k is None:
            top_k = self.retrieval_top_k

        candidates = []

        for skill in self._skills.values():
            # Filter: drop skills whose preconditions can't hold
            if current_facts is not None and skill.preconditions:
                try:
                    cond_set = parse_conditions(skill.preconditions)
                    holds, _ = cond_set.evaluate(current_facts)
                    if not holds:
                        continue
                except (ValueError, KeyError):
                    pass  # If we can't parse, don't filter

            # Score: description similarity + reliability
            sim = self._text_similarity(query, skill.description, skill.signature)
            reliability = skill.reliability_score(self.reliability_percentile)
            # Combined score: weighted sum
            score = 0.7 * sim + 0.3 * reliability

            if sim >= self.similarity_threshold:
                candidates.append((score, skill))

        # Sort by score descending
        candidates.sort(key=lambda x: -x[0])

        return [skill for _, skill in candidates[:top_k]]

    def get_reuse_stats(self) -> dict:
        """Return reuse statistics for the pilot decision rules."""
        skills_used = [s for s in self._skills.values() if s.total_uses > 0]
        skills_used_5plus = [s for s in skills_used if s.total_uses >= 5]

        return {
            "total_skills": len(self._skills),
            "skills_used": len(skills_used),
            "skills_used_5plus": len(skills_used_5plus),
            "total_invocations": sum(s.total_uses for s in self._skills.values()),
            "avg_uses": (
                sum(s.total_uses for s in skills_used) / len(skills_used)
                if skills_used else 0.0
            ),
        }

    # ── Persistence ────────────────────────────────────────────────────

    def _save(self):
        """Persist the library to disk."""
        if self.persist_path is None:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version_counter": self._version_counter,
            "skills": [s.to_dict() for s in self._skills.values()],
        }
        with open(self.persist_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        """Load the library from disk."""
        with open(self.persist_path) as f:
            data = json.load(f)
        self._version_counter = data.get("version_counter", {})
        for sd in data.get("skills", []):
            skill = SkillRecord.from_dict(sd)
            self._skills[skill.id] = skill

    # ── Similarity scoring ─────────────────────────────────────────────

    @staticmethod
    def _text_similarity(query: str, description: str, signature: str) -> float:
        """
        Simple keyword-overlap similarity between a query and a skill's
        description/signature.

        This is a placeholder; will be replaced with embedding-based cosine
        similarity when sentence-transformers is integrated.
        """
        query_tokens = set(_tokenize(query))
        desc_tokens = set(_tokenize(description)) | set(_tokenize(signature))

        if not query_tokens or not desc_tokens:
            return 0.0

        intersection = query_tokens & desc_tokens
        union = query_tokens | desc_tokens

        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _make_base_name(signature: str) -> str:
        """Extract a base name from a signature for versioning."""
        # "take_object(obj, recep)" -> "take_object"
        name = signature.split("(")[0].strip()
        name = re.sub(r"[^a-z0-9_]", "_", name.lower())
        return name or "skill"


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r"[a-z0-9]+", text.lower())
