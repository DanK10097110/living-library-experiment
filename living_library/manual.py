"""A rule manual built from experience, after AutoManual (Chen et al., NeurIPS 2024, arXiv 2405.16247).

Adapted to this agent (a hierarchical step-by-step ReAct agent, not a code-writing planner):
  * A rule has a type, the rule text (it starts with when it applies), an example (a short action
    sequence or observation, not Python) and a validation note (AutoManual's validation log; never
    shown to the agent).
  * Types, as in AutoManual: Special Phenomenon/Mechanism, Success Process, Corrected Error,
    Unresolved Error. AutoManual's fifth type, Useful Helper Method (code), is not used (the code-skill
    library was removed on 2026-11-20).
  * After every practice game a Builder (the same local model) sees the game and the current rules.
    The case is decided from the game: direct success (won without an invalid action), indirect
    success (won after errors), failure. Case-conditioned prompting, as in AutoManual: the Builder
    first says whether the rules or the agent fell short, and each case limits what it may write.
    The limits are enforced in code, not only asked for.
  * No cap on the number of rules (AutoManual caps at 12 because it puts every rule in every prompt).
    Instead each rule carries a scope: the kind of task it came from, or "all". A game sees only the
    relevant rules (its kind's Success Process, then its kind's and general rules, newest first, at
    most SHOWN), and the Builder sees the rules relevant to the game it reviews (at most BUILDER_SEES),
    as the AutoManual authors suggest for scaling (retrieval, as in AutoGuide). One Success Process per
    task kind.
  * E-minus (append-only) may only write new rules: no note, no update, no delete, no merge.

Redesign of 2026-11-20 (LIBRARY-SPEC.md; reasons in ARCHITECTURE.md section 4, history in
results/DECISIONS.md). Rules start decent: all quality control on text happens when a rule is written (text
checks, plus a trace check that every command a rule instructs worked in the won game it came from). The text
the agent sees never changes because of one game: the Builder only writes rules, adds validation notes and
rewrites hidden Unresolved Error notes. Changes need evidence about the rule itself: after every practice game
(E and E-minus) a separate outcome-blind judge scores each shown rule on its own (followed yes/no, usefulness
-2..2; a judge failure gives no evidence). E only: a rule that is bad (>= MIN_EVIDENCE followed games and a
shrunk mean usefulness <= BAD_MEAN) is refined (at most MAX_REVISIONS texts after the first; a failed
refinement retires it) or else retired; a rule shown but rarely followed is retired as useless; capacity
pruning above CAPACITY. Removed: Beta reliability, base rates and lift, expected-utility ranking, ExpeL votes,
hidden guesses and their promotion, young/dead-recipe rewrites, command-rejection retirement, consolidation
(folding) and retrieval modes.

Selection and upkeep keep these parts of MACLA (Forouzandeh et al., AAMAS 2026, arXiv 2512.18950):
  * Selection: the kind's Success Process is always shown first. Rel is task-keyed, as in ExpeL/Memp (a
    memory is retrieved by the similarity of the current task to the tasks it came from / worked on),
    because short general rule text vs task text similarity is mostly noise: evidence = max similarity of
    the goal to the rule's source task(s) and to the tasks of games where it was judged helpful; text =
    similarity of goal and rule text; Rel = w * evidence + (1 - w) * text with w = h / (h + EVIDENCE_PRIOR),
    h = followed games with a positive score, so a new rule is ranked by its text. Rank = Rel + RANK_WEIGHT *
    mean usefulness (MACLA's expected utility, with the judge's usefulness in place of a win rate).
    Candidates: this kind's rules and the general ones; rules of other kinds
    only when the manual has no rule of this kind (an unseen kind of task) and their evidence >=
    CROSS_TYPE_EVIDENCE. (Goal similarity is dominated by the object: with bge-small, "heat some apple
    and put it in fridge" is 0.97 similar to "clean some apple and put it in fridge" but 0.81 to "heat
    some egg and put it in countertop", so other kinds' rules are never mixed into a known kind.)
    Deterministic, no LLM selector call (ExpeL/AutoGuide-style LLM selection would add a model call per
    game and its own noise; worth considering only for manuals above ~50 rules per kind).
  * Refinement (sec. 4.3, contrastive): a bad rule is rewritten from its stored contexts where it helped
    and where it misled (with the judge's reasons). A rule's "contexts" are this refinement's evidence, not
    rules: the last K_CONTEXTS judged games with a positive and with a negative score, current text only.
    They are never shown to the agent or the Builder, only to the refiner.
  * Merging (sec. 4.1/5.1): a new rule with similarity >= DUP_SIMILARITY to an existing rule of the
    same type and kind of task, or to a general ("all") one, is merged into it (its task kept as extra
    evidence, no text change) instead of added. Merging never widens a rule's scope.
  * Pruning (eq. 8, simplified): above CAPACITY rules, hidden notes oldest first, then the lowest mean
    usefulness, then the least recently used.
  * Not taken: meta-procedures (the paper's description is inconsistent and its code never uses them).
E-minus is append-only: it writes and is judged and ranked like E, but never changes or removes anything.
In batched practice E's refine and bad-retire ops are replayed only if the rule is still bad on the live
rules, with at most one text change per rule per batch; useless retirement, the near-duplicate merge
(batch_dedupe) and pruning run once per batch on the live rules (batch_upkeep).

Experience gathering follows ExpeL (Zhao et al., AAAI 2024, sec. 4.1), which uses Reflexion (Shinn et
al. 2023): when a practice game of E or E-minus is lost, the agent reflects on the failed attempt
(Reflexion's ALFWorld reflection prompt) and replays the same game from its start with the reflections
in view, up to RETRIES times, stopping at the first win. The Builder then gets the failed and the
successful attempt of the same task and writes a contrastive Corrected Error rule ("When <situation>, do
Y instead of X"); only if every retry fails does it write an Unresolved Error. Retries read the memory
(rules) but change nothing, and never run in evaluation or for C, D. The practice record keeps the FIRST
attempt (success, trace, judged evidence); retry costs are added to the game's totals and also reported
separately under "retries". E-minus retries too, so the ablation differs from E only in rule management.

Unresolved Error rules (from a failure without a contrasting success) are Builder notes only: they are
never shown to the agent and never judged (ExpeL extracts insights only from success/failure comparisons).
A lost game writes nothing else: won games rediscover anything true. A retry win may turn a note into a
Corrected Error (update_note) only if the per-rule judge says the winning retry followed the new text with
usefulness >= CONVERT_USEFULNESS and the text passes the write gate against the winning retry's trace.
Rules other than a Success Process may not list steps.

The Builder answers with JSON operations (write_rule / note / update_note), never code. If a game shows a
rule is wrong, it adds a validation note (never shown to the agent; the refiner reads it).

Rule form: both papers aim at short, general, reusable rules (AutoManual's rules; MACLA's abstract
procedures with preconditions). The Builder and refiner are asked for one general condition -> action
sentence (a Success Process: a few generic steps), and a cheap check in code rejects rule text that is
too long or names numbered objects ("drawer 3"); rejections are reported as errors. Instance numbers of
ALFWorld objects and receptacles are stripped first ("microwave 1" -> "the microwave"), and text that still
fails gets one model rewrite told its problems before it is rejected.
"""
import copy
import re

from . import avoid

