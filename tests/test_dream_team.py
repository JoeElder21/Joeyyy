"""Structural validation for the dream-team corps expansion roster."""

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
        cls.corps = tomllib.loads(
            (ROOT / "config" / "specialist_corps.toml").read_text(encoding="utf-8")
        )

    def _candidates(self, brain: str) -> list[dict]:
        return self.roster[brain].get("candidates", [])

    def test_every_candidate_is_candidate_stage_and_brain_locked(self) -> None:
        self.assertEqual(self.roster["stage"], "candidate")
        for brain, prefix in (("apex", "apex_"), ("jeos", "jeos_")):
            for candidate in self._candidates(brain):
                self.assertTrue(
                    candidate["id"].startswith(prefix),
                    f"{candidate['id']} violates the {brain} brain lock",
                )
                for forbidden in ("write_targets", "connectors", "routes", "status"):
                    self.assertNotIn(
                        forbidden,
                        candidate,
                        f"candidate {candidate['id']} must not carry {forbidden} before promotion",
                    )

    def test_candidate_ids_are_unique_and_chartered(self) -> None:
        ids = [c["id"] for b in ("apex", "jeos") for c in self._candidates(b)]
        self.assertEqual(len(ids), len(set(ids)))
        for brain in ("apex", "jeos"):
            for candidate in self._candidates(brain):
                self.assertTrue(candidate["charter"].strip())
                self.assertTrue(candidate["name"].strip())
                self.assertTrue(candidate["layer"].strip())

    def test_mentor_classes_are_valid(self) -> None:
        valid = set(self.roster["valid_mentor_classes"])
        for brain in ("apex", "jeos"):
            for candidate in self._candidates(brain):
                self.assertIn(candidate["mentor_class"], valid, candidate["id"])

    def test_existing_rostered_agents_match_the_v21_corps(self) -> None:
        v21_agents = set()
        for key, value in self.corps.items():
            if isinstance(value, dict) and "agents" in value:
                v21_agents.update(value["agents"])
        flat = {
            name
            for name in self._flatten_strings(self.corps)
            if name.startswith(("apex_", "jeos_"))
        }
        known = v21_agents | flat
        for brain in ("apex", "jeos"):
            for name in self.roster[brain]["existing_rostered"]:
                self.assertIn(name, known, f"{name} is not a known v2.1 specialist")

    def test_roster_counts_match_joes_directive(self) -> None:
        # 42 APEX named minus 5 already rostered = 37 candidates; JEOS message
        # truncated after 5 named, 2 already rostered = 3 candidates.
        self.assertEqual(len(self._candidates("apex")), 37)
        self.assertEqual(len(self.roster["apex"]["existing_rostered"]), 5)
        self.assertEqual(len(self._candidates("jeos")), 3)
        self.assertEqual(len(self.roster["jeos"]["existing_rostered"]), 2)

    @classmethod
    def _flatten_strings(cls, value) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [item for v in value.values() for item in cls._flatten_strings(v)]
        if isinstance(value, list):
            return [item for v in value for item in cls._flatten_strings(v)]
        return []


if __name__ == "__main__":
    unittest.main()
