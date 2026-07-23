"""Static, synthetic validation for the mirrored specialist corps.

This harness does not invoke a named agent, call a connector, or complete a
real mission. It parses the deployed configuration and uses PacketGuard to
validate synthetic schema-2.1 packets for every specialist.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.packet_guard import PacketGuard  # noqa: E402
from scripts.privacy_guard import scan_repository  # noqa: E402


RESULT_FIELDS = {
    "valid",
    "validation_mode",
    "named_agents_invoked",
    "connectors_called",
    "real_missions_completed",
    "contract_packets_validated",
    "boundary_rejections_validated",
}


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def _evidence(source_ref: str, brain: str) -> dict[str, Any]:
    return {
        "source_ref": source_ref,
        "owner_brain": brain,
        "source_type": "synthetic",
        "scope_verified_by": "apex_chief_of_staff",
        "sensitivity": "internal",
    }


def _delegation(agent: str, meta: dict[str, Any]) -> dict[str, Any]:
    brain = meta["brain"]
    source_ref = f"synthetic/{agent}/source-1"
    return {
        "schema_version": "2.1",
        "delegation_id": f"validation:{agent}:delegation",
        "mission_id": f"validation:{agent}:mission",
        "resource_id": f"validation:{agent}:resource",
        "agent": agent,
        "owner_brain": brain,
        "memory_namespace": meta["memory_namespace"],
        "roundtable_namespace": f"{brain}::Roundtable",
        "mission": "Validate one synthetic typed specialist return.",
        "definition_of_done": [
            "Return one source-linked typed artifact without performing a mutation."
        ],
        "definition_of_done_ids": ["typed-artifact"],
        "allowed_evidence": [_evidence(source_ref, brain)],
        "allowed_read_namespaces": [meta["memory_namespace"]],
        "allowed_write_targets": [],
        "prohibited_scope": [
            "opposite-brain data",
            "external actions",
            "canonical writes",
        ],
        "allowed_actions": ["analyze", "read_packet_evidence"],
        "writer_agent": None,
        "writer_lease_id": None,
        "deadline": None,
        "dependencies": [],
        "risk_flags": [],
        "approval_level": "L0",
        "sensitivity": "internal",
        "return_schema": "schemas/handoff_packet.schema.json",
        "mode": meta["modes"][0],
        "required_artifact_types": [meta["artifact_types"][0]],
        "mutation_contract": {
            "allowed_operations": [],
            "require_idempotency_key": True,
            "require_expected_version": True,
        },
    }


def _handoff(
    delegation: dict[str, Any], meta: dict[str, Any]
) -> dict[str, Any]:
    agent = delegation["agent"]
    source_ref = delegation["allowed_evidence"][0]["source_ref"]
    record_id = f"validation:{agent}:record-1"
    return {
        "schema_version": "2.1",
        "delegation_id": delegation["delegation_id"],
        "mission_id": delegation["mission_id"],
        "resource_id": delegation["resource_id"],
        "agent": agent,
        "owner_brain": delegation["owner_brain"],
        "memory_namespace": delegation["memory_namespace"],
        "invocation_mode": "delegated",
        "external_actions_performed": False,
        "status": "completed",
        "findings": ["The synthetic contract fixture produced one typed record."],
        "mode": delegation["mode"],
        "artifacts": [
            {
                "artifact_type": meta["artifact_types"][0],
                "records": [
                    {
                        "record_id": record_id,
                        "record_type": "validation_record",
                        "source_refs": [source_ref],
                        "as_of": None,
                        "source_locator": source_ref,
                        "revision": "synthetic-v1",
                        "content_hash": None,
                        "fields": {
                            "fixture": "static-contract",
                            "named_agent_invoked": False,
                        },
                        "confidence": "confirmed",
                    }
                ],
            }
        ],
        "evidence": delegation["allowed_evidence"],
        "tests": ["PacketGuard accepted the synthetic typed return."],
        "assumptions": [],
        "blockers": [],
        "challenges": [],
        "proposed_writes": [],
        "validation": [
            "The artifact record is source-linked and no mutation was proposed."
        ],
        "criterion_validation": [
            {
                "criterion_id": "typed-artifact",
                "status": "passed",
                "evidence_record_ids": [record_id],
                "note": "Validated structurally and relationally by PacketGuard.",
            }
        ],
        "confidence": "confirmed",
        "sensitivity": "internal",
        "recommended_next_handoff": "apex_chief_of_staff",
    }


def _boundary_handoff(
    delegation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": "2.1",
        "delegation_id": delegation["delegation_id"],
        "mission_id": delegation["mission_id"],
        "resource_id": delegation["resource_id"],
        "agent": delegation["agent"],
        "owner_brain": delegation["owner_brain"],
        "memory_namespace": delegation["memory_namespace"],
        "invocation_mode": "delegated",
        "external_actions_performed": False,
        "status": "boundary_blocked",
        "findings": [],
        "mode": delegation["mode"],
        "artifacts": [],
        "evidence": [],
        "tests": [],
        "assumptions": [],
        "blockers": ["BOUNDARY_SCOPE_REJECTED"],
        "challenges": [],
        "proposed_writes": [],
        "validation": [],
        "criterion_validation": [],
        "confidence": "unknown",
        "sensitivity": "internal",
        "recommended_next_handoff": "apex_chief_of_staff",
    }


def _parse_configuration() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest = _load_toml(ROOT / "config" / "specialist_corps.toml")
    apex = _load_toml(ROOT / "brains" / "apex" / "agents.toml")
    jeos = _load_toml(ROOT / "brains" / "jeos" / "agents.toml")
    _load_toml(ROOT / ".codex" / "config.toml")

    roster = manifest["apex_roster"] + manifest["jeos_roster"]
    if len(roster) != 10 or len(set(roster)) != 10:
        errors.append("specialist manifest must contain ten unique agents")
    if apex["roster"] != manifest["apex_roster"]:
        errors.append("APEX brain roster does not match the root manifest")
    if jeos["roster"] != manifest["jeos_roster"]:
        errors.append("JEOS brain roster does not match the root manifest")

    native_paths = sorted((ROOT / ".codex" / "agents").glob("*.toml"))
    parsed_native = {path.stem: _load_toml(path) for path in native_paths}
    expected_native = {"apex_chief_of_staff", *roster}
    if set(parsed_native) != expected_native:
        errors.append("native custom-agent files do not match Agent 007 plus the roster")
    for agent in roster:
        native = parsed_native.get(agent)
        if native is None or native.get("name") != agent:
            errors.append(f"native agent definition is missing or mismatched for {agent}")

    return manifest, errors


def run_validation() -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {
        "valid": False,
        "validation_mode": "static_contract_and_synthetic_packet",
        "named_agents_invoked": False,
        "connectors_called": False,
        "real_missions_completed": False,
        "contract_packets_validated": 0,
        "boundary_rejections_validated": 0,
    }
    errors: list[str] = []

    try:
        manifest, parse_errors = _parse_configuration()
        errors.extend(parse_errors)
        guard = PacketGuard(ROOT)

        for agent in manifest["apex_roster"] + manifest["jeos_roster"]:
            meta = manifest["agents"][agent]
            delegation = _delegation(agent, meta)
            delegation_errors = guard.validate(
                "delegation_packet.schema.json", delegation
            )
            handoff = _handoff(delegation, meta)
            handoff_errors = guard.validate(
                "handoff_packet.schema.json",
                handoff,
                delegations=[delegation],
            )
            if delegation_errors or handoff_errors:
                errors.extend(
                    f"{agent}: delegation: {item}" for item in delegation_errors
                )
                errors.extend(f"{agent}: handoff: {item}" for item in handoff_errors)
            else:
                result["contract_packets_validated"] += 1

            opposite = "JEOS" if meta["brain"] == "APEX" else "APEX"
            contaminated = deepcopy(delegation)
            contaminated["allowed_evidence"] = [
                _evidence(f"{opposite}/synthetic-opposite", opposite)
            ]
            rejection_errors = guard.validate(
                "delegation_packet.schema.json", contaminated
            )
            boundary_errors = guard.validate(
                "handoff_packet.schema.json",
                _boundary_handoff(delegation),
                delegations=[delegation],
            )
            if not rejection_errors:
                errors.append(f"{agent}: opposite-brain delegation was not rejected")
            elif boundary_errors:
                errors.extend(
                    f"{agent}: boundary response: {item}" for item in boundary_errors
                )
            else:
                result["boundary_rejections_validated"] += 1

        privacy_findings = scan_repository(ROOT)
        errors.extend(f"privacy: {item}" for item in privacy_findings)
    except Exception as exc:  # Fail closed while preserving machine-readable stdout.
        errors.append(f"validation harness failed: {exc}")

    result["valid"] = (
        not errors
        and result["contract_packets_validated"] == 10
        and result["boundary_rejections_validated"] == 10
    )
    if set(result) != RESULT_FIELDS:
        errors.append("validation result field set changed unexpectedly")
        result["valid"] = False
    return result, errors


def main() -> int:
    result, errors = run_validation()
    if errors:
        print("\n".join(errors), file=sys.stderr)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
