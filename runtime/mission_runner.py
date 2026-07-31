"""Controlled-mission harness: the machinery the active gate actually requires.

``config/specialist_corps.toml`` sets the promotion bar:

    Static contracts, typed 2.1 output, one controlled real mission per material
    mode, runtime connector-isolation evidence, readback, and a versioned
    lifecycle promotion.

Everything in that sentence except "one controlled real mission per material
mode" already had machinery. This module supplies the missing piece: it brackets
a real specialist run, validates both sides of it against the canonical schemas,
and writes a hash-chained evidence record that a promotion can actually cite.

**What this module deliberately does not do.** It does not execute the
specialist. The specialists are Claude Code subagents; Agent 007 invokes them
through the runtime. A harness that also generated the specialist's answer would
be grading its own homework, and the resulting "evidence" would prove nothing.
So the flow is:

    prepare()  -> Agent 007 gathers evidence from live connectors, and this
                  builds + PacketGuard-validates the delegation packet
      (Agent 007 invokes the specialist with that packet)
    complete() -> validates the typed 2.1 return against the delegation,
                  records connector-isolation evidence, writes the ledger entry,
                  and emits a value observation

A mission that never reached ``complete()`` has no evidence record, and a mode
with no evidence record is not promotable. That asymmetry is the point.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from runtime.value_meter import (
    ObservationRejected,
    ValueLedger,
    ValuePolicy,
    build_observation,
)
from scripts.agent_runtime import (
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "audit" / "missions.jsonl"
DEFAULT_VALUE_LEDGER = ROOT / "audit" / "value.jsonl"

# PacketGuard keys its schema table by file name.
DELEGATION_SCHEMA = "delegation_packet.schema.json"
HANDOFF_SCHEMA = "handoff_packet.schema.json"

VALID_EVIDENCE_SENSITIVITY = {"public", "internal", "confidential", "restricted"}

# Scheme-prefixed tokens are the shape a real connector locator takes.
LOCATOR_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>,;)\]]+")

# The generated form: uuid4().hex[:12]. A pinned run_id must match it exactly,
# because ids are composed as `<kind>:<agent>:<run_id>` and split back on ":".
RUN_ID_PATTERN = re.compile(r"[0-9a-f]{12}")

# Statuses whose return can carry benefit against the human baseline. The
# baseline measures a completed task; `blocked` and `boundary_blocked` produced
# no deliverable, so they carry their full cost and zero benefit rather than
# drawing against a workload nobody performed.
STATUSES_WITH_DELIVERABLE_VALUE = {"completed", "partial"}


class MissionRejected(ValueError):
    """The mission cannot run as specified. Fail closed; never downgrade to a guess."""


def load_brain_roster(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Agent metadata from the brain manifests, tagged with owner brain."""
    roster: dict[str, dict[str, Any]] = {}
    for brain in ("apex", "jeos"):
        manifest = tomllib.loads(
            (root / "brains" / brain / "agents.toml").read_text(encoding="utf-8")
        )
        for name, meta in manifest["agents"].items():
            if name in roster:
                # The same agent id in both manifests is a brain-separation
                # failure, not a merge conflict to resolve silently.
                raise MissionRejected(
                    f"agent {name!r} is registered in both brain manifests "
                    f"({roster[name]['brain']} and {manifest['brain']}); "
                    "brain separation is violated"
                )
            entry = dict(meta)
            entry["brain"] = manifest["brain"]
            entry["roundtable_namespace"] = manifest["roundtable_namespace"]
            roster[name] = entry
    return roster


@dataclass(frozen=True)
class EvidenceRecord:
    """One piece of evidence Agent 007 retrieved and is handing to a specialist.

    ``source_ref`` locates the real record; ``content`` carries what the
    specialist actually analyzes.

    Carrying only a locator was a design error: a packet-only specialist has no
    connector and no filesystem tool, so it cannot dereference
    ``gmail://thread/abc`` or a Drive file id. Without the content in the packet,
    the only way to convey it would be an unvalidated side channel such as the
    objective text — which is exactly the ungoverned path the packet contract
    exists to prevent.

    Keep ``content`` bounded and minimized: the smallest excerpt that supports
    the mission, never a raw dump, and always labeled with its sensitivity.
    """

    source_ref: str
    source_type: str
    content: str = ""
    sensitivity: str = "internal"
    retrieved_by: str = "apex_chief_of_staff"
    as_of: str | None = None
    # Which brain the source material actually belongs to, as verified by
    # Agent 007 when it retrieved the record. Required for real evidence.
    #
    # Deriving this from the recipient specialist's brain meant a professional
    # APEX email handed to a JEOS mission was relabelled JEOS and passed
    # PacketGuard — opposite-brain content delivered under a valid-looking
    # packet. Ownership is now asserted at retrieval and checked, not inferred.
    owner_brain: str = ""

    def as_packet_evidence(self, brain: str) -> dict[str, Any]:
        record = {
            "source_ref": self.source_ref,
            "owner_brain": self.owner_brain or brain,
            "source_type": self.source_type,
            "scope_verified_by": self.retrieved_by,
            "sensitivity": self.sensitivity,
        }
        if self.content:
            record["content"] = self.content
        if self.as_of:
            record["as_of"] = self.as_of
        return record


