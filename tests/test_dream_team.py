"""Structural validation for the dream-team charter-mode roster."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DreamTeamRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.roster = tomllib.loads(
            (ROOT / "config" / "dream_team_roster.toml").read_text(encoding="utf-8")
        )
        cls.brains = {
            brain: tomllib.loads(
                (ROOT / "brains" / brain / "agents.toml").read_text(encoding="utf-8")
            )
            for brain in ("apex", "jeos")
        }

    def _modes(self, brain: str) -> list[dict]:
        return self.roster[brain].get("charter_modes", [])

    def test_roster_kind_is_charter_mode_not_agent(self) -> None:
        self.assertEqual(self.roster["kind"], "charter_mode")
        for brain in ("apex", "jeos"):
            self.assertNotIn("candidates", self.roster[brain])

    def test_every_charter_mode_is_brain_locked_to_its_owner(self) -> None:
        for brain, prefix in (("apex", "apex_"), ("jeos", "jeos_")):
            rostered = set(self.brains[brain]["roster"])
            for mode in self._modes(brain):
                self.assertTrue(
                    mode["owner_agent"].startswith(prefix),
                    f"{mode['mode']} owner violates the {brain} brain lock",
                )
                self.assertIn(
                    mode["owner_agent"],
                    rostered,
                    f"{mode['mode']} owner is not a rostered {brain} specialist",
                )
                for forbidden in ("write_targets", "connectors", "routes", "status"):
                    self.assertNotIn(
                        forbidden,
                        mode,
                        f"charter mode {mode['mode']} must not carry {forbidden}",
                    )

    def test_owner_class_matches_the_owning_specialist(self) -> None:
        valid = set(self.roster["valid_owner_classes"])
        for brain in ("apex", "jeos"):
            agents = self.brains[brain]["agents"]
            for mode in self._modes(brain):
                self.assertIn(mode["owner_class"], valid, mode["mode"])
                owner = agents[mode["owner_agent"]]
                self.assertEqual(
                    owner["class_id"],
                    mode["owner_class"],
                    f"{mode['mode']} owner_class does not match {mode['owner_agent']}",
                )

    def test_mode_ids_are_unique_and_chartered(self) -> None:
        ids = [m["mode"] for b in ("apex", "jeos") for m in self._modes(b)]
        self.assertEqual(len(ids), len(set(ids)))
        for brain in ("apex", "jeos"):
            existing_contract_modes = {
                contract_mode
                for agent in self.brains[brain]["agents"].values()
                for contract_mode in agent.get("modes", [])
            }
            for mode in self._modes(brain):
                self.assertTrue(mode["charter"].strip())
                self.assertTrue(mode["name"].strip())
                self.assertTrue(mode["layer"].strip())
                self.assertNotIn(
                    mode["mode"],
                    existing_contract_modes,
                    f"{mode['mode']} collides with a v2.1 contract mode",
                )

    def test_existing_rostered_agents_match_the_v21_corps(self) -> None:
        for brain in ("apex", "jeos"):
            rostered = set(self.brains[brain]["roster"])
            for name in self.roster[brain]["existing_rostered"]:
                self.assertIn(name, rostered, f"{name} is not a rostered v2.1 specialist")

    def test_roster_counts_match_joes_directive(self) -> None:
        # 42 APEX named minus 5 that are v2.1 specialists = 37 charter modes;
        # JEOS message truncated after 5 named, 2 already specialists = 3 modes.
        self.assertEqual(len(self._modes("apex")), 37)
        self.assertEqual(len(self.roster["apex"]["existing_rostered"]), 5)
        self.assertEqual(len(self._modes("jeos")), 3)
        self.assertEqual(len(self.roster["jeos"]["existing_rostered"]), 2)


if __name__ == "__main__":
    unittest.main()
