"""The tiered universe and its bounded research budget."""

import unittest

from terminal import universe


class UniverseTests(unittest.TestCase):
    def test_highest_tier_wins(self):
        assignment = universe.assign({"a"}, {"a", "b"}, {"b", "c"}, {"c", "d", "a"})
        self.assertEqual(assignment.tiers, {"a": "T1", "b": "T2", "c": "T3", "d": "T4"})
        self.assertEqual(assignment.counts, {"T1": 1, "T2": 1, "T3": 1, "T4": 1})
        self.assertEqual(assignment.members("T2"), ["b"])

    def test_budget_batches_are_bounded_and_non_empty(self):
        assignment = universe.assign({f"o{i}" for i in range(9)}, set(), set(), {"m1"})
        plan = universe.research_budget(assignment, {"T1": 4})
        self.assertEqual(plan["T1"]["slots"], 4)
        self.assertEqual(sum(len(b) for b in plan["T1"]["batches"]), 9)
        self.assertTrue(all(plan["T1"]["batches"]))
        self.assertEqual(plan["T2"]["batches"], [])
        self.assertEqual(plan["T4"]["assets"], 1)


if __name__ == "__main__":
    unittest.main()