@dataclass
class MissionSpec:
    """What Agent 007 commits to before the specialist sees anything."""

    agent: str
    mode: str
    objective: str
    definition_of_done: list[str]
    definition_of_done_ids: list[str]
    evidence: list[EvidenceRecord]
    baseline_minutes: int
    baseline_source: str
    mission_id: str | None = None
    resource_id: str | None = None
    # Pin the run identity. `mission_id` and `resource_id` were already
    # overridable while the delegation id was not, so re-preparing an unchanged
    # mission minted a delegation the specialist's existing return no longer
    # matched -- the work had to be thrown away and re-run to fix an
    # orchestration bug that never touched the evidence. Setting this reproduces
    # a byte-identical packet, which is the only case where reusing a return is
    # honest: same evidence, same actions, same identity.
    run_id: str | None = None
    sensitivity: str = "internal"
    # `challenge` is delegated by default, not as a convenience. The
    # constitution requires a specialist to say where it disagrees with the
    # material it was handed, and PacketGuard refuses a `challenges` field that
    # the delegation did not authorize. Granting only analyze and
    # read_packet_evidence therefore made the challenge duty unexerciseable:
    # a specialist that obeyed the contract produced a packet that failed
    # validation, and the way to pass was to stay silent.
    allowed_actions: list[str] = field(
        default_factory=lambda: ["analyze", "read_packet_evidence", "challenge"]
    )
    deadline: str | None = None
    # Which artifact types the return must produce. Required, never inferred.
    #
    # An earlier version hardcoded artifact_types[0] for every mode, so
    # technical_qa demanded a delivery_board and a correct qa_risk_packet return
    # failed PacketGuard — most non-first modes could never complete a mission.
    # Defaulting to "all registered types" is equally wrong, because PacketGuard
    # requires every listed type to be present. And no positional mode->artifact
    # mapping exists: apex_intelligence_forge has five modes and four artifact
    # types, jeos_life_architect five and three. So the mission must say which
    # artifact its mode produces, and a mission that does not is refused.
    required_artifact_types: list[str] = field(default_factory=list)

    def validated_against(self, meta: dict[str, Any]) -> None:
        """Reject the mission rather than let an invalid one produce evidence."""
        if self.mode not in meta.get("modes", []):
            raise MissionRejected(
                f"{self.agent}: mode {self.mode!r} is not registered "
                f"(registered: {meta.get('modes', [])})"
            )
        if not self.definition_of_done:
            raise MissionRejected(f"{self.agent}: mission has no definition of done")
        if len(self.definition_of_done_ids) != len(self.definition_of_done):
            raise MissionRejected(f"{self.agent}: every definition-of-done entry needs a stable id")
        if not self.evidence:
            raise MissionRejected(
                f"{self.agent}: a controlled mission needs at least one evidence record; "
                "a specialist with no packet evidence cannot produce source-linked output"
            )
        for record in self.evidence:
            if record.sensitivity not in VALID_EVIDENCE_SENSITIVITY:
                raise MissionRejected(
                    f"{self.agent}: evidence sensitivity {record.sensitivity!r} is invalid"
                )
            if record.source_type != "synthetic" and not record.owner_brain:
                raise MissionRejected(
                    f"{self.agent}: evidence {record.source_ref!r} declares no verified "
                    "owner_brain; ownership may not be inferred from the recipient"
                )
            if record.owner_brain and record.owner_brain != meta["brain"]:
                raise MissionRejected(
                    f"{self.agent}: evidence {record.source_ref!r} belongs to "
                    f"{record.owner_brain} but this mission is {meta['brain']}; "
                    "cross-brain material needs a constraint packet, not a relabel"
                )
            if record.source_type != "synthetic" and not record.content:
                # A toolless specialist cannot dereference a locator. Real
                # connector evidence must arrive with its content in the packet.
                raise MissionRejected(
                    f"{self.agent}: evidence {record.source_ref!r} carries no content; "
                    "a packet-only specialist has no connector to fetch it with"
                )
        if self.baseline_minutes <= 0:
            raise MissionRejected(
                f"{self.agent}: controlled missions need a positive human baseline so the "
                "value meter has something real to compare against"
            )
        if self.baseline_source not in {"measured", "joe_declared"}:
            raise MissionRejected(
                f"{self.agent}: baseline_source must be 'measured' or 'joe_declared'; "
                f"got {self.baseline_source!r}"
            )
        registered = meta.get("artifact_types", [])
        if not self.required_artifact_types:
            raise MissionRejected(
                f"{self.agent}: mission must name the artifact type(s) mode "
                f"{self.mode!r} produces (registered: {registered}); the harness "
                "will not guess, because a wrong guess fails every return"
            )
        unknown = [a for a in self.required_artifact_types if a not in registered]
        if unknown:
            raise MissionRejected(
                f"{self.agent}: artifact types {unknown} are not registered "
                f"(registered: {registered})"
            )


