"""Batched practice: k games run at once from the same memory, then merge in a fixed order.

Each game of a batch is still its own episode (own trace, own record). It runs on a private copy
of the memory as it was at the start of the batch. Afterwards the main process applies each
game's changes, in position order, to the live memory:

  new skill versions   added; a second new skill with a name that is already active (two games of
                       the batch wrote the same skill) is dropped as a duplicate, as it would have
                       been sequentially; a revision whose parent is no longer active is dropped
  usage counters       success/failure counts, streaks, tests and failure notes add up
  status / active map  applied when the live memory still has the value the game started from
                       (otherwise an earlier game of the batch already changed it)
  E-plus bookkeeping   usage statistics and pair counts add up, lessons are united and their
                       scores add up, failure/success examples are appended / replaced
  D trajectories       successful traces are appended

Every skill a game admitted already passed its replay gate inside that game. With k = 1 the merge
returns exactly the game's own final memory, i.e. sequential practice.
"""
import copy

COUNTERS = ('successes', 'failures')


def _skills(library):
    return {s['id']: s for s in library['skills']}


def _name(sid):
    return sid.split('@')[0]


def merge_library(live, base, end, log):
    """Apply the change base -> end (one game) onto live; returns the new live library."""
    out = copy.deepcopy(live)
    skills, before, after = _skills(out), _skills(base), _skills(end)
    active_base, active_end = base['active'], end['active']
    for sid, s in after.items():
        if sid not in before:                                   # written by this game
            name = _name(sid)
            if sid in skills:                                   # an earlier game wrote the same version id
                log.append(['duplicate', sid])
                continue
            if active_end.get(name) == sid and out['active'].get(name) != active_base.get(name):
                # An earlier game of the batch already added or replaced this skill name.
                log.append(['superseded', sid])
                continue
            out['skills'].append(copy.deepcopy(s))
            skills[sid] = out['skills'][-1]
            continue
        target, old = skills.get(sid), before[sid]
        if target is None:
            continue
        gained = {key: s[key] - old[key] for key in COUNTERS}
        for key in COUNTERS:
            target[key] += gained[key]
        if gained['successes']:
            target['streak'] = s['streak']                      # trailing failures after its last success
        elif gained['failures']:
            target['streak'] += gained['failures']
        for key in ('tests', 'failure_notes'):
            for item in s[key][len(old[key]):]:
                if item not in target[key]:
                    target[key].append(copy.deepcopy(item))
        if s['status'] != old['status'] and target['status'] == old['status']:
            target['status'] = s['status']
    for name in set(active_base) | set(active_end):
        was, now = active_base.get(name), active_end.get(name)
        if was == now:
            continue
        if out['active'].get(name) == was and (now is None or now in skills):
            if now is None:
                out['active'].pop(name, None)
            else:
                out['active'][name] = now
    out['active'] = {n: sid for n, sid in sorted(out['active'].items())}
    # Keep status consistent with the active map (e.g. a revision dropped as superseded leaves its
    # parent active): active <=> in the map; an "active" skill no longer in the map was replaced.
    current = set(out['active'].values())
    for s in out['skills']:
        if s['id'] in current:
            s['status'] = 'active'
        elif s['status'] == 'active':
            s['status'] = 'fallback'
    meta = _merge_meta(live.get('meta', {}), base.get('meta', {}), end.get('meta', {}))
    if meta:
        out['meta'] = meta
    else:
        out.pop('meta', None)
    return out


def _merge_meta(live, base, end):
    out = copy.deepcopy(live)
    if not end and not base:
        return out
    # usage evidence: add deltas
    for sid, stats in end.get('stats', {}).items():
        old = base.get('stats', {}).get(sid, {'offered': 0, 'chosen': 0, 'ok': 0, 'arguments': []})
        target = out.setdefault('stats', {}).setdefault(sid, {'offered': 0, 'chosen': 0, 'ok': 0, 'arguments': []})
        for key in ('offered', 'chosen', 'ok'):
            target[key] += stats[key] - old[key]
        for arguments in stats['arguments']:
            if arguments not in target['arguments'] and len(target['arguments']) < 10:
                target['arguments'].append(copy.deepcopy(arguments))
    for key, entry in end.get('pairs', {}).items():
        old = base.get('pairs', {}).get(key, {'count': 0})
        target = out.setdefault('pairs', {}).setdefault(key, {'count': 0})
        target['count'] += entry['count'] - old['count']
        if 'example' in entry:
            target['example'] = copy.deepcopy(entry['example'])
    for key in ('retired',):
        for sid, reason in end.get(key, {}).items():
            out.setdefault(key, {}).setdefault(sid, reason)
    for key in ('composed',):
        for item in end.get(key, []):
            if item not in out.setdefault(key, []):
                out[key].append(item)
    for key in ('age',):
        for sid, n in end.get(key, {}).items():
            out.setdefault(key, {})[sid] = max(out.get(key, {}).get(sid, 0), n)
    if 'consolidations' in end:
        out['consolidations'] = max(out.get('consolidations', 0), end['consolidations'])
    # lessons: unite by text, add score deltas; drop the ones this game's consolidation dropped
    old_lessons = {l['text']: l for l in base.get('lessons', [])}
    end_lessons = {l['text']: l for l in end.get('lessons', [])}
    live_lessons = {l['text']: l for l in out.get('lessons', [])}
    for text, lesson in end_lessons.items():
        if text in live_lessons:
            if text in old_lessons:
                for key in ('score', 'shown'):
                    live_lessons[text][key] += lesson[key] - old_lessons[text][key]
        else:
            live_lessons[text] = copy.deepcopy(lesson)
    for text in set(old_lessons) - set(end_lessons):
        live_lessons.pop(text, None)
    if live_lessons or 'lessons' in out:
        out['lessons'] = sorted(live_lessons.values(), key=lambda l: (-l['score'], l['id']))
    # reflector material
    for item in end.get('failures', []):
        if item not in base.get('failures', []) and item not in out.get('failures', []):
            out.setdefault('failures', []).append(copy.deepcopy(item))
    if 'failures' in end and not end['failures'] and base.get('failures'):
        out['failures'] = [f for f in out.get('failures', []) if f not in base['failures']]
    if 'failures' in out:
        out['failures'] = out['failures'][-6:]
    for kind, example in end.get('successes', {}).items():
        if base.get('successes', {}).get(kind) != example:
            out.setdefault('successes', {})[kind] = copy.deepcopy(example)
    return out


def merge_memory(live, base, end, log, rule_operations=()):
    """Memory = {'library', 'trajectories', 'rules'}: D appends successful practice traces; the
    rule manual replays the game's applied Builder operations onto the live rules (manual.replay; a rule's
    text changes at most once per batch, judged against the batch's starting rules `base['rules']`)."""
    from .manual import replay
    trajectories = copy.deepcopy(live['trajectories']) + copy.deepcopy(end['trajectories'][len(base['trajectories']):])
    merged = {'library': merge_library(live['library'], base['library'], end['library'], log),
              'trajectories': trajectories}
    if 'rules' in live or 'rules' in end:
        merged['rules'] = replay(live.get('rules', []), list(rule_operations), log, base.get('rules', []))
    return merged
