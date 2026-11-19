"""Synthetic libraries of N visible rules built from the real rule pool, with deterministic relevance labels.

A library = one Success Process per kind of task (the real one with most wins; the live code allows only one)
+ the real non-recipe rules + model-written variants of them (paraphrases, near-duplicates, more general,
more specific (other objects), the analogous rule for another kind, and junk: vague, wrong,
instance-specific), added in a fixed random order. Every candidate passes the live merge gate first
(manual.near_duplicate, similarity >= 0.85 to a rule of the same type and kind): one that the live code
would have merged is skipped, as it could never coexist in a real library.

Synthetic rules get realistic bookkeeping: source task(s) and won/lost game contexts drawn from real ALFWorld
practice goals of their kind (a more specific rule's evidence names its object), and Beta counts drawn from the
real rules' (won, lost) distribution, whatever the variant class (co-shown rules get the same credit, so junk is
not less reliable by its counts; LOG 2026-11-19 13:08).

Labels (no model; see results/lab/REPORT.md "Labeling rules"):
  * junk (vague, wrong, instance-specific, or a real rule flagged by hand) -> gain 0, 'junk'
  * wrong kind: scope is another kind, or the text uses another kind's action words -> gain 0, 'wrong kind'
  * more-specific variant naming objects -> relevant only if the goal names one of them
  * otherwise gain 2 for the query kind's Success Process, else 1.
Duplicates: a rule and its paraphrases/near-duplicates share a group; top-k items whose group was already
shown are duplicates (no gain in nDCG, no extra recall)."""
import json
import random
import re
import zlib
from pathlib import Path

from .. import manual
from .data import KINDS, SHORT, ROOT, objects_in

LONG = {v: k for k, v in SHORT.items()}
KIND_TEXT = {
    'simple': 'put an object in/on a receptacle', 'look': 'examine an object under a desklamp/floorlamp',
    'clean': 'clean an object with the sinkbasin, then put it in a receptacle',
    'heat': 'heat an object with the microwave, then put it in a receptacle',
    'cool': 'cool an object with the fridge, then put it in a receptacle',
    'two': 'put two objects of the same kind in a receptacle'}
# Action words only (appliance nouns can be targets: "put a tomato in microwave" is a simple task).
ACTIONS = {
    'clean': r'clean(?:s|ed|ing)?|rins\w*|wash\w*',
    'cool': r'cool(?:s|ed|ing)?|chill\w*',
    'heat': r'heat(?:s|ed|ing)?|warm\w*',
    'look': r'desklamp|floorlamp|lamp|light',
    'two': r'two objects|two items|both objects|both items|each object|second object|second item|'
           r'another (?:object|item)|two of',
}
# Real rules judged junk by hand (spot check of the pool, written down in the report). Matched on text start.
HAND_JUNK = [
    'When the task is to put two alarmclocks',        # instance-specific, and the claim is meaningless
    'When the task is to put two keychains',
    'When the task is to put two pencils',
    'When the task is to cool an object and put it in countertop, the game may win',   # trace-bug artefact
    'When the task is to put a cool pan in diningtable',
    'When cooling an object, place it on a safe surface first',     # nonsense (LOG 2026-11-19 13:08)
    'When heating a container on a stoveburner',      # wrong: ALFWorld heats with the microwave
    'When attempting to go to a cabinet, ensure it is open first',   # wrong: cannot open before going
    'When a cabinet is closed, go to a drawer or countertop',        # harmful (LOG 13:09)
    'When heating a mug for a task, examine the kettle first',       # wrong / instance-specific
    'When placing a cooled object in a container, use the move command instead of opening',   # wrong
    'When a stoveburner already has a kettle on it',  # instance-specific
    'When an object must be picked up and placed: use inventory to check',   # useless (LOG 11-19)
    'When a sinkbasin is empty, check it before',     # meaningless
]

VARIANT_SYSTEM = ('You write test data for a study of rule libraries of an ALFWorld household agent (text '
                  'commands: go to, take, put/move, open, close, clean/heat/cool X with Y, use desklamp). '
                  'Return only one JSON object.')
VARIANT_PROMPT = """A rule from the agent's rule manual:
type: {type}
kind of task: {kind} ({kind_text})
rule: {rule}

Write variants of it. Each variant is ONE sentence of at most 35 words starting with "When".
Return JSON with exactly these keys:
"paraphrases": 2 rules that say the same thing in clearly different words;
"near_duplicates": 2 rules with almost the same words (a few words changed or reordered);
"more_general": 1 rule giving the same advice for a broader situation, still correct in ALFWorld;
"more_specific": 2 objects {{"object": <an ALFWorld object that this kind of task can be about, lowercase, e.g. mug, apple, pillow, cd, soapbar>, "rule": <the same advice for tasks about that object only, e.g. "When the task object is a mug, ...">}};
"other_kind": 2 objects {{"kind": <one of: {others}>, "rule": <a correct, useful rule in the same spirit for that kind of task (in ALFWorld: clean X with sinkbasin, heat X with microwave, cool X with fridge, examine X by using the desklamp while holding X, two = find and place two objects one at a time)>}};
"vague": 1 rule that sounds helpful but says nothing concrete (a platitude);
"wrong": 1 rule that sounds plausible but is factually wrong for ALFWorld;
"instance_specific": 1 rule tied to one particular game (names a numbered receptacle like "cabinet 4" and an object)."""


