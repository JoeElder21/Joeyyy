"""Trusted launcher: user-signed, one-time grants for write-capable mounts.

Authority is separated from execution. The launcher — not the agent — holds
the only path to starting a write-capable MCP mount, and it starts one only
when presented a grant that Joe signed. Grants are single-use, short-lived,
mount-specific, and HMAC-signed with a key that lives outside the repository
(created 0600 on first grant). Every authorization and every denial is
appended to the hash-chained audit ledger, so denial is provable history,
not an assumption.

Usage (Joe, on the machine that will run the mount):

    python scripts/trusted_launcher.py grant --mount civil3d --minutes 30
    python scripts/trusted_launcher.py launch --mount civil3d --grant <file>

Mounts marked `require_grant = true` in config/mcp_mounts.toml refuse to
launch without a valid grant. Read-only mounts (e.g. governance) launch
without one. `launch --dry-run` verifies authorization without executing —
the activation proof used by the test suite.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agent_runtime import AuditLedger  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MOUNTS = ROOT / "config" / "mcp_mounts.toml"
DEFAULT_KEY_PATH = Path.home() / ".agent007" / "launch_key"
DEFAULT_LEDGER = ROOT / "audit" / "launcher.jsonl"


class LaunchDenied(Exception):
    """The grant check failed; the mount must not start."""


def _load_mounts() -> dict[str, dict]:
    with MOUNTS.open("rb") as source:
        return {mount["name"]: mount for mount in tomllib.load(source)["mounts"]}


def _load_or_create_key(key_path: Path) -> bytes:
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(secrets.token_bytes(32))
        key_path.chmod(0o600)
    return key_path.read_bytes()


def _sign(key: bytes, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_grant(
    mount: str, minutes: int, key_path: Path = DEFAULT_KEY_PATH,
    out_dir: Path | None = None, now: float | None = None,
) -> Path:
    """Create a signed, single-use grant file for one mount."""
    mounts = _load_mounts()
    if mount not in mounts:
        raise LaunchDenied(f"unknown mount {mount!r}")
    now = now if now is not None else time.time()
    payload = {
        "mount": mount,
        "issued_at": int(now),
        "expires_at": int(now + minutes * 60),
        "nonce": secrets.token_hex(16),
    }
    key = _load_or_create_key(key_path)
    grant = {**payload, "sig": _sign(key, payload)}
    out_dir = out_dir or (key_path.parent / "grants")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"grant-{mount}-{payload['nonce'][:8]}.json"
    path.write_text(json.dumps(grant, indent=1, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path


def _consumed_nonces(ledger: AuditLedger) -> set[str]:
    if not ledger.path.exists():
        return set()
    nonces = set()
    for raw in ledger.path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entry = json.loads(raw)
        if entry.get("event") == "launch_authorized":
            nonce = entry.get("detail", {}).get("nonce")
            if nonce:
                nonces.add(nonce)
    return nonces


def authorize(
    mount: str, grant_path: Path | None,
    key_path: Path = DEFAULT_KEY_PATH,
    ledger: AuditLedger | None = None,
    now: float | None = None,
) -> dict:
    """Fail-closed authorization. Returns the mount spec or raises LaunchDenied."""
    ledger = ledger or AuditLedger(DEFAULT_LEDGER)
    mounts = _load_mounts()

    def deny(reason: str) -> LaunchDenied:
        ledger.append("launch_denied", {"mount": mount, "reason": reason})
        return LaunchDenied(f"launch of {mount!r} denied: {reason}")

    spec = mounts.get(mount)
    if spec is None:
        raise deny("mount is not registered; unlisted mounts are unreachable")
    if not spec.get("require_grant"):
        ledger.append("launch_authorized", {"mount": mount, "grant": "not-required"})
        return spec
    if grant_path is None:
        raise deny("write-capable mount requires a signed one-time grant")
    try:
        grant = json.loads(Path(grant_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise deny(f"grant unreadable: {error}") from error
    payload = {k: grant.get(k) for k in ("mount", "issued_at", "expires_at", "nonce")}
    if not key_path.exists():
        raise deny("no signing key exists; only Joe's machine can mint grants")
    expected = _sign(key_path.read_bytes(), payload)
    if not hmac.compare_digest(expected, str(grant.get("sig", ""))):
        raise deny("grant signature invalid")
    if payload["mount"] != mount:
        raise deny(f"grant is for {payload['mount']!r}, not {mount!r}")
    now = now if now is not None else time.time()
    if now > float(payload["expires_at"]):
        raise deny("grant expired")
    if payload["nonce"] in _consumed_nonces(ledger):
        raise deny("grant already consumed (single-use)")
    ledger.append(
        "launch_authorized",
        {"mount": mount, "nonce": payload["nonce"],
         "expires_at": payload["expires_at"]},
    )
    return spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trusted mount launcher.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="Mint a signed one-time grant (Joe only).")
    g.add_argument("--mount", required=True)
    g.add_argument("--minutes", type=int, default=30)
    l = sub.add_parser("launch", help="Launch a mount under grant control.")
    l.add_argument("--mount", required=True)
    l.add_argument("--grant", type=Path)
    l.add_argument("--dry-run", action="store_true",
                   help="Verify authorization without executing.")
    args = parser.parse_args(argv)

    if args.cmd == "grant":
        path = issue_grant(args.mount, args.minutes)
        print(json.dumps({"grant": str(path), "mount": args.mount,
                          "minutes": args.minutes}))
        return 0

    try:
        spec = authorize(args.mount, args.grant)
    except LaunchDenied as denial:
        print(json.dumps({"authorized": False, "error": str(denial)}))
        return 1
    if args.dry_run:
        print(json.dumps({"authorized": True, "mount": args.mount,
                          "command": spec["command"], "dry_run": True}))
        return 0
    env = dict(**os.environ)
    return subprocess.call(spec["command"], cwd=str(ROOT), env=env)


if __name__ == "__main__":
    sys.exit(main())
