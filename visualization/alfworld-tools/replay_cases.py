"""Load matched recorded task comparisons without reconstructing missing actions."""
import copy
import json
from pathlib import Path


def load_cases(repo, selection):
    manifest = json.loads(Path(selection).read_text())
    episodes, seen = [], set()
    for case in manifest['comparisons']:
        for side in ('left', 'right'):
            spec = case[side]
            path = Path(repo) / spec['source_file']
            record = json.loads(path.read_text())
            if 'attempt' in spec:
                initial = spec['attempt'] == 0
                game = record['practice_game']
                retry = None if initial else next(
                    r for r in record['retries'] if r['attempt'] == spec['attempt'])
                actions = record['first_attempt_trace'] if initial else retry['actions']
                ep = {
                    **copy.deepcopy(game), 'id': spec['id'], 'title': spec['label'],
                    'source': copy.deepcopy(record['source']), 'condition': 'E',
                    'success': game['success'] if initial else retry['won'],
                    'steps': len(actions),
                    'invalid_actions': sum(not a['valid'] for a in actions),
                    'model_calls': game.get('model_calls') if initial else None,
                    'trace': [dict(a, step=i) for i, a in enumerate(actions, 1)],
                    'rules_shown': record['rules_shown_in_first_attempt'],
                    'reflection': None if initial else retry['reflection'],
                    'rule_changes_after': [] if initial else record['rules_changed'],
                }
            else:
                ep = copy.deepcopy(record[spec['condition']] if spec.get('condition') else record)
                ep['id'] = spec['id']
            ep['comparison_id'] = case['id']
            ep['comparison_side'] = side
            ep['display_label'] = spec['label']
            ep['phase_label'] = spec['phase']
            if ep['id'] in seen:
                raise ValueError(f'Duplicate episode ID: {ep["id"]}')
            seen.add(ep['id'])
            episodes.append((ep, spec['source_file']))
    for case in manifest['comparisons']:
        pair = [e for e, _ in episodes if e['comparison_id'] == case['id']]
        if len({e['game_id'] for e in pair}) != 1:
            raise ValueError(f'Comparison {case["id"]} is not the same task instance')
        if case.get('require_right_success'):
            right = next(e for e in pair if e['comparison_side'] == 'right')
            if right['condition'] != 'E' or not right['success']:
                raise ValueError(f'Comparison {case["id"]} requires a successful E recording')
    return manifest, episodes