# Writing and retrieval
DUP_SIMILARITY = 0.85        # MACLA sec. 5.1 theta_dup: a new rule this similar to an existing one is merged
CAPACITY = 200               # MACLA sec. 5.1 N_p; the lab measured 0.2-0.3 rules per game: never hit in 300
RETRIES = 3                  # ExpeL: up to 3 Reflexion retries of a failed practice game
RETRY_CONDITIONS = ('E', 'E-minus')
MAX_REFLECTION = 400         # characters; Reflexion asks for a few sentences
HIDDEN = ('Unresolved Error', avoid.POOL)    # Builder notes and the failure pools, never shown to the agent
EVIDENCE_PRIOR = 2           # retrieval: weight of task evidence = h / (h + 2); a new rule ranks by its text
CROSS_TYPE_EVIDENCE = 0.85   # evidence needed to show another kind's rule in an unseen kind of task
RANK_WEIGHT = 0.1            # rank = relevance + 0.1 m: usefulness reorders within a kind, not across kinds
MAX_SOURCES = 15             # source tasks kept per rule (written from + merged in): enough task evidence
MAX_WORDS = {'Success Process': 45, avoid.TYPE: avoid.MAX_WORDS}   # rule-text limit enforced in code
MAX_WORDS_DEFAULT = 35       # one sentence of at most 25 words is asked for; 10 words of slack
MAX_EXAMPLE = 200            # characters: one short line of real steps
MAX_NOTES = 3                # validation notes kept per rule, as in AutoManual's validation log
# Evidence (per-rule judge) and management (E only)
PRIOR = 2                    # m = sum / (followed + 2): one or two harsh scores cannot make a rule look bad
MIN_EVIDENCE = 6             # followed games before a rule can be bad (about 36 practice games for a recipe)
BAD_MEAN = -0.5              # m at or below this is bad: a net score of about -4 over 6 followed games
MAX_REVISIONS = 2            # text changes after the first text: at most 3 texts per rule, the cap on drift
USELESS_MIN = 12             # judged showings before a rule can be useless (simulator: 10 gave 0.9% false retirement at f 0.6)
USELESS_FOLLOWED = 0.2       # ... when followed in fewer than this share of them (under 1 game in 5)
K_CONTEXTS = 6               # refiner evidence: the last 6 helped and the last 6 misled games
CONTEXT_STEPS = 12           # valid actions kept per context: the end of a game, where it is decided
JUDGE_STEPS = 40             # valid actions shown to the judge: a whole typical game
JUDGE_OBSERVATION = 100      # characters of each observation shown to the judge: enough to see a failure
CONVERT_USEFULNESS = 1       # a retry must follow a note's new text at least this usefully to make it visible
SCORES = (-2, -1, 0, 1, 2)   # the judge's usefulness scale
RULE_FORM = (
    'A rule is ONE short, general sentence, "If/When <condition>, <action>.", at most 25 words, e.g. '
    '"If a container is closed, open it before putting things in it." It must help in other games too: '
    'say "the object", "the target", "a container" instead of this game\'s objects and places, never name '
    'numbered objects ("drawer 3"), never name a specific portable object (plate, tomato, fork, mug) or a '
    'room (a game is one room); write for the whole task type; never narrate a game ("the agent took ..."), do not start with the rule '
    'type. Only a Success Process may list steps: at most 5 short steps (at most 40 words) for a kind '
    'of task that carry what the games showed and is not obvious: which appliance or place does the job '
    'and the exact command form, where the object was found (places to search first), what must be '
    'opened; leave out obvious steps like "go to the target". Shape: "When an object must be <done> and '
    'placed: search <places> first, <exact command> with the <appliance>, open the target if closed, '
    'put it there."')
REFINE_GUIDE = (
    'A rule from an agent\'s manual was judged in several games of a household text game (ALFWorld): '
    'in helped_games following it helped, in misled_games following it misled the agent (with the judge\'s '
    'reason). Compare them and rewrite the rule so it helps in cases like the helped ones and does not '
    'mislead in cases like the misled ones: make its condition more precise (if it should not be used in '
    'some situation, say so inside the condition, e.g. "If ... and ..., ...") or correct its action. The '
    'validation notes say what later games showed. Rewrite it, do not add to it: the result must not be '
    'longer than the original. ' + RULE_FORM + ' Keep its type; use only commands the games show. '
    'Output {"rule": "..."}.')
JUDGE_GUIDE = (
    'Did the agent\'s actions follow this rule, and how useful was the rule in this game? You are not told how '
    'the game ended; do not guess it. usefulness: 2 = following it clearly moved the agent toward the goal '
    '(something it prescribes was needed and worked); 1 = it helped a little; 0 = not followed, or followed '
    'but made no difference; -1 = following it wasted steps; -2 = following it misled the agent (a prescribed '
    'command failed, or it pointed away from the goal). If not followed, usefulness is 0.')

SHOWN = 8           # rules shown to the planner and actor in a game (at most 8 judge calls per game)
BUILDER_SEES = 24   # rules shown to the Builder for the game it reviews
RARE_SHOWINGS = 3   # a rule shown in fewer games is "rarely shown": one shown slot is kept for the best of them
NEWEST_SLOTS = 2    # Builder slots for the newest rules not otherwise included, so it sees what batch-mates wrote
TYPES = ('Special Phenomenon', 'Success Process', 'Corrected Error', 'Unresolved Error', avoid.TYPE)
CASE_TYPES = {      # which rule types each case may WRITE (LIBRARY-SPEC section 3)
    'direct success': ('Success Process', 'Special Phenomenon'),
    'indirect success': ('Success Process', 'Special Phenomenon', 'Corrected Error'),
    'failure': ('Unresolved Error',),       # a lost game writes no visible rule
    # Lost, then won on a Reflexion retry of the same game (ExpeL's success/failure pair).
    'corrected failure': ('Corrected Error', 'Success Process', 'Special Phenomenon'),
}
MAX_WRITES = {'direct success': 2, 'indirect success': 2, 'failure': 1, 'corrected failure': 2}
REFLECT_GUIDE = (   # Reflexion's ALFWorld reflection prompt (Shinn et al. 2023), as used by ExpeL
    'You will be given the history of a past experience in which you were placed in an environment and '
    'given a task to complete. You were unsuccessful in completing the task. Do not summarize your '
    'environment, but rather think about the strategy and path you took to attempt to complete the task. '
    'Devise a concise, new plan of action that accounts for your mistake with reference to specific '
    'actions that you should have taken. For example, if you tried A and B but forgot C, then devise a '
    'plan to achieve C with environment-specific actions. You will need this later when you are solving '
    'the same task. previous_reflections are from your earlier failed attempts at it. At most 3 sentences: '
    'what you did that failed and what to do instead. Output {"reflection": "..."}.')

BUILDER_GUIDE = (
    'You maintain a short manual of rules for an agent that does household tasks in a text game '
    '(ALFWorld). You get one finished game (its task, whether it was won, and its steps with what the '
    'game answered) and the current rules. Rule types: "Special Phenomenon" (how this game behaves, '
    'e.g. which commands work and how they must be phrased, where objects tend to be); "Success '
    'Process" (the generic steps that solve a kind of task); "Corrected Error" (a mistake the agent made '
    'and then fixed, or that failed in a lost attempt and was avoided in a won attempt of the same task: '
    '"When <situation>, do <Y> instead of <X>" or "When <situation>, never do <X>"); "Unresolved Error" '
    '(a note from a lost game: in that situation, that action failed; do not guess the cause, never claim '
    'a task is impossible, never list steps; notes are not shown to the agent). ' + RULE_FORM + ' '
    'Write only what this game shows; do not invent commands or places it did not show. The example '
    'field may quote this game\'s real steps (one short line). '
    'First set "diagnosis": "imperfect rules" if the game met something the rules do not cover or no '
    'Success Process exists for this kind of task, else "imperfect agent" if the rules covered it but '
    'the agent did not follow them. Then give "operations": write_rule {type, rule, example, scope}, where '
    'scope is "task" if the rule is about this kind of task only and "all" if it holds in every task; '
    'note {id, validation}: one short sentence on what this game showed about an existing rule (confirmed '
    'it, or showed it is wrong or incomplete); update_note {id, rule} to rewrite an Unresolved Error note. '
    'The text of a rule the agent sees is never rewritten here: if this game shows a rule is wrong, add a '
    'validation note to it (rules are corrected later from the evidence of many games). There is at most '
    'one Success Process per kind of task (task_type): if one exists for this kind of task, never write '
    'another. The rules you get are those for this kind of task and the general ones: if what you want to '
    'say is already in one of them, even in other words, add a note to that rule; never restate it as a '
    'new rule. Output {"diagnosis": "...", "operations": [...]}.')
CASE_NOTES = {
    'direct success': ' This game was won without mistakes: you may write a Success Process and Special '
                      'Phenomenon rules only.',
    'indirect success': ' This game was won after mistakes: if the rules fell short, write a Corrected '
                        'Error for the main mistake and a Success Process; if the agent ignored existing '
                        'rules, add a validation note to those rules instead.',
    'failure': ' This game was lost: if the rules fell short, write at most ONE Unresolved Error note (or '
               'update_note an existing note about the same situation); if the agent ignored existing '
               'rules or a rule misled it, add a validation note to them. A lost game writes no other type.',
    'corrected failure': ' This game was lost (game), then the agent replayed the same game after '
                         'reflecting on its failure (reflections) and won (successful_retry). Compare the '
                         'two attempts and write ONE Corrected Error rule about the decisive difference: '
                         '"When <situation>, do <Y> instead of <X>" or "When <situation>, never do <X>". '
                         'If an Unresolved Error note shown here is about the same situation, use update_note '
                         'on it instead, giving "type": "Corrected Error" and the corrected rule text. You '
                         'may also write the Success Process from the won attempt.',
}
RETRY_NOTE = (' The agent replayed this lost game after reflecting and lost again each time '
              '(failed_retries): an Unresolved Error note may say what kept failing.')
APPEND_ONLY_NOTE = (' Append-only manual: you may only use write_rule; existing rules and notes cannot be '
                    'changed or annotated.')


NUMBERED = re.compile(r'\b(?!steps?\b)[a-z]+ \d+\b', re.IGNORECASE)   # "drawer 3", not "1. take"
TYPE_LABEL = re.compile(r'^\[?(?:%s)\]?\s*:\s*' % '|'.join(TYPES), re.IGNORECASE)


def tidy(text):
    """Normalise rule text: one line, no leading type label, no repeated words ("When When")."""
    text = TYPE_LABEL.sub('', ' '.join(str(text).split()))
    text = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', text, flags=re.IGNORECASE)
    return text[:1].upper() + text[1:]


