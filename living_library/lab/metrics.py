"""Retrieval quality of one top-k list against deterministic labels (synth.label)."""
import math

KS = (3, 5, 8)


def score(top, rules_by_id, meta, query, relevant_groups, label):
    """Metrics of `top` (rule ids, ranked) for one query. relevant_groups: {group: best gain} over the whole
    library. Duplicates (a group already shown) earn no gain and no recall."""
    out = {}
    for k in KS:
        ids = top[:k]
        seen, gains, hits, junk, wrong, dup, rel = set(), [], set(), 0, 0, 0, 0
        for i in ids:
            g, is_junk, is_wrong = label(rules_by_id[i], meta[i], query)
            group = meta[i]['group']
            duplicate = group in seen
            seen.add(group)
            dup += duplicate
            junk += is_junk
            wrong += is_wrong
            rel += g > 0
            gains.append(0 if duplicate else g)
            if g > 0 and not duplicate:
                hits.add(group)
        ideal = sorted(relevant_groups.values(), reverse=True)[:k]
        dcg = sum(g / math.log2(r + 2) for r, g in enumerate(gains))
        idcg = sum(g / math.log2(r + 2) for r, g in enumerate(ideal))
        n = len(ids) or 1
        out[k] = {'recall': len(hits) / max(1, min(k, len(relevant_groups))),
                  'precision': rel / n, 'useful': len(hits), 'ndcg': dcg / idcg if idcg else 0.0,
                  'dup': dup / n, 'junk': junk / n, 'wrong': wrong / n, 'shown': len(ids)}
    return out


def relevant_groups(rules, meta, query, label):
    best = {}
    for r in rules:
        g = label(r, meta[r['id']], query)[0]
        if g > 0:
            best[meta[r['id']]['group']] = max(g, best.get(meta[r['id']]['group'], 0))
    return best


def mean(rows):
    """Average of per-query metric dicts {k: {name: value}}."""
    out = {}
    for k in KS:
        out[k] = {m: sum(r[k][m] for r in rows) / len(rows) for m in rows[0][k]}
    return out