@dataclass
class PreparedMission:
    """A validated delegation packet, ready for the specialist."""

    spec: MissionSpec
    meta: dict[str, Any]
    delegation: dict[str, Any]
    prepared_at: str
    contract_sha: str = ""

    @property
    def delegation_id(self) -> str:
        return self.delegation["delegation_id"]


@dataclass
class MissionEvidence:
    """The completed record: what ran, what it proved, and what it did not."""

    delegation_id: str
    mission_id: str
    agent: str
    mode: str
    brain: str
    status: str
    typed_return_valid: bool
    connector_isolation_verified: bool
    readback_performed: bool
    errors: list[str]
    ledger_entry: dict[str, Any] | None
    value_observation: dict[str, Any] | None
    value_recorded: bool = False
    contract_sha: str = ""
    completed_at: str = ""
    # True only when every evidence record came from a real source. The active
    # gate says "controlled real mission"; a schema-valid synthetic fixture must
    # never satisfy it, and the test suite is full of such fixtures.
    real_evidence: bool = False

    @property
    def qualifies_mode(self) -> bool:
        """Does this single mission satisfy the per-mode controlled-mission gate?

        The gate in config/specialist_corps.toml names readback explicitly, so a
        run that never read its result back does not qualify — previously the
        default of False still produced a covered mode.
        """
        return (
            self.status == "completed"
            and self.typed_return_valid
            and self.connector_isolation_verified
            and self.readback_performed
            and self.value_recorded
            and self.real_evidence
            and not self.errors
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "mission_id": self.mission_id,
            "agent": self.agent,
            "mode": self.mode,
            "brain": self.brain,
            "status": self.status,
            "typed_return_valid": self.typed_return_valid,
            "connector_isolation_verified": self.connector_isolation_verified,
            "readback_performed": self.readback_performed,
            "value_recorded": self.value_recorded,
            "real_evidence": self.real_evidence,
            "contract_sha": self.contract_sha,
            "completed_at": self.completed_at,
            "errors": self.errors,
            "qualifies_mode": self.qualifies_mode,
            "value_observation": self.value_observation,
        }


