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
UPVOTE and EDIT add 1, DOWNVOTE subtracts 1. Amended 2026-11-20 (design review): importance is only a ranking
signal and a vote never removes a rule (ExpeL removed it at 0; the outcome-aware Builder's votes deleted good
rules); rules are removed only by statistical retirement (and MACLA capacity pruning).

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
E-minus is append-only: no text edits, deletion, refinement, merging, folding, retirement or pruning. Since the
2026-11-20 design review it keeps the same evidence bookkeeping as E (outcome-blind judge, Beta updates,
contexts, base rates, hidden-guess promotion), used for retrieval and visibility only, so E and E-minus differ
only in that E may edit, delete, merge and fold rules.

Design review (2026-11-20, results/DECISIONS.md), E unless noted:
  1. The text freeze covers every visible rule (young rules and rejected instructed commands excepted); any
     text change starts fresh counters (fresh_counters; the op keeps the old text). The exceptions end after
     MAX_REWRITES text changes of the verified rule (`rewrites`, never reset; refine and folds count too).
  2. Contrastive refinement only for rules whose followed-win rate is below the base rate (refinable).
  3. A recipe is credited only when the judge says it was followed (observe); "never won" retires a rule only
     if its kind of task has had wins; a kind's only recipe is never retired (sole_recipe).
  4. E-minus: the same bookkeeping (above).
  5. Retrieval keeps one slot for a rarely shown rule (take) and ranks by lift over the base rate (lift).
  6. A hidden guess is promoted only with CONFIRM_WINS followed wins and a followed-win rate >= the base rate,
     counting followed losses (promoted); a text change resets it.
  7. Both conditions' Builders see the relevant rules plus the newest (for_builder); votes never delete.
  8. Corrected Errors may not list steps (rule_problems).
  9. Batched E re-runs the similarity merge at the end of each batch (batch_dedupe).
  10. A fold keeps the strongest rule's counts; an absorbed rule needs a won credited game.
  11. Base rates are per kind of task: expected wins = the sum of the followed games' kinds' base rates
      (expected_wins), so general rules are compared with the kinds they were followed in.

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
("verified": false). Amended 2026-11-20 (E): a guess is shown only after CONFIRM_WINS won games whose actions
the outcome-blind judge says followed it (guesses are judged alongside the shown rules but never shown);
a Builder upvote, update or merge no longer confirms it. A retry win turns an Unresolved Error into a
Corrected Error only if the judge says the winning retry's actions followed the corrected text.
A lost game may not rewrite the text or example of a rule the agent sees (the confirmed text stays;
only its validation note is added). Rules other than a Success Process may not list steps.

Retirement (added to MACLA's capacity pruning, which rarely triggers): every practice game also counts
toward a base win rate of its kind of task for each rule that could be shown in it (same kind or "all",
since the rule was written), so a rule is compared with games of the same difficulty and period, not
with 0.5. A rule shown in at least RETIRE_MIN games is retired (logged) when it never won, or when its
Beta posterior puts its win rate below that base rate with probability >= RETIRE_CONFIDENCE (the base
rate test alone never fires for kinds of task that are almost never won).

Against recipe drift (amended 2026-11-19, E only; the Builder prompts are unchanged): a verified Success
Process changes its text only by contrastive refinement, never by one game's update_rule; a corrected failure
(retry win) may write rules but not rewrite visible ones (text_frozen). The commands a followed rule instructs
("take the lamp") are checked against the game's trace; a rule whose command the game rejected in
REJECTED_MIN followed games and never accepted in a won game is retired (command_evidence). In batched
practice a rule's text changes at most once per batch, the first change in position order (replay).
Amended 2026-11-20 (E): a young recipe (credited in fewer than YOUNG_CREDITS games) may still be rewritten by
a won game's update, and so may a recipe the judge says a game followed while the game rejected one of its
instructed commands; the judge now runs before the Builder, on the rules as the agent saw them.

The Builder answers with JSON operations (write_rule / update_rule / upvote_rule / downvote_rule),
never code.

Rule form: both papers aim at short, general, reusable rules (AutoManual's rules; MACLA's abstract
procedures with preconditions). The Builder and refiner are asked for one general condition -> action
sentence (a Success Process: a few generic steps), and a cheap check in code rejects rule text that is
too long or names numbered objects ("drawer 3"); rejections are reported as errors. Amended 2026-11-20
(both conditions): instance numbers of ALFWorld objects and receptacles are stripped first ("microwave 1" ->
"the microwave"), and text that still fails gets one model rewrite told its problems before it is rejected.
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
USELESS_MIN = 8              # showings before a rule that is never followed can be retired
USELESS_FOLLOWED = 0.2       # ... when followed in fewer than this share of its showings
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
RARE_SHOWINGS = 3   # a rule shown in fewer games is "rarely shown": one shown slot is kept for the best of them
NEWEST_SLOTS = 2    # Builder slots for the newest rules not otherwise included (2026-11-20 design review)
BASE_PRIOR = 2      # lift smoothing: pseudo-games at the expected (base) rate
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
    'merged into another). Each rule has an importance (votes rank rules; they never remove one). Never merge two '
    'Success Process rules. There is at most one Success Process per kind of task (task_type): if '
    'one exists for this kind of task, update it instead of writing another. The rules you get are '
    'those for this kind of task and the general ones: if what you want to say is already in one of them, '
    'even in other words, update or upvote that rule; never restate it as a new rule. Use "validation" to note when a later game confirmed or contradicted a '
    'rule, in one short sentence. A rule with "confirmed": false is an unconfirmed guess from a lost game, '
    'not shown to the agent: upvote or update it when this game confirms it. '
    'Output {"diagnosis": "...", "operations": [...]}.')
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
                 'one; update it only if this game shows a better generic recipe.')
    return BUILDER_GUIDE + CASE_NOTES[case] + note + (APPEND_ONLY_NOTE if append_only else '')


def shown_to_agent(rule):
    """Not a Builder note: neither an Unresolved Error nor an unconfirmed guess from a lost game."""
    return rule['type'] not in HIDDEN and rule.get('verified', True)


YOUNG_CREDITS = 3          # credited games below which a verified recipe is still young (correctable)
MAX_REWRITES = 2           # text changes of a verified rule after which the young/rejected-step exceptions end


def count_rewrite(rule):
    """One more text change of a verified rule (`rewrites` survives fresh_counters)."""
    rule['rewrites'] = rule.get('rewrites', 0) + 1


