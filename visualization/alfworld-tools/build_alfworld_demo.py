"""Package simulator captures as a self-contained English interactive demo."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--captures', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--template', type=Path, default=Path(__file__).with_name('alfworld-demo.template.html'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
data = json.loads((args.captures/'replay.json').read_text())
assert data.get('comparisons'), 'Expected matched comparison definitions.'
by_id = {ep['id']: ep for ep in data['episodes']}
expected_ids = {comparison[side]['id'] for comparison in data['comparisons']
                for side in ('left', 'right')}
assert len(by_id) == len(data['episodes']), 'Duplicate replay IDs.'
assert set(by_id) == expected_ids, 'Selected replays are missing or unexpected.'
for comparison in data['comparisons']:
    left, right = [by_id[comparison[side]['id']] for side in ('left', 'right')]
    assert left['game_id'] == right['game_id'], comparison['id']
    assert left['game_sha256'] == right['game_sha256'], comparison['id']
    if comparison.get('require_right_success'):
        assert right['condition'] == 'E' and right['recorded_won'] and right['thor_won'], comparison['id']
    for beat in comparison['beats']:
        assert 0 <= beat['left'] <= len(left['steps']), comparison['id']
        assert 0 <= beat['right'] <= len(right['steps']), comparison['id']
for episode in data['episodes']:
    assert episode['recorded_won'] == episode['textworld_won'] == episode['thor_won'], episode['id']
    assert all(step['recorded_valid'] == step['textworld_valid'] for step in episode['steps']), episode['id']
for ep in data['episodes']:
    ep['focus_objects'] = sorted({s['action'][5:].split(' from ', 1)[0]
                                 for s in ep['steps'] if s['action'].startswith('take ')})

images, deduplicated, frames = {}, {}, []
for ep in data['episodes']:
    paths = [ep['initial_frame']]
    for step in ep['steps']:
        paths.append(step['frame'])
        paths.extend(sub['frame'] for sub in step['low_level'])
    for name in paths:
        raw = (args.captures/name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in deduplicated:
            deduplicated[digest] = len(frames)
            frames.append('data:image/jpeg;base64,'+base64.b64encode(raw).decode())
        images[name] = deduplicated[digest]
payload = json.dumps({'episodes': data['episodes'], 'comparisons': data['comparisons'], 'initial_comparison': data.get('initial_comparison'), 'images': images, 'frames': frames}, separators=(',', ':')).replace('</', '<\\/')
template = args.template.read_text()
assert template.count('__REPLAY_DATA__') == 1
html = template.replace('__REPLAY_DATA__', payload)
(args.output/'alfworld-episodes.html').write_text(html)
data['frame_storage'] = 'RGB frames are embedded in alfworld-episodes.html, keyed by the frame IDs in this data.'
(args.output/'alfworld-replay.json').write_text(json.dumps(data, indent=2))
print('Player:', len(html.encode()), 'bytes;', len(images), 'image keys;', len(deduplicated), 'unique frames', flush=True)

for ep in data['episodes']:
    assert all(s['recorded_valid'] == s['textworld_valid'] for s in ep['steps'])
    assert ep['recorded_won'] == ep['textworld_won']
    print(ep['id'], 'recorded=', ep['recorded_won'], 'TextWorld=', ep['textworld_won'], '3D=', ep['thor_won'])
