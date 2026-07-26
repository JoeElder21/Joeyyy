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
    """The mount registry, or raise ManifestUnavailable.

    The corps loader was given this treatment a round earlier and the mount
    registry -- a SECOND bare loader on the same authorization path -- was left
    open, so a missing or half-written `mcp_mounts.toml` still terminated the
    CLI with a traceback instead of its denial JSON and appended no denial
    event. Both loaders now fail closed the same way, through the audited path.
    """
    try:
        with MOUNTS.open("rb") as source:
            return {mount["name"]: mount
                    for mount in tomllib.load(source)["mounts"]}
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise ManifestUnavailable(f"{MOUNTS.name}: {error}") from error


CORPS = ROOT / "config" / "specialist_corps.toml"


class ManifestUnavailable(Exception):
    """A brain manifest could not be read, so no stage can be resolved."""


def _corps() -> dict:
    """Load the corps registry, or raise ManifestUnavailable.

    Leaking OSError/TOMLDecodeError here terminated the CLI with a traceback
    instead of its denial JSON, and skipped the ledger append this module
    promises for every refusal -- so a missing or half-written registry failed
    LOUDLY but not auditably. Both callers already handle this exception, so
    the same failure now goes out through the normal denial path.
    """
    try:
        with CORPS.open("rb") as source:
            return tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ManifestUnavailable(f"{CORPS.name}: {error}") from error


def _brain_manifest(path: str) -> dict:
    """Load a brain manifest, or raise.

    Returning {} on failure was a fail-OPEN: with no per-agent entry found,
    specialist_stage() fell back to the corps-wide deployed_stage, so the
    moment that snapshot reads `active` an unreadable or deleted manifest
    would make every allowlisted roster specialist connector-eligible --
    including one whose authoritative per-agent status is shadow or
    restricted. Deleting a file must not be a way to gain authority.
    """
    try:
        with (ROOT / path).open("rb") as source:
            return tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ManifestUnavailable(f"{path}: {error}") from error


def mount_allowlist(spec: dict, mount: str) -> list[str]:
    """The mount's `agents` allowlist, or raise ManifestUnavailable.

    `agents = "*"` is syntactically valid TOML and a plausible typo, and
    Python string membership made `"*" in "*"` true -- so a scalar was read as
    a WILDCARD, minting a null-identity grant that `authorize()` then accepted,
    bypassing both the identity check and the lifecycle gate. Any scalar would
    do it: `"apex_chief_of_staff"` contains no `*`, but it does contain every
    substring of itself, so a one-character agent name would match too. The
    field must be a list of non-empty strings before `*` means anything.
    """
    declared = spec.get("agents", [])
    if not isinstance(declared, (list, tuple)) or not all(
            isinstance(name, str) and name.strip() for name in declared):
        raise ManifestUnavailable(
            f"mount {mount!r}: `agents` must be a list of agent names; the "
            "registry cannot say who is allowed")
    return list(declared)


