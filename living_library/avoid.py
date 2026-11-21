"""Anti-Pattern rules: "When <situation>, do not <X>." for kinds of task the agent keeps losing.

Negative results become memory only when they repeat. A rule of this type is written from a POOL of
never-won attempts of one kind of task (several games, each with its first attempt and its failed
Reflexion retries), never from one game. It states only what to avoid, taken from what the trajectories
show, never a guessed cause and never a guessed fix.

Followed from the literature:
  * ExpeL (Zhao et al., AAAI 2024, sec. 4.2): insights are extracted by comparing failures with
    successes of the same kind of task; here the contrast set is the won attempts (and the commands the
    game ever accepted) of the kind, and a pattern that also appears there is not an anti-pattern.
  * Reflexion (Shinn et al., 2023): failed attempts are the raw material (the pool holds every failed
    retry), but a single reflection is a guess; only what recurs across games is kept.
  * AutoManual (Chen et al., NeurIPS 2024): the Unresolved Error type (what failed, no guessed cause,
    no impossibility claims); the Anti-Pattern is its pooled, pattern-checked, agent-visible form.
  * MACLA (Forouzandeh et al., AAMAS 2026): contrastive evidence (a pattern needs failures and a
    clear contrast), and a later win of the kind re-checks the rule (kept if the pattern still never
    occurs in wins, retired otherwise).

Mechanism (deterministic parts first, the language model only words what the measurement says):
  1. Pool (one hidden "Failure Pool" entry per kind of task): lost games that were never won, as compact
     (command, accepted) lists per attempt; the won attempts of the kind; the command forms the game
     ever accepted.
  2. Mining: a pattern is (a) an invalid command form never accepted anywhere in the kind
     ("place <X> on <X>", "done"); (b) a command repeated 3+ times in a row; (c) two commands
     alternated 3+ times; (d) a task-specific command form (heat/cool/clean/use/toggle/slice/move
     <object> to <place>) used in lost attempts and in none of >= 3 won attempts. It must appear in
     >= 2 different task instances, >= 4 lost attempts and half of the pooled games, and in no won
     attempt. A pattern shared by every kind of attempt (won too) or tied to one instance is dropped.
  3. Wording: the model gets the measured pattern and writes one rule or declines (null).
  4. Post-checks in code: the usual rule form (<= 25 words, no numbered entity, no object kind), a
     negation, no cause or advice words, every command word of the rule is one the pattern or the kind of
     task supplies, and every word the pattern consists of is named. One repair round with the reasons.
  5. Upkeep (redesign of 2026-11-20, LIBRARY-SPEC.md section 5): the rule is a normal rule for retrieval
     and the evidence (used = cited for the plan, harm from the trace). It is retired as useless (shown but
     rarely used), as bad (harmful in most of its uses; an Anti-Pattern is never refined, and the Builder never
     rewrites it), or by this module's own contradiction check: a won attempt of the kind contains its
     pattern (recheck).
"""
import collections
import json
import re

TYPE = 'Anti-Pattern'
POOL = 'Failure Pool'
MIN_GAMES = 2          # different task instances whose lost attempts show the pattern
MIN_ATTEMPTS = 4       # lost attempts showing it
MIN_SHARE = 0.5        # of the pooled never-won games (a command the game never accepts needs only a quarter)
MIN_SHARE_INVALID = 0.25
MIN_WON = 3            # won attempts of the kind needed to call a task command "never used in wins"
LOOP_REPEAT = 3        # a command repeated, or a pair alternated, this many times
MAX_POOL_GAMES = 12
MAX_WON = 12
MAX_STEPS = 40
MAX_ASKS = 2           # candidates offered to the model per game
MAX_WORDS = 25

OBJECTS = set("""alarmclock apple baseballbat basketball book bowl box bread butterknife candle cd cellphone
    cloth creditcard cup dishsponge egg fork glassbottle kettle keychain knife ladle laptop lettuce mug
    newspaper pan papertowelroll pen pencil peppershaker pillow plate plunger pot potato remotecontrol
    saltshaker soapbar soapbottle spatula spoon spraybottle statue teddybear tissuebox toiletpaper tomato
    towel vase watch winebottle""".split())