def rule_problems(kind, text):
    """Why rule text is not a short general rule (an empty list if it is fine)."""
    problems, words = [], len(text.split())
    limit = MAX_WORDS.get(kind, MAX_WORDS_DEFAULT)
    if words > limit:
        problems.append(f'too long ({words} words > {limit})')
    found = NUMBERED.search(text)
    if found:
        problems.append(f'names a numbered object ({found.group(0)!r})')
    if kind != 'Success Process' and recipe_shaped(text):     # Corrected Errors too (2026-11-20 review)
        problems.append('lists steps (only a Success Process may)')
    return problems


STEP_VERB = re.compile(r'\b(find|finds|found|locat\w*|search\w*|take|takes|taking|took|pick\w*|go|goes|going|went|'
                       r'mov\w*|put|puts|putting|plac\w*|open\w*|clos\w*|clean\w*|heat\w*|cool\w*|slic\w*|'
                       r'examin\w*|toggl\w*)\b', re.IGNORECASE)


def recipe_shaped(text):
    """A step-by-step procedure: three or more different step verbs in a sequence (colon, "then", or a
    list of three or more commas). "When a container is closed, open it before ..." is not one."""
    verbs = {m.group(1).lower()[:4] for m in STEP_VERB.finditer(text)}
    return len(verbs) >= 3 and (':' in text or re.search(r'\bthen\b', text, re.IGNORECASE) is not None
                                or text.count(',') >= 3)


def specific_terms(text):
    """Words that tie a rule to one object or to rooms: an ALFWorld object (or its plural) or "room(s)".
    Appliances and receptacles (avoid.PLACES) are fine."""
    found = set()
    for word in re.findall(r'[a-z]+', text.lower()):
        if word in avoid.OBJECTS or re.fullmatch(r'rooms?', word) or any(
                word in (o + 's', o + 'es') for o in avoid.OBJECTS):
            found.add(word)
    return sorted(found)


def generalize(kind, text, ask):
    """Text with no specific objects/rooms: as given, or one Builder rewrite; ValueError if still specific."""
    bad = specific_terms(text)
    if not bad:
        return text
    data = ask('builder', {'instructions': (
        'Rewrite this rule of a household-game manual so it is general for the whole task type: replace '
        'specific objects with "the object" / "the target", never name a room (a game is one room), keep '
        'it at most 25 words and keep its meaning. Output {"rule": "..."}.'),
        'rule': text, 'offending_words': bad, 'response_schema': {'rule': 'string'}})
    new = rewritten(data)
    if not new or specific_terms(new) or rule_problems(kind, new):
        raise ValueError(f"rejected {kind} text, names specific objects or rooms ({', '.join(bad)}): {text[:80]}")
    return new


# Action words of each kind of task (a won game may contain steps of another kind; the appliance nouns
# alone, e.g. "search the fridge", are not actions).
KIND_ACTIONS = {
    'clean': r'clean(?:s|ed|ing)?', 'cool': r'cool(?:s|ed|ing)?', 'heat': r'heat(?:s|ed|ing)?',
    'look': r'(?:turn(?:ed|ing)? on|use|using)\b[^.;:]*?\blamp|desklamp|floorlamp',
    'two': r'two objects|both|each object|second object'}


def foreign_actions(task_type, text):
    """Action words in `text` that belong to a different ALFWorld task kind than `task_type`."""
    own = next((k for k in KIND_ACTIONS if f'pick_{k}_' in str(task_type) or str(task_type).startswith(
        {'look': 'look_at_obj', 'two': 'pick_two_obj'}.get(k, '\0'))), None)
    if own is None:
        return []
    found = []
    for k, pattern in KIND_ACTIONS.items():
        if k != own:
            found += [m.group(0).lower() for m in re.finditer(rf'\b(?:{pattern})\b', text, re.IGNORECASE)]
    return sorted(set(found))


def drop_foreign(kind, text, task_type, ask):
    """Text without steps of another kind of task: as given, or one Builder rewrite; ValueError if still."""
    bad = foreign_actions(task_type, text)
    if not bad:
        return text
    data = ask('builder', {'instructions': (
        f'This rule is for {task_type} tasks only. Rewrite it: remove steps that belong to another kind of '
        f'task: {", ".join(bad)}. Keep it at most 25 words. Output {{"rule": "..."}}.'),
        'rule': text, 'offending_words': bad, 'response_schema': {'rule': 'string'}})
    new = rewritten(data)
    if not new or foreign_actions(task_type, new) or rule_problems(kind, new):
        raise ValueError(f"rejected {kind} text, has steps of another kind of task ({', '.join(bad)}): {text[:80]}")
    return new


INSTANCE = re.compile(r'\b(?:(the|a|an|this|that|each|any|another)\s+)?([a-z]+) \d+\b', re.IGNORECASE)


def strip_instances(text):
    """Instance numbers of ALFWorld objects and receptacles removed (amended 2026-11-20, both conditions):
    "heat it with microwave 1" -> "heat it with the microwave", "the drawer 3" -> "the drawer". A numbered
    word that is no ALFWorld noun ("most 5") is left for the numbered-object check."""
    def swap(m):
        if _noun(m.group(2).lower()) is None:
            return m.group(0)
        return f"{m.group(1) or 'the'} {m.group(2).lower()}"
    return INSTANCE.sub(swap, str(text))


def rewritten(data):
    """The tidied, instance-stripped rule text of a model rewrite ('' if there is none)."""
    if not isinstance(data, dict) or not isinstance(data.get('rule'), str):
        return ''
    return tidy(strip_instances(tidy(data['rule'])))


def repair(kind, text, problems, ask):
    """Text without `problems` (too long, numbered words, steps outside a recipe): one Builder rewrite that
    is told the problems, or ValueError if it still fails (amended 2026-11-20, both conditions)."""
    data = ask('builder', {'instructions': (
        'This rule of a household-game manual was rejected: ' + '; '.join(problems) + '. Rewrite it so it '
        'passes, keeping its meaning. ' + RULE_FORM + ' Output {"rule": "..."}.'),
        'rule': text, 'type': kind, 'problems': list(problems), 'response_schema': {'rule': 'string'}})
    new = rewritten(data)
    if not new or rule_problems(kind, new):
        raise ValueError(f"rejected {kind} text, {'; '.join(problems)} (still after one rewrite): {text[:80]}")
    return new


def checked(kind, text, ask=None, task_type=None):
    """Tidied rule text, or ValueError naming its problems. Instance numbers of ALFWorld objects and
    receptacles are stripped first ("microwave 1" -> "the microwave"). With `ask` (a model call), text that
    still fails a check (length, numbered words, steps) gets one rewrite told its problems (repair), or is
    rejected; then text naming specific objects or rooms gets one general rewrite, or is rejected; so does
    text (for a rule scoped to `task_type`) with an action of another kind of task."""
    text = tidy(strip_instances(tidy(text)))
    problems = rule_problems(kind, text)
    if problems and ask is not None:
        text, problems = repair(kind, text, problems, ask), []
    if problems:
        raise ValueError(f"rejected {kind} text, {'; '.join(problems)}: {text[:80]}")
    if ask is not None:
        text = generalize(kind, text, ask)
        if task_type:
            text = drop_foreign(kind, text, task_type, ask)
    return text


def builder_guide(case, append_only, task_type, shown):
    """The Builder's instructions for one game: the case limits and whether a Success Process exists."""
    allowed = CASE_TYPES[case]
    recipe = next((r for r in shown if r['type'] == 'Success Process' and r.get('task_type') == task_type), None)
    note = f" You may write only these types here: {', '.join(allowed)}."
    if recipe is not None and 'Success Process' in allowed:
        note += (f" This kind of task already has a Success Process ({recipe['id']}): never write another "
                 'one; if this game shows it is wrong, add a validation note to it.')
    return BUILDER_GUIDE + CASE_NOTES[case] + note + (APPEND_ONLY_NOTE if append_only else '')


def shown_to_agent(rule):
    """Not a hidden Builder note (Unresolved Error) or a failure pool."""
    return rule['type'] not in HIDDEN and not rule.get('hidden', False)


# Evidence about a rule's CURRENT text (LIBRARY-SPEC section 2): `ev` resets on a text change, `total` is
# lifetime (reports and the retrieval weight only).
EVIDENCE_KEYS = ('shown', 'followed', 'sum', 'pos', 'neg', 'won', 'lost')


def empty_evidence():
    return dict.fromkeys(EVIDENCE_KEYS, 0)


def ev(rule):
    """The evidence of the rule's current text (zeros for a rule without any)."""
    return rule.get('ev') or empty_evidence()


def mean(rule):
    """m = ev.sum / (ev.followed + PRIOR): the shrunk mean usefulness of the current text (0 for a new rule)."""
    e = ev(rule)
    return e['sum'] / (e['followed'] + PRIOR)


def bad(rule):
    """Followed in >= MIN_EVIDENCE judged games of its current text with m <= BAD_MEAN (visible rules only)."""
    return shown_to_agent(rule) and ev(rule)['followed'] >= MIN_EVIDENCE and mean(rule) <= BAD_MEAN


