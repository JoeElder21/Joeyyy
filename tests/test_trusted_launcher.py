"""Denial-first tests for the trusted launcher: every refusal path is proven
before any activation path is trusted. Stdlib-only — always runs in CI.

Tests both runtime/trusted_launcher.py (library) and scripts/trusted_launcher.py (CLI).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from runtime.trusted_launcher import GrantDeniedError, TrustedLauncher, sign_claims
from scripts.agent_runtime import AuditLedger
from scripts.trusted_launcher import LaunchDenied, authorize, issue_grant

ROOT = Path(__file__).resolve().parents[1]


def build_grant(
    *,
    grant_id: str,
    tool_id: str,
    operation: str,
    issued_at: datetime,
    expires_at: datetime,
    secret: str,
    subject: str = "agent007-launcher",
) -> dict:
    claims = {
        "grant_id": grant_id,
        "subject": subject,
        "tool_id": tool_id,
        "operation": operation,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "nonce": f"nonce-{grant_id}",
        "purpose": "bounded validation",
    }
    return {"claims": claims, "signature": sign_claims(claims, secret)}


class RuntimeTrustedLauncherTests(unittest.TestCase):
    """Tests for runtime/trusted_launcher.py (library)."""
    
    def setUp(self):
        self.secret = "test-secret"
        self.now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        self.tempdir = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.tempdir.name) / "ledger.json"
        self.launcher = TrustedLauncher(
            {
                "civil3d-mcp": {
                    "manual_synthetic_dwg_trial": ("echo", "ok"),
                }
            },
            ledger_path=self.ledger_path,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_prove_denial_blocks_missing_grant(self):
        self.assertEqual(
            self.launcher.prove_denial("civil3d-mcp", "manual_synthetic_dwg_trial"),
            "denied: missing signed one-time grant",
        )

    def test_valid_grant_launches_once_then_denies_replay(self):
        grant = build_grant(
            grant_id="grant-1",
            tool_id="civil3d-mcp",
            operation="manual_synthetic_dwg_trial",
            issued_at=self.now - timedelta(minutes=2),
            expires_at=self.now + timedelta(minutes=2),
            secret=self.secret,
        )
        result = self.launcher.launch(grant, secret=self.secret, now=self.now, dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.grant_id, "grant-1")

        with self.assertRaisesRegex(GrantDeniedError, "already consumed"):
            self.launcher.launch(grant, secret=self.secret, now=self.now, dry_run=True)

    def test_invalid_signature_is_denied(self):
        grant = build_grant(
            grant_id="grant-2",
            tool_id="civil3d-mcp",
            operation="manual_synthetic_dwg_trial",
            issued_at=self.now - timedelta(minutes=2),
            expires_at=self.now + timedelta(minutes=2),
            secret=self.secret,
        )
        grant["signature"] = "bad"
        with self.assertRaisesRegex(GrantDeniedError, "invalid"):
            self.launcher.launch(grant, secret=self.secret, now=self.now, dry_run=True)

    def test_unknown_tool_or_operation_is_denied(self):
        unknown_tool = build_grant(
            grant_id="grant-3",
            tool_id="not-allowed",
            operation="manual_synthetic_dwg_trial",
            issued_at=self.now - timedelta(minutes=2),
            expires_at=self.now + timedelta(minutes=2),
            secret=self.secret,
        )
        with self.assertRaisesRegex(GrantDeniedError, "not allowlisted"):
            self.launcher.launch(unknown_tool, secret=self.secret, now=self.now, dry_run=True)

        wrong_operation = build_grant(
            grant_id="grant-4",
            tool_id="civil3d-mcp",
            operation="write_anything",
            issued_at=self.now - timedelta(minutes=2),
            expires_at=self.now + timedelta(minutes=2),
            secret=self.secret,
        )
        with self.assertRaisesRegex(GrantDeniedError, "not allowlisted"):
            self.launcher.launch(wrong_operation, secret=self.secret, now=self.now, dry_run=True)

    def test_expired_or_oversized_lifetime_is_denied(self):
        expired = build_grant(
            grant_id="grant-5",
            tool_id="civil3d-mcp",
            operation="manual_synthetic_dwg_trial",
            issued_at=self.now - timedelta(minutes=10),
            expires_at=self.now - timedelta(minutes=1),
            secret=self.secret,
        )
        with self.assertRaisesRegex(GrantDeniedError, "expired"):
            self.launcher.launch(expired, secret=self.secret, now=self.now, dry_run=True)

        too_long = build_grant(
            grant_id="grant-6",
            tool_id="civil3d-mcp",
            operation="manual_synthetic_dwg_trial",
            issued_at=self.now - timedelta(minutes=1),
            expires_at=self.now + timedelta(hours=2),
            secret=self.secret,
        )
        with self.assertRaisesRegex(GrantDeniedError, "lifetime exceeds"):
            self.launcher.launch(too_long, secret=self.secret, now=self.now, dry_run=True)


class ScriptsTrustedLauncherTests(unittest.TestCase):
    """Tests for scripts/trusted_launcher.py (CLI tool for MCP mounts)."""
    
    def _env(self, tmp: str):
        key = Path(tmp) / "launch_key"
        ledger = AuditLedger(Path(tmp) / "launcher.jsonl")
        return key, ledger

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

            spec = authorize("civil3d", grant_path, key, ledger, now=1_000_060)
            self.assertEqual(spec["name"], "civil3d")
            with self.assertRaisesRegex(LaunchDenied, "already consumed"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_120)
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


class LedgerDurabilityTests(unittest.TestCase):
    """A torn ledger write bricks every future launch, so the write must be atomic."""

    def test_consume_grant_replaces_the_ledger_atomically(self):
        import inspect

        from runtime.trusted_launcher import TrustedLauncher

        source = inspect.getsource(TrustedLauncher._consume_grant_id)
        self.assertIn("os.replace", source)
        self.assertIn("os.fsync", source)
        # The real path must never be opened for writing directly.
        self.assertNotIn("self.ledger_path.write_text", source)

    def test_no_temp_files_are_left_behind_after_a_successful_consume(self):
        import tempfile as _tempfile
        from pathlib import Path as _Path

        from runtime.trusted_launcher import TrustedLauncher

        with _tempfile.TemporaryDirectory() as tmp:
            ledger = _Path(tmp) / "grants.json"
            launcher = TrustedLauncher.__new__(TrustedLauncher)
            launcher.ledger_path = ledger
            launcher._consume_grant_id("grant-1")
            launcher._consume_grant_id("grant-2")

            import json as _json

            payload = _json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(payload["used_grants"], ["grant-1", "grant-2"])
            # Claim markers are the exclusive on-disk claim and are meant to
            # persist; what must not survive is a partial ledger write.
            leftovers = [
                p.name
                for p in _Path(tmp).iterdir()
                if p.name != "grants.json" and not p.name.startswith(".grants.json.claim-")
            ]
            self.assertEqual(leftovers, [])


class LauncherFailClosedTests(unittest.TestCase):
    def _launcher(self, tmp, catalog=None):
        from pathlib import Path as _P

        from runtime.trusted_launcher import TrustedLauncher

        return TrustedLauncher(catalog, ledger_path=_P(tmp) / "grants.json")

    def test_explicitly_empty_catalog_stays_empty(self):
        """An empty catalog is a deliberate fail-closed configuration."""
        import tempfile as _t

        with _t.TemporaryDirectory() as tmp:
            launcher = self._launcher(tmp, {})
            self.assertEqual(launcher.tool_catalog, {})
            self.assertIn("unknown tool operation", launcher.prove_denial("civil3d-mcp", "version"))

    def test_default_catalog_still_loads_when_omitted(self):
        import tempfile as _t

        with _t.TemporaryDirectory() as tmp:
            self.assertIn("civil3d-mcp", self._launcher(tmp).tool_catalog)

    def test_malformed_ledger_denies_instead_of_reading_as_empty(self):
        import json as _j
        import tempfile as _t
        from pathlib import Path as _P

        from runtime.trusted_launcher import GrantDeniedError

        for corrupt in ({}, {"used_grants": "nope"}, {"used_grants": [1, 2]}, []):
            with self.subTest(corrupt=corrupt), _t.TemporaryDirectory() as tmp:
                ledger = _P(tmp) / "grants.json"
                ledger.write_text(_j.dumps(corrupt), encoding="utf-8")
                launcher = self._launcher(tmp)
                with self.assertRaises(GrantDeniedError):
                    launcher._used_grants()

    def test_a_second_process_cannot_claim_the_same_grant(self):
        import tempfile as _t

        from runtime.trusted_launcher import GrantDeniedError

        with _t.TemporaryDirectory() as tmp:
            launcher = self._launcher(tmp)
            launcher._claim_grant_exclusively("grant-x")
            with self.assertRaises(GrantDeniedError):
                launcher._claim_grant_exclusively("grant-x")

    def test_executables_resolve_to_absolute_paths(self):
        import tempfile as _t

        from runtime.trusted_launcher import GrantDeniedError, TrustedLauncher

        resolved = TrustedLauncher._resolved_command(("python3", "--version"))
        self.assertTrue(resolved[0].startswith("/"))
        with self.assertRaises(GrantDeniedError):
            TrustedLauncher._resolved_command(("definitely-not-a-real-binary-xyz",))
