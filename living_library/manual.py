"""A rule manual built from experience, after AutoManual (Chen et al., NeurIPS 2024, arXiv 2405.16247).

Adapted to this agent (a hierarchical step-by-step ReAct agent, not a code-writing planner):
  * A rule has a type, the rule text (it starts with when it applies), an example (a short action
    sequence or observation, not Python) and a validation note (AutoManual's validation log; never
    shown to the agent).
  * Types, as in AutoManual: Special Phenomenon/Mechanism, Success Process, Corrected Error,
    Unresolved Error. AutoManual's fifth type, Useful Helper Method (code), is this project's
    replay-verified code skill library, which keeps running alongside the manual.
  * After every practice game a Builder (the same local model) sees the game and the current rules.
    The case is decided from the game: direct success (won without an invalid action), indirect
    success (won after errors), failure. Case-conditioned prompting, as in AutoManual: the Builder
    first says whether the rules or the agent fell short, and each case limits what it may write.
    The limits are enforced in code, not only asked for.
  * No cap on the number of rules (AutoManual caps at 12 because it puts every rule in every prompt).
    Instead each rule carries a scope: the kind of task it came from, or "all". A game sees only the
    relevant rules (its kind's Success Process, then its kind's and general rules, newest first, at
    most SHOWN), and the Builder sees the rules relevant to the game it reviews (at most BUILDER_SEES),
    as the AutoManual authors suggest for scaling (retrieval, as in AutoGuide). The Builder still
    prefers updating a related rule to writing a near-duplicate; one Success Process per task kind.
  * E-minus (append-only) may only write new rules: no update, no delete, no merge.

Rule management follows ExpeL (Zhao et al., AAAI 2024, section 4.2): a new rule has importance 2;
UPVOTE and EDIT add 1, DOWNVOTE subtracts 1, and a rule is removed when its importance reaches 0. There
is no direct delete: a wrong rule disappears only after repeated disagreement, so one bad Builder call
cannot erase a good rule. Merging = edit one rule, downvote the other.

Selection and upkeep follow MACLA (Forouzandeh et al., AAMAS 2026, arXiv 2512.18950), implemented
from the paper (its released code does not implement these parts):
  * Bayesian reliability (sec. 4.2): each rule has Beta(alpha, beta), prior Beta(1, 1). After a
    practice game every rule the agent was shown gets alpha+1 if the game was won, else beta+1
    (MACLA checks a procedure's postconditions; a rule has none, so the game outcome is the signal).
  * Expected-utility selection (eq. 4): EU = Rel * mean * R_MAX - Risk * (1 - mean) * C_FAIL
    + LAMBDA_INFO * H[Beta], with Risk = the rule's share of failures on this kind of task. The kind's
    Success Process is always shown first. Rel is task-keyed, as in ExpeL/Memp (a memory is retrieved
    by the similarity of the current task to the tasks it came from / worked on), because short general
    rule text vs task text similarity is mostly noise: evidence = max similarity of the goal to the
    rule's source task(s) and to the goals of games it was shown in and won; text = similarity of goal
    and rule text; Rel = w * evidence + (1 - w) * text with w = wins / (wins + EVIDENCE_PRIOR), so a new
    rule is ranked by its text. Candidates: this kind's rules and the general ones; rules of other kinds
    only when the manual has no rule of this kind (an unseen kind of task) and their evidence >=
    CROSS_TYPE_EVIDENCE. (Goal similarity is dominated by the object: with bge-small, "heat some apple
    and put it in fridge" is 0.97 similar to "clean some apple and put it in fridge" but 0.81 to "heat
    some egg and put it in countertop", so other kinds' rules are never mixed into a known kind.)
    Deterministic, no LLM selector call (ExpeL/AutoGuide-style LLM selection would add a model call per
    game and its own noise; worth considering only for manuals above ~50 rules per kind).
  * Contrastive refinement (sec. 4.3): once a rule has >= MIN_CONTRAST won and lost games since its
    last refinement, the model compares them and rewrites the rule as one short rule with a tighter
    condition (an exclusion goes into the condition; nothing is appended).
    A rule's "contexts" are this refinement's evidence, not rules: one entry per game the rule was shown
    in (task, won/lost, the last valid actions), at most K_CONTEXTS of each. They are bookkeeping, never
    shown to the agent or the Builder, only to the refiner.
  * Merging (sec. 4.1/5.1): a new rule with similarity >= DUP_SIMILARITY to an existing rule of the
    same type and kind of task, or to a general ("all") one, is merged into it (counted as agreement,
    its task kept as extra evidence) instead of added. Merging never widens a rule's scope.
  * Pruning (eq. 8): above CAPACITY rules, drop the lowest U = 0.5 mean + 0.3 use share + 0.2 recency.
  * Not taken: meta-procedures (the paper's description is inconsistent and its code never uses them).
E-minus is append-only: no Beta updates, refinement, merging or pruning.

Experience gathering follows ExpeL (Zhao et al., AAAI 2024, sec. 4.1), which uses Reflexion (Shinn et
al. 2023): when a practice game of E or E-minus is lost, the agent reflects on the failed attempt
(Reflexion's ALFWorld reflection prompt) and replays the same game from its start with the reflections
in view, up to RETRIES times, stopping at the first win. The Builder then gets the failed and the
successful attempt of the same task and writes a contrastive Corrected Error rule ("When <situation>, do
Y instead of X"); only if every retry fails does it write an Unresolved Error. Retries read the memory
(rules and skills) but change nothing, and never run in evaluation or for C, D, E-text. The practice
record keeps the FIRST attempt (success, trace, Beta updates); retry costs are added to the game's
totals and also reported separately under "retries". E-minus retries too, so the ablation differs from E
only in append-only rule management.

Unresolved Error rules (from a failure without a contrasting success) are Builder notes only: they are
never shown to the agent (ExpeL extracts insights only from success/failure comparisons), and a retry
success may turn one into a Corrected Error. Likewise any rule WRITTEN from a game that was not won
(first attempt lost, no retry won) is an unconfirmed guess and a hidden Builder note, whatever its type
("verified": false), until the Builder upvotes, updates or merges into it after a won game or retry.
A lost game may not rewrite the text or example of a rule the agent sees (the confirmed text stays;
only its validation note is added). Rules other than a Success Process may not list steps.

Retirement (added to MACLA's capacity pruning, which rarely triggers): every practice game also counts
toward a base win rate of its kind of task for each rule that could be shown in it (same kind or "all",
since the rule was written), so a rule is compared with games of the same difficulty and period, not
with 0.5. A rule shown in at least RETIRE_MIN games is retired (logged) when it never won, or when its
Beta posterior puts its win rate below that base rate with probability >= RETIRE_CONFIDENCE (the base
rate test alone never fires for kinds of task that are almost never won).

The Builder answers with JSON operations (write_rule / update_rule / upvote_rule / downvote_rule),
never code.

Rule form: both papers aim at short, general, reusable rules (AutoManual's rules; MACLA's abstract
procedures with preconditions). The Builder and refiner are asked for one general condition -> action
sentence (a Success Process: a few generic steps), and a cheap check in code rejects rule text that is
too long or names numbered objects ("drawer 3"); rejections are reported as errors.
"""
import math
import re

