"""Reference E-minus probe for a run whose probe.json predates the E-minus probe.

An E-only restart (`study --restart-streams E`, run.ps1 study -RestartE) keeps E-minus's games only if the
current code's fixture E-minus probe (experiment.e_minus_probe) equals the probe taken with the code the run
recorded (sources.json). Runs started before 2026-11-19 have no such probe in probe.json; this tool computes
it from that code: an earlier commit (--ref, exported with git archive) or an exported tree (--tree). The probe
function of the CURRENT code is run against the OLD package, so both sides measure the same things.

  python tools/e_minus_probe.py --ref 7da1ecf --run /root/ll-runs/study
writes results/probes/e-minus-<sources>.json (found by restart_library) after checking that the tree's
source digest equals the run's recorded sources.
"""
import argparse
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from living_library.config import Settings, digest   # noqa: E402
from living_library.experiment import E_MINUS_PROBES, e_minus_probe, load_json   # noqa: E402

RUNNER = '''
import json, sys
sys.path.insert(0, {root!r})
from living_library.config import Settings, digest
from living_library.experiment import source_hashes
{probe}
cfg = Settings(**json.loads({settings!r}))
print(json.dumps({{'sources': digest(source_hashes()), 'settings': digest(cfg.to_dict()),
                  'probe': e_minus_probe(cfg)}}))
'''


def probe_tree(tree, cfg, python=sys.executable):
    """{'sources', 'settings', 'probe'} of the package in `tree`, measured with the current probe function."""
    code = RUNNER.format(root=str(tree), probe=inspect.getsource(e_minus_probe),
                         settings=json.dumps(cfg.to_dict()))
    out = subprocess.run([python, '-c', code], cwd=tree, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def export(ref, destination):
    archive = subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', ref],
                             capture_output=True, check=True).stdout
    subprocess.run(['tar', '-x', '-C', str(destination)], input=archive, check=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--ref', help='git commit with the code the run recorded')
    source.add_argument('--tree', help='a directory holding that code (living_library/ at its top)')
    p.add_argument('--config', default=str(ROOT / 'configs' / 'pilot.json'))
    p.add_argument('--run', help="the run's output directory: its sources.json must match the tree")
    p.add_argument('--out', default=str(E_MINUS_PROBES))
    args = p.parse_args(argv)
    cfg = Settings.load(args.config)
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(args.tree) if args.tree else Path(tmp)
        if args.ref:
            export(args.ref, tree)
        found = probe_tree(tree, cfg)
    if args.run:
        recorded = digest(load_json(Path(args.run) / 'sources.json'))
        if found['sources'] != recorded:
            print(f'error: the tree is not the code {args.run} recorded (sources differ)', file=sys.stderr)
            return 2
    found['ref'] = args.ref or str(args.tree)
    out = Path(args.out) / f"e-minus-{found['sources'][:16]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(found, indent=2, sort_keys=True) + '\n')
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