def specialist_stage(agent: str, corps: dict | None = None) -> str | None:
    """The lifecycle stage of a roster specialist, or None if not one.

    Resolved from the named agent's own entry in its brain manifest
    (`[agents.<id>] status`), falling back to the corps-wide `deployed_stage`
    only when the agent has no entry of its own. Reading the corps-wide value
    first was wrong in both directions: an individually promoted specialist was
    denied while the snapshot said `shadow`, and moving the snapshot to
    `active` would have made every still-shadow allowlisted specialist eligible
    at once.

    When the two disagree, the MORE RESTRICTIVE wins. A per-agent promotion is
    real authority and must be recorded per agent; a per-agent restriction must
    never be widened by a permissive global snapshot.

    Agent 007 is not a rostered specialist and is not stage-gated here: it is
    the designated executor, which is the whole reason the specialists are.
    """
    corps = corps if corps is not None else _corps()
    # Syntactically valid TOML can still be structurally wrong -- a roster
    # mistyped as a scalar during a partial edit, say. Indexing it raised a
    # bare TypeError, and both callers convert only ManifestUnavailable, so the
    # CLI printed a traceback and wrote no denial event: the same
    # loud-but-unauditable failure the loaders were fixed for, one layer up.
    rosters = {}
    for key in ("apex_roster", "jeos_roster"):
        value = corps.get(key, [])
        if not isinstance(value, (list, tuple)) or not all(
                isinstance(name, str) for name in value):
            raise ManifestUnavailable(
                f"{CORPS.name}: [{key}] must be a list of agent names; the "
                "registry cannot say who is rostered")
        rosters[key] = set(value)
    roster = rosters["apex_roster"] | rosters["jeos_roster"]
    if agent not in roster:
        # The exemption belongs to the DESIGNATED EXECUTOR, not to "anyone the
        # roster does not mention". Keying it on absence made a missing roster
        # array -- syntactically valid TOML, exactly what a partial write
        # leaves behind -- promote every allowlisted shadow specialist to the
        # one identity that is not stage-gated. Nothing raised, because nothing
        # was malformed. Name the executor instead, and refuse every other
        # identity whose lifecycle this registry cannot account for.
        executor = corps.get("governance", {}).get("designated_executor")
        if executor and agent == executor:
            return None
        return "unrostered"

    deployed = corps.get("lifecycle", {}).get("deployed_stage")
    # Read the OWNING brain's manifest only. Walking apex-then-jeos meant an
    # unreadable APEX manifest denied every JEOS specialist too, before its own
    # healthy records were ever consulted -- one brain's connector eligibility
    # made to depend on the other brain's files, which is precisely the
    # coupling AGENTS.md separates the brains to avoid. A read failure is still
    # an authorization failure, but only for the brain that owns the agent.
    in_apex = agent in rosters["apex_roster"]
    in_jeos = agent in rosters["jeos_roster"]
    if in_apex and in_jeos:
        # Brain-locking is the point: an identity belongs to exactly one brain,
        # so listing it in both is not a preference to resolve but a registry
        # that cannot say who owns the agent. Silently preferring APEX let the
        # more permissive of two manifests decide -- APEX `active` beating an
        # authoritative JEOS `restricted` -- which is the widening the
        # owning-brain lookup was introduced to stop, reached by a different
        # route. Ambiguous ownership is an authorization failure.
        raise ManifestUnavailable(
            f"{agent!r} is listed in both the APEX and JEOS rosters; brain "
            "ownership is ambiguous, so no authoritative stage exists")
    manifest_key = "apex_brain_manifest" if in_apex else "jeos_brain_manifest"
    expected_brain = "APEX" if in_apex else "JEOS"
    per_agent = None
    manifest_path = corps.get(manifest_key)
    if manifest_path:
        manifest = _brain_manifest(manifest_path)
        # The file at the APEX path must SAY it is the APEX manifest. Reading
        # the per-agent stage without checking meant a manifest swapped into
        # the wrong path -- structurally valid, declaring the other brain --
        # supplied authority for an identity it does not own, which is the
        # brain-locking boundary AGENTS.md builds the whole separation on. The
        # manifest names its own brain; take it at that word or refuse.
        declared_brain = manifest.get("brain")
        if declared_brain != expected_brain:
            raise ManifestUnavailable(
                f"{manifest_path} declares brain {declared_brain!r}, not "
                f"{expected_brain!r}; it cannot speak for {agent!r}")
        agents = manifest.get("agents", {})
        # Valid TOML, wrong shape: `agents = 1` raised a bare AttributeError,
        # and both callers convert only ManifestUnavailable, so a partial
        # manifest update produced a traceback and no audited denial. The corps
        # roster got this treatment a round earlier; the separately loaded
        # brain manifest did not.
        if not isinstance(agents, dict):
            raise ManifestUnavailable(
                f"{manifest_path}: [agents] must be a table; the manifest "
                "cannot say what stage any agent is at")
        entry = agents.get(agent)
        if isinstance(entry, dict) and entry.get("status"):
            per_agent = entry["status"]

    if per_agent is None:
        # No authoritative record for this agent -- the manifest path is absent
        # from the corps file, or the manifest has no entry for it. Falling
        # back to the corps-wide snapshot is only safe while that snapshot
        # denies. The moment `deployed_stage` reads `active`, the fallback
        # hands a connector to every allowlisted specialist whose promotion
        # nobody ever recorded, which is the exact widening this function's
        # own rule forbids: a per-agent promotion is real authority and must be
        # recorded per agent. A permissive snapshot plus a missing record is
        # therefore a denial, not an inheritance.
        if stage_permits_connector(deployed):
            return "unrecorded"
        return deployed
    if deployed is None:
        return per_agent
    # Take whichever grants less. An unknown stage is not eligible anyway, so
    # comparing eligibility is enough and needs no ordering.
    if stage_permits_connector(per_agent) and not stage_permits_connector(deployed):
        return deployed
    return per_agent