def text_frozen(rule, case, rejected_step=False):
    """Why a Builder update may not rewrite this rule's text (None if it may). E only (E-minus never updates).
    A verified rule (any type the agent sees; recipes since 2026-11-19, all types since the 2026-11-20 design
    review) changes only through contrastive refinement (refine), and a corrected failure (a retry win) may
    write new rules but not rewrite visible ones. Exceptions: a young rule (credited in fewer than
    YOUNG_CREDITS games) may still be rewritten by a won game's update; and a rule the outcome-blind judge says
    this game followed while the game rejected one of its instructed commands (`rejected_step`) may be
    rewritten by this game, even a corrected failure (its retry win shows the fix). Any text change of a
    verified rule starts fresh counters (fresh_counters). Both exceptions apply only while the rule's text was
    changed fewer than MAX_REWRITES times (`rewrites`, never reset), so a young rule cannot drift through a
    chain of fresh starts; after that its text changes only by contrastive refinement."""
    if not shown_to_agent(rule):
        return None
    if rule.get('rewrites', 0) >= MAX_REWRITES:
        return (f"a verified {rule['type']} rewritten {rule['rewrites']} times changes only by contrastive "
                'refinement')
    if rejected_step:
        return None
    if credited(rule) >= YOUNG_CREDITS:
        return f"a verified {rule['type']} changes only by contrastive refinement"
    if case == 'corrected failure':
        return 'a corrected failure may write new rules, not rewrite rules the agent sees'
    return None


def rejected_steps(rules, followed, trace):
    """Ids of the visible rules (not Anti-Patterns) the judge says were `followed` in a game whose `trace`
    rejected one of their instructed commands (command_evidence): such a rule may be rewritten by this game."""
    followed = set(followed or ())
    return sorted(r['id'] for r in rules if r['id'] in followed and shown_to_agent(r)
                  and r['type'] not in (avoid.TYPE, avoid.POOL)
                  and 'rejected' in command_evidence(r['rule'], trace).values())


# Counters a text change resets (2026-11-20 design review): the evidence belongs to the old text. Kept: id,
# type, task_type, sources, importance, base (the kind's base win rate since the rule was written).
FRESH = {'alpha': 1, 'beta': 1, 'contexts': [], 'confirmations': 0, 'unused': 0, 'refined_at': [0, 0]}
FRESH_DROPPED = ('credits', 'guess_credits', 'commands', 'violations')


def fresh_counters(rule):
    """Start a rule's evidence afresh after its text changed (the old text's credit is not carried over)."""
    rule.update(copy.deepcopy(FRESH))
    for key in FRESH_DROPPED:
        rule.pop(key, None)
    return rule


def type_rate(rule, task_type):
    """Laplace-smoothed base win rate of `task_type` over the games the rule could have been shown in since it
    was written (rules from before per-type counts: the rule's pooled base)."""
    if 'base_types' in rule:
        won, games = rule['base_types'].get(str(task_type), [0, 0])     # JSON keys are strings
    else:
        won, games = rule.get('base', [0, 0])
    return (won + 1) / (games + 2)


def credit_counts(rule, key='credits'):
    """{task type: [won, lost]} of the games the rule was credited in (followed); rules without per-type
    counts: their Beta counts under their own task type."""
    if key in rule:
        return rule[key]
    if key != 'credits':
        return {}
    won, lost = observed(rule)
    return {str(rule.get('task_type')): [won, lost]} if won + lost else {}


def expected_wins(rule, counts=None):
    """Wins expected from the base rates alone (2026-11-20 review, decision 11): the sum of the base rates of
    the followed games' task types, so a general rule followed mostly in easy kinds of task is compared with
    those kinds."""
    counts = credit_counts(rule) if counts is None else counts
    return sum((won + lost) * type_rate(rule, t) for t, (won, lost) in counts.items())


def expected_rate(rule, task_type=None):
    """Expected (base) win rate of the rule's followed games; with none, the base rate of `task_type`
    (default: the rule's own)."""
    counts = credit_counts(rule)
    games = sum(won + lost for won, lost in counts.values())
    if games:
        return expected_wins(rule, counts) / games
    return type_rate(rule, task_type or rule.get('task_type'))


def lift(rule, task_type=None):
    """Followed-win rate minus the expected (base) rate, smoothed toward the base rate with BASE_PRIOR
    pseudo-games: (wins - expected wins) / (games + BASE_PRIOR); 0 for a rule never credited."""
    won, lost = observed(rule)
    games = won + lost
    return (won - games * expected_rate(rule, task_type)) / (games + BASE_PRIOR)


def showings(rule):
    """Games the rule was shown in (credited or shown but not followed)."""
    return credited(rule) + rule.get('unused', 0)


# Evidence check against traces (E only): the commands a rule instructs, and whether the game rejected them.
COMMAND_VERBS = {'go to': 'go to', 'take': 'take', 'pick up': 'take', 'put': 'move', 'move': 'move',
                 'place': 'move', 'open': 'open', 'close': 'close', 'use': 'use', 'turn on': 'use',
                 'heat': 'heat', 'cool': 'cool', 'clean': 'clean', 'examine': 'examine', 'toggle': 'toggle'}
DETERMINERS = {'the', 'a', 'an', 'some', 'any', 'each', 'another', 'that', 'this'}
NEGATED = re.compile(r"\b(?:instead of|rather than|never|not|don't|do not|cannot|can't|avoid|without|no)\b"
                     r"[^.;:,]*", re.IGNORECASE)
REJECTED_MIN = 2            # followed games in which the instructed command was rejected, to retire the rule


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


def rejected_command(rule):
    """An instructed command of a visible rule that was rejected in >= REJECTED_MIN games where the rule was
    followed and never accepted in a won game (None if there is none)."""
    if rule['type'] in (avoid.TYPE, avoid.POOL) or not shown_to_agent(rule):
        return None
    counts = rule.get('commands', {})
    for verb, noun in instructed_commands(rule['rule']):
        rejected, accepted = counts.get(f'{verb} {noun}', [0, 0])
        if rejected >= REJECTED_MIN and accepted == 0:
            return f'{verb} {noun}'
    return None


MODES =('task', 'placeholder', 'plan', 'steps')   # retrieval modes (how rules are chosen, not written)
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
    """MACLA eq. 4, with the rule's reliability measured as lift over the base rate (2026-11-20 design review):
    mean = 0.5 + lift (clipped to [0, 1]), so a rule that wins as often as its kind of task is 0.5 like a new
    rule, and rules of hard kinds of task are not ranked down for the kind's difficulty."""
    a, b = rule.get('alpha', 1), rule.get('beta', 1)
    mean = min(1.0, max(0.0, 0.5 + lift(rule, task_type)))
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


