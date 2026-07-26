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

import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.agent_runtime import (
    AuditLedger,
    HandoffRejected,
    admit_delegation,
    validate_specialist_return,
)
from scripts.packet_guard import PacketGuard

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "audit" / "missions.jsonl"

# PacketGuard keys its schema table by file name.
DELEGATION_SCHEMA = "delegation_packet.schema.json"
HANDOFF_SCHEMA = "handoff_packet.schema.json"

VALID_EVIDENCE_SENSITIVITY = {"public", "internal", "confidential", "restricted"}


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
            entry = dict(meta)
            entry["brain"] = manifest["brain"]
            entry["roundtable_namespace"] = manifest["roundtable_namespace"]
            roster[name] = entry
    return roster


@dataclass(frozen=True)
class EvidenceRecord:
    """One piece of evidence Agent 007 retrieved and is handing to a specialist.

    ``source_ref`` must locate the real record. ``retrieved_by`` names who called
    the connector — always Agent 007, because specialists have no connector tool.
    """

    source_ref: str
    source_type: str
    sensitivity: str = "internal"
    retrieved_by: str = "apex_chief_of_staff"

    def as_packet_evidence(self, brain: str) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "owner_brain": brain,
            "source_type": self.source_type,
            "scope_verified_by": self.retrieved_by,
            "sensitivity": self.sensitivity,
        }


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
    sensitivity: str = "internal"
    allowed_actions: list[str] = field(default_factory=lambda: ["analyze", "read_packet_evidence"])
    deadline: str | None = None

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
            raise MissionRejected(
                f"{self.agent}: every definition-of-done entry needs a stable id"
            )
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


@dataclass
class PreparedMission:
    """A validated delegation packet, ready for the specialist."""

    spec: MissionSpec
    meta: dict[str, Any]
    delegation: dict[str, Any]
    prepared_at: str

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

    @property
    def qualifies_mode(self) -> bool:
        """Does this single mission satisfy the per-mode controlled-mission gate?"""
        return (
            self.status == "completed"
            and self.typed_return_valid
            and self.connector_isolation_verified
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
    ) -> None:
        self.root = root
        self.roster = load_brain_roster(root)
        self.guard = guard or PacketGuard(root)
        self.ledger = AuditLedger(ledger_path or DEFAULT_LEDGER)

    # ---------------------------------------------------------------- prepare

    def prepare(self, spec: MissionSpec) -> PreparedMission:
        """Build and validate the delegation packet. Raises rather than degrade."""
        meta = self.roster.get(spec.agent)
        if meta is None:
            raise MissionRejected(f"{spec.agent} is not in either brain manifest")
        spec.validated_against(meta)

        brain = meta["brain"]
        run_id = uuid.uuid4().hex[:12]
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
            "required_artifact_types": [meta["artifact_types"][0]],
            "mutation_contract": {
                "allowed_operations": [],
                "require_idempotency_key": True,
                "require_expected_version": True,
            },
        }

        errors = self.guard.validate(DELEGATION_SCHEMA, delegation)
        if errors:
            raise MissionRejected(
                f"{spec.agent}: delegation packet failed PacketGuard: {errors}"
            )

        # Fail-closed admission: schema, addressee match, and the brain lock.
        try:
            admit_delegation(delegation, spec.agent, self._agent_runtime_roster(), self.guard)
        except HandoffRejected as rejection:
            raise MissionRejected(f"{spec.agent}: delegation refused admission: {rejection}")

        self.ledger.append(
            "mission_prepared",
            {
                "delegation_id": delegation["delegation_id"],
                "agent": spec.agent,
                "mode": spec.mode,
                "brain": brain,
                "evidence_count": len(spec.evidence),
                "baseline_minutes": spec.baseline_minutes,
            },
        )

        return PreparedMission(
            spec=spec,
            meta=meta,
            delegation=delegation,
            prepared_at=datetime.now(timezone.utc).isoformat(),
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
        accepted_first_pass: bool = True,
        output_rejected: bool = False,
        readback_performed: bool = False,
        notes: str = "",
    ) -> MissionEvidence:
        """Validate the specialist's typed return and write the evidence record."""
        errors: list[str] = []
        delegation = prepared.delegation
        spec = prepared.spec
        brain = prepared.meta["brain"]

        # 1. The return must be a schema-valid 2.1 handoff bound to this delegation.
        schema_errors = self.guard.validate(
            HANDOFF_SCHEMA, handoff, delegations=[delegation]
        )
        errors.extend(schema_errors)

        # 2. It must survive the runtime's own return validation.
        errors.extend(
            f"return: {error}"
            for error in validate_specialist_return(
                handoff, self.guard, delegations=[delegation]
            )
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
                    errors.append(
                        "lifecycle: shadow-stage specialist reported a performed write"
                    )

        status = str(handoff.get("status", "unknown"))
        typed_return_valid = not schema_errors

        value_observation = {
            "mode": spec.mode,
            "agent": spec.agent,
            "mission_id": delegation["mission_id"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
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

        evidence = MissionEvidence(
            delegation_id=delegation["delegation_id"],
            mission_id=delegation["mission_id"],
            agent=spec.agent,
            mode=spec.mode,
            brain=brain,
            status=status,
            typed_return_valid=typed_return_valid,
            connector_isolation_verified=connector_isolation_verified,
            readback_performed=readback_performed,
            errors=errors,
            ledger_entry=None,
            value_observation=value_observation,
        )

        evidence.ledger_entry = self.ledger.append("mission_completed", evidence.to_json())
        return evidence

    # ---------------------------------------------------------------- helpers

    def _agent_runtime_roster(self) -> dict[str, dict[str, Any]]:
        """Roster shape expected by scripts.agent_runtime.admit_delegation."""
        return {
            name: {"brain": meta["brain"]} for name, meta in self.roster.items()
        }

    @staticmethod
    def _cited_source_refs(handoff: dict[str, Any]) -> set[str]:
        cited: set[str] = set()
        for artifact in handoff.get("artifacts", []) or []:
            if not isinstance(artifact, dict):
                continue
            for record in artifact.get("records", []) or []:
                if isinstance(record, dict):
                    cited.update(record.get("source_refs", []) or [])
        return cited

    # ------------------------------------------------------------- promotion

    def promotion_status(
        self, evidences: Iterable[MissionEvidence]
    ) -> dict[str, Any]:
        """Which modes now have a qualifying controlled mission, and which do not.

        Reports the gap honestly: a mode with no qualifying mission is listed as
        uncovered, not omitted. Silence about missing coverage reads as coverage.
        """
        qualifying: dict[str, list[str]] = {}
        for evidence in evidences:
            if evidence.qualifies_mode:
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
        )


def load_mission_catalog(root: Path = ROOT) -> dict[str, CatalogEntry]:
    """Load the prepared missions from ``config/mission_catalog.toml``."""
    raw = tomllib.loads(
        (root / "config" / "mission_catalog.toml").read_text(encoding="utf-8")
    )
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
        )
    return catalog