def useless(rule):
    """Shown (judged) in >= USELESS_MIN games of its current text but followed in under USELESS_FOLLOWED of
    them. All visible types, recipes and Anti-Patterns included: a recipe followed in under 1 game of 5 is not
    working as a recipe, and an Anti-Pattern the agent breaks anyway changes nothing."""
    e = ev(rule)
    return shown_to_agent(rule) and e['shown'] >= USELESS_MIN and e['followed'] < USELESS_FOLLOWED * e['shown']


def showings(rule):
    """Judged games the rule's current text was shown in (the exploration slot's "rarely shown")."""
    return ev(rule)['shown']


def fresh_evidence(rule):
    """Start a rule's evidence afresh after its text changed (the old text's evidence does not carry over);
    `total` is kept."""
    rule['ev'], rule['contexts'] = empty_evidence(), []
    return rule


# Commands a rule instructs, checked against traces (the write gate's trace check, the refiner's check).
COMMAND_VERBS = {'go to': 'go to', 'take': 'take', 'pick up': 'take', 'put': 'move', 'move': 'move',
                 'place': 'move', 'open': 'open', 'close': 'close', 'use': 'use', 'turn on': 'use',
                 'heat': 'heat', 'cool': 'cool', 'clean': 'clean', 'examine': 'examine', 'toggle': 'toggle'}
DETERMINERS = {'the', 'a', 'an', 'some', 'any', 'each', 'another', 'that', 'this'}
NEGATED = re.compile(r"\b(?:instead of|rather than|never|not|don't|do not|cannot|can't|avoid|without|no)\b"
                     r"[^.;:,]*", re.IGNORECASE)


def _noun(word):
    for w in (word, word[:-1] if word.endswith('s') else None, word[:-2] if word.endswith('es') else None):
        if w and (w in avoid.OBJECTS or w in avoid.PLACES):
            return w
    return None


def instructed_commands(text):
    """(verb, noun) commands a rule tells the agent to do: an environment command verb directly followed
    (after articles) by an ALFWorld object or receptacle noun. "take the lamp" -> ('take', 'lamp');
    "take it to the lamp" and anything after "never", "instead of", "do not", ... give nothing."""
    words = re.findall(r"[a-z']+", NEGATED.sub(' , ', str(text).lower()))
    found = set()
    for i in range(len(words)):
        for phrase, verb in COMMAND_VERBS.items():
            parts = phrase.split()
            if words[i:i + len(parts)] != parts:
                continue
            j = i + len(parts)
            while j < len(words) and words[j] in DETERMINERS:
                j += 1
            noun = _noun(words[j]) if j < len(words) else None
            if noun:
                found.add((verb, noun))
    return sorted(found)


def _matches(action, verb, noun):
    """The game command `action` is `verb` applied to `noun` (its first argument; "lamp" matches "desklamp")."""
    words = str(action).lower().split()
    head = verb.split()
    if verb == 'move':
        ok = bool(words) and words[0] in ('move', 'put')
    else:
        ok = words[:len(head)] == head
    if not ok or len(words) <= len(head):
        return False
    target = words[len(head)]
    return target == noun or (len(noun) >= 4 and (target.endswith(noun) or target.startswith(noun)))


def _rejected(step):
    return not step.get('valid', True) or str(step.get('after', '')).strip().startswith('Nothing happens')


def command_evidence(text, trace):
    """{'verb noun': 'ok' | 'rejected'} for each command the rule instructs that this trace tried: 'ok' if
    the game accepted it at least once, else 'rejected'."""
    out = {}
    for verb, noun in instructed_commands(text):
        tried = [t for t in trace if _matches(t.get('action', ''), verb, noun)]
        if tried:
            out[f'{verb} {noun}'] = 'rejected' if all(_rejected(t) for t in tried) else 'ok'
    return out


def trace_problems(text, trace):
    """The write gate's trace check (LIBRARY-SPEC section 3): the instructed commands of `text` that were not
    accepted at least once in `trace` (the won trace the rule was written from); [] if all worked. "take the
    lamp" fails when the game only accepted "use desklamp"."""
    found = command_evidence(text, trace)
    return [f'{verb} {noun}' for verb, noun in instructed_commands(text) if found.get(f'{verb} {noun}') != 'ok']


def trace_checked(kind, text, trace, ask=None, task_type=None):
    """`text` (already through `checked`) if every command it instructs worked in `trace`; else one model
    repair told the problem (and checked again), else ValueError. Hidden notes and Anti-Patterns are not
    trace-checked; trace None skips the check (offline callers without a trace)."""
    if trace is None or kind in HIDDEN or kind == avoid.TYPE:
        return text
    missing = trace_problems(text, trace)
    if not missing:
        return text
    if ask is None:
        raise ValueError(f"rejected {kind} text, instructs commands that did not work in the won game "
                         f"({', '.join(missing)}): {text[:80]}")
    problem = (f"it instructs commands that did not work in the won game ({', '.join(missing)}); use only "
               'commands the game accepted, in the form it accepted them')
    data = ask('builder', {'instructions': (
        'This rule of a household-game manual was rejected: ' + problem + '. Rewrite it so it passes, keeping '
        'its meaning. ' + RULE_FORM + ' Output {"rule": "..."}.'),
        'rule': text, 'type': kind, 'problems': [problem],
        'accepted_commands': sorted({t['action'] for t in trace if not _rejected(t)})[:40],
        'response_schema': {'rule': 'string'}})
    new = rewritten(data)
    if not new:
        raise ValueError(f"rejected {kind} text, {problem} (no rewrite): {text[:80]}")
    try:
        new = checked(kind, new, None, task_type)
    except ValueError as exc:
        raise ValueError(f'rejected {kind} text after the trace repair: {exc}') from None
    still = trace_problems(new, trace)
    if still:
        raise ValueError(f"rejected {kind} text, instructs commands that did not work in the won game "
                         f"({', '.join(still)}) (still after one rewrite): {text[:80]}")
    return new


def won_plans(rule):
    """The plans (subgoal descriptions, ' ; '-joined) of the games where this rule was judged helpful."""
    return list(dict.fromkeys(c['plan'] for c in rule.get('contexts', []) if c.get('score', 0) > 0
                              and c.get('plan')))


def plan_coverage(rules):
    """(rules the agent can see that have a stored helpful plan, rules the agent can see)."""
    seen = [r for r in rules if shown_to_agent(r) and r['type'] != avoid.POOL]
    return sum(bool(won_plans(r)) for r in seen), len(seen)


def for_agent(rules, task_type, k, query=None, similarity=None):
    """The rules a game shows its planner and actor: relevant ones (`query` is the goal), without Builder
    notes. One retrieval for every condition (the retrieval modes were removed on 2026-11-20)."""
    known = any(r.get('task_type') == task_type for r in rules)
    return relevant([r for r in rules if shown_to_agent(r)], task_type, k, query, similarity,
                    cross_type=not known)


def case_of(result):
    if not result['success']:
        return 'failure'
    return 'direct success' if all(t['valid'] for t in result['trace']) else 'indirect success'


def evidence_tasks(rule):
    """The goals a rule is keyed by: its source task(s) and the games where it was judged helpful."""
    goals = [s.get('task') for s in rule.get('sources', [])] + [
        c.get('task') for c in rule.get('contexts', []) if c.get('score', 0) > 0]
    return list(dict.fromkeys(g for g in goals if g))


def helped(rule):
    """h: lifetime followed games with a positive score (the weight of task evidence in relevance)."""
    return (rule.get('total') or {}).get('pos', 0)


def relevance(rule, sims, evidence=None):
    """Task-keyed relevance (ExpeL/Memp): (Rel, evidence); `sims` maps text -> similarity to the goal.
    `evidence`: the rule's evidence similarity when the caller computed it."""
    text = max(0.0, sims[rule['rule']])
    if evidence is None:
        evidence = max([max(0.0, sims[g]) for g in evidence_tasks(rule)], default=0.0)
    h = helped(rule)
    w = h / (h + EVIDENCE_PRIOR)
    return w * evidence + (1 - w) * text, evidence


def _number(rule):
    return int(rule['id'].split('_')[1])


