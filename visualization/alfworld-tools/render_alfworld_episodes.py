"""Replay selected recorded actions in ALFWorld's TextWorld and AI2-THOR engines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
from replay_cases import load_cases

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--data-root', type=Path, required=True)
parser.add_argument('--cache-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--only', help='Regenerate one saved episode ID, retaining other captures.')
parser.add_argument('--selection', type=Path, default=Path(__file__).with_name('alfworld-comparisons.json'))
parser.add_argument('--reuse', action='store_true', help='Reuse captures whose source record hash matches.')
args = parser.parse_args()
args.data_root = args.data_root.resolve()
args.output = args.output.resolve()
args.output.mkdir(parents=True, exist_ok=True)
os.environ['ALFWORLD_DATA'] = str(args.data_root.parent)

import numpy as np
from PIL import Image
import textworld
import alfworld.agents
import alfworld.gen.constants as constants
from alfworld.env.thor_env import ThorEnv
from alfworld.agents.controller.oracle import OracleAgent
from alfworld.agents.environment.alfred_tw_env import AlfredDemangler


def physical_id(name):
    for old, new in [('_bar_', '|'), ('_minus_', '-'), ('_plus_', '+'),
                     ('_dot_', '.'), ('_comma_', ',')]:
        name = name.replace(old, new)
    return name.lower()


class CaptureThorEnv(ThorEnv):
    """Keep the official simulator and task logic; capture returned RGB frames."""
    capture_dir = None
    captured = None

    def base_dir(self):
        return str(args.cache_root.resolve())

    def build_url(self):
        url, checksum = super().build_url()
        return url.replace('http://', 'https://', 1), checksum

    def step(self, action, *pos, **kw):
        event = super().step(action, *pos, **kw)
        if self.capture_dir is not None:
            name = f'{len(self.captured):04d}.jpg'
            Image.fromarray(event.frame).save(self.capture_dir / name, quality=90)
            self.captured.append({
                'frame': str((self.capture_dir / name).relative_to(args.output)),
                'action': action['action'],
                'success': bool(event.metadata['lastActionSuccess']),
                'error': event.metadata.get('errorMessage', ''),
            })
        return event


class AlignedOracle(OracleAgent):
    """Use TextWorld's canonical instance IDs in the existing oracle controller.

    ALFWorld's two backends otherwise number entities in different orders. This
    changes names only: scene physics, task checks, and commands stay official.
    """
    def __init__(self, *pos, aliases, **kw):
        self.aliases = aliases
        self.viewpoints = {}
        self.next_action = ''
        super().__init__(*pos, **kw)

    def init_scene(self, load_receps):
        super().init_scene(load_receps)
        for oid, item in self.receptacles.items():
            if oid.lower() in self.aliases:
                item['num_id'] = self.aliases[oid.lower()]

    def explore_scene(self):
        # Same oracle map-building procedure, with vectorized segmentation counts.
        # The upstream nested loop assumes a square image; this also permits 4:3.
        height = self.env.last_event.metadata['agent']['position']['y']
        for point in self.openable_points.values():
            action = {'action': 'TeleportFull', 'x': point[0], 'y': height,
                      'z': point[1], 'rotateOnTeleport': False,
                      'rotation': point[2], 'horizon': point[3]}
            event = self.env.step(action)
            if not event.metadata['lastActionSuccess']:
                continue
            counts, color_map = self.get_instance_seg()
            for color, pixels in counts.most_common():
                oid = color_map.get(color)
                if oid is None:
                    continue
                if (oid not in self.viewpoints
                        or pixels > self.viewpoints[oid]['pixels']):
                    self.viewpoints[oid] = {'locs': action, 'pixels': pixels}
                kind = oid.split('|')[0] + ('Basin' if 'Basin' in oid else '')
                if kind not in self.STATIC_RECEPTACLES:
                    continue
                if oid not in self.receptacles:
                    self.receptacles[oid] = {
                        'object_id': oid, 'object_type': kind, 'locs': action,
                        'num_pixels': pixels,
                        'num_id': self.aliases.get(oid.lower(), f'{kind.lower()} {self.get_next_num_id(kind, self.receptacles)}'),
                        'closed': True if kind in constants.OPENABLE_CLASS_LIST else None,
                    }
                elif pixels > self.receptacles[oid]['num_pixels']:
                    self.receptacles[oid]['locs'] = action
                    self.receptacles[oid]['num_pixels'] = pixels
        # Small burners can be absent from the segmentation masks at the oracle
        # viewpoints. Keep their physical entity identity and nearest viewpoint.
        for meta in self.env.last_event.metadata['objects']:
            oid = meta['objectId']
            if (oid in self.receptacles or oid.lower() not in self.aliases
                    or meta['objectType'] not in self.STATIC_RECEPTACLES):
                continue
            if oid in self.viewpoints:
                pose = self.viewpoints[oid]['locs']
            else:
                p = meta['position']
                point = min(self.openable_points.values(),
                            key=lambda v: (v[0]-p['x'])**2+(v[1]-p['z'])**2)
                pose = {'action': 'TeleportFull', 'x': point[0], 'y': height,
                        'z': point[1], 'rotateOnTeleport': False,
                        'rotation': float(np.degrees(np.arctan2(p['x']-point[0], p['z']-point[1])) % 360),
                        'horizon': 30}
            self.receptacles[oid] = {
                'object_id': oid, 'object_type': meta['objectType'],
                'locs': pose, 'num_pixels': 0,
                'num_id': self.aliases[oid.lower()],
                'closed': meta.get('isOpen') is False if meta.get('openable') else None,
            }

    def get_instance_seg(self):
        rgb = self.env.last_event.instance_segmentation_frame.astype(np.uint32)
        packed = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
        colors, counts = np.unique(packed, return_counts=True)
        return (Counter({(int(c >> 16), int((c >> 8) & 255), int(c & 255)): int(n)
                         for c, n in zip(colors, counts)}),
                self.env.last_event.color_to_object_id)

    def step(self, command):
        # A countertop can span several metres. For a recorded go-to + pickup,
        # select the existing oracle viewpoint showing that pickup's object.
        # This grounds the high-level commands; it does not invent policy actions.
        if command.startswith('go to ') and self.next_action.startswith('take '):
            target = command[6:]
            obj_name = self.next_action[5:].split(' from ', 1)[0]
            recep = self.get_object(target, self.receptacles)
            physical = next((k for k in self.viewpoints
                             if self.aliases.get(k.lower()) == obj_name), None)
            if recep and physical:
                recep['locs'] = self.viewpoints[physical]['locs']
        if command.startswith('take ') and ' from ' in command:
            obj_name, source = command[5:].split(' from ', 1)
            recep = self.get_object(source, self.receptacles)
            if obj_name not in self.visible_objects and recep and self.curr_recep == source:
                # The saved policy acts in the abstract TextWorld state. Ground
                # that entity directly for the oracle, rather than requiring a
                # new visual detector to rediscover an occluded bowl. The actual
                # pickup still runs through the official forceAction THOR API.
                meta = next((m for m in self.env.last_event.metadata['objects']
                             if self.aliases.get(m['objectId'].lower()) == obj_name
                             and recep['object_id'] in (m['parentReceptacles'] or [])), None)
                if meta:
                    oid = meta['objectId']
                    self.objects[oid] = {'object_id': oid, 'object_type': meta['objectType'],
                                         'parent': recep['object_id'], 'loc': self.curr_loc,
                                         'num_pixels': 0, 'num_id': obj_name}
                    self.visible_objects.append(obj_name)
                    print('Oracle ground-truth entity pickup:', obj_name, flush=True)
        return super().step(command)

    def print_frame(self, recep, loc):
        # Let the official controller discover objects from instance masks.
        visible, feedback = super().print_frame(recep, loc)
        old_names = {}
        for oid, item in self.objects.items():
            old_names.setdefault(item['num_id'], []).append(oid)
            if oid.lower() in self.aliases:
                item['num_id'] = self.aliases[oid.lower()]
        # Rebuild the visible names from metadata rather than replacing strings,
        # because two numbering schemes can assign the same name differently.
        visible_names = []
        for oid, item in self.objects.items():
            meta = self.get_obj_id_from_metadata(oid)
            if (meta and meta['visible']
                    and recep['object_id'] in (meta['parentReceptacles'] or [])
                    and item['num_id'] not in self.inventory):
                visible_names.append(item['num_id'])
        contents = ', '.join(visible_names) if visible_names else 'nothing'
        return visible_names, f"On the {recep['num_id']}, you see {contents}."


def state_summary(env, aliases):
    meta = env.last_event.metadata
    return {
        'inventory': [aliases.get(o['objectId'].lower(), o['objectType'].lower())
                      for o in meta['inventoryObjects']],
        'heated': [aliases.get(x.lower(), x) for x in sorted(env.heated_objects)],
        'cleaned': [aliases.get(x.lower(), x) for x in sorted(env.cleaned_objects)],
        'cooled': [aliases.get(x.lower(), x) for x in sorted(env.cooled_objects)],
        'lights_on': [aliases.get(o['objectId'].lower(), o['objectType'].lower())
                      for o in meta['objects']
                      if o.get('isToggled') and 'Lamp' in o['objectType']],
        'agent_position': meta['agent']['position'],
        'agent_rotation': meta['agent']['rotation'],
    }


manifest, selected = load_cases(args.repo, args.selection)
selected_ids = {ep['id'] for ep, _ in selected}
results = []
if (args.only or args.reuse) and (args.output/'replay.json').exists():
    results = [r for r in json.loads((args.output/'replay.json').read_text())['episodes']
               if r['id'] in selected_ids and r['id'] != args.only]


def enrich(result, episode):
    for key in ['comparison_id', 'comparison_side', 'display_label', 'phase_label',
                'reflection', 'rule_changes_after']:
        result[key] = episode.get(key)
    return result


def save_results():
    results.sort(key=lambda item: next(i for i, (r, _) in enumerate(selected)
                                      if r['id'] == item['id']))
    (args.output/'replay.json').write_text(json.dumps({
        'renderer': 'ALFWorld 0.4.2 / AI2-THOR 2.1.0',
        'mode': 'Replay of recorded actions; no new language-model inference.',
        'resolution': [800, 600],
        'alignment': 'TextWorld aliases mapped to physical IDs; oracle viewpoints and official forceAction object interaction. Not a vision-policy evaluation.',
        'comparisons': manifest['comparisons'],
        'episodes': results,
    }, indent=2))


env = CaptureThorEnv(player_screen_width=800, player_screen_height=600)
try:
    for ep, source_file in selected:
        if args.only and ep['id'] != args.only:
            continue
        cached = next((r for r in results if r['id'] == ep['id']), None)
        source_hash = hashlib.sha256((args.repo/source_file).read_bytes()).hexdigest()
        if args.reuse and cached and cached['source_sha256'] == source_hash:
            enrich(cached, ep)
            print('REUSED', ep['id'], flush=True)
            continue
        results[:] = [r for r in results if r['id'] != ep['id']]
        print('\nEPISODE', ep['id'], flush=True)
        scene_root = args.data_root / ep['game_id']
        gamefile = scene_root / 'game.tw-pddl'
        tw = textworld.start(str(gamefile),
            request_infos=textworld.EnvInfos(facts=True, won=True, admissible_commands=True),
            wrappers=[AlfredDemangler(shuffle=False)])
        try:
            tw_state = tw.reset()
            aliases = {physical_id(k): info.name.strip()
                       for k, info in tw._entity_infos.items() if '_bar_' in k}
            traj = json.loads((scene_root / 'traj_data.json').read_text())
            env.capture_dir = None
            env.task = None
            env.reset(traj['scene']['scene_num'])
            env.restore_scene(traj['scene']['object_poses'],
                              traj['scene']['object_toggles'],
                              traj['scene']['dirty_and_empty'])
            env.step(dict(traj['scene']['init_action']))
            alias_adjustments = []
            for meta in env.last_event.metadata['objects']:
                oid = meta['objectId'].lower()
                if oid in aliases or len(oid.split('|')) != 4:
                    continue
                parts = oid.split('|')
                try:
                    xyz = np.array([float(v) for v in parts[1:]])
                except ValueError:
                    continue
                candidates = []
                for original, alias in list(aliases.items()):
                    other = original.split('|')
                    if len(other) == 4 and parts[0] == other[0]:
                        distance = float(np.linalg.norm(xyz-np.array([float(v) for v in other[1:]])))
                        if distance <= 0.035:
                            candidates.append((distance, original, alias))
                if candidates:
                    distance, original, alias = min(candidates)
                    aliases[oid] = alias
                    alias_adjustments.append({'textworld_object_id': original,
                                              'thor_object_id': meta['objectId'],
                                              'alias': alias, 'id_coordinate_difference': distance})
                    print('Physical ID rounding alignment:', alias, original, '=>', oid, flush=True)
            for meta in env.last_event.metadata['objects']:
                if meta['objectType'] == traj['pddl_params']['object_target']:
                    print('TARGET', meta['objectId'], 'alias', aliases.get(meta['objectId'].lower()),
                          'parents', meta['parentReceptacles'], flush=True)
            reward_config = Path(alfworld.agents.__file__).parent / 'config/rewards.json'
            env.set_task(traj, SimpleNamespace(reward_config=str(reward_config)), reward_type='sparse')
            oracle = AlignedOracle(env, traj, str(scene_root), aliases=aliases,
                                   use_gt_relations=True, debug=False)
            # Exploration builds a map. Put the camera back at the recorded start.
            env.step(dict(traj['scene']['init_action']))
            episode_dir = args.output / ep['id']
            episode_dir.mkdir(parents=True, exist_ok=True)
            initial_frame = episode_dir / 'initial.jpg'
            Image.fromarray(env.last_event.frame).save(initial_frame, quality=90)
            initial_state = state_summary(env, aliases)
            env.capture_dir = episode_dir
            env.captured = []
            steps = []
            for record_index, rec in enumerate(ep['trace']):
                before_count = len(env.captured)
                original = rec['action']
                # TextWorld says "move ... to"; the official THOR controller says
                # "put ... in" for the same semantic action. Keep both in output.
                command = original
                if command.startswith('move '):
                    command = 'put ' + command[5:].replace(' to ', ' in ', 1)
                admissible = original in tw_state['admissible_commands']
                tw_state, _, _ = tw.step(original)
                oracle.next_action = (ep['trace'][record_index + 1]['action']
                                      if record_index + 1 < len(ep['trace']) else '')
                feedback = oracle.step(command)
                filename = episode_dir / f"step-{rec['step']:02d}.jpg"
                Image.fromarray(env.last_event.frame).save(filename, quality=90)
                item = {
                    'step': rec['step'], 'action': original,
                    'controller_action': command,
                    'recorded_valid': rec['valid'], 'textworld_valid': admissible,
                    'recorded_observation': rec.get('observation'),
                    'textworld_observation': tw_state['feedback'],
                    'thor_observation': feedback,
                    'textworld_won': bool(tw_state['won']),
                    'thor_won': bool(env.get_goal_satisfied()),
                    'frame': str(filename.relative_to(args.output)),
                    'low_level': env.captured[before_count:],
                    'state': state_summary(env, aliases),
                }
                steps.append(item)
                print(rec['step'], original, '| THOR:', feedback[:90],
                      '| won:', item['thor_won'], flush=True)
            result = {
                'id': ep['id'], 'title': ep['title'], 'goal': ep['goal'],
                'condition': ep['condition'], 'task_kind': ep['task_kind'],
                'game_id': ep['game_id'], 'source': ep['source'],
                'source_file': source_file,
                'source_sha256': hashlib.sha256((args.repo/source_file).read_bytes()).hexdigest(),
                'game_sha256': hashlib.sha256(gamefile.read_bytes()).hexdigest(),
                'recorded_won': ep['success'], 'textworld_won': bool(tw_state['won']),
                'alias_adjustments': alias_adjustments,
                'thor_won': bool(env.get_goal_satisfied()),
                'initial_frame': str(initial_frame.relative_to(args.output)),
                'initial_state': initial_state,
                'plan': ep.get('plan', []), 'rules': ep.get('rules_shown', []),
                'recorded_model_calls': ep.get('model_calls'),
                'recorded_invalid_actions': ep['invalid_actions'],
                'steps': steps,
            }
            enrich(result, ep)
            (episode_dir/'replay.json').write_text(json.dumps(result, indent=2))
            results.append(result)
            save_results()
            print('DONE:', ep['id'], 'recorded=', ep['success'],
                  'TextWorld=', tw_state['won'], 'THOR=', result['thor_won'], flush=True)
        finally:
            tw.close()
    save_results()
finally:
    env.capture_dir = None
    env.stop()
