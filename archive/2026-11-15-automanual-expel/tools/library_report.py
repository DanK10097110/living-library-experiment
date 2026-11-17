"""Summarize a stream's skill library and admissions from its checkpoints.
usage: python tools/library_report.py <run dir> <stream key> [--skills]"""
import collections
import glob
import json
import sys

run, key = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(f'{run}/checkpoints/{key}/*.json'))
if not files:
    sys.exit(f'no checkpoints for {key}')
errors, rows = collections.Counter(), []
for path in files:
    r = json.load(open(path))['record']
    rows.append(r)
    errors.update(e.split(':')[0] + ': ' + e.split(':', 1)[-1][:60].strip()
                  for e in r['program_errors'] if e.startswith(('candidate', 'planner')))
n = len(rows)
calls = [i for r in rows for i in r['invocations']]
print(f'{key}: {n} episodes, success {sum(r["success"] for r in rows)}/{n}, '
      f'false success {sum(r["subgoals_passed"] and not r["success"] for r in rows)}, '
      f'planner fallbacks {sum(r["planner_fallbacks"] for r in rows)}')
print(f'  skill candidates {sum(r["candidate_attempts"] for r in rows)}, '
      f'rejected {sum(r["candidate_rejections"] for r in rows)}, '
      f'skill calls {len(calls)} ({sum(c["success"] for c in calls)} ok, '
      f'{sum(c["retrieval_error"] for c in calls)} precondition misses)')
for error, count in errors.most_common(6):
    print(f'  {count:3}x {error}')
library = json.load(open(files[-1]))['memory']['library']
uses = collections.Counter(c['skill_id'] for c in calls)
print(f'  library: {len(library["skills"])} skills, {len(library["active"])} active, '
      f'{sum(1 for s in library["skills"] if s["successes"] + s["failures"] >= 5)} used 5+ times')
if '--skills' in sys.argv:
    for s in sorted(library['skills'], key=lambda s: -(s['successes'] + s['failures'])):
        print(f"  {s['id']:28} {s['status']:9} uses {s['successes']}/{s['successes'] + s['failures']} "
              f"params {list(s['parameters'])} pre {s['preconditions']} post {s['postconditions']}")
        print('      ' + s['body'].replace('\n', ' | ')[:200])