PLACES = set("""cabinet drawer countertop shelf diningtable sidetable desk dresser bed sofa armchair coffeetable
    garbagecan safe bathtubbasin bathtub sinkbasin sink toilet toiletpaperhanger towelholder handtowelholder
    microwave fridge stoveburner toaster coffeemachine desklamp floorlamp lamp ottoman cart tvstand
    countertop""".split())
VERBS = set("""take open close go examine look use heat cool clean slice toggle move put place pick drop inventory
    done turn""".split())
FUNCTIONAL = {'heat', 'cool', 'clean', 'use', 'toggle', 'slice', 'move', 'put', 'place'}
SYNONYMS = {'move': {'put', 'place'}, 'put': {'move', 'place'}, 'place': {'move', 'put'}}
PREPOSITIONS = {'to', 'from', 'in', 'on', 'with', 'at', 'the', 'a'}
CUES = {'repeat', 'again', 'loop', 'over', 'cycl', 'alternat', 'back', 'forth', 'consecut'}
TASK_WORDS = {'heat': {'heat', 'hot', 'warm'}, 'cool': {'cool', 'cold'}, 'clean': {'clean', 'dirty'},
              'look': {'light', 'lamp', 'desklamp'}}
BANNED = re.compile(r"\b(because|since|so that|therefore|causes?|caused|due to|in order|leads? to|results? in|"
                    r"waste[sd]?|wasting|pointless|useless|impossible|instead|rather|better|try|first|then|"
                    r"otherwise|unless|should(?! not)|must(?! (?:be|not)\b))\b", re.IGNORECASE)
NEGATION = re.compile(r"\b(do not|don't|never|avoid|must not|should not)\b", re.IGNORECASE)
GENERIC = {'use', 'uses', 'using', 'used', 'go', 'goes', 'going'}   # ordinary English as much as commands
ENTITY = re.compile(r'\b([a-z]+) \d+\b')

AVOID_GUIDE = (
    'You write ONE avoid rule for an agent\'s manual (household text game, ALFWorld). The agent keeps losing '
    'one kind of task. Below is a pattern that was MEASURED in many lost games of this kind and in none of the '
    'won ones. State only what to avoid, as "When <situation>, do not <what the pattern shows>." (at most 25 '
    'words). Rules: describe the pattern as measured (the command, or the repetition), in general words ("the '
    'object", "an appliance", "the same command"), no numbers, no object names, no angle brackets. Use the given "rule_ending" '
    'as the end of your rule and write only the situation before it ("When <situation>, <rule_ending>"). Always name '
    'the command word itself (its verb, e.g. "place" or "examine") and any appliance the pattern contains. Do NOT say why it fails, do '
    'NOT say what to do instead, do not add commands or places the pattern does not contain, do not claim '
    'anything is impossible. Example of the form, for a different pattern: "When cleaning an object, do not '
    'alternate between opening and closing the sinkbasin." If the pattern cannot be stated without guessing, '
    'answer {"rule": null}. Output {"rule": "..."}.')
REPAIR_NOTE = ' Your earlier answer was rejected (see "rejected"); fix exactly those problems or answer {"rule": null}.'


# ----- command forms -------------------------------------------------------------------------------------

def _words(action):
    return ' '.join(str(action).lower().split())


def skeleton(action):
    """"place mug 1 on stoveburner 1" -> "place <X> on <X>"."""
    return ENTITY.sub('<X>', _words(action))


def family(action):
    """Like skeleton but keeping what kind of place and saying "<object>" for portable things:
    "move mug 1 to stoveburner 1" -> "move <object> to stoveburner"."""
    return ENTITY.sub(lambda m: '<object>' if m.group(1) in OBJECTS else m.group(1), _words(action))


def usable(action):
    """A command-shaped step (not free text the model wrote into the action)."""
    return 0 < len(_words(action).split()) <= 8


def compact(trace):
    return [[t['action'], 1 if t['valid'] else 0] for t in trace][:MAX_STEPS]


