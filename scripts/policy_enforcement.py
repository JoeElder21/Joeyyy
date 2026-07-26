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

# The exact fields `trusted_launcher.issue_grant` signs, in its order. An
# HMAC is over the whole dict, so a verifier reconstructing a different set
# rejects every valid grant -- which is what happened when the issuer gained
# `agent` and this module kept rebuilding four keys.
LAUNCH_GRANT_SIGNED_FIELDS = ("mount", "agent", "issued_at", "expires_at", "nonce")

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
        # Added when the JOEYYY constitution superseded the six-item list.
        # AGENTS.md section 9 now also reserves final permit or agency
        # submission, scheduled-task creation or deletion, and modification of
        # Separation governance or canonical brain masters and snapshots -- and
        # its changelog says so explicitly: "Section 9's live-approval list
        # supersedes the prior six-item explicit-instruction list."
        #
        # Keeping six while the contract said nine is the exact shape this
        # record calls a control that has quietly stopped covering what it
        # claims: `submit_permit` and `create_scheduled_task` reached the
        # boundary and it raised no objection.
        "final_submission",
        "scheduled_task_change",
        "governance_or_master_change",
    }
)

# Concrete tool verbs that ARE one of the boundary categories above.
#
# Kept as an explicit map rather than inferred: a wrong entry here would demand
# Joe's signature for ordinary work, and a missing one lets a boundary action
# past, so both directions are worth stating by hand and testing. This is a
# floor, not a claim of completeness -- a dispatcher that knows its tool's
# category should pass the category, and this map catches the common verbs a
# caller would naturally use instead.
HIGH_IMPACT_VERBS = {
    "publish": "public_publication",
    "post": "public_publication",
    "send": "public_publication",
    "broadcast": "public_publication",
    "transfer": "financial_transaction",
    "pay": "financial_transaction",
    "purchase": "financial_transaction",
    "invoice": "financial_transaction",
    "sign": "sign_or_certify_professional_work",
    "certify": "sign_or_certify_professional_work",
    "seal": "sign_or_certify_professional_work",
    "stamp": "sign_or_certify_professional_work",
    "purge": "irreversible_bulk_deletion",
    "truncate": "irreversible_bulk_deletion",
    "drop": "irreversible_bulk_deletion",
    "wipe": "irreversible_bulk_deletion",
    "revoke": "credential_or_access_change",
    "grant": "credential_or_access_change",
    "rotate": "credential_or_access_change",
    "authorize": "credential_or_access_change",
    # Section 9's three additions, mapped to the verbs a dispatcher emits.
    # `submit` alone is deliberately NOT here: submitting a form to an internal
    # queue is ordinary work, and only a FINAL permit or agency submission is
    # reserved. The qualifier carries the meaning, so the compound is matched
    # via SUBMISSION_QUALIFIERS below rather than by the bare verb.
    "overwrite": "irreversible_bulk_deletion",
}

# `binding_legal_commitment` was in HIGH_IMPACT_ACTIONS from the start with NO
# verb mapped to it, so it fired only when a caller volunteered the category
# name as its own action -- the "controls that ask the caller to incriminate
# itself" shape removed elsewhere in this module. `accept_contract`,
# `execute_agreement` and `agree_to_terms` all reached the fallback unchanged.
#
# Compound, like the submission and schedule rules, and for the same reason
# learned the same way: the first attempt mapped the bare verbs, which gated
# `execute_query`, `commit_message` and `accept_row` -- ordinary database, git
# and data work. The verb alone carries no legal meaning; the OBJECT does.
LEGAL_COMMITMENT_VERBS = frozenset(
    {"accept", "agree", "commit", "countersign", "execute", "ratify", "bind", "enter"}
)
LEGAL_COMMITMENT_NOUNS = frozenset(
    {
        "contract",
        "agreement",
        "terms",
        "deed",
        "covenant",
        "waiver",
        "settlement",
        "nda",
        "msa",
        "sow",
        "engagement",
        "undertaking",
    }
)

# `submit` is gated only when qualified as a final or external submission.
# Gating every `submit` would demand Joe's signature for saving a draft, and a
# boundary that fires on ordinary work is one an operator learns to wave
# through -- the same reasoning that keeps `read` out of the issuer.
SUBMISSION_QUALIFIERS = frozenset({"permit", "agency", "final", "submission"})

# Scheduled-task creation or deletion. The SCHEDULING marker is what makes it
# gated: a `create` or `delete` of a SCHEDULE is reserved, while creating a
# record is not, so both a marker and a change verb must be present.
#
# `task` was in the noun set and is the whole finding. AGENTS.md reserves
# "scheduled-task creation or deletion", and a bare `task` is not a schedule --
# so `create_task` and `delete_task`, ordinary task-registry writes, demanded
# Joe's personally signed instruction. A boundary that fires on ordinary work is
# one an operator learns to wave through, which is the reasoning that already
# keeps `read` out of the issuer and `submit` behind a qualifier.
#
# Removing it exposed the opposite defect in the same rule. `schedule_task` --
# about as literal a scheduled-task creation as exists -- was ALREADY ungated,
# because both its tokens were nouns and the rule demanded a verb. Fixing only
# the over-gate would have left that.
#
# So the scheduling act itself counts as a verb, but POSITIONALLY: only when it
# leads the action name. Accepting `schedule` as a verb anywhere let one token
# satisfy both halves of the rule and gated `read_schedule` and `view_schedule`
# -- reading a schedule is not changing one, and that is the same over-gate this
# finding is about, reintroduced by its own fix. The leading token of an action
# is its verb everywhere in this codebase (`create_task`, `read_record`,
# `publish_report`), so position carries real information here rather than being
# a convenient tiebreak.
#
# Markers match as a substring of a TOKEN, never of the whole action, so word
# boundaries survive -- `unschedule` and `rescheduled` carry the marker while
# `multitasking` does not acquire one.
SCHEDULE_MARKERS = ("schedul", "cron", "crontab", "timer")
SCHEDULE_VERBS = frozenset({"create", "delete", "remove", "add", "register", "unregister"})
# Verb forms OF scheduling, which need no separate change verb because they are
# one. Checked only in leading position.
SCHEDULE_ACT_VERBS = frozenset({"schedule", "unschedule", "reschedule"})


def _is_schedule_marker(token: str) -> bool:
    """Whether one action token names a scheduling mechanism."""
    return any(marker in token for marker in SCHEDULE_MARKERS)


def _changes_a_schedule(tokens: tuple[str, ...]) -> bool:
    """Whether the action both names a schedule and changes it."""
    if not any(_is_schedule_marker(token) for token in tokens):
        return False
    if any(token in SCHEDULE_VERBS for token in tokens):
        return True
    return bool(tokens) and tokens[0] in SCHEDULE_ACT_VERBS


# Separation governance and canonical brain masters/snapshots.
GOVERNANCE_NOUNS = frozenset(
    {"separation", "governance", "master", "masters", "snapshot", "snapshots", "canonical"}
)
GOVERNANCE_VERBS = frozenset(
    {"modify", "change", "update", "edit", "alter", "rewrite", "overwrite"}
)

# A destructive verb plus a wholesale qualifier is a bulk deletion, even though
# neither token carries that meaning alone. `delete` is an ordinary mutation the
# writer lease governs; `delete_all` is one of the six actions AGENTS.md
# reserves for Joe.
DESTRUCTIVE_VERBS = frozenset({"delete", "remove", "destroy", "erase", "clear", "prune"})
BULK_QUALIFIERS = frozenset({"all", "everything", "bulk", "mass", "entire", "batch"})