def _number(rule):
    return int(rule['id'].split('_')[1])


def ranked(rules, task_type, query=None, similarity=None, cross_type=False, text_query=None, evidence=None):
    """(this kind's Success Process, the other candidates ranked, {id(rule): Rel}): candidates are this kind's
    other rules and the general ones, ranked by MACLA's expected utility with task-keyed relevance when a query
    and similarity function are given, else by importance (Rel then empty). `cross_type`: other kinds' rules
    may join when their task evidence is high. `evidence(rule)`: [(query, text)] pairs the rule is keyed by
    (default: `query` vs its tasks); `text_query`: what the rule text is compared with (default `query`)."""
    rules = [r for r in rules if r['type'] != avoid.POOL]
    recipe = [r for r in rules if r['type'] == 'Success Process' and r.get('task_type') == task_type]
    others = [r for r in rules if r not in recipe and r['type'] != 'Success Process'
              and r.get('task_type') in (task_type, 'all', None)]
    if not (query and similarity):
        others.sort(key=lambda r: (r.get('importance', NEW_IMPORTANCE), _number(r)), reverse=True)
        return recipe, others, {}
    foreign = [r for r in rules if cross_type and r not in recipe and r not in others
               and r['type'] != 'Success Process']
    pool = others + foreign
    if not pool:
        return recipe, [], {}
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
    pool.sort(key=lambda r: (utility[id(r)], _number(r)), reverse=True)
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


def relevant(rules, task_type, k, query=None, similarity=None, cross_type=False, text_query=None, evidence=None):
    """This kind of task's Success Process first, then its other rules and the general ones (ranked), at most
    `k` (None: all), with one slot kept for a rarely shown rule (take)."""
    recipe, pool, rel = ranked(rules, task_type, query, similarity, cross_type, text_query, evidence)
    return take(recipe, pool, rel, k)


def for_builder(rules, task_type, k, query=None, similarity=None):
    """The rules the Builder sees for a game, built the same way for E and E-minus (2026-11-20 design review):
    the rules relevant to the game, ranked with the agent's task-keyed function (Builder notes and hidden
    guesses included), plus NEWEST_SLOTS slots for the newest rules not otherwise included."""
    known = any(r.get('task_type') == task_type for r in rules)
    recipe, pool, rel = ranked(rules, task_type, query, similarity, cross_type=not known)
    if len(recipe) + len(pool) <= k:
        return recipe + pool
    top = take(recipe, pool, rel, max(k - NEWEST_SLOTS, len(recipe)))
    rest = [r for r in recipe + pool if r not in top]
    newest = sorted(rest, key=_number, reverse=True)[:k - len(top)]
    return top + sorted(newest, key=_number)


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
          goal=None, ask=None, correctable=(), retry_followed=None):
    """Apply Builder operations under the case limits; returns the applied operations (for batching).
    `visible`: ids the Builder was shown (it may only change those); default all. `goal`: the game's
    task, stored on written rules (and merged ones) as task-keyed retrieval evidence.
    A game that was not won ('failure') writes only hidden, unconfirmed rules and cannot rewrite what
    the agent sees. A hidden guess is no longer confirmed by a Builder upvote, update or merge (amended
    2026-11-20): it is shown only after CONFIRM_WINS won games whose actions followed it (_observe).
    `correctable`: recipe ids this game may rewrite although frozen (rejected_steps). `retry_followed`:
    (rule text) -> whether the winning retry's actions followed it; a corrected failure turns an Unresolved
    Error into a Corrected Error (shown to the agent) only when it did."""
    applied, writes = [], 0
    visible = {r['id'] for r in rules} if visible is None else set(visible)
    by_id = {r['id']: r for r in rules}
    allowed = CASE_TYPES[case]
    won = case != 'failure'
    source = {'task': goal, 'task_type': task_type} if goal else None
    correctable = set(correctable)

    def confirm(rule):
        """{'verified': True} when a retry win's actions followed a note it turned into a Corrected Error."""
        if won and not rule.get('verified', True) and rule['type'] == 'Corrected Error':
            rule['verified'] = True
            log.append(f"{rule['id']} confirmed by the winning retry that followed it (now shown to the agent)")
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
                    [r for r in rules if not won or r.get('verified', True)], op['type'], scope, text,
                    similarity, task_type)   # a won game's rule is never merged into a hidden guess
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
                    vote(rules, by_id, rule['id'], delta)     # ranks only; never removes (2026-11-20 review)
                    applied.append({'op': kind, 'id': rule['id'], **confirmed})
                    continue
                changes = {k: str(op[k])[:600] for k in ('rule', 'example', 'validation') if isinstance(op.get(k), str)}
                if not changes:
                    raise ValueError('update needs rule, example or validation')
                # Only a success/failure pair of the same task turns a note into a rule the agent sees;
                # any other type in an update is ignored (types never change otherwise).
                if (op.get('type') == 'Corrected Error' and rule['type'] == 'Unresolved Error'
                        and case == 'corrected failure' and 'rule' in changes):
                    changes['type'] = 'Corrected Error'     # kept only if the retry followed it (below)
                elif op.get('type') not in (None, rule['type']):
                    log.append(f"{rule['id']} keeps its type {rule['type']} (only a retry success turns a note "
                               'into a Corrected Error)')
                if not won and shown_to_agent(rule) and ({'rule', 'example'} & set(changes)):
                    # A lost game's rewrite would be an unverified guess shown to the agent: keep the text.
                    changes = {k: v for k, v in changes.items() if k not in ('rule', 'example')}
                    log.append(f"{rule['id']} keeps its text (a lost game may not rewrite a rule the agent sees)")
                    if not changes:
                        continue
                frozen = text_frozen(rule, case, rule['id'] in correctable)
                if frozen and ({'rule', 'example'} & set(changes)):
                    # Rule stability: single games rewrote verified rules back and forth (drift).
                    changes = {k: v for k, v in changes.items() if k not in ('rule', 'example', 'type')}
                    log.append(f"{rule['id']} keeps its text ({frozen})")
                    if not changes:
                        continue
                if changes.get('type') == 'Corrected Error' and rule['type'] == 'Unresolved Error' and not (
                        retry_followed is not None and retry_followed(tidy(strip_instances(changes['rule'])))):
                    del changes['type']    # the note may be reworded but stays hidden
                    log.append(f"{rule['id']} keeps its type Unresolved Error (the winning retry did not follow it)")
                old_text = rule['rule']
                if 'rule' in changes:
                    changes['rule'] = checked(changes.get('type', rule['type']), changes['rule'], ask,
                                              rule.get('task_type'))
                    if changes['rule'] == old_text:
                        del changes['rule']
                    elif shown_to_agent(rule):
                        log.append(f"{rule['id']} rewritten although verified ("
                                   + ('a young rule: credited in {} of {} games'.format(credited(rule), YOUNG_CREDITS)
                                      if credited(rule) < YOUNG_CREDITS else
                                      'a step it instructs was rejected in this game, which followed it')
                                   + '; fresh counters)')
                if 'example' in changes:
                    changes['example'] = ' '.join(changes['example'].split())[:MAX_EXAMPLE]
                if 'validation' in changes:   # keep the last few notes, as AutoManual does
                    changes['validation'] = ' | '.join(([rule['validation']] if rule['validation'] else [])
                                                       + [changes['validation']]).split(' | ')[-3:]
                    changes['validation'] = ' | '.join(changes['validation'])
                if not changes:
                    continue
                was_visible = shown_to_agent(rule)
                rule.update(changes)
                if 'rule' in changes:
                    # The old text's credit does not carry over to the new text (2026-11-20 design review).
                    fresh_counters(rule)
                    changes.update({'fresh': True, 'old_rule': old_text})
                    if was_visible:
                        count_rewrite(rule)
                        changes['rewrite'] = True
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


