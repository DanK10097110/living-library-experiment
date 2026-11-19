"""Offline consolidation of UNDERUSED rules on a frozen library (lab experiment; owner's idea).

The selection rule, live checks and record merging now live in living_library/manual.py (variant B is the live
periodic step `manual.consolidate`); this module keeps the offline variants for experiments:
  A  underused rules merged only with each other: per (task type, rule type) agglomerative clusters of similar
     texts (embedding similarity >= CLUSTER_SIM, size <= MAX_CLUSTER); one general rule per cluster.
  B  each underused rule folded into the most similar well-used rule of the same task type and rule type
     (never a Success Process or Anti-Pattern).
The model writes, the live checks gate; failed rewrites keep the originals."""
import json

from .. import manual

CLUSTER_SIM = 0.65     # A: average-link similarity needed to join a cluster
MAX_CLUSTER = 4        # A: rules per cluster
FOLD_SIM = manual.FOLD_SIM
MAX_FOLD = manual.MAX_FOLD
MAX_WORDS = manual.FOLD_WORDS
SYSTEM = manual.FOLD_SYSTEM

games_shown = manual.credited
visible = manual._visible
percentile = manual.percentile
base_rates = manual.base_rates
select = manual.underused
problems = manual.fold_problems
fold_prompt = manual.fold_prompt
merged_record = manual.merged_record


def ask_rule(chat, user, kind, task_type):
    """Ask the model; (text, problems or []) after at most two tries (the second shows the first's problems)."""
    return manual.ask_folded(
        lambda text, attempt: chat.ask_json(SYSTEM, text, max_tokens=300, temperature=0.2 if attempt == 0 else 0.7,
                                            seed=attempt), user, kind, task_type)


def merge_prompt(task, kind, rules):
    listed = '\n'.join(f'{i + 1}. {r["rule"]}' for i, r in enumerate(rules))
    return (f'These rules of type "{kind}" all belong to the same kind of task ({task}).\n{listed}\n\n'
            'Write ONE general rule that covers all of them: keep every distinct useful detail (command forms, '
            'places to search, order) that is correct for the whole task type, drop only what is redundant or '
            'tied to one object. ' + manual.RULE_FORM + ' Use "If/When <condition>, <action>." and at most '
            f'{MAX_WORDS} words. If the rules contradict each other or one rule cannot be covered without losing '
            'its meaning, set "covers_all" to false.\n'
            'Return JSON {"rule": "<the rule>", "covers_all": true|false}.')


def clusters(rules, similarity, threshold=CLUSTER_SIM, max_size=MAX_CLUSTER):
    """Average-link agglomerative clusters of `rules` (same task and rule type) by text similarity."""
    groups = [[r] for r in rules]

    def sim(a, b):
        texts = [y['rule'] for y in b]
        return sum(sum(float(s) for s in similarity(x['rule'], texts)) for x in a) / (len(a) * len(b))
    while True:
        best, pair = threshold, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if len(groups[i]) + len(groups[j]) <= max_size:
                    s = sim(groups[i], groups[j])
                    if s >= best:
                        best, pair = s, (i, j)
        if pair is None:
            return groups
        i, j = pair
        groups[i] += groups.pop(j)


def by_scope(rules, ids):
    out = {}
    for r in rules:
        if r['id'] in ids:
            out.setdefault((r.get('task_type'), r['type']), []).append(r)
    return out


def variant_a(rules, chat, similarity):
    """(new rules, merges, rejected, info). Underused rules merged with each other only."""
    under, _, info = select(rules)
    plans = []
    for (task, kind), group in by_scope(rules, set(under)).items():
        for cluster in clusters(group, similarity):
            if len(cluster) > 1:
                plans.append((task, kind, cluster))

    def one(plan):
        task, kind, cluster = plan
        return ask_rule(chat, merge_prompt(task, kind, cluster), kind, task)
    results = chat.map(one, plans)
    replace, drop, merges, rejected = {}, set(), [], []
    for (task, kind, cluster), (text, why) in zip(plans, results):
        if text is None:
            rejected.append({'ids': [r['id'] for r in cluster], 'texts': [r['rule'] for r in cluster], 'why': why})
            continue
        keeper = max(cluster, key=lambda r: games_shown(r))
        others = [r for r in cluster if r is not keeper]
        replace[keeper['id']] = merged_record(keeper, others, text)
        drop |= {r['id'] for r in others}
        merges.append({'variant': 'A', 'kept_id': keeper['id'], 'task_type': task, 'type': kind,
                       'sources': [r['id'] for r in cluster], 'source_rules': [r['rule'] for r in cluster],
                       'new_rule': text})
    out = [replace.get(r['id'], r) for r in rules if r['id'] not in drop]
    info.update(underused=len(under), clusters=len(plans))
    return out, merges, rejected, info


def variant_b(rules, chat, similarity):
    """(new rules, merges, rejected, info). Each underused rule folded into its most similar well-used rule."""
    under, well, info = select(rules)
    plans = manual.fold_plans(rules, similarity)

    def one(plan):
        absorber, extras = plan
        why = []
        while extras:                      # on failure retry with the least similar one dropped
            text, why = ask_rule(chat, fold_prompt(absorber.get('task_type'), absorber['type'], absorber, extras),
                                 absorber['type'], absorber.get('task_type'))
            if text is not None:
                return extras, text, []
            extras = extras[:-1]
        return [], None, why
    results = chat.map(one, plans)
    replace, drop, merges, rejected = {}, set(), [], []
    for (absorber, wanted), (extras, text, why) in zip(plans, results):
        if text is None:
            rejected.append({'ids': [absorber['id']] + [r['id'] for r in wanted],
                             'texts': [absorber['rule']] + [r['rule'] for r in wanted], 'why': why})
            continue
        replace[absorber['id']] = merged_record(absorber, extras, text)
        drop |= {r['id'] for r in extras}
        merges.append({'variant': 'B', 'kept_id': absorber['id'], 'task_type': absorber.get('task_type'),
                       'type': absorber['type'], 'sources': [absorber['id']] + [r['id'] for r in extras],
                       'source_rules': [absorber['rule']] + [r['rule'] for r in extras], 'new_rule': text})
    out = [replace.get(r['id'], r) for r in rules if r['id'] not in drop]
    info.update(underused=len(under), well_used=len(well), absorbers=len(plans),
                unmatched=len(under) - sum(len(e) for _, e in plans))
    return out, merges, rejected, info


def dump(rules, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=1)
