#!/usr/bin/env python3
"""Replay a recorded example step by step (stdlib only), for live demos.

usage:
  python replay.py episodes/e/e-win-look-3-steps.json            # print instantly
  python replay.py episodes/paired/pair-heat-mug-cabinet.json --delay 1.5
  python replay.py episodes/paired/pair-heat-mug-cabinet.json --only C
  python replay.py library/builder/bx-04-three-retries-win-on-third.json --delay 1
  python replay.py library/snapshots/snap-mature-study-E-after-35-games.json
  python replay.py --list                                          # list all examples

Press Enter instead of using --delay with --step. Options: --width N (wrap), --no-obs (hide observations).
"""
import argparse
import glob
import json
import os
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OPTS = None


def out(text='', pause=0.0):
    print(text, flush=True)
    if OPTS.step:
        try:
            input()
        except EOFError:
            pass
    elif pause:
        time.sleep(pause)


def wrap(text, indent='    '):
    if OPTS.width <= 0:
        return indent + text
    return textwrap.fill(text, OPTS.width, initial_indent=indent, subsequent_indent=indent)


def show_rules(ep):
    if 'rules_shown' in ep:
        print('\nRULES SHOWN TO PLANNER AND ACTOR')
        if not ep['rules_shown']:
            print('  (none)')
        for r in ep['rules_shown']:
            print(f"  [{r['type']}] {r['id']} Beta({r['alpha']},{r['beta']})")
            print(wrap(r['rule'], '      '))
    if 'memory_shown' in ep:
        print('\nMEMORY SHOWN TO THE ACTOR (similar solved tasks)')
        for m in ep['memory_shown']:
            print(f"  solved before: {m['goal']}  (similarity {m.get('similarity')})")
            print('     ' + ' > '.join(m['actions'][:12]) + (' ...' if len(m['actions']) > 12 else ''))
    if ep.get('plan'):
        print('\nPLANNER SUBGOALS')
        for i, p in enumerate(ep['plan'], 1):
            print(f'  {i}. {p}')


def play_episode(ep, label=None):
    bar = '=' * 78
    print(bar)
    print(f"{label + ': ' if label else ''}{ep.get('title', ep['id'])}")
    print(f"condition {ep['condition']} | {ep['task_kind']} | game {ep['game_id'].split('/')[-2] if '/' in ep['game_id'] else ep['game_id']}")
    print(bar)
    print(f"GOAL: {ep['goal']}")
    show_rules(ep)
    print('\nSTART')
    out(wrap(ep['initial_observation'].strip().split('\n\n')[-1], '  '), OPTS.delay)
    for s in ep['trace']:
        bad = '' if s['valid'] else '   [INVALID ACTION]'
        out(f"\n{s['step']:>2}. > {s['action']}{bad}", OPTS.delay)
        if not OPTS.no_obs:
            out(wrap(s['observation'], '      '), OPTS.delay * 0.5)
    verdict = 'WON' if ep['success'] else 'LOST'
    print(f"\n>>> {verdict} after {ep['steps']} steps ({ep['invalid_actions']} invalid), {ep['model_calls']} model calls\n")


def play_builder(obj):
    print('=' * 78)
    print(obj['title'])
    print('=' * 78)
    g = obj['practice_game']
    print(f"practice game: {g['goal']}  ({g['task_kind']})")
    print('\nRULES SHOWN IN THE FIRST ATTEMPT')
    for r in obj['rules_shown_in_first_attempt'] or []:
        print(f"  [{r['type']}] {r['id']} Beta({r['alpha']},{r['beta']}): {r['rule']}")
    if not obj['rules_shown_in_first_attempt']:
        print('  (none)')
    print(f"\nFIRST ATTEMPT: {'WON' if g['success'] else 'LOST'} in {g['steps']} steps")
    for s in obj['first_attempt_trace']:
        out(f"  {s['step']:>2}. {'' if s['valid'] else '!'}{s['action']}", OPTS.delay * 0.4)
    for a in obj.get('retries') or []:
        print(f"\nRETRY {a['attempt']} (agent reflected first):")
        print(wrap('reflection: ' + a['reflection'].strip(), '  '))
        for i, x in enumerate(a['actions'], 1):
            out(f"  {i:>2}. {'' if x['valid'] else '!'}{x['action']}", OPTS.delay * 0.4)
        print(f"  -> {'WON' if a['won'] else 'lost'} in {a['steps']} steps")
    b = obj['builder_report']
    print(f"\nBUILDER REPORT: case={b['case']} diagnosis={b['diagnosis']}")
    for o in b['operations']:
        line = f"  {o['op']}"
        if o.get('id'):
            line += f" {o['id']}"
        if o.get('type'):
            line += f" [{o['type']}]"
        out(line, OPTS.delay)
        if o.get('rule'):
            print(wrap(o['rule'], '      '))
    for e in b['log_lines']:
        out(f'  log: {e}', OPTS.delay)
    print('\nMANUAL CHANGES')
    for c in obj['rules_changed']:
        print(f"  {c['id']} {c['change']}")
        if c['before']:
            print(wrap(f"before ({c['before']['type']}, Beta({c['before']['alpha']},{c['before']['beta']}), visible={c['before']['visible_to_agent']}): {c['before']['rule']}", '      '))
        if c['after']:
            print(wrap(f"after  ({c['after']['type']}, Beta({c['after']['alpha']},{c['after']['beta']}), visible={c['after']['visible_to_agent']}): {c['after']['rule']}", '      '))
        out('', OPTS.delay)


def play_snapshot(s):
    print('=' * 78)
    print(s['label'])
    print('=' * 78)
    for r in sorted(s['rules'], key=lambda r: (r['task_type'] or '', r['type'])):
        vis = '' if r['visible_to_agent'] else ' (HIDDEN note)'
        out(f"[{r['type']}] {r['id']} {r['task_type']} Beta({r['alpha']},{r['beta']}) mean {r['mean']}{vis}", OPTS.delay)
        print(wrap(r['rule'], '      '))


def main():
    global OPTS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', nargs='?')
    ap.add_argument('--delay', type=float, default=0.0, help='seconds between steps')
    ap.add_argument('--step', action='store_true', help='wait for Enter after each step')
    ap.add_argument('--only', choices=['C', 'E'], help='paired examples: show only one side')
    ap.add_argument('--width', type=int, default=100)
    ap.add_argument('--no-obs', action='store_true')
    ap.add_argument('--list', action='store_true')
    OPTS = ap.parse_args()
    if OPTS.list or not OPTS.path:
        for p in sorted(glob.glob(os.path.join(HERE, '**', '*.json'), recursive=True)):
            print(os.path.relpath(p, HERE).replace(os.sep, '/'))
        return
    path = OPTS.path if os.path.exists(OPTS.path) else os.path.join(HERE, OPTS.path)
    with open(path, encoding='utf-8') as f:
        obj = json.load(f)
    if 'C' in obj and 'E' in obj:
        print(f"SAME GAME, TWO CONDITIONS: {obj['title']}  ({obj['result']})")
        for side in ('C', 'E'):
            if OPTS.only in (None, side):
                play_episode(obj[side], side)
    elif 'trace' in obj:
        play_episode(obj)
    elif 'builder_report' in obj:
        play_builder(obj)
    elif 'rules' in obj and 'label' in obj:
        play_snapshot(obj)
    else:
        print(json.dumps(obj, indent=1)[:4000])


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        sys.exit(0)