def ranked(rules, task_type, query=None, similarity=None, cross_type=False):
    """(this kind's Success Process, the other candidates ranked, {id(rule): Rel}): candidates are this kind's
    other rules and the general ones, ranked by Rel + RANK_WEIGHT * m with task-keyed relevance when a query
    and similarity function are given, else by m and then newest first (Rel then empty). `cross_type`: other
    kinds' rules may join when their task evidence is high."""
    rules = [r for r in rules if r['type'] != avoid.POOL]
    recipe = [r for r in rules if r['type'] == 'Success Process' and r.get('task_type') == task_type]
    others = [r for r in rules if r not in recipe and r['type'] != 'Success Process'
              and r.get('task_type') in (task_type, 'all', None)]
    if not (query and similarity):
        others.sort(key=lambda r: (mean(r), _number(r)), reverse=True)
        return recipe, others, {}
    foreign = [r for r in rules if cross_type and r not in recipe and r not in others
               and r['type'] != 'Success Process']
    pool = others + foreign
    if not pool:
        return recipe, [], {}
    texts = list(dict.fromkeys([r['rule'] for r in pool] + [g for r in pool for g in evidence_tasks(r)]))
    sims = {t: float(s) for t, s in zip(texts, similarity(query, texts))}
    scored = {id(r): relevance(r, sims) for r in pool}
    pool = others + [r for r in foreign if scored[id(r)][1] >= CROSS_TYPE_EVIDENCE]
    rank = {id(r): scored[id(r)][0] + RANK_WEIGHT * mean(r) for r in pool}
    pool.sort(key=lambda r: (rank[id(r)], _number(r)), reverse=True)
    return recipe, pool, {id(r): scored[id(r)][0] for r in pool}


def take(recipe, pool, rel, k):
    """The first `k` of recipe + pool, keeping one slot (when there are more candidates than slots) for the
    best-matching (highest Rel) rarely shown rule (fewer than RARE_SHOWINGS showings) if none made the cut
    (2026-11-20 design review: new rules were starved). The recipe stays first."""
    chosen = (recipe + pool)[:k]
    if k is None or k < 1 or len(recipe) + len(pool) <= k or not rel:
        return chosen
    if any(showings(r) < RARE_SHOWINGS for r in chosen if r not in recipe):
        return chosen
    rare = [r for r in pool if showings(r) < RARE_SHOWINGS and r not in chosen]
    if not rare:
        return chosen
    best = max(rare, key=lambda r: (rel[id(r)], _number(r)))
    return chosen[:k - 1] + [best]


def relevant(rules, task_type, k, query=None, similarity=None, cross_type=False):
    """This kind of task's Success Process first, then its other rules and the general ones (ranked), at most
    `k` (None: all), with one slot kept for a rarely shown rule (take)."""
    recipe, pool, rel = ranked(rules, task_type, query, similarity, cross_type)
    return take(recipe, pool, rel, k)


def for_builder(rules, task_type, k, query=None, similarity=None):
    """The rules the Builder sees for a game, built the same way for E and E-minus: the rules relevant to the
    game, ranked with the agent's task-keyed function (hidden notes included), plus NEWEST_SLOTS slots for
    the newest rules not otherwise included."""
    known = any(r.get('task_type') == task_type for r in rules)
    recipe, pool, rel = ranked(rules, task_type, query, similarity, cross_type=not known)
    if len(recipe) + len(pool) <= k:
        return recipe + pool
    top = take(recipe, pool, rel, max(k - NEWEST_SLOTS, len(recipe)))
    rest = [r for r in recipe + pool if r not in top]
    newest = sorted(rest, key=_number, reverse=True)[:k - len(top)]
    return top + sorted(newest, key=_number)


def new_rule(rule_id, kind, text, example, task_type, sources=(), created=None):
    """A rule record (LIBRARY-SPEC section 2). `created`: the practice position it was written at."""
    return {'id': rule_id, 'type': kind, 'rule': text, 'example': example, 'validation': '',
            'task_type': task_type, 'hidden': kind in HIDDEN, 'sources': [dict(s) for s in sources][-MAX_SOURCES:],
            'created': created, 'revisions': 0, 'ev': empty_evidence(), 'total': empty_evidence(),
            'contexts': [], 'last_used': None}


KIND_SPECIFIC = re.compile(r'\b(cool(?:ed|ing)?|fridge|refrigerator|heat(?:ed|ing)?|microwave|clean(?:ed|ing)?|'
                           r'sinkbasin|sink|desklamp|floorlamp|lamp|light|two objects|both|each object|'
                           r'multiple objects|two|second object)\b', re.IGNORECASE)


def kind_specific(text):
    """Rule text that names an action or appliance of one kind of task cannot hold in every task."""
    return bool(KIND_SPECIFIC.search(text))


def narrowed(rule, task_type, log):
    """An 'all' rule whose text is kind-specific is limited to this game's kind of task (True if changed)."""
    if rule.get('task_type') == 'all' and task_type and kind_specific(rule['rule']):
        rule['task_type'] = task_type
        log.append(f"{rule['id']} narrowed from all tasks to {task_type} (its text names a task-specific action)")
        return True
    return False


def add_source(rule, source):
    if source and source not in rule.setdefault('sources', []):
        rule['sources'] = (rule['sources'] + [dict(source)])[-MAX_SOURCES:]


def render(rules, limit=300):
    """The rules as the planner and actor see them (validation notes are not shown)."""
    return [f"[{r['type']}] {r['rule']}" + (f" Example: {r['example'][:limit]}" if r.get('example') else '')
            for r in rules]


def _game(result, task_goal, max_steps=40):
    steps = [{'action': t['action'], 'valid': t['valid'], 'result': t['after'][:200]} for t in result['trace']]
    return {'task': task_goal, 'won': result['success'], 'steps': steps[-max_steps:]}


def apply(rules, operations, case, append_only, next_id, log, task_type=None, visible=None, similarity=None,
          goal=None, ask=None, trace=None, retry_check=None, position=None):
    """Apply Builder operations under the case limits (LIBRARY-SPEC section 3); returns the applied operations
    (for batching). `visible`: ids the Builder was shown (it may only annotate or update those); default all.
    `goal`: the game's task, stored on written (and merged) rules as task-keyed retrieval evidence. `trace`: the
    won trace the rules are written from (the first attempt if won, else the winning retry) for the write
    gate's trace check. `retry_check`: (rule) -> whether the winning retry followed it with usefulness >=
    CONVERT_USEFULNESS (per-rule judge); a corrected failure's update_note turns an Unresolved Error into a
    Corrected Error only when it did. `position`: the practice position, stored as `created`.
    Operations: write_rule (all conditions); note and update_note (E only). The Builder never rewrites the
    text of a rule the agent sees."""
    applied, writes = [], 0
    visible = {r['id'] for r in rules} if visible is None else set(visible)
    by_id = {r['id']: r for r in rules}
    allowed = CASE_TYPES[case]
    source = {'task': goal, 'task_type': task_type} if goal else None
    for op in operations if isinstance(operations, list) else []:
        if not isinstance(op, dict):
            continue
        kind = op.get('op')
        try:
            if kind == 'write_rule':
                if op.get('type') not in TYPES or not isinstance(op.get('rule'), str) or not op['rule'].strip():
                    raise ValueError('rule needs a known type and text')
                if op['type'] not in allowed:
                    raise ValueError(f"a {case} may not write a {op['type']} rule")
                if writes >= MAX_WRITES[case]:
                    raise ValueError(f'a {case} may write at most {MAX_WRITES[case]} rule(s)')
                kind_scope = task_type if op['type'] == 'Success Process' or op.get('scope') != 'all' else None
                text = checked(op['type'], op['rule'], ask, kind_scope)
                text = trace_checked(op['type'], text, trace, ask, kind_scope)
                if any(tidy(r['rule']).lower() == text.lower() for r in rules):
                    raise ValueError('duplicate rule')
                if op['type'] == 'Success Process':
                    # As in AutoManual: one Success Process per kind of task.
                    existing = next((r for r in rules if r['type'] == 'Success Process'
                                     and r.get('task_type') == task_type), None)
                    if existing is not None:
                        raise ValueError(f"a Success Process for this kind of task exists ({existing['id']}): "
                                         'write refused')
                scope = 'all' if op.get('scope') == 'all' and op['type'] != 'Success Process' else task_type
                if scope == 'all' and task_type and kind_specific(text):
                    scope = task_type
                    log.append(f'a general rule was limited to {task_type} (its text names a task-specific action)')
                twin = None if append_only or similarity is None else near_duplicate(
                    rules, op['type'], scope, text, similarity, task_type)
                if twin is not None:
                    # MACLA: merge into the existing rule instead of adding a near-copy. Its text and scope never
                    # change; this game's task is kept as extra retrieval evidence.
                    add_source(twin, source)
                    narrowed(twin, task_type, log)
                    applied.append({'op': 'merge_rule', 'id': twin['id'], 'task_type': twin.get('task_type'),
                                    **({'source': source} if source else {})})
                    log.append(f"merged a new rule into {twin['id']}")
                    continue
                example = ' '.join(str(op.get('example') or '').split())[:MAX_EXAMPLE]
                rule = new_rule(next_id(), op['type'], text, example, scope, [source] if source else [], position)
                rules.append(rule)
                by_id[rule['id']] = rule
                writes += 1
                applied.append({'op': 'write_rule', **{k: rule[k] for k in ('type', 'rule', 'example', 'task_type',
                                                                             'sources', 'created')}})
            elif kind in ('note', 'update_note'):
                if append_only:
                    raise ValueError('append-only manual: rules cannot be changed or annotated')
                rule = by_id.get(op.get('id'))
                if rule is None or rule.get('id') not in visible or rule['type'] == avoid.POOL:
                    raise ValueError(f"unknown rule id {op.get('id')}")
                if kind == 'note':
                    if not isinstance(op.get('validation'), str) or not op['validation'].strip():
                        raise ValueError('note needs a validation sentence')
                    change = {'op': 'note', 'id': rule['id'], 'validation': ' '.join(op['validation'].split())[:300]}
                    _note(rule, change)
                    applied.append(change)
                    continue
                if shown_to_agent(rule) or rule['type'] != 'Unresolved Error':
                    raise ValueError(f"{rule['id']} is not a hidden note: the Builder never rewrites a rule the "
                                     'agent sees (add a validation note instead)')
                if not isinstance(op.get('rule'), str) or not op['rule'].strip():
                    raise ValueError('update_note needs the rule text')
                change = None
                if op.get('type') == 'Corrected Error' and case == 'corrected failure':
                    # A success/failure pair of the same task may turn the note into a rule the agent sees, if
                    # the new text passes the write gate (against the winning retry) and the judge says the
                    # winning retry followed it usefully.
                    try:
                        text = checked('Corrected Error', op['rule'], ask, rule.get('task_type'))
                        text = trace_checked('Corrected Error', text, trace, ask, rule.get('task_type'))
                        if retry_check is None or not retry_check({'type': 'Corrected Error', 'rule': text}):
                            raise ValueError('the winning retry did not follow it with usefulness >= '
                                             f'{CONVERT_USEFULNESS}')
                        change = {'op': 'update_note', 'id': rule['id'], 'rule': text, 'type': 'Corrected Error',
                                  'old_rule': rule['rule']}
                        log.append(f"{rule['id']} turned into a Corrected Error (shown to the agent)")
                    except ValueError as exc:
                        log.append(f"{rule['id']} stays a hidden note ({exc})")
                elif op.get('type') not in (None, 'Unresolved Error'):
                    log.append(f"{rule['id']} keeps its type Unresolved Error (only a retry success turns a note "
                               'into a Corrected Error)')
                if change is None:
                    text = checked('Unresolved Error', op['rule'], ask, rule.get('task_type'))
                    if text == rule['rule']:
                        continue
                    change = {'op': 'update_note', 'id': rule['id'], 'rule': text, 'old_rule': rule['rule']}
                _update_note(rule, change)
                applied.append(change)
            else:
                raise ValueError(f'unknown operation {kind!r}')
        except ValueError as exc:
            log.append(str(exc))
    return applied