# Word boundaries inside an action name, camelCase included.
#
# Both places that tokenize an action lowercased it FIRST and then split on
# non-alpha, which erases every camelCase boundary: `deleteAll` became the
# single token `deleteall`, so the high-impact map -- which matches by token
# equality -- saw nothing it recognised. `deleteAll`, `publishReport`,
# `sendEmail`, and `rotateCredentials` all walked past the boundary Joe
# reserves for himself, while their underscore spellings were classified
# correctly. A dispatcher's naming convention should not decide whether a
# control fires.
#
# Written once and used by both call sites deliberately. The last three rounds
# each produced a defect from fixing one site and leaving its sibling, and this
# is the same tokenizer serving `_is_mutating` and `_boundary_category`.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _action_tokens(action: str) -> list[str]:
    """Lower-case word tokens of an action, splitting camelCase before folding."""
    spaced = _CAMEL_BOUNDARY.sub(" ", action or "")
    return [token for token in re.split(r"[^a-z0-9]+", spaced.lower()) if token]


def _canonical_action(action: str) -> str:
    """The one spelling every rule reads: lower `snake_case`, boundaries kept.

    `deleteAll`, `DELETE_ALL`, and `delete-all` are the same action, and the
    classifier must not be able to tell which spelling the caller happened to
    use. Folding case without splitting first is what let `deleteAll` through
    the high-impact boundary; splitting here means no downstream rule has to
    know that camelCase exists.
    """
    return "_".join(_action_tokens(action))


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

# The sentinel for text carried in the invocation itself, per
# docs/SPECIALIST_CORPS_PROTOCOL.md: a specialist invoked directly by Joe
# without a packet enters `direct_read_only` and may use current-message text
# only. It is not a resource -- there is nothing durable to own, and no brain
# owns it -- but the brain lock classified it as an unresolvable resource and
# denied it. Packet admission already treats it as non-canonical, so the
# documented direct-invocation path was refused by exactly one rule and had no
# lawful route at all: the third deadlock of this shape in this change set,
# after the execution-authority and brain-neutral-read ones.
CURRENT_MESSAGE = "current-message"

# `C:/…`, `c:\…`, and the UNC form. A single letter before the colon is what
# distinguishes a drive from a `mount:`/`connector:` handle, and it is the whole
# reason a Windows path was being treated as an opaque handle rather than a path.
# ANY drive-qualified path, not only drive-ABSOLUTE ones. The pattern required
# a separator after the colon, so `C:\\secret.txt` was caught while the
# drive-RELATIVE `C:..\\secret.txt` was not: separator normalization turns it
# into `C:../secret.txt`, which matches neither this pattern nor the leading
# `../` check, and Windows resolves it against the drive's current directory --
# outside the repository. `C:secret.txt` was equally uncaught. On Windows every
# drive-qualified spelling names a location this module cannot prove is inside
# the tree, so all of them are escapes.
_DRIVE_QUALIFIED = re.compile(r"^[A-Za-z]:")

# A memory namespace is `APEX::…` or `JEOS::…`. Anchored, because merely
# CONTAINING `::` was still enough to be treated as opaque -- so
# `scripts/../../outside::secret` skipped normalization AND matched the
# `scripts/` neutral prefix on its raw text, making it a packetless read of a
# path a filesystem executor resolves outside the repository. That is the same
# defect the previous round removed for a single colon, arriving through the
# clause written to replace it: the instance was fixed and the class was not.
_BRAIN_NAMESPACE = re.compile(r"^(APEX|JEOS)::", re.IGNORECASE)

# Lease statuses under which a mutation may proceed. Anything else -- released,
# verified, expired -- is a closed lease and authorizes nothing further.
ACTIVE_LEASE_STATUSES = frozenset({"active", "in_flight"})

# The known repository defect: schemas/writer_lease.schema.json pins
# schema_version to const "2.0" while runtime/writer_lease.py issues "2.1", so
# every lease the registry produces fails its own schema. Resolving which of the
# two is authoritative is a contract decision for Joe -- see
# docs/REPO_OPTIMIZATION_2026-07-25.md.
#
# Until then the enforcement point reconciles the defect rather than suppressing
# the error it produces. Suppression was tried twice and failed twice, in
# opposite directions: dropping the error string deleted the guard's ONLY finding
# (it short-circuits), and retaining it denied every legitimate write. The
# suppression that survived those two rounds was still fail-open in a third way
# -- PacketGuard.validate() returns as soon as the lease ledger has any error, so
# the packet-to-lease relationship checks (writer_lease_id uniqueness, and
# mission_id / resource_id / owner_brain / writer_agent / write_target equality)
# never ran at all. A delegation with a forged writer_lease_id and a foreign
# mission_id was admitted; reproduced before this fix.
#
# Reconciling the one field instead means the ledger validates cleanly and every
# downstream relational check executes. It is deliberately narrower than the
# filter it replaces: the filter dropped the const error whatever the actual
# version was, so a lease claiming "9.9" was tolerated too. This rewrites the
# value ONLY when it is exactly what the registry issues.
ISSUED_LEASE_SCHEMA_VERSION = "2.1"
DECLARED_LEASE_SCHEMA_VERSION = "2.0"

# The error the guard emits purely BECAUSE the ledger was withheld. It carries
# no information on the semantic pass -- that pass always omits the ledger, so
# the error is guaranteed and says nothing about the packet. Retaining it made
# every write-bearing packet fail: no governed mutation could pass at all.
LEDGER_ABSENT_ARTIFACT = "write-bearing packet requires the active writer-lease ledger"