DEDUPE_EXEMPT = ('Success Process', avoid.TYPE, avoid.POOL)   # one recipe per kind; Anti-Patterns by signature


def batch_dedupe(rules, base_ids, similarity):
    """E only, after a batch is replayed (2026-11-20 review, decision 9): games of a batch never saw each
    other's new rules, so the similarity merge of write_rule is run again. Each rule written in the batch (id
    not in `base_ids`), oldest first, is merged into an older near-duplicate (near_duplicate: same type, same
    kind of task or a general one; a verified rule never into a hidden guess). The older rule keeps its text
    and counts, gains the sources and +1 importance. Mutates `rules`; returns the ops (replayed by _dedupe)."""
    ops = []
    for new in sorted([r for r in rules if r['id'] not in set(base_ids) and r['type'] not in DEDUPE_EXEMPT],
                      key=_number):
        if new not in rules:
            continue
        older = [r for r in rules if _number(r) < _number(new)
                 and (not new.get('verified', True) or r.get('verified', True))]
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
    vote(rules, by_id, twin['id'], 1)
    rules.remove(gone)


def observe(rules, shown_ids, won, context, position, violated=(), followed=None, trace=None, guesses=(),
            changed=()):
    """MACLA Beta update and contrastive contexts for the rules the agent followed in a game; returns the op.
    Both E and E-minus (2026-11-20 design review: E-minus gets the same bookkeeping, used for retrieval and
    visibility only).
    `violated`: shown Anti-Pattern rules whose pattern the agent did anyway.
    `followed`: ids the outcome-blind judge says the actions followed (None: credit every shown rule). Shown
    rules not followed, Success Process recipes included (2026-11-20 review), only get `unused` += 1.
    `trace`: the game's steps; for each rule the judge says was followed, whether the commands it instructs
    were accepted or rejected (command_evidence) is recorded in the op as 'commands'.
    `guesses`: hidden guesses (not shown) the judge says the actions followed, in a won or lost game; a guess
    is shown once CONFIRM_WINS followed games were won and its followed-win rate is at least the base rate
    (promoted).
    `changed`: rules whose text this game's Builder changed: they started fresh counters and get no credit
    for a game played with their old text."""
    changed = set(changed)
    shown_ids = [i for i in shown_ids if i not in changed]
    guesses = [i for i in guesses if i not in set(shown_ids) and i not in changed]
    unused = []
    if followed is not None:
        unused = [i for i in shown_ids if i not in set(followed)]
    commands = {}
    if followed is not None and trace is not None:
        by_id = {r['id']: r for r in rules}
        for rule_id in shown_ids:
            rule = by_id.get(rule_id)
            if rule_id in set(followed) and rule is not None and rule['type'] not in (avoid.TYPE, avoid.POOL):
                found = command_evidence(rule['rule'], trace)
                if found:
                    commands[rule_id] = found
    op = {'op': 'outcome', 'ids': [i for i in shown_ids if i not in unused], 'won': bool(won), 'context': context,
          'position': position, **({'violated': list(violated)} if violated else {}),
          **({'unused': unused} if unused else {}), **({'commands': commands} if commands else {}),
          **({'guessed': list(guesses)} if guesses else {})}
    _observe(rules, op)
    return op


def _count(rule, key, task_type, won):
    """Add one game to rule[key][task_type] = [won, lost]."""
    counts = rule.setdefault(key, {}).setdefault(str(task_type), [0, 0])     # JSON keys are strings
    counts[0 if won else 1] += 1


def promoted(rule):
    """A hidden guess that may be shown: followed in >= CONFIRM_WINS won games and its followed-win rate at
    least the base rate (wins >= the expected wins of its followed games; 2026-11-20 design review)."""
    counts = credit_counts(rule, 'guess_credits')
    wins = sum(won for won, _ in counts.values())
    return rule.get('confirmations', 0) >= CONFIRM_WINS and wins >= expected_wins(rule, counts)


def _observe(rules, op):
    by_id = {r['id']: r for r in rules}
    kind = op['context'].get('task_type')
    won_game = bool(op['won'])
    for rule in rules:   # base rate of this kind of task for every rule that could have been shown
        if rule.get('task_type') in (kind, 'all', None):
            won, games = rule.get('base', [0, 0])
            rule['base'] = [won + won_game, games + 1]
            base = rule.setdefault('base_types', {}).setdefault(str(kind), [0, 0])
            base[0] += won_game
            base[1] += 1
    for rule_id in op.get('unused', ()):   # shown, not followed: no Beta update
        if rule_id in by_id:
            by_id[rule_id]['unused'] = by_id[rule_id].get('unused', 0) + 1
            by_id[rule_id]['last_used'] = op['position']
    for rule_id in op['ids']:
        rule = by_id.get(rule_id)
        if rule is None:
            continue
        key = 'alpha' if op['won'] else 'beta'
        rule[key] = rule.get(key, 1) + 1
        _count(rule, 'credits', kind, won_game)
        contexts = rule.get('contexts', []) + [{**op['context'], 'won': op['won']}]
        won = [c for c in contexts if c['won']][-K_CONTEXTS:]        # keep the newest K of each kind
        lost = [c for c in contexts if not c['won']][-K_CONTEXTS:]
        rule['contexts'] = won + lost
        rule['last_used'] = op['position']
        if rule_id in op.get('violated', ()):
            rule['violations'] = rule.get('violations', 0) + 1
    for rule_id, found in op.get('commands', {}).items():   # [games rejected, won games accepted]
        if rule_id in by_id:
            counts = by_id[rule_id].setdefault('commands', {})
            for command, outcome in found.items():
                rejected, accepted = counts.get(command, [0, 0])
                counts[command] = [rejected + (outcome == 'rejected'),
                                   accepted + (outcome == 'ok' and bool(op['won']))]
    guessed = list(op.get('guessed', ())) + (list(op.get('confirms', ())) if op['won'] else [])   # 'confirms': older ops
    for rule_id in guessed:   # hidden guesses the judge says were followed
        rule = by_id.get(rule_id)
        if rule is not None and not rule.get('verified', True):
            _count(rule, 'guess_credits', kind, won_game)
            rule['confirmations'] = rule.get('confirmations', 0) + won_game
            if promoted(rule):
                rule['verified'] = True


