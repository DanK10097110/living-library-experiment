import csv
import tempfile
import unittest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import library_snapshots as ls  # noqa: E402


def _rule(i, typ='Success Process', **kw):
    return dict(id=f'rule_{i}', type=typ, task_type='t', rule='a b c', revisions=1, hidden=typ == 'Unresolved Error',
                ev={'shown': 3, 'followed': 2, 'sum': 2, 'pos': 2, 'neg': 0, 'won': 1, 'lost': 1},
                total={'shown': 5, 'followed': 3}, **kw)


def _fake_run(tmp_path, n=10):
    d = tmp_path / 'run' / 'checkpoints' / 'practice-E-0'
    d.mkdir(parents=True)
    (tmp_path / 'run' / 'checkpoints' / 'practice-D-0').mkdir()
    for i in range(n):
        rules = [_rule(j) for j in range(i // 2 + 1)] + [_rule(99, 'Unresolved Error')]
        ops = [{'op': 'retire'}] if i == 3 else []
        rec = {'success': i % 2 == 0, 'manual': {'operations': ops}}
        (d / f'{i:05d}.json').write_text(json.dumps({'record': rec, 'memory': {'rules': rules}}))
    return tmp_path / 'run'


class SnapshotTest(unittest.TestCase):
    def test_snapshots_and_trends(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            run, out = _fake_run(tmp_path), tmp_path / 'out'
            argv = sys.argv
            sys.argv = ['x', str(run), '--every', '5', '--out', str(out)]
            try:
                ls.main()
                snap = out / 'snapshots' / 'practice-E-0'
                self.assertEqual(sorted(p.name for p in snap.glob('*.json')), ['g005.json', 'g010.json'])
                self.assertFalse((out / 'snapshots' / 'practice-D-0').exists())
                self.assertEqual(json.loads((snap / 'g005.json').read_text())['games'], 5)
                text = (snap / 'g005.txt').read_text()
                self.assertIn('rule_0 [Success Process]', text)
                self.assertIn('shown=3 followed=2 m=+0.50 revisions=1', text)
                marker = snap / 'g005.json'
                marker.write_text('{"keep": 1}')
                ls.main()
                self.assertEqual(marker.read_text(), '{"keep": 1}')
            finally:
                sys.argv = argv
            rows = list(csv.DictReader((out / 'trends-practice-E-0.csv').open()))
            self.assertEqual([r['games'] for r in rows], ['5', '10'])
            self.assertEqual((rows[0]['retire_ops'], rows[1]['retire_ops']), ('1', '0'))
            self.assertEqual((rows[0]['win_rate'], rows[0]['hidden']), ('0.6', '1'))
            self.assertEqual((rows[1]['added'], rows[1]['removed']), ('2', '0'))
            self.assertEqual((rows[0]['mean_usefulness_visible'], rows[0]['revisions_total']), ('0.5', '4'))
            self.assertIn('| 5 | 4 | 3 |', (out / 'TRENDS.md').read_text())


if __name__ == '__main__':
    unittest.main()