def _note(rule, op):
    """Append a validation note, keeping the last MAX_NOTES (AutoManual's validation log)."""
    notes = ([rule['validation']] if rule.get('validation') else []) + [op['validation']]
    rule['validation'] = ' | '.join(' | '.join(notes).split(' | ')[-MAX_NOTES:])


def _update_note(rule, op):
    """Rewrite a hidden note; with 'type' it becomes a visible Corrected Error with empty evidence."""
    rule['rule'] = op['rule']
    if op.get('type'):
        rule['type'], rule['hidden'] = op['type'], False
    fresh_evidence(rule)


def near_duplicate(rules, kind, scope, text, similarity, task_type=None):
    """A rule of the same type saying nearly the same, of the same kind of task (the new rule's scope or
    the game's kind) or a general ("all") one; never another kind's rule, so merging never widens a
    rule's scope. Success Processes stay one per kind of task."""
    kinds = {scope, task_type, 'all'} if kind != 'Success Process' else {scope}
    pool = [r for r in rules if r['type'] == kind and r.get('task_type') in kinds]
    if not pool:
        return None
    scores = [float(x) for x in similarity(text, [r['rule'] for r in pool])]
    best = max(range(len(pool)), key=lambda i: scores[i])
    return pool[best] if scores[best] >= DUP_SIMILARITY else None


DEDUPE_EXEMPT = ('Success Process', avoid.TYPE, avoid.POOL)   # one recipe per kind; Anti-Patterns by signature


def batch_dedupe(rules, base_ids, similarity):
    """E only, at the end of a batch (part of batch_upkeep): games of a batch never saw each other's new rules,
    so the similarity merge of write_rule is run again. Each rule written in the batch (id not in `base_ids`),
    oldest first, is merged into an older near-duplicate (near_duplicate: same type, same kind of task or a
    general one). The older rule keeps its text and evidence and gains the sources. Mutates `rules`; returns
    the ops (replayed by _dedupe)."""
    ops = []
    for new in sorted([r for r in rules if r['id'] not in set(base_ids) and r['type'] not in DEDUPE_EXEMPT],
                      key=_number):
        if new not in rules:
            continue
        older = [r for r in rules if _number(r) < _number(new)]
        twin = near_duplicate(older, new['type'], new.get('task_type'), new['rule'], similarity)
        if twin is None:
            continue
        op = {'op': 'dedupe', 'id': twin['id'], 'absorbed': new['id'], 'absorbed_rule': new['rule'],
              'sources': copy.deepcopy(new.get('sources', []))}
        _dedupe(rules, op)
        ops.append(op)
    return ops


def _dedupe(rules, op):
    by_id = {r['id']: r for r in rules}
    twin, gone = by_id.get(op['id']), by_id.get(op['absorbed'])
    if twin is None or gone is None:
        return
    for source in op.get('sources', []):
        add_source(twin, source)
    rules.remove(gone)


def observe(rules, verdicts, context, position, won):
    """Record one game's per-rule judge verdicts (E and E-minus); returns the op (replayed by _observe).
    `verdicts`: {rule id: {'followed': bool, 'usefulness': -2..2, 'reason': str, 'rule': the judged text}}
    for the shown rules judged without failure; a rule whose judge call failed has no entry and so gets no
    evidence from this game. `context`: {task, task_type, steps, plan}, stored with the score for followed
    rules (the refiner's evidence). `won`: the first attempt's outcome, kept for reports only."""
    op = {'op': 'outcome', 'verdicts': {k: dict(v) for k, v in verdicts.items()}, 'won': bool(won),
          'context': context, 'position': position}
    _observe(rules, op)
    return op


def _observe(rules, op):
    """followed = yes: shown, followed, sum, pos/neg and won/lost += 1, context stored; followed = no: shown
    += 1 only. A verdict on a text the rule no longer has (changed or converted since it was judged, e.g.
    by a batch-mate's refinement) is not counted."""
    by_id = {r['id']: r for r in rules}
    for rule_id, verdict in op.get('verdicts', {}).items():
        rule = by_id.get(rule_id)
        if rule is None or not shown_to_agent(rule) or verdict.get('rule', rule['rule']) != rule['rule']:
            continue
        score, followed = int(verdict['usefulness']), bool(verdict['followed'])
        for key in ('ev', 'total'):
            e = rule.setdefault(key, empty_evidence())
            e['shown'] += 1
            if followed:
                e['followed'] += 1
                e['sum'] += score
                e['pos'] += score > 0
                e['neg'] += score < 0
                e['won' if op['won'] else 'lost'] += 1
        rule['last_used'] = op['position']
        if followed and score:
            contexts = rule.get('contexts', []) + [{**op['context'], 'won': bool(op['won']), 'score': score,
                                                    'reason': verdict.get('reason', '')}]
            rule['contexts'] = ([c for c in contexts if c['score'] > 0][-K_CONTEXTS:]
                                + [c for c in contexts if c['score'] < 0][-K_CONTEXTS:])


def decisions(rules):
    """(the bad rule to refine, or None; the bad rules to retire), LIBRARY-SPEC section 5. A bad rule that may
    still be revised (revisions < MAX_REVISIONS, not an Anti-Pattern) is refined, at most one per game, the
    lowest m first (the others wait); every other bad rule is retired."""
    flagged = [r for r in rules if bad(r)]
    doomed = [r for r in flagged if r['type'] == avoid.TYPE or r.get('revisions', 0) >= MAX_REVISIONS]
    target = min([r for r in flagged if r not in doomed], key=lambda r: (mean(r), _number(r)), default=None)
    return target, doomed


def retire_op(rule, reason, check=None):
    """A retire op; check='bad': replay applies it only if the rule is still bad on the live rules."""
    e = ev(rule)
    return {'op': 'retire', 'id': rule['id'], 'reason': reason, 'ev': dict(e), 'revisions': rule.get('revisions', 0),
            **({'check': check} if check else {})}


def _retire(rules, op):
    rule = next((r for r in rules if r['id'] == op['id']), None)
    if rule is not None:
        avoid.forget(rules, rule) if rule['type'] == avoid.TYPE else rules.remove(rule)


def manage(agent, rules, report):
    """E only, after the game's evidence is recorded: retire the bad rules that cannot be revised any more and
    refine at most one bad rule (decisions). Ops are appended to the report."""
    target, doomed = decisions(rules)
    for rule in doomed:
        e = ev(rule)
        why = ('an Anti-Pattern is never refined' if rule['type'] == avoid.TYPE
               else f"{rule.get('revisions', 0)} revisions used")
        op = retire_op(rule, f"bad: m {mean(rule):.2f} over {e['followed']} followed games; {why}", 'bad')
        _retire(rules, op)
        report['operations'].append(op)
        report['errors'].append(f"retired {rule['id']} ({op['reason']})")
    if target is not None:
        refine(agent, rules, target, report)


