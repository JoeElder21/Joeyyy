"""Regression tests for the AutoGen challenge-pair preflight."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import autogen_challenge_pair  # noqa: E402
sys.path.pop(0)


class AutoGenChallengePairTests(unittest.TestCase):
    def test_registered_apex_pair_creates_connector_isolated_plan(self) -> None:
        plan = autogen_challenge_pair.build_plan(
            "APEX",
            ["apex_war_architect", "apex_intelligence_forge"],
            "synthetic-autogen-preflight",
            ["synthetic://apex/challenge-input"],
        )
        self.assertEqual(plan["execution_state"], "preflight_only")
        self.assertEqual(plan["tool_access"], "none")
        self.assertFalse(plan["external_actions_performed"])

    def test_cross_brain_pair_is_rejected(self) -> None:
        with self.assertRaises(autogen_challenge_pair.ChallengePlanError):
            autogen_challenge_pair.build_plan(
                "APEX",
                ["apex_war_architect", "jeos_life_architect"],
                "synthetic-cross-brain-rejection",
                ["synthetic://apex/input"],
            )

    def test_unregistered_pair_is_rejected(self) -> None:
        with self.assertRaises(autogen_challenge_pair.ChallengePlanError):
            autogen_challenge_pair.build_plan(
                "APEX",
                ["apex_war_architect", "apex_systems_blacksmith"],
                "synthetic-unregistered-pair",
                ["synthetic://apex/input"],
            )


if __name__ == "__main__":
    unittest.main()
