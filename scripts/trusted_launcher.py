"""Trusted launcher: user-signed, one-time grants for write-capable mounts.

Authority is separated from execution. The launcher — not the agent — holds
the only path to starting a write-capable MCP mount, and it starts one only
when presented a grant that Joe signed. Grants are single-use, short-lived,
mount-specific, and HMAC-signed with a key that lives outside the repository
(created 0600 on first grant). Every authorization and every denial is
appended to the hash-chained audit ledger, so denial is provable history,
not an assumption.

Usage (Joe, on the machine that will run the mount):

    python scripts/trusted_launcher.py grant --mount civil3d --minutes 30 \
        --agent apex_chief_of_staff
    python scripts/trusted_launcher.py launch --mount civil3d --grant <file>

The authorized identity is signed into the grant, so a caller cannot claim an
identity it was not granted -- forging one needs the signing key. It is checked
against that mount's `agents` allowlist in config/mcp_mounts.toml (mounts
allowing "*" are exempt). Every denial is recorded with the rejected identity.

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
    agent: str | None = None, ledger: AuditLedger | None = None,
) -> Path:
    """Create a signed, single-use grant file for one mount and one identity.

    The agent is part of the signed payload. A caller cannot claim an identity
    it was not granted, because forging one requires the signing key -- which
    lives outside the repository and only exists on Joe's machine. An earlier
    version read the identity from a CLI flag at launch time, which any caller
    holding a valid grant could set to anything.
    """
    ledger = ledger or AuditLedger(DEFAULT_LEDGER)
    mounts = _load_mounts()

    def refuse(reason: str) -> LaunchDenied:
        # The module promises that every denial is recorded. Grant-time refusals
        # are the ones worth keeping most: an attempt to mint authority for a
        # shadow specialist is exactly the event an audit should surface.
        detail = {"mount": mount, "reason": reason}
        if agent is not None:
            detail["agent"] = agent
        ledger.append("grant_denied", detail)
        return LaunchDenied(reason)

    if mount not in mounts:
        raise refuse(f"unknown mount {mount!r}")

    allowed = mounts[mount].get("agents", [])
    if "*" not in allowed:
        if agent is None:
            raise refuse(
                f"mount {mount!r} is agent-scoped; --agent is required when "
                f"minting the grant (allowed: {', '.join(allowed) or 'none'})"
            )
        if agent not in allowed:
            raise refuse(
                f"agent {agent!r} is not on {mount!r}'s allowlist "
                f"({', '.join(allowed) or 'none'})"
            )

    now = now if now is not None else time.time()
    payload = {
        "mount": mount,
        "agent": agent,
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
    agent: str | None = None,
    authorized: dict | None = None,
) -> dict:
    """Fail-closed authorization. Returns the mount spec or raises LaunchDenied.

    For a grant-gated mount the authoritative identity is the one signed into
    the grant; `agent` is only an optional cross-check and a mismatch is refused.
    The allowlist is the executable half of `packet_only_no_direct_connectors`:
    it was documentation only until this check existed, and then briefly relied
    on a caller-supplied flag any grant holder could set to anything.
    """
    ledger = ledger or AuditLedger(DEFAULT_LEDGER)
    mounts = _load_mounts()
    authorized = {} if authorized is None else authorized

    # Set once the grant's signature verifies. From that point the signed
    # identity is authoritative and is what the ledger must attribute a denial
    # to: --agent is optional, so without this an expired or reused grant from a
    # correctly signed identity would be recorded with no agent at all, and the
    # audit could not tell which authorized identity presented it.
    verified_identity: dict[str, str | None] = {"agent": None}

    def deny(reason: str) -> LaunchDenied:
        detail = {"mount": mount, "reason": reason}
        signed = verified_identity["agent"]
        # A caller-supplied --agent is recorded as-is: a mismatched claim is
        # itself the forensically interesting fact. The signed identity only
        # fills in when the caller supplied none, which is the documented launch
        # command -- without it, an expired or reused grant from a correctly
        # signed identity would reach the ledger attributed to nobody.
        if agent is not None:
            detail["agent"] = agent
            detail["agent_source"] = "caller-supplied"
            if signed is not None and signed != agent:
                detail["agent_signed"] = signed
        elif signed is not None:
            detail["agent"] = signed
            detail["agent_source"] = "signed-grant"
        ledger.append("launch_denied", detail)
        return LaunchDenied(f"launch of {mount!r} denied: {reason}")

    def check_agent(spec: dict, identity: str | None) -> None:
        """Enforce the mount's `agents` allowlist against a *signed* identity.

        Ordered after the grant check on purpose: the Joe-signed grant is the
        human authority to start anything at all, and the allowlist is the scope
        within that authority. Reporting a missing grant first keeps the more
        fundamental refusal the one the caller sees.
        """
        allowed = spec.get("agents", [])
        if "*" in allowed:
            return
        if identity is None:
            raise deny(
                "mount is agent-scoped; the grant must carry a signed agent "
                f"identity (allowed: {', '.join(allowed) or 'none'})"
            )
        if identity not in allowed:
            raise deny(
                f"agent {identity!r} is not on this mount's allowlist "
                f"({', '.join(allowed) or 'none'})"
            )

    spec = mounts.get(mount)
    if spec is None:
        raise deny("mount is not registered; unlisted mounts are unreachable")

    if not spec.get("require_grant"):
        # Only wildcard mounts may skip a grant, so there is no unauthenticated
        # identity to trust here. test_agent_scoped_mounts_all_require_a_grant
        # keeps that invariant true.
        check_agent(spec, agent)
        authorized["agent"] = agent
        authorized["agent_source"] = "caller-supplied" if agent else "not-required"
        ledger.append(
            "launch_authorized",
            {"mount": mount, "agent": agent, "grant": "not-required"},
        )
        return spec
    if grant_path is None:
        raise deny("write-capable mount requires a signed one-time grant")
    try:
        grant = json.loads(Path(grant_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise deny(f"grant unreadable: {error}") from error
    payload = {
        k: grant.get(k)
        for k in ("mount", "agent", "issued_at", "expires_at", "nonce")
    }
    if not key_path.exists():
        raise deny("no signing key exists; only Joe's machine can mint grants")
    expected = _sign(key_path.read_bytes(), payload)
    if not hmac.compare_digest(expected, str(grant.get("sig", ""))):
        raise deny("grant signature invalid")
    # Signature holds: every denial from here on can name the signed identity.
    verified_identity["agent"] = payload["agent"]
    if payload["mount"] != mount:
        raise deny(f"grant is for {payload['mount']!r}, not {mount!r}")
    now = now if now is not None else time.time()
    if now > float(payload["expires_at"]):
        raise deny("grant expired")
    if payload["nonce"] in _consumed_nonces(ledger):
        raise deny("grant already consumed (single-use)")

    # The identity that counts is the one inside the signature, never a value
    # the caller supplied. A passed --agent is only a cross-check.
    signed_agent = payload["agent"]
    if agent is not None and agent != signed_agent:
        raise deny(
            f"grant authorizes {signed_agent!r}, but launch claimed {agent!r}"
        )
    check_agent(spec, signed_agent)
    authorized["agent"] = signed_agent
    authorized["agent_source"] = "signed-grant"

    ledger.append(
        "launch_authorized",
        {"mount": mount, "agent": signed_agent, "nonce": payload["nonce"],
         "expires_at": payload["expires_at"]},
    )
    return spec


# Variables every child process needs simply to run. Nothing here identifies an
# account or authorizes anything.
BASELINE_ENV = (
    "PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "TZ",
    "SYSTEMROOT", "COMSPEC", "PATHEXT", "USERPROFILE",
)


def mount_env(spec: dict) -> dict[str, str]:
    """The environment one mount is allowed to see.

    Previously the launcher passed a copy of the entire process environment, so
    starting the Azure mount handed a freshly downloaded npm package every other
    credential on the machine -- TFE_TOKEN, GITHUB_PERSONAL_ACCESS_TOKEN, any
    APS secret -- none of which it needs. A mount now receives the baseline plus
    exactly the variables it declares in `env` in config/mcp_mounts.toml.

    Declaring nothing means the mount gets no credentials at all, which is the
    safe default: a mount that needs one must say so in the registry, where the
    grant reviewer can see it.
    """
    allowed = list(BASELINE_ENV) + list(spec.get("env", []))
    return {
        name: os.environ[name]
        for name in allowed
        if name in os.environ
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trusted mount launcher.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="Mint a signed one-time grant (Joe only).")
    g.add_argument("--mount", required=True)
    g.add_argument("--minutes", type=int, default=30)
    g.add_argument("--agent",
                   help="Identity this grant authorizes. Signed into the grant, "
                        "so it cannot be changed at launch. Required for any "
                        "mount whose agents list is not ['*'].")
    l = sub.add_parser("launch", help="Launch a mount under grant control.")
    l.add_argument("--mount", required=True)
    l.add_argument("--grant", type=Path)
    l.add_argument("--agent",
                   help="Optional cross-check. The authoritative identity is "
                        "the one signed into the grant; if this is supplied it "
                        "must match, otherwise the launch is refused.")
    l.add_argument("--dry-run", action="store_true",
                   help="Verify authorization without executing.")
    args = parser.parse_args(argv)

    if args.cmd == "grant":
        try:
            path = issue_grant(args.mount, args.minutes, agent=args.agent)
        except LaunchDenied as denial:
            print(json.dumps({"granted": False, "error": str(denial)}))
            return 1
        print(json.dumps({"grant": str(path), "mount": args.mount,
                          "agent": args.agent, "minutes": args.minutes}))
        return 0

    try:
        authorized: dict = {}
        spec = authorize(args.mount, args.grant, agent=args.agent,
                         authorized=authorized)
    except LaunchDenied as denial:
        print(json.dumps({"authorized": False, "error": str(denial)}))
        return 1
    if args.dry_run:
        print(json.dumps({"authorized": True, "mount": args.mount,
                          # The identity that was actually authorized, which for
                          # the documented launch command comes from the signed
                          # grant rather than the optional --agent flag. Echoing
                          # args.agent printed null in exactly the case dry-run
                          # exists to evidence.
                          "agent": authorized.get("agent"),
                          "agent_source": authorized.get("agent_source"),
                          "command": spec["command"],
                          "dry_run": True}))
        return 0
    return subprocess.call(spec["command"], cwd=str(ROOT), env=mount_env(spec))


if __name__ == "__main__":
    sys.exit(main())
