"""Builder check on real games: the Builder's call (one per game) replayed on archived practice games, with the
library as it was before each game, for two input variants (game facts on / off), so a Claude reader can grade
the operations side by side.

For each checkpoint of RUN/checkpoints/STREAM: rules = the memory saved after the previous game; the Builder sees
the rules `manual.for_builder` picks, the game, the retry pair (a winning retry is rebuilt from its stored actions),
and with --facts the game facts. Its operations go through `manual.apply` on a copy (the shipped checks), so the
output is what the library would have received. Retries, evidence and management are not re-run.

Writes <out>/<variant>.jsonl: per game the task, outcome, case, numbered last steps, facts, the rules shown, the
applied operations and the refusals.

usage: python tools/builder_check.py RUN STREAM OUT --variant base|facts [--games 48] [--seed 0]
"""
import argparse
import concurrent.futures
import copy
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library import manual  # noqa: E402
from living_library.embedding import LexicalEmbedding  # noqa: E402


class Asker:
    def __init__(self, model, seed):
        self.model, self.seed = model, seed

    def _ask(self, role, payload):
        return self.model.complete(role, {'task': {'goal': 'builder check'}, **payload}, self.seed, {}).data


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run')
    p.add_argument('stream')
    p.add_argument('out')
    p.add_argument('--variant', choices=('base', 'facts', 'facts2', 'facts3'), required=True)
    p.add_argument('--games', type=int, default=48)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--config', default='configs/pilot.json')
    a = p.parse_args()
    from living_library.config import Settings
    from living_library.models import HTTPModel
    manual.BUILDER_FACTS = a.variant != 'base'
    cfg = Settings.load(a.config)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kinds = {}
    for tasks in json.loads(Path('/root/ll-runs/manifest.json').read_text())['splits'].values():
        kinds.update({task['id']: task['task_type'] for task in tasks})
    files = sorted((Path(a.run) / 'checkpoints' / a.stream).glob('*.json'))[:a.games]
    local = threading.local()
    embedder = LexicalEmbedding()

    def one(i):
        if not hasattr(local, 'model'):
            local.model = HTTPModel(cfg, out / f'cache-{a.variant}.sqlite')
        asker = Asker(local.model, a.seed)
        prev = json.loads(files[i - 1].read_text())['memory']['rules'] if i else []
        rules = copy.deepcopy(prev)
        r = json.loads(files[i].read_text())['record']
        goal, task_type = r['goal'], kinds.get(r['task_id'])
        case = manual.case_of(r)
        extra, retry_trace = {}, None
        s = r.get('retries')
        if s and s.get('attempts'):
            if s['won']:
                case = 'corrected failure'
                retry_trace = [{'action': x, 'valid': True, 'after': ''} for x in s['attempts'][-1]['actions']]
                extra = {'successful_retry': manual._game({'trace': retry_trace, 'success': True}, goal),
                         'reflections': [x['reflection'] for x in s['attempts']]}
            else:
                extra = {'failed_retries': [{k: x[k] for k in ('reflection', 'actions')} for x in s['attempts']]}
        contrast = manual.contrast_trace(rules, task_type) if manual.BUILDER_FACTS and case == 'failure' else None
        if contrast:
            case = 'contrasted failure'
        shown = manual.for_builder(rules, task_type, manual.BUILDER_SEES, goal, embedder.similarity)
        guide = manual.builder_guide(case, False, task_type, shown)
        if 'failed_retries' in extra:
            guide += manual.RETRY_NOTE
        payload = manual.builder_payload(guide, r, goal, extra, task_type, shown, case, False, retry_trace,
                                         contrast)
        counter = [max([int(x['id'].split('_')[1]) for x in rules] + [0])]

        def next_id():
            counter[0] += 1
            return f'rule_{counter[0]}'
        row = {'game': i, 'task': goal, 'won_first_attempt': r['success'], 'case': case,
               'steps': [t['action'] + ('' if t['valid'] else ' [rejected]') for t in r['trace']][-30:],
               'first_step_shown': max(1, len(r['trace']) - 29),
               'facts': payload.get('game_facts', []), 'won_game_of_this_kind': payload.get('won_game_of_this_kind'), 'retry_won': bool(s and s.get('won')),
               'rules_shown': {x['id']: x['rule'] for x in shown}}
        errors = []
        try:
            data = asker._ask('builder', payload)
            row['diagnosis'] = data.get('diagnosis')
            won_trace = r['trace'] if r['success'] else (retry_trace or contrast)
            refused = []
            applied = manual.apply(rules, data.get('operations'), case, False, next_id, errors, task_type,
                                   [x['id'] for x in shown], embedder.similarity, goal, asker._ask, won_trace,
                                   None, r['position'], refused)
            fixable = [(op, why) for op, why in refused if op.get('op') != 'note' and why != 'duplicate rule']
            if fixable and a.variant == 'facts3':
                payload['instructions'] += manual.REVISE_NOTE
                payload['refused_operations'] = [{'operation': op, 'reason': why} for op, why in fixable]
                data = asker._ask('builder', payload)
                errors.append('--- revision ---')
                again = manual.apply(rules, data.get('operations') if isinstance(data, dict) else None, case, False,
                                     next_id, errors, task_type, [x['id'] for x in shown], embedder.similarity,
                                     goal, asker._ask, won_trace, None, r['position'], None,
                                     sum(o['op'] == 'write_rule' for o in applied))
                row['revised'] = [{k: o.get(k) for k in ('op', 'type', 'id', 'rule', 'validation') if o.get(k)}
                                  for o in again if o.get('op') in ('write_rule', 'note', 'update_note')]
                applied += again
            row['operations'] = [{k: o.get(k) for k in ('op', 'type', 'id', 'rule', 'validation') if o.get(k)}
                                 for o in applied if o.get('op') in ('write_rule', 'note', 'update_note')]
        except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
            errors.append(f'builder: {exc}'[:200])
            row['operations'] = []
        row['refused_by_checks'] = errors
        return row

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(one, range(len(files))))
    with open(out / f'{a.variant}.jsonl', 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')
    ops = [o for row in rows for o in row['operations']]
    print(a.variant, len(rows), 'games;', sum(o['op'] == 'write_rule' for o in ops), 'rules,',
          sum(o['op'] == 'note' for o in ops), 'notes,', sum(len(row['refused_by_checks']) for row in rows), 'refused')


if __name__ == '__main__':
    main()