def loops(attempt):
    """Loop signatures in one attempt: ('repeat', form) for the SAME command (same words and numbers, so
    visiting different drawers is not a loop) issued LOOP_REPEAT+ times in a row, ('cycle', a, b) for two
    commands alternated LOOP_REPEAT+ times; the signature is the command form (numbers dropped)."""
    exact = [_words(a) if usable(a) else None for a, _ in attempt]
    found, n, i = set(), len(exact), 0
    while i < n:
        j = i
        while j + 1 < n and exact[j + 1] == exact[i]:
            j += 1
        if exact[i] and j - i + 1 >= LOOP_REPEAT:
            found.add(('repeat', family(exact[i])))
        i = j + 1
    for i in range(n - 1):
        a, b = exact[i], exact[i + 1]
        if a and b and a != b:
            k = 0
            while i + 2 * k + 1 < n and exact[i + 2 * k] == a and exact[i + 2 * k + 1] == b:
                k += 1
            if k >= LOOP_REPEAT:
                found.add(('cycle', *sorted((family(a), family(b)))))
    return found


def signatures(attempt):
    """{signature: an example command} for one attempt: invalid forms, loops, task commands used."""
    out = {}
    for action, valid in attempt:
        if not usable(action):
            continue
        if not valid:
            out.setdefault(('invalid', skeleton(action)), action)
        elif _words(action).split()[0] in FUNCTIONAL:
            out.setdefault(('used', family(action)), action)
    for sig in loops(attempt):
        out.setdefault(sig, '')
    return out


# ----- pool ----------------------------------------------------------------------------------------------

def new_entry(task_type):
    return {'games': [], 'won': [], 'accepted': [], 'retired': [], 'declined': {}, 'task_type': task_type}


def _accept(entry, attempt):
    forms = set(entry['accepted'])
    forms.update(skeleton(a) for a, v in attempt if v and usable(a))
    entry['accepted'] = sorted(forms)


def add_game(entry, game):
    """A never-won game: {'task_id', 'task', 'attempts': [compact attempt, ...]}."""
    entry['games'] = [g for g in entry['games'] if g['task_id'] != game['task_id']] + [game]
    entry['games'] = entry['games'][-MAX_POOL_GAMES:]
    for attempt in game['attempts']:
        _accept(entry, attempt)


def add_won(entry, attempt):
    entry['won'] = (entry['won'] + [attempt])[-MAX_WON:]
    _accept(entry, attempt)


def key(sig):
    return json.dumps(list(sig))


def pool_entry(rules, task_type):
    return next((r for r in rules if r.get('type') == POOL and r.get('task_type') == task_type), None)


def apply_pool_op(rules, op, next_id):
    """Apply a pool operation ('pool_game' / 'pool_won') to the pool entry of its kind (created if needed)."""
    entry_rule = pool_entry(rules, op['task_type'])
    if entry_rule is None:
        from . import manual
        entry_rule = manual.new_rule(next_id(), POOL, 'failure pool', '', op['task_type'])
        entry_rule['pool'] = new_entry(op['task_type'])
        rules.append(entry_rule)
    if op['op'] == 'pool_game':
        add_game(entry_rule['pool'], op['game'])
    else:
        add_won(entry_rule['pool'], op['attempt'])
        for other in op.get('others', []):     # the game's earlier, lost attempts: only what the game accepted
            _accept(entry_rule['pool'], other)
    return entry_rule['pool']


# ----- mining --------------------------------------------------------------------------------------------

def contrast_clear(sig, entry):
    """No contrary evidence: the pattern never occurs in a won attempt of the kind (and, for an invalid
    command form, the game never accepted it)."""
    if any(sig in signatures(a) for a in entry['won']):
        return False
    if sig[0] == 'invalid' and sig[1] in set(entry['accepted']):
        return False
    if sig[0] == 'used' and len(entry['won']) < MIN_WON:
        return False
    return True


