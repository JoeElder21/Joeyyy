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
import posixpath
import re
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

# Resource prefixes that denote a connector or MCP mount rather than a memory
# namespace or write target. Under the packet-only policy these are Agent 007's
# alone -- a specialist reaches them through a packet, never directly.
CONNECTOR_PREFIXES = ("mount:", "connector:")

# Repository surfaces that belong to neither brain, so a specialist touching
# them is not a brain-isolation event. Declared as data because the brain lock
# now fails closed on any resource whose owner it cannot resolve: without an
# explicit neutral set, "cannot classify" would deny reading the contract that
# defines the classification.
BRAIN_NEUTRAL_PREFIXES = (
    "docs/",
    "schemas/",
    "templates/",
    "scripts/",
    "tests/",
    "runtime/",
    "config/",
    "AGENTS.md",
    "README.md",
    "CLAUDE.md",
)

# The only schemas that can authorize a tool invocation. `packet_schema` is a
# caller-supplied string, so without this list a caller could point it at
# `writer_lease.schema.json` (or any other schema in schemas/) and satisfy
# packet admission with an object that authorizes nothing -- a lease, a memory
# record, a roundtable memo. Admission checked that the packet was *valid*
# without ever checking it was the *kind of thing that grants permission*.
AUTHORIZATION_SCHEMAS = frozenset(
    {
        "delegation_packet.schema.json",
        "handoff_packet.schema.json",
    }
)

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

# Action fragments that read without changing anything. THIS IS AN ALLOWLIST,
# and the direction is the whole point.
#
# The first version was the inverse: a list of mutating verbs, with anything
# unlisted treated as a read. That is fail-open by construction -- it protects
# against the verbs someone thought of and silently waves through every verb
# they did not. The configured filesystem mount exposes `edit_file` and
# `move_file`; neither `edit` nor `move` was on the mutating list, so
# `action="edit_file"` on `mount:filesystem` was classified as a read and
# skipped the lease, lifecycle, and launch-grant rules entirely. Extending the
# denylist by two entries would have fixed the instance and left the class.
#
# Inverted, an action nobody anticipated is a mutation, which costs a lease.
# That is the correct direction of error: over-classifying a read is an
# inconvenience, under-classifying a write forfeits every mutation control at
# once.
READ_ONLY_ACTION_VERBS = frozenset(
    {
        "read",
        "list",
        "get",
        "search",
        "find",
        "view",
        "query",
        "inspect",
        "describe",
        "show",
        "count",
        "diff",
        "status",
        "info",
        "tree",
        "fetch",
        "peek",
    }
)

# Retained for documentation and tests: these must classify as mutating under
# any implementation. They are no longer the mechanism -- the allowlist above
# is -- so this list going stale can no longer open a hole.
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
    "set",
    "put",
    "post",
    "edit",
    "move",
    "rename",
    "copy",
    "purge",
    "drop",
    "truncate",
    "revoke",
    "grant",
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
    # The write verb the executor will actually perform (`append`, `replace`,
    # `delete`), matched against what the packet proposed. Without it, every
    # check bound *where* a write lands and none bound *what it does*.
    operation: str | None = None
    # Signed grant material, not an assertion. `launch_grant_verified` used to be
    # a plain bool the caller set, which is the same "trust the caller" defect as
    # the mutating flag: any caller could claim a grant it never held.
    launch_grant: dict[str, Any] | None = None
    # The third instance of that same defect, and the one that took longest to
    # find. `explicit_instruction: bool = False` let any caller authorize a
    # financial transaction, an access change, or a public publication by
    # setting a flag -- the very boundary AGENTS.md reserves for Joe. It is now
    # signed material bound to this action and this resource, verified with the
    # launcher's own primitive so a grant for `read` on one target cannot be
    # replayed against `financial_transaction` on another.
    instruction_grant: dict[str, Any] | None = None
    # Authoritative ledgers, forwarded to PacketGuard. Supplying none of these
    # meant the guard rejected any delegation that referenced a validated
    # constraint, or carried a real lease, as unvalidated -- so a lawful
    # constraint-backed request could not pass admission at all. The guard needs
    # the same context here that it gets at real admission, or this gate is
    # stricter than the one it consolidates in a way that denies correct work.
    active_leases: tuple[Any, ...] = ()
    delegations: tuple[Any, ...] = ()
    constraint_packets: tuple[Any, ...] = ()
    private_constraint_packets: tuple[Any, ...] = ()


