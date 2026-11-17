import copy
from dataclasses import asdict
from types import SimpleNamespace
import unittest

from living_library.config import Settings
from living_library.domain import BudgetExceeded, Episode, Predicate
from living_library.environments import MiniWorld, demo_manifest, normalize_alfworld, validate_manifest
from living_library.library import Library, LexicalEmbedding, Skill
from living_library.program import InvalidProgram, Program


BODY = '''act(f"take {obj} from table 1")
act(f"go to {target}")
if not check(f"is_open({target})"):
    act(f"open {target}")
act(f"move {obj} to {target}")'''


def skill(sid="put@v1", body=BODY, parent=None):
    return Skill(sid, "put an object in a cabinet", {"obj": "entity", "target": "entity"},
                 ["located(obj, table 1)", "exists(target)"], ["located(obj, target)"], body, parent)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Settings()
        self.world = MiniWorld()
        self.world.reset({"id": "test"})
        self.bindings = {"obj": "apple 1", "target": "cabinet 1"}
        self.test = {"snapshot": self.world.snapshot(), "bindings": self.bindings}

    def verify(self, candidate, test):
        env = MiniWorld()
        env.restore(test["snapshot"])
        if not env.state.check(candidate.preconditions, test["bindings"]):
            return False
        try:
            Program(candidate.body, candidate.parameters).run(
                Episode(env, 20), test["bindings"], lambda *a: None)
        except (ValueError, RuntimeError):
            return False
        return env.state.check(candidate.postconditions, test["bindings"])

    def test_program_changes_simulator_and_replays(self):
        before = self.world.snapshot()
        Program(BODY, self.bindings).run(Episode(self.world, 10), self.bindings, lambda *a: None)
        self.assertTrue(self.world.state.won)
        saved = self.world.snapshot()
        self.world.restore(before)
        self.assertFalse(self.world.state.won)
        self.world.restore(saved)
        self.assertTrue(self.world.state.won)

    def test_program_rejects_python_escape_routes(self):
        for source in ('import os', 'act.__class__', 'open("/tmp/x")',
                       'while True: act("look")', 'act(f"{obj.__class__}")',
                       'for i in range(1000000): act("look")',
                       'act("look"); __builtins__ = "x"'):
            with self.subTest(source=source), self.assertRaises(InvalidProgram):
                Program(source, ["obj"])

    def test_shared_action_budget_counts_invalid_actions(self):
        episode = Episode(self.world, 1)
        with self.assertRaises(RuntimeError):
            episode.act("fly away")
        with self.assertRaises(BudgetExceeded):
            episode.act("look")
        self.assertEqual(len(episode.trace), 1)

    def test_instruction_budget_covers_nested_loops(self):
        p = Program('for i in range(20):\n    for j in range(20):\n        x = "ok"')
        with self.assertRaises(BudgetExceeded):
            p.run(Episode(self.world, 10), {}, lambda *a: None, budget=30)

    def test_contracts_cannot_be_free_form(self):
        with self.assertRaises(ValueError):
            Predicate.parse("looks_good(apple)")
        with self.assertRaises(ValueError):
            Predicate.parse("located(apple)")
        self.assertFalse(self.world.state.check(["located(obj, target)"], self.bindings))

    def test_regression_gate_keeps_old_version_and_rejects_weak_contract(self):
        library = Library(self.cfg)
        self.assertTrue(library.admit(skill(), self.test, self.verify))
        self.assertFalse(library.admit(skill("put@v2", 'act("look")', "put@v1"), self.test, self.verify))
        self.assertEqual(library.active["put"], "put@v1")
        candidate = skill("put@v3", parent="put@v1")
        candidate.postconditions = ["exists(obj)"]
        with self.assertRaises(ValueError):
            library.admit(candidate, self.test, self.verify)
        self.assertEqual(library.skills["put@v2"].status, "rejected")

    def test_admission_checks_all_old_tests_even_at_storage_limit(self):
        library = Library(Settings(test_limit=1))
        library.admit(skill(), self.test, lambda *a: True)
        second = copy.deepcopy(self.test)
        second["bindings"]["obj"] = "apple 2"
        called = []
        self.assertTrue(library.admit(skill("put@v2", parent="put@v1"), second,
                                     lambda s, t: called.append(t) or True))
        self.assertEqual(len(called), 2)

    def test_append_only_and_retrieval_errors_do_not_mutate_statistics(self):
        library = Library(self.cfg)
        library.admit(skill(), self.test, self.verify)
        before = library.snapshot()
        self.assertEqual(library.record("put@v1", False, False, self.test), "retrieval_error")
        library.record("put@v1", True, True, self.test, updates=False)
        self.assertEqual(before, library.snapshot())
        with self.assertRaises(ValueError):
            library.admit(skill("put@v2", parent="put@v1"), self.test, self.verify, updates=False)

    def test_low_sample_beta_and_retrieval_filter(self):
        library = Library(self.cfg)
        library.admit(skill(), self.test, self.verify)
        s = library.skills["put@v1"]
        self.assertAlmostEqual(s.reliability(self.cfg), 0.1)
        retrieved = library.retrieve("put object cabinet", self.bindings, self.world.state, LexicalEmbedding())
        self.assertEqual([s.id for s in retrieved], ["put@v1"])
        self.world.step("take apple 1 from table 1")
        self.assertEqual(library.retrieve("put", self.bindings, self.world.state, LexicalEmbedding()), [])

    def test_updates_trigger_revision_and_rollback(self):
        library = Library(self.cfg)
        library.admit(skill(), self.test, self.verify)
        for _ in range(30):
            library.record("put@v1", True, True, self.test)
        library.admit(skill("put@v2", parent="put@v1"), self.test, self.verify)
        for _ in range(4):
            library.record("put@v2", False, True, self.test, note="Could not open cabinet.")
        self.assertEqual(library.active["put"], "put@v2")
        self.assertEqual(library.record("put@v2", False, True, self.test), "rollback")
        self.assertEqual(library.active["put"], "put@v1")

    def test_model_counters_are_not_trusted_and_snapshot_is_detached(self):
        library = Library(self.cfg)
        s = skill()
        s.successes = 10000
        library.admit(s, self.test, self.verify)
        self.assertEqual(library.skills[s.id].successes, 0)
        snapshot = library.snapshot()
        snapshot["skills"][0]["body"] = 'act("look")'
        self.assertEqual(library.skills[s.id].body, BODY)
        self.assertEqual(Library.restore(library.snapshot(), self.cfg).snapshot(), library.snapshot())
        source = library.snapshot()
        restored = Library.restore(source, self.cfg)
        restored.skills[s.id].failure_notes.append("new note")
        self.assertEqual(source["skills"][0]["failure_notes"], [])

    def test_alfworld_predicates_use_ground_truth_not_narrative(self):
        def fact(name, *args):
            return SimpleNamespace(name=name, arguments=[SimpleNamespace(name=n, type=t) for n, t in args])
        raw = {"feedback": "Everything is hot and on!", "won": False, "admissible_commands": [],
               "facts": [fact("atLocation", ("agent", "agent"), ("loc1", "location")),
                         fact("receptacleAtLocation", ("Cabinet 1 ", "receptacle"), ("loc1", "location")),
                         fact("inReceptacle", ("Apple 1 ", "object"), ("Cabinet 1 ", "receptacle")),
                         fact("isToggled", ("Lamp 1", "object")),
                         fact("isOn", ("Lamp 2", "object"))]}
        state = normalize_alfworld(raw)
        self.assertTrue(state.check(["located(apple 1, cabinet 1)", "at(cabinet 1)", "is_on(lamp 2)"]))
        self.assertFalse(state.check(["is_on(lamp 1)"]))
        self.assertFalse(state.check(["is_hot(apple 1)"]))
        self.assertNotIn("loc1", state.entities)
        self.assertNotIn("facts", state.public())

    def test_manifest_rejects_split_leakage(self):
        manifest = demo_manifest()
        validate_manifest(manifest)
        manifest["splits"]["evaluation"][0]["id"] = manifest["splits"]["practice"][0]["id"]
        with self.assertRaises(ValueError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()


class LiftedPredicateTests(unittest.TestCase):
    def test_types_match_any_instance_and_ground_to_held_or_seen(self):
        from living_library.domain import State, Predicate
        state = State('On the countertop 1, you see a mug 2.', [], {'mug 1', 'mug 2', 'countertop 1', 'sinkbasin 1'},
                      {('located', 'mug 2', 'countertop 1')})
        self.assertTrue(state.holds(Predicate.parse('located(mug, countertop 1)')))
        self.assertFalse(state.holds(Predicate.parse('located(mug, sinkbasin)')))
        self.assertTrue(state.resolves('mug') and not state.resolves('kettle'))
        self.assertEqual(state.ground('mug'), 'mug 2')        # in view
        state.facts.add(('holding', 'mug 1'))
        self.assertEqual(state.ground('mug'), 'mug 1')        # held wins
        self.assertEqual(state.ground('sinkbasin 1'), 'sinkbasin 1')


class SkillArgumentTests(unittest.TestCase):
    def test_actor_fills_unbound_arguments_and_types_ground(self):
        from living_library.agents import Agent
        from living_library.domain import State
        from living_library.library import Skill
        skill = Skill('take_object@v1', 'take obj from place', {'obj': 'entity', 'place': 'entity'},
                      [], ['holding(obj)'], 'act(f"take {obj} from {place}")', status='active')
        goal = {'bindings': {'obj': 'mug'}}
        self.assertEqual(Agent._skill_action(skill, goal), 'use skill take_object@v1 obj=mug, place=<place>')
        state = State('On the countertop 1, you see a mug 2.', [], {'mug 1', 'mug 2', 'countertop 1'}, set())
        args = Agent._skill_arguments('use skill take_object@v1 obj=mug, place=countertop 1', skill, goal, state)
        self.assertEqual(args, {'obj': 'mug 2', 'place': 'countertop 1'})