def mine(entry):
    """Candidate anti-patterns of a pool, best first; each says how much evidence stands behind it."""
    games = entry['games']
    task_ids = {g['task_id'] for g in games}
    attempts_total = sum(len(g['attempts']) for g in games)
    seen = collections.defaultdict(lambda: {'games': set(), 'attempts': 0, 'example': ''})
    for g in games:
        for attempt in g['attempts']:
            for sig, example in signatures(attempt).items():
                s = seen[sig]
                s['games'].add(g['task_id'])
                s['attempts'] += 1
                s['example'] = s['example'] or example
    found = []
    for sig, s in seen.items():
        if (len(s['games']) < MIN_GAMES or s['attempts'] < MIN_ATTEMPTS
                or len(s['games']) / len(task_ids) < (MIN_SHARE_INVALID if sig[0] == 'invalid' else MIN_SHARE)
                or not contrast_clear(sig, entry)):
            continue
        if sig[0] == 'used' and sig[1].split()[0] not in FUNCTIONAL:
            continue
        found.append({'sig': list(sig), 'kind': sig[0], 'games': len(s['games']), 'of_games': len(task_ids),
                      'attempts': s['attempts'], 'of_attempts': attempts_total, 'wins_checked': len(entry['won']),
                      'example': s['example']})
    invalid = {c['sig'][1].split()[0] for c in found if c['kind'] == 'invalid'}
    found = [c for c in found if not (c['kind'] == 'repeat' and c['sig'][1].split()[0] in invalid)]
    found.sort(key=lambda c: (c['games'] / c['of_games'], c['games'], c['attempts']), reverse=True)
    return found


def plain(form):
    """A command form in words: "place <X> on <X>" -> "place something on something"."""
    return form.replace('<X>', 'something').replace('<object>', 'an object')


def describe(cand):
    """The pattern as measured, for the model."""
    sig = cand['sig']
    if cand['kind'] == 'invalid':
        what = f'the command "{plain(sig[1])}" was rejected by the game, which answered "Nothing happens."'
    elif cand['kind'] == 'repeat':
        what = f'the same command "{plain(sig[1])}" was issued {LOOP_REPEAT} or more times in a row'
    elif cand['kind'] == 'cycle':
        what = (f'the commands "{plain(sig[1])}" and "{plain(sig[2])}" alternated {LOOP_REPEAT} or more times '
                'in a row')
    else:
        what = f'the command "{plain(sig[1])}" was used'
    seen = (f"seen in {cand['games']} of {cand['of_games']} different lost tasks and in {cand['attempts']} of "
            f"{cand['of_attempts']} lost attempts")
    never = (f"never in the {cand['wins_checked']} won attempts of this kind of task" if cand['wins_checked']
             else 'no won attempt of this kind exists yet')
    if cand['kind'] == 'invalid':
        never = 'the game never accepted this command in any attempt of this kind of task, won or lost'
    return {'pattern': what, 'seen': seen, 'contrast': never, 'rule_ending': ending(cand)}


def ending(cand):
    """The second half of the rule, fixed by the measurement; the model only chooses the situation."""
    sig = cand['sig']
    verb = lambda form: form.split()[0]
    if cand['kind'] == 'invalid':
        return f'do not use the command "{verb(sig[1])}".'
    if cand['kind'] == 'repeat':
        return f'do not issue the same "{verb(sig[1])}" command again and again.'
    if cand['kind'] == 'cycle':
        return f'do not alternate between "{verb(sig[1])}" and "{verb(sig[2])}" over and over.'
    kinds = [w for w in re.findall(r'[a-z]+', sig[1]) if w in PLACES]
    return f'do not {verb(sig[1])} an object {"to" if " to " in sig[1] else "with"} {kinds[0] if kinds else "that place"}.'


# ----- grounding checks ----------------------------------------------------------------------------------

def stem(word):
    word = word.lower()
    for suffix in ('ing', 'ed', 'es', 's'):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[:-len(suffix)]
            break
    return word[:-1] if word.endswith('e') and len(word) > 3 else word


COMMAND_VOCAB = {stem(w) for w in VERBS | PLACES | OBJECTS}


def pattern_words(sig):
    """Command words the pattern consists of (verbs and kinds of place), as stems."""
    words = set()
    for form in sig[1:]:
        for w in re.findall(r'[a-z]+', form):
            if w not in PREPOSITIONS and w != 'object' and w != 'x':
                words.add(w)
    verbs = {w for w in words if w in VERBS}
    for v in list(verbs):
        words |= SYNONYMS.get(v, set())
    return {stem(w) for w in words}


