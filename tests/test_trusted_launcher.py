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
