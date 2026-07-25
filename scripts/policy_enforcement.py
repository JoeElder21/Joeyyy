"""Single policy-enforcement point, evaluated immediately before tool execution.

Absorbed from `cedar-policy/cedar` per `docs/REPO_OPTIMIZATION_2026-07-25.md`
(Tier 2 #5). The verdict there was **absorb the pattern, do not replatform** —
the existing guards work and are tested, and rewriting them in a policy language
would trade proven code for a new dependency. The extractable idea was structural
rather than technological:

    one explicit enforcement point immediately before tool execution,
    rather than checks spread across the call path.

That is what this module is. It decides nothing new. Every rule below already
existed and is still owned by the module that implemented it — `PacketGuard`,
the roster manifests, `runtime.writer_lease`, `scripts.trusted_launcher`, and
`AGENTS.md`. What was missing was a place where a reader could see the complete
set at once, and a single call a caller cannot partially perform.

Why that matters here specifically: checks spread across a call path fail open by
omission. A new call site that forgets one of five scattered checks is not a
visible bug — nothing errors, the missing check simply never runs. Consolidating
them means a new call site either passes through the gate or does not, and
"forgot the brain lock" stops being an available failure mode.

The Cedar vocabulary maps directly, which is why the pattern transferred:

    principal  -> the acting agent, and the brain it is locked to
    action     -> the tool invocation, and its packet mode
    resource   -> the connector, mount, or write target
    context    -> the active writer lease, lifecycle stage, and launch grant

Fail-closed: an unrecognised request is denied, not permitted. Every denial
carries its reasons, and callers with a ledger get both outcomes recorded.
"""

from __future__ import annotations

import datetime
import hmac
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.writer_lease import canonical_key  # noqa: E402
from scripts.agent_runtime import AuditLedger, load_roster  # noqa: E402
from scripts.packet_guard import PacketGuard  # noqa: E402

# Grant verification reuses the launcher's own signing primitive, so the two can
# never disagree about what a valid grant looks like.
from scripts.trusted_launcher import DEFAULT_KEY_PATH as DEFAULT_LAUNCH_KEY  # noqa: E402
from scripts.trusted_launcher import _sign as _sign_grant  # noqa: E402

# AGENTS.md: explicit task-level instruction is required for each of these.
# Kept as data so the boundary list is enumerable and testable rather than
# scattered through prose and conditionals.
HIGH_IMPACT_ACTIONS = frozenset(
    {
        "irreversible_bulk_deletion",
        "financial_transaction",
        "credential_or_access_change",
        "sign_or_certify_professional_work",
        "binding_legal_commitment",
        "public_publication",
    }
)

# The only connector posture the deployed roster declares. Anything else is a
# configuration the runtime has never been shown to be safe under.
PACKET_ONLY = "packet_only_no_direct_connectors"

# Specialists in these stages may not execute mutations themselves. Per
# AGENTS.md, while specialists are in shadow, Agent 007 alone executes and
# verifies mutations.
NON_EXECUTING_STAGES = frozenset({"candidate", "shadow", "restricted", "deprecated", "retired"})

CHIEF = "apex_chief_of_staff"

# Lease statuses under which a mutation may proceed. Anything else -- released,
# verified, expired -- is a closed lease and authorizes nothing further.
ACTIVE_LEASE_STATUSES = frozenset({"active", "in_flight"})

# The single schema error tolerated on a writer lease, and only this one.
# See the comment in PolicyEnforcementPoint._writer_lease for why.
VERSION_MISMATCH_DEFECT = "$.schema_version: expected const '2.0'"

# Action fragments that imply a mutation regardless of what the caller declares.
# Deliberately generous: over-classifying a read as a mutation costs a lease,
# while under-classifying a write costs every mutation control at once.
MUTATING_ACTION_VERBS = (
    "write",
    "create",
    "update",
    "delete",
    "remove",
    "mutate",
    "publish",
    "send",
    "commit",
    "push",
    "append",
    "modify",
    "set_",
    "put",
    "post",
)


