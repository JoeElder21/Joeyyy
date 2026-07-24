"""Trusted launcher for constrained external-tool execution.

The launcher separates authority (signed, one-time grant) from execution
(predefined tool catalog). It denies by default, consumes each grant once,
and records replay prevention in a local ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / ".state" / "trusted_launcher_ledger.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str, field: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_claims(claims: dict[str, Any], secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), _canonical_json(claims).encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


class GrantDeniedError(ValueError):
    """Raised when a launch request violates trusted-launcher policy."""


@dataclass(frozen=True)
class LaunchResult:
    grant_id: str
    tool_id: str
    operation: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    executed_at: str
    dry_run: bool


class TrustedLauncher:
    """Launch only approved catalog operations with one-time signed grants."""

    def __init__(
        self,
        tool_catalog: dict[str, dict[str, tuple[str, ...]]] | None = None,
        *,
        ledger_path: Path = DEFAULT_LEDGER,
        max_grant_lifetime: timedelta = timedelta(minutes=30),
        expected_subject: str = "agent007-launcher",
    ):
        self.tool_catalog = tool_catalog or {
            "civil3d-mcp": {
                "version": ("node", "--version"),
                "manual_synthetic_dwg_trial": ("echo", "manual Civil 3D trial must run on workstation"),
            },
            "codex-autorunner": {
                "version": ("car", "--version"),
            },
            "multica": {
                "version": ("multica", "version"),
            },
        }
        self.ledger_path = ledger_path
        self.max_grant_lifetime = max_grant_lifetime
        self.expected_subject = expected_subject

    def prove_denial(self, tool_id: str, operation: str) -> str:
        if tool_id not in self.tool_catalog or operation not in self.tool_catalog[tool_id]:
            return "denied: unknown tool operation"
        return "denied: missing signed one-time grant"

    def launch(
        self,
        grant_packet: dict[str, Any],
        *,
        secret: str,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> LaunchResult:
        current = now or _utcnow()
        claims = self._validate_and_resolve_claims(grant_packet, secret, current)
        command = self.tool_catalog[claims["tool_id"]][claims["operation"]]
        self._consume_grant_id(claims["grant_id"])

        if dry_run:
            return LaunchResult(
                grant_id=claims["grant_id"],
                tool_id=claims["tool_id"],
                operation=claims["operation"],
                command=command,
                returncode=None,
                stdout="",
                stderr="",
                executed_at=current.isoformat(),
                dry_run=True,
            )

        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
        return LaunchResult(
            grant_id=claims["grant_id"],
            tool_id=claims["tool_id"],
            operation=claims["operation"],
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            executed_at=current.isoformat(),
            dry_run=False,
        )

    def _validate_and_resolve_claims(
        self,
        grant_packet: dict[str, Any],
        secret: str,
        now: datetime,
    ) -> dict[str, Any]:
        if not isinstance(grant_packet, dict):
            raise GrantDeniedError("grant packet must be a JSON object")
        claims = grant_packet.get("claims")
        signature = grant_packet.get("signature")
        if not isinstance(claims, dict) or not isinstance(signature, str):
            raise GrantDeniedError("grant packet requires claims and signature")

        required = {
            "grant_id",
            "subject",
            "tool_id",
            "operation",
            "issued_at",
            "expires_at",
            "nonce",
            "purpose",
        }
        missing = sorted(field for field in required if field not in claims)
        if missing:
            raise GrantDeniedError(f"grant claims missing required fields: {missing}")

        expected_signature = sign_claims(claims, secret)
        if not hmac.compare_digest(signature, expected_signature):
            raise GrantDeniedError("grant signature is invalid")

        if claims["subject"] != self.expected_subject:
            raise GrantDeniedError("grant subject does not match trusted launcher")

        tool_id = claims["tool_id"]
        operation = claims["operation"]
        if tool_id not in self.tool_catalog:
            raise GrantDeniedError(f"tool {tool_id!r} is not allowlisted")
        if operation not in self.tool_catalog[tool_id]:
            raise GrantDeniedError(f"operation {operation!r} is not allowlisted for {tool_id!r}")

        issued_at = _parse_timestamp(claims["issued_at"], "claims.issued_at")
        expires_at = _parse_timestamp(claims["expires_at"], "claims.expires_at")
        if expires_at <= issued_at:
            raise GrantDeniedError("grant expires_at must be after issued_at")
        if expires_at - issued_at > self.max_grant_lifetime:
            raise GrantDeniedError("grant lifetime exceeds launcher limit")
        if now < issued_at:
            raise GrantDeniedError("grant is not yet valid")
        if now > expires_at:
            raise GrantDeniedError("grant is expired")

        if claims["grant_id"] in self._used_grants():
            raise GrantDeniedError("grant_id already consumed")

        return claims

    def _used_grants(self) -> set[str]:
        if not self.ledger_path.exists():
            return set()
        content = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        used = content.get("used_grants", [])
        return {item for item in used if isinstance(item, str)}

    def _consume_grant_id(self, grant_id: str) -> None:
        used = self._used_grants()
        used.add(grant_id)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"used_grants": sorted(used)}
        self.ledger_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


__all__ = [
    "GrantDeniedError",
    "LaunchResult",
    "TrustedLauncher",
    "sign_claims",
]