@dataclass
class Decision:
    """Allow or deny, with the reasons either way.

    `request` is the *normalized* request the rules actually saw, not the one
    the caller handed in. Without it, an audit record built from the caller's
    object describes a different request than the one that was judged — an
    inferred mutation logged as `mutating: false`, a `FINANCIAL_TRANSACTION`
    logged in whatever casing it arrived in. Incident review reads the ledger,
    so the ledger has to hold the evaluated form.
    """

    allowed: bool
    reasons: tuple[str, ...] = ()
    checks_run: tuple[str, ...] = field(default_factory=tuple)
    request: ToolRequest | None = None

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
        launch_key_path: Path | None = None,
        clock: Any | None = None,
    ) -> None:
        self.root = root
        # The clock belongs to the enforcement point, for the same reason the
        # signing key does. Expiry was compared against `ToolRequest.now`, which
        # the caller supplies -- so anyone holding an expired instruction could
        # replay it by backdating the request. A grant that expired in 2020 was
        # accepted with `now` set before its expiry. Injectable only so tests
        # can pin it; no request can move it.
        self._clock_fn = clock or (lambda: datetime.datetime.now(datetime.UTC))
        # The trust anchor belongs to the enforcement point, not to the request.
        # `ToolRequest.launch_key_path` let a caller write its own key file,
        # sign a `financial_transaction` instruction with it, point the request
        # at it, and be believed -- so the signature checks proved only that the
        # caller could sign, which every caller can. Verifying a signature
        # against a key the signer chose is not verification.
        self.launch_key_path = Path(launch_key_path or DEFAULT_LAUNCH_KEY)
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
        action = (request.action or "").strip().lower()
        if action in HIGH_IMPACT_ACTIONS:
            return True
        # Allowlist, matched as a LEADING TOKEN -- not as a substring.
        #
        # The previous round replaced a mutating denylist with this allowlist
        # and kept substring matching, which fails open just as badly in the
        # other direction: `delete_thread` contains "read", `update_status`
        # contains "status", `remove_from_list` contains "list", and
        # `spreadsheet_update` contains "read". All four classified as reads and
        # skipped the lease, lifecycle, packet, and launch-grant controls.
        #
        # Inverting the list was the right move and the matching was still
        # wrong, which is worth stating plainly: the fix to a fail-open check
        # was itself fail-open. Only the verb position carries the intent, so
        # only the verb position is consulted.
        tokens = [token for token in re.split(r"[^a-z]+", action) if token]
        if not tokens or tokens[0] not in READ_ONLY_ACTION_VERBS:
            return True
        # Backstop: a read-leading compound whose tail names a mutation
        # (`list_purge`) is still a mutation. This is a denylist, but it can
        # only ever ADD strictness -- the allowlist above already defaults to
        # mutating -- so it going stale cannot open a hole the way the original
        # denylist did.
        return any(token in MUTATING_ACTION_VERBS for token in tokens[1:])

    @staticmethod
    def normalize(request: ToolRequest) -> tuple[ToolRequest, list[str]]:
        """Put the request in the one form every rule reads.

        Two separate defects lived in the gap between "what the caller sent" and
        "what a rule happened to look at":

        * `_is_mutating()` lowercased the action; `_high_impact_boundary()` did
          not. `action="FINANCIAL_TRANSACTION"` was therefore classified as a
          mutation *and* walked past the explicit-instruction boundary, because
          the boundary compared a raw string against a lowercase frozenset.
          Normalizing in one place, once, is the only version of this that does
          not regress the moment a ninth rule is added.

        * A timezone-naive `now` compared against a timezone-aware lease expiry
          raises `TypeError` rather than denying. An enforcement point that
          raises on an input a caller can supply by writing the obvious
          `datetime.datetime.now()` is not fail-closed, it is a crash. Naive
          clocks are rejected as a reason, and dropped so the remaining rules
          still evaluate against real UTC instead of exploding.
        """
        errors: list[str] = []
        normalized = request

        action = (request.action or "").strip().lower()
        if action != request.action:
            normalized = replace(normalized, action=action)

        if PolicyEnforcementPoint._is_mutating(normalized) and not normalized.mutating:
            normalized = replace(normalized, mutating=True)

        return normalized, errors

    def evaluate(self, request: ToolRequest) -> Decision:
        # Normalize once, up front, so every rule sees the same answer to
        # "which action is this, is it a mutation, and what time is it".
        request, reasons = self.normalize(request)
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

        return Decision(
            allowed=not reasons,
            reasons=tuple(reasons),
            checks_run=tuple(checks),
            request=request,
        )

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
        # Refused before any prefix comparison. A resource that climbs out of
        # the tree cannot be classified as owned or neutral, and guessing is
        # how `scripts/../brains/jeos/agents.toml` read as neutral.
        if self._escapes_the_tree(request.resource):
            errors.append(
                f"brain lock: resource {request.resource!r} escapes the repository once "
                "normalized, so its owning brain cannot be established"
            )
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
        elif resource_brain is None and not self._is_brain_neutral(request.resource):
            # Unresolvable ownership was treated as no objection, so the lock
            # held only over resources whose names happened to match a manifest
            # prefix. `brains/jeos/agents.toml` is plainly JEOS material and
            # resolved to nothing, so an APEX specialist reading it passed.
            #
            # "I cannot tell who owns this" is not "anyone may have it". The
            # brain-neutral list below is what makes that answerable rather than
            # an outage: shared repository surfaces are declared, everything
            # else must be classifiable or it is refused.
            errors.append(
                f"brain lock: cannot resolve which brain owns {request.resource!r}, "
                f"and an unclassifiable resource is not established as {agent_brain!r}'s "
                f"to touch; name it under a manifest-declared prefix or a brain-neutral one"
            )
        return errors

    @staticmethod
    def _canonical_resource(resource: str) -> str:
        """Collapse a resource to the path an executor would actually open.

        Both prefix checks compared the caller's raw string, so
        `scripts/../brains/jeos/agents.toml` matched the `scripts/` neutral
        prefix and was waved through — while a filesystem executor resolving
        that same string opens the JEOS manifest. The policy and the executor
        disagreed about what the resource *was*, which makes every prefix
        comparison downstream meaningless.

        This is the third traversal defect in this change set, after the
        `--run-id` output escape and its Windows-separator sibling. Comparing
        unnormalised paths is apparently a reflex worth distrusting.
        """
        if ":" in resource.split("/", 1)[0]:
            return resource  # mount:/connector: handles are opaque, not paths
        return posixpath.normpath(resource.replace("\\", "/"))

    @staticmethod
    def _escapes_the_tree(resource: str) -> bool:
        """A resource that climbs out of the repository cannot be classified."""
        canonical = PolicyEnforcementPoint._canonical_resource(resource)
        return canonical.startswith(("../", "/")) or canonical == ".."

    @staticmethod
    def _is_brain_neutral(resource: str) -> bool:
        """Shared repository surfaces that belong to neither brain.

        Compared after normalization, and tolerant of the directory itself:
        `normpath("docs/")` is `"docs"`, which does not start with `"docs/"`.
        """
        canonical = PolicyEnforcementPoint._canonical_resource(resource)
        return any(
            canonical == prefix.rstrip("/") or canonical.startswith(prefix)
            for prefix in BRAIN_NEUTRAL_PREFIXES
        )

    def _resource_owner(self, resource: str) -> str | None:
        """Which brain owns this resource, by manifest-declared prefix or path."""
        canonical = self._canonical_resource(resource)
        for prefix, owner in self.brain_prefixes.items():
            if canonical.startswith(prefix):
                return owner
        # Repository paths under `brains/<brain>/` are that brain's material as
        # plainly as its namespace is, but carry none of the declared prefixes,
        # so ownership resolution missed them entirely.
        lowered = canonical.lower()
        for brain in ("apex", "jeos"):
            if lowered.startswith(f"brains/{brain}/"):
                return brain.upper()
        return None

    def _is_canonical_resource(self, resource: str) -> bool:
        """A durable resource, as opposed to text carried in the message itself.

        Canonical means the request reaches past the conversation: a brain's
        memory namespace or write target, a connector mount, or a path in this
        repository. Reading any of those is governed work and needs a
        delegation behind it.
        """
        if any(resource.startswith(prefix) for prefix in CONNECTOR_PREFIXES):
            return True
        if self._resource_owner(resource) is not None:
            return True
        return self._is_brain_neutral(resource) or self._escapes_the_tree(resource)

    def _connector_policy(self, request: ToolRequest) -> list[str]:
        spec = self._spec(request.agent)
        policy = spec.get("connector_policy")
        if policy is None or request.agent == CHIEF:
            return []
        if policy != PACKET_ONLY:
            return [f"connector policy {policy!r} is not the approved {PACKET_ONLY!r}"]
        # `packet_only_no_direct_connectors` is a statement about *reads* as much
        # as writes. Only the mutating path was guarded, so a shadow specialist
        # could read `mount:gdrive` directly and be allowed -- the exact direct
        # connector access the policy name forbids. Checking the policy string
        # and then permitting the thing it prohibits is not enforcement.
        if any(request.resource.startswith(prefix) for prefix in CONNECTOR_PREFIXES):
            return [
                f"{request.agent!r} is {PACKET_ONLY!r} and may not touch connector "
                f"resource {request.resource!r} directly, read or write; "
                f"{CHIEF} performs connector work on its behalf"
            ]
        return []

    def _packet_admission(self, request: ToolRequest) -> list[str]:
        # An unrecognised schema is refused before the packet is read at all.
        # `packet_schema` is caller-supplied: pointing it at a non-authorization
        # schema let a caller satisfy admission with a schema-valid object that
        # grants nothing -- a writer lease, a memory record -- so the check
        # proved wellformedness where it was supposed to prove permission.
        if request.packet_schema not in AUTHORIZATION_SCHEMAS:
            return [
                f"packet schema {request.packet_schema!r} does not authorize a tool "
                f"invocation; admission accepts only {sorted(AUTHORIZATION_SCHEMAS)}"
            ]
        if request.packet is None:
            if request.mutating:
                return ["mutating request carries no packet; packet-only policy admits nothing"]
            # Reads needed a packet too, and did not require one. AGENTS.md
            # confines packetless direct invocation to current-message text;
            # a canonical memory namespace, write target, or repository path is
            # none of those. Without this, `apex_war_architect` could read
            # `APEX/Intel-Sources` -- another specialist's canonical source --
            # with no delegation authorizing it and no reason recorded.
            #
            # The chief is exempt because it issues the delegations.
            if request.agent != CHIEF and self._is_canonical_resource(request.resource):
                return [
                    f"read of canonical resource {request.resource!r} requires a validated "
                    "delegation; the packetless path is confined to current-message text"
                ]
            return []
        # A packet that is not an object cannot be scope-checked. `.get()` on a
        # scalar raises AttributeError, so hostile input crashed the evaluation
        # instead of denying it -- and a gate that raises on input a caller
        # controls is a denial of service on every other caller in the process,
        # not a fail-closed decision.
        if not isinstance(request.packet, dict):
            return [f"packet rejected: $: expected an object, got {type(request.packet).__name__}"]
        errors = [
            f"packet rejected: {error}"
            for error in self.guard.validate(
                request.packet_schema,
                request.packet,
                # The authoritative ledgers. Without them the guard cannot
                # resolve a referenced constraint or confirm a lease is uniquely
                # active, so it refused lawful packets -- and the separate lease
                # rule cannot lift a denial raised during admission.
                self._lease_ledger(request),
                delegations=list(request.delegations),
                constraint_packets=list(request.constraint_packets),
                private_constraint_packets=list(request.private_constraint_packets),
            )
            # The SAME narrow tolerance `_writer_lease` applies, and it has to be
            # here too. Deriving this ledger from the registry (previous round)
            # started feeding the guard genuine `schema_version: "2.1"` leases,
            # which its schema pins to "2.0" -- so admission rejected every
            # mutation backed by the real LeaseRegistry, and the later filter in
            # `_writer_lease` cannot lift an error raised at this stage.
            #
            # That made the gate deny all legitimate mutations: the second
            # fail-shut defect this change set has produced, both of them
            # introduced by a fix rather than found in the original code. The
            # underlying 2.1-vs-2.0 mismatch is still a contract decision for
            # Joe; this keeps the tolerance consistent wherever leases are read.
            if VERSION_MISMATCH_DEFECT not in error
        ]
        # Scope binding only runs on a packet that survived validation. Running
        # it on a rejected packet reads fields from a structure the guard has
        # already said it cannot vouch for.
        if errors:
            return errors
        return self._packet_scope_errors(request)

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
        # Required on mutations, for the chief too. `_brain_lock` exempts the
        # chief because it is the sole cross-brain agent, which left the brain
        # comparison here and in `_packet_scope_errors` both conditional on a
        # field the chief could simply omit. A schema-valid JEOS handoff could
        # then be paired with a genuine APEX lease for the same `resource_id`
        # and authorize an APEX write -- cross-brain leakage through the one
        # agent permitted to see both sides, which is exactly the actor the
        # isolation rules exist to constrain.
        if not request.owner_brain:
            errors.append(
                "mutation declares no owner_brain; being the cross-brain agent permits "
                "acting for either brain, not for an unstated one"
            )
        elif lease.get("owner_brain") != request.owner_brain:
            errors.append(
                f"lease is scoped to {lease.get('owner_brain')!r}, request declares "
                f"{request.owner_brain!r}"
            )
        target = lease.get("write_target")
        # Exact equality, matching PacketGuard's authoritative lease matching.
        # `startswith` silently widened every lease to its own prefix family: a
        # genuine lease for `APEX/Strategy-Campaigns` covered
        # `APEX/Strategy-Campaigns-Evil`, and any target an attacker could name
        # by appending characters. There is no declared resource hierarchy in
        # this repository, so prefix containment was inventing an authorization
        # relationship rather than reading one.
        if target and request.resource and request.resource != target:
            errors.append(f"lease covers {target!r}, which does not cover {request.resource!r}")
        # Required, not merely compared-when-present. Omitting `resource_id`
        # skipped record-level matching here AND in `_packet_scope_errors`, so a
        # lease and packet issued for record A authorized an executor request
        # that writes record B under the same write target -- the caller simply
        # left the record identity out. An optional identifier that the checks
        # only honour when supplied is an opt-out, and this is the one field
        # that distinguishes which row actually changes.
        if not request.resource_id:
            errors.append(
                "mutation declares no resource_id; the lease and packet are issued per "
                "record, so a write with no record identity cannot be matched to either"
            )
        elif lease.get("resource_id") != request.resource_id:
            errors.append(
                f"lease is for resource {lease.get('resource_id')!r}, request targets "
                f"{request.resource_id!r}"
            )
        errors.extend(self._lease_expiry_errors(lease, request))
        return errors

    def _lease_ledger(self, request: ToolRequest) -> list[Any]:
        """The lease ledger PacketGuard validates against, from the registry.

        Forwarding `request.active_leases` handed the guard a ledger the caller
        wrote. A caller who knew a genuine active lease id could submit a
        schema-valid fabricated entry carrying that id but a different
        `mission_id`, have the guard validate a write-bearing packet against the
        fabricated mission, and then pair it with the real registry lease --
        which matches on brain, target, resource, and writer, so
        `_writer_lease` raises no objection either. Two checks, each satisfied
        by a different object.

        The registry is authoritative when present; the caller's copy is used
        only when there is none, and in that case `_writer_lease` already
        refuses every mutation.
        """
        if self.registry is None:
            return list(request.active_leases)
        issued = getattr(self.registry, "_active", None)
        if isinstance(issued, dict):
            return [dict(lease) for lease in issued.values()]
        # Unknown registry shape: fall back to the one lease we can look up
        # authoritatively rather than trusting the submitted ledger.
        _, verified = self._registry_membership(request.lease or {})
        return [verified] if verified else []

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
            # The chief executes what shadow specialists propose, so a packet it
            # acts on names the specialist, not itself. Requiring the chief to
            # be the addressee deadlocked the only lawful mutation path in the
            # system: the specialist is blocked by `_lifecycle_stage`, the chief
            # was blocked here, and addressing the packet to the chief is not an
            # option because PacketGuard expects a registered specialist.
            #
            # Execution authority comes from the lease, not the addressee. The
            # chief may act on a specialist's packet only while holding the
            # writer lease for it -- which `_writer_lease` verifies against the
            # registry, so this is not a second trust decision, it is the same
            # one read from the authoritative place.
            chief_executing = request.agent == CHIEF and (
                packet.get("writer_agent") == CHIEF
                or (request.lease or {}).get("writer_agent") == CHIEF
            )
            if not chief_executing:
                errors.append(
                    f"packet addresses {addressee!r}, not the requesting agent {request.agent!r}"
                )
        brain = packet.get("owner_brain")
        if brain and request.mutating and not request.owner_brain:
            # The same omission, from the packet side. A mutating request that
            # states no brain cannot be checked against the packet's, so the
            # comparison silently passed on the one path where it matters most.
            errors.append(
                f"packet is scoped to {brain!r} but the mutating request declares no "
                "owner_brain, so the two cannot be matched"
            )
        elif brain and request.owner_brain and brain != request.owner_brain:
            errors.append(
                f"packet owner_brain {brain!r} does not match the request's {request.owner_brain!r}"
            )
        resource = packet.get("resource_id")
        if resource and request.resource_id and resource != request.resource_id:
            errors.append(
                f"packet resource {resource!r} does not match the requested {request.resource_id!r}"
            )
        errors.extend(self._packet_namespace_errors(request, packet))
        errors.extend(self._packet_operation_errors(request, packet))
        return errors

    @staticmethod
    def _handoff_scope(packet: dict[str, Any], *, mutating: bool) -> list[str] | None:
        """What a handoff is bound to, since it carries no allow-lists.

        Two corrections to the previous round, which had this wrong in both
        directions at once:

        * The field is `target`, not `write_target` -- the handoff schema names
          it `target` and requires it. Reading the wrong key meant no proposed
          write was ever found, so the mutating path always fell through to
          `memory_namespace`.
        * `memory_namespace` is where a specialist *reads*. Including it for
          mutations let a schema-valid read-only handoff, paired with a genuine
          matching lease, authorize a `replace`. A handoff that proposes no
          write authorizes no write, and there is no second-best answer.

        Returns None when nothing binds it, so the caller denies rather than
        treating an unscoped packet as an unscoped grant.
        """
        targets = [
            write["target"]
            for write in (packet.get("proposed_writes") or [])
            if isinstance(write, dict) and write.get("target")
        ]
        if mutating:
            return targets or None
        scope = [entry for entry in [packet.get("memory_namespace")] if entry]
        return (scope + targets) or None

    @staticmethod
    def _packet_operations(packet: dict[str, Any]) -> set[str]:
        """Operations the packet actually proposes or permits."""
        allowed = {
            str(operation).strip().lower()
            for operation in (packet.get("mutation_contract") or {}).get("allowed_operations", [])
        }
        for write in packet.get("proposed_writes") or []:
            if isinstance(write, dict) and write.get("operation"):
                allowed.add(str(write["operation"]).strip().lower())
        return allowed

    def _packet_operation_errors(self, request: ToolRequest, packet: dict[str, Any]) -> list[str]:
        """The executed operation must be the one the packet proposed.

        Target, resource id, brain, and lease could all match while the request
        performed a strictly more destructive operation than the validated
        packet asked for -- a packet restricted to `append` raised no objection
        against a `replace`. Matching everything about *where* a write lands and
        nothing about *what it does* is not a bound authorization.
        """
        if not request.mutating:
            return []
        allowed = self._packet_operations(packet)
        if not allowed:
            return []  # nothing proposed; the lease and target checks stand alone
        if not request.operation:
            return [
                f"packet permits operations {sorted(allowed)} but the request names none; "
                "an unstated operation cannot be matched against the one proposed"
            ]
        operation = request.operation.strip().lower()
        if operation not in allowed:
            return [f"packet proposes {sorted(allowed)}, not {operation!r}"]
        return []

    def _packet_namespace_errors(self, request: ToolRequest, packet: dict[str, Any]) -> list[str]:
        """The packet must authorize *this* resource, not merely exist.

        Requiring a delegation for canonical reads (previous round) stopped
        packetless access but accepted any valid same-brain packet: a War
        Architect delegation scoped to `APEX::Strategy-Campaigns` authorized a
        read of `APEX/Intel-Sources`, another specialist's source. A delegation
        that does not name the resource does not authorize it -- otherwise
        holding any delegation is holding all of them, and the bounded
        assignment the packet exists to express means nothing.
        """
        # Selected by operation kind, never unioned. Merging the two lists let a
        # read-only delegation authorize a write: the chief could pair a
        # Strategy-Campaigns delegation granting only `allowed_read_namespaces`
        # with a genuine lease for that target and pass, though
        # `allowed_write_targets` was empty. The lease proves exclusive
        # execution; it does not prove the bounded assignment permitted a write.
        if request.mutating:
            declared = list(packet.get("allowed_write_targets", []))
            kind = "write"
        else:
            declared = list(packet.get("allowed_read_namespaces", []))
            kind = "read"

        if not declared:
            # A handoff carries no allow-lists, so it used to reach an
            # unconditional success path -- and "declares no scope" was read as
            # "unrestricted scope", which is the fail-open shape this module
            # keeps rediscovering. A handoff is bound to its own
            # memory_namespace, and failing that to nothing at all.
            fallback = self._handoff_scope(packet, mutating=request.mutating)
            if fallback is None:
                return [
                    f"packet declares no scope permitting a {kind} of "
                    f"{request.resource!r}; absent scope is not unrestricted scope"
                ]
            declared = fallback
        resource = self._canonical_resource(request.resource)
        for entry in declared:
            # Namespaces are written `APEX::Strategy-Campaigns::agent` and write
            # targets `APEX/Strategy-Campaigns`; compare on the shared segments
            # rather than demanding one spelling.
            normalized = str(entry).replace("::", "/")
            if resource == normalized or resource.startswith(f"{normalized}/"):
                return []
            if normalized.startswith(f"{resource}/"):
                return []
        return [
            f"packet does not authorize {request.resource!r}; it is scoped to "
            f"{sorted(str(entry) for entry in declared)}"
        ]

    def _clock(self, request: ToolRequest | None = None) -> datetime.datetime:
        """The comparison clock: enforcement-owned, always timezone-aware.

        `request` is accepted and ignored, so existing call sites read the same
        way. It used to be the source, which made every expiry check advisory:
        a caller could present a genuinely signed instruction that expired years
        ago and set the clock to just before its expiry.
        """
        now = self._clock_fn()
        if now.tzinfo is None:
            return now.replace(tzinfo=datetime.UTC)
        return now

    def _lease_expiry_errors(self, lease: dict[str, Any], request: ToolRequest) -> list[str]:
        """An expired lease is a closed lease. Unparseable timestamps fail closed."""
        expiry = lease.get("expires_at")
        if not expiry:
            return ["lease declares no expiry"]
        now = self._clock(request)
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
        """The boundary AGENTS.md reserves for Joe, verified rather than asserted.

        This was `explicit_instruction: bool = False` — the third appearance of
        the same defect, after `mutating` and `launch_grant_verified`, and the
        one with the worst blast radius: a caller could authorize a financial
        transaction, a credential change, or a public publication by setting a
        flag on its own request. The control guarding the actions Joe must
        personally sanction was the one a caller could sanction for itself.

        The grant is bound to *this* action and *this* resource, so an
        instruction for one boundary action cannot be replayed against another.
        Signature only; nonce consumption stays with the launcher, because a
        policy evaluation must not have side effects.
        """
        # Compare the normalized action. `evaluate()` normalizes before any rule
        # runs; lowercasing again here keeps a directly-invoked rule honest
        # rather than making the boundary depend on the caller's entry point.
        action = (request.action or "").strip().lower()
        if action not in HIGH_IMPACT_ACTIONS:
            return []
        grant = request.instruction_grant
        if grant is not None and not isinstance(grant, dict):
            # `.get()` on a truthy scalar raises AttributeError. The packet path
            # was type-checked a round earlier and both grant paths were left
            # alone -- the sibling-untouched pattern once more.
            return [f"instruction grant must be an object, got {type(grant).__name__}"]
        if not grant:
            return [
                f"{action!r} is a high-impact boundary and requires a signed "
                "task-level instruction from Joe; none was presented"
            ]
        payload = {
            "action": grant.get("action"),
            "resource": grant.get("resource"),
            "issued_at": grant.get("issued_at"),
            "expires_at": grant.get("expires_at"),
            "nonce": grant.get("nonce"),
        }
        if payload["action"] != action:
            return [f"instruction authorizes {payload['action']!r}, not {action!r}"]
        if payload["resource"] != request.resource:
            return [f"instruction is scoped to {payload['resource']!r}, not {request.resource!r}"]
        key_path = self.launch_key_path
        if not key_path.exists():
            return ["no signing key is present, so the instruction cannot be verified"]
        expected = _sign_grant(key_path.read_bytes(), payload)
        if not hmac.compare_digest(expected, str(grant.get("sig", ""))):
            return ["instruction signature is invalid"]
        try:
            expires = float(payload["expires_at"])
        except (TypeError, ValueError):
            return ["instruction has no usable expiry"]
        if self._clock(request).timestamp() > expires:
            return ["instruction has expired"]
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
        if grant is not None and not isinstance(grant, dict):
            return [f"launch grant must be an object, got {type(grant).__name__}"]
        if not grant:
            return [
                f"write-capable mount {request.resource!r} requires a signed one-time "
                "launch grant; none was presented"
            ]
        mount = request.resource.split(":", 1)[1]
        payload = {key: grant.get(key) for key in ("mount", "issued_at", "expires_at", "nonce")}
        if payload["mount"] != mount:
            return [f"grant is for mount {payload['mount']!r}, not {mount!r}"]
        key_path = self.launch_key_path
        if not key_path.exists():
            return ["no launch signing key is present, so the grant cannot be verified"]
        expected = _sign_grant(key_path.read_bytes(), payload)
        if not hmac.compare_digest(expected, str(grant.get("sig", ""))):
            return ["launch grant signature is invalid"]
        now = self._clock(request)
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
    # Record what was *judged*, not what was submitted. Logging the caller's
    # object described an inferred mutation as `mutating: false` and a
    # `FINANCIAL_TRANSACTION` in its original casing, so the audit trail
    # disagreed with the decision it was recording — precisely when it matters,
    # during incident review.
    judged = decision.request or request
    if ledger is not None:
        ledger.append(
            "policy_allowed" if decision.allowed else "policy_denied",
            {
                "agent": judged.agent,
                "action": judged.action,
                "action_as_submitted": request.action,
                "resource": judged.resource,
                "mutating": judged.mutating,
                "mutation_derived": judged.mutating and not request.mutating,
                "reasons": list(decision.reasons),
            },
        )
    if not decision.allowed:
        raise PolicyDenied(request, list(decision.reasons))
    return decision