def refine(agent, rules, rule, report):
    """MACLA contrastive refinement of one bad rule: the refiner gets the rule, its contexts where it helped
    and where it misled (with the judge's reasons) and its validation notes, and returns one rewritten rule.
    The new text must pass the text checks, and the commands it instructs must appear in the actions of a
    stored context. Any failure retires the rule (it is not kept for another try every game)."""
    contexts = rule.get('contexts', [])
    try:
        data = agent._ask('refiner', {
            'instructions': REFINE_GUIDE, 'rule': {k: rule.get(k, '') for k in ('type', 'rule', 'example')},
            'validation': [n for n in str(rule.get('validation') or '').split(' | ') if n],
            'helped_games': [c for c in contexts if c['score'] > 0],
            'misled_games': [c for c in contexts if c['score'] < 0],
            'response_schema': {'rule': 'string'}})
        text = data.get('rule') if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError('refiner gave no rule')
        text = checked(rule['type'], text, agent._ask, rule.get('task_type'))
        if text == rule['rule']:
            raise ValueError('refiner gave the same rule')
        actions = [a for c in contexts for a in c.get('steps', [])]
        missing = [f'{verb} {noun}' for verb, noun in instructed_commands(text)
                   if not any(_matches(a, verb, noun) for a in actions)]
        if missing:
            raise ValueError(f"the new text instructs commands no stored game shows ({', '.join(missing)})")
        op = {'op': 'refine', 'id': rule['id'], 'rule': text, 'old_rule': rule['rule'],
              'revision': rule.get('revisions', 0) + 1}
        _refine(rules, op)
        report['operations'].append(op)
        report['errors'].append(f"refined {rule['id']} (revision {op['revision']} of {MAX_REVISIONS}; fresh evidence)")
    except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        op = retire_op(rule, f'bad, and refinement failed: {exc}'[:200], 'bad')
        _retire(rules, op)
        report['operations'].append(op)
        report['errors'].append(f"retired {rule['id']} ({op['reason']})")


def _refine(rules, op):
    """A refined rule: new text, one more revision, fresh evidence (`total` kept)."""
    for rule in rules:
        if rule['id'] == op['id']:
            rule['rule'] = op['rule']
            rule['revisions'] = rule.get('revisions', 0) + 1
            fresh_evidence(rule)


def prune(rules):
    """Above CAPACITY rules (Failure Pools excluded): drop hidden notes oldest first, then visible rules by
    lowest m, then least recently used. Mutates `rules`; returns the prune ops."""
    ops = []
    while sum(r['type'] != avoid.POOL for r in rules) > CAPACITY:
        pool = [r for r in rules if r['type'] != avoid.POOL]
        notes = [r for r in pool if not shown_to_agent(r)]
        if notes:
            victim = min(notes, key=_number)
        else:
            victim = min(pool, key=lambda r: (mean(r), -1 if r.get('last_used') is None else r['last_used'],
                                              _number(r)))
        op = {'op': 'prune', 'id': victim['id']}
        _retire(rules, op)
        ops.append(op)
    return ops


def batch_upkeep(rules, base_ids, similarity):
    """E only, the deterministic upkeep, once at the end of each batch on the live rules (in the main
    process; with practice_batch == 1 `build` runs it after each game): retire useless rules, merge the
    batch's near-duplicates (batch_dedupe), prune above CAPACITY. Mutates `rules`; returns the ops (append
    them to the batch's last game, so replay reproduces every checkpoint)."""
    ops = []
    for rule in [r for r in rules if useless(r)]:
        e = ev(rule)
        op = retire_op(rule, f"useless: followed in {e['followed']} of {e['shown']} judged showings")
        _retire(rules, op)
        ops.append(op)
    if similarity is not None:
        ops += batch_dedupe(rules, base_ids, similarity)
    return ops + prune(rules)


def judge_payload(agent, rule, trace=None):
    """Outcome-blind input for the per-rule judge (LIBRARY-SPEC section 4): goal, one rule, the last
    JUDGE_STEPS valid actions of `trace` (default: the first attempt) with short observations; no success
    flag, no reward, and the final observation (which reveals a win) is left out."""
    trace = [t for t in (agent.result['trace'] if trace is None else trace) if t['valid']]
    steps = [{'action': t['action'], 'observation': t['after'][:JUDGE_OBSERVATION]} for t in trace[-JUDGE_STEPS:]]
    if steps:
        steps[-1].pop('observation')
    return {'instructions': JUDGE_GUIDE, 'goal': agent.public_task.get('goal', ''),
            'rule': {'type': rule['type'], 'rule': rule['rule']}, 'steps': steps,
            'response_schema': {'followed': 'yes|no', 'usefulness': '-2|-1|0|1|2', 'reason': 'one short sentence'}}


def parse_verdict(data):
    """{'followed', 'usefulness', 'reason'} from a judge answer, or ValueError (no JSON object, a bad value).
    A rule that was not followed has usefulness 0."""
    if not isinstance(data, dict):
        raise ValueError('no JSON object')
    said = data.get('followed')
    if isinstance(said, bool):
        followed = said
    elif isinstance(said, str) and said.strip().lower() in ('yes', 'no'):
        followed = said.strip().lower() == 'yes'
    else:
        raise ValueError(f'bad followed value {said!r}')
    value = data.get('usefulness')
    try:
        score = None if isinstance(value, bool) else int(str(value).strip().lstrip('+'))
    except ValueError:
        score = None
    if score not in SCORES:
        raise ValueError(f'bad usefulness value {value!r}')
    return {'followed': followed, 'usefulness': score if followed else 0,
            'reason': ' '.join(str(data.get('reason') or '').split())[:200]}


def judge_rule(agent, rule, errors, trace=None):
    """The per-rule judge's verdict on `rule` in this game (`trace`: default the first attempt), from one
    separate outcome-blind call (role 'judge'), or None on any failure (logged): no evidence, never "credit
    all"."""
    try:
        return parse_verdict(agent._ask('judge', judge_payload(agent, rule, trace)))
    except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f"judge {rule.get('id', 'note')}: {exc}; no evidence"[:200])
        return None


def judge_shown(agent, rules, errors):
    """{rule id: verdict + the judged text} for every visible rule shown in the game (at most SHOWN calls)."""
    by_id = {r['id']: r for r in rules}
    verdicts = {}
    for rule_id in dict.fromkeys(agent.rules_shown or ()):
        rule = by_id.get(rule_id)
        if rule is None or not shown_to_agent(rule):
            continue
        verdict = judge_rule(agent, rule, errors)
        if verdict is not None:
            verdicts[rule_id] = {**verdict, 'rule': rule['rule']}
    return verdicts


def retry_judge(agent, retried, errors):
    """(rule) -> whether the winning retry followed it with usefulness >= CONVERT_USEFULNESS (the per-rule
    judge on the retry trace; False on failure, logged). Used before update_note makes a note visible."""
    def followed(rule):
        verdict = judge_rule(agent, rule, errors, retried['trace'])
        return verdict is not None and verdict['followed'] and verdict['usefulness'] >= CONVERT_USEFULNESS
    return followed


COSTS = ('model_calls', 'input_tokens', 'output_tokens', 'model_wall_seconds')


def retry(agent, errors):
    """ExpeL experience gathering: after a lost practice game, reflect (Reflexion) and replay the same
    game from its start with the reflections, up to RETRIES times, until it is won. Retries are frozen
    (they change no memory). Their cost (reflections and replays) is added to the game's totals.
    Returns (summary for the record, the last retry's result) or (None, None)."""
    if agent.condition not in RETRY_CONDITIONS or agent.result['success'] or RETRIES <= 0:
        return None, None
    goal = agent.public_task.get('goal', '')
    before = {k: agent.result[k] for k in COSTS}
    gpu_before, known_before = agent.gpu, agent.gpu_known
    reflections, attempts, last = [], [], agent.result
    for attempt in range(1, RETRIES + 1):
        try:
            data = agent._ask('reflector', {'instructions': REFLECT_GUIDE, 'game': _game(last, goal),
                                            'previous_reflections': list(reflections),
                                            'response_schema': {'reflection': 'string'}})
            text = ' '.join(str(data.get('reflection') or '').split())[:MAX_REFLECTION]
            if not text:
                raise ValueError('reflector gave no reflection')
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            errors.append(f'reflector: {exc}'[:200])
            break
        reflections.append(text)
        last = agent.retry_agent(list(reflections)).run(agent.task, agent.seed, {**agent.context, 'attempt': attempt})
        for key in COSTS:
            agent.result[key] += last[key]
        if last.get('gpu_seconds') is None:
            agent.gpu_known = False
        else:
            agent.gpu += last['gpu_seconds']
        attempts.append({'attempt': attempt, 'reflection': text, 'success': last['success'],
                         'steps': len(last['trace']), 'model_calls': last['model_calls'],
                         'actions': [t['action'] for t in last['trace'] if t['valid']][-20:],
                         'trace': avoid.compact(last['trace'])})
        if last['success']:
            break
    summary = {'attempts': attempts, 'won': bool(attempts) and attempts[-1]['success'],
               **{k: agent.result[k] - before[k] for k in COSTS},
               'gpu_seconds': (agent.gpu - gpu_before) if agent.gpu_known and known_before else None}
    return summary, (last if attempts else None)