def _is_ledger_artifact(error: str) -> bool:
    """True for the ledger-absent artifact, bare or wrapped by a nesting prefix.

    `PacketGuard` validates a handoff's originating delegation recursively and
    re-emits each inner error as `originating delegation invalid: <error>`. The
    filter compared for exact equality, so on a handoff whose delegation permits
    a write the artifact arrived wrapped, survived the filter, and denied a
    lawful write-bearing handoff even when the bound pass had its genuine
    registry lease. The fix to a fail-shut was itself fail-shut, one nesting
    level down.

    Matching the tail rather than the whole string stays within the rule this
    module keeps re-learning -- a suppression must not remove a finding it was
    not written for. On the ledger-free pass this sentence is emitted only
    because that pass withholds the ledger, at whatever nesting depth, so every
    occurrence is the artifact and none of them is informative. The bound pass
    runs WITH the ledger and still reports genuine lease-match failures.
    """
    return error == LEDGER_ABSENT_ARTIFACT or error.endswith(f": {LEDGER_ABSENT_ARTIFACT}")


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
        # The governance mount's own tools. `validate_packet`,
        # `validate_handoff_return`, and `verify_audit_ledger` inspect data and
        # change nothing, but led with verbs absent from this list, so three of
        # that mount's five tools were classified as mutations and denied for
        # lacking a packet, lease, and launch grant -- on the one mount that is
        # deliberately grant-free and available to every agent.
        "validate",
        "verify",
        "audit",
        "check",
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
    # The concurrency controls the packet's `mutation_contract` can DEMAND.
    #
    # `require_expected_version` and `require_idempotency_key` are required
    # fields of the delegation schema, so every validated packet states a
    # position on both -- and nothing read either one. A write-bearing packet
    # setting both to `true` was admitted for a request that supplied neither,
    # which is the schema declaring a control and the gate ignoring it: a
    # blind-overwrite and a double-apply both passed the check that exists to
    # stop them. Reproduced before fixing.
    #
    # Strings, both of them. An expected version is an opaque revision token in
    # every store this repository talks to (etag, revision hash, `v7`), not an
    # integer to be arithmetically compared, and typing it as one keeps
    # `normalize()`'s single string discipline instead of adding a second shape
    # for one field.
    expected_version: str | None = None
    idempotency_key: str | None = None
    # The MCP mount actually executing this invocation, carried independently of
    # `resource`.
    #
    # The launch-grant rule keyed off `resource.startswith("mount:")`, but a
    # mutation dispatched through a mount has to name its canonical write target
    # in `resource` -- that is what the packet and lease scope checks compare
    # against. So the two requirements were mutually exclusive: name the mount
    # and lose scope binding, or name the target and skip the grant entirely. A
    # fully authorized canonical mutation was allowed with no grant at all.
    #
    # This field is caller-supplied, which this module has learned to distrust
    # three separate times. It is not the same shape as those: it cannot grant
    # anything, only oblige. Setting it can add the grant requirement and never
    # remove one. But a dispatcher that OMITS it reproduces the hole, so
    # populating it is part of the dispatcher contract that wiring `enforce()`
    # has to establish -- recorded with that work, not assumed here.
    mount: str | None = None
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
        self._mounts_cache: frozenset[str] | None = None

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
        # The DECLARED OPERATION, not only the action name. `operation` is
        # documented as the verb actually performed by the executor, and it was
        # consulted by the packet and lease rules while the mutation
        # classification ignored it entirely -- so `action="read_record",
        # operation="replace"` evaluated as a read and skipped the lease,
        # lifecycle, packet and launch-grant controls with nothing presented.
        # Reproduced before fixing. A request that says it will replace a
        # record is a mutation whatever its action is called, and where the two
        # disagree the more dangerous reading is the one that must win.
        operation = (
            (request.operation or "").strip().lower() if isinstance(request.operation, str) else ""
        )
        if operation:
            operation_tokens = _action_tokens(operation)
            if not operation_tokens or operation_tokens[0] not in READ_ONLY_ACTION_VERBS:
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
        tokens = _action_tokens(action)
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

        The action is canonicalized to lower `snake_case` rather than merely
        lowercased. Folding case ALONE destroyed the word boundaries the
        high-impact classifier reads: `deleteAll` arrived at the boundary rule
        as the single token `deleteall`, matching no verb and requiring no
        instruction. The previous round fixed the classifier to split camelCase
        and left this, so the rule denied when called directly and `evaluate()`
        allowed -- and the regression test called the rule directly, which is
        why it passed. **A control is only as good as the entry point the
        system actually uses.** Canonicalizing here keeps one lowercase form
        for every rule, which is what this function exists for, while carrying
        the word boundaries through the fold instead of erasing them.
        """
        errors: list[str] = []
        normalized = request

        # Types before string operations. `resource=["docs/x"]` from malformed
        # deserialized data reached `.strip()` and raised AttributeError before
        # any rule could deny or any audit event could be written -- the
        # enforcement boundary unwound instead of refusing. `packet_schema` was
        # type-checked for this exact reason two rounds ago and every other
        # string field was left alone, so this covers the whole class: each is
        # reported AND blanked, because rules downstream call `.startswith`,
        # `.strip`, and `.lower` on them and would raise in turn.
        # `required` distinguishes the three fields every rule is a statement
        # ABOUT from the optional ones. For the required three, `None` is
        # malformed in the same way a list is: the `value is not None` guard
        # below let a null `resource` through the type check and straight into
        # `_canonical_resource`, which called `.startswith` on it and raised
        # AttributeError before any rule could deny. The optional fields keep
        # their None, because for them absence is a lawful state and blanking
        # is exactly what the check does anyway.
        blanked: dict[str, Any] = {}
        for name, value, empty, required in (
            ("agent", request.agent, "", True),
            ("action", request.action, "", True),
            ("resource", request.resource, "", True),
            ("owner_brain", request.owner_brain, None, False),
            ("resource_id", request.resource_id, None, False),
            ("operation", request.operation, None, False),
            ("expected_version", request.expected_version, None, False),
            ("idempotency_key", request.idempotency_key, None, False),
            ("mount", request.mount, None, False),
        ):
            if value is None and required:
                errors.append(
                    f"request declares no {name}; a decision cannot be made about an "
                    "unstated principal, action, or resource"
                )
                blanked[name] = empty
                continue
            if value is not None and not isinstance(value, str):
                errors.append(
                    f"request {name} must be a string, got {type(value).__name__}; "
                    "a malformed request is refused, not evaluated"
                )
                blanked[name] = empty

        # The collection fields, for the same reason and in the same place.
        # The check above covered the STRING fields and stopped there, so
        # `delegations=7` still reached `list(...)` inside `_packet_admission`
        # and raised TypeError before any denial or audit event -- the untouched
        # sibling, in a fix written one round earlier for this exact property.
        # The class is "every caller-supplied field a rule performs a typed
        # operation on", not "every string field".
        #
        # A str or dict is rejected rather than accepted: `list("abc")` and
        # `list({"a": 1})` both succeed and yield something the caller plainly
        # did not mean, which is worse than raising because nothing reports it.
        # The object-valued fields, for the same reason. `lease=7` reached
        # `.get()` in the scope binding and raised AttributeError before
        # `_writer_lease` could return its fail-closed denial. The string and
        # collection fields were each covered in an earlier round and the
        # dict-shaped ones were left -- the third slice of one property.
        for name, value in (
            ("lease", request.lease),
            ("packet", request.packet),
            ("instruction_grant", request.instruction_grant),
            ("launch_grant", request.launch_grant),
        ):
            if value is not None and not isinstance(value, dict):
                errors.append(
                    f"request {name} must be an object, got {type(value).__name__}; "
                    "a malformed request is refused, not evaluated"
                )
                blanked[name] = None

        for name, value in (
            ("delegations", request.delegations),
            ("constraint_packets", request.constraint_packets),
            # The fourth ledger. The previous round added the three above and
            # missed this one, so `active_leases=7` still raised TypeError out
            # of `_usable_leases` -- on the no-registry path, where
            # `_lease_ledger` falls back to the caller's copy. Enumerating
            # fields by hand is how a fourth gets missed; the test below is
            # derived from the dataclass instead.
            ("active_leases", request.active_leases),
            ("private_constraint_packets", request.private_constraint_packets),
        ):
            if not isinstance(value, (list, tuple)):
                errors.append(
                    f"request {name} must be a list or tuple, got {type(value).__name__}; "
                    "a malformed request is refused, not evaluated"
                )
                blanked[name] = ()

        if blanked:
            normalized = replace(normalized, **blanked)

        action = _canonical_action(normalized.action)
        if action != normalized.action:
            normalized = replace(normalized, action=action)

        # The three fields every rule is a statement ABOUT. A request missing
        # any of them describes no decision, so there is nothing to allow.
        #
        # This is checked here, before any rule and therefore before any
        # exemption. `evaluate(agent=CHIEF, action="read", resource="")`
        # returned allowed=True with an empty reason tuple: `_brain_lock` and
        # `_packet_admission` both exempt the chief, and every remaining rule
        # reads the resource, so a blank one simply matched no prefix and
        # objected to nothing. The gate reported approval having verified
        # neither ownership nor mount registration -- while the tool arguments
        # an executor actually receives may well name a real target.
        #
        # The empty ACTION case was caught only by accident: a blank action is
        # classified as mutating, so the lease rules happened to fire. Accident
        # is not enforcement, so all three are stated.
        #
        # Read from `normalized`, NOT from `request`. Reading the original is
        # how the type check above got bypassed three lines after being
        # written: a non-string agent was blanked on the copy and then
        # `.strip()`ed on the original, raising the very AttributeError the
        # check exists to prevent. Caught by running the reproduction again
        # after the fix rather than assuming it.
        for name, value in (
            ("agent", normalized.agent),
            ("action", action),
            ("resource", normalized.resource),
        ):
            if not (value or "").strip():
                errors.append(
                    f"request declares no {name}; a decision cannot be made about an "
                    "unstated principal, action, or resource, and no exemption applies "
                    "to a request that names nothing"
                )

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
        # Escape is checked BEFORE the chief exemption, because the exemption is
        # about which BRAIN may be touched, not about whether the target is
        # inside the governed tree at all. Returning early for the chief skipped
        # `_escapes_the_tree` entirely: `evaluate(agent=CHIEF, action="read",
        # resource="/etc/shadow")` was allowed with an EMPTY reason tuple, as
        # were `../outside-secret` and `docs/../../.ssh/id_rsa`. A filesystem
        # executor following a policy-approved request would have read straight
        # out of the repository. Reproduced before fixing.
        #
        # Being the sole cross-brain agent permits acting for either brain. It
        # does not put the whole filesystem in scope, and no brain owns a path
        # outside the tree, so there is nothing here for the exemption to waive.
        if self._escapes_the_tree(request.resource):
            return [
                f"brain lock: resource {request.resource!r} escapes the repository once "
                "normalized, so its owning brain cannot be established"
            ]
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
        # The sentinel waives RESOURCE OWNERSHIP, not the principal's brain.
        #
        # Placing it as an early return skipped the whole rule, including the
        # comparison of the caller's declared brain against its registered one:
        # `jeos_reflection_forge` reading `current-message` while declaring
        # `owner_brain="APEX"` -- or omitting the field entirely -- was allowed.
        # APEX message content could be routed through a JEOS specialist with no
        # objection. That is the same shape as the two exemption-ordering
        # fail-opens already recorded here, and it arrived in the fix for the
        # third deadlock. An exemption has to name what it waives.
        #
        # What it genuinely waives: message text has no owning brain, so the
        # ownership resolution below cannot classify it and would deny. Everything
        # about the PRINCIPAL still applies.
        if request.resource == CURRENT_MESSAGE:
            if agent_brain != request.owner_brain:
                return [
                    f"brain lock: {request.agent!r} belongs to {agent_brain!r}, "
                    f"request declares {request.owner_brain!r}"
                ]
            return []
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
        # Opacity is reserved for real handle syntax, not for "contains a colon
        # before the first slash". That test also matched a WINDOWS DRIVE PATH:
        # `C:\Users\Joe\secret.txt` has no `/` at all, so the whole string was
        # its own first segment, the colon made it opaque, normalization never
        # ran, and `_escapes_the_tree` saw a string starting with neither `../`
        # nor `/`. The chief could read it with no denial reasons -- on the one
        # platform the workstation actually runs. The escape check added the
        # round before was correct and simply never reached.
        if resource.startswith(CONNECTOR_PREFIXES) or _BRAIN_NAMESPACE.match(resource):
            return resource  # mount:/connector: handles and namespaces are not paths
        return posixpath.normpath(resource.replace("\\", "/"))

    @staticmethod
    def _escapes_the_tree(resource: str) -> bool:
        """A resource that climbs out of the repository cannot be classified.

        Drive-qualified and UNC paths are escapes in their own right: they name
        a location that no amount of normalization brings inside the tree, and
        `posixpath` has no concept of either. Drive-RELATIVE spellings
        (`C:..\\secret.txt`, `C:secret.txt`) count, not only drive-absolute
        ones -- Windows resolves them against that drive's current directory,
        which this module cannot know.
        """
        canonical = PolicyEnforcementPoint._canonical_resource(resource)
        if _DRIVE_QUALIFIED.match(canonical) or canonical.startswith("//"):
            return True
        return canonical.startswith(("../", "/")) or canonical == ".."

    @staticmethod
    def _is_brain_neutral(resource: str) -> bool:
        """Shared repository surfaces that belong to neither brain.

        Compared after normalization, and tolerant of the directory itself:
        `normpath("docs/")` is `"docs"`, which does not start with `"docs/"`.

        Directory entries match descendants; NAMED FILES match only themselves.
        Applying prefix matching to both meant `AGENTS.md` also matched
        `AGENTS.md.private`, `README.md.jeos`, and `CLAUDE.md-secrets` -- files
        whose ownership is unresolvable and which an APEX specialist could
        therefore read packetlessly. The trailing slash in the declaration is
        what distinguishes the two cases, so it is what the comparison reads.
        This matters more since the previous round, which made a neutral read
        an exemption from packet admission rather than merely a classification.
        """
        canonical = PolicyEnforcementPoint._canonical_resource(resource)
        for prefix in BRAIN_NEUTRAL_PREFIXES:
            if prefix.endswith("/"):
                if canonical == prefix.rstrip("/") or canonical.startswith(prefix):
                    return True
            elif canonical == prefix:
                return True
        return False

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

    def _registered_mounts(self) -> frozenset[str]:
        """Mount names declared in config/mcp_mounts.toml, the governed list."""
        if getattr(self, "_mounts_cache", None) is None:
            path = self.root / "config" / "mcp_mounts.toml"
            names: set[str] = set()
            if path.exists():
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                names = {
                    str(mount["name"]) for mount in data.get("mounts", []) if mount.get("name")
                }
            self._mounts_cache = frozenset(names)
        return self._mounts_cache

    def _guard_errors(self, request: ToolRequest) -> list[str]:
        """Validate the packet twice, and never let a filter hide a semantic error.

        The previous round tolerated the writer-lease `2.0`-vs-`2.1` mismatch by
        dropping that one error string from the guard's output. That was a
        fail-OPEN bug, and a worse one than the fail-shut it replaced:
        `PacketGuard` returns the lease-ledger error and *short-circuits*, so a
        packet with a genuine semantic defect -- a delegation carrying another
        specialist's memory namespace -- produced exactly one error, the
        version mismatch, which the filter then deleted. Result: `allowed`.

        Reproduced before fixing. Without the ledger the guard says
        `agent apex_war_architect must use memory namespace
        APEX::Strategy-Campaigns::apex_war_architect`; with a real 2.1 lease it
        says only `leases[0]: expected const '2.0'`; after the filter, nothing.

        So semantics are established on a pass that cannot be short-circuited by
        the ledger at all, and the tolerance is applied only to errors the
        ledger itself introduced. A suppression rule must never be able to
        remove a finding it was not written for.
        """
        semantic = self.guard.validate(
            request.packet_schema,
            request.packet,
            # No ledger: this pass is about the packet's own consistency, and it
            # is the pass whose findings are never filtered.
            delegations=list(request.delegations),
            constraint_packets=list(request.constraint_packets),
            private_constraint_packets=list(request.private_constraint_packets),
        )
        bound = self.guard.validate(
            request.packet_schema,
            request.packet,
            self._lease_ledger(request),
            delegations=list(request.delegations),
            constraint_packets=list(request.constraint_packets),
            private_constraint_packets=list(request.private_constraint_packets),
        )
        # Drop the one error that exists only because this pass withholds the
        # ledger. It cannot hide a real lease problem: the bound pass below runs
        # WITH the ledger and reports genuine lease-match failures, so this
        # filter removes an artifact rather than a finding.
        #
        # Stated explicitly because the last suppression rule written here
        # caused a fail-open: a filter is safe only when the thing it removes is
        # provably uninformative in the pass it applies to, and when some other
        # pass still covers the underlying property.
        semantic = [error for error in semantic if not _is_ledger_artifact(error)]
        seen = set(semantic)
        # No version filter here any more. The ledger is reconciled at source in
        # `_lease_ledger`, so the bound pass no longer stops at a lease-schema
        # error before it reaches `_lease_match_errors` -- which is the check
        # that binds this packet to that lease. Every error the bound pass now
        # reports is a real one, so none is dropped.
        extra = [error for error in bound if error not in seen]
        return [f"packet rejected: {error}" for error in [*semantic, *extra]]

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
        # Registration is checked BEFORE the chief exemption. The exemption used
        # to return first, so `mount:shadow_it_server` and
        # `connector:unregistered` -- handles naming nothing in
        # config/mcp_mounts.toml -- were allowed outright. The mount contract
        # says an unlisted server is unreachable; an enforcement point that
        # accepts any string after `mount:` is not enforcing that.
        #
        # Both spellings of "which server" are checked. `ToolRequest.mount` was
        # added one round earlier to carry the executing mount independently of
        # the write target, and it was wired only into the launch-grant rule --
        # so a packet-only specialist could name its own memory namespace in
        # `resource`, set `mount="gdrive"` or even an unregistered mount, and be
        # allowed. Adding a field that names a connector without teaching the
        # connector rule to read it moved the boundary rather than widening it
        # on purpose. Reproduced before fixing.
        touched = [
            request.resource[len(p) :] for p in CONNECTOR_PREFIXES if request.resource.startswith(p)
        ]
        if request.mount:
            touched.append(request.mount)
        registered = self._registered_mounts()
        for handle in touched:
            if handle not in registered:
                return [
                    f"{handle!r} names no mount registered in "
                    f"config/mcp_mounts.toml; unlisted servers are unreachable"
                ]
        spec = self._spec(request.agent)
        policy = spec.get("connector_policy")
        if policy is None or request.agent == CHIEF:
            return []
        if policy != PACKET_ONLY:
            return [f"connector policy {policy!r} is not the approved {PACKET_ONLY!r}"]
        if request.mount:
            return [
                f"{request.agent!r} is {PACKET_ONLY!r} and may not dispatch through "
                f"mount {request.mount!r}; {CHIEF} performs connector work on its behalf"
            ]
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
        #
        # Type-checked before the membership test. A frozenset lookup on an
        # unhashable value raises `TypeError`, so a caller supplying a list or
        # dict for `packet_schema` unwound the enforcement call instead of
        # receiving a denial -- and a gate that raises on caller-controlled
        # input is a denial of service on every other caller sharing the
        # process, not a fail-closed decision. Same reasoning as the non-dict
        # packet check below; that one was fixed and this one was left, which is
        # the sibling-untouched pattern again.
        if not isinstance(request.packet_schema, str):
            return [f"packet schema must be a string, got {type(request.packet_schema).__name__}"]
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
            #
            # Brain-neutral surfaces are exempt because requiring a delegation
            # for them was a DEADLOCK, not a control. `_is_canonical_resource()`
            # counts `docs/`, `schemas/`, `config/`, `AGENTS.md` and the rest as
            # canonical, so a specialist reading one was denied without a
            # packet -- and denied WITH one too: a delegation's
            # `allowed_read_namespaces` is confined by `PacketGuard` to the
            # agent's private memory and roundtable, so no schema-valid packet
            # can name a repository path. All three branches denied, including
            # a specialist reading AGENTS.md, the contract defining its own
            # behaviour. Reproduced before fixing.
            #
            # Same shape as the earlier execution-authority deadlock: a rule
            # whose only lawful path does not exist is not strict, it is broken.
            #
            # Scoped tightly. This exempts ONLY the declared neutral set, which
            # is matched after normalization -- so `scripts/../brains/jeos/...`
            # does not qualify -- and only on a read. Connector handles and
            # brain-owned namespaces still require a delegation, and a resource
            # that escapes the tree is not neutral and stays refused.
            neutral_read = self._is_brain_neutral(request.resource) and not self._escapes_the_tree(
                request.resource
            )
            if (
                request.agent != CHIEF
                and not neutral_read
                and self._is_canonical_resource(request.resource)
            ):
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
        errors = self._guard_errors(request)
        # Scope binding only runs on a packet that survived validation. Running
        # it on a rejected packet reads fields from a structure the guard has
        # already said it cannot vouch for.
        if errors:
            return errors
        deadline = self._deadline_errors(request)
        if deadline:
            return deadline
        return self._packet_scope_errors(request)

    def _deadline_errors(self, request: ToolRequest) -> list[str]:
        """Every packet in the authorizing chain, not just the one presented.

        The previous round added this check and applied it only to
        `request.packet`. A HANDOFF carries no `deadline` -- the field lives on
        the delegation that commissioned it -- so presenting a handoff meant the
        check ran against a packet that could never fail it. A handoff backed by
        a delegation dated 2020 authorized a canonical read. Reproduced before
        fixing.

        The bound belongs to the assignment, and a handoff inherits its
        assignment's bound: a return cannot outlive the commission it answers.
        """
        errors = self._packet_deadline_errors(request.packet)
        if errors:
            return errors
        origin = self._originating_delegation(request)
        if origin is None:
            return []
        return [
            f"originating delegation: {error}" for error in self._packet_deadline_errors(origin)
        ]

    @staticmethod
    def _originating_delegation(request: ToolRequest) -> dict[str, Any] | None:
        """The delegation this packet answers, matched by `delegation_id`.

        Returns None when the packet is itself a delegation, when it names no
        origin, or when the ledger does not carry exactly one match. Ambiguity
        is not resolved by guessing -- `PacketGuard` independently requires a
        uniquely validated originating delegation for a handoff, so a packet
        with none or several is already refused by the time this runs.
        """
        packet = request.packet
        if not isinstance(packet, dict):
            return None
        origin_id = packet.get("delegation_id")
        if not origin_id or "allowed_read_namespaces" in packet:
            return None  # a delegation carries its own id; it is not its own origin
        matches = [
            item
            for item in request.delegations
            if isinstance(item, dict) and item.get("delegation_id") == origin_id
        ]
        return matches[0] if len(matches) == 1 else None

    def _packet_deadline_errors(self, packet: Any) -> list[str]:
        """A time-bounded assignment must actually be bounded by that time.

        `deadline` is declared in the delegation schema and nothing anywhere
        parsed it -- not `PacketGuard`, not this module. A delegation with
        `deadline: "2020-01-01T00:00:00Z"` was admitted, so an assignment stated
        as time-bounded stayed reusable indefinitely for as long as some lease
        was available to pair with it. Reproduced before fixing.

        Null is not a defect: the schema declares the field nullable, and a
        delegation with no deadline is an unbounded assignment by design. Only a
        STATED deadline is enforced -- and a stated one that cannot be parsed is
        refused rather than ignored, because an unreadable bound is not an
        absent bound.
        """
        deadline = packet.get("deadline")
        if deadline is None:
            return []
        try:
            when = datetime.datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        except ValueError:
            return [
                f"packet deadline {deadline!r} is not a parseable timestamp; an "
                "unreadable bound is not an absent one"
            ]
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.UTC)
        if when <= self._clock():
            return [f"packet deadline {deadline} has passed; the assignment is no longer live"]
        return []

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
        # Reconciled for the known 2.1-vs-2.0 defect only; see
        # `_reconciled_lease`. Every other schema error still denies, and a
        # lease claiming any version other than the one the registry issues is
        # not reconciled at all -- which the error filter this replaces could
        # not distinguish, because it dropped the const error whatever the
        # offending value was.
        lease = self._reconciled_lease(issued)

        errors = [
            f"lease rejected: {error}"
            for error in self.guard.validate("writer_lease.schema.json", lease)
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
            return self._usable_leases(request.active_leases)
        issued = getattr(self.registry, "_active", None)
        if isinstance(issued, dict):
            # Reconciled, so the ledger validates and the guard proceeds to the
            # packet-to-lease relationship checks instead of returning at the
            # first ledger error. Without this the ledger is authoritative but
            # never actually compared against the packet.
            return self._usable_leases(issued.values())
        # Unknown registry shape: fall back to the one lease we can look up
        # authoritatively rather than trusting the submitted ledger.
        _, verified = self._registry_membership(request.lease or {})
        return self._usable_leases([verified] if verified else [])

    def _usable_leases(self, leases: Any) -> list[Any]:
        """Reconcile the known version defect, and drop leases already lapsed.

        `LeaseRegistry._expire()` runs only inside `issue()`, so a lease that
        has passed its `expires_at` stays in `_active` until some unrelated
        issuance happens to sweep it. Handing that record to `PacketGuard` made
        it report `active writer lease is expired` for the LEDGER -- and
        `validate()` returns at the first ledger error, so a single lapsed lease
        denied every packet-backed operation in the corps, including reads that
        have nothing to do with any lease. Reproduced against a lease expired in
        real wall-clock time before fixing.

        Filtered rather than swept: this is a policy evaluation, and asking
        whether an action is permitted must not mutate the registry. The same
        reasoning defers instruction-nonce consumption to the execution
        boundary.

        This cannot let a mutation ride a lapsed lease. Dropping it from the
        ledger means a packet naming it fails `writer lease ... is not uniquely
        active`, and `_writer_lease` independently checks expiry against this
        point's own clock. Both directions are tested.
        """
        usable = []
        for lease in leases:
            reconciled = self._reconciled_lease(lease)
            if isinstance(reconciled, dict) and self._has_lapsed(reconciled):
                continue
            usable.append(reconciled)
        return usable

    def _has_lapsed(self, lease: dict[str, Any]) -> bool:
        """True when the lease's own expiry has passed, by this point's clock.

        Deliberately `<=`, matching `PacketGuard`'s own comparison rather than
        `_lease_expiry_errors`' strict `>`. The filter has to be at least as
        aggressive as the check it is protecting: a lease this kept but the
        guard rejected would re-shut the gate on the one boundary instant.
        """
        expires = lease.get("expires_at")
        if not expires:
            return False
        try:
            deadline = datetime.datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        except ValueError:
            # Unparseable expiry is not "not expired". Keeping it in the ledger
            # lets the guard reject it, which is the fail-closed outcome;
            # dropping it silently would hide a malformed lease instead.
            return False
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=datetime.UTC)
        return deadline <= self._clock()

    @staticmethod
    def _reconciled_lease(lease: Any) -> Any:
        """Neutralize the known 2.1-vs-2.0 defect, and nothing else.

        Returns a copy whose `schema_version` reads as the schema's declared
        const, but only when the stored value is exactly the version
        `runtime/writer_lease.py` issues. Any other value -- including one a
        caller invented -- is left alone so the schema still rejects it.

        Everything except this one field is untouched, so a lease with a second
        schema defect still fails, and a lease that does not match the packet
        still fails the relational checks this reconciliation exists to let run.
        """
        if not isinstance(lease, dict):
            return lease
        if lease.get("schema_version") != ISSUED_LEASE_SCHEMA_VERSION:
            return lease
        reconciled = dict(lease)
        reconciled["schema_version"] = DECLARED_LEASE_SCHEMA_VERSION
        return reconciled

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
        if resource and not request.resource_id and self._is_canonical_resource(request.resource):
            # An optional identifier honoured only when supplied is an opt-out.
            # A delegation for `resource-1` denied a request naming
            # `resource-2` and ALLOWED one that named nothing, so any record
            # under the authorized namespace was reachable by omitting the
            # field. `_writer_lease` already required it for mutations -- the
            # read path was the untouched sibling.
            errors.append(
                f"packet is issued for record {resource!r} but the request names none; "
                "a read with no record identity cannot be matched to the packet"
            )
        elif resource and request.resource_id and resource != request.resource_id:
            errors.append(
                f"packet resource {resource!r} does not match the requested {request.resource_id!r}"
            )
        errors.extend(self._prohibited_scope_errors(request, packet))
        errors.extend(self._packet_namespace_errors(request, packet))
        errors.extend(self._packet_operation_errors(request, packet))
        errors.extend(self._packet_concurrency_errors(request, packet))
        return errors

    def _prohibited_scope_errors(self, request: ToolRequest, packet: dict[str, Any]) -> list[str]:
        """A bounded assignment cannot authorize what it explicitly forbids.

        `prohibited_scope` is a required field of the delegation schema and
        nothing consulted it. A schema-valid delegation whose `prohibited_scope`
        named its own `memory_namespace` authorized a read of exactly that
        namespace -- the packet contradicted itself and the contradiction
        resolved in favour of access. Reproduced before fixing.

        Applied BEFORE the allowlist, because a prohibition that only takes
        effect where the allowlist already denies is not a prohibition.

        Only machine-resolvable entries are enforced. `prohibited_scope` also
        carries prose ("binding commitments"), which no comparison here can
        adjudicate -- those remain a matter for the role-adherence judge and are
        deliberately not guessed at. An entry is treated as a scope when it
        looks like a namespace or a path, which is the same normalization the
        allowlist comparison uses, so the two cannot disagree about what a
        given string denotes.
        """
        # The submitted packet AND the delegation it answers. A handoff carries
        # no `prohibited_scope` at all -- the schema does not define one -- so
        # reading only the submitted packet meant a return packet escaped every
        # prohibition its commission stated. `_packet_namespace_errors` beside
        # this one already derives its ALLOWLIST from the originating
        # delegation; taking the permission from the commission and the
        # prohibition from the return packet is the same assignment read from
        # two different documents, and the looser one won.
        sources: list[tuple[str, Any]] = [("packet", packet)]
        origin = self._originating_delegation(request)
        if origin is not None:
            sources.append(("originating delegation", origin))

        resource = self._canonical_resource(request.resource).replace("::", "/")
        errors = []
        for label, source in sources:
            prohibited = source.get("prohibited_scope") or []
            if not isinstance(prohibited, list):
                errors.append(f"{label} prohibited_scope must be a list")
                continue
            for entry in prohibited:
                if not isinstance(entry, str) or not entry.strip():
                    continue
                normalized = self._canonical_resource(entry.strip()).replace("::", "/")
                # Prose entries name no resource. `/` or `::` in the original is
                # what distinguishes "APEX::Roundtable" from "binding commitments".
                if "/" not in normalized and "::" not in entry:
                    continue
                if resource == normalized or resource.startswith(f"{normalized}/"):
                    errors.append(
                        f"{label} prohibits {entry!r}, which covers the requested "
                        f"{request.resource!r}; a delegation cannot authorize what it forbids"
                    )
                elif normalized.startswith(f"{resource}/"):
                    # Containment the OTHER way: the request names a parent that
                    # CONTAINS the prohibited record. Checking only whether the
                    # prohibition covers the resource meant a delegation
                    # allowing `APEX::Roundtable` while prohibiting
                    # `APEX::Roundtable::secret` still authorized a read of the
                    # parent collection -- which serves the withheld record
                    # along with everything else. The prohibition was satisfied
                    # by asking for strictly more than it forbade.
                    #
                    # Denied rather than filtered: this is an authorization
                    # decision with no access to the records, so it cannot serve
                    # a redacted collection, and there is no third answer
                    # between allowing the exposure and refusing the read. A
                    # commission that means to permit the parent must not
                    # prohibit a child of it.
                    errors.append(
                        f"{label} prohibits {entry!r}, which is contained by the requested "
                        f"{request.resource!r}; a collection read cannot serve a record the "
                        "commission withholds, and this gate cannot redact one"
                    )
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

        A `direct_read_only` handoff binds NOTHING canonical. That mode is the
        packetless path written down: no delegation commissioned it, and the
        schema confines it to `resource_id="current-message"`. Treating its
        `memory_namespace` as an authorization scope let a specialist mint a
        schema-valid direct handoff and read its own canonical memory namespace
        with no Agent 007 assignment behind it -- which is precisely the
        self-issued authority the packet contract exists to prevent, arriving
        through the one packet kind that needs no issuer.
        """
        targets = [
            write["target"]
            for write in (packet.get("proposed_writes") or [])
            if isinstance(write, dict) and write.get("target")
        ]
        if mutating:
            return targets or None
        if packet.get("invocation_mode") == "direct_read_only":
            return None
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
            # An EXPLICIT empty list is a schema-permitted way of saying "no
            # operation is authorized". Reading absence as unrestricted is the
            # same absent-scope-means-unlimited-scope defect the handoff path
            # had, in the operation dimension -- `replace`, `disable`, and an
            # invented `destroy` all passed. The declaration is only absent
            # when the packet carries no mutation contract AND no proposed
            # writes at all; a stated empty set authorizes nothing.
            declared = (packet.get("mutation_contract") or {}).get("allowed_operations")
            if declared is not None or packet.get("proposed_writes") is not None:
                return [
                    "packet declares an empty operation allowlist, which authorizes "
                    "no mutation; an explicit empty set is not an unrestricted one"
                ]
            return []
        if not request.operation:
            return [
                f"packet permits operations {sorted(allowed)} but the request names none; "
                "an unstated operation cannot be matched against the one proposed"
            ]
        operation = request.operation.strip().lower()
        if operation not in allowed:
            return [f"packet proposes {sorted(allowed)}, not {operation!r}"]
        return []

    # The two `mutation_contract` flags, paired with the request field each one
    # obliges. Enumerated once so a third control added to the schema is a
    # one-line change here rather than a second hand-written branch that
    # silently keeps reading only these two.
    _CONCURRENCY_CONTROLS: tuple[tuple[str, str, str], ...] = (
        (
            "require_expected_version",
            "expected_version",
            "a write with no expected version is a blind overwrite of whatever is there now",
        ),
        (
            "require_idempotency_key",
            "idempotency_key",
            "a write with no idempotency key applies twice on retry",
        ),
    )

    def _packet_concurrency_errors(self, request: ToolRequest, packet: dict[str, Any]) -> list[str]:
        """A control the packet demands must actually be carried.

        `require_expected_version` and `require_idempotency_key` are REQUIRED
        fields of the delegation schema, so a validated packet always states a
        position on both, and no rule read either. Every other dimension --
        target, record, brain, lease, operation -- was bound while the two
        controls the packet itself insisted on were optional in practice.

        Absence of the flags is NOT read as a demand. That looks like the
        "absent scope means unlimited scope" defect this module has fixed three
        times, but it is the opposite shape: an allowlist's silence is a claim
        about what is permitted, whereas these flags are a claim about what the
        *issuer* requires. Inventing a requirement the issuer did not state
        would deny lawful appends to append-only logs, where neither control
        applies. A malformed flag is a different matter and is treated as a
        demand: only `False` and absence waive, so the string `"false"` -- which
        is truthy in Python and would otherwise silently disable the control --
        does not. The schema types both flags as booleans and rejects that
        packet first; this rule does not lean on that, because a rule whose
        correctness depends on a validator running upstream breaks the day it is
        called from anywhere else.

        **What this does not do.** It proves the control is CARRIED, not that it
        is HONOURED. Nothing here can tell whether the executor performs a
        compare-and-set against the version it was handed, or whether the
        idempotency key was already consumed -- that needs a ledger of applied
        keys at the execution boundary, the same shape as the unimplemented
        nonce consumption for instruction grants, and it is recorded with it in
        `docs/REPO_OPTIMIZATION_2026-07-25.md`. Carrying the value is the
        precondition: today a mutation reaches the executor with nothing to
        compare and nothing to deduplicate, so the executor could not honour
        the control even if it tried.
        """
        if not request.mutating:
            return []
        contract = packet.get("mutation_contract") or {}
        if not isinstance(contract, dict):
            # A validated packet cannot get here, but `_packet_operations`
            # already tolerates a malformed contract by treating it as absent,
            # and a rule that raises where its sibling refuses is not a stricter
            # rule -- it is an unwound enforcement boundary.
            return [
                "packet mutation_contract must be an object, got "
                f"{type(contract).__name__}; a malformed contract is refused, not read"
            ]
        errors: list[str] = []
        for flag, field_name, consequence in self._CONCURRENCY_CONTROLS:
            demanded = contract.get(flag)
            if demanded is False or demanded is None:
                continue
            supplied = getattr(request, field_name)
            if supplied is None or not str(supplied).strip():
                errors.append(
                    f"packet sets {flag} but the request supplies no {field_name}; {consequence}"
                )
        return errors

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
            #
            # But its own namespace is not a grant. The COMMISSION is the grant:
            # a handoff whose originating delegation permits only
            # `APEX::Roundtable` was reading
            # `APEX/Strategy-Campaigns/apex_war_architect`, because the fallback
            # read the handoff's mandatory `memory_namespace` field and never
            # consulted the delegation that authorized the work. A return packet
            # cannot widen the assignment it answers.
            #
            # So the delegation bounds it where one is matched, and the handoff's
            # own namespace applies only when no delegation is available -- in
            # which case `PacketGuard` has independently refused the handoff for
            # having no uniquely validated origin, so this path is not a way in.
            origin = self._originating_delegation(request)
            if origin and not request.mutating:
                declared = list(origin.get("allowed_read_namespaces") or [])
                if not declared:
                    return [
                        f"the originating delegation permits no read of "
                        f"{request.resource!r}; a handoff cannot grant what its "
                        "commission withheld"
                    ]
            else:
                fallback = self._handoff_scope(packet, mutating=request.mutating)
                if fallback is None:
                    return [
                        f"packet declares no scope permitting a {kind} of "
                        f"{request.resource!r}; absent scope is not unrestricted scope"
                    ]
                declared = fallback
        # Both sides, not one. The comment below states the intent -- compare on
        # the shared segments rather than demanding one spelling -- but only the
        # DECLARED entry was normalized, so a request naming its resource in
        # namespace form could never match a scope that authorized it. The
        # denial then printed two strings that looked identical, because the
        # difference was the separator being compared. `_canonical_resource`
        # does not help: it treats anything with a colon in its first segment as
        # an opaque handle, which a `::` namespace is not.
        resource = self._canonical_resource(request.resource).replace("::", "/")
        for entry in declared:
            # Namespaces are written `APEX::Strategy-Campaigns::agent` and write
            # targets `APEX/Strategy-Campaigns`; compare on the shared segments
            # rather than demanding one spelling.
            normalized = str(entry).replace("::", "/")
            # Equality, or the request is a DESCENDANT of the declared scope.
            # The reverse direction used to be accepted too -- a declared scope
            # that is a descendant of the REQUEST -- which let a delegation
            # naming only `APEX::Strategy-Campaigns::apex_war_architect`
            # authorize a request for `APEX/Strategy-Campaigns`, the parent
            # collection holding every specialist's namespace. A bounded
            # assignment must not widen to its own parent: on a
            # collection-backed store that is the difference between one
            # specialist's records and all of them.
            if resource == normalized or resource.startswith(f"{normalized}/"):
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

    @staticmethod
    def _boundary_category(action: str) -> str:
        """Map a real tool action to its high-impact category, compounds included.

        The previous round replaced exact matching against the abstract category
        names with a verb map, and then looked the WHOLE action up in it. Real
        dispatchers emit compounds -- and the comment introducing that map named
        `delete_all` as its own example of a real invocation, which the map did
        not cover. Fixing the instance and leaving the class is the failure this
        record has now logged four times; here it happened inside the fix.

        Tokenized on the same boundary `_is_mutating` uses, and matched by TOKEN
        EQUALITY rather than substring, because substring matching is what made
        `delete_thread` read as a read three rounds after the allowlist landed.
        `design` does not contain the token `sign`; `publications` is not
        `publish`.

        Over-classification costs a signature request on work that did not need
        one. Under-classification forfeits the boundary Joe reserves for
        himself. The directions are not symmetric, so ambiguity resolves toward
        classifying.
        """
        folded = (action or "").strip().lower()
        if folded in HIGH_IMPACT_ACTIONS:
            return folded
        if folded in HIGH_IMPACT_VERBS:
            return HIGH_IMPACT_VERBS[folded]
        tokens = _action_tokens(action)
        # A destructive verb qualified as wholesale is a bulk deletion even when
        # neither token means that alone: `delete` is an ordinary mutation the
        # lease governs, `all` is nothing, `delete_all` is irreversible.
        if any(token in DESTRUCTIVE_VERBS for token in tokens) and any(
            token in BULK_QUALIFIERS for token in tokens
        ):
            return "irreversible_bulk_deletion"

        # The three compound categories the constitution added. Each needs BOTH
        # a verb and its noun, because the bare verb is ordinary work: `submit`
        # saves a draft, `create` makes a record, `modify` edits a field. It is
        # the object that makes the act reserved, so requiring both keeps the
        # boundary off routine mutations while still catching the real thing.
        #
        # Checked BEFORE the single-verb map so that `overwrite_all_originals`
        # and `delete_scheduled_task` resolve to the category the contract
        # names rather than to whichever bare verb happens to match first.
        if "submit" in tokens and any(token in SUBMISSION_QUALIFIERS for token in tokens):
            return "final_submission"
        if _changes_a_schedule(tokens):
            return "scheduled_task_change"
        if any(token in GOVERNANCE_VERBS for token in tokens) and any(
            token in GOVERNANCE_NOUNS for token in tokens
        ):
            return "governance_or_master_change"
        if any(token in LEGAL_COMMITMENT_VERBS for token in tokens) and any(
            token in LEGAL_COMMITMENT_NOUNS for token in tokens
        ):
            return "binding_legal_commitment"

        for token in tokens:
            if token in HIGH_IMPACT_VERBS:
                return HIGH_IMPACT_VERBS[token]
        return folded

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
        # Canonicalized here as well as in `normalize()`, so a directly-invoked
        # rule and a full `evaluate()` reach the same verdict. They did not:
        # `normalize()` folded case without splitting camelCase, so this rule
        # denied `deleteAll` when called directly and `evaluate()` allowed it,
        # and the regression test called it directly. Two entry points that
        # disagree mean the tested one is not the one that runs.
        raw_action = _canonical_action(request.action)
        # Concrete verbs map to their category, not just the category label.
        #
        # The comparison was exact against `HIGH_IMPACT_ACTIONS`, whose members
        # are abstract category names (`public_publication`). A real tool is
        # invoked as `publish`, `send`, `delete_all`, `transfer` -- and this
        # module already classifies several of those as mutations elsewhere, so
        # it plainly expects concrete verbs. The boundary therefore fired only
        # when a caller volunteered the category as its action name, which is
        # the same "controls that ask the caller to incriminate itself" shape as
        # the three caller-set booleans removed earlier: nobody publishing
        # something they should not would spell the action `public_publication`.
        action = self._boundary_category(raw_action)
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
        # Either spelling obliges a grant: the resource IS a mount handle, or
        # the request declares the mount it is dispatched through while naming a
        # canonical target. Keying only off the resource meant those two were
        # mutually exclusive -- a mutation could satisfy the packet and lease
        # scope checks by naming its write target, and skip this rule for the
        # same reason.
        mount = request.mount or (
            request.resource.split(":", 1)[1] if request.resource.startswith("mount:") else None
        )
        if not (request.mutating and mount):
            return []
        grant = request.launch_grant
        if grant is not None and not isinstance(grant, dict):
            return [f"launch grant must be an object, got {type(grant).__name__}"]
        if not grant:
            return [
                f"write-capable mount {mount!r} requires a signed one-time "
                "launch grant; none was presented"
            ]
        # The issuer's EXACT payload, `agent` included. `trusted_launcher`
        # gained agent-binding -- it signs five fields now -- and this
        # reconstruction still built four, so the HMAC over a four-key dict
        # could never match a five-key signature and every legitimately issued
        # grant verified as "signature is invalid". Fail-SHUT, and invisible
        # while `enforce()` has no call sites: the first symptom would have
        # been every granted mount mutation denied on wiring day.
        #
        # Derived from the signed field list rather than restated, so the next
        # field the issuer adds cannot silently desynchronize the two again.
        payload = {key: grant.get(key) for key in LAUNCH_GRANT_SIGNED_FIELDS}
        if payload["mount"] != mount:
            return [f"grant is for mount {payload['mount']!r}, not {mount!r}"]
        # The signed identity binds the grant to one agent. A grant minted for
        # the Chief must not authorize a specialist's mutation just because the
        # mount matches.
        signed_agent = payload.get("agent")
        if signed_agent is not None and signed_agent != request.agent:
            return [
                f"launch grant authorizes {signed_agent!r}, not the requesting {request.agent!r}"
            ]
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
