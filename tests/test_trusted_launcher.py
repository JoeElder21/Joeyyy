"""Denial-first tests for the trusted launcher: every refusal path is proven
before any activation path is trusted. Stdlib-only — always runs in CI."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.agent_runtime import AuditLedger
from scripts.trusted_launcher import LaunchDenied, authorize, issue_grant

ROOT = Path(__file__).resolve().parents[1]


class TrustedLauncherTests(unittest.TestCase):
    def _env(self, tmp: str):
        key = Path(tmp) / "launch_key"
        ledger = AuditLedger(Path(tmp) / "launcher.jsonl")
        return key, ledger

    def test_agent_scoped_mount_requires_an_agent_identity(self):
        """The `agents` allowlist was documentation only: authorize() never
        looked at it, so narrowing a mount to one agent changed no runtime
        decision. Launching an agent-scoped mount without an identity must now
        fail closed rather than silently ignoring the allowlist."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants")
            with self.assertRaises(LaunchDenied) as caught:
                authorize("terraform", grant, key_path=key, ledger=ledger)
            self.assertIn("--agent is required", str(caught.exception))

    def test_agent_absent_from_the_allowlist_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants")
            for identity in ("jeos_life_architect", "apex_systems_blacksmith",
                             "not_an_agent"):
                with self.subTest(agent=identity):
                    with self.assertRaises(LaunchDenied) as caught:
                        authorize("terraform", grant, key_path=key,
                                  ledger=ledger, agent=identity)
                    self.assertIn("not on this mount's allowlist",
                                  str(caught.exception))

    def test_denied_identity_is_recorded_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("azure", 30, key_path=key,
                                out_dir=Path(tmp) / "grants")
            with self.assertRaises(LaunchDenied):
                authorize("azure", grant, key_path=key, ledger=ledger,
                          agent="jeos_energy_director")
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            denials = [e for e in entries if e["event"] == "launch_denied"]
            self.assertTrue(denials)
            self.assertEqual(denials[-1]["detail"]["agent"],
                             "jeos_energy_director")

    def test_allowlisted_agent_with_a_valid_grant_is_authorized(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants")
            spec = authorize("terraform", grant, key_path=key, ledger=ledger,
                             agent="apex_chief_of_staff")
            self.assertIn("hashicorp/terraform-mcp-server", " ".join(spec["command"]))
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            granted = [e for e in entries if e["event"] == "launch_authorized"]
            self.assertEqual(granted[-1]["detail"]["agent"],
                             "apex_chief_of_staff")

    def test_wildcard_mount_still_launches_without_an_agent(self):
        """governance is agents = ["*"]; requiring an identity there would break
        the read-only path that needs no grant."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            spec = authorize("governance", None, key_path=key, ledger=ledger)
            self.assertTrue(spec["command"])

    def test_write_capable_mount_is_denied_without_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaisesRegex(LaunchDenied, "requires a signed"):
                authorize("civil3d", None, key, ledger)
            events = [json.loads(l)["event"]
                      for l in ledger.path.read_text().splitlines()]
            self.assertEqual(events, ["launch_denied"])

    def test_unregistered_mount_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaisesRegex(LaunchDenied, "not registered"):
                authorize("shadow_it_server", None, key, ledger)

    def test_tampered_expired_and_reused_grants_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant_path = issue_grant("civil3d", 30, key, Path(tmp), now=1_000_000)

            tampered = json.loads(grant_path.read_text())
            tampered["mount"] = "github"
            bad = Path(tmp) / "tampered.json"
            bad.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(LaunchDenied, "signature invalid"):
                authorize("github", bad, key, ledger, now=1_000_060)

            with self.assertRaisesRegex(LaunchDenied, "expired"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_000 + 31 * 60)

            # civil3d is agent-scoped, so the allowlist check now applies to it
            # too: an identity is required even with a valid grant.
            spec = authorize("civil3d", grant_path, key, ledger, now=1_000_060,
                             agent="apex_chief_of_staff")
            self.assertEqual(spec["name"], "civil3d")
            with self.assertRaisesRegex(LaunchDenied, "already consumed"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_120,
                          agent="apex_chief_of_staff")
            self.assertEqual(ledger.verify(), [])

    def test_grant_for_wrong_mount_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant_path = issue_grant("filesystem", 30, key, Path(tmp), now=2_000_000)
            with self.assertRaisesRegex(LaunchDenied, "is for 'filesystem'"):
                authorize("civil3d", grant_path, key, ledger, now=2_000_060)

    def test_read_only_governance_mount_needs_no_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            spec = authorize("governance", None, key, ledger)
            self.assertEqual(spec["name"], "governance")


if __name__ == "__main__":
    unittest.main()