def actions(text):
    return {k for k, p in ACTIONS.items() if re.search(rf'\b(?:{p})\b', text, re.IGNORECASE)}


def short(task_type):
    return SHORT.get(task_type, task_type)


def recipes(pool):
    """One real Success Process per kind: the one with most wins (then most contexts)."""
    out = {}
    for r in pool:
        if r['type'] != 'Success Process' or r.get('task_type') not in KINDS:
            continue
        score = (manual.observed(r)[0], len(r.get('contexts', [])))
        if r['task_type'] not in out or score > out[r['task_type']][0]:
            out[r['task_type']] = (score, r)
    return [out[k][1] for k in KINDS if k in out]


def generate_variants(pool, chat, path, round_=0):
    """Model-written variants of each real non-recipe rule (cached on disk and in the chat cache). Round 0:
    temperature 0.2; later rounds: temperature 0.9 with seed = round (more, different variants)."""
    path = Path(path)
    bases = [r for r in pool if r['type'] != 'Success Process']

    def one(r):
        kind = short(r['task_type'])
        others = ', '.join(k for k in KIND_TEXT if k != kind)
        prompt = VARIANT_PROMPT.format(type=r['type'], kind=kind if kind in KIND_TEXT else 'all kinds',
                                       kind_text=KIND_TEXT.get(kind, 'any task'), rule=r['rule'], others=others)
        return {"parent": r["rule"], "data": chat.ask_json(VARIANT_SYSTEM, prompt, temperature=0.9 if round_ else 0.2, seed=round_)}
    out = chat.map(one, bases)
    path.write_text(json.dumps(out, indent=1))
    return out


def flatten(variants, pool):
    """(class, text, parent rule, extra) candidates from the model output; malformed items dropped."""
    by_text = {r['rule']: r for r in pool}
    out = []
    for v in variants:
        parent, d = by_text.get(v['parent']), v['data']
        if parent is None:
            continue

        def texts(key):
            x = d.get(key)
            x = x if isinstance(x, list) else [x]
            return [t.strip() for t in x if isinstance(t, str) and 5 < len(t.split()) <= 45]
        for cls in ('paraphrases', 'near_duplicates', 'more_general', 'vague', 'wrong', 'instance_specific'):
            for t in texts(cls):
                out.append({'cls': cls, 'text': t, 'parent': parent})
        for item in d.get('more_specific') or []:
            if isinstance(item, dict) and isinstance(item.get('rule'), str):
                objs = objects_in(item['rule'])
                if objs and len(item['rule'].split()) <= 45:
                    out.append({'cls': 'more_specific', 'text': item['rule'].strip(), 'parent': parent,
                                'objects': sorted(objs)})
        for item in d.get('other_kind') or []:
            if isinstance(item, dict) and item.get('kind') in KIND_TEXT and isinstance(item.get('rule'), str):
                if item['kind'] != short(parent['task_type']) and len(item['rule'].split()) <= 45:
                    out.append({'cls': 'other_kind', 'text': item['rule'].strip(), 'parent': parent,
                                'kind': item['kind']})
    return out


TEMPLATES = {
    'simple': ('put a {o} in {r}.', 'put some {o} on {r}.'),
    'look': ('examine the {o} with the desklamp.', 'look at {o} under the desklamp.'),
    'clean': ('clean some {o} and put it in {r}.', 'put a clean {o} in {r}.'),
    'heat': ('heat some {o} and put it in {r}.', 'put a hot {o} in {r}.'),
    'cool': ('cool some {o} and put it in {r}.', 'put a cool {o} in {r}.'),
    'two': ('put two {o} in {r}.', 'find two {o} and put them in {r}.'),
}


def goal_bank():
    """ALFWorld-style goals of every practice game in the manifest (template from the game folder name)."""
    import json as _json
    from .data import RUNS
    manifest = _json.loads((RUNS / 'manifest.json').read_text())
    bank = {k: [] for k in KINDS}
    for t in manifest['splits']['practice']:
        folder = t['id'].split('/')[1]
        parts = folder.split('-')
        kind, obj, recep = parts[0], parts[1].lower(), parts[3].lower()
        if kind in bank:
            tpl = TEMPLATES[short(kind)][zlib.crc32(folder.encode()) % 2]
            bank[kind].append(tpl.format(o=obj, r=recep))
    return {k: sorted(set(v)) for k, v in bank.items()}