def connector_stages(corps: dict | None = None) -> frozenset[str]:
    """The stages at which a specialist may hold a connector, from the registry.

    This is a governance rule, and
    `.github/instructions/agent-safety.instructions.md` requires governance
    rules to live in the configuration the runtime actually reads rather than
    in application logic. Hardcoding it meant a rename or addition in the
    registry's own `stages` list could be accepted by the registry and its
    validators while this module went on enforcing a stale set -- denying the
    intended stage, or keeping authority for one that had been removed.

    Fails closed when the key is missing or malformed, and deliberately does
    NOT fall back to a built-in default: a silent default is the exact failure
    this key exists to remove.
    """
    corps = corps if corps is not None else _corps()
    declared = corps.get("lifecycle", {}).get("connector_stages")
    if (not isinstance(declared, list) or not declared
            or not all(isinstance(stage, str) and stage for stage in declared)):
        raise ManifestUnavailable(
            f"{CORPS.name}: [lifecycle] connector_stages must be a non-empty "
            "list of stage names; connector eligibility cannot be resolved")
    return frozenset(declared)


def stage_permits_connector(stage: str | None, corps: dict | None = None) -> bool:
    """Whether a specialist at `stage` may hold a mount of its own.

    MEMBERSHIP, not ordering. The ordinal test this replaced was wrong in the
    one direction that matters: the stage list runs candidate, shadow, active,
    value-proven, restricted, deprecated, retired -- so every ADMINISTRATIVE
    EXIT sorts after `active` and compared as a promotion. A specialist the
    lifecycle graph moved to `restricted` for writing outside its lease kept
    minting full connector grants, as did a deprecated or retired one. Naming
    the eligible stages means a new stage is denied by default instead of
    inheriting authority from its position in a list.

    An unrecognised stage is not evidence of promotion, so it is denied.
    """
    if stage is None:
        return True
    return stage in connector_stages(corps)


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
    mount: str,
    minutes: int,
    key_path: Path = DEFAULT_KEY_PATH,
    out_dir: Path | None = None,
    now: float | None = None,
    agent: str | None = None,
    ledger: AuditLedger | None = None,
) -> Path:
    """Create a signed, single-use grant file for one mount and one identity.

    The agent is part of the signed payload. A caller cannot claim an identity
    it was not granted, because forging one requires the signing key -- which
    lives outside the repository and only exists on Joe's machine. An earlier
    version read the identity from a CLI flag at launch time, which any caller
    holding a valid grant could set to anything.
    """
    ledger = ledger or AuditLedger(DEFAULT_LEDGER)

    def refuse(reason: str) -> LaunchDenied:
        # The module promises that every denial is recorded. Grant-time refusals
        # are the ones worth keeping most: an attempt to mint authority for a
        # shadow specialist is exactly the event an audit should surface.
        detail = {"mount": mount, "reason": reason}
        if agent is not None:
            detail["agent"] = agent
        ledger.append("grant_denied", detail)
        return LaunchDenied(reason)

    # Loaded AFTER refuse() exists, so an unreadable registry leaves a denial in
    # the ledger rather than a traceback on stderr.
    try:
        mounts = _load_mounts()
    except ManifestUnavailable as error:
        raise refuse(
            f"cannot read the mount registry: {error}. An unreadable registry "
            "is an authorization failure, not an empty allowlist.")

    if mount not in mounts:
        raise refuse(f"unknown mount {mount!r}")

    try:
        allowed = mount_allowlist(mounts[mount], mount)
    except ManifestUnavailable as error:
        raise refuse(
            f"cannot read the allowlist: {error}. A malformed allowlist is an "
            "authorization failure, not a wildcard.")
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

    # Being on the allowlist is necessary, not sufficient. Those lists record
    # which specialist WILL own a mount once promoted; making them executable
    # without a lifecycle check handed mutation-capable connectors to agents
    # the contract confines to analysis and proposed writes. Every rostered
    # specialist is currently `shadow`, so in practice this leaves Agent 007 as
    # the only identity that can hold a grant -- which is the documented
    # arrangement, now enforced rather than described.
    try:
        stage = specialist_stage(agent) if agent else None
    except ManifestUnavailable as error:
        raise refuse(
            f"cannot resolve the lifecycle stage of {agent!r}: {error}. "
            "An unreadable brain manifest is an authorization failure, not an "
            "absent override."
        )
    if not stage_permits_connector(stage):
        raise refuse(
            f"agent {agent!r} is lifecycle stage {stage!r}; a specialist may "
            "hold a connector only at "
            f"{', '.join(sorted(connector_stages()))}. Promote it through "
            "docs/AGENT_COMMUNITY_PROTOCOL.md first, or mint the grant for the "
            "designated executor."
        )

    # The disclosure must exist BEFORE a signature does. Validating it only in
    # verify_mcp_mounts.py left the authorization path itself unprotected: a
    # runtime registry with a missing, blank or non-string grant_scope still
    # produced a signed grant, and the mint output showed Joe an empty
    # disclosure for a whole-server authority. A gate that runs beside the
    # thing it guards is not guarding it.
    if mounts[mount].get("require_grant"):
        declared = mounts[mount].get("grant_scope", "")
        if not isinstance(declared, str) or not declared.strip():
            raise refuse(
                "this mount declares no readable grant_scope, so the blast "
                "radius of the signature cannot be shown; refusing to mint a "
                "grant whose authority cannot be stated")

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


