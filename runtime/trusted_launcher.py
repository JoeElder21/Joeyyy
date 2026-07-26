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
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / ".state" / "trusted_launcher_ledger.json"

# Fixed search path for allowlisted executables.
#
# Resolving through the inherited PATH — even to an absolute path — still lets
# whoever controls the environment choose the binary a signed grant executes.
# The grant authorizes a tool, not "whatever is first on PATH", so resolution
# ignores the environment entirely.
TRUSTED_BIN_DIRS = (
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/local/sbin"),
    Path("/usr/sbin"),
    Path("/sbin"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str, field: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


class GrantDeniedError(ValueError):
    """Raised when a launch request violates trusted-launcher policy."""


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


MIN_SECRET_LENGTH = 16


def _require_secret(secret: str) -> str:
    """Refuse an absent or trivially guessable signing secret.

    A missing environment variable defaulted to "" would otherwise still produce
    a valid HMAC, so anyone could mint a grant for an allowlisted operation.
    """
    if not isinstance(secret, str) or not secret.strip():
        raise GrantDeniedError("launcher signing secret is empty")
    if len(secret) < MIN_SECRET_LENGTH:
        raise GrantDeniedError(
            f"launcher signing secret must be at least {MIN_SECRET_LENGTH} characters"
        )
    return secret


def sign_claims(claims: dict[str, Any], secret: str) -> str:
    _require_secret(secret)
    digest = hmac.new(secret.encode("utf-8"), _canonical_json(claims).encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


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
        # `or` treated an explicitly empty catalog as absent and silently
        # restored the built-in tools, granting capabilities the caller removed.
        self.tool_catalog = tool_catalog if tool_catalog is not None else {
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
            self._resolved_command(command),
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

        non_string_fields = sorted(f for f in required if f in claims and not isinstance(claims[f], str))
        if non_string_fields:
            raise GrantDeniedError(f"grant claims fields must be strings: {non_string_fields}")

        _require_secret(secret)
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

        try:
            issued_at = _parse_timestamp(claims["issued_at"], "claims.issued_at")
        except (ValueError, TypeError) as exc:
            raise GrantDeniedError(f"invalid issued_at timestamp: {exc}") from exc
        try:
            expires_at = _parse_timestamp(claims["expires_at"], "claims.expires_at")
        except (ValueError, TypeError) as exc:
            raise GrantDeniedError(f"invalid expires_at timestamp: {exc}") from exc
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

    @staticmethod
    def _resolved_command(command: tuple[str, ...]) -> list[str]:
        """Resolve the executable to an absolute path before running it.

        A signed grant authorizes a tool and operation, not "whatever binary
        happens to be first on the caller's PATH". Passing a bare name such as
        `node` lets a modified environment turn an allowlisted version check
        into arbitrary code execution.
        """
        resolved = list(command)
        executable = resolved[0]
        if Path(executable).is_absolute():
            if not Path(executable).is_file():
                raise GrantDeniedError(f"allowlisted executable not found: {executable}")
            return resolved
        for directory in TRUSTED_BIN_DIRS:
            candidate = directory / executable
            if candidate.is_file():
                resolved[0] = str(candidate)
                return resolved
        raise GrantDeniedError(
            f"allowlisted executable {executable!r} was not found in the trusted "
            f"bin directories {[str(d) for d in TRUSTED_BIN_DIRS]}; PATH is "
            "deliberately not consulted"
        )

    def _used_grants(self) -> set[str]:
        if not self.ledger_path.exists():
            return set()
        try:
            content = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise GrantDeniedError(f"ledger read/parse failure: {exc}") from exc
        if not isinstance(content, dict) or "used_grants" not in content:
            raise GrantDeniedError("ledger is malformed: missing used_grants")
        used = content["used_grants"]
        if not isinstance(used, list) or any(not isinstance(item, str) for item in used):
            # Silently dropping unreadable entries would let anyone who can edit
            # the ledger corrupt one consumed id and replay a captured grant.
            raise GrantDeniedError("ledger is malformed: used_grants must be a list of strings")
        return set(used)

    def _claim_grant_exclusively(self, grant_id: str) -> None:
        """Take an exclusive on-disk claim before consuming the grant.

        Validation and consumption were two separate steps, so two concurrent
        processes could both pass the replay check before either wrote the
        ledger and both execute a one-time grant. An O_EXCL claim file makes the
        winner unambiguous; the loser is denied.
        """
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        claim = self.ledger_path.parent / f".{self.ledger_path.name}.claim-{grant_id}"
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise GrantDeniedError("grant_id is already being consumed") from exc
        os.close(fd)

    def _consume_grant_id(self, grant_id: str) -> None:
        """Record a consumed grant, replacing the ledger atomically.

        A torn write here is unrecoverable rather than merely inconvenient:
        ``_used_grants()`` raises ``GrantDeniedError`` on a parse failure, so a
        half-written ledger fails every subsequent launch closed until a human
        repairs the file by hand. Writing to a temp file in the same directory
        and calling ``os.replace`` means a reader sees either the old ledger or
        the new one, never a partial one.
        """
        self._claim_grant_exclusively(grant_id)
        used = self._used_grants()
        used.add(grant_id)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"used_grants": sorted(used)}, indent=2)

        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.ledger_path.parent,
            prefix=f".{self.ledger_path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.ledger_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise


__all__ = [
    "GrantDeniedError",
    "LaunchResult",
    "TrustedLauncher",
    "sign_claims",
]
