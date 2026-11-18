"""Show what a practice run learned.

usage: python tools/show_library.py RUN_DIR_OR_RULES_FILE [--stream practice-E-0]
A run dir: reads the last checkpoint of the stream (memory rules) and counts manual operations and builder
errors/rejections over all checkpoint records. A rules file: prints the per-rule lines only.
"""
import argparse
import collections
import json
from pathlib import Path

HIDDEN = ('Unresolved Error',)


def rule_lines(rules):
    lines = []
    for r in rules:
        ctx = r.get('contexts')
        stored = 'n/a (stripped)' if ctx is None else f"{len(ctx)} ctx, {sum(bool(c.get('plan')) for c in ctx)} with plan"
        hidden = 'hidden' if (r.get('type') in HIDDEN or r.get('verified') is False) else 'visible'
        lines.append(f"{r.get('id')} [{r.get('type')}] task_type={r.get('task_type')} "
                     f"a/b={r.get('alpha')}/{r.get('beta')} {hidden} won contexts: {stored}\n    {r.get('rule')}")
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument('path')
    p.add_argument('--stream', default='practice-E-0')
    a = p.parse_args()
    path = Path(a.path)
    if path.is_dir():
        files = sorted((path / 'checkpoints' / a.stream).glob('*.json'))
        if not files:
            raise SystemExit(f'no checkpoints in {path / "checkpoints" / a.stream}')
        rules = json.loads(files[-1].read_text())['memory']['rules']
        print(f'{files[-1]}: {len(rules)} rules')
        ops, errors, extra = collections.Counter(), 0, collections.Counter()
        for f in files:
            rec = json.loads(f.read_text())['record']
            m = rec.get('manual') or {}
            ops.update(o.get('op') for o in m.get('operations', []))
            errors += len(m.get('errors', []))
            for k in ('candidate_attempts', 'candidate_rejections', 'candidate_duplicates', 'candidate_refinements'):
                extra[k] += rec.get(k) or 0
        print('\n'.join(rule_lines(rules)))
        print(f'\nmanual operations over {len(files)} games: ' + ', '.join(f'{k}={v}' for k, v in sorted(ops.items())))
        print(f'builder errors: {errors}; ' + ', '.join(f'{k}={v}' for k, v in sorted(extra.items())))
    else:
        rules = json.loads(path.read_text())
        print(f'{path}: {len(rules)} rules')
        print('\n'.join(rule_lines(rules)))


if __name__ == '__main__':
    main()