CONFIRM_WINS = 2            # won games whose actions followed a hidden guess before it is shown


def guess_candidates(rules, task_type):
    """Hidden guesses that would be shown if confirmed, for this kind of task: unverified rules of a shown
    type (not Unresolved Error notes, not the failure pools), of this kind or general."""
    return [r for r in rules if not r.get('verified', True) and r['type'] not in HIDDEN
            and r.get('task_type') in (task_type, 'all')]


def observed(rule):
    """Games won / lost while this rule was shown (from Beta(1, 1); contexts are capped, counts are not)."""
    return [rule.get('alpha', 1) - 1, rule.get('beta', 1) - 1]


def useless(rule):
    """Shown in >= USELESS_MIN games but followed in under USELESS_FOLLOWED of them (recipes and Anti-Patterns exempt)."""
    if rule['type'] in ('Success Process', avoid.TYPE, avoid.POOL):
        return False
    won, lost = observed(rule)
    shown = won + lost + rule.get('unused', 0)
    return shown >= USELESS_MIN and (won + lost) < USELESS_FOLLOWED * shown


def kind_had_wins(rule):
    """Whether the kinds of task the rule was credited in have had won games since it was written."""
    if 'base_types' not in rule:
        return rule.get('base', [0, 0])[0] > 0
    return any(rule['base_types'].get(t, [0, 0])[0] > 0 for t in credit_counts(rule))


def retirable(rule):
    """Shown in >= RETIRE_MIN games and, by its Beta posterior, clearly below the expected (base) win rate of
    the games it was followed in (Laplace-smoothed per kind of task; expected_wins)."""
    won, lost = observed(rule)
    if useless(rule) or rejected_command(rule):
        return True
    if won + lost < RETIRE_MIN or rule['type'] == avoid.POOL:
        return False
    if won == 0 and rule['type'] == avoid.TYPE:
        # An Anti-Pattern belongs to a kind of task that is mostly lost, so "never won" proves nothing:
        # it is retired when the agent did the avoided thing in every game it was shown in (it changed nothing).
        return rule.get('violations', 0) >= won + lost
    if won == 0:
        # Never won while followed: retired only if its kind of task has had wins (2026-11-20 review); a kind
        # that is never won says nothing about the rule.
        return kind_had_wins(rule)
    if not rule.get('base', [0, 0])[1]:
        return False
    return float(beta_distribution(1 + won, 1 + lost).cdf(expected_rate(rule))) >= RETIRE_CONFIDENCE


def sole_recipe(rule, rules):
    """The only visible Success Process of its kind of task: never retired or pruned (2026-11-20 review)."""
    return rule['type'] == 'Success Process' and shown_to_agent(rule) and not any(
        r is not rule and r['type'] == 'Success Process' and r.get('task_type') == rule.get('task_type')
        and shown_to_agent(r) for r in rules)


def retire(rules, report):
    """Remove rules that do clearly worse than their kind of task's base rate; logged. Removal is by this
    statistical retirement only (and capacity pruning), never by Builder votes (2026-11-20 review)."""
    for rule in [r for r in rules if retirable(r) and not sole_recipe(r, rules)]:
        won, lost = observed(rule)
        op = {'op': 'retire', 'id': rule['id'], 'won': won, 'lost': lost, 'base': list(rule['base'])}
        if rule.get('unused'):
            op['unused'] = rule['unused']
        gone_useless, bad = useless(rule), rejected_command(rule)
        if bad:
            op['reason'] = f'instructed command always rejected: {bad}'
        avoid.forget(rules, rule)
        report['operations'].append(op)
        if bad:
            report['errors'].append(f"retired {rule['id']} ({op['reason']})")
            continue
        if gone_useless:
            report['errors'].append(f"retired {rule['id']} (useless: followed in {won + lost} of "
                                    f"{won + lost + op.get('unused', 0)} games shown)")
            continue
        report['errors'].append(f"retired {rule['id']} (won {won} of {won + lost} games shown"
                                f"{', never won' if not won else ''}; base "
                                f"{rule['base'][0]} of {rule['base'][1]})")


def refinable(rule):
    """Enough new won and lost games for contrastive refinement, and (2026-11-20 review) a followed-win rate
    below the base rate of its games (wins < expected_wins): a rule doing as well as its kind is left alone."""
    if rule['type'] in (avoid.TYPE, avoid.POOL):      # worded and checked by code; a rewrite would lose that
        return False
    won, lost = observed(rule)
    done = rule.get('refined_at', [0, 0])
    return (won - done[0] >= MIN_CONTRAST and lost - done[1] >= MIN_CONTRAST
            and won < expected_wins(rule))


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
            if text == rule['rule']:
                raise ValueError('refiner gave the same rule')
            op = {'op': 'refine', 'id': rule['id'], 'rule': text, 'refined_at': [0, 0], 'old_rule': rule['rule'],
                  'fresh': True}
            _refine(rules, op)
            report['operations'].append(op)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['errors'].append(f'refiner: {exc}'[:200])
        return


def _refine(rules, op):
    """A refined rule gets fresh counters (2026-11-20 review; ops without 'fresh' are older and kept theirs)."""
    for rule in rules:
        if rule['id'] == op['id']:
            if op.get('fresh'):
                fresh_counters(rule)
                if shown_to_agent(rule):
                    count_rewrite(rule)
            rule['rule'], rule['refined_at'] = op['rule'], list(op['refined_at'])


