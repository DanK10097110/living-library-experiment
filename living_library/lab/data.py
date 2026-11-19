"""Real data for the lab: the pool of real rules (with contexts) and real queries (game goal, task type, plan)."""
import json
import re
from pathlib import Path

from .. import manual

ROOT = Path(__file__).resolve().parents[2]
RUNS = Path('/root/ll-runs')
KINDS = ('pick_and_place_simple', 'look_at_obj_in_light', 'pick_clean_then_place_in_recep',
         'pick_heat_then_place_in_recep', 'pick_cool_then_place_in_recep', 'pick_two_obj_and_place')
SHORT = {'pick_and_place_simple': 'simple', 'look_at_obj_in_light': 'look', 'pick_clean_then_place_in_recep': 'clean',
         'pick_heat_then_place_in_recep': 'heat', 'pick_cool_then_place_in_recep': 'cool',
         'pick_two_obj_and_place': 'two'}
# Words that tie a rule's CONTENT to one kind of task (used for labels; the scope field alone can be wrong).
CONTENT = {
    'clean': r'clean(?:s|ed|ing)?|sinkbasin|sink|rins\w*|wash\w*',
    'cool': r'cool(?:s|ed|ing)?|fridge|refrigerat\w*|chill\w*',
    'heat': r'heat(?:s|ed|ing)?|microwave|stoveburner|stove|warm\w*',
    'look': r'desklamp|floorlamp|lamp|light',
    'two': r'two objects|two items|both objects|both items|each object|second object|second item|'
           r'another (?:object|item|one)|two of',
}


def content_kinds(text):
    """Short kind names whose action/appliance words the rule text uses."""
    return {k for k, p in CONTENT.items() if re.search(rf'\b(?:{p})\b', text, re.IGNORECASE)}


def objects_in(text):
    """ALFWorld object names in a text (singular)."""
    from .. import avoid
    found = set()
    for w in re.findall(r'[a-z]+', text.lower()):
        if w in avoid.OBJECTS:
            found.add(w)
        elif w.endswith('s') and w[:-1] in avoid.OBJECTS:
            found.add(w[:-1])
    return found


def _norm(text):
    return re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()


def rule_files():
    """(label, path) of every real rule library: frozen copies in results/, practice runs and the study's E."""
    files = []
    for p in sorted((ROOT / 'results').glob('*/rules-full.json')):
        files.append((p.parent.name, p))
    for p in sorted((ROOT / 'results').glob('mini-macla-*/rules.json')):
        if not (p.parent / 'rules-full.json').exists():
            files.append((p.parent.name, p))
    for run in ('practice-b', 'practice-c', 'practice-d', 'practice-e', 'mini-macla', 'study'):
        stream = RUNS / run / 'checkpoints' / 'practice-E-0'
        last = sorted(stream.glob('*.json'))[-1:] if stream.exists() else []
        if last:
            files.append((f'wsl:{run}', last[0]))
    return files


def load_rules(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get('memory', {}).get('rules') or []
    return data


def real_pool():
    """Distinct real rules the agent can see (not Builder notes, not failure pools), deduplicated by text;
    the copy with the most evidence is kept. Each gets 'origin' (library label)."""
    best = {}
    for label, path in rule_files():
        for r in load_rules(path):
            if not manual.shown_to_agent(r) or r['type'] == manual.avoid.POOL:
                continue
            key = _norm(r['rule'])
            score = (len(r.get('contexts', [])), r.get('alpha', 1) + r.get('beta', 1))
            if key not in best or score > best[key][0]:
                best[key] = (score, dict(r, origin=label))
    return [v[1] for v in best.values()]


def _records(pattern):
    for stream in sorted(RUNS.glob(pattern)):
        for f in sorted(stream.glob('*.json')):
            try:
                rec = json.loads(f.read_text())['record']
            except (ValueError, KeyError):
                continue
            yield rec


def task_types():
    manifest = json.loads((RUNS / 'manifest.json').read_text())
    return {t['id']: t['task_type'] for split in manifest['splits'].values() for t in split}


def real_queries():
    """Development games (valid_seen, 'id') and evaluation games (valid_unseen, 'ood') with goal and plan,
    one per task id, from all checkpointed runs."""
    kinds = task_types()
    out = {}
    for pattern, split in (('*/checkpoints/development-*', 'id'), ('*/checkpoints/gate-*', 'id'),
                           ('*/checkpoints/evaluation-*', 'ood'), ('*/checkpoints/id-evaluation-*', 'id')):
        for rec in _records(pattern):
            tid, goal = rec.get('task_id'), rec.get('goal')
            if not tid or not goal or tid not in kinds:
                continue
            q = out.setdefault(tid, {'id': tid, 'goal': goal, 'task_type': kinds[tid], 'plan': '', 'split': split})
            if rec.get('plan') and not q['plan']:
                q['plan'] = rec['plan']
    return sorted(out.values(), key=lambda q: q['id'])


def practice_goals():
    """Goals (and plans) of real practice games by task type: evidence for synthetic rules."""
    kinds = task_types()
    out = {k: {} for k in KINDS}
    for rec in _records('*/checkpoints/practice-*'):
        tid, goal = rec.get('task_id'), rec.get('goal')
        if tid in kinds and goal and kinds[tid] in out:
            entry = out[kinds[tid]].setdefault(goal, {'task': goal, 'plan': ''})
            if rec.get('plan') and not entry['plan']:
                entry['plan'] = rec['plan']
    return {k: sorted(v.values(), key=lambda e: e['task']) for k, v in out.items()}


def snapshot(path=ROOT / 'results' / 'lab' / 'data' / 'real.json'):
    """Write the real pool, queries and practice goals once (the bench then runs from this file)."""
    data = {'rules': real_pool(), 'queries': real_queries(), 'practice_goals': practice_goals(),
            'files': [[label, str(p)] for label, p in rule_files()]}
    Path(path).write_text(json.dumps(data, indent=1))
    return data