def _grant_scope(mount: str) -> str:
    """What a grant for `mount` actually authorizes, verbatim from the registry.

    Never guess and never summarise: an empty string means the registry does
    not declare it, and `verify_mcp_mounts.py` fails the gate on exactly that,
    so silence here is a gate failure rather than an implied "narrow".
    """
    try:
        return str(_load_mounts().get(mount, {}).get("grant_scope", ""))
    except Exception:  # noqa: BLE001 - reporting must not break the mint path
        return ""


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
    mount: str,
    grant_path: Path | None,
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

    # Same as the grant path: the registry load must go out through deny().
    try:
        mounts = _load_mounts()
    except ManifestUnavailable as error:
        raise deny(
            f"cannot read the mount registry: {error}. An unreadable registry "
            "is an authorization failure, not an empty allowlist.")

    def check_agent(spec: dict, identity: str | None) -> None:
        """Enforce the mount's `agents` allowlist against a *signed* identity.

        Ordered after the grant check on purpose: the Joe-signed grant is the
        human authority to start anything at all, and the allowlist is the scope
        within that authority. Reporting a missing grant first keeps the more
        fundamental refusal the one the caller sees.
        """
        try:
            allowed = mount_allowlist(spec, mount)
        except ManifestUnavailable as error:
            raise deny(
                f"cannot read the allowlist: {error}. A malformed allowlist "
                "is an authorization failure, not a wildcard.")
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
        # Lifecycle is re-read HERE, not trusted from mint time. A grant is
        # short-lived but not instantaneous, and eligibility can be withdrawn
        # inside its window: a specialist that was `active` when the grant was
        # signed and is `restricted` by the time it launches would otherwise
        # still be authorized, because the signature, expiry and allowlist all
        # still check out. An administrative restriction has to revoke
        # outstanding access, not just prevent new grants.
        try:
            stage = specialist_stage(identity)
        except ManifestUnavailable as error:
            raise deny(
                f"cannot resolve the lifecycle stage of {identity!r}: {error}. "
                "An unreadable brain manifest is an authorization failure, not "
                "an absent override."
            )
        if not stage_permits_connector(stage):
            raise deny(
                f"agent {identity!r} is lifecycle stage {stage!r}; a specialist "
                "may hold a connector only at "
                f"{', '.join(sorted(connector_stages()))}. The grant was valid "
                "when minted; eligibility was withdrawn before launch."
            )

    spec = mounts.get(mount)
    if spec is None:
        raise deny("mount is not registered; unlisted mounts are unreachable")

    if not spec.get("require_grant"):
        # Only WILDCARD mounts may skip a grant, and that is now enforced here
        # rather than left to a test over the committed registry. The test
        # proves today's file is consistent; it cannot speak for a registry
        # edited between releases, half-applied, or merged from two branches.
        # An agent-scoped mount that declares no grant requirement is exactly
        # that ambiguity, and the old code resolved it the wrong way: it
        # accepted the caller's own --agent, filed it as `agent_authenticated:
        # false`, and started a write-capable mount with nothing Joe had
        # signed. Runtime authorization refuses an ambiguous registry.
        try:
            declared = mount_allowlist(spec, mount)
        except ManifestUnavailable as error:
            raise deny(
                f"cannot read the allowlist: {error}. A malformed allowlist "
                "is an authorization failure, not a wildcard.")
        if "*" not in declared:
            raise deny(
                "mount is agent-scoped but declares no grant requirement "
                f"(allowed: {', '.join(declared) or 'none'}). Only a wildcard "
                "mount may start without a Joe-signed grant; set "
                "`require_grant = true` or open the allowlist deliberately.")
        check_agent(spec, agent)
        authorized["agent"] = agent
        authorized["agent_source"] = "caller-supplied" if agent else "not-required"
        # Record the claim AS a claim. Nothing authenticated `agent` on this
        # path -- there is no grant to have signed it -- so writing it into the
        # same `agent` field a grant-backed launch uses preserved a forged
        # identity in the hash chain as though it had been verified. The chain
        # is only as good as what it attributes, and an unauthenticated string
        # filed under the authenticated name is worse than no attribution.
        ledger.append(
            "launch_authorized",
            {"mount": mount, "claimed_agent": agent,
             "agent_authenticated": False, "grant": "not-required"},
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
        {
            "mount": mount,
            "agent": signed_agent,
            "nonce": payload["nonce"],
            "expires_at": payload["expires_at"],
        },
    )
    return spec