def required_groups(sig, accepted):
    """Alternatives groups the rule must each touch: the verbs of the pattern, kinds where they matter."""
    groups = []
    verbs = [f.split()[0] for f in sig[1:]]
    for v in verbs:
        groups.append({stem(v)} | {stem(s) for s in SYNONYMS.get(v, set())})
    if sig[0] in ('repeat', 'cycle'):
        groups.append(set(CUES))
    if sig[0] == 'used':
        kinds = [w for w in re.findall(r'[a-z]+', sig[1]) if w in PLACES]
        groups += [{stem(k)} for k in kinds]
    if sig[0] == 'invalid':
        verb = verbs[0]
        if any(s.split()[0] == verb for s in accepted):     # the verb works elsewhere: the kinds matter
            groups += [{stem(w)} for w in re.findall(r'[a-z]+', sig[1]) if w in PLACES]
    return groups


def task_words(task_type):
    out = set()
    for name, words in TASK_WORDS.items():
        if name in (task_type or ''):
            out |= words
    return {stem(w) for w in out}


ALL_CHECKS = ('form', 'negation', 'banned', 'objects', 'grounded', 'required')


def judge(text, cand, task_type, accepted=(), checks=ALL_CHECKS):
    """Why rule text is not an acceptable anti-pattern (empty list if it is)."""
    from . import manual
    problems = list(manual.rule_problems(TYPE, text)) if 'form' in checks else []
    if 'form' in checks and not re.match(r'(when|if)\b', text.strip(), re.IGNORECASE):
        problems.append('must start with "When" or "If"')
    if 'negation' in checks and not NEGATION.search(text):
        problems.append('must say what NOT to do ("do not ...")')
    if 'banned' in checks:
        found = BANNED.search(text)
        if found:
            problems.append(f'gives a cause or advice ({found.group(0)!r}); state only what to avoid')
    tokens = re.findall(r"[a-z]+", text.lower())
    if 'form' in checks and re.search(r'[<>]', text):
        problems.append('contains angle brackets; say "something" or "the object"')
    if 'objects' in checks:
        named = [w for w in tokens if w.rstrip('s') in OBJECTS or w in OBJECTS]
        if named:
            problems.append(f'names an object kind ({named[0]!r}); say "the object"')
    sig = tuple(cand['sig'])
    if 'grounded' in checks:
        allowed = pattern_words(sig) | task_words(task_type)
        extra = sorted({w for w in tokens if stem(w) in COMMAND_VOCAB and stem(w) not in allowed
                        and w not in GENERIC})
        if extra:
            problems.append(f"names {extra} which the measured pattern does not contain")
    if 'required' in checks:
        stems = {stem(w) for w in tokens} | {w[:5] for w in tokens}
        for group in required_groups(sig, accepted):
            if not any(g in stems or g[:5] in stems for g in group):
                problems.append(f"does not name {sorted(group)[0]!r}, which the pattern consists of")
    return problems


# ----- wording -------------------------------------------------------------------------------------------

def kind_info(entry):
    goals = list(dict.fromkeys(g['task'] for g in entry['games'] if g.get('task')))
    return {'name': entry.get('task_type'), 'example_goals': goals[:3]}


def write(ask, entry, cand, checks=ALL_CHECKS):
    """Ask the model to word one candidate; one repair round. Returns (text or None, notes)."""
    payload = {'instructions': AVOID_GUIDE, 'kind_of_task': kind_info(entry), 'evidence': describe(cand),
               'response_schema': {'rule': 'string, or null if it cannot be stated without guessing'}}
    rejected, notes = [], []
    from . import manual
    for attempt in range(2):
        data = ask('avoider', {**payload, **({'rejected': rejected,
                                             'instructions': AVOID_GUIDE + REPAIR_NOTE} if rejected else {})})
        text = data.get('rule')
        if not isinstance(text, str) or not text.strip():
            notes.append('declined')
            return None, notes
        text = manual.tidy(text)
        problems = judge(text, cand, entry.get('task_type'), entry['accepted'], checks)
        if not problems:
            return text, notes
        notes.append(f'rejected {text[:70]!r}: {"; ".join(problems)}')
        rejected = [{'rule': text, 'problems': problems}]
    return None, notes


