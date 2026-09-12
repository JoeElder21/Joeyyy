"""First executable APEX slice: Agent 007 -> Delivery Commander technical QA.

Phases, matching the constitution's close-out loop:

    PREPARE  Agent 007 builds a PacketGuard-valid delegation from the catalog
    EXECUTE  the packet-only worker runs (no connector, no write)
    VERIFY   MissionRunner.complete() checks schema, isolation, and criteria
    REPORT   a structured report; specialists remain shadow; no promotion

Synthetic evidence is intentional. A qualifying controlled *real* mission is
still required before any shadow-to-active flip, and this module does not
perform that flip.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.mission_runner import MissionEvidence, MissionRunner, PreparedMission
from runtime.specialist_dispatch import (
    CHIEF,
    V21_APEX_IDENTITIES,
    WIRED_AGENT,
    WIRED_MODE,
    invoke_prepared,
    prepare_first_slice_spec,
)

SLICE_COSTS = {
    "agent_minutes": 1.0,
    "review_minutes": 2.0,
    "correction_minutes": 0.0,
    "maintenance_share_minutes": 0.5,
    "incident_minutes": 0.0,
    "accepted_first_pass": False,
    "readback_performed": True,
    "notes": (
        "First APEX slice VERIFY/REPORT on synthetic public-safe evidence. "
        "Not a promotion-qualifying controlled real mission."
    ),
}


@dataclass
class SliceRun:
    prepared: PreparedMission
    handoff: dict[str, Any]
    evidence: MissionEvidence
    report: dict[str, Any]


def run_first_apex_slice(
    *,
    runner: MissionRunner | None = None,
    ledger_dir: Path | None = None,
) -> SliceRun:
    """Execute PREPARE -> EXECUTE -> VERIFY -> REPORT for the wired mode."""
    workdir = (
        Path(ledger_dir)
        if ledger_dir is not None
        else Path(tempfile.mkdtemp(prefix="joeyyy-first-slice-"))
    )
    workdir.mkdir(parents=True, exist_ok=True)
    working = runner or MissionRunner(
        ledger_path=workdir / "missions.jsonl",
        value_ledger_path=workdir / "value.jsonl",
    )
    spec = prepare_first_slice_spec()
    prepared = working.prepare(spec)
    handoff = invoke_prepared(prepared, runner=working)
    evidence = working.complete(prepared, handoff, **SLICE_COSTS)
    report = build_report(prepared, handoff, evidence, working)
    return SliceRun(prepared=prepared, handoff=handoff, evidence=evidence, report=report)


def build_report(
    prepared: PreparedMission,
    handoff: dict[str, Any],
    evidence: MissionEvidence,
    runner: MissionRunner,
) -> dict[str, Any]:
    """VERIFY + REPORT payload. Lifecycle stays shadow; coverage is not claimed."""
    meta = runner.roster[WIRED_AGENT]
    promotion = runner.promotion_status()
    identities = sorted(
        {
            prepared.delegation["agent"],
            handoff["agent"],
            handoff.get("recommended_next_handoff") or CHIEF,
            CHIEF,
        }
    )
    unknown = [name for name in identities if name not in V21_APEX_IDENTITIES]
    verify = {
        "typed_return_valid": evidence.typed_return_valid,
        "connector_isolation_verified": evidence.connector_isolation_verified,
        "readback_performed": evidence.readback_performed,
        "status": evidence.status,
        "errors": list(evidence.errors),
        "passed": (
            evidence.typed_return_valid
            and evidence.connector_isolation_verified
            and not evidence.errors
            and evidence.status == "completed"
        ),
    }
    return {
        "phase": "REPORT",
        "slice": "first_apex_delivery_commander_technical_qa",
        "orchestrator": CHIEF,
        "specialist": WIRED_AGENT,
        "mode": WIRED_MODE,
        "brain": "APEX",
        "lifecycle": {
            "specialist_status": meta.get("status"),
            "shadow_to_active_flip": False,
            "qualifies_mode": evidence.qualifies_mode,
            "real_evidence": evidence.real_evidence,
            "reason_not_promoted": (
                "Specialists remain shadow. This run used synthetic evidence, "
                "so it cannot satisfy the controlled-real-mission gate."
            ),
        },
        "identities": identities,
        "unknown_identities": unknown,
        "verify": verify,
        "handoff_status": handoff.get("status"),
        "artifact_types": [
            artifact.get("artifact_type")
            for artifact in handoff.get("artifacts") or []
            if isinstance(artifact, dict)
        ],
        "findings": list(handoff.get("findings") or []),
        "challenges": list(handoff.get("challenges") or []),
        "proposed_writes": list(handoff.get("proposed_writes") or []),
        "promotion_status": {
            "covered_modes": promotion.get("covered_modes"),
            "agents_fully_covered": promotion.get("agents_fully_covered"),
        },
        "value_recorded": evidence.value_recorded,
    }


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)
