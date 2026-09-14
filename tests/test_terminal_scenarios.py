"""Scenario mathematics: one definition of return, probabilities that sum to one."""

import unittest

from terminal import scenarios


class ScenarioTests(unittest.TestCase):
    def test_total_return_formula(self):
        self.assertAlmostEqual(scenarios.total_return(100, 118, distributions=1, costs=0.5), 0.185)
        with self.assertRaises(ValueError):
            scenarios.total_return(0, 10)
        with self.assertRaises(ValueError):
            scenarios.total_return(10, 10, costs=-1)

    def test_probability_weighted_return(self):
        cases = [
            scenarios.Scenario("bear", 0.25, 80.0),
            scenarios.Scenario("base", 0.5, 118.0, 1.0),
            scenarios.Scenario("bull", 0.25, 150.0),
        ]
        result = scenarios.probability_weighted(100.0, cases, costs=0.5)
        self.assertAlmostEqual(result.expected, 0.165)
        self.assertAlmostEqual(result.by_scenario["bear"], -0.205)
        self.assertAlmostEqual(result.worst, -0.205)
        self.assertAlmostEqual(result.best, 0.495)
        self.assertAlmostEqual(result.asymmetry, round(0.495 / 0.205, 4))
        self.assertFalse(scenarios.base_beats_bear(result.by_scenario))
        self.assertTrue(scenarios.base_beats_bear({"base": 0.25, "bear": -0.2}))

    def test_probabilities_are_validated(self):
        with self.assertRaises(ValueError):
            scenarios.probability_weighted(
                100, [scenarios.Scenario("a", 0.6, 1), scenarios.Scenario("b", 0.6, 1)]
            )
        with self.assertRaises(ValueError):
            scenarios.probability_weighted(
                100, [scenarios.Scenario("a", 1.2, 1), scenarios.Scenario("b", -0.2, 1)]
            )
        with self.assertRaises(ValueError):
            scenarios.probability_weighted(
                100, [scenarios.Scenario("a", 0.5, 1), scenarios.Scenario("a", 0.5, 1)]
            )
        with self.assertRaises(ValueError):
            scenarios.probability_weighted(100, [])

    def test_base_must_exceed_bear_loss(self):
        self.assertFalse(scenarios.base_beats_bear({"base": 0.1, "bear": -0.2}))
        with self.assertRaises(KeyError):
            scenarios.base_beats_bear({"base": 0.1})


if __name__ == "__main__":
    unittest.main()
