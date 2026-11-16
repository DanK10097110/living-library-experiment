"""Small synchronous model interface; fixture runs never contact a model server."""
from dataclasses import dataclass, asdict
import json
import math
import sqlite3
import time
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from .config import digest


INTERFACE_PROMPT = '''You control an ALFWorld text game. Return one JSON object matching response_schema.
Use only public observations, admissible commands, and history. Examples below illustrate syntax;
their entity names are NOT evidence about this game. Never invent objects or locations.
PLANNER: Return achievable subgoals, not commands. All postconditions of ONE subgoal
must hold simultaneously: never put at(two different places) in the same subgoal.
Use exact observed numbered entities, never bare object types. Use bindings {} when
no parameters are needed. If the desired object is unseen, return ONLY one exploration
subgoal for a location not yet searched in history, then let the next planning call
use the new observation. For example, if shelf 1 is visible and unsearched:
{"subgoals":[{"description":"Inspect shelf 1","bindings":{},"postconditions":["at(shelf 1)"]}]}
If at a closed receptacle, use is_open(receptacle) to inspect its contents.
After observing an object, use holding(object) to pick it up, then located(object, target)
to place it. at takes ONE argument; located takes TWO. Do not use findable/exists to
represent searching: they do not mean the agent has discovered an object.
EXECUTOR: When response_schema asks for program, return executable Python as a JSON
string. Example: {"program":"act(\\"go to shelf 1\\")"}.
Another example: {"program":"act(\\"take mug 2 from shelf 1\\")"}.
Use a command from the current admissible list. act("command") performs an action;
check("holding(mug 2)") only tests a fact and does not change the world.
Never write bare commands like go to shelf 1 or check(at(shelf 1)).
No imports, functions, attributes, observation variables, or unbounded loops.
For flat or text-only responses, obey their action schema instead of returning program.
Use errors and previous_errors to correct your response. Do not repeat invalid syntax.
'''


@dataclass
class ModelResponse:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    wall_seconds: float = 0.0
    gpu_seconds: float | None = None
    cached: bool = False


EXECUTOR_PROMPT = '''You are the code executor for an ALFWorld text game.
Return a JSON object with exactly one key, program, whose value is Python source.
Your objective is payload.goal; state.admissible_commands is the list of actions
available NOW. Copy action strings exactly from that list into act("...").
Never invent or paraphrase commands. Predicates describe outcomes, not commands:
located(object, target) is achieved by a move command, never by locate.
If the desired placement command is available, execute it instead of navigating.
If it is not available, take an admissible prerequisite action toward the goal.
Use history to track what was picked up and which locations were already visited.
Example ONLY (names are not facts about this game): if goal is located(book 2, desk 3)
and admissible_commands contains "move book 2 to desk 3", return
{"program":"act(\\"move book 2 to desk 3\\")"}.
For holding(book 2), choose the available take command for book 2.
For at(desk 3), choose the available go to desk 3 command.
For is_open(drawer 2), choose the available open drawer 2 command.
Use act(string), check(string), and call(exact retrieved skill ID, keyword arguments).
check only tests facts; it cannot accomplish an action. No imports, functions,
attributes, unbounded loops, or invented observation variables. Correct errors.
'''


# Simulator mechanics shared by planning and execution; no game-specific locations.
SIMULATOR_RULES = '''
ALFWORLD MECHANICS:
at(x) means the agent is at a receptacle, never at a portable object or lamp.
Navigate to the receptacle containing an object or lamp, not to the object itself.
You can carry only one object. For two-object tasks, pick up and deliver the first
object before picking up and delivering the second distinct object.
To clean, heat, or cool an object, first hold it, navigate to the appropriate
sinkbasin, microwave, or fridge, then copy the available clean/heat/cool command.
To place a held object, first navigate to the destination and open it if required,
then use the available move command. Never assume navigation happened.
For look-at-object-in-light tasks, hold the requested object and use the appropriate
lamp at its containing receptacle. Examining the object alone does not win.
Use holding(object), at(receptacle), and finally task_won() as light-task goals.
Do not use at(object), at(lamp), or is_on(lamp) for this task.
If an object is absent from the current take commands, do not invent a take command.
Consult observed history for its location or search unopened/unsearched receptacles.
Every act command must be copied exactly from CURRENT admissible_commands.
Take prerequisite actions when the desired action is unavailable; never repeat
an unavailable command in an unchanged state.
'''
INTERFACE_PROMPT += SIMULATOR_RULES
EXECUTOR_PROMPT += SIMULATOR_RULES


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
                   'messages': [{'role': 'system', 'content': (
                       EXECUTOR_PROMPT if role == 'executor' and not payload.get('flat')
                       and not payload.get('text_only') else INTERFACE_PROMPT)},
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