def prune(rules, position, log):
    """MACLA eq. 8 above CAPACITY: drop the lowest 0.5 mean + 0.3 use share + 0.2 recency."""
    total = sum(r.get('alpha', 1) + r.get('beta', 1) - 2 for r in rules) or 1
    while sum(r['type'] != avoid.POOL for r in rules) > CAPACITY:
        def utility(r):
            uses = r.get('alpha', 1) + r.get('beta', 1) - 2
            age = position - (r['last_used'] if r.get('last_used') is not None else 0)
            return 0.5 * reliability(r) + 0.3 * uses / total + 0.2 * math.exp(-max(age, 0) / TAU)
        victims = [r for r in rules if r['type'] != avoid.POOL and not sole_recipe(r, rules)]
        if not victims:
            return
        victim = min(victims, key=utility)
        avoid.forget(rules, victim) if victim['type'] == avoid.TYPE else rules.remove(victim)
        log.append(f"pruned {victim['id']} (lowest utility)")


def vote(rules, by_id, rule_id, delta):
    """Change a rule's importance (a ranking signal, never below 0). Since the 2026-11-20 design review a vote
    never removes a rule (rules go only by statistical retirement): returns False."""
    rule = by_id[rule_id]
    rule['importance'] = max(0, rule.get('importance', NEW_IMPORTANCE) + delta)
    return False


JUDGE_GUIDE = ('Which of these rules did the agent\'s actions follow (did what the rule says, whether or not it '
               'helped)? A rule counts only if some action clearly did what it says. You are not told how the game '
               'ended; do not guess. Return {"followed": ["rule ids"]}; an empty list is fine.')
JUDGE_OBSERVATION = 100     # characters of each observation shown to the judge


def judge_payload(agent, rules, candidates=(), trace=None):
    """Outcome-blind input for the `followed` judge: goal, the shown rules plus `candidates` (hidden guesses,
    judged but never shown to the agent; the judge is not told which is which), the valid actions of `trace`
    (default: the first attempt) with short observations; no success flag, no reward, and the final
    observation (which reveals a win) is left out."""
    shown = set(agent.rules_shown) | {r['id'] for r in candidates}
    trace = [t for t in (agent.result['trace'] if trace is None else trace) if t['valid']]
    steps = [{'action': t['action'], 'observation': t['after'][:JUDGE_OBSERVATION]} for t in trace[-40:]]
    if steps:
        steps[-1].pop('observation')
    listed = [r for r in rules if r['id'] in shown] + [r for r in candidates if r not in rules]
    return {'instructions': JUDGE_GUIDE, 'goal': agent.public_task.get('goal', ''),
            'rules': [{'id': r['id'], 'rule': r['rule']} for r in listed],
            'steps': steps, 'response_schema': {'followed': ['rule ids']}}


def judge_followed(agent, rules, errors, candidates=()):
    """(ids of the shown rules whose advice the actions followed, ids of the `candidates` followed), from one
    separate outcome-blind model call. The first is None (credit every shown rule) on failure, logged, or
    when nothing was shown and there are no candidates."""
    if not agent.rules_shown and not candidates:
        return None, []
    try:
        data = agent._ask('builder', judge_payload(agent, rules, candidates))
        if not isinstance(data.get('followed'), list):
            raise ValueError('no followed list')
        said = [i for i in data['followed'] if isinstance(i, str)]
        hidden = {r['id'] for r in candidates}
        return ([i for i in said if i in set(agent.rules_shown)] if agent.rules_shown else None,
                sorted({i for i in said if i in hidden}))
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        errors.append(f'followed judge: {exc}; all shown rules credited'[:200])
        return None, []


def retry_judge(agent, retried, errors):
    """(rule text) -> whether the winning retry's actions followed it (outcome-blind judge on the retry trace;
    False on failure, logged). Used before a corrected failure turns a hidden note into a Corrected Error."""
    def followed(text):
        note = {'id': 'note', 'rule': text}
        try:
            data = agent._ask('builder', judge_payload(agent, [], [note], retried['trace']))
            return isinstance(data.get('followed'), list) and 'note' in data['followed']
        except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
            errors.append(f'retry judge: {exc}'[:200])
            return False
    return followed


CONSOLIDATE_EVERY = 25      # practice games between consolidations of underused rules
CONSOLIDATE_MIN = 3         # underused rules needed to consolidate
CONSOLIDATE_SHARE = 0.4     # underused: credited games below this percentile of the visible pool
FOLD_SIM = 0.6              # minimum similarity of an underused rule to its absorber
MAX_FOLD = 3                # underused rules folded into one absorber
FOLD_WORDS = 25
FOLD_FORM = re.compile(r'^(if|when)\b', re.IGNORECASE)
FOLD_SYSTEM = ('You edit the rule manual of a household text-game agent (ALFWorld: go to, take, move X to Y, open, '
               'close, clean/heat/cool X with Y, use desklamp). Return only one JSON object.')


def credited(rule):
    """Games the rule was credited in (alpha + beta - 2)."""
    return rule.get('alpha', 1) + rule.get('beta', 1) - 2


def _visible(rule):
    return shown_to_agent(rule) and rule['type'] != avoid.POOL


def percentile(values, share):
    """Linear-interpolated percentile (numpy's default)."""
    v = sorted(values)
    if not v:
        return 0.0
    pos = share * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def base_rates(rules):
    """Pooled win rate of the visible rules per task type (wins / credited games), None if none credited."""
    won, games = {}, {}
    for r in rules:
        if _visible(r):
            t = r.get('task_type')
            won[t] = won.get(t, 0) + r.get('alpha', 1) - 1
            games[t] = games.get(t, 0) + credited(r)
    return {t: (won[t] / games[t] if games[t] else None) for t in games}


def underused(rules):
    """(underused ids, well-used ids, info). Pool: visible rules that are not recipes or Anti-Patterns.
    Underused: credited games below the pool's 40th percentile and either no losses or a Beta mean at or
    above the base rate of its task type. Well-used: not underused and credited games >= the pool median."""
    pool = [r for r in rules if _visible(r) and r['type'] not in ('Success Process', avoid.TYPE)]
    counts = [credited(r) for r in pool]
    cut, median = percentile(counts, CONSOLIDATE_SHARE), percentile(counts, 0.5)
    rates = base_rates(rules)
    under, well = [], []
    for r in pool:
        a, b = r.get('alpha', 1), r.get('beta', 1)
        rate = rates.get(r.get('task_type'))
        decent = b == 1 or (rate is not None and a / (a + b) >= rate)
        if credited(r) < cut and decent:
            under.append(r['id'])
        elif credited(r) >= median and credited(r) >= cut:
            well.append(r['id'])
    return under, well, {'pool': len(pool), 'credited_p40': cut, 'credited_median': median, 'base_rates': rates}


