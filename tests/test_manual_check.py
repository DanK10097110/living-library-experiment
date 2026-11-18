import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import manual_check  # noqa: E402


class LoadRulesTest(unittest.TestCase):
    def _dir(self, stripped, full=None):
        d = Path(tempfile.mkdtemp())
        (d / 'rules.json').write_text(json.dumps(stripped))
        if full is not None:
            (d / 'rules-full.json').write_text(json.dumps(full))
        return d

    def test_falls_back_to_full(self):
        d = self._dir([{'id': 'r1'}], [{'id': 'r1', 'contexts': [{'task': 't'}]}])
        rules, msg = manual_check.load_rules(d / 'rules.json')
        self.assertTrue(rules[0]['contexts'])
        self.assertIn('rules-full.json', msg)

    def test_warns_without_contexts(self):
        rules, msg = manual_check.load_rules(self._dir([{'id': 'r1'}]) / 'rules.json')
        self.assertTrue(msg.startswith('WARNING'))

    def test_full_file_is_silent(self):
        d = self._dir([{'id': 'r1', 'contexts': [{}]}])
        self.assertIsNone(manual_check.load_rules(d / 'rules.json')[1])


if __name__ == '__main__':
    unittest.main()
