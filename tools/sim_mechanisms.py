"""Mechanism simulator for the rule library's management thresholds (LIBRARY-SPEC.md section 7). CPU only, no
model: synthetic rules with known usefulness distributions go through the real manual code (observe, the
bad/refine decision `decisions`, `useless`) with a noisy judge, over 300 practice games.

usage: python tools/sim_mechanisms.py [--runs 2000] [--seed 0] [--eligible 0.1667]

A rule is eligible (shown) in a practice game with probability `eligible` (default 1/6: one kind of task's
share, about 50 of 300 games), followed with probability f. Each judged showing: with probability FAIL the judge
fails (no evidence); else with probability SWAP the verdict is replaced by a random one (followed yes/no at
random, usefulness uniform on -2..2, 0 if not followed); else the true verdict (the class's score if followed).
A run stops at the first management event: 'revised' (refinement chosen), 'retired' (bad at the revision cap),
'useless'. Acceptance (asserted by tests/test_rules_sim.py):
  helpful (scores +1/+2, f 0.8): revised or retired in <= 2% of runs;
  neutral (0 w.p. 0.8, else +-1, f 0.8): revised or retired in <= 5% of runs;
  harmful (-1/-2 w.p. 0.9, else 0, f 0.8): revised or retired within 15 followed games in >= 90% of runs;
  neutral rule with f 0.1: retired as useless in >= 90% of runs; with f 0.6: in <= 1%.
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from living_library import manual  # noqa: E402

GAMES = 300
ELIGIBLE = 1 / 6
SWAP = 0.15
FAIL = 0.1
CLASSES = {
    'helpful': lambda rng: rng.choice((1, 2)),
    'neutral': lambda rng: 0 if rng.random() < 0.8 else rng.choice((-1, 1)),
    'harmful': lambda rng: rng.choice((-1, -2)) if rng.random() < 0.9 else 0,
}
CONTEXT = {'task': 'heat some egg and put it in countertop.', 'task_type': 'pick_heat_then_place_in_recep',
           'steps': ['go to fridge 1', 'open fridge 1']}


def run_rule(kind, follow, rng, games=GAMES, eligible=ELIGIBLE, swap=SWAP, fail=FAIL):
    """One synthetic rule through `games` practice games; the first management event or None."""
    rule = manual.new_rule('rule_1', 'Special Phenomenon', 'When the object is cold, open the fridge.', '',
                           CONTEXT['task_type'])
    followed_games = 0
    for position in range(games):
        if rng.random() >= eligible:
            continue
        followed = rng.random() < follow
        followed_games += followed
        if rng.random() < fail:
            continue                                  # judge failure: no evidence from this game
        if rng.random() < swap:                       # a noisy verdict
            said = rng.random() < 0.5
            score = rng.choice(manual.SCORES) if said else 0
        else:
            said, score = followed, (CLASSES[kind](rng) if followed else 0)
        manual.observe([rule], {rule['id']: {'followed': said, 'usefulness': score, 'reason': '', 'rule': rule['rule']}},
                       CONTEXT, position, True)
        target, doomed = manual.decisions([rule])     # E's per-game management (manage)
        if target is not None or doomed:
            return {'event': 'revised' if target is not None else 'retired', 'followed_games': followed_games,
                    'position': position}
        if manual.useless(rule):                      # batch_upkeep
            return {'event': 'useless', 'followed_games': followed_games, 'position': position}
    return {'event': None, 'followed_games': followed_games, 'position': games}


def rate(events, test):
    return sum(map(test, events)) / len(events)


def simulate(runs=2000, seed=0, eligible=ELIGIBLE):
    """{criterion: (measured share, limit, passed)} for the acceptance criteria."""
    rng = random.Random(seed)
    sample = lambda kind, follow: [run_rule(kind, follow, rng, eligible=eligible) for _ in range(runs)]
    changed = lambda e: e['event'] in ('revised', 'retired')
    out = {}
    share = rate(sample('helpful', 0.8), changed)
    out['helpful revised or retired'] = (share, '<= 0.02', share <= 0.02)
    share = rate(sample('neutral', 0.8), changed)
    out['neutral revised or retired'] = (share, '<= 0.05', share <= 0.05)
    share = rate(sample('harmful', 0.8), lambda e: changed(e) and e['followed_games'] <= 15)
    out['harmful revised or retired within 15 followed games'] = (share, '>= 0.90', share >= 0.90)
    share = rate(sample('neutral', 0.1), lambda e: e['event'] == 'useless')
    out['f=0.1 retired as useless'] = (share, '>= 0.90', share >= 0.90)
    share = rate(sample('neutral', 0.6), lambda e: e['event'] == 'useless')
    out['f=0.6 retired as useless'] = (share, '<= 0.01', share <= 0.01)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=int, default=2000)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--eligible', type=float, default=ELIGIBLE)
    a = p.parse_args()
    print(f'{a.runs} runs per rule, {GAMES} practice games, eligible {a.eligible:.3f}, judge swap {SWAP}, '
          f'failure {FAIL}; PRIOR {manual.PRIOR}, MIN_EVIDENCE {manual.MIN_EVIDENCE}, BAD_MEAN {manual.BAD_MEAN}, '
          f'USELESS_MIN {manual.USELESS_MIN}, USELESS_FOLLOWED {manual.USELESS_FOLLOWED}')
    ok = True
    for name, (share, limit, passed) in simulate(a.runs, a.seed, a.eligible).items():
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  {name}: {share:.3f} (needs {limit})")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