def _evidence(rng, kind, goals, counts, objects=()):
    """(sources, contexts, alpha, beta) for a synthetic rule of `kind` (a task_type or 'all')."""
    won, lost = rng.choice(counts)

    def goal():
        k = kind if kind in goals else rng.choice(KINDS)
        pick = [g for g in goals[k] if objects and objects_in(g) & set(objects)] if objects else []
        if objects and not pick:
            obj = rng.choice(sorted(objects))
            return k, rng.choice(TEMPLATES[short(k)]).format(o=obj, r='countertop')
        return k, rng.choice(pick or goals[k])
    k, g = goal()
    sources = [{'task': g, 'task_type': k}]
    contexts = []
    for i in range(min(won, manual.K_CONTEXTS)):
        k, g = goal()
        contexts.append({'task': g, 'task_type': k, 'won': True})
    for i in range(min(lost, manual.K_CONTEXTS)):
        k, g = goal()
        contexts.append({'task': g, 'task_type': k, 'won': False})
    return sources, contexts, 1 + won, 1 + lost


def candidates_in_order(pool, variants, seed):
    """Real non-recipe rules (shuffled) first, then the shuffled variants: a library of N is a prefix."""
    rng = random.Random(seed)
    real = [r for r in pool if r['type'] != 'Success Process']
    rng.shuffle(real)
    var = list(variants)
    rng.shuffle(var)
    return real, var


def build(pool, variants, n, seed, similarity, goals, junk_counts="same", other_kind_junk=False, junk_share=0.2):
    """(rules, meta, stats): a library with n visible rules; meta[id] = labeling data. junk_share: the share of
    junk kept constant as variants are added (None: as generated, which raises it with N)."""
    rng = random.Random(seed * 7919 + 1)
    counts = [tuple(manual.observed(r)) for r in pool if r['type'] != 'Success Process']
    rules, meta, skipped = [], {}, {}
    group_of = {}

    def add(rule, info):
        rule = dict(rule, id=f'rule_{len(rules) + 1}')
        rules.append(rule)
        meta[rule['id']] = info

    for r in recipes(pool):
        group_of[r['rule']] = f"g{len(group_of)}"
        add(r, {'cls': 'real', 'group': group_of[r['rule']], 'junk': False, 'objects': []})
    real, var = candidates_in_order(pool, variants, seed)
    for r in real:
        if len(rules) >= n:
            break
        group_of[r['rule']] = f"g{len(group_of)}"
        junk = any(r['rule'].startswith(j) for j in HAND_JUNK)
        # A real rule that names objects ("When searching for a bowl, ...") applies only to tasks about them.
        add(r, {'cls': 'real', 'group': group_of[r['rule']], 'junk': junk, 'objects': sorted(objects_in(r['rule']))})
    junk_now = sum(m['junk'] for m in meta.values())
    pending, deferred = list(var), []
    while pending and len(rules) < n:
        v = pending.pop(0)
        parent = v['parent']
        junk = (v['cls'] in ('vague', 'wrong', 'instance_specific')
                or any(parent['rule'].startswith(j) for j in HAND_JUNK)     # variants of junk are junk
                or (other_kind_junk and v['cls'] == 'other_kind'))   # sensitivity: transfer labels are noisy
        room = junk_share is None or junk_now + 1 <= junk_share * (len(rules) + 1)
        if junk and not room:
            deferred.append(v)       # keep the library's junk share fixed: size, not composition, varies
            continue
        if not junk and deferred and room:
            pending.insert(0, v)
            v, junk = deferred.pop(0), True
            parent = v['parent']
        if v['cls'] == 'other_kind':
            scope = LONG[v['kind']]
        elif v['cls'] == 'more_general' and not actions(v['text']):
            scope = 'all'
        else:
            scope = parent['task_type']
        kind = parent['type']
        if manual.near_duplicate(rules, kind, scope, v['text'], similarity, scope) is not None:
            skipped[v['cls']] = skipped.get(v['cls'], 0) + 1
            continue
        objects = sorted(objects_in(v['text']))
        junk_now += junk
        sources, contexts, a, b = _evidence(rng, scope, goals, counts, objects)
        if junk and junk_counts == "worse" and a > b:     # sensitivity: junk loses more often than it wins
            a, b = b, a
            contexts = [dict(c, won=not c["won"]) for c in contexts]
        rule = manual.new_rule('x', kind, v['text'], '', scope, sources=sources)
        rule.update(alpha=a, beta=b, contexts=contexts)
        if v['cls'] in ('paraphrases', 'near_duplicates'):
            group = group_of.get(parent['rule']) or group_of.setdefault(parent['rule'], f"g{len(group_of)}")
        else:
            group = f"v{len(rules)}"
        add(rule, {'cls': v['cls'], 'group': group, 'objects': objects,
                   "junk": junk})
    return rules, meta, {'size': len(rules), 'merge_gate_skipped': skipped}


def label(rule, info, query):
    """(gain, junk, wrong_kind) of a rule for a query; see the module docstring."""
    kind = short(query['task_type'])
    scope = rule.get('task_type')
    wrong = (scope not in (query['task_type'], 'all', None)) or bool(actions(rule['rule']) - {kind})
    if info['junk']:
        return 0, True, wrong
    if wrong:
        return 0, False, True
    if (info['objects'] and rule['type'] != 'Success Process'
            and not (set(info['objects']) & objects_in(query['goal']))):
        return 0, False, False
    return (2 if rule['type'] == 'Success Process' else 1), False, False
