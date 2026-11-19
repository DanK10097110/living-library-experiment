"""Small cached chat client for lab generation (OpenAI-style local server). Every response is stored on disk
(sqlite, keyed by the full request), so reruns never call the model again. At most MAX_CONCURRENT requests
are in flight (the study shares the server and has priority)."""
import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

URL = 'http://127.0.0.1:8000/v1/chat/completions'
MODEL = 'qwen3.5-9b-q4_k_m'
MAX_CONCURRENT = 4


class CachedChat:
    def __init__(self, path, url=URL, model=MODEL, offline=False):
        self.url, self.model, self.offline = url, model, offline
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), timeout=60, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.commit()
        self.calls = 0          # real (uncached) model calls
        self.seconds = 0.0

    def _key(self, request):
        return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()

    def ask_json(self, system, user, max_tokens=900, temperature=0.2, seed=0):
        """The model's JSON object reply ({} if it is not valid JSON)."""
        request = {'model': self.model, 'messages': [{'role': 'system', 'content': system},
                                                     {'role': 'user', 'content': user}],
                   'temperature': temperature, 'max_tokens': max_tokens, 'seed': seed,
                   'response_format': {'type': 'json_object'}}
        key = self._key(request)
        with self.lock:
            row = self.db.execute('SELECT value FROM responses WHERE key=?', (key,)).fetchone()
        if row:
            content = row[0]
        else:
            if self.offline:
                raise RuntimeError('offline: response not cached')
            started = time.monotonic()
            for delay in (0, 5, 15, 30, 60):
                time.sleep(delay)
                try:
                    req = Request(self.url, json.dumps(request).encode(), {'Content-Type': 'application/json'})
                    with urlopen(req, timeout=600) as response:
                        content = json.load(response)['choices'][0]['message']['content']
                    break
                except OSError:
                    continue
            else:
                raise RuntimeError('model server unavailable')
            with self.lock:
                self.calls += 1
                self.seconds += time.monotonic() - started
                self.db.execute('INSERT OR REPLACE INTO responses VALUES (?,?)', (key, content))
                self.db.commit()
        try:
            data = json.loads(content)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def map(self, fn, items):
        """fn(item) for every item, at most MAX_CONCURRENT at a time, results in order."""
        with ThreadPoolExecutor(MAX_CONCURRENT) as pool:
            return list(pool.map(fn, items))