def fold_problems(kind, text, task_type):
    """Live checks on a model-written rule; [] when it passes."""
    out = []
    if not FOLD_FORM.match(text):
        out.append('not in If/When form')
    if len(text.split()) > FOLD_WORDS:
        out.append(f'too long ({len(text.split())} words)')
    try:
        checked(kind, text)
    except ValueError as e:
        out.append(str(e))
    bad = specific_terms(text)
    if bad:
        out.append('names specific objects or rooms: ' + ', '.join(bad))
    foreign = foreign_actions(task_type, text)
    if foreign:
        out.append('has steps of another kind of task: ' + ', '.join(foreign))
    out += [p for p in rule_problems(kind, text) if p not in out]
    return out


def ask_folded(ask, user, kind, task_type):
    """`ask(user_text, attempt)` returns the model's JSON. (text, []) or (None, problems) after at most two tries."""
    note = ''
    for attempt in range(2):
        reply = ask(user + note, attempt)
        text = tidy(reply.get('rule') or '') if isinstance(reply.get('rule'), str) else ''
        if reply.get('covers_all') is False or not text:
            return None, ['model could not cover all rules in one rule']
        found = fold_problems(kind, text, task_type)
        if not found:
            return text, []
        note = '\n\nYour previous answer was rejected: ' + '; '.join(found) + '. Fix this and answer again.'
    return None, found


def fold_prompt(task, kind, absorber, extras):
    listed = '\n'.join(f'{i + 1}. {r["rule"]}' for i, r in enumerate(extras))
    return (f'A well-used rule of the manual (type "{kind}", task type {task}):\n{absorber["rule"]}\n\n'
            f'Narrower rules that are rarely shown:\n{listed}\n\n'
            'Rewrite the well-used rule so it ALSO covers the narrower rule(s), keeping everything the original '
            'says that is correct. ' + RULE_FORM + ' Use "If/When <condition>, <action>." and at most '
            f'{FOLD_WORDS} words. If it cannot cover them without losing meaning or becoming vague, set '
            '"covers_all" to false.\nReturn JSON {"rule": "<the rewritten rule>", "covers_all": true|false}.')


COUNT_KEYS = ('alpha', 'beta', 'contexts', 'credits', 'unused', 'base', 'base_types', 'commands', 'refined_at',
              'confirmations', 'guess_credits', 'violations')


def merged_record(keeper, others, text):
    """The absorbing rule `keeper` rewritten to `text`. It keeps the counts of the strongest rule of the group
    (most credited games; 2026-11-20 review: summing double-counted games where several were shown), not a
    sum; sources (retrieval evidence) are united."""
    group = [keeper, *others]
    strongest = max(group, key=lambda r: (credited(r), r.get('alpha', 1)))
    new = copy.deepcopy(keeper)
    new['rule'] = text
    for key in COUNT_KEYS:
        if key in strongest:
            new[key] = copy.deepcopy(strongest[key])
        else:
            new.pop(key, None)
    sources = []
    for r in group:
        for s in r.get('sources', []):
            if s not in sources:
                sources.append(copy.deepcopy(s))
    new['sources'] = sources[-MAX_SOURCES:]
    new['importance'] = max(r.get('importance', 0) for r in group)
    last = [r['last_used'] for r in group if r.get('last_used') is not None]
    new['last_used'] = max(last) if last else keeper.get('last_used')
    return new


def fold_plans(rules, similarity):
    """[(absorber, [underused rules to fold in])]: each underused rule goes to the most similar well-used rule
    of the same task type and rule type (similarity >= FOLD_SIM); at most MAX_FOLD per absorber. An absorbed
    rule needs at least one won credited game (2026-11-20 review: no folding of unevidenced rules)."""
    under, well, _ = underused(rules)
    by_id = {r['id']: r for r in rules}
    assigned = {}
    for uid in under:
        u = by_id[uid]
        if observed(u)[0] < 1:
            continue
        cands = [by_id[w] for w in well if by_id[w].get('task_type') == u.get('task_type')
                 and by_id[w]['type'] == u['type']]
        if not cands:
            continue
        sims = [float(s) for s in similarity(u['rule'], [c['rule'] for c in cands])]
        k = max(range(len(cands)), key=lambda i: sims[i])
        if sims[k] >= FOLD_SIM:
            assigned.setdefault(cands[k]['id'], []).append((sims[k], u))
    return [(by_id[aid], [u for _, u in sorted(v, key=lambda x: -x[0])[:MAX_FOLD]]) for aid, v in assigned.items()]


def conflicting(ask, absorber, extras):
    """Contradiction guard: True when the model says the rules give conflicting advice."""
    data = ask('builder', {'instructions': 'Do any of these rules of the same kind of task give conflicting or '
                           'contradictory advice (one says to do what another says not to, or they require '
                           'incompatible steps)? Answer yes or no.',
                           'rules': [absorber['rule']] + [r['rule'] for r in extras],
                           'response_schema': {'conflict': 'yes|no'}})
    answer = data.get('conflict')
    return answer is True or str(answer).strip().lower() in ('yes', 'true')


def _consolidate(rules, op):
    """Fold the rules `op['absorbed']` into `op['id']` (text `op['rule']`); missing rules are skipped."""
    by_id = {r['id']: r for r in rules}
    if op['id'] not in by_id:
        return
    extras = [by_id[i] for i in op['absorbed'] if i in by_id and i != op['id']]
    merged = merged_record(by_id[op['id']], extras, op['rule'])
    if shown_to_agent(merged) and merged['rule'] != by_id[op['id']]['rule']:
        count_rewrite(merged)          # a fold rewrites the absorber's text (the absorber keeps its own count)
    rules[rules.index(by_id[op['id']])] = merged
    for r in extras:
        rules.remove(r)


