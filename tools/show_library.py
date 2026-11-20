"""Show what a practice run learned.

usage: python tools/show_library.py RUN_DIR_OR_RULES_FILE [--stream practice-E-0]
A run dir: reads the last checkpoint of the stream (memory rules) and counts manual operations and builder
errors/rejections over all checkpoint records. A rules file: prints the per-rule lines only.
Per rule: the evidence of its current text (judged showings, followed, shrunk mean usefulness m) and its
revisions (LIBRARY-SPEC.md section 2).
"""
import argparse
import collections
import json
from pathlib import Path

HIDDEN = ('Unresolved Error', 'Failure Pool')
PRIOR = 2          # manual.PRIOR: m = sum / (followed + PRIOR)


def is_hidden(r):
    return r.get('type') in HIDDEN or bool(r.get('hidden'))


def mean(r):
    """The shrunk mean usefulness m of the rule's current text (0 without evidence)."""
    ev = r.get('ev') or {}
    return (ev.get('sum') or 0) / ((ev.get('followed') or 0) + PRIOR)


def rule_lines(rules):
    lines = []
    for r in rules:
        ev, total = r.get('ev') or {}, r.get('total') or {}
        ctx = r.get('contexts')
        stored = 'n/a' if ctx is None else (f"{sum(c.get('score', 0) > 0 for c in ctx)}+/"
                                           f"{sum(c.get('score', 0) < 0 for c in ctx)}-")
        lines.append(f"{r.get('id')} [{r.get('type')}] task_type={r.get('task_type')} "
                     f"{'hidden' if is_hidden(r) else 'visible'} shown={ev.get('shown', 0)} "
                     f"followed={ev.get('followed', 0)} m={mean(r):+.2f} revisions={r.get('revisions', 0)} "
                     f"lifetime={total.get('followed', 0)}/{total.get('shown', 0)} contexts={stored}\n"
                     f"    {r.get('rule')}")
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
        ops, errors = collections.Counter(), 0
        for f in files:
            m = json.loads(f.read_text())['record'].get('manual') or {}
            ops.update(o.get('op') for o in m.get('operations', []))
            errors += len(m.get('errors', []))
        print('\n'.join(rule_lines(rules)))
        print(f'\nmanual operations over {len(files)} games: ' + ', '.join(f'{k}={v}' for k, v in sorted(ops.items())))
        print(f'builder and judge log lines: {errors}')
    else:
        rules = json.loads(path.read_text())
        print(f'{path}: {len(rules)} rules')
        print('\n'.join(rule_lines(rules)))


if __name__ == '__main__':
    main()
