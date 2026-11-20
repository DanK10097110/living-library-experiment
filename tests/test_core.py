from types import SimpleNamespace
import unittest

from living_library.domain import BudgetExceeded, Episode, Predicate, State
from living_library.environments import MiniWorld, demo_manifest, normalize_alfworld, validate_manifest


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.world = MiniWorld()
        self.world.reset({"id": "test"})
        self.bindings = {"obj": "apple 1", "target": "cabinet 1"}

    def test_simulator_snapshot_restores_state(self):
        before = self.world.snapshot()
        for command in ("take apple 1 from table 1", "go to cabinet 1", "open cabinet 1", "move apple 1 to cabinet 1"):
            self.world.step(command)
        self.assertTrue(self.world.state.won)
        saved = self.world.snapshot()
        self.world.restore(before)
        self.assertFalse(self.world.state.won)
        self.world.restore(saved)
        self.assertTrue(self.world.state.won)

    def test_shared_action_budget_counts_invalid_actions(self):
        episode = Episode(self.world, 1)
        with self.assertRaises(RuntimeError):
            episode.act("fly away")
        with self.assertRaises(BudgetExceeded):
            episode.act("look")
        self.assertEqual(len(episode.trace), 1)

    def test_contracts_cannot_be_free_form(self):
        with self.assertRaises(ValueError):
            Predicate.parse("looks_good(apple)")
        with self.assertRaises(ValueError):
            Predicate.parse("located(apple)")
        self.assertFalse(self.world.state.check(["located(obj, target)"], self.bindings))

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


class LiftedPredicateTests(unittest.TestCase):
    def test_types_match_any_instance(self):
        state = State('On the countertop 1, you see a mug 2.', [], {'mug 1', 'mug 2', 'countertop 1', 'sinkbasin 1'},
                      {('located', 'mug 2', 'countertop 1')})
        self.assertTrue(state.holds(Predicate.parse('located(mug, countertop 1)')))
        self.assertFalse(state.holds(Predicate.parse('located(mug, sinkbasin)')))
        self.assertTrue(state.resolves('mug') and not state.resolves('kettle'))


if __name__ == "__main__":
    unittest.main()
