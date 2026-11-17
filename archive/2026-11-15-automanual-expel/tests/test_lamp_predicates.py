"""Regression for real ALFWorld light-task facts; no simulator required."""
from types import SimpleNamespace
import unittest

from living_library.environments import normalize_alfworld


class LampPredicateTests(unittest.TestCase):
    def test_toggle_history_is_not_current_power_or_victory(self):
        def fact(name, obj):
            return SimpleNamespace(name=name, arguments=[
                SimpleNamespace(name=obj, type="object")])

        raw = {"feedback": "You turn on the desklamp 1.", "won": True,
               "admissible_commands": [], "facts": [
                   fact("istoggled", "desklamp 1"),
                   fact("not_ison", "desklamp 1"),
                   fact("ison", "desklamp 2")]}
        state = normalize_alfworld(raw)
        self.assertTrue(state.check(["is_toggled(desklamp 1)"]))
        self.assertFalse(state.check(["is_on(desklamp 1)"]))
        self.assertTrue(state.check(["is_on(desklamp 2)"]))
        self.assertFalse(state.check(["is_toggled(desklamp 2)"]))
        raw["facts"] = []
        state = normalize_alfworld(raw)
        self.assertTrue(state.won)
        self.assertFalse(state.check(["is_toggled(desklamp 1)"]))
        self.assertFalse(state.check(["is_on(desklamp 1)"]))
