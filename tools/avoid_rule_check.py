"""Scores the Anti-Pattern mechanism (living_library/avoid.py) on pooled failure sets with a known answer.

Scenarios (tests/fixtures/avoid_scenarios.json): hand-written pools of never-won attempts, each marked
`create` (an avoid rule SHOULD come out) or `none` (it should not: no common pattern, one instance only,
a pattern that also appears in won games, an invalid command the game accepts elsewhere, too few wins to
call a command unused ...), plus `report` scenarios built from real practice checkpoints (printed, not scored).
Rows of the form [action, accepted] or "!action" (not accepted).

Stages scored:
  deterministic  mining alone: does it offer a candidate exactly when a rule should exist?
  wording        sentences that must be accepted / rejected by the post-checks (a guessed cause, a guessed fix,
                 an appliance the pattern does not contain, a numbered entity ...), no model needed
  end to end     with the real model (--llm, server on 127.0.0.1:8000) in four variants:
                   naive      the model sees the raw pooled trajectories and writes a rule or null; only the
                              form is checked (the baseline: "learn from failures" with no mining)
                   prefilter  mining first, the model words the measured pattern; form checks only
                   checked    + post-checks (negation, no cause/advice, grounded words, pattern words named)
                   final      + one repair round with the reasons (the mechanism as shipped)
                 outcome per scenario: correct, false_positive (rule where none belongs), miss, bad_text
                 (a rule whose text breaks the strict checks or names something outside the pattern).

usage: python tools/avoid_rule_check.py [--llm] [--runs 3] [--variants naive,prefilter,checked,final] [--verbose]
"""
import argparse
import collections
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import avoid  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures' / 'avoid_scenarios.json'
VARIANTS = {   # checks applied to the model's text, rounds of wording (1 = no repair), mining on/off
    'naive': {'checks': ('form', 'negation'), 'rounds': 1, 'mine': False},
    'prefilter': {'checks': ('form', 'negation'), 'rounds': 1, 'mine': True},
    'checked': {'checks': avoid.ALL_CHECKS, 'rounds': 1, 'mine': True},
    'final': {'checks': avoid.ALL_CHECKS, 'rounds': 2, 'mine': True},
}
NAIVE_GUIDE = (
    'You maintain a manual of rules for an agent in a household text game (ALFWorld). The agent lost every '
    'attempt at the tasks below (several games, each with its failed retries; "!" marks a command the game '
    'rejected with "Nothing happens."). Write ONE avoid rule, "When <situation>, do not <X>.", at most 25 words, '
    'general, no numbers, or {"rule": null} if the attempts show no clear repeated mistake. Output {"rule": "..."}.')


def attempt_of(rows):
    return [[r[1:], 0] if isinstance(r, str) and r.startswith('!') else [r, 1] if isinstance(r, str) else list(r)
            for r in rows]


def entry_of(scenario):
    entry = avoid.new_entry(scenario['task_type'])
    for g in scenario['games']:
        avoid.add_game(entry, {'task_id': g['task_id'], 'task': g['task'],
                               'attempts': [attempt_of(a) for a in g['attempts']]})
    for w in scenario['won']:
        avoid.add_won(entry, attempt_of(w))
    return entry


def raw_text(entry):
    lines = []
    for g in entry['games']:
        for k, attempt in enumerate(g['attempts']):
            lines.append(f"[{g['task']} attempt {k + 1}] " + '; '.join(('' if v else '!') + a for a, v in attempt))
    return '\n'.join(lines)


def strict_problems(text, scenario, cand):
    """Full post-checks plus the scenario's own expectations."""
    problems = avoid.judge(text, cand, scenario['task_type'], entry_accepted(scenario)) if cand else []
    stems = {avoid.stem(w) for w in re.findall(r'[a-z]+', text.lower())}
    for word in scenario.get('must_name', []):
        if avoid.stem(word) not in stems:
            problems.append(f'does not name {word!r}')
    for word in scenario.get('must_not_name', []):
        if avoid.stem(word) in stems:
            problems.append(f'names {word!r}')
    return problems


_ACCEPTED = {}


def entry_accepted(scenario):
    if scenario['name'] not in _ACCEPTED:
        _ACCEPTED[scenario['name']] = entry_of(scenario)['accepted']
    return _ACCEPTED[scenario['name']]


def deterministic(scenarios):
    rows, ok = [], 0
    for s in scenarios:
        if s['expect'] == 'report':
            continue
        found = avoid.mine(entry_of(s))
        want = s['expect'] == 'create'
        kind_ok = (not want) or (found and found[0]['kind'] in s['note'].split('|'))
        good = bool(found) == want and kind_ok
        ok += good
        rows.append((s['name'], s['expect'], [f"{c['kind']}:{c['sig'][1:]}" for c in found][:2], good))
    return rows, ok


def wording(scenarios):
    rows, ok, total = [], 0, 0
    for s in scenarios:
        if not (s.get('good_outputs') or s.get('bad_outputs')):
            continue
        found = avoid.mine(entry_of(s))
        if not found:
            continue
        cand, accepted = found[0], entry_of(s)['accepted']
        for text, want in [(t, True) for t in s['good_outputs']] + [(t, False) for t in s['bad_outputs']]:
            problems = strict_problems(text, {**s, 'must_name': [], 'must_not_name': []}, cand)
            good = (not problems) == want
            total += 1
            ok += good
            rows.append((s['name'], want, good, text, problems))
    return rows, ok, total


