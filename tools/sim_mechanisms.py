"""Mechanism simulator for the rule library's management thresholds (LIBRARY-SPEC.md section 7). CPU only, no
model: synthetic rules with known behaviour go through the real manual code (observe, the bad/refine decision
`decisions`, `useless`) with noisy evidence, over 300 practice games.

usage: python tools/sim_mechanisms.py [--runs 2000] [--seed 0] [--eligible 0.1667]

A rule is eligible (shown) in a practice game with probability `eligible` (default 1/6: one kind of task's
share, about 50 of 300 games) and followed with probability f. The evidence is noisy like the real one
(manual.assess):
  used: the citation call names a followed rule with probability CITE_HIT and a rule it did not follow with
        probability CITE_FALSE (assumed; to be measured on real games);
  harm: in a used game where the rule really did harm the trace signal fires with probability HARM_HIT, in
        any other used game with probability HARM_FALSE (both measured on 55 gold-labelled archived uses,
        DECISIONS 2026-11-20: 15 of 18 harmful uses flagged, 7 of 37 others);
  score: -1 on a harm signal, else +1 if the game was won, else 0.
A run stops at the first management event: 'revised' (refinement chosen), 'retired' (bad at the revision cap),
'useless'. Acceptance (asserted by tests/test_rules_sim.py):
  helpful (never harmful, games won w.p. 0.7, f 0.8): revised or retired in <= 2% of runs;
  neutral (never harmful, won w.p. 0.5, f 0.8): revised or retired in <= 5% of runs;
  neutral in a hard kind (won w.p. 0.2, f 0.8): revised or retired in <= 10% of runs;
  harmful (harmful in 90% of the games it is used in, won w.p. 0.3, f 0.8): revised or retired within 15
      followed games in >= 90% of runs;
  neutral rule with f 0.1: retired as useless in >= 85% of runs; with f 0.6: in <= 1%. (A rarely used rule
      that lingers only costs a low-ranked slot; retiring a working one loses it: the false-retirement limit
      is the strict one. With citation noise no USELESS_MIN meets 90% and 1% together.)
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from living_library import manual  # noqa: E402

GAMES = 300
ELIGIBLE = 1 / 6
CITE_HIT, CITE_FALSE = 0.8, 0.1
HARM_HIT, HARM_FALSE = 15 / 18, 7 / 37
CLASSES = {                 # (share of used games where it really does harm, win rate when used)
    'helpful': (0.0, 0.7),
    'neutral': (0.0, 0.5),
    'neutral-hard': (0.0, 0.2),
    'harmful': (0.9, 0.3),
}
CONTEXT = {'task': 'heat some egg and put it in countertop.', 'task_type': 'pick_heat_then_place_in_recep',
           'steps': ['go to fridge 1', 'open fridge 1']}


def run_rule(kind, follow, rng, games=GAMES, eligible=ELIGIBLE):
    """One synthetic rule through `games` practice games; the first management event or None."""
    rule = manual.new_rule('rule_1', 'Special Phenomenon', 'When the object is cold, open the fridge.', '',
                           CONTEXT['task_type'])
    harmful, win = CLASSES[kind]
    followed_games = 0
    for position in range(games):
        if rng.random() >= eligible:
            continue
        followed = rng.random() < follow
        followed_games += followed
        used = rng.random() < (CITE_HIT if followed else CITE_FALSE)
        score = 0
        if used:
            did_harm = followed and rng.random() < harmful
            if rng.random() < (HARM_HIT if did_harm else HARM_FALSE):
                score = -1
            else:
                score = int(rng.random() < win)
        manual.observe([rule], {rule['id']: {'followed': used, 'usefulness': score, 'reason': '', 'rule': rule['rule']}},
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
    sample = lambda kind, follow: [run_rule(kind, follow, rng, eligible=eligible) for _ in range(runs)]  # noqa: E731
    changed = lambda e: e['event'] in ('revised', 'retired')  # noqa: E731
    out = {}
    share = rate(sample('helpful', 0.8), changed)
    out['helpful revised or retired'] = (share, '<= 0.02', share <= 0.02)
    share = rate(sample('neutral', 0.8), changed)
    out['neutral revised or retired'] = (share, '<= 0.05', share <= 0.05)
    share = rate(sample('neutral-hard', 0.8), changed)
    out['neutral (hard kind) revised or retired'] = (share, '<= 0.10', share <= 0.10)
    share = rate(sample('harmful', 0.8), lambda e: changed(e) and e['followed_games'] <= 15)
    out['harmful revised or retired within 15 followed games'] = (share, '>= 0.90', share >= 0.90)
    share = rate(sample('neutral', 0.1), lambda e: e['event'] == 'useless')
    out['f=0.1 retired as useless'] = (share, '>= 0.85', share >= 0.85)
    share = rate(sample('neutral', 0.6), lambda e: e['event'] == 'useless')
    out['f=0.6 retired as useless'] = (share, '<= 0.01', share <= 0.01)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runs', type=int, default=2000)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--eligible', type=float, default=ELIGIBLE)
    a = p.parse_args()
    print(f'{a.runs} runs per rule, {GAMES} practice games, eligible {a.eligible:.3f}, citation {CITE_HIT}/'
          f'{CITE_FALSE}, harm signal {HARM_HIT:.2f}/{HARM_FALSE:.2f}; PRIOR {manual.PRIOR}, MIN_EVIDENCE '
          f'{manual.MIN_EVIDENCE}, BAD_MEAN {manual.BAD_MEAN}, USELESS_MIN {manual.USELESS_MIN}, USELESS_FOLLOWED '
          f'{manual.USELESS_FOLLOWED}')
    ok = True
    for name, (share, limit, passed) in simulate(a.runs, a.seed, a.eligible).items():
        ok &= passed
        print(f"  {'PASS' if passed else 'FAIL'}  {name}: {share:.3f} (needs {limit})")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
