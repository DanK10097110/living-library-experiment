"""Small synchronous model interface; fixture runs never contact a model server."""
from dataclasses import dataclass, asdict
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
from urllib.error import URLError
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
    # Static parts of a request go first so the server's prompt cache reuses them
    # across calls; the per-call payload follows in compact JSON.
    STATIC_KEYS = ('instructions', 'response_schema', 'allowed_predicates')
    SYSTEM = ('Return only one JSON object matching the supplied response_schema. Use only public '
              'observations and allowed predicates. Never invent environment facts.')
    RETRIES = (5, 15, 30, 60, 120)

    def __init__(self, cfg, cache_path):
        self.cfg = cfg
        for url in (cfg.planner_url, cfg.executor_url):
            parsed = urlparse(url)
            if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
                raise ValueError('model endpoints must be local HTTP servers')
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(cache_path), timeout=60)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()

    def request(self, role, payload, seed):
        planner = role == 'planner'
        if role == 'actor':
            # Step-by-step ALFWorld actor: the published plain-text ReAct prompt, no JSON wrapper.
            messages = [{'role': 'user', 'content': payload['prompt']}]
            max_tokens = self.cfg.max_tokens
            if payload.get('partial') is not None:
                # Follow-up to a reply that ran out of tokens: its own reasoning, then "act now".
                messages += [{'role': 'assistant', 'content': payload['partial']},
                             {'role': 'user', 'content': payload['followup']}]
                max_tokens = payload['followup_tokens']
            return {'model': self.cfg.executor_model, 'messages': messages,
                    'temperature': self.cfg.temperature, 'max_tokens': max_tokens, 'seed': seed}
        static = {'role': role, **{k: payload[k] for k in self.STATIC_KEYS if k in payload}}
        dynamic = {k: v for k, v in payload.items() if k not in self.STATIC_KEYS}
        ordered = {k: dynamic[k] for k in ('task', 'goal') if k in dynamic}
        ordered.update({k: dynamic[k] for k in sorted(dynamic) if k not in ordered})
        compact = dict(sort_keys=False, separators=(',', ':'))
        return {'model': self.cfg.planner_model if planner else self.cfg.executor_model,
                'messages': [{'role': 'system', 'content': self.SYSTEM + '\n' + json.dumps(static, sort_keys=True, separators=(',', ':'))},
                             {'role': 'user', 'content': json.dumps(ordered, **compact)}],
                'temperature': self.cfg.temperature, 'max_tokens': self.cfg.max_tokens * (2 if role == 'builder' else 1),  # Builder: whole operation lists
                'seed': seed, 'response_format': {'type': 'json_object'}}

    def _post(self, url, request):
        for attempt, delay in enumerate((0,) + self.RETRIES):
            if delay:
                time.sleep(delay)
            try:
                req = Request(url, json.dumps(request).encode(), {'Content-Type': 'application/json'})
                with urlopen(req, timeout=900) as response:
                    return json.load(response)
            except (URLError, ConnectionError, TimeoutError) as exc:
                # A server restart is not an agent failure; give it time, then stop the run.
                if attempt == len(self.RETRIES):
                    raise
                print(f'model server unavailable ({exc}); retrying', file=sys.stderr, flush=True)

    def complete(self, role, payload, seed, context):
        planner = role == 'planner'
        url = (self.cfg.planner_url if planner else self.cfg.executor_url).rstrip('/') + '/chat/completions'
        request = self.request(role, payload, seed)
        # The episode context addresses the cache (deterministic replay) but is not shown to the model.
        key = digest({'url': url, 'request': request, 'context': context})
        row = self.db.execute('SELECT value FROM responses WHERE key=?', (key,)).fetchone()
        if row:
            return ModelResponse(**{**json.loads(row[0]), 'cached': True})
        started = time.monotonic()
        raw = self._post(url, request)
        elapsed = time.monotonic() - started
        try:
            content = raw['choices'][0]['message']['content']
            data = {'text': content} if role == 'actor' else json.loads(content)
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
        if role == 'actor':
            admissible = payload['admissible']
            action = next((c for c in [commands[0], commands[3], commands[2]] if c in admissible), f'go to {target}')
            data = {'text': f'<think>fixture policy</think> <action>{action}</action>'}
        elif role == 'planner':
            data = {'subgoals': [{'description': 'put object in target', 'bindings': bindings, 'postconditions': [f'located({obj}, {target})']}]}
        elif role == 'builder':
            # One Success Process per won game (skipped if already written), one error rule otherwise.
            known = {r['rule'] for r in payload.get('rules', [])}
            if payload['game']['won']:
                rule = {'op': 'write_rule', 'type': 'Success Process',
                        'rule': 'When the task is to put an object somewhere: 1. take it, 2. go there, 3. open it, 4. move it in.',
                        'example': f'take {obj} from table 1; go to {target}; open {target}; move {obj} to {target}'}
            else:
                rule = {'op': 'write_rule', 'type': 'Unresolved Error',
                        'rule': 'When an action is not admissible, nothing happens.', 'example': ''}
            data = {'diagnosis': 'imperfect rules', 'operations': [] if rule['rule'] in known else [rule]}
        elif role == 'judge':
            # Per-rule usefulness judge (manual.py): every shown rule followed and a little useful.
            data = {'followed': 'yes', 'usefulness': 1, 'reason': 'fixture'}
        else:
            # No fixture answer (e.g. reflector, refiner): the caller records a model error. Tests that
            # need these roles subclass the fixture.
            raise KeyError(f'fixture model has no answer for role {role!r}')
        return ModelResponse(data)

    def close(self):
        pass


# Descriptive alias for callers.
OpenAICompatibleModel = HTTPModel
