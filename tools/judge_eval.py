"""Evaluate the per-rule usefulness judge on archived games (no game replay). Needs the model server for `run`.

  extract RUN LIBRARY OUT      cases (goal, trace, one shown rule) from RUN/records.json; rule texts from an
                               append-only library json (E-minus: ids and texts never change)
  synth CASES OUT              synthetic cases with known answers built from real traces (see SYNTH below)
  run CASES OUT [--guide F]    the judge (manual.judge_payload / parse_verdict) on every case
  score VERDICTS LABELS        agreement with gold labels {case_id, followed, usefulness}

A case: {case_id, task_type, goal, won, rule_id, rule_type, rule, trace: [{action, after, valid}]}.
"""
import argparse
import concurrent.futures
import json
import random
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402


def kind(task_id):
    return task_id.split('/')[1].split('-')[0]


def extract(a):
    records = json.loads((Path(a.run) / 'records.json').read_text())
    library = json.loads(Path(a.library).read_text())
    texts = {r['id']: r for r in library['rules']}
    out = []
    for g in records:
        if g.get('condition') != a.condition:
            continue
        for rule_id in dict.fromkeys(g.get('rules_shown') or ()):
            rule = texts.get(rule_id)
            if rule is None or not manual.shown_to_agent(rule):
                continue
            out.append({'case_id': f"{g['position']}-{rule_id}", 'task_type': kind(g['task_id']), 'goal': g['goal'],
                        'won': bool(g['success']), 'rule_id': rule_id, 'rule_type': rule['type'],
                        'rule': rule['rule'], 'trace': [{k: t[k] for k in ('action', 'after', 'valid')}
                                                        for t in g['trace']]})
    Path(a.out).write_text('\n'.join(json.dumps(c) for c in out) + '\n')
    print(f'{len(out)} cases from {len({c["goal"] for c in out})} games')


# SYNTH: rules whose answer is known from the trace alone.
#   other_kind   a rule written for a different kind of task          -> followed no, usefulness 0
#   echo         a rule that prescribes the game's own accepted key command form (won games)
#                                                                     -> followed yes, usefulness >= 1
#   failed       a rule that prescribes a command form the game shows failing ("Nothing happens") over and
#                over                                                 -> followed yes, usefulness <= -1
KEY = re.compile(r'^(heat|cool|clean|use|slice) ')


def synth(a):
    cases = [json.loads(line) for line in Path(a.cases).read_text().splitlines() if line.strip()]
    games = {c['goal'] + str(c['won']) + c['case_id'].split('-')[0]: c for c in cases}
    by_kind = {}
    for c in cases:
        by_kind.setdefault(c['task_type'], []).append(c)
    rng = random.Random(0)
    out = []
    for gid, c in games.items():
        base = {k: c[k] for k in ('task_type', 'goal', 'won', 'trace')}
        others = [o for k, v in by_kind.items() if k != c['task_type'] for o in v
                  if o['rule_type'] == 'Success Process']
        if others:
            o = rng.choice(others)
            out.append({**base, 'case_id': f'synth-other-{gid[-6:]}-{len(out)}', 'rule_id': 'synth',
                        'rule_type': 'Success Process', 'rule': o['rule'], 'expect': 'not_followed'})
        good = [t['action'] for t in c['trace'] if t['valid'] and KEY.match(t['action'])]
        if c['won'] and good:
            verb, obj, _, place = (good[0].split(' ') + ['', '', '', ''])[:4]
            out.append({**base, 'case_id': f'synth-echo-{len(out)}', 'rule_id': 'synth', 'rule_type': 'Special Phenomenon',
                        'rule': f'When an object must be {verb}ed for this kind of task, hold it and use "{verb} <object> with {re.sub(r" [0-9]+$", "", place)}" directly; the command works only while you hold the object.',
                        'expect': 'helpful'})
        failed = {}
        for t in c['trace']:
            if not t['valid']:
                form = ' '.join(w for w in t['action'].split() if not w.isdigit())
                failed[form] = failed.get(form, 0) + 1
        form, n = max(failed.items(), key=lambda kv: kv[1], default=(None, 0))
        if n >= 3:
            out.append({**base, 'case_id': f'synth-failed-{len(out)}', 'rule_id': 'synth', 'rule_type': 'Special Phenomenon',
                        'rule': f'For this kind of task, use the command "{form}" (with the object and place numbers) at this point; repeat it until it works.',
                        'expect': 'misled'})
    Path(a.out).write_text('\n'.join(json.dumps(c) for c in out) + '\n')
    import collections
    print(len(out), collections.Counter(c['expect'] for c in out))


def payload_agent(case):
    trace = [{**t, 'before': ''} for t in case['trace']]
    return types.SimpleNamespace(result={'trace': trace}, public_task={'goal': case['goal']})