from scipy.stats import beta as beta_distribution

from . import avoid

R_MAX, C_FAIL, LAMBDA_INFO = 1.0, 0.5, 0.1     # MACLA sec. 5.1 / appendix C.2
MIN_CONTRAST = 3                                # MACLA sec. 5.1: >= 3 successes and >= 3 failures
K_CONTEXTS = 15                                 # MACLA sec. 5.1: K_fail
DUP_SIMILARITY = 0.85                           # MACLA sec. 5.1: theta_dup
CAPACITY = 200                                  # MACLA sec. 5.1: N_p
TAU = 100.0                                     # recency scale for pruning, in practice games
RETRIES = 3                  # ExpeL: up to 3 Reflexion retries of a failed practice game
RETRY_CONDITIONS = ('E', 'E-minus')
MAX_REFLECTION = 400         # characters
HIDDEN = ('Unresolved Error', avoid.POOL)    # Builder notes and the failure pools, never shown to the agent
RETIRE_MIN = 4               # games shown before a rule can be retired
RETIRE_CONFIDENCE = 0.9      # P(rule win rate < base rate of its kind of task) needed to retire it
EVIDENCE_PRIOR = 2           # retrieval: weight of task evidence = wins / (wins + EVIDENCE_PRIOR)
CROSS_TYPE_EVIDENCE = 0.85   # evidence needed to show another kind's rule in an unseen kind of task
MAX_SOURCES = 15             # source tasks kept per rule (written from + merged in)
MAX_WORDS = {'Success Process': 45, avoid.TYPE: avoid.MAX_WORDS}   # rule-text limit enforced in code
MAX_WORDS_DEFAULT = 35
MAX_EXAMPLE = 200                       # characters
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
    'A rule from an agent\'s manual was shown in several games of a household text game (ALFWorld). '
    'In some the agent won, in others it lost. Compare the won and lost games and rewrite the rule so it '
    'helps in cases like the won ones and does not mislead in cases like the lost ones: make its condition '
    'more precise (if it should not be used in some situation, say so inside the condition, e.g. "If ... '
    'and ..., ...") or correct its action. Rewrite it, do not add to it: the result must not be longer than '
    'the original. ' + RULE_FORM + ' Keep its type; do not invent commands the games did not show. '
    'Output {"rule": "..."}.')
NEW_IMPORTANCE = 2
import copy