class MissionRunner:
    """Brackets one controlled mission: prepare the packet, then judge the return."""

    def __init__(
        self,
        root: Path = ROOT,
        ledger_path: Path | None = None,
        guard: PacketGuard | None = None,
        value_ledger_path: Path | None = None,
        value_policy: ValuePolicy | None = None,
    ) -> None:
        self.root = root
        self.roster = load_brain_roster(root)
        self.guard = guard or PacketGuard(root)
        # Derive from *this* runner's root. The module-level defaults point at
        # the checkout that imported the module, so a runner aimed at a staged
        # or temporary tree would contaminate this one's evidence.
        self.ledger = AuditLedger(ledger_path or (root / "audit" / "missions.jsonl"))
        # Lifecycle evidence and value evidence are written by the same call, so
        # a mission cannot land in the promotion record while leaving no trace of
        # what it cost Joe.
        self.value_ledger = ValueLedger(value_ledger_path or (root / "audit" / "value.jsonl"))
        # Load the policy from *this* runner's root. Using the module-global
        # default meant a runner pointed at a staged or temporary checkout was
        # measured against the policy of a different repository.
        self.value_policy = value_policy or ValuePolicy.load(root / "config" / "value_policy.toml")

    # ---------------------------------------------------------------- prepare

    def prepare(self, spec: MissionSpec) -> PreparedMission:
        """Build and validate the delegation packet. Raises rather than degrade."""
        meta = self.roster.get(spec.agent)
        if meta is None:
            raise MissionRejected(f"{spec.agent} is not in either brain manifest")
        spec.validated_against(meta)

        brain = meta["brain"]
        if spec.run_id is not None and not RUN_ID_PATTERN.fullmatch(spec.run_id):
            # Every id below is built as `<kind>:<agent>:<run_id>`, and the ids
            # are split back apart on ":" to recover the run. A run_id carrying
            # a colon, whitespace, or arbitrary length would silently produce
            # ids that no longer parse to what they were built from, so it is
            # refused rather than normalised -- a mission whose identity cannot
            # be recovered is worse than a mission that never started.
            raise MissionRejected(
                f"{spec.agent}: run_id {spec.run_id!r} must be 12 lowercase hex "
                "characters, matching the generated form"
            )
        run_id = spec.run_id or uuid.uuid4().hex[:12]
        mission_id = spec.mission_id or f"mission:{spec.agent}:{spec.mode}:{run_id}"
        resource_id = spec.resource_id or f"resource:{spec.agent}:{run_id}"

        delegation = {
            "schema_version": "2.1",
            "delegation_id": f"delegation:{spec.agent}:{run_id}",
            "mission_id": mission_id,
            "resource_id": resource_id,
            "agent": spec.agent,
            "owner_brain": brain,
            "memory_namespace": meta["memory_namespace"],
            "roundtable_namespace": meta["roundtable_namespace"],
            "mission": spec.objective,
            "definition_of_done": list(spec.definition_of_done),
            "definition_of_done_ids": list(spec.definition_of_done_ids),
            "allowed_evidence": [e.as_packet_evidence(brain) for e in spec.evidence],
            "allowed_read_namespaces": [meta["memory_namespace"]],
            # Shadow-stage specialists propose writes; Agent 007 performs them.
            "allowed_write_targets": [],
            "prohibited_scope": [
                "opposite-brain data",
                "external actions",
                "canonical writes",
                "direct connector calls",
            ],
            "allowed_actions": list(spec.allowed_actions),
            "writer_agent": None,
            "writer_lease_id": None,
            "deadline": spec.deadline,
            "dependencies": [],
            "risk_flags": [],
            "approval_level": "L0",
            "sensitivity": spec.sensitivity,
            "return_schema": "schemas/handoff_packet.schema.json",
            "mode": spec.mode,
            "required_artifact_types": list(spec.required_artifact_types),
            "mutation_contract": {
                "allowed_operations": [],
                "require_idempotency_key": True,
                "require_expected_version": True,
            },
        }

        # The policy owns the baseline's provenance as well as its size.
        # Checking only the minutes let a mission adopt the configured 240 while
        # declaring `baseline_source = "measured"`, and the observation was then
        # persisted as measured evidence -- silently upgrading Joe's declaration
        # into a measurement nobody took.
        configured = self.value_policy.baselines.get(spec.mode) or {}
        configured_source = configured.get("source")
        if (
            configured_source in self.value_policy.baseline_sources
            and spec.baseline_source != configured_source
        ):
            raise MissionRejected(
                f"{spec.agent}: mode {spec.mode!r} has a {configured_source!r} baseline "
                f"on record; this mission claims {spec.baseline_source!r}. Change the "
                "provenance in config/value_policy.toml, not per mission"
            )

        established = self._established_baseline(spec.mode)
        if established is not None and established != spec.baseline_minutes:
            # A baseline that moves per run lets the same mode reach 35% by
            # inflating the comparison rather than by saving time.
            raise MissionRejected(
                f"{spec.agent}: mode {spec.mode!r} already has an established baseline of "
                f"{established} minutes; this mission supplied {spec.baseline_minutes}. "
                "Change it deliberately in config/value_policy.toml, not per mission"
            )

        errors = self.guard.validate(DELEGATION_SCHEMA, delegation)
        if errors:
            raise MissionRejected(f"{spec.agent}: delegation packet failed PacketGuard: {errors}")

        # Fail-closed admission: schema, addressee match, and the brain lock.
        try:
            admit_delegation(delegation, spec.agent, self._agent_runtime_roster(), self.guard)
        except HandoffRejected as rejection:
            raise MissionRejected(
                f"{spec.agent}: delegation refused admission: {rejection}"
            ) from rejection

        # Pinning a run_id reuses an identity, so it must not be allowed to
        # reuse it for a DIFFERENT packet. Without this, a retry could keep the
        # id while changing the objective, evidence, allowed actions or
        # criteria, and the ledger would hold two delegations that are
        # indistinguishable by identity while meaning different things --
        # exactly the "byte-identical" guarantee the run_id comment claims.
        packet_digest = self._packet_digest(delegation)
        if spec.run_id is not None:
            prior = self._prepared_packet_digest(delegation["delegation_id"])
            if prior is not None and prior != packet_digest:
                raise MissionRejected(
                    f"{spec.agent}: run_id {spec.run_id!r} was already prepared for a "
                    "different packet; pinning reuses an identity and may only "
                    "reproduce the packet it was minted for"
                )

        self.ledger.append(
            "mission_prepared",
            {
                "delegation_id": delegation["delegation_id"],
                "agent": spec.agent,
                "mode": spec.mode,
                "brain": brain,
                "evidence_count": len(spec.evidence),
                "baseline_minutes": spec.baseline_minutes,
                "packet_digest": packet_digest,
            },
        )

        return PreparedMission(
            spec=spec,
            meta=meta,
            delegation=delegation,
            prepared_at=datetime.now(UTC).isoformat(),
            contract_sha=self.contract_sha(spec.agent),
        )

    # --------------------------------------------------------------- complete

    def complete(
        self,
        prepared: PreparedMission,
        handoff: dict[str, Any],
        *,
        agent_minutes: float,
        review_minutes: float,
        correction_minutes: float,
        maintenance_share_minutes: float,
        incident_minutes: float = 0.0,
        # Fail closed. Defaulting to True recorded acceptance Joe never gave, and
        # five such calls satisfy the 70% quality gate on unmeasured acceptance.
        accepted_first_pass: bool = False,
        output_rejected: bool = False,
        readback_performed: bool = False,
        notes: str = "",
    ) -> MissionEvidence:
        """Validate the specialist's typed return and write the evidence record."""
        errors: list[str] = []
        delegation = prepared.delegation
        spec = prepared.spec
        brain = prepared.meta["brain"]

        # Two missions prepared before either completes both see no established
        # observation, so the prepare-time guard alone lets them record
        # different baselines. Re-check against what is now on record.
        established = self._established_baseline(delegation["mode"])
        if established is not None and established != spec.baseline_minutes:
            errors.append(
                f"baseline drift: mode {delegation['mode']!r} is established at "
                f"{established} minutes but this mission used {spec.baseline_minutes}"
            )

        # 1. The return must be a schema-valid 2.1 handoff bound to this delegation.
        schema_errors = self.guard.validate(HANDOFF_SCHEMA, handoff, delegations=[delegation])
        errors.extend(schema_errors)

        # 2. It must survive the runtime's own return validation.
        errors.extend(
            f"return: {error}"
            for error in validate_specialist_return(handoff, self.guard, delegations=[delegation])
        )

        # 3. Connector isolation: the specialist must not claim external action,
        #    and every source it cites must have been in the packet we handed it.
        allowed_refs = {record.source_ref for record in spec.evidence}
        connector_isolation_verified = True
        if handoff.get("external_actions_performed") is not False:
            connector_isolation_verified = False
            errors.append(
                "connector isolation: specialist reported external_actions_performed != false"
            )
        for cited in self._cited_source_refs(handoff):
            if cited not in allowed_refs:
                connector_isolation_verified = False
                errors.append(
                    f"connector isolation: return cites {cited!r}, which was not in the "
                    "delegation packet — the specialist reached past its evidence"
                )
        # Locators quoted from inside the delegated content are delegated too.
        delegated_tokens = {
            token.rstrip(".") for token in self._delegated_content_tokens(delegation)
        }
        for token in self._locator_like_tokens(handoff):
            if token not in allowed_refs and token not in delegated_tokens:
                connector_isolation_verified = False
                errors.append(
                    f"connector isolation: return references locator {token!r} in free "
                    "text, which was not in the delegation packet"
                )

        # 4. Every definition-of-done id must have a validation record.
        validated_ids = {
            record.get("criterion_id")
            for record in handoff.get("criterion_validation", [])
            if isinstance(record, dict)
        }
        for dod_id in spec.definition_of_done_ids:
            if dod_id not in validated_ids:
                errors.append(f"definition of done {dod_id!r} has no criterion_validation record")

        # 5. A shadow-stage specialist may not have performed a canonical write.
        if handoff.get("proposed_writes") and prepared.meta.get("status") == "shadow":
            for write in handoff["proposed_writes"]:
                if isinstance(write, dict) and write.get("performed"):
                    errors.append("lifecycle: shadow-stage specialist reported a performed write")

        status = str(handoff.get("status", "unknown"))
        typed_return_valid = not schema_errors

        # An invalid or non-completed return is not a first-pass acceptance, no
        # matter what the caller passed. Otherwise five failing missions could
        # still average out to meets_threshold.
        # A brain or sensitivity rejection, or a shadow specialist reporting a
        # performed write, is a boundary incident — not merely a failed run that
        # ages out of the window.
        boundary_markers = ("owner_brain", "sensitivity", "brain", "lifecycle:")
        if any(marker in error.lower() for error in errors for marker in boundary_markers):
            connector_isolation_verified = False

        # Only an untrustworthy RETURN forces a rejection. A return that failed
        # validation cannot be said to have been accepted, whatever the caller
        # passed, so the quality terms are overridden fail-closed.
        #
        # Status is deliberately NOT part of this test. It used to be
        # (`status == "completed" and not errors`), which meant a specialist
        # that honestly reported `partial` -- because its evidence was stale, or
        # because it could not verify current state -- had its work scored as
        # output_rejected, and a rejected output carries full cost and zero
        # benefit. Joe could read that output, accept it, act on it, and the
        # meter would still record the run as a net loss. That penalised the
        # honest self-report and paid a better score for overclaiming
        # `completed`, which is precisely backwards for a system whose whole
        # premise is refusing to assert what it cannot show.
        #
        # The promotion gate is unchanged and still demands a completed status:
        # see MissionEvidence.qualifies_mode. A partial mission may be valuable
        # to Joe and still not count toward promoting a mode to active. Those
        # are two different questions and this is the one about value.
        # Ignoring status ENTIRELY was an over-correction, and it opened a
        # larger hole than the one it closed. A schema-valid `blocked` return
        # with no artifacts and every criterion untested is trustworthy by this
        # test, so an accepting caller would have credited it the full workload
        # baseline; five of those reach meets_threshold without the workload
        # ever being done. The baseline measures a completed task, so only a
        # return that actually produced the deliverable may draw against it.
        produced_deliverable = status in STATUSES_WITH_DELIVERABLE_VALUE and any(
            artifact.get("records")
            for artifact in handoff.get("artifacts", [])
            if isinstance(artifact, dict)
        )
        return_trustworthy = not errors
        if not return_trustworthy or not produced_deliverable:
            accepted_first_pass = False
            output_rejected = True

        completed_at = datetime.now(UTC).isoformat()
        value_observation = {
            "mode": delegation["mode"],
            "agent": delegation["agent"],
            "mission_id": delegation["mission_id"],
            "observed_at": completed_at,
            "baseline_minutes": spec.baseline_minutes,
            "baseline_source": spec.baseline_source,
            "agent_minutes": agent_minutes,
            "review_minutes": review_minutes,
            "correction_minutes": correction_minutes,
            "incident_minutes": incident_minutes,
            "maintenance_share_minutes": maintenance_share_minutes,
            "accepted_first_pass": accepted_first_pass,
            "output_rejected": output_rejected,
            "boundary_incident": not connector_isolation_verified,
            "notes": notes,
        }

        # Validate the observation up front, but do not persist it yet: the two
        # ledgers must land together. Writing value first and then failing to
        # write the mission record would leave reportable value credit behind
        # for a mission that officially never completed.
        value_recorded = False
        pending_observation = None
        try:
            pending_observation = build_observation(self.value_policy, value_observation)
        except ObservationRejected as rejection:
            errors.append(f"value observation rejected: {rejection}")

        evidence = MissionEvidence(
            delegation_id=delegation["delegation_id"],
            mission_id=delegation["mission_id"],
            # Identity comes from the validated delegation. Reading it from the
            # caller's still-mutable spec let a caller run one mode, rewrite
            # spec.mode to a sibling, and collect coverage for the sibling.
            agent=delegation["agent"],
            mode=delegation["mode"],
            brain=brain,
            status=status,
            typed_return_valid=typed_return_valid,
            connector_isolation_verified=connector_isolation_verified,
            readback_performed=readback_performed,
            errors=errors,
            ledger_entry=None,
            value_observation=value_observation,
            value_recorded=value_recorded,
            contract_sha=prepared.contract_sha,
            completed_at=completed_at,
        )

        # Ordering matters in both directions. Writing value first risks value
        # credit for a mission with no completion record; writing the mission
        # record first with the flag already unset means the reconstructed
        # evidence never qualifies. So the flag is set to what the write is
        # about to achieve, the mission record lands first, and a failure to
        # record value emits a compensating entry that revokes the claim.
        evidence.real_evidence = all(record.source_type != "synthetic" for record in spec.evidence)
        evidence.value_recorded = pending_observation is not None
        evidence.ledger_entry = self.ledger.append("mission_completed", evidence.to_json())

        if pending_observation is not None:
            try:
                self.value_ledger.record(pending_observation)
            except OSError as failure:
                evidence.value_recorded = False
                evidence.errors.append(f"value ledger write failed: {failure}")
                self.ledger.append(
                    "value_record_failed",
                    {
                        "delegation_id": evidence.delegation_id,
                        "mission_id": evidence.mission_id,
                        "mode": evidence.mode,
                        "error": str(failure),
                    },
                )
        return evidence

    @staticmethod
    def _packet_digest(delegation: dict[str, Any]) -> str:
        """Fingerprint the material content of a delegation packet.

        The identity fields are excluded on purpose: two packets that differ
        only by run id are the same assignment, and two that share a run id but
        differ in substance are the case this exists to catch.
        """
        material = {
            key: value
            for key, value in delegation.items()
            if key not in {"delegation_id", "mission_id", "resource_id"}
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:32]

    def _prepared_packet_digest(self, delegation_id: str) -> str | None:
        """The digest recorded when this delegation id was first prepared."""
        if not self.ledger.path.exists():
            return None
        for line in self.ledger.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            # AuditLedger.append stores the body under "detail". Reading a key
            # that does not exist made this guard fail OPEN -- it found no prior
            # digest and cheerfully accepted a mismatched packet -- so the
            # lookup is asserted by a test that reuses an id for a different
            # packet, not merely by inspection.
            detail = entry.get("detail")
            if not isinstance(detail, dict):
                continue
            if (
                entry.get("event") == "mission_prepared"
                and detail.get("delegation_id") == delegation_id
                and detail.get("packet_digest")
            ):
                return detail["packet_digest"]
        return None

    def _established_baseline(self, mode: str) -> int | None:
        """The baseline this mode has already been measured against, if any.

        Prefers the reviewed policy file, then the most recent recorded
        observation, so a baseline is set once rather than per run.
        """
        from_policy = self.value_policy.usable_baseline(mode)
        if from_policy is not None:
            return from_policy
        if not self.value_ledger.path.exists():
            return None
        try:
            observations = self.value_ledger.observations(self.value_policy)
        except ObservationRejected:
            return None
        for observation in reversed(observations):
            if observation.mode == mode:
                return observation.baseline_minutes
        return None

    def contract_sha(self, agent: str) -> str:
        """Fingerprint of the exact contract + manifest entry a mission ran under.

        Coverage keyed only by (agent, mode) would keep crediting a mode after
        its contract changed. Binding the evidence to a contract hash means a
        behavioural change invalidates the coverage it earned.
        """
        meta = self.roster[agent]
        contract = (self.root / meta["native_file"]).read_bytes()
        entry = json.dumps(
            {k: v for k, v in sorted(meta.items()) if k != "roundtable_namespace"},
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(contract + entry).hexdigest()[:16]

    def evidence_from_ledger(self) -> list[MissionEvidence]:
        """Reconstruct completed-mission evidence from the audit ledger.

        The runbook's coverage command previously passed an empty list, so it
        always reported zero covered modes no matter how many missions had run.
        """
        if not self.ledger.path.exists():
            return []
        recovered: list[MissionEvidence] = []
        revoked: set[str] = set()
        for raw in self.ledger.path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("event") == "value_record_failed":
                revoked.add(entry.get("detail", {}).get("delegation_id"))
                continue
            if entry.get("event") != "mission_completed":
                continue
            detail = entry.get("detail", {})
            recovered.append(
                MissionEvidence(
                    delegation_id=detail.get("delegation_id", ""),
                    mission_id=detail.get("mission_id", ""),
                    agent=detail.get("agent", ""),
                    mode=detail.get("mode", ""),
                    brain=detail.get("brain", ""),
                    status=detail.get("status", "unknown"),
                    typed_return_valid=bool(detail.get("typed_return_valid")),
                    connector_isolation_verified=bool(detail.get("connector_isolation_verified")),
                    readback_performed=bool(detail.get("readback_performed")),
                    errors=list(detail.get("errors", [])),
                    ledger_entry=entry,
                    value_observation=detail.get("value_observation"),
                    value_recorded=bool(detail.get("value_recorded")),
                    real_evidence=bool(detail.get("real_evidence")),
                    contract_sha=detail.get("contract_sha", ""),
                    completed_at=detail.get("completed_at", ""),
                )
            )
        # Drop missions whose value record was later revoked by a compensation.
        surviving = [evidence for evidence in recovered if evidence.delegation_id not in revoked]

        # Read-time reconciliation. A crash between the mission append and the
        # value append (or while writing the compensation) leaves a record
        # claiming value_recorded=true with no observation behind it. The
        # compensating entry cannot cover that window, so verify against the
        # value ledger rather than trusting the flag.
        recorded_missions: set[str] = set()
        try:
            recorded_missions = {
                observation.mission_id
                for observation in self.value_ledger.observations(self.value_policy)
            }
        except (ObservationRejected, OSError):
            recorded_missions = set()

        for evidence in surviving:
            if evidence.value_recorded and evidence.mission_id not in recorded_missions:
                evidence.value_recorded = False
                evidence.errors.append(
                    "reconciliation: mission claims a value observation that the "
                    "value ledger does not contain"
                )
        return surviving

    # ---------------------------------------------------------------- helpers

    def _agent_runtime_roster(self) -> dict[str, dict[str, Any]]:
        """Roster shape expected by scripts.agent_runtime.admit_delegation."""
        return {name: {"brain": meta["brain"]} for name, meta in self.roster.items()}

    @staticmethod
    def _cited_source_refs(handoff: dict[str, Any]) -> set[str]:
        """Structured source citations from artifact records."""
        cited: set[str] = set()
        for artifact in handoff.get("artifacts", []) or []:
            if not isinstance(artifact, dict):
                continue
            for record in artifact.get("records", []) or []:
                if isinstance(record, dict):
                    cited.update(record.get("source_refs", []) or [])
            if isinstance(artifact, dict):
                cited.update(artifact.get("source_refs", []) or [])
        for record in handoff.get("evidence", []) or []:
            if isinstance(record, dict) and record.get("source_ref"):
                cited.update([record["source_ref"]])
        return cited

    @staticmethod
    def _delegated_content_tokens(delegation: dict[str, Any]) -> set[str]:
        """Locators that appear *inside* the evidence Agent 007 supplied.

        A delegated email or document routinely contains links. Those are part of
        the content the specialist was given, not evidence it reached past its
        packet, so they must not count as undelegated locators.
        """
        blob = " ".join(
            str(record.get("content", ""))
            for record in delegation.get("allowed_evidence", []) or []
            if isinstance(record, dict)
        )
        return set(LOCATOR_PATTERN.findall(blob))

    @staticmethod
    def _locator_like_tokens(handoff: dict[str, Any]) -> set[str]:
        """Locator-shaped tokens anywhere in the return's free text.

        Checking only ``artifacts[*].records[*].source_refs`` left a hole: a
        specialist could cite an undelegated ``gmail://`` or Drive locator inside
        findings, tests, validation, or notes while attaching one allowed
        artifact record, and still be scored connector-isolation clean. Scheme
        prefixed tokens are the shape a real connector locator takes.
        """
        blob_parts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, str):
                blob_parts.append(node)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, (list, tuple)):
                for value in node:
                    walk(value)

        walk(handoff)
        return {token.rstrip(".") for token in LOCATOR_PATTERN.findall(" ".join(blob_parts))}

    # ------------------------------------------------------------- promotion

    def promotion_status(
        self, evidences: Iterable[MissionEvidence] | None = None
    ) -> dict[str, Any]:
        """Which modes now have a qualifying controlled mission, and which do not.

        Reports the gap honestly: a mode with no qualifying mission is listed as
        uncovered, not omitted. Silence about missing coverage reads as coverage.
        """
        ledger_errors: list[str] = []
        supplied = evidences is not None
        if evidences is None:
            # A broken hash chain means the evidence store has been rewritten.
            # Granting coverage from it would let an edited record promote a
            # mode, so fail closed and grant nothing.
            ledger_errors = self.ledger.verify()
            evidences = [] if ledger_errors else self.evidence_from_ledger()

        # Supplied evidence is convenient for tests but must not be a way to
        # hand-construct coverage. Cross-check each record against the ledger.
        recorded_ids: set[str] = set()
        if supplied:
            ledger_errors = self.ledger.verify()
            if not ledger_errors:
                # Comparing ids alone let a caller reuse a real delegation_id
                # while substituting a different agent, mode, and contract hash.
                # Match the identity fields that decide coverage.
                recorded_ids = {
                    (
                        entry.delegation_id,
                        entry.agent,
                        entry.mode,
                        entry.contract_sha,
                        entry.real_evidence,
                        entry.readback_performed,
                        entry.value_recorded,
                    )
                    for entry in self.evidence_from_ledger()
                }

        qualifying: dict[str, list[str]] = {}
        stale: list[str] = []
        unrecorded: list[str] = []
        for evidence in evidences:
            if not evidence.qualifies_mode:
                continue
            current = self.contract_sha(evidence.agent) if evidence.agent in self.roster else ""
            # An absent hash is stale, not exempt. Defaulting it to "" and then
            # skipping the comparison failed open on the exact binding it added.
            # Checked before ledger membership so genuinely outdated evidence is
            # diagnosed as stale rather than as merely unrecorded.
            if not evidence.contract_sha or evidence.contract_sha != current:
                stale.append(f"{evidence.agent}:{evidence.mode}")
                continue
            fingerprint = (
                evidence.delegation_id,
                evidence.agent,
                evidence.mode,
                evidence.contract_sha,
                evidence.real_evidence,
                evidence.readback_performed,
                evidence.value_recorded,
            )
            if supplied and fingerprint not in recorded_ids:
                unrecorded.append(f"{evidence.agent}:{evidence.mode}")
                continue
            qualifying.setdefault(evidence.agent, []).append(evidence.mode)

        report: dict[str, Any] = {"agents": {}, "total_modes": 0, "covered_modes": 0}
        for name, meta in sorted(self.roster.items()):
            modes = meta.get("modes", [])
            covered = sorted(set(qualifying.get(name, [])) & set(modes))
            uncovered = sorted(set(modes) - set(covered))
            report["total_modes"] += len(modes)
            report["covered_modes"] += len(covered)
            report["agents"][name] = {
                "status": meta.get("status"),
                "brain": meta["brain"],
                "modes": modes,
                "covered_modes": covered,
                "uncovered_modes": uncovered,
                # Every material mode needs its own mission before the agent as a
                # whole can leave shadow. One passing mode never qualifies siblings.
                "all_modes_covered": not uncovered,
            }
        report["agents_fully_covered"] = sorted(
            name for name, entry in report["agents"].items() if entry["all_modes_covered"]
        )
        report["stale_contract_evidence"] = sorted(set(stale))
        report["unrecorded_evidence"] = sorted(set(unrecorded))
        report["ledger_verification_errors"] = ledger_errors
        report["ledger_trustworthy"] = not ledger_errors
        return report