def consolidate(agent, rules, report):
    """Periodic step: fold underused rules into similar well-used ones (see underused). One contradiction check
    and at most two rewrite tries per absorber; on any failure the originals stay. Logged as 'consolidate' ops."""
    if len(underused(rules)[0]) < CONSOLIDATE_MIN:
        return
    for absorber, extras in fold_plans(rules, agent.embedder.similarity):
        try:
            if conflicting(agent._ask, absorber, extras):
                report['errors'].append(f"consolidate: {absorber['id']} skipped (conflicting rules)")
                continue
            text, why = None, []
            while extras:                      # on failure retry with the least similar one dropped
                text, why = ask_folded(
                    lambda user, attempt: agent._ask('builder', {
                        'instructions': FOLD_SYSTEM + '\n' + user,
                        'response_schema': {'rule': 'string', 'covers_all': 'true|false'}}),
                    fold_prompt(absorber.get('task_type'), absorber['type'], absorber, extras),
                    absorber['type'], absorber.get('task_type'))
                if text is not None:
                    break
                extras = extras[:-1]
            if text is None:
                report['errors'].append(f"consolidate: {absorber['id']} kept ({'; '.join(why)})"[:200])
                continue
            op = {'op': 'consolidate', 'id': absorber['id'], 'absorbed': [r['id'] for r in extras], 'rule': text,
                  'old_rule': absorber['rule'], 'absorbed_rules': [r['rule'] for r in extras]}
            _consolidate(rules, op)
            report['operations'].append(op)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            report['errors'].append(f'consolidate: {exc}'[:200])


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
    goal = agent.public_task.get('goal', '')
    # The same view for E and E-minus (2026-11-20 review): relevance to this game plus the newest rules.
    shown = for_builder(rules, agent.task.get('task_type'), BUILDER_SEES, goal, agent.embedder.similarity)
    guide = builder_guide(report['case'], append_only, agent.task.get('task_type'), shown)
    if 'failed_retries' in extra:
        guide += RETRY_NOTE
    correctable, retry_followed = [], None
    # The outcome-blind judge runs on the rules as the agent saw them, before the Builder changes them
    # (amended 2026-11-20), for E and E-minus alike (design review: E-minus gets the same bookkeeping): its
    # verdict credits rules and hidden guesses and, in E, decides which frozen rules this game may correct.
    guesses = guess_candidates(rules, agent.task.get('task_type'))
    followed, guessed = judge_followed(agent, rules, report['errors'], guesses)
    report['followed'] = followed
    if guessed:
        report['guesses_followed'] = guessed
    if not append_only:
        correctable = rejected_steps(rules, followed, agent.result['trace'])
        if report['case'] == 'corrected failure':
            retry_followed = retry_judge(agent, retried, report['errors'])
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
                                                'validation': 'string'}],
                                }})
        report['diagnosis'] = data.get('diagnosis')
        report['operations'] += apply(rules, data.get('operations'), report['case'], append_only, next_id,
                                      report['errors'], agent.task.get('task_type'), [r['id'] for r in shown],
                                      agent.embedder.similarity, agent.public_task.get('goal', ''), agent._ask,
                                      correctable, retry_followed)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        report['errors'].append(f'builder: {exc}'[:200])
    # Every game, E and E-minus: Beta updates of the followed rules, base rates, guess promotion (E-minus uses
    # them for retrieval and visibility only; it never edits, deletes, merges, folds or retires).
    hidden = {r['id'] for r in rules if not r.get('verified', True)}
    text_changed = [op['id'] for op in report['operations'] if op.get('op') == 'update_rule' and op.get('fresh')]
    report['operations'].append(observe(rules, agent.rules_shown, agent.result['success'],
                                        {'task': goal,
                                         'task_type': agent.task.get('task_type'),
                                         'steps': [t['action'] for t in agent.result['trace'] if t['valid']][-12:],
                                         **({'plan': agent.plan_text} if agent.plan_text else {})},
                                        position,
                                        avoid.violated(rules, agent.rules_shown, avoid.compact(agent.result['trace'])),
                                        followed, agent.result['trace'], guessed, text_changed))
    for rule in rules:
        if rule['id'] in hidden and rule.get('verified', True):
            report['errors'].append(f"{rule['id']} confirmed by {rule.get('confirmations', 0)} won games that "
                                    'followed it, at least its base rate (now shown to the agent)')
    if not append_only:
        retire(rules, report)
    report['operations'] += avoid_update(agent, rules, report, summary, append_only, next_id)
    if not append_only:
        refine(agent, rules, [r for r in rules if r['id'] in set(agent.rules_shown)], report)
        before = {r['id'] for r in rules}
        prune(rules, position, report['errors'])
        for gone in before - {r['id'] for r in rules}:
            report['operations'].append({'op': 'prune', 'id': gone})
        if (position + 1) % CONSOLIDATE_EVERY == 0:
            consolidate(agent, rules, report)
    return report


TEXT_KEYS = ('rule', 'example', 'type')     # what a dropped text change of an update_rule loses


def replay(live, operations, log, base=None):
    """Batching: apply one game's applied operations onto the live rules (ids re-issued for writes).
    `base`: the rules at the start of the batch (the copy this game ran on). With it, a rule's text changes
    at most once per batch: an update_rule text, refine or consolidate of a rule whose text (or refinement)
    an earlier game of the batch, or an earlier op of this game, already changed is dropped and logged
    (the first in position order wins). Only E produces these ops; E-minus's replay is unchanged."""
    rules = copy.deepcopy(live)
    by_id = {r['id']: r for r in rules}
    counter = [max([int(r['id'].split('_')[1]) for r in rules] + [0])]
    started = None if base is None else {r['id']: (r['rule'], r.get('refined_at')) for r in base}
    changed = set()

    def taken(rule_id):
        """True when this rule's text already changed in this batch."""
        if started is None:
            return False
        rule = by_id.get(rule_id)
        return rule_id in changed or (rule is not None and rule_id in started
                                      and (rule['rule'], rule.get('refined_at')) != started[rule_id])

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
        if op['op'] in ('refine', 'consolidate') and taken(op['id']):
            log.append(['text change dropped (already changed in this batch)', op['op'], op['id']])
            continue
        if op['op'] == 'refine':
            _refine(rules, op)
            changed.add(op['id'])
            continue
        if op['op'] == 'consolidate':
            _consolidate(rules, op)
            by_id.clear()
            by_id.update({r['id']: r for r in rules})
            changed.add(op['id'])
            continue
        if op['op'] == 'dedupe':
            _dedupe(rules, op)
            by_id.clear()
            by_id.update({r['id']: r for r in rules})
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
            keys = ('rule', 'example', 'validation', 'type', 'verified', 'task_type')
            text = 'rule' in op
            if text and taken(op['id']):
                log.append(['text change dropped (already changed in this batch)', op['op'], op['id']])
                # 'verified' came with the type change (a note turned Corrected Error): dropping one drops both,
                # so a hidden Unresolved Error never ends up marked verified.
                keys = tuple(k for k in keys if k not in TEXT_KEYS + (('verified',) if 'type' in op else ()))
                text = False
            elif text and started is not None:
                changed.add(op['id'])
            target = by_id[op['id']]
            target.update({k: v for k, v in op.items() if k in keys})
            if text and op.get('fresh'):
                fresh_counters(target)      # the new text starts fresh counters, as in apply
            if text and op.get('rewrite'):
                count_rewrite(target)
            vote(rules, by_id, op['id'], 1)
    return rules