SHOWN = 8           # rules shown to the planner and actor in a game
BUILDER_SEES = 24   # rules shown to the Builder for the game it reviews
TYPES = ('Special Phenomenon', 'Success Process', 'Corrected Error', 'Unresolved Error', avoid.TYPE)
CASE_TYPES = {      # which rule types each case may WRITE (updates follow the same limits)
    'direct success': ('Success Process', 'Special Phenomenon'),
    'indirect success': ('Success Process', 'Special Phenomenon', 'Corrected Error'),
    'failure': ('Unresolved Error', 'Special Phenomenon'),
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
    'update_rule {id, and any of rule, example, validation} to correct or generalise an existing rule: '
    'give the whole new rule, still one short general rule, never append another case to it '
    '(prefer this over writing a near-duplicate); upvote_rule {id} when this game confirms a rule; '
    'downvote_rule {id} when this game contradicts a rule or shows it is wrong (also downvote a rule you '
    'merged into another). Each rule has an importance; rules that reach 0 are removed. Never merge two '
    'Success Process rules. There is at most one Success Process per kind of task (task_type): if '
    'one exists for this kind of task, update it instead of writing another. The rules you get are '
    'those for this kind of task and the general ones: if what you want to say is already in one of them, '
    'even in other words, update or upvote that rule; never restate it as a new rule. Use "validation" to note when a later game confirmed or contradicted a '
    'rule, in one short sentence. A rule with "confirmed": false is an unconfirmed guess from a lost game, '
    'not shown to the agent: upvote or update it when this game confirms it. '
    'Output {"diagnosis": "...", "operations": [...]}; an empty list is fine.')
CASE_NOTES = {
    'direct success': ' This game was won without mistakes: you may write or update a Success Process '
                      'and Special Phenomenon rules only.',
    'indirect success': ' This game was won after mistakes: if the rules fell short, write a Corrected '
                        'Error for the main mistake and a Success Process; if the agent ignored existing '
                        'rules, update those rules to stress what was ignored instead.',
    'failure': ' This game was lost: if the rules fell short, write at most ONE Unresolved Error rule; '
               'if the agent ignored existing rules, add a validation note to them (a lost game cannot '
               'change their text). Never write a Success Process from a lost game.',
    'corrected failure': ' This game was lost (game), then the agent replayed the same game after '
                         'reflecting on its failure (reflections) and won (successful_retry). Compare the '
                         'two attempts and write ONE Corrected Error rule about the decisive difference: '
                         '"When <situation>, do <Y> instead of <X>" or "When <situation>, never do <X>". '
                         'If an Unresolved Error note shown here is about the same situation, update that '
                         'note instead, giving "type": "Corrected Error" and the corrected rule text. You '
                         'may also write or update the Success Process from the won attempt.',
}
RETRY_NOTE = (' The agent replayed this lost game after reflecting and lost again each time '
              '(failed_retries): an Unresolved Error note may say what kept failing.')
APPEND_ONLY_NOTE = ' Append-only manual: you may only use write_rule; existing rules cannot be changed.'


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
    if kind not in ('Success Process', 'Corrected Error') and recipe_shaped(text):
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
    new = tidy(data['rule']) if isinstance(data, dict) and isinstance(data.get('rule'), str) else ''
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
    new = tidy(data['rule']) if isinstance(data, dict) and isinstance(data.get('rule'), str) else ''
    if not new or foreign_actions(task_type, new) or rule_problems(kind, new):
        raise ValueError(f"rejected {kind} text, has steps of another kind of task ({', '.join(bad)}): {text[:80]}")
    return new


def checked(kind, text, ask=None, task_type=None):
    """Tidied rule text, or ValueError naming its problems. With `ask` (a model call), text naming
    specific objects or rooms gets one general rewrite, or is rejected; so does text (for a rule scoped
    to `task_type`) with an action of another kind of task."""
    text = tidy(text)
    problems = rule_problems(kind, text)
    if ask is not None and not problems:
        text = generalize(kind, text, ask)
        if task_type:
            text = drop_foreign(kind, text, task_type, ask)
    if problems:
        raise ValueError(f"rejected {kind} text, {'; '.join(problems)}: {text[:80]}")
    return text


def builder_guide(case, append_only, task_type, shown):
    """The Builder's instructions for one game: the case limits and whether a Success Process exists."""
    allowed = CASE_TYPES[case]
    recipe = next((r for r in shown if r['type'] == 'Success Process' and r.get('task_type') == task_type), None)
    note = f" You may write only these types here: {', '.join(allowed)}."
    if recipe is not None and 'Success Process' in allowed:
        note += (f" This kind of task already has a Success Process ({recipe['id']}): never write another "
                 'one; update it only if this game shows a better generic recipe.')
    return BUILDER_GUIDE + CASE_NOTES[case] + note + (APPEND_ONLY_NOTE if append_only else '')


def shown_to_agent(rule):
    """Not a Builder note: neither an Unresolved Error nor an unconfirmed guess from a lost game."""
    return rule['type'] not in HIDDEN and rule.get('verified', True)


MODES = ('task', 'placeholder', 'plan', 'steps')   # retrieval modes (how rules are chosen, not written)
KEEP_NAMES = {'desklamp', 'floorlamp', 'lamp'}      # the light in "look at X under the desklamp" is not a receptacle