def _load_brain_manifests(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Status, connector policy, and write targets, from the brain-owned files."""
    merged: dict[str, dict[str, Any]] = {}
    for brain in ("apex", "jeos"):
        path = root / "brains" / brain / "agents.toml"
        if not path.exists():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for agent, spec in data.get("agents", {}).items():
            merged[agent] = dict(spec)
    return merged


def _load_brain_prefixes(root: Path = ROOT) -> dict[str, str]:
    """Namespace and write-target prefixes that identify which brain owns a resource.

    Read from the brain-owned manifests rather than hardcoded, so a renamed
    prefix cannot silently detach the ownership check from reality.
    """
    prefixes: dict[str, str] = {}
    for brain in ("apex", "jeos"):
        path = root / "brains" / brain / "agents.toml"
        if not path.exists():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        owner = str(data.get("brain") or brain).upper()
        for key in ("write_target_prefix", "namespace_prefix"):
            value = data.get(key)
            if value:
                prefixes[str(value)] = owner
    return prefixes


@dataclass(frozen=True)
class ToolRequest:
    """A tool invocation awaiting authorization.

    Deliberately explicit. A request that does not state its principal, action,
    and resource cannot be evaluated, and guessing any of them is how an
    enforcement point becomes decorative.
    """

    agent: str
    action: str
    resource: str
    owner_brain: str | None = None
    mutating: bool = False
    packet: dict[str, Any] | None = None
    packet_schema: str = "delegation_packet.schema.json"
    lease: dict[str, Any] | None = None
    resource_id: str | None = None
    now: datetime.datetime | None = None
    explicit_instruction: bool = False
    # Signed grant material, not an assertion. `launch_grant_verified` used to be
    # a plain bool the caller set, which is the same "trust the caller" defect as
    # the mutating flag: any caller could claim a grant it never held.
    launch_grant: dict[str, Any] | None = None
    launch_key_path: Path | None = None


@dataclass
class Decision:
    """Allow or deny, with the reasons either way."""

    allowed: bool
    reasons: tuple[str, ...] = ()
    checks_run: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.allowed


class PolicyDenied(Exception):
    """Raised by `enforce` when the request is not authorized."""

    def __init__(self, request: ToolRequest, reasons: list[str]):
        self.request = request
        self.reasons = reasons
        super().__init__(
            f"{request.agent} -> {request.action} on {request.resource}: " + "; ".join(reasons)
        )


class PolicyEnforcementPoint:
    """Evaluates every rule, then returns one verdict.

    Rules are evaluated in full rather than short-circuiting on the first
    failure: a caller fixing a denial should see every reason at once instead of
    discovering them one round trip at a time.
    """

    def __init__(
        self,
        root: Path = ROOT,
        guard: PacketGuard | None = None,
        registry: Any | None = None,
    ) -> None:
        self.root = root
        self.guard = guard or PacketGuard(root)
        # Authoritative source of issued leases. Without it, a mutation cannot
        # be authorized at all -- see _registry_membership_errors.
        self.registry = registry
        self.roster = load_roster(root)
        # `.codex/agents/*.toml` (what load_roster reads) carries brain and
        # instructions but NOT status or connector_policy — those live in the
        # brain-owned manifests. Sourcing them from the roster alone made the
        # lifecycle-stage and connector-policy rules silently evaluate to "no
        # objection" for every agent, which is the exact fail-open-by-omission
        # this enforcement point exists to eliminate. Found by running it.
        self.manifest = _load_brain_manifests(root)
        self.brain_prefixes = _load_brain_prefixes(root)

    def _spec(self, agent: str) -> dict[str, Any]:
        """Merged view: brain manifest wins, roster fills the rest."""
        merged = dict(self.roster.get(agent) or {})
        merged.update(self.manifest.get(agent) or {})
        return merged

    @staticmethod
    def _is_mutating(request: ToolRequest) -> bool:
        """Derive mutation status; never simply believe the caller.

        `mutating` defaulted to False, so a caller that forgot the flag on an
        `action="write"` request skipped the lease, lifecycle, and launch-grant
        rules entirely — a shadow-stage specialist could write with no lease and
        be allowed. An enforcement point whose protections a caller can decline
        by omission is the failure this module exists to remove, and it had that
        failure in its own signature.

        The flag can now only ever *add* strictness: it is OR-ed with a
        derivation from the action and resource, so declaring `mutating=False`
        on a write no longer buys anything.
        """
        if request.mutating:
            return True
        action = (request.action or "").lower()
        if any(verb in action for verb in MUTATING_ACTION_VERBS):
            return True
        return action in HIGH_IMPACT_ACTIONS

    def evaluate(self, request: ToolRequest) -> Decision:
        # Re-derive once, up front, so every rule sees the same answer.
        if self._is_mutating(request) and not request.mutating:
            request = replace(request, mutating=True)

        reasons: list[str] = []
        checks: list[str] = []

        for name, check in (
            ("agent_registered", self._agent_registered),
            ("brain_lock", self._brain_lock),
            ("connector_policy", self._connector_policy),
            ("packet_admission", self._packet_admission),
            ("writer_lease", self._writer_lease),
            ("lifecycle_stage", self._lifecycle_stage),
            ("high_impact_boundary", self._high_impact_boundary),
            ("launch_grant", self._launch_grant),
        ):
            checks.append(name)
            reasons.extend(check(request))

        return Decision(allowed=not reasons, reasons=tuple(reasons), checks_run=tuple(checks))

    # --- rules ----------------------------------------------------------
    # Each returns a list of reasons the request must be denied. Empty means
    # this rule has no objection, never that the request is approved.

    def _agent_registered(self, request: ToolRequest) -> list[str]:
        if request.agent not in self.roster:
            return [
                f"agent {request.agent!r} is not in the deployed roster; unlisted agents cannot act"
            ]
        return []

    def _brain_lock(self, request: ToolRequest) -> list[str]:
        spec = self._spec(request.agent)
        if not spec:
            return []  # _agent_registered already denies this
        if request.agent == CHIEF:
            return []  # the sole cross-brain agent, by contract
        # An omitted owner_brain used to mean "no objection", which let a caller
        # bypass the brain lock simply by withholding the field. Fail-closed
        # means a non-chief agent must declare its brain: silence is not consent.
        if request.owner_brain is None:
            return [
                f"brain lock: {request.agent!r} declared no owner_brain; a specialist "
                "must state its brain, and omitting it does not waive the lock"
            ]
        agent_brain = spec.get("brain")
        errors = []
        if agent_brain != request.owner_brain:
            errors.append(
                f"brain lock: {request.agent!r} belongs to {agent_brain!r}, "
                f"request declares {request.owner_brain!r}"
            )
        # Declaring your own brain correctly is not the same as being entitled to
        # the resource. Previously only the declaration was checked, so an APEX
        # specialist could read `JEOS/Weekly` simply by declaring "APEX" -- the
        # lock compared the caller against itself. Resolve who owns the resource
        # and compare that too.
        resource_brain = self._resource_owner(request.resource)
        if resource_brain and agent_brain and resource_brain != agent_brain:
            errors.append(
                f"brain lock: resource {request.resource!r} belongs to "
                f"{resource_brain!r}, and {request.agent!r} is {agent_brain!r}-only"
            )
        return errors

    def _resource_owner(self, resource: str) -> str | None:
        """Which brain owns this resource, by manifest-declared prefix."""
        for prefix, owner in self.brain_prefixes.items():
            if resource.startswith(prefix):
                return owner
        return None

    def _connector_policy(self, request: ToolRequest) -> list[str]:
        spec = self._spec(request.agent)
        policy = spec.get("connector_policy")
        if policy is None or request.agent == CHIEF:
            return []
        if policy != PACKET_ONLY:
            return [f"connector policy {policy!r} is not the approved {PACKET_ONLY!r}"]
        return []

    def _packet_admission(self, request: ToolRequest) -> list[str]:
        if request.packet is None:
            if request.mutating:
                return ["mutating request carries no packet; packet-only policy admits nothing"]
            return []
        errors = [
            f"packet rejected: {error}"
            for error in self.guard.validate(request.packet_schema, request.packet)
        ]
        return errors + self._packet_scope_errors(request)

    def _writer_lease(self, request: ToolRequest) -> list[str]:
        """Validate the lease as a lease, not as two matching strings.

        The first version accepted any dict carrying a matching `writer_agent`
        and `write_target`. That let a caller mint its own authorization:
        `{"writer_agent": "apex_chief_of_staff", "write_target": "APEX/..."}`
        passed, though no lease had ever been issued — defeating the
        single-active-writer invariant precisely where it is supposed to hold.

        The lease is now checked against `schemas/writer_lease.schema.json` by
        the same guard the runtime uses, then against status, expiry, brain, and
        resource. A forged dict fails the schema before any field comparison.
        """
        if not request.mutating:
            return []
        if request.lease is None:
            return [f"mutation of {request.resource!r} requires an active writer lease"]

        lease = request.lease

        # Schema validity proves shape, never issuance. A caller that fabricates
        # a *complete* lease-shaped dict passes every structural check, so the
        # lease id must be confirmed against the authoritative registry that
        # issued it — otherwise the single-active-writer invariant holds only
        # against careless callers, not against the one this gate exists for.
        #
        # Fail-closed when no registry is supplied: an unverifiable lease is not
        # a lease. Because enforce() has no live call sites yet, this can be
        # strict from the outset rather than loosened later.
        registry_errors, issued = self._registry_membership(lease)
        if registry_errors:
            return registry_errors
        # From here on, read the REGISTRY's lease, never the caller's copy.
        # Comparing only lease_id against the registry and then reading the rest
        # from the submitted dict let a caller copy a genuine active lease,
        # change writer_agent (or status, or expiry), and pass -- the id matched
        # a real lease while every authorization-relevant field came from the
        # attacker. The id is the lookup key; it is not the authorization.
        lease = issued

        raw = self.guard.validate("writer_lease.schema.json", lease)
        # KNOWN REPOSITORY DEFECT, scoped deliberately narrowly.
        #
        # schemas/writer_lease.schema.json pins schema_version to const "2.0",
        # but runtime/writer_lease.py issues "2.1". Every lease the registry
        # produces therefore fails its own schema. Nothing caught it because the
        # only test touching both checks required-field presence, not the const,
        # and the packet-contract fixtures hand-build 2.0 leases.
        # scripts/memory_layer.py would already reject a real registry lease.
        #
        # Blocking on it here would deny every legitimate mutation; silently
        # skipping schema validation would recreate the forged-lease hole this
        # rule exists to close. So exactly one error string is tolerated, and
        # every other schema error still denies. Resolving the mismatch is a
        # contract decision for Joe — see docs/REPO_OPTIMIZATION_2026-07-25.md.
        errors = [
            f"lease rejected: {error}" for error in raw if VERSION_MISMATCH_DEFECT not in error
        ]
        if errors:
            # A lease that is not schema-valid is not a lease; comparing its
            # fields afterwards would be reading an unvalidated structure.
            return errors

        holder = lease.get("writer_agent")
        if holder != request.agent:
            errors.append(
                f"lease on {request.resource!r} is held by {holder!r}, not {request.agent!r}"
            )
        status = lease.get("status")
        if status not in ACTIVE_LEASE_STATUSES:
            errors.append(
                f"lease status {status!r} is not active; a closed lease authorizes nothing"
            )
        if request.owner_brain and lease.get("owner_brain") != request.owner_brain:
            errors.append(
                f"lease is scoped to {lease.get('owner_brain')!r}, request declares "
                f"{request.owner_brain!r}"
            )
        target = lease.get("write_target")
        if target and request.resource and not request.resource.startswith(target):
            errors.append(f"lease covers {target!r}, which does not cover {request.resource!r}")
        if request.resource_id and lease.get("resource_id") != request.resource_id:
            errors.append(
                f"lease is for resource {lease.get('resource_id')!r}, request targets "
                f"{request.resource_id!r}"
            )
        errors.extend(self._lease_expiry_errors(lease, request))
        return errors

    def _registry_membership(self, lease: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """Look the lease up and return the authoritative copy alongside errors."""
        if self.registry is None:
            return (
                [
                    "no authoritative lease registry available; a caller-supplied lease "
                    "cannot be verified as issued, and an unverifiable lease is not a lease"
                ],
                {},
            )
        try:
            key = canonical_key(
                str(lease.get("owner_brain", "")),
                str(lease.get("write_target", "")),
                str(lease.get("resource_id", "")),
            )
        except Exception as error:
            # A lease too malformed to even key must deny, not raise. An
            # enforcement point that throws on hostile input is a denial-of-
            # service on every legitimate caller sharing the process.
            return ([f"lease cannot be keyed, so it cannot be verified as issued: {error}"], {})
        issued = self.registry.active_lease(key)
        if issued is None:
            return ([f"no active lease is registered for {key!r}"], {})
        if issued.get("lease_id") != lease.get("lease_id"):
            return (
                [
                    f"lease id {lease.get('lease_id')!r} does not match the registered "
                    f"active lease for {key!r}"
                ],
                {},
            )
        return ([], dict(issued))

    def _packet_scope_errors(self, request: ToolRequest) -> list[str]:
        """Bind the packet to *this* invocation.

        A schema-valid packet addressed to another specialist was previously
        accepted as authorization, so a read-only delegation for one agent could
        authorize a different agent's request. `admit_delegation()` already binds
        addressee and brain; the enforcement point has to do the same or it is a
        weaker gate than the one it consolidates.
        """
        packet = request.packet or {}
        errors = []
        addressee = packet.get("agent")
        if addressee and addressee != request.agent:
            errors.append(
                f"packet addresses {addressee!r}, not the requesting agent {request.agent!r}"
            )
        brain = packet.get("owner_brain")
        if brain and request.owner_brain and brain != request.owner_brain:
            errors.append(
                f"packet owner_brain {brain!r} does not match the request's {request.owner_brain!r}"
            )
        resource = packet.get("resource_id")
        if resource and request.resource_id and resource != request.resource_id:
            errors.append(
                f"packet resource {resource!r} does not match the requested {request.resource_id!r}"
            )
        return errors

    @staticmethod
    def _lease_expiry_errors(lease: dict[str, Any], request: ToolRequest) -> list[str]:
        """An expired lease is a closed lease. Unparseable timestamps fail closed."""
        expiry = lease.get("expires_at")
        if not expiry:
            return ["lease declares no expiry"]
        now = request.now or datetime.datetime.now(datetime.UTC)
        try:
            deadline = datetime.datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        except ValueError:
            return [f"lease expiry {expiry!r} is not a parseable timestamp"]
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=datetime.UTC)
        if now > deadline:
            return [f"lease expired at {expiry}"]
        return []

    def _lifecycle_stage(self, request: ToolRequest) -> list[str]:
        if not request.mutating or request.agent == CHIEF:
            return []
        stage = self._spec(request.agent).get("status")
        if stage in NON_EXECUTING_STAGES:
            return [
                f"{request.agent!r} is in {stage!r}; only {CHIEF} executes and verifies "
                "mutations while specialists are pre-active"
            ]
        return []

    def _high_impact_boundary(self, request: ToolRequest) -> list[str]:
        if request.action in HIGH_IMPACT_ACTIONS and not request.explicit_instruction:
            return [
                f"{request.action!r} is a high-impact boundary and requires explicit "
                "task-level instruction from Joe"
            ]
        return []

    def _launch_grant(self, request: ToolRequest) -> list[str]:
        """Verify the grant's signature; never accept a claim that one exists.

        This was a caller-set boolean — the identical "trust the caller" defect
        as the `mutating` flag fixed one round earlier, sitting two rules away.
        Any caller could assert `launch_grant_verified=True` and walk past the
        control without ever holding a grant.

        Signature verification only. Single-use nonce consumption stays with
        `scripts/trusted_launcher.py`, which owns the ledger: a policy
        evaluation must not have side effects, or merely *asking* whether an
        action is permitted would burn the grant.
        """
        if not (request.mutating and request.resource.startswith("mount:")):
            return []
        grant = request.launch_grant
        if not grant:
            return [
                f"write-capable mount {request.resource!r} requires a signed one-time "
                "launch grant; none was presented"
            ]
        mount = request.resource.split(":", 1)[1]
        payload = {key: grant.get(key) for key in ("mount", "issued_at", "expires_at", "nonce")}
        if payload["mount"] != mount:
            return [f"grant is for mount {payload['mount']!r}, not {mount!r}"]
        key_path = Path(request.launch_key_path or DEFAULT_LAUNCH_KEY)
        if not key_path.exists():
            return ["no launch signing key is present, so the grant cannot be verified"]
        expected = _sign_grant(key_path.read_bytes(), payload)
        if not hmac.compare_digest(expected, str(grant.get("sig", ""))):
            return ["launch grant signature is invalid"]
        now = request.now or datetime.datetime.now(datetime.UTC)
        try:
            expires = float(payload["expires_at"])
        except (TypeError, ValueError):
            return ["launch grant has no usable expiry"]
        if now.timestamp() > expires:
            return ["launch grant has expired"]
        return []


def enforce(
    request: ToolRequest,
    *,
    pep: PolicyEnforcementPoint | None = None,
    ledger: AuditLedger | None = None,
) -> Decision:
    """Authorize a tool invocation or raise. Call immediately before execution.

    Raising rather than returning a falsy value on denial is deliberate: a
    caller that ignores a return value silently proceeds, and a policy decision
    a caller can ignore is not an enforcement point.
    """
    pep = pep or PolicyEnforcementPoint()
    decision = pep.evaluate(request)
    if ledger is not None:
        ledger.append(
            "policy_allowed" if decision.allowed else "policy_denied",
            {
                "agent": request.agent,
                "action": request.action,
                "resource": request.resource,
                "mutating": request.mutating,
                "reasons": list(decision.reasons),
            },
        )
    if not decision.allowed:
        raise PolicyDenied(request, list(decision.reasons))
    return decision