def avoid_update(agent, rules, report, summary, append_only, next_id):
    """Anti-Pattern upkeep after a practice game (avoid.py): pool a never-won game, add a won attempt as
    contrast, maybe write a rule, re-check the kind's rules. Returns the operations to replay."""
    attempts = [avoid.compact(agent.result['trace'])] + [a['trace'] for a in (summary or {}).get('attempts', [])
                                                          if 'trace' in a]
    won = bool(agent.result['success'] or (summary and summary['won']))
    try:
        return avoid.update(agent._ask, rules, agent.task.get('task_type'), agent.public_task.get('goal', ''),
                            agent.task.get('id') or agent.public_task.get('goal', ''), attempts, won, next_id,
                            report['errors'], append_only)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        report['errors'].append(f'anti-pattern: {exc}'[:200])
        return []


def build(agent):
    """One Builder pass after a practice game (LIBRARY-SPEC sections 3-5). Mutates agent.rules; returns a
    report. Order: Reflexion retries, the per-rule judge (on the rules as the agent saw them), the Builder,
    the evidence, management (E), Anti-Patterns, and with practice_batch == 1 the batch upkeep (E)."""
    rules, report = agent.rules, {'case': case_of(agent.result), 'operations': [], 'errors': []}
    append_only = agent.condition == 'E-minus'
    base_ids = {r['id'] for r in rules}
    summary, retried = retry(agent, report['errors'])
    extra = {}
    if summary is not None:
        agent.result['retries'] = summary
        if summary['won']:
            report['case'] = 'corrected failure'
            extra = {'successful_retry': _game(retried, agent.public_task.get('goal', '')),
                     'reflections': [a['reflection'] for a in summary['attempts']]}
        elif summary['attempts']:
            extra = {'failed_retries': [{k: a[k] for k in ('reflection', 'actions')} for a in summary['attempts']]}
    counter = [max([int(r['id'].split('_')[1]) for r in rules] + [0])]

    def next_id():
        counter[0] += 1
        return f'rule_{counter[0]}'
    position = agent.context.get('position', 0)
    goal = agent.public_task.get('goal', '')
    task_type = agent.task.get('task_type')
    # The same view for E and E-minus: relevance to this game plus the newest rules.
    shown = for_builder(rules, task_type, BUILDER_SEES, goal, agent.embedder.similarity)
    guide = builder_guide(report['case'], append_only, task_type, shown)
    if 'failed_retries' in extra:
        guide += RETRY_NOTE
    # The outcome-blind per-rule judge, E and E-minus alike, on the rules as the agent saw them.
    verdicts = judge_shown(agent, rules, report['errors'])
    report['judged'] = {i: {k: v[k] for k in ('followed', 'usefulness')} for i, v in verdicts.items()}
    won_trace = agent.result['trace'] if agent.result['success'] else (
        retried['trace'] if report['case'] == 'corrected failure' else None)
    retry_check = None
    if report['case'] == 'corrected failure' and not append_only:
        retry_check = retry_judge(agent, retried, report['errors'])
    ops = ['write_rule'] if append_only else ['write_rule', 'note', 'update_note']
    try:
        data = agent._ask('builder', {
            'instructions': guide,
            'game': _game(agent.result, goal), **extra,
            'task_type': task_type,
            'rules': [{k: r.get(k, '') for k in ('id', 'type', 'rule', 'example', 'validation')} for r in shown],
            'response_schema': {'diagnosis': 'imperfect rules | imperfect agent',
                                'operations': [{'op': ' | '.join(ops), 'id': 'rule_N',
                                                'type': '|'.join(CASE_TYPES[report['case']]), 'rule': 'string',
                                                'example': 'string', 'scope': 'task | all',
                                                'validation': 'string'}]}})
        report['diagnosis'] = data.get('diagnosis')
        report['operations'] += apply(rules, data.get('operations'), report['case'], append_only, next_id,
                                      report['errors'], task_type, [r['id'] for r in shown],
                                      agent.embedder.similarity, goal, agent._ask, won_trace, retry_check, position)
    except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        report['errors'].append(f'builder: {exc}'[:200])
    report['operations'].append(observe(rules, verdicts, {
        'task': goal, 'task_type': task_type,
        'steps': [t['action'] for t in agent.result['trace'] if t['valid']][-CONTEXT_STEPS:],
        **({'plan': agent.plan_text} if getattr(agent, 'plan_text', None) else {})},
        position, agent.result['success']))
    if not append_only:
        manage(agent, rules, report)
    report['operations'] += avoid_update(agent, rules, report, summary, append_only, next_id)
    if not append_only and getattr(agent.cfg, 'practice_batch', 1) <= 1:
        upkeep = batch_upkeep(rules, base_ids, agent.embedder.similarity)
        report['operations'] += upkeep
        report['errors'] += [f"retired {op['id']} ({op['reason']})" for op in upkeep if op['op'] == 'retire']
    return report


def replay(live, operations, log, base=None):
    """Batching: apply one game's applied operations onto the live rules (ids re-issued for writes), so the
    live rules end exactly as `build` and `batch_upkeep` left them. `base`: the rules at the start of the batch
    (the copy this game ran on). A refine or bad-retire op (check 'bad') is applied only if the rule is still
    bad on the live rules (the batch-mates' evidence is already replayed), and with `base` a rule's text
    changes at most once per batch (the first in position order); otherwise the op is dropped and logged.
    An update_note applies only while the target is still a hidden note."""
    rules = copy.deepcopy(live)
    by_id = {r['id']: r for r in rules}
    counter = [max([int(r['id'].split('_')[1]) for r in rules] + [0])]
    started = None if base is None else {r['id']: r['rule'] for r in base}
    changed = set()

    def taken(rule_id):
        """True when this rule's text already changed in this batch."""
        if started is None:
            return False
        rule = by_id.get(rule_id)
        return rule_id in changed or (rule is not None and rule_id in started and rule['rule'] != started[rule_id])

    def next_id():
        counter[0] += 1
        return f'rule_{counter[0]}'

    def refresh():
        by_id.clear()
        by_id.update({r['id']: r for r in rules})
    for op in operations:
        kind = op['op']
        if kind in ('pool_game', 'pool_won'):
            avoid.apply_pool_op(rules, op, next_id)
            refresh()
            continue
        if kind == 'outcome':
            _observe(rules, op)
            continue
        if kind == 'write_rule':
            if any(r['rule'] == op['rule'] for r in rules) or (
                    op.get('pattern') and any(r.get('pattern') and r['pattern']['sig'] == op['pattern']['sig']
                                              and r.get('task_type') == op.get('task_type') for r in rules)) or (
                    op['type'] == 'Success Process' and any(r['type'] == 'Success Process' and
                                                             r.get('task_type') == op.get('task_type') for r in rules)):
                log.append(['duplicate rule', op['rule'][:60]])
                continue
            rule = new_rule(next_id(), op['type'], op['rule'], op['example'], op.get('task_type'),
                            op.get('sources', ()), op.get('created'))
            if op.get('pattern'):
                rule['pattern'] = copy.deepcopy(op['pattern'])
            rules.append(rule)
            by_id[rule['id']] = rule
            continue
        if op.get('id') not in by_id:
            log.append(['rule already gone', kind, op.get('id')])
            continue
        target = by_id[op['id']]
        if kind == 'refine' or (kind == 'retire' and op.get('check') == 'bad'):
            if not bad(target):
                log.append(['dropped (no longer bad on the live rules)', kind, op['id']])
                continue
            if kind == 'refine' and taken(op['id']):
                log.append(['text change dropped (already changed in this batch)', kind, op['id']])
                continue
        if kind == 'refine':
            _refine(rules, op)
            changed.add(op['id'])
        elif kind in ('retire', 'prune'):
            _retire(rules, op)
            refresh()
        elif kind == 'dedupe':
            _dedupe(rules, op)
            refresh()
        elif kind == 'merge_rule':        # scope never widens on a merge
            add_source(target, op.get('source'))
            if target.get('task_type') == 'all' and op.get('task_type') not in (None, 'all'):
                target['task_type'] = op['task_type']
        elif kind == 'note':
            _note(target, op)
        elif kind == 'update_note':
            if shown_to_agent(target) or (op.get('type') and taken(op['id'])):
                log.append(['note update dropped (no longer a hidden note)', kind, op['id']])
                continue
            _update_note(target, op)
            if started is not None:
                changed.add(op['id'])
        else:
            log.append(['unknown operation', kind, op.get('id')])
    return rules