# ------------------------------------------------------------------- catalog


@dataclass(frozen=True)
class CatalogEntry:
    """A prepared mission awaiting live evidence and a baseline.

    Everything except the two things only Joe can supply is settled in advance,
    so a Monday mission is executed rather than designed.
    """

    key: str
    agent: str
    mode: str
    trigger: str
    objective: str
    definition_of_done: list[str]
    definition_of_done_ids: list[str]
    evidence_sources: list[str]
    baseline_prompt: str
    required_artifact_types: list[str]

    def to_spec(
        self,
        evidence: list[EvidenceRecord],
        baseline_minutes: int,
        baseline_source: str = "joe_declared",
    ) -> MissionSpec:
        """Bind live evidence and Joe's baseline into a runnable mission."""
        return MissionSpec(
            agent=self.agent,
            mode=self.mode,
            objective=self.objective.strip(),
            definition_of_done=list(self.definition_of_done),
            definition_of_done_ids=list(self.definition_of_done_ids),
            evidence=evidence,
            baseline_minutes=baseline_minutes,
            baseline_source=baseline_source,
            required_artifact_types=list(self.required_artifact_types),
        )


def load_mission_catalog(root: Path = ROOT) -> dict[str, CatalogEntry]:
    """Load the prepared missions from ``config/mission_catalog.toml``."""
    raw = tomllib.loads((root / "config" / "mission_catalog.toml").read_text(encoding="utf-8"))
    catalog: dict[str, CatalogEntry] = {}
    for entry in raw.get("mission", []):
        catalog[entry["key"]] = CatalogEntry(
            key=entry["key"],
            agent=entry["agent"],
            mode=entry["mode"],
            trigger=entry["trigger"],
            objective=entry["objective"],
            definition_of_done=list(entry["definition_of_done"]),
            definition_of_done_ids=list(entry["definition_of_done_ids"]),
            evidence_sources=list(entry.get("evidence_sources", [])),
            baseline_prompt=entry["baseline_prompt"],
            required_artifact_types=list(entry["required_artifact_types"]),
        )
    return catalog
