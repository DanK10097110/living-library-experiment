"""One-off maintenance of a stopped study (amended 2026-11-21): drop streams the current design no longer plans
(D's practice replicate 1 and the evaluations initialised from it, experiment.SINGLE_REPLICATE), re-sign the kept
streams with the current run identity, and optionally merge model-response caches of an earlier run into
memoryless streams (C's games are independent, so their earlier responses replay exactly).

Like restart_library, but the source change is a design change by the owner (D runs one replicate), so the C/D
fixture probe is retaken rather than compared. Settings and manifest must be unchanged. Kept checkpoints keep
their integrity hashes; only their stream identity is re-signed.

usage: python -m tools.drop_streams OUTPUT [--merge-cache OLD_OUTPUT KEY ...] [--config configs/pilot.json]
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from living_library.config import Settings  # noqa: E402
from living_library.experiment import Runner, identity, load_json, write_json  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('output')
    p.add_argument('--merge-cache', nargs='+', metavar=('OLD_OUTPUT', 'KEY'))
    p.add_argument('--manifest', default='/root/ll-runs/manifest.json')
    p.add_argument('--config', default='configs/pilot.json')
    a = p.parse_args()
    cfg, manifest, output = Settings.load(a.config), load_json(a.manifest), Path(a.output)
    run = load_json(output / 'run.json')
    new = identity(cfg, manifest)
    if run['identity']['settings'] != new['settings'] or run['identity']['manifest'] != new['manifest']:
        raise SystemExit('settings or manifest changed; use a new output directory')
    plan = load_json(output / 'plan.json')
    write_json(output / 'run.json', {**run, 'identity': new})
    runner = Runner(cfg, manifest, output)          # identity matches again; writes sources.json and the probe
    wanted = {s['key'] for s in runner.study_specs()} | {s['key'] for s in plan if s['phase'].startswith('gate')}
    dropped = [s['key'] for s in plan if s['key'] not in wanted]
    for key in dropped:
        shutil.rmtree(output / 'checkpoints' / key, ignore_errors=True)
        for cache in (output / 'model-cache').glob(f'{key}.sqlite*'):
            cache.unlink()
    kept = [s for s in plan if s['key'] in wanted]
    write_json(output / 'plan.json', kept)
    specs = {s['key']: s for s in kept}
    for spec in kept:
        runner.restamp(spec, specs)
    print('dropped', dropped or 'nothing', '; kept', len(kept), 'streams')
    if a.merge_cache:
        old, keys = Path(a.merge_cache[0]), a.merge_cache[1:]
        for key in keys:
            src, dst = old / 'model-cache' / f'{key}.sqlite', output / 'model-cache' / f'{key}.sqlite'
            con = sqlite3.connect(dst)
            con.execute('CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            before = con.execute('select count(*) from responses').fetchone()[0]
            con.execute('ATTACH DATABASE ? AS old', (str(src),))
            con.execute('INSERT OR IGNORE INTO responses SELECT key, value FROM old.responses')
            con.commit()
            after = con.execute('select count(*) from responses').fetchone()[0]
            con.close()
            print(f'{key}: cache {before} -> {after} responses')


if __name__ == '__main__':
    main()
