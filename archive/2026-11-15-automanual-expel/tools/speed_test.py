"""Throughput probe for the running model server (127.0.0.1:8000). Stdlib only.

Sends `--concurrency` simultaneous chat requests shaped like the experiment's actor calls
(~900 prompt tokens, fixed-length outputs) for `--rounds` rounds, and prints aggregate and
per-stream generation speed. Touches no experiment data.

usage: python tools/speed_test.py --concurrency 16 [--rounds 3] [--out-tokens 180] [--label x] [--csv f]
"""
import argparse
import csv
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

URL = 'http://127.0.0.1:8000/v1/chat/completions'
ROOMS = ['cabinet', 'drawer', 'countertop', 'shelf', 'sinkbasin', 'fridge', 'microwave', 'desk',
         'sidetable', 'garbagecan', 'toaster', 'stoveburner', 'bed', 'sofa', 'dresser', 'safe']


def prompt(rng):
    """An ALFWorld-style actor prompt with a unique observation (no shared-prefix shortcut)."""
    objects = ', '.join(f'a {rng.choice(ROOMS)} {rng.randint(1, 12)}' for _ in range(30))
    history = '\n'.join(f'[Observation {i}: You arrive at {rng.choice(ROOMS)} {rng.randint(1, 9)}. '
                        f'On it, you see a {rng.choice(ROOMS)} {rng.randint(1, 4)}.] '
                        f'[Action {i}: "go to {rng.choice(ROOMS)} {rng.randint(1, 9)}"]' for i in range(14))
    return (f'You are an expert agent operating in the ALFRED Embodied Environment. Your task is to: '
            f'put a clean mug in coffeemachine. Prior to this step, you have already taken 14 step(s). '
            f'Below are the most recent observations and the corresponding actions you took:\n{history}\n'
            f'You are now at step 15 and your current observation is: You are in the middle of a room. '
            f'Looking quickly around you, you see {objects}.\nYour admissible actions of the current '
            f'situation are: [{objects}].\nNow it\'s your turn to take an action. You should first reason '
            f'step-by-step about the current situation within <think> </think> tags. Then choose an '
            f'admissible action and present it within <action> </action> tags.')


def call(model, text, out_tokens):
    body = {'model': model, 'messages': [{'role': 'user', 'content': text}], 'temperature': 0.2,
            'max_tokens': out_tokens, 'ignore_eos': True}
    started = time.monotonic()
    with urlopen(Request(URL, json.dumps(body).encode(), {'Content-Type': 'application/json'}),
                 timeout=900) as r:
        usage = json.load(r)['usage']
    return usage['prompt_tokens'], usage['completion_tokens'], time.monotonic() - started


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--concurrency', type=int, required=True)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--out-tokens', type=int, default=180)
    p.add_argument('--model', default='qwen3.6-35b-a3b-ud-q4_k_xl')
    p.add_argument('--label', default='')
    p.add_argument('--csv')
    a = p.parse_args()
    rng = random.Random(0)
    call(a.model, prompt(rng), 8)                      # warm-up
    n = a.concurrency * a.rounds
    prompts = [prompt(rng) for _ in range(n)]
    started = time.monotonic()
    with ThreadPoolExecutor(a.concurrency) as pool:
        results = list(pool.map(lambda t: call(a.model, t, a.out_tokens), prompts))
    wall = time.monotonic() - started
    pin, out = sum(r[0] for r in results), sum(r[1] for r in results)
    per_call = sorted(r[2] for r in results)
    row = {'label': a.label, 'concurrency': a.concurrency, 'requests': n,
           'prompt_tokens_mean': round(pin / n), 'out_tokens_mean': round(out / n),
           'wall_s': round(wall, 1), 'gen_tok_s_total': round(out / wall, 1),
           'tok_s_per_stream': round(out / sum(per_call), 1),
           'call_s_p50': round(per_call[n // 2], 1), 'calls_per_min': round(60 * n / wall, 1)}
    print(json.dumps(row))
    if a.csv:
        new = not os.path.exists(a.csv)
        with open(a.csv, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)


if __name__ == '__main__':
    main()