def mask(goal):
    """A goal with its object and receptacle names replaced by OBJ / RECEP (ALFWorld goals are regular):
    "heat some apple and put it in fridge" -> "heat some OBJ and put it in RECEP"."""
    def swap(m):
        word = m.group(0).lower()
        if word in avoid.OBJECTS or (word.endswith('s') and word[:-1] in avoid.OBJECTS):
            return 'OBJ'
        return 'RECEP' if word in avoid.PLACES and word not in KEEP_NAMES else m.group(0)
    return re.sub(r'[A-Za-z]+', swap, goal)


def won_plans(rule):
    """The plans (subgoal descriptions, ' ; '-joined) of the games this rule was shown in and won."""
    return list(dict.fromkeys(c['plan'] for c in rule.get('contexts', []) if c.get('won') and c.get('plan')))


def plan_coverage(rules):
    """(rules the agent can see that have a stored won plan, rules the agent can see)."""
    seen = [r for r in rules if shown_to_agent(r) and r['type'] != avoid.POOL]
    return sum(bool(won_plans(r)) for r in seen), len(seen)


def for_agent(rules, task_type, k, query=None, similarity=None, mode='task', probe=''):
    """The rules a game shows its planner and actor: relevant ones, without Builder notes.
    `query` is the goal. mode: 'task' = goal vs the tasks a rule won; 'placeholder' = the same with object
    and receptacle names masked; 'plan' = `probe` (the planner's subgoals for this game) vs the plans of
    games the rule won (a rule with no stored plan falls back to 'task'); 'steps' = like plan, with `probe`
    a subgoal plus recent actions, also matched against each stored subgoal."""
    known = any(r.get('task_type') == task_type for r in rules)
    text_query, evidence = query, None
    if mode == 'placeholder' and query:
        masked = mask(query)
        evidence = lambda r: [(masked, mask(g)) for g in evidence_tasks(r)]
        query = masked
    elif mode in ('plan', 'steps') and probe and query:
        def evidence(r):
            plans = won_plans(r)
            if not plans:
                return [(text_query, g) for g in evidence_tasks(r)]
            if mode == 'steps':
                plans += [d for p in plans for d in p.split(' ; ')]
            return [(probe, p) for p in dict.fromkeys(plans)]
    return relevant([r for r in rules if shown_to_agent(r)], task_type, k, query, similarity,
                    cross_type=not known, text_query=text_query, evidence=evidence)


def case_of(result):
    if not result['success']:
        return 'failure'
    return 'direct success' if all(t['valid'] for t in result['trace']) else 'indirect success'


def reliability(rule):
    return rule.get('alpha', 1) / (rule.get('alpha', 1) + rule.get('beta', 1))


def expected_utility(rule, relevance, task_type):
    """MACLA eq. 4."""
    a, b = rule.get('alpha', 1), rule.get('beta', 1)
    mean = a / (a + b)
    same = [c for c in rule.get('contexts', []) if c.get('task_type') == task_type]
    risk = sum(not c['won'] for c in same) / len(same) if same else 0.0
    return relevance * mean * R_MAX - risk * (1 - mean) * C_FAIL + LAMBDA_INFO * float(beta_distribution(a, b).entropy())


def evidence_tasks(rule):
    """The goals a rule is keyed by: its source task(s) and the games it was shown in and won."""
    goals = [s.get('task') for s in rule.get('sources', [])] + [
        c.get('task') for c in rule.get('contexts', []) if c.get('won')]
    return list(dict.fromkeys(g for g in goals if g))


def relevance(rule, sims, evidence=None):
    """Task-keyed relevance (ExpeL/Memp): (Rel, evidence); `sims` maps text -> similarity to the goal.
    `evidence`: the rule's evidence similarity when the caller computed it (retrieval modes)."""
    text = max(0.0, sims[rule['rule']])
    if evidence is None:
        evidence = max([max(0.0, sims[g]) for g in evidence_tasks(rule)], default=0.0)
    wins = observed(rule)[0]
    w = wins / (wins + EVIDENCE_PRIOR)
    return w * evidence + (1 - w) * text, evidence


