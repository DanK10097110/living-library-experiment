"""Diagnostic baseline (not experiment data): a flat ALFWorld agent built from published code.

Prompt = verl-agent's ALFWORLD_TEMPLATE (Apache-2.0, langfengQ/verl-agent
agent_system/environments/prompts/alfworld.py) preceded by ReAct's two task-type demonstrations
(MIT, ysymyth/ReAct); both vendored in third_party/ (see SOURCES.md), with ReAct's 'put X in/on Y' rewritten to this
ALFWorld version's 'move X to Y'. Invalid actions return "Nothing happens." as in ALFWorld.

usage: python tools/probe_react.py <served model name> <games per family> [--no-examples]
"""
import json
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'third_party'))
from verl_agent_alfworld_prompt import ALFWORLD_TEMPLATE  # noqa: E402  (vendored strings)

from living_library.environments import ALFWorld  # noqa: E402

MODEL, PER_FAMILY = sys.argv[1], int(sys.argv[2])
EXAMPLES = '--no-examples' not in sys.argv
REACT = json.load(open(ROOT / 'third_party' / 'react_alfworld_3prompts.json'))
VERB = {'pick_and_place': 'put', 'pick_clean_then_place': 'clean', 'pick_heat_then_place': 'heat',
        'pick_cool_then_place': 'cool', 'look_at_obj': 'examine', 'pick_two_obj': 'puttwo'}
HISTORY = 10


def demos(task_type):
    verb = next(v for k, v in VERB.items() if task_type.startswith(k))
    text = REACT[f'react_{verb}_1'] + REACT[f'react_{verb}_0']
    text = re.sub(r'> put (.+?) (?:in/on|in|on) (.+)', r'> move \1 to \2', text)
    text = re.sub(r'You put the (.+?) in/on the (.+?)\.', r'You move the \1 to the \2.', text)
    return 'Here are two example solutions of similar tasks (">" marks the agent\'s actions):\n' + text


def ask(messages):
    body = {'model': MODEL, 'messages': messages, 'temperature': 0.2, 'max_tokens': 512}
    req = Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(body).encode(),
                  {'Content-Type': 'application/json'})
    with urlopen(req, timeout=900) as r:
        raw = json.load(r)
    return raw['choices'][0]['message']['content'], raw['usage']


def play(task):
    env = ALFWorld()
    state = env.reset(task)
    goal = env.goal
    obs = state.observation
    history, tokens = [], [0, 0]
    for step in range(50):
        prompt = ALFWORLD_TEMPLATE.format(
            task_description=goal, step_count=step, history_length=min(HISTORY, len(history)),
            action_history=''.join(f'\n[Observation {i + 1}: {o}, Action {i + 1}: {a}]'
                                   for i, (o, a) in enumerate(history[-HISTORY:])),
            current_step=step + 1, current_observation=obs,
            admissible_actions=', '.join(f"'{c}'" for c in env.state.admissible if c != 'help'))
        messages = [{'role': 'user', 'content': (demos(task['task_type']) + '\n' if EXAMPLES else '') + prompt}]
        text, usage = ask(messages)
        tokens[0] += usage['prompt_tokens']; tokens[1] += usage['completion_tokens']
        m = re.search(r'<action>\s*(.*?)\s*</action>', text, re.S)
        action = (m.group(1) if m else text.strip().splitlines()[-1] if text.strip() else '').strip().strip("'\"")
        history.append((obs, action))
        if action in env.state.admissible:
            obs = env.step(action).observation
        else:
            obs = 'Nothing happens.'
        if env.state.won or env.state.done:
            break
    env.close()
    return task['task_type'], bool(env.state.won), step + 1, tokens


def main():
    tasks_by_family = {}
    for t in json.load(open('/root/ll-runs/manifest.json'))['splits']['development']:
        tasks_by_family.setdefault(t['task_type'], []).append(t)
    tasks = [t for ts in tasks_by_family.values() for t in ts[:PER_FAMILY]]
    start = time.monotonic()
    # TextWorld's parser is not thread-safe: one process per concurrent game.
    with ProcessPoolExecutor(8) as pool:
        results = list(pool.map(play, tasks))
    wall = time.monotonic() - start
    by = {}
    for family, won, steps, tok in results:
        by.setdefault(family, []).append(won)
    for family, wins in sorted(by.items()):
        print(f'  {family:34} {sum(wins)}/{len(wins)}')
    n = len(results)
    print(f"{MODEL} {'2-shot' if EXAMPLES else '0-shot'}: {sum(r[1] for r in results)}/{n} "
          f"({100 * sum(r[1] for r in results) / n:.0f}%), avg steps {sum(r[2] for r in results) / n:.1f}, "
          f"tokens/ep in {sum(r[3][0] for r in results) // n} out {sum(r[3][1] for r in results) // n}, "
          f"{wall:.0f}s wall ({n / wall * 3600:.0f} episodes/h at 8 parallel)")


if __name__ == '__main__':
    main()
