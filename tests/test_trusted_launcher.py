"""Denial-first tests for the trusted launcher: every refusal path is proven
before any activation path is trusted. Stdlib-only — always runs in CI."""

from __future__ import annotations

import json
import time
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

    def test_grant_for_an_agent_scoped_mount_needs_an_identity(self):
        """The identity lives in the signed grant, so it must be supplied when
        the grant is minted -- which only Joe's machine can do."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied) as caught:
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants", ledger=ledger)
            self.assertIn("--agent is required", str(caught.exception))

    def test_grant_cannot_be_minted_for_a_non_allowlisted_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            for identity in ("jeos_life_architect", "apex_systems_blacksmith",
                             "not_an_agent"):
                with self.subTest(agent=identity):
                    with self.assertRaises(LaunchDenied) as caught:
                        issue_grant("terraform", 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent=identity, ledger=ledger)
                    self.assertIn("is not on", str(caught.exception))

    def test_grant_time_denials_reach_the_ledger(self):
        """The module promises every denial is recorded. Grant-time refusals were
        raised directly, so an attempt to mint authority for a shadow specialist
        left no hash-chained evidence -- the very event an audit should surface."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants",
                            agent="apex_systems_blacksmith", ledger=ledger)
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            denials = [e for e in entries if e["event"] == "grant_denied"]
            self.assertTrue(denials, entries)
            self.assertEqual(denials[-1]["detail"]["agent"],
                             "apex_systems_blacksmith")
            self.assertEqual(denials[-1]["detail"]["mount"], "terraform")
            self.assertEqual(ledger.verify(), [])

    def test_caller_cannot_claim_an_identity_it_was_not_granted(self):
        """The whole point of signing the identity. An earlier version read it
        from a CLI flag, so any holder of a valid grant could assert Agent 007."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            with self.assertRaises(LaunchDenied) as caught:
                authorize("terraform", grant, key_path=key, ledger=ledger,
                          agent="apex_systems_blacksmith")
            self.assertIn("grant authorizes", str(caught.exception))

    def test_editing_the_identity_in_a_grant_breaks_its_signature(self):
        """The agent field is inside the HMAC payload, so tampering is caught by
        the signature check rather than by trusting the file."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("azure", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            body = json.loads(grant.read_text())
            body["agent"] = "apex_systems_blacksmith"
            tampered = Path(tmp) / "tampered.json"
            tampered.write_text(json.dumps(body))
            with self.assertRaisesRegex(LaunchDenied, "signature invalid"):
                authorize("azure", tampered, key_path=key, ledger=ledger)

    def test_denied_identity_is_recorded_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("azure", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
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

    def test_signed_identity_authorizes_and_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            spec = authorize("terraform", grant, key_path=key, ledger=ledger)
            self.assertIn("hashicorp/terraform-mcp-server", " ".join(spec["command"]))
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            granted = [e for e in entries if e["event"] == "launch_authorized"]
            self.assertEqual(granted[-1]["detail"]["agent"],
                             "apex_chief_of_staff")

    def test_agent_scoped_mounts_all_require_a_grant(self):
        """A non-wildcard mount that skipped grants would fall back to an
        unauthenticated caller-supplied identity. This invariant keeps the
        signed path the only path for every agent-scoped mount."""
        import tomllib
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            for mount in tomllib.load(source)["mounts"]:
                if "*" in mount.get("agents", []):
                    continue
                with self.subTest(mount=mount["name"]):
                    self.assertTrue(
                        mount.get("require_grant"),
                        f"{mount['name']} is agent-scoped but grant-free, so its "
                        "identity would be unauthenticated",
                    )

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
            grant_path = issue_grant("civil3d", 30, key, Path(tmp), now=1_000_000,
                                     agent="apex_chief_of_staff")

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
            spec = authorize("civil3d", grant_path, key, ledger, now=1_000_060)
            self.assertEqual(spec["name"], "civil3d")
            with self.assertRaisesRegex(LaunchDenied, "already consumed"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_120)
            self.assertEqual(ledger.verify(), [])

    def test_grant_for_wrong_mount_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant_path = issue_grant("filesystem", 30, key, Path(tmp), now=2_000_000,
                                     agent="apex_chief_of_staff")
            with self.assertRaisesRegex(LaunchDenied, "is for 'filesystem'"):
                authorize("civil3d", grant_path, key, ledger, now=2_000_060)

    def test_read_only_governance_mount_needs_no_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            spec = authorize("governance", None, key, ledger)
            self.assertEqual(spec["name"], "governance")


    def test_post_signature_denials_name_the_signed_identity(self):
        """--agent is optional at launch. Once the signature verifies, the
        signed identity is known, so an expired or already-consumed grant must
        be attributed to it -- otherwise the audit cannot say which authorized
        identity presented a stale grant."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff", ledger=ledger)

            # Expired: launched without --agent, so only the signature knows.
            with self.assertRaises(LaunchDenied):
                authorize("terraform", grant, key_path=key, ledger=ledger,
                          now=time.time() + 10_000)
            # Consumed: authorize once, then replay, again without --agent.
            authorize("terraform", grant, key_path=key, ledger=ledger)
            with self.assertRaises(LaunchDenied):
                authorize("terraform", grant, key_path=key, ledger=ledger)

            denials = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line)["event"] == "launch_denied"
            ]
            reasons = {d["detail"]["reason"] for d in denials}
            self.assertTrue(any("expired" in r for r in reasons), reasons)
            self.assertTrue(any("consumed" in r for r in reasons), reasons)
            for denial in denials:
                with self.subTest(reason=denial["detail"]["reason"]):
                    self.assertEqual(
                        denial["detail"].get("agent"), "apex_chief_of_staff")
                    self.assertEqual(
                        denial["detail"].get("agent_source"), "signed-grant")

    def test_denials_never_touch_the_machine_local_ledger(self):
        """Synthetic denials must not contaminate the evidence they validate.
        Exercises the denial paths with an explicit temporary ledger and asserts
        the real audit/launcher.jsonl is byte-for-byte unchanged -- a missing
        `ledger` argument silently falls back to it."""
        from scripts.trusted_launcher import DEFAULT_LEDGER

        before = (DEFAULT_LEDGER.read_bytes()
                  if DEFAULT_LEDGER.exists() else None)
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants", ledger=ledger)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants",
                            agent="jeos_life_architect", ledger=ledger)
            with self.assertRaises(LaunchDenied):
                authorize("terraform", None, key_path=key, ledger=ledger)
            self.assertTrue(ledger.path.exists(), "temp ledger took the writes")
        after = (DEFAULT_LEDGER.read_bytes()
                 if DEFAULT_LEDGER.exists() else None)
        self.assertEqual(before, after,
                         "a denial path wrote to the machine-local ledger")


if __name__ == "__main__":
    unittest.main()