def relevant(rules, task_type, k, query=None, similarity=None, cross_type=False, text_query=None, evidence=None):
    """This kind of task's Success Process first, then its other rules and the general ones, ranked by
    MACLA's expected utility with task-keyed relevance when a query and similarity function are given,
    else by importance. `cross_type`: other kinds' rules may join when their task evidence is high.
    `evidence(rule)`: [(query, text)] pairs the rule is keyed by (default: `query` vs its tasks);
    `text_query`: what the rule text is compared with (default `query`)."""
    def number(r):
        return int(r['id'].split('_')[1])
    rules = [r for r in rules if r['type'] != avoid.POOL]
    recipe = [r for r in rules if r['type'] == 'Success Process' and r.get('task_type') == task_type]
    others = [r for r in rules if r not in recipe and r['type'] != 'Success Process'
              and r.get('task_type') in (task_type, 'all', None)]
    if not (query and similarity):
        others.sort(key=lambda r: (r.get('importance', NEW_IMPORTANCE), number(r)), reverse=True)
        return (recipe + others)[:k]
    foreign = [r for r in rules if cross_type and r not in recipe and r not in others
               and r['type'] != 'Success Process']
    pool = others + foreign
    if not pool:
        return recipe[:k]
    text_query = text_query or query
    pairs = {id(r): evidence(r) if evidence else [(query, g) for g in evidence_tasks(r)] for r in pool}
    wanted = {text_query: [r['rule'] for r in pool]}
    for found in pairs.values():
        for q, t in found:
            wanted.setdefault(q, []).append(t)
    sims = {}
    for q, texts in wanted.items():
        texts = list(dict.fromkeys(texts))
        sims.update({(q, t): float(s) for t, s in zip(texts, similarity(q, texts))})
    scored = {id(r): relevance(r, {r['rule']: sims[(text_query, r['rule'])]},
                               max([max(0.0, sims[p]) for p in pairs[id(r)]], default=0.0)) for r in pool}
    pool = others + [r for r in foreign if scored[id(r)][1] >= CROSS_TYPE_EVIDENCE]
    utility = {id(r): expected_utility(r, scored[id(r)][0], task_type) for r in pool}
    pool.sort(key=lambda r: (utility[id(r)], number(r)), reverse=True)
    return (recipe + pool)[:k]


def new_rule(rule_id, kind, text, example, task_type, verified=True, sources=()):
    return {'id': rule_id, 'type': kind, 'rule': text, 'example': example, 'validation': '',
            'importance': NEW_IMPORTANCE, 'task_type': task_type, 'alpha': 1, 'beta': 1,
            'contexts': [], 'refined_at': [0, 0], 'last_used': None, 'base': [0, 0],
            'verified': bool(verified), 'sources': [dict(s) for s in sources]}


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
          goal=None, ask=None):
    """Apply Builder operations under the case limits; returns the applied operations (for batching).
    `visible`: ids the Builder was shown (it may only change those); default all. `goal`: the game's
    task, stored on written rules (and merged ones) as task-keyed retrieval evidence.
    A game that was not won ('failure') writes only hidden, unconfirmed rules and cannot rewrite what
    the agent sees; a won game (or retry) confirms the rules it upvotes, updates or merges into."""
    applied, writes = [], 0
    visible = {r['id'] for r in rules} if visible is None else set(visible)
    by_id = {r['id']: r for r in rules}
    allowed = CASE_TYPES[case]
    won = case != 'failure'
    source = {'task': goal, 'task_type': task_type} if goal else None

    def confirm(rule):
        """{'verified': True} when this won game confirms a hidden guess (for the applied op)."""
        if won and not rule.get('verified', True):
            rule['verified'] = True
            log.append(f"{rule['id']} confirmed by a won game (now shown to the agent)")
            return {'verified': True}
        return {}
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
                text = checked(op['type'], op['rule'], ask,
                               task_type if op['type'] == 'Success Process' or op.get('scope') != 'all' else None)
                if any(tidy(r['rule']).lower() == text.lower() for r in rules):
                    raise ValueError('duplicate rule')
                if op['type'] == 'Success Process':
                    # As in AutoManual: one Success Process per kind of task; later games refine it.
                    existing = next((r for r in rules if r['type'] == 'Success Process'
                                     and r.get('task_type') == task_type), None)
                    if existing is not None:
                        raise ValueError(f"a Success Process for this kind of task exists ({existing['id']}): "
                                         'update it instead')
                scope = 'all' if op.get('scope') == 'all' and op['type'] != 'Success Process' else task_type
                if scope == 'all' and task_type and kind_specific(text):
                    scope = task_type
                    log.append(f'a general rule was limited to {task_type} (its text names a task-specific action)')
                twin = None if append_only or similarity is None else near_duplicate(
                    rules, op['type'], scope, text, similarity, task_type)
                if twin is not None:
                    # MACLA: merge into the existing rule instead of adding a near-copy (counts as agreement).
                    # Its scope never changes; this game's task is kept as extra retrieval evidence.
                    add_source(twin, source)
                    narrowed(twin, task_type, log)
                    merged = {'op': 'merge_rule', 'id': twin['id'], 'task_type': twin.get('task_type'),
                              **({'source': source} if source else {}), **confirm(twin)}
                    vote(rules, by_id, twin['id'], 1)
                    applied.append(merged)
                    log.append(f"merged a new rule into {twin['id']}")
                    continue
                example = ' '.join(str(op.get('example') or '').split())[:MAX_EXAMPLE]
                rule = new_rule(next_id(), op['type'], text, example, scope, verified=won,
                                sources=[source] if source else [])
                rules.append(rule)
                by_id[rule['id']] = rule
                writes += 1
                if not won and rule['type'] not in HIDDEN:
                    log.append(f"{rule['id']} is a hidden Builder note until a won game confirms it")
                applied.append({'op': 'write_rule', **{k: rule[k] for k in ('type', 'rule', 'example', 'task_type',
                                                                             'verified', 'sources')}})
            elif kind in ('update_rule', 'upvote_rule', 'downvote_rule'):
                if append_only:
                    raise ValueError('append-only manual: rules cannot be changed')
                rule = by_id.get(op.get('id'))
                if rule is None or rule.get('id') not in visible:
                    raise ValueError(f"unknown rule id {op.get('id')}")
                if kind == 'update_rule' and rule['type'] == avoid.TYPE:
                    raise ValueError('an Anti-Pattern is written and checked by code; vote on it, do not rewrite it')
                if kind != 'update_rule':
                    delta = 1 if kind == 'upvote_rule' else -1
                    confirmed = confirm(rule) if delta > 0 else {}
                    if vote(rules, by_id, rule['id'], delta):
                        log.append(f"removed {rule['id']} (importance reached 0)")
                    applied.append({'op': kind, 'id': rule['id'], **confirmed})
                    continue
                changes = {k: str(op[k])[:600] for k in ('rule', 'example', 'validation') if isinstance(op.get(k), str)}
                if not changes:
                    raise ValueError('update needs rule, example or validation')
                # Only a success/failure pair of the same task turns a note into a rule the agent sees;
                # any other type in an update is ignored (types never change otherwise).
                if (op.get('type') == 'Corrected Error' and rule['type'] == 'Unresolved Error'
                        and case == 'corrected failure' and 'rule' in changes):
                    changes['type'] = 'Corrected Error'
                elif op.get('type') not in (None, rule['type']):
                    log.append(f"{rule['id']} keeps its type {rule['type']} (only a retry success turns a note "
                               'into a Corrected Error)')
                if not won and shown_to_agent(rule) and ({'rule', 'example'} & set(changes)):
                    # A lost game's rewrite would be an unverified guess shown to the agent: keep the text.
                    changes = {k: v for k, v in changes.items() if k not in ('rule', 'example')}
                    log.append(f"{rule['id']} keeps its text (a lost game may not rewrite a rule the agent sees)")
                    if not changes:
                        continue
                if 'rule' in changes:
                    changes['rule'] = checked(changes.get('type', rule['type']), changes['rule'], ask,
                                              rule.get('task_type'))
                if 'example' in changes:
                    changes['example'] = ' '.join(changes['example'].split())[:MAX_EXAMPLE]
                if 'validation' in changes:   # keep the last few notes, as AutoManual does
                    changes['validation'] = ' | '.join(([rule['validation']] if rule['validation'] else [])
                                                       + [changes['validation']]).split(' | ')[-3:]
                    changes['validation'] = ' | '.join(changes['validation'])
                rule.update(changes)
                if narrowed(rule, task_type, log):
                    changes['task_type'] = rule['task_type']
                changes.update(confirm(rule))
                vote(rules, by_id, rule['id'], 1)            # ExpeL: EDIT also counts as agreement
                applied.append({'op': 'update_rule', 'id': rule['id'], **changes})
            else:
                raise ValueError(f'unknown operation {kind!r}')
        except ValueError as exc:
            log.append(str(exc))
    return applied


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