def run(a):
    from living_library.config import Settings
    from living_library.models import HTTPModel
    if a.guide:
        manual.JUDGE_GUIDE = Path(a.guide).read_text().strip()
    cfg = Settings.load(a.config)
    import threading
    local = threading.local()
    cases = [json.loads(line) for line in Path(a.cases).read_text().splitlines() if line.strip()]
    if a.limit:
        cases = cases[:a.limit]

    def one(case):
        rule = {'type': case['rule_type'], 'rule': case['rule'], 'id': case['case_id']}
        payload = manual.judge_payload(payload_agent(case), rule)
        if a.binary:
            payload['response_schema'] = {'evidence': 'step numbers, or none', 'used': 'yes|no'}
        if not hasattr(local, 'model'):
            local.model = HTTPModel(cfg, Path(a.cache))
        try:
            response = local.model.complete('judge', {'task': {'goal': case['goal']}, **payload}, 0, {'case': case['case_id']})
            data = response.data
            if a.binary:
                used = str(data.get('used', '')).strip().lower()
                if used not in ('yes', 'no'):
                    raise ValueError(f'bad used {used!r}')
                data = {'followed': used, 'usefulness': 0, 'reason': data.get('evidence', '')}
            verdict = manual.parse_verdict(data)
        except (ValueError, KeyError, TypeError) as exc:
            verdict = {'error': str(exc)[:200]}
        return {'case_id': case['case_id'], **verdict}

    with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
        verdicts = list(pool.map(one, cases))
    Path(a.out).write_text('\n'.join(json.dumps(v) for v in verdicts) + '\n')
    errors = sum('error' in v for v in verdicts)
    print(f'{len(verdicts)} verdicts, {errors} errors')
    if any('expect' in c for c in cases):
        score_synth(cases, verdicts)


def score_synth(cases, verdicts):
    by = {v['case_id']: v for v in verdicts}
    ok = {'not_followed': lambda v: not v['followed'],
          'helpful': lambda v: v['followed'] and v['usefulness'] >= 1,
          'misled': lambda v: v['followed'] and v['usefulness'] <= -1}
    for expect, test in ok.items():
        group = [by[c['case_id']] for c in cases if c.get('expect') == expect]
        good = sum('error' not in v and test(v) for v in group)
        print(f'synthetic {expect:13} {good}/{len(group)} correct')


def score(a):
    verdicts = {v['case_id']: v for v in map(json.loads, Path(a.verdicts).read_text().splitlines()) if v}
    labels = [json.loads(line) for line in Path(a.labels).read_text().splitlines() if line.strip()]
    pairs = [(lab, verdicts[lab['case_id']]) for lab in labels
             if lab['case_id'] in verdicts and 'error' not in verdicts[lab['case_id']]]
    n = len(pairs)
    yes = lambda x: x in (True, 'yes', 'partly')  # noqa: E731
    followed = sum(yes(lab['followed']) == v['followed'] for lab, v in pairs)
    sign = sum((lab['usefulness'] > 0) - (lab['usefulness'] < 0) == (v['usefulness'] > 0) - (v['usefulness'] < 0)
               for lab, v in pairs)
    mae = sum(abs(lab['usefulness'] - v['usefulness']) for lab, v in pairs) / max(n, 1)
    over = sum(v['usefulness'] > lab['usefulness'] for lab, v in pairs)
    under = sum(v['usefulness'] < lab['usefulness'] for lab, v in pairs)
    neg_gold = [(lab, v) for lab, v in pairs if lab['usefulness'] < 0]
    pos_gold = [(lab, v) for lab, v in pairs if lab['usefulness'] > 0]
    print(f'{n} labelled cases: followed agreement {followed / n:.2f}, usefulness sign agreement {sign / n:.2f}, '
          f'MAE {mae:.2f}, judge higher {over}, lower {under}')
    print(f'gold negative: {len(neg_gold)}, judge negative on {sum(v["usefulness"] < 0 for _, v in neg_gold)}; '
          f'gold positive: {len(pos_gold)}, judge positive on {sum(v["usefulness"] > 0 for _, v in pos_gold)}; '
          f'judge negative where gold >= 0: {sum(v["usefulness"] < 0 and lab["usefulness"] >= 0 for lab, v in pairs)}')


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('extract')
    e.add_argument('run')
    e.add_argument('library')
    e.add_argument('out')
    e.add_argument('--condition', default='E-minus')
    s = sub.add_parser('synth')
    s.add_argument('cases')
    s.add_argument('out')
    r = sub.add_parser('run')
    r.add_argument('cases')
    r.add_argument('out')
    r.add_argument('--guide')
    r.add_argument('--config', default='configs/pilot.json')
    r.add_argument('--cache', default='/tmp/judge-eval.sqlite')
    r.add_argument('--workers', type=int, default=16)
    r.add_argument('--limit', type=int)
    r.add_argument('--binary', action='store_true')
    c = sub.add_parser('score')
    c.add_argument('verdicts')
    c.add_argument('labels')
    a = p.parse_args()
    {'extract': extract, 'synth': synth, 'run': run, 'score': score}[a.cmd](a)


if __name__ == '__main__':
    main()
