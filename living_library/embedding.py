"""Text similarity for retrieval: D's example trajectories and the rule manual's relevance."""
import math
import re


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
