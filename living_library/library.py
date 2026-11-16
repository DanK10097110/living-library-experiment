from dataclasses import asdict, dataclass, field
import copy
import math
import re

from .config import Settings
from .domain import Predicate
from .program import Program


@dataclass
class Skill:
    id: str
    description: str
    parameters: dict[str, str]
    preconditions: list[str]
    postconditions: list[str]
    body: str
    parent: str | None = None
    successes: int = 0
    failures: int = 0
    streak: int = 0
    failure_notes: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    status: str = "candidate"

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_]*@v[1-9][0-9]*", self.id):
            raise ValueError("skill ids must have form name@v1")
        if not self.description.strip() or not self.postconditions:
            raise ValueError("description and nonempty postconditions required")
        for name, kind in self.parameters.items():
            if (not re.fullmatch(r"[a-z][a-z0-9_]*", name) or kind != "entity"
                    or name in {"act", "check", "call", "range"}):
                raise ValueError("parameters must be named entity arguments")
        for p in self.preconditions + self.postconditions:
            Predicate.parse(p)
        Program(self.body, self.parameters)

    @property
    def name(self):
        return self.id.split("@")[0]

    @property
    def signature(self):
        return f"{self.name}({', '.join(self.parameters)})"

    @property
    def uses(self):
        return self.successes + self.failures

    def mean(self, cfg):
        return (cfg.beta_alpha + self.successes) / (cfg.beta_alpha + cfg.beta_beta + self.uses)

    def reliability(self, cfg):
        from scipy.stats import beta
        return float(beta.ppf(cfg.reliability_percentile, cfg.beta_alpha + self.successes,
                              cfg.beta_beta + self.failures))

    def needs_revision(self, cfg):
        return ((self.uses >= cfg.min_uses and self.mean(cfg) < cfg.low_reliability)
                or self.streak >= cfg.consecutive_failures)

    def text(self):
        return {"id": self.id, "signature": self.signature, "description": self.description,
                "preconditions": self.preconditions, "postconditions": self.postconditions,
                "steps": Program(self.body, self.parameters).render(),
                "failure_notes": self.failure_notes}


class LexicalEmbedding:
    """Cheap deterministic smoke-test retrieval, never the benchmark default."""
    def similarity(self, query, descriptions):
        q = set(re.findall(r"[a-z0-9]+", query.lower()))
        result = []
        for text in descriptions:
            d = set(re.findall(r"[a-z0-9]+", text.lower()))
            result.append(len(q & d) / math.sqrt(max(1, len(q) * len(d))))
        return result


class SentenceEmbedding:
    def __init__(self, name, revision):
        from sentence_transformers import SentenceTransformer
        # Models must be installed by the user; never trigger a model download.
        self.model = SentenceTransformer(name, revision=revision, device="cpu", local_files_only=True)
        self.cache = {}

    def similarity(self, query, descriptions):
        missing = list(dict.fromkeys(t for t in [query, *descriptions] if t not in self.cache))
        if missing:
            encoded = self.model.encode(missing, normalize_embeddings=True)
            self.cache.update(zip(missing, encoded))
        return [float(self.cache[query] @ self.cache[d]) for d in descriptions]


class Library:
    def __init__(self, cfg=None, skills=None, active=None):
        self.cfg = cfg or Settings()
        self.skills = {s["id"]: Skill(**copy.deepcopy(s)) for s in (skills or [])}
        self.active = dict(active or {})
        for name, sid in self.active.items():
            if sid not in self.skills or self.skills[sid].name != name:
                raise ValueError("corrupt active skill index")

    def snapshot(self):
        return copy.deepcopy({"skills": [asdict(s) for s in self.skills.values()], "active": self.active})

    @classmethod
    def restore(cls, data, cfg):
        return cls(cfg, **data)

    def catalog(self):
        # L1 deliberately gets no bodies, conditions, or outcome notes.
        return [{"id": s.id, "signature": s.signature} for s in self.current()]

    def current(self):
        return [self.skills[sid] for _, sid in sorted(self.active.items())]

    def next_id(self, name):
        versions = [int(s.id.rsplit("v", 1)[1]) for s in self.skills.values() if s.name == name]
        return f"{name}@v{max(versions, default=0) + 1}"

    def retrieve(self, query, bindings, state, embedder):
        eligible = [s for s in self.current() if set(s.parameters) <= set(bindings)
                    and all(bindings[p] in state.entities for p in s.parameters)
                    and state.check(s.preconditions, bindings)]
        scores = embedder.similarity(query, [s.description for s in eligible])
        ranked = sorted(zip(eligible, scores), key=lambda pair: (
            -(self.cfg.similarity_weight * pair[1] + self.cfg.reliability_weight * pair[0].reliability(self.cfg)),
            pair[0].id))
        return [s for s, _ in ranked[:self.cfg.top_k]]

    def record(self, sid, success, preconditions_held, test, note="", updates=True):
        s = self.skills[sid]
        if not preconditions_held:
            return "retrieval_error"
        if not updates:
            return "append_only"
        if success:
            s.successes += 1
            s.streak = 0
            if test not in s.tests and len(s.tests) < self.cfg.test_limit:
                s.tests.append(copy.deepcopy(test))
        else:
            s.failures += 1
            s.streak += 1
            if note:
                s.failure_notes.append(" ".join(note.split())[:500])
        if (s.parent and self.active.get(s.name) == s.id and s.uses >= self.cfg.min_uses
                and s.mean(self.cfg) < self.skills[s.parent].reliability(self.cfg)):
            s.status = "fallback"
            self.skills[s.parent].status = "active"
            self.active[s.name] = s.parent
            return "rollback"
        return "revision_due" if s.needs_revision(self.cfg) else "recorded"

    def admit(self, candidate, test, verify, updates=True):
        """The only admission path, also used for repairs and optional consolidation.

        verify(skill, replay_test) uses an isolated simulator and never changes counters.
        Even a new skill must pass a real replay; vacuous admission is forbidden.
        """
        if candidate.id in self.skills:
            raise ValueError("immutable version id already exists")
        old = self.skills.get(candidate.parent)
        if candidate.parent and old is None:
            raise ValueError("unknown parent")
        if old:
            if not updates or self.active.get(old.name) != old.id:
                raise ValueError("only the active version can be replaced, with updates enabled")
            if (candidate.name != old.name or candidate.parameters != old.parameters
                    or candidate.preconditions != old.preconditions
                    or candidate.postconditions != old.postconditions):
                raise ValueError("a revision must preserve its typed contract")
        elif candidate.name in self.active:
            raise ValueError("existing skill requires an explicit parent")
        # Do not trust model-supplied counters, tests, or status.
        candidate = Skill(candidate.id, candidate.description, copy.deepcopy(candidate.parameters),
                          candidate.preconditions.copy(), candidate.postconditions.copy(), candidate.body,
                          parent=candidate.parent)
        tests = copy.deepcopy(old.tests if old else [])
        if test not in tests:
            tests.append(copy.deepcopy(test))
        candidate.tests = tests[:self.cfg.test_limit]
        self.skills[candidate.id] = candidate
        try:
            outcomes = [bool(verify(candidate, t)) for t in tests]
        except Exception:
            candidate.status = "rejected"
            raise
        if not all(outcomes):
            candidate.status = "rejected"
            return False
        if old:
            old.status = "fallback"
        candidate.status = "active"
        self.active[candidate.name] = candidate.id
        return True
