import unittest
from living_library.extensions import consolidation_candidates, admit_consolidation
from living_library.library import Library, Skill


class ConsolidationTests(unittest.TestCase):
    def library(self):
        lib = Library()
        for name, command in [('first', 'take apple'), ('second', 'take mug')]:
            skill = Skill(name+'@v1', name, {}, [], ['task_won()'], f'act("{command}")',
                          tests=[{'task': name}], status='active', successes=20)
            lib.skills[skill.id] = skill
            lib.active[skill.name] = skill.id
        return lib

    def test_only_proposes_and_gate_checks_union(self):
        lib = self.library()
        proposal, = consolidation_candidates(lib)
        self.assertEqual(len(lib.skills), 2)
        seen = []
        def verify(skill, test):
            seen.append(test['task'])
            return test['task'] != 'second'
        self.assertFalse(admit_consolidation(lib, proposal, verify))
        self.assertCountEqual(seen, ['first', 'second'])
        self.assertEqual(len(lib.current()), 2)
        self.assertEqual(lib.skills[proposal.candidate.id].successes, 0)

    def test_supplied_body_and_success_retains_originals(self):
        lib = self.library()
        proposal, = consolidation_candidates(lib, lambda ids: 'act("general")')
        proposal.tests.clear()  # cannot remove real source regressions
        seen = []
        self.assertTrue(admit_consolidation(lib, proposal, lambda s, t: seen.append(t) or True))
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(lib.skills), 3)
        self.assertEqual(len(lib.skills[proposal.candidate.id].tests), 2)
        self.assertEqual(lib.skills[proposal.candidate.id].uses, 0)

    def test_no_replays_or_different_contract(self):
        lib = self.library()
        for s in lib.current():
            s.tests.clear()
        proposal, = consolidation_candidates(lib)
        with self.assertRaisesRegex(ValueError, 'real source'):
            admit_consolidation(lib, proposal, lambda s, t: True)
        lib.skills['second@v1'].postconditions = ['is_clean(apple)']
        self.assertEqual(consolidation_candidates(lib), [])


if __name__ == '__main__':
    unittest.main()