def observe(rules, shown_ids, won, context, position, violated=()):
    """MACLA Beta update and contrastive contexts for the rules shown in a game; returns the op.
    `violated`: shown Anti-Pattern rules whose pattern the agent did anyway."""
    op = {'op': 'outcome', 'ids': list(shown_ids), 'won': bool(won), 'context': context, 'position': position,
          **({'violated': list(violated)} if violated else {})}
    _observe(rules, op)
    return op


def _observe(rules, op):
    by_id = {r['id']: r for r in rules}
    kind = op['context'].get('task_type')
    for rule in rules:   # base rate of this kind of task for every rule that could have been shown
        if rule.get('task_type') in (kind, 'all', None):
            won, games = rule.get('base', [0, 0])
            rule['base'] = [won + bool(op['won']), games + 1]
    for rule_id in op['ids']:
        rule = by_id.get(rule_id)
        if rule is None:
            continue
        key = 'alpha' if op['won'] else 'beta'
        rule[key] = rule.get(key, 1) + 1
        contexts = rule.get('contexts', []) + [{**op['context'], 'won': op['won']}]
        won = [c for c in contexts if c['won']][-K_CONTEXTS:]        # keep the newest K of each kind
        lost = [c for c in contexts if not c['won']][-K_CONTEXTS:]
        rule['contexts'] = won + lost
        rule['last_used'] = op['position']
        if rule_id in op.get('violated', ()):
            rule['violations'] = rule.get('violations', 0) + 1


def observed(rule):
    """Games won / lost while this rule was shown (from Beta(1, 1); contexts are capped, counts are not)."""
    return [rule.get('alpha', 1) - 1, rule.get('beta', 1) - 1]


