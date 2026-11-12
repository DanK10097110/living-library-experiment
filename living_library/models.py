"""Small synchronous model interface; fixture runs never contact a model server."""
from dataclasses import dataclass, asdict
import json
import math
import sqlite3
import time
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from .config import digest


@dataclass
class ModelResponse:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    wall_seconds: float = 0.0
    gpu_seconds: float | None = None
    cached: bool = False


class HTTPModel:
    """OpenAI-compatible local server with durable, request-addressed replay.

    Usage is the server's token accounting. GPU seconds are only accepted from an
    explicitly supplied measurement field; elapsed request time is never GPU time.
    """
    def __init__(self, cfg, cache_path):
        self.cfg = cfg
        for url in (cfg.planner_url, cfg.executor_url):
            parsed = urlparse(url)
            if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
                raise ValueError('model endpoints must be local HTTP servers')
        self.db = sqlite3.connect(str(cache_path))
        self.db.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()

    def complete(self, role, payload, seed, context):
        planner = role == 'planner'
        url = (self.cfg.planner_url if planner else self.cfg.executor_url).rstrip('/') + '/chat/completions'
        request = {'model': self.cfg.planner_model if planner else self.cfg.executor_model,
                   'messages': [{'role': 'system', 'content': 'Return only one JSON object matching the supplied response_schema. Use only public observations and allowed predicates. Never invent environment facts.'},
                                {'role': 'user', 'content': json.dumps({'role': role, 'context': context, **payload}, sort_keys=True)}],
                   'temperature': self.cfg.temperature, 'max_tokens': self.cfg.max_tokens,
                   'seed': seed, 'response_format': {'type': 'json_object'}}
        key = digest({'url': url, 'request': request})
        row = self.db.execute('SELECT value FROM responses WHERE key=?', (key,)).fetchone()
        if row:
            return ModelResponse(**{**json.loads(row[0]), 'cached': True})
        started = time.monotonic()
        req = Request(url, json.dumps(request).encode(), {'Content-Type': 'application/json'})
        with urlopen(req, timeout=180) as response:
            raw = json.load(response)
        elapsed = time.monotonic() - started
        try:
            data = json.loads(raw['choices'][0]['message']['content'])
            if not isinstance(data, dict):
                data = {'_response_error': 'model must return a JSON object'}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            data = {'_response_error': 'invalid model JSON: ' + str(exc)}
        usage = raw.get('usage', {})
        if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
            raise ValueError('server must report nonnegative prompt/completion token counts')
        gpu = raw.get('measured_gpu_seconds')
        if gpu is not None and (type(gpu) not in (float, int) or not math.isfinite(gpu) or gpu < 0):
            raise ValueError('invalid measured GPU time')
        result = ModelResponse(data, usage['prompt_tokens'], usage['completion_tokens'], elapsed, gpu)
        self.db.execute('INSERT OR REPLACE INTO responses VALUES (?,?)', (key, json.dumps(asdict(result))))
        self.db.commit()
        return result

    def close(self):
        self.db.close()


class FixtureModel:
    """Handwritten MiniWorld policy for plumbing checks, not an LLM benchmark."""
    def complete(self, role, payload, seed, context):
        task = payload['task']
        obj, target = task.get('object', 'apple 1'), task.get('target', 'cabinet 1')
        bindings = {'object': obj, 'target': target}
        commands = [f'take {obj} from table 1', f'go to {target}', f'open {target}', f'move {obj} to {target}']
        if role == 'planner':
            data = {'subgoals': [{'description': 'put object in target', 'bindings': bindings, 'postconditions': [f'located({obj}, {target})']}]}
        elif role == 'librarian':
            parent = payload.get('parent')
            data = {'candidate': {'name': 'put_object', 'description': 'put object in target',
                    'parameters': {'object': 'entity', 'target': 'entity'},
                    'preconditions': ['at(table 1)', 'located(object, table 1)'],
                    'postconditions': ['located(object, target)', 'task_won()'],
                    'body': '\n'.join(['act(f"take {object} from table 1")', 'act(f"go to {target}")', 'act(f"open {target}")', 'act(f"move {object} to {target}")'])}}
            if parent:
                data['candidate'].update({k: parent[k] for k in ('parameters', 'preconditions', 'postconditions')})
        elif payload.get('flat'):
            skills = payload.get('skills', [])
            if skills:
                data = {'skill_id': skills[0]['id'], 'bindings': bindings}
            elif payload.get('catalog') and not payload['goal']['bindings']:
                data = {'bindings': bindings}
            else:
                admissible = payload['state']['admissible_commands']
                command = next((c for c in [commands[0], commands[3], commands[2]] if c in admissible), f'go to {target}')
                data = {'action': command, 'bindings': bindings}
        elif payload.get('text_only'):
            admissible = payload['state']['admissible_commands']
            priorities = [commands[0], commands[3], commands[2]]
            command = next((c for c in priorities if c in admissible), f'go to {target}')
            data = {'actions': [command]}
        else:
            skills = payload.get('skills', [])
            if skills:
                skill = skills[0]
                data = {'program': f'call({skill["id"]!r}, object={obj!r}, target={target!r})'}
            else:
                observation = payload['state']['observation']
                if ' is at inventory.' in observation:
                    commands = commands[1:]
                if f'At {target}.' in observation:
                    commands = commands[2:]
                if f'{target} is open.' in observation:
                    commands = [commands[-1]]
                data = {'program': '\n'.join(f'act({c!r})' for c in commands)}
        return ModelResponse(data)

    def close(self):
        pass


# Descriptive alias for callers.
OpenAICompatibleModel = HTTPModel
