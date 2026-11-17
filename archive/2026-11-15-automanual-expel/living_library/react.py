"""ALFWorld step-by-step (ReAct) prompting, reused from published code (see prompts/SOURCES.md).

The prompt is verl-agent's ALFWORLD_TEMPLATE preceded by ReAct's two demonstrations for the task
type. Memory is added as plain extra context: skills (callable as one action), skill text (E-text)
or successful past trajectories (D). Invalid actions are answered with ALFWorld's own
"Nothing happens."
"""
import json
from pathlib import Path
import re

from .prompts.verl_agent_alfworld_prompt import ALFWORLD_TEMPLATE

HISTORY = 10
NOTHING = 'Nothing happens.'
VERB = {'pick_and_place': 'put', 'pick_clean_then_place': 'clean', 'pick_heat_then_place': 'heat',
        'pick_cool_then_place': 'cool', 'look_at_obj': 'examine', 'pick_two_obj': 'puttwo'}
_DEMOS = None


def demos(task_type):
    """ReAct's two demonstrations for this task type, in this ALFWorld version's command words."""
    global _DEMOS
    verb = next((v for k, v in VERB.items() if str(task_type).startswith(k)), None)
    if verb is None:
        return ''
    if _DEMOS is None:
        _DEMOS = json.loads((Path(__file__).parent / 'prompts' / 'react_alfworld_3prompts.json').read_text())
    text = _DEMOS[f'react_{verb}_1'] + _DEMOS[f'react_{verb}_0']
    text = re.sub(r'> put (.+?) (?:in/on|in|on) (.+)', r'> move \1 to \2', text)
    text = re.sub(r'You put the (.+?) in/on the (.+?)\.', r'You move the \1 to the \2.', text)
    return 'Here are two example solutions of similar tasks (">" marks the agent\'s actions):\n' + text


def history(trace):
    """(observation before, action) pairs; an invalid action's result is 'Nothing happens.'"""
    pairs, before = [], None
    for step in trace:
        pairs.append((step['before'] if before is None else before, step['action']))
        before = step['after'] if step['valid'] else NOTHING
    return pairs


def current_observation(trace, initial):
    if not trace:
        return initial
    return trace[-1]['after'] if trace[-1]['valid'] else NOTHING


def build(goal, task_type, trace, initial_observation, admissible, subgoal=None,
          skills=(), skill_texts=(), examples=(), lessons=(), brief=False):
    parts = []
    if lessons:                   # E-plus: general lessons validated in simulation
        parts.append('Rules learned from earlier practice (follow them):\n' + '\n'.join(f'- {text}' for text in lessons))
    demo = demos(task_type)
    if demo:
        parts.append(demo)
    for example in examples:      # D: successful practice trajectories
        parts.append('Here is a task you solved before:\nYour task is to: ' + example['goal'] + '\n'
                     + ''.join(f'> {a}\n' for a in example['actions']))
    for skill in skill_texts:     # E-text: library skills as reference steps
        parts.append(f"Reference procedure {skill['signature']} ({skill['description']}):\n"
                     + '\n'.join(skill['steps']))
    actions = [c for c in admissible if c != 'help']
    if skills:                    # skill libraries: each skill is one extra action
        parts.append('You can also use these learned skills; each runs several steps as one action:\n'
                     + '\n'.join(f"'{action}': {description}" for action, description in skills))
        actions += [action for action, _ in skills]
    pairs = history(trace)[-HISTORY:]
    offset = max(0, len(trace) - HISTORY)
    task = goal + (f' Your current subgoal is: {subgoal}.' if subgoal else '')
    parts.append(ALFWORLD_TEMPLATE.format(
        task_description=task, step_count=len(trace), history_length=len(pairs),
        action_history=''.join(f'\n[Observation {offset + i + 1}: {o}, Action {offset + i + 1}: {a}]'
                               for i, (o, a) in enumerate(pairs)),
        current_step=len(trace) + 1, current_observation=current_observation(trace, initial_observation),
        admissible_actions=', '.join(f"'{a}'" for a in actions)))
    if brief:                     # for models that otherwise reason until they run out of tokens
        parts.append(BRIEF)
    return '\n'.join(parts)


BRIEF = ('Keep your reasoning inside <think> </think> short: at most three sentences. '
         'Then give your action inside <action> </action> right away.')


# Edge case: the actor sometimes reasons until it hits max_tokens without choosing an action.
# Instead of guessing an action from the truncated text, the agent shows the model its own
# unfinished reasoning and asks once for just the action.
FOLLOWUP = ('Stop reasoning now. Based on what you have worked out so far, reply with only your '
            'chosen admissible action inside <action> </action> tags, with no other text.')
FOLLOWUP_TOKENS = 64


def has_action(text):
    return re.search(r'<action>\s*(.*?)\s*</action>', text or '', re.S) is not None


def parse_action(text):
    match = re.search(r'<action>\s*(.*?)\s*</action>', text or '', re.S)
    if match:
        action = match.group(1)
    else:
        lines = [line for line in (text or '').strip().splitlines() if line.strip()]
        action = lines[-1] if lines else ''
    return action.strip().strip('\'"').strip()