def retirable(rule):
    """Shown in >= RETIRE_MIN games and, by its Beta posterior, clearly below the base win rate of
    the games it could have been shown in (Laplace-smoothed)."""
    won, lost = observed(rule)
    base_won, base_games = rule.get('base', [0, 0])
    if won + lost < RETIRE_MIN or rule['type'] == avoid.POOL:
        return False
    if won == 0 and rule['type'] == avoid.TYPE:
        # An Anti-Pattern belongs to a kind of task that is mostly lost, so "never won" proves nothing:
        # it is retired when the agent did the avoided thing in every game it was shown in (it changed nothing).
        return rule.get('violations', 0) >= won + lost
    if won == 0:          # never won while shown: retired whatever the base rate (which may be ~0)
        return True
    if not base_games:
        return False
    base = (base_won + 1) / (base_games + 2)
    return float(beta_distribution(1 + won, 1 + lost).cdf(base)) >= RETIRE_CONFIDENCE


def retire(rules, report):
    """Remove rules that do clearly worse than their kind of task's base rate; logged."""
    for rule in [r for r in rules if retirable(r)]:
        won, lost = observed(rule)
        op = {'op': 'retire', 'id': rule['id'], 'won': won, 'lost': lost, 'base': list(rule['base'])}
        avoid.forget(rules, rule)
        report['operations'].append(op)
        report['errors'].append(f"retired {rule['id']} (won {won} of {won + lost} games shown"
                                f"{', never won' if not won else ''}; base "
                                f"{rule['base'][0]} of {rule['base'][1]})")


def refinable(rule):
    if rule['type'] in (avoid.TYPE, avoid.POOL):      # worded and checked by code; a rewrite would lose that
        return False
    won, lost = observed(rule)
    done = rule.get('refined_at', [0, 0])
    return won - done[0] >= MIN_CONTRAST and lost - done[1] >= MIN_CONTRAST


def refine(agent, rules, candidates, report):
    """MACLA contrastive refinement of at most one rule per game (cost control)."""
    for rule in candidates:
        if not refinable(rule):
            continue
        won = [c for c in rule['contexts'] if c['won']][-MIN_CONTRAST * 2:]
        lost = [c for c in rule['contexts'] if not c['won']][-MIN_CONTRAST * 2:]
        try:
            data = agent._ask('refiner', {'instructions': REFINE_GUIDE,
                                          'rule': {k: rule[k] for k in ('type', 'rule', 'example')},
                                          'won_games': won, 'lost_games': lost,
                                          'response_schema': {'rule': 'string'}})
            text = data.get('rule')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('refiner gave no rule')
            text = checked(rule['type'], text, agent._ask, rule.get('task_type'))    # a concise rewrite; nothing is appended
            op = {'op': 'refine', 'id': rule['id'], 'rule': text, 'refined_at': observed(rule)}
            _refine(rules, op)
            report['operations'].append(op)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['errors'].append(f'refiner: {exc}'[:200])
        return


def _refine(rules, op):
    for rule in rules:
        if rule['id'] == op['id']:
            rule['rule'], rule['refined_at'] = op['rule'], op['refined_at']


def prune(rules, position, log):
    """MACLA eq. 8 above CAPACITY: drop the lowest 0.5 mean + 0.3 use share + 0.2 recency."""
    total = sum(r.get('alpha', 1) + r.get('beta', 1) - 2 for r in rules) or 1
    while sum(r['type'] != avoid.POOL for r in rules) > CAPACITY:
        def utility(r):
            uses = r.get('alpha', 1) + r.get('beta', 1) - 2
            age = position - (r['last_used'] if r.get('last_used') is not None else 0)
            return 0.5 * reliability(r) + 0.3 * uses / total + 0.2 * math.exp(-max(age, 0) / TAU)
        victim = min((r for r in rules if r['type'] != avoid.POOL), key=utility)
        avoid.forget(rules, victim) if victim['type'] == avoid.TYPE else rules.remove(victim)
        log.append(f"pruned {victim['id']} (lowest utility)")