# Variables every child process needs simply to run. Nothing here identifies an
# account or authorizes anything.
BASELINE_ENV = (
    "PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "TZ",
    "SYSTEMROOT", "COMSPEC", "PATHEXT", "USERPROFILE",
)

# Outbound transport configuration. A mount that fetches its own package or
# image (npx, docker pull) cannot reach the network at all on a proxied
# workstation once the environment is filtered -- authorization succeeds and
# the launch then fails at download. These are deliberately NOT in
# BASELINE_ENV: a proxy URL can carry credentials in its userinfo, so only
# mounts that declare `network = true` in the registry receive them.
NETWORK_ENV = (
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
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

    A mount that declares `network = true` additionally receives NETWORK_ENV,
    without which a proxied workstation cannot fetch the mount's own package or
    image. That is opt-in rather than baseline because a proxy URL may embed
    credentials, so a purely local mount has no business seeing one.
    """
    allowed = list(BASELINE_ENV) + list(spec.get("env", []))
    if spec.get("network"):
        allowed += list(NETWORK_ENV)
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
    g.add_argument(
        "--agent",
        help="Identity this grant authorizes. Signed into the grant, "
             "so it cannot be changed at launch. Required for any "
             "mount whose agents list is not ['*'].",
    )
    l = sub.add_parser("launch", help="Launch a mount under grant control.")
    l.add_argument("--mount", required=True)
    l.add_argument("--grant", type=Path)
    l.add_argument(
        "--agent",
        help="Optional cross-check. The authoritative identity is "
             "the one signed into the grant; if this is supplied it "
             "must match, otherwise the launch is refused.",
    )
    l.add_argument(
        "--dry-run", action="store_true", help="Verify authorization without executing."
    )
    args = parser.parse_args(argv)

    if args.cmd == "grant":
        try:
            path = issue_grant(args.mount, args.minutes, agent=args.agent)
        except LaunchDenied as denial:
            print(json.dumps({"granted": False, "error": str(denial)}))
            return 1
        # Print what the signature actually authorizes. The grant names a
        # mount, and a mount is an entire server: a grant minted for an Azure
        # inventory task equally authorizes deletion, RBAC and credential
        # tools, because nothing downstream mediates individual tool calls.
        # Leaving that to be inferred from `purpose` asks Joe to sign a
        # blast radius he was never shown.
        print(
            json.dumps(
                {
                    "grant": str(path),
                    "mount": args.mount,
                    "agent": args.agent,
                    "minutes": args.minutes,
                    "authorizes": _grant_scope(args.mount),
                }
            )
        )
        return 0

    try:
        authorized: dict = {}
        spec = authorize(args.mount, args.grant, agent=args.agent,
                         authorized=authorized)
    except LaunchDenied as denial:
        print(json.dumps({"authorized": False, "error": str(denial)}))
        return 1
    if args.dry_run:
        print(
            json.dumps(
                {
                    "authorized": True,
                    "mount": args.mount,
                    # The identity that was actually authorized, which for
                    # the documented launch command comes from the signed
                    # grant rather than the optional --agent flag. Echoing
                    # args.agent printed null in exactly the case dry-run
                    # exists to evidence.
                    "agent": authorized.get("agent"),
                    "agent_source": authorized.get("agent_source"),
                    "command": spec["command"],
                    "dry_run": True,
                }
            )
        )
        return 0
    return subprocess.call(spec["command"], cwd=str(ROOT), env=mount_env(spec))


if __name__ == "__main__":
    sys.exit(main())