def example_of(cand):
    sig = cand['sig']
    if cand['kind'] == 'invalid':
        return f'"{sig[1]}" answers "Nothing happens."'
    if cand['kind'] == 'repeat':
        return f'"{sig[1]}", again and again'
    if cand['kind'] == 'cycle':
        return f'"{sig[1]}" then "{sig[2]}", over and over'
    return f'"{sig[1]}"'


def known(rules, entry):
    keys = {key(r['pattern']['sig']) for r in rules if r.get('type') == TYPE and r.get('pattern')}
    return keys | {key(s) for s in entry['retired']}


def update(ask, rules, task_type, goal, task_id, attempts, won, next_id, log, append_only=False,
           checks=ALL_CHECKS):
    """After a practice game. `attempts`: compact attempts (the first, then each retry); `won`: whether the
    game was won at any attempt (the winning attempt is the last one). Mutates `rules`; returns the
    operations to replay. A lost game is pooled and may yield ONE new rule; a won game adds contrast and
    re-checks the kind's rules."""
    ops = []
    if won:
        op = {'op': 'pool_won', 'task_type': task_type, 'attempt': attempts[-1], 'others': attempts[:-1]}
        entry = apply_pool_op(rules, op, next_id)
        ops.append(op)
        if not append_only:
            ops += recheck(rules, task_type, entry, log)
        return ops
    op = {'op': 'pool_game', 'task_type': task_type,
          'game': {'task_id': task_id, 'task': goal, 'attempts': attempts}}
    entry = apply_pool_op(rules, op, next_id)
    ops.append(op)
    skip = known(rules, entry)
    asked = 0
    for cand in mine(entry):
        if key(cand['sig']) in skip or entry['declined'].get(key(cand['sig']), 0) >= cand['games']:
            continue
        if asked >= MAX_ASKS:
            break
        asked += 1
        try:
            text, notes = write(ask, entry, cand, checks)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            log.append(f'avoider: {exc}'[:200])
            break
        log.extend(f'anti-pattern {n}' for n in notes)
        if text is None:
            entry['declined'][key(cand['sig'])] = cand['games']
            continue
        from . import manual
        rule = manual.new_rule(next_id(), TYPE, text, example_of(cand), task_type,
                               sources=[{'task': goal, 'task_type': task_type}])
        rule['pattern'] = {**cand}
        rules.append(rule)
        ops.append({'op': 'write_rule', 'type': TYPE, 'rule': text, 'example': rule['example'],
                    'task_type': task_type, 'sources': rule['sources'], 'pattern': rule['pattern']})
        log.append(f"{rule['id']} anti-pattern written from {cand['games']} of {cand['of_games']} lost tasks")
        break
    return ops


def recheck(rules, task_type, entry, log):
    """A won attempt of the kind arrived: keep each Anti-Pattern rule whose pattern still never occurs in
    a won attempt (its evidence is refreshed), retire the others."""
    ops = []
    for rule in [r for r in rules if r.get('type') == TYPE and r.get('task_type') == task_type]:
        sig = tuple(rule['pattern']['sig'])
        if contrast_clear(sig, entry):
            rule['pattern']['wins_checked'] = len(entry['won'])
            continue
        forget(rules, rule)
        ops.append({'op': 'retire', 'id': rule['id'], 'reason': 'its pattern occurs in a won attempt'})
        log.append(f"retired {rule['id']} (anti-pattern contradicted by a won attempt of this kind of task)")
    return ops


def forget(rules, rule):
    """Remove an Anti-Pattern rule and remember its pattern so it is not written again."""
    if rule in rules:
        rules.remove(rule)
    entry = pool_entry(rules, rule.get('task_type'))
    if entry is not None and rule.get('pattern'):
        retired = entry['pool']['retired']
        if list(rule['pattern']['sig']) not in retired:
            retired.append(list(rule['pattern']['sig']))
