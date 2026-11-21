"""Refiner check on real harmful rules: does the refiner (REFINE_GUIDE, the 9B) fix what made a rule harmful?

Cases come from results/judge-eval: archived E-minus games where a rule was shown, gold-labelled by Claude
(gold.jsonl: followed, usefulness -2..2, reason). Every rule with at least one gold-harmful use (followed
yes/partly, usefulness < 0) becomes one scenario, built the way manual.refine sees it: harmful_games (gold
harmful uses, reason = manual.harms on the trace, or the gold reason when harms finds nothing) and used_games
(other followed uses), each with the last CONTEXT_STEPS steps, rejected ones marked. The refiner is called with
several seeds; each output goes through the shipped checks (manual.checked with repair, the accepted-command
check). Trial games are not played here (they need the live game).

Writes <out>/refiner.jsonl: one row per scenario and seed with the payload summary, the gold reasons of the
harmful uses, the raw rewrite, the checked text or the check error. Grading is qualitative (a Claude reader,
blind to which seed is which): does the rewrite remove the cause named in the gold reasons, without new errors?

usage: python tools/refiner_check.py results/judge-eval /root/refiner-check [--seeds 3] [--config configs/pilot.json]
"""
import argparse
import collections
import concurrent.futures
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402


def steps(trace):
    return [t['action'] + ('' if t['valid'] else manual.REJECTED_MARK) for t in trace][-manual.CONTEXT_STEPS:]


def scenarios(folder):
    cases = {}
    for line in (folder / 'cases.jsonl').read_text().splitlines():
        if line.strip():
            c = json.loads(line)
            cases[c['case_id']] = c
    gold = [json.loads(line) for line in (folder / 'gold.jsonl').read_text().splitlines() if line.strip()]
    by_rule = collections.defaultdict(list)
    for g in gold:
        c = cases[g['case_id']]
        if g['followed'] in ('yes', 'partly'):
            by_rule[(c['rule_id'], c['rule'])].append((c, g))
    out = []
    for (rule_id, text), uses in sorted(by_rule.items()):
        harmful = [(c, g) for c, g in uses if g['usefulness'] < 0]
        if not harmful:
            continue
        rule = {'id': rule_id, 'type': uses[0][0]['rule_type'], 'rule': text, 'example': '',
                'task_type': uses[0][0]['task_type']}
        contexts = []
        for c, g in uses:
            harm = manual.harms(rule, c['trace'], c['goal']) if g['usefulness'] < 0 else []
            contexts.append({'task': c['goal'], 'won': c['won'], 'steps': steps(c['trace']),
                             'score': -1 if g['usefulness'] < 0 else (1 if c['won'] else 0),
                             'reason': '; '.join(harm) or (g['reason'] if g['usefulness'] < 0 else '')})
        rule['contexts'] = (contexts[-2 * manual.K_CONTEXTS:])
        out.append({'rule': rule, 'gold_reasons': [g['reason'] for _, g in harmful],
                    'harm_found': [bool(manual.harms(rule, c['trace'], c['goal'])) for c, _ in harmful]})
    return out


class Asker:
    """The bits of Agent that manual.checked and the refiner call need."""
    def __init__(self, model, seed):
        self.model, self.seed = model, seed

    def _ask(self, role, payload):
        return self.model.complete(role, {'task': {'goal': 'refiner check'}, **payload}, self.seed, {}).data


def main():
    p = argparse.ArgumentParser()
    p.add_argument('folder')
    p.add_argument('out')
    p.add_argument('--seeds', type=int, default=3)
    p.add_argument('--config', default='configs/pilot.json')
    a = p.parse_args()
    from living_library.config import Settings
    from living_library.models import HTTPModel
    cfg = Settings.load(a.config)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    local = threading.local()
    items = scenarios(Path(a.folder))
    print(len(items), 'scenarios;', sum(len(s['rule']['contexts']) for s in items), 'contexts', flush=True)

    def one(job):
        s, seed = job
        if not hasattr(local, 'model'):
            local.model = HTTPModel(cfg, out / 'model-cache.sqlite')
        asker, rule = Asker(local.model, seed), s['rule']
        contexts = rule['contexts']
        shown = [{k: c[k] for k in ('task', 'won', 'steps', 'reason') if k in c} for c in contexts]
        row = {'rule_id': rule['id'], 'seed': seed, 'type': rule['type'], 'old_rule': rule['rule'],
               'gold_reasons': s['gold_reasons'], 'harm_found': s['harm_found'],
               'harmful_games': [c for c, full in zip(shown, contexts) if full['score'] < 0],
               'used_games': len([c for c in contexts if c['score'] >= 0])}
        try:
            data = asker._ask('refiner', {
                'instructions': manual.REFINE_GUIDE,
                'rule': {k: rule.get(k, '') for k in ('type', 'rule', 'example')}, 'validation': [],
                'harmful_games': [c for c, full in zip(shown, contexts) if full['score'] < 0],
                'used_games': [c for c, full in zip(shown, contexts) if full['score'] >= 0],
                'response_schema': {'rule': 'string'}})
            row['raw'] = data.get('rule') if isinstance(data, dict) else None
            text = manual.checked(rule['type'], row['raw'] or '', asker._ask, rule['task_type'])
            actions = [x for c in contexts for x in c['steps'] if not x.endswith(manual.REJECTED_MARK)]
            missing = [f'{v} {n}' for v, n in manual.instructed_commands(text)
                       if not any(manual._matches(x, v, n) for x in actions)]
            row['checked'] = text
            if text == rule['rule']:
                row['check_error'] = 'same rule'
            elif missing:
                row['check_error'] = 'commands no stored game shows: ' + ', '.join(missing)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            row['check_error'] = str(exc)[:300]
        return row

    jobs = [(s, seed) for s in items for seed in range(a.seeds)]
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(one, jobs))
    with open(out / 'refiner.jsonl', 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')
    ok = sum(1 for r in rows if 'check_error' not in r)
    print(f'{len(rows)} rewrites, {ok} pass the shipped checks')
    for r in rows:
        print(r['rule_id'], r['seed'], '|', r['old_rule'][:90], '->', r.get('checked', '')[:140], '|', r.get('check_error', '')[:80])


if __name__ == '__main__':
    main()