def make_asker(seed, tag):
    from living_library.config import Settings
    from living_library.models import HTTPModel
    cfg = Settings.load(str(Path(__file__).resolve().parent.parent / 'configs' / 'pilot.json'))
    model = HTTPModel(cfg, Path(tempfile.gettempdir()) / 'avoid-check-cache.sqlite')

    def ask(role, payload):
        response = model.complete(role, {'task': {}, **payload}, seed, {'avoid_check': tag})
        if '_response_error' in response.data:
            raise ValueError(response.data['_response_error'])
        return response.data
    return ask


def run_variant(ask, name, scenario, entry, found):
    """(rule text or None, notes) for one scenario under one variant."""
    cfg = VARIANTS[name]
    if not cfg['mine']:
        data = ask('avoider', {'instructions': NAIVE_GUIDE, 'kind_of_task': avoid.kind_info(entry),
                               'lost_attempts': raw_text(entry), 'response_schema': {'rule': 'string or null'}})
        text = data.get('rule')
        if not isinstance(text, str) or not text.strip():
            return None, ['declined']
        from living_library import manual
        text = manual.tidy(text)
        problems = avoid.judge(text, found[0] if found else {'sig': ['invalid', '']}, scenario['task_type'],
                               entry['accepted'], cfg['checks'])
        return (None, ['rejected: ' + '; '.join(problems)]) if problems else (text, [])
    all_notes = []
    for cand in found[:avoid.MAX_ASKS]:
        text, notes = write_rounds(ask, entry, cand, cfg)
        if text:
            return text, notes
        all_notes += notes
    return None, all_notes or ['no candidate']


def write_rounds(ask, entry, cand, cfg):
    from living_library import manual
    payload = {'instructions': avoid.AVOID_GUIDE, 'kind_of_task': avoid.kind_info(entry),
               'evidence': avoid.describe(cand), 'response_schema': {'rule': 'string, or null'}}
    rejected, notes = [], []
    for _ in range(cfg['rounds']):
        data = ask('avoider', {**payload, **({'rejected': rejected, 'instructions': avoid.AVOID_GUIDE + avoid.REPAIR_NOTE}
                                             if rejected else {})})
        text = data.get('rule')
        if not isinstance(text, str) or not text.strip():
            return None, notes + ['declined']
        text = manual.tidy(text)
        problems = avoid.judge(text, cand, entry['task_type'], entry['accepted'], cfg['checks'])
        if not problems:
            return text, notes
        notes.append(f'rejected {text[:60]!r}: {"; ".join(problems)}')
        rejected = [{'rule': text, 'problems': problems}]
    return None, notes


def end_to_end(scenarios, variants, runs, verbose, show=False):
    summary = {v: collections.Counter() for v in variants}
    for variant in variants:
        for run in range(runs):
            ask = make_asker(11 + run, f'{variant}-{run}')
            for s in scenarios:
                entry = entry_of(s)
                found = avoid.mine(entry)
                text, notes = run_variant(ask, variant, s, entry, found)
                if s['expect'] == 'report':
                    if run == 0:
                        print(f"  [{variant}] {s['name']}: candidates={[c['sig'][1:] + [c['games'], c['attempts']] for c in found][:3]} "
                              f"rule={text!r} {notes[:1]}")
                    continue
                want = s['expect'] == 'create'
                if text is None:
                    outcome = 'miss' if want else 'correct'
                elif not want:
                    outcome = 'false_positive'
                else:
                    cand = found[0] if found else None
                    outcome = 'bad_text' if strict_problems(text, s, cand) else 'correct'
                summary[variant][outcome] += 1
                if (verbose and outcome != 'correct') or (show and run == 0 and want):
                    if outcome == 'correct':
                        print(f"  [{variant}] {s['name']}: {text!r}")
                    else:
                        print(f"  [{variant} run {run}] {s['name']}: {outcome}: {text!r} {notes[:2]}")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--llm', action='store_true')
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--variants', default=','.join(VARIANTS))
    p.add_argument('--verbose', action='store_true')
    p.add_argument('--show', action='store_true', help='print the rules written for scenarios that should have one')
    a = p.parse_args()
    scenarios = json.loads(FIXTURES.read_text())
    scored = [s for s in scenarios if s['expect'] != 'report']
    rows, ok = deterministic(scenarios)
    print(f'DETERMINISTIC mining: {ok}/{len(rows)} scenarios right ({sum(s["expect"] == "create" for s in scored)} '
          f'should create, {sum(s["expect"] == "none" for s in scored)} should not)')
    for name, expect, found, good in rows:
        if not good or a.verbose:
            print(f"  {'ok ' if good else 'BAD'} {name}: expect {expect}, found {found}")
    w_rows, w_ok, w_total = wording(scenarios)
    print(f'WORDING post-checks: {w_ok}/{w_total} sentences judged right (good accepted, bad rejected)')
    for name, want, good, text, problems in w_rows:
        if not good or a.verbose:
            print(f"  {'ok ' if good else 'BAD'} {name} want={'accept' if want else 'reject'}: {text!r} {problems}")
    for s in scenarios:
        if s['expect'] == 'report':
            found = avoid.mine(entry_of(s))
            print(f"REAL {s['name']}: {len(s['games'])} lost games, {len(s['won'])} won attempts; candidates "
                  f"{[(c['kind'], c['sig'][1:], c['games'], c['attempts']) for c in found][:4]}")
    if a.llm:
        variants = a.variants.split(',')
        summary = end_to_end(scenarios, variants, a.runs, a.verbose, a.show)
        print(f'\nEND TO END with the model ({a.runs} runs x {len(scored)} scenarios per variant)')
        for v in variants:
            c, total = summary[v], sum(summary[v].values())
            print(f"  {v:10} correct {c['correct']}/{total}  false_positive {c['false_positive']}  "
                  f"miss {c['miss']}  bad_text {c['bad_text']}")


if __name__ == '__main__':
    main()