def vote(rules, by_id, rule_id, delta):
    """Change a rule's importance; remove it at 0. Returns True if it was removed."""
    rule = by_id[rule_id]
    rule['importance'] = rule.get('importance', NEW_IMPORTANCE) + delta
    if rule['importance'] <= 0:
        rules.remove(rule)
        del by_id[rule_id]
        return True
    return False


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
        replay_agent = type(agent)(agent.cfg, agent.condition, agent.model, agent.library, agent.embedder,
                                   agent.env_factory, trajectories=agent.trajectories, frozen=True,
                                   rules=agent.rules, reflections=list(reflections))
        last = replay_agent.run(agent.task, agent.seed, {**agent.context, 'attempt': attempt})
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
    """One Builder pass after a practice game. Mutates agent.rules; returns a report."""
    rules, report = agent.rules, {'case': case_of(agent.result), 'operations': [], 'errors': []}
    append_only = agent.condition == 'E-minus'
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
    if not append_only:   # every game: Beta updates of the shown rules and the base rates
        report['operations'].append(observe(rules, agent.rules_shown, agent.result['success'],
                                            {'task': agent.public_task.get('goal', ''),
                                             'task_type': agent.task.get('task_type'),
                                             'steps': [t['action'] for t in agent.result['trace'] if t['valid']][-12:],
                                             **({'plan': agent.plan_text} if agent.plan_text else {})},
                                            position,
                                            avoid.violated(rules, agent.rules_shown, avoid.compact(agent.result['trace']))))
        retire(rules, report)
    shown = relevant(rules, agent.task.get('task_type'), BUILDER_SEES)
    guide = builder_guide(report['case'], append_only, agent.task.get('task_type'), shown)
    if 'failed_retries' in extra:
        guide += RETRY_NOTE
    try:
        data = agent._ask('builder', {
            'instructions': guide,
            'game': _game(agent.result, agent.public_task.get('goal', '')), **extra,
            'task_type': agent.task.get('task_type'),
            'rules': [{k: r.get(k, NEW_IMPORTANCE if k == 'importance' else '')
                       for k in ('id', 'type', 'rule', 'example', 'validation', 'importance')}
                      | ({} if r.get('verified', True) else {'confirmed': False}) for r in shown],
            'response_schema': {'diagnosis': 'imperfect rules | imperfect agent',
                                'operations': [{'op': 'write_rule | update_rule | upvote_rule | downvote_rule', 'id': 'rule_N',
                                                'type': '|'.join(CASE_TYPES[report['case']]), 'rule': 'string', 'example': 'string',
                                                'validation': 'string'}]}})
        report['diagnosis'] = data.get('diagnosis')
        report['operations'] += apply(rules, data.get('operations'), report['case'], append_only, next_id,
                                      report['errors'], agent.task.get('task_type'), [r['id'] for r in shown],
                                      agent.embedder.similarity, agent.public_task.get('goal', ''), agent._ask)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        report['errors'].append(f'builder: {exc}'[:200])
    report['operations'] += avoid_update(agent, rules, report, summary, append_only, next_id)
    if not append_only:
        refine(agent, rules, [r for r in rules if r['id'] in set(agent.rules_shown)], report)
        before = {r['id'] for r in rules}
        prune(rules, position, report['errors'])
        for gone in before - {r['id'] for r in rules}:
            report['operations'].append({'op': 'prune', 'id': gone})
    return report


def replay(live, operations, log):
    """Batching: apply one game's applied operations onto the live rules (ids re-issued for writes)."""
    rules = copy.deepcopy(live)
    by_id = {r['id']: r for r in rules}
    counter = [max([int(r['id'].split('_')[1]) for r in rules] + [0])]

    def next_id():
        counter[0] += 1
        return f'rule_{counter[0]}'
    for op in operations:
        if op['op'] in ('pool_game', 'pool_won'):
            avoid.apply_pool_op(rules, op, next_id)
            by_id.clear()
            by_id.update({r['id']: r for r in rules})
            continue
        if op['op'] == 'outcome':
            _observe(rules, op)
            continue
        if op['op'] == 'refine':
            _refine(rules, op)
            continue
        if op['op'] in ('prune', 'retire'):
            if op['id'] in by_id:
                gone = by_id.pop(op['id'])
                avoid.forget(rules, gone) if gone['type'] == avoid.TYPE else rules.remove(gone)
            continue
        if op['op'] == 'write_rule':
            if any(r['rule'] == op['rule'] for r in rules) or (
                    op.get('pattern') and any(r.get('pattern') and r['pattern']['sig'] == op['pattern']['sig']
                                              and r.get('task_type') == op.get('task_type') for r in rules)) or (
                    op['type'] == 'Success Process' and any(r['type'] == 'Success Process' and
                                                             r.get('task_type') == op.get('task_type') for r in rules)):
                log.append(['duplicate rule', op['rule'][:60]])
                continue
            rule = new_rule(next_id(), op['type'], op['rule'], op['example'], op.get('task_type'),
                            op.get('verified', True), op.get('sources', ()))
            if op.get('pattern'):
                rule['pattern'] = copy.deepcopy(op['pattern'])
            rules.append(rule)
            by_id[rule['id']] = rule
        elif op['id'] not in by_id:
            log.append(['rule already gone', op['id']])
        elif op['op'] in ('upvote_rule', 'downvote_rule'):
            if op.get('verified'):
                by_id[op['id']]['verified'] = True
            vote(rules, by_id, op['id'], 1 if op['op'] == 'upvote_rule' else -1)
        elif op['op'] == 'merge_rule':        # scope never changes on a merge
            add_source(by_id[op['id']], op.get('source'))
            if by_id[op['id']].get('task_type') == 'all' and op.get('task_type') not in (None, 'all'):
                by_id[op['id']]['task_type'] = op['task_type']
            if op.get('verified'):
                by_id[op['id']]['verified'] = True
            vote(rules, by_id, op['id'], 1)
        else:
            by_id[op['id']].update({k: v for k, v in op.items()
                                    if k in ('rule', 'example', 'validation', 'type', 'verified', 'task_type')})
            vote(rules, by_id, op['id'], 1)
    return rules
