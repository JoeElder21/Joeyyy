"""Fail-closed relational validation for the Agent 007 specialist corps."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Iterable
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
ACTION_FIELDS = {
    "findings": "analyze",
    "challenges": "challenge",
    "proposed_writes": "propose",
}
BOUNDARY_BLOCKER = "BOUNDARY_SCOPE_REJECTED"


def _matches_type(value: Any, expected: str | list[str]) -> bool:
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    mapping = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "null": type(None),
    }
    return isinstance(value, mapping[expected])


def _structural_errors(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    if "type" in schema and not _matches_type(instance, schema["type"]):
        return [f"{path}: expected {schema['type']}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: not in enum")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: string too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string too long")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], instance):
            errors.append(f"{path}: pattern mismatch")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: too few items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: too many items")
        for index, item in enumerate(instance):
            if "items" in schema:
                errors.extend(_structural_errors(item, schema["items"], f"{path}[{index}]"))
    if isinstance(instance, dict):
        required = set(schema.get("required", []))
        missing = required - set(instance)
        if missing:
            errors.append(f"{path}: missing {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(instance) - set(properties)
            if extras:
                errors.append(f"{path}: extras {sorted(extras)}")
        for key, value in instance.items():
            if key in properties:
                errors.extend(_structural_errors(value, properties[key], f"{path}.{key}"))
    return errors


class PacketGuard:
    """Validate packet shape and relationships against the deployed manifests."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        with (root / "config" / "specialist_corps.toml").open("rb") as source:
            self.manifest = tomllib.load(source)
        self.agents = self.manifest["agents"]
        self.rosters = {
            "APEX": set(self.manifest["apex_roster"]),
            "JEOS": set(self.manifest["jeos_roster"]),
        }
        governance = self.manifest["governance"]
        self.roundtable_targets = {
            "APEX": governance["apex_roundtable_write_target"],
            "JEOS": governance["jeos_roundtable_write_target"],
        }
        self.schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in (root / "schemas").glob("*.schema.json")
        }

    def validate(
        self,
        schema_name: str,
        packet: Any,
        active_leases: Iterable[Any] | None = None,
        *,
        delegations: Iterable[Any] | None = None,
        constraint_packets: Iterable[Any] | None = None,
        private_constraint_packets: Iterable[Any] | None = None,
        mutation_results: Iterable[Any] | None = None,
    ) -> list[str]:
        if schema_name not in self.schemas:
            return [f"$: unknown schema {schema_name}"]
        errors = _structural_errors(packet, self.schemas[schema_name])
        if errors:
            return errors
        errors.extend(self._identifier_errors(packet))
        if errors:
            return errors

        leases = list(active_leases or [])
        delegation_ledger = list(delegations or [])
        constraints = list(constraint_packets or [])
        private_constraints = list(private_constraint_packets or [])
        results = list(mutation_results or [])

        if active_leases is not None:
            errors.extend(self.validate_lease_ledger(leases))
        if constraint_packets is not None:
            errors.extend(self.validate_constraint_ledger(constraints))
        if private_constraint_packets is not None:
            errors.extend(self.validate_private_constraint_ledger(private_constraints))
        if errors:
            return errors

        if schema_name == "delegation_packet.schema.json":
            return self._delegation_errors(packet, leases, constraints, private_constraints)
        if schema_name == "handoff_packet.schema.json":
            return self._handoff_errors(
                packet,
                leases,
                delegation_ledger,
                constraints,
                private_constraints,
            )
        if schema_name == "roundtable_memo.schema.json":
            return self._roundtable_errors(
                packet,
                leases,
                delegation_ledger,
                constraints,
                private_constraints,
            )
        if schema_name == "writer_lease.schema.json":
            return self._writer_lease_errors(packet)
        if schema_name == "memory_record.schema.json":
            return self._memory_record_errors(
                packet,
                leases,
                constraints,
                private_constraints,
                results,
            )
        if schema_name == "cross_brain_constraint_packet.schema.json":
            return self._cross_brain_errors(packet)
        if schema_name == "brain_private_constraint_packet.schema.json":
            return self._private_constraint_errors(packet)
        if schema_name == "mutation_result.schema.json":
            return self._mutation_result_errors(packet, leases)
        return []

    def require_valid(self, schema_name: str, packet: Any, **kwargs: Any) -> None:
        errors = self.validate(schema_name, packet, **kwargs)
        if errors:
            raise ValueError("; ".join(errors))

    def validate_lease_ledger(self, leases: Iterable[Any]) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()
        active_resources: dict[tuple[str, str, str], str] = {}
        for index, lease in enumerate(leases):
            item_errors = self.validate("writer_lease.schema.json", lease)
            if item_errors:
                errors.extend(f"leases[{index}]: {item}" for item in item_errors)
                continue
            if lease["lease_id"] in seen_ids:
                errors.append(f"leases[{index}]: duplicate lease_id {lease['lease_id']!r}")
            seen_ids.add(lease["lease_id"])
            if lease["status"] != "active":
                continue
            key = (
                lease["owner_brain"],
                lease["write_target"],
                self._canonical_identifier(lease["resource_id"]),
            )
            if key in active_resources:
                errors.append(
                    f"duplicate active writer lease for canonical resource {key}: "
                    f"{active_resources[key]} and {lease['lease_id']}"
                )
            else:
                active_resources[key] = lease["lease_id"]
        return errors

    def validate_constraint_ledger(self, packets: Iterable[Any]) -> list[str]:
        return self._validate_id_ledger(
            packets, "cross_brain_constraint_packet.schema.json", "packet_id", "constraints"
        )

    def validate_private_constraint_ledger(self, packets: Iterable[Any]) -> list[str]:
        return self._validate_id_ledger(
            packets,
            "brain_private_constraint_packet.schema.json",
            "packet_id",
            "private_constraints",
        )

    def _validate_id_ledger(
        self,
        packets: Iterable[Any],
        schema_name: str,
        id_field: str,
        label: str,
    ) -> list[str]:
        errors: list[str] = []
        seen: set[str] = set()
        for index, packet in enumerate(packets):
            item_errors = self.validate(schema_name, packet)
            if item_errors:
                errors.extend(f"{label}[{index}]: {item}" for item in item_errors)
                continue
            identifier = packet[id_field]
            if identifier in seen:
                errors.append(f"{label}[{index}]: duplicate {id_field} {identifier!r}")
            seen.add(identifier)
        return errors

    def _agent_relationship_errors(self, packet: dict[str, Any]) -> list[str]:
        agent = packet["agent"]
        if agent not in self.agents:
            return [f"agent {agent!r} is not in the active specialist roster"]
        expected = self.agents[agent]
        errors: list[str] = []
        if packet["owner_brain"] != expected["brain"]:
            errors.append(f"agent {agent} belongs to {expected['brain']}, not {packet['owner_brain']}")
        if packet["memory_namespace"] != expected["memory_namespace"]:
            errors.append(f"agent {agent} must use memory namespace {expected['memory_namespace']}")
        if packet.get("schema_version") == "2.1":
            mode = packet.get("mode")
            if mode == "direct_read_only" and packet.get("invocation_mode") == "direct_read_only":
                pass
            elif mode not in expected.get("modes", []):
                errors.append(f"mode {mode!r} is not registered for agent {agent}")
        return errors

    def _registered_target_errors(self, packet: dict[str, Any]) -> list[str]:
        brain = packet["owner_brain"]
        targets = {
            target
            for agent in self.rosters[brain]
            for target in self.agents[agent]["write_targets"]
        }
        targets.add(self.roundtable_targets[brain])
        errors: list[str] = []
        if packet["write_target"] not in targets:
            errors.append(f"write target is not registered to the {brain} unit")
        elif packet["writer_agent"] not in self._eligible_writers(
            brain, packet["write_target"]
        ):
            errors.append(
                "writer is not eligible for the target at the deployed lifecycle stage"
            )
        return errors

    def _target_owners(self, brain: str, target: str) -> list[str]:
        return [
            agent
            for agent in self.rosters[brain]
            if target in self.agents[agent]["write_targets"]
        ]

    def _eligible_writers(self, brain: str, target: str) -> set[str]:
        eligible = {"apex_chief_of_staff"}
        owners = self._target_owners(brain, target)
        if len(owners) != 1:
            return eligible
        owner = owners[0]
        meta = self.agents[owner]
        if (
            meta.get("status") not in {"active", "value-proven"}
            or not meta.get("active_writer_eligible", False)
        ):
            return eligible
        native_file = self.root / meta["file"]
        try:
            with native_file.open("rb") as source:
                native = tomllib.load(source)
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            return eligible
        if native.get("sandbox_mode") != "read-only":
            eligible.add(owner)
        return eligible

    def _lease_match_errors(
        self,
        packet: dict[str, Any],
        target: str,
        active_leases: list[dict[str, Any]],
    ) -> list[str]:
        if not active_leases:
            return ["write-bearing packet requires the active writer-lease ledger"]
        lease_id = packet.get("writer_lease_id")
        matches = [
            item
            for item in active_leases
            if isinstance(item, dict) and item.get("lease_id") == lease_id
        ]
        if len(matches) != 1:
            return [f"writer lease {lease_id!r} is not uniquely active"]
        lease = matches[0]
        expected = {
            "mission_id": packet["mission_id"],
            "resource_id": packet["resource_id"],
            "owner_brain": packet["owner_brain"],
            "writer_agent": packet.get("writer_agent"),
            "write_target": target,
            "status": "active",
        }
        errors = [
            f"writer lease field {key} must equal {value!r}"
            for key, value in expected.items()
            if lease.get(key) != value
        ]
        term_pairs = [
            ("expected_state", "expected_state"),
            ("validation_readback", "validation_readback"),
            ("rollback", "rollback"),
            ("rollback_method", "rollback"),
            ("sensitivity", "sensitivity"),
        ]
        for packet_field, lease_field in term_pairs:
            if packet_field in packet and packet[packet_field] != lease.get(lease_field):
                errors.append(
                    f"packet field {packet_field} must match lease field {lease_field}"
                )
        return errors

    def _evidence_errors(
        self,
        evidence: list[dict[str, Any]],
        brain: str,
        packet_sensitivity: str,
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
        *,
        mission_id: str,
        resource_id: str,
        agent: str,
        requested_actions: Iterable[str] = (),
    ) -> list[str]:
        errors: list[str] = []
        opposite = "JEOS" if brain == "APEX" else "APEX"
        for item in evidence:
            if item["owner_brain"] != brain:
                errors.append("evidence item belongs to the opposite brain")
            if SENSITIVITY[item["sensitivity"]] > SENSITIVITY[packet_sensitivity]:
                errors.append("evidence-item sensitivity is downgraded")
            source_ref = item["source_ref"]
            source_upper = source_ref.upper()
            if item["source_type"] == "cross_brain_constraint":
                matches = [p for p in constraints if p["packet_id"] == source_ref]
                if len(matches) != 1:
                    errors.append("cross-brain constraint reference is not validated")
                else:
                    constraint = matches[0]
                    if item["sensitivity"] != constraint["sensitivity"]:
                        errors.append(
                            "cross-brain constraint sensitivity metadata does not match "
                            "its validated packet"
                        )
                    expected = {
                        "destination_brain": brain,
                        "destination_agent": agent,
                        "mission_id": mission_id,
                        "resource_id": resource_id,
                    }
                    for field, value in expected.items():
                        if constraint[field] != value:
                            errors.append(
                                f"cross-brain constraint field {field} does not match "
                                "the consuming packet"
                            )
                    disallowed = set(requested_actions) - set(
                        constraint["permitted_actions"]
                    )
                    if disallowed:
                        errors.append(
                            "cross-brain constraint does not permit "
                            f"actions {sorted(disallowed)}"
                        )
            elif item["source_type"] == "brain_private_constraint":
                matches = [p for p in private_constraints if p["packet_id"] == source_ref]
                if len(matches) != 1:
                    errors.append("brain-private constraint reference is not validated")
                else:
                    constraint = matches[0]
                    if item["sensitivity"] != constraint["sensitivity"]:
                        errors.append(
                            "brain-private constraint sensitivity metadata does not match "
                            "its validated packet"
                        )
                    expected = {
                        "owner_brain": brain,
                        "destination_agent": agent,
                        "mission_id": mission_id,
                        "resource_id": resource_id,
                    }
                    for field, value in expected.items():
                        if constraint[field] != value:
                            errors.append(
                                f"brain-private constraint field {field} does not match "
                                "the consuming packet"
                            )
                    disallowed = set(requested_actions) - set(
                        constraint["permitted_actions"]
                    )
                    if disallowed:
                        errors.append(
                            "brain-private constraint does not permit "
                            f"actions {sorted(disallowed)}"
                        )
            elif source_upper.startswith(f"{opposite}::") or source_upper.startswith(
                f"{opposite}/"
            ):
                errors.append("source reference names the opposite brain")
        return errors

    def _delegation_errors(
        self,
        packet: dict[str, Any],
        active_leases: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
    ) -> list[str]:
        errors = self._agent_relationship_errors(packet)
        if errors:
            return errors
        meta = self.agents[packet["agent"]]
        brain = meta["brain"]
        roundtable = f"{brain}::Roundtable"
        if packet["roundtable_namespace"] != roundtable:
            errors.append(f"roundtable must be {roundtable}")
        readable = {meta["memory_namespace"], roundtable}
        for namespace in packet["allowed_read_namespaces"]:
            if namespace not in readable:
                errors.append(
                    f"read namespace {namespace!r} is outside private memory and roundtable"
                )
        errors.extend(
            self._evidence_errors(
                packet["allowed_evidence"],
                brain,
                packet["sensitivity"],
                constraints,
                private_constraints,
                mission_id=packet["mission_id"],
                resource_id=packet["resource_id"],
                agent=packet["agent"],
                requested_actions=packet["allowed_actions"],
            )
        )
        if packet["allowed_evidence"] and "read_packet_evidence" not in packet["allowed_actions"]:
            errors.append(
                "delegation with evidence requires action 'read_packet_evidence'"
            )
        if packet.get("schema_version") == "2.1":
            required_v21 = [
                "mode",
                "definition_of_done_ids",
                "required_artifact_types",
                "mutation_contract",
            ]
            for field in required_v21:
                if field not in packet:
                    errors.append(f"2.1 delegation requires field {field}")
            criterion_ids = packet.get("definition_of_done_ids", [])
            if len(criterion_ids) != len(packet["definition_of_done"]):
                errors.append(
                    "2.1 definition_of_done_ids must align one-to-one with definition_of_done"
                )
            if len(criterion_ids) != len(set(criterion_ids)):
                errors.append("2.1 definition_of_done_ids must be unique")
            requested_types = set(packet.get("required_artifact_types", []))
            if not requested_types.issubset(set(meta.get("artifact_types", []))):
                errors.append(
                    "2.1 required artifact type is not registered to the selected agent"
                )
        allowed_targets = set(meta["write_targets"])
        for target in packet["allowed_write_targets"]:
            if target not in allowed_targets:
                errors.append(f"write target {target!r} is outside {packet['agent']}'s allowlist")
        if packet["allowed_write_targets"]:
            target = packet["allowed_write_targets"][0]
            if packet["writer_agent"] not in self._eligible_writers(brain, target):
                errors.append(
                    "delegation writer is not eligible for the target at the deployed stage"
                )
            if not packet["writer_lease_id"]:
                errors.append("a write-bearing delegation requires a writer lease")
            errors.extend(
                self._lease_match_errors(
                    packet, target, active_leases
                )
            )
        elif packet["writer_agent"] is not None or packet["writer_lease_id"] is not None:
            errors.append("read-only delegation must not name a writer or lease")
        return errors

    def _validated_delegation(
        self,
        packet: dict[str, Any],
        active_leases: list[dict[str, Any]],
        delegations: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, list[str]]:
        delegation_id = packet["delegation_id"]
        matches = [
            item
            for item in delegations
            if isinstance(item, dict) and item.get("delegation_id") == delegation_id
        ]
        if len(matches) != 1:
            return None, [f"delegation {delegation_id!r} is not uniquely validated"]
        delegation = matches[0]
        errors = self.validate(
            "delegation_packet.schema.json",
            delegation,
            active_leases,
            constraint_packets=constraints,
            private_constraint_packets=private_constraints,
        )
        if errors:
            return None, [f"originating delegation invalid: {item}" for item in errors]
        for field in [
            "mission_id",
            "resource_id",
            "agent",
            "owner_brain",
            "memory_namespace",
        ]:
            if packet[field] != delegation[field]:
                errors.append(f"handoff field {field} must match originating delegation")
        if packet.get("schema_version") == "2.1" and packet.get("mode") != delegation.get(
            "mode"
        ):
            errors.append("2.1 handoff mode must match originating delegation")
        return delegation, errors

    def _handoff_errors(
        self,
        packet: dict[str, Any],
        active_leases: list[dict[str, Any]],
        delegations: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
    ) -> list[str]:
        errors = self._agent_relationship_errors(packet)
        if errors:
            return errors
        meta = self.agents[packet["agent"]]
        delegation: dict[str, Any] | None = None

        if packet["status"] == "boundary_blocked":
            for field in [
                "findings",
                "evidence",
                "tests",
                "assumptions",
                "challenges",
                "proposed_writes",
                "validation",
            ]:
                if packet[field]:
                    errors.append(f"boundary_blocked handoff must keep {field} empty")
            for field in ["artifacts", "criterion_validation"]:
                if packet.get(field):
                    errors.append(f"boundary_blocked handoff must keep {field} empty")
            if packet["blockers"] != [BOUNDARY_BLOCKER]:
                errors.append(
                    f"boundary_blocked handoff must use only the safe sentinel "
                    f"{BOUNDARY_BLOCKER!r}"
                )
            if packet["recommended_next_handoff"] != "apex_chief_of_staff":
                errors.append("boundary_blocked handoff must return to Agent 007")
            if packet["confidence"] != "unknown":
                errors.append("boundary_blocked confidence must be unknown")
        elif packet["status"] == "blocked":
            if not packet["blockers"]:
                errors.append("blocked handoff requires at least one blocker")
            if packet["proposed_writes"]:
                errors.append("blocked handoff cannot propose a canonical write")
            if packet["recommended_next_handoff"] != "apex_chief_of_staff":
                errors.append("blocked handoff must return to Agent 007")
        elif packet["status"] == "completed":
            if packet["blockers"]:
                errors.append("completed handoff cannot contain unresolved blockers")
            for field in ["findings", "tests", "validation"]:
                if not packet[field]:
                    errors.append(f"completed handoff requires nonempty {field}")
            if packet["confidence"] in {"assumption", "unknown"}:
                errors.append("completed handoff requires judgment-or-better confidence")

        if packet["invocation_mode"] == "direct_read_only":
            if packet["delegation_id"] is not None:
                errors.append("direct_read_only delegation_id must be null")
            if packet["mission_id"] != f"direct:{packet['agent']}":
                errors.append("direct_read_only mission_id must use direct:<agent>")
            if packet["resource_id"] != "current-message":
                errors.append("direct_read_only resource_id must be current-message")
            if packet["status"] not in {"partial", "boundary_blocked"}:
                errors.append("direct_read_only status must be partial or boundary_blocked")
            if packet["proposed_writes"] or packet["evidence"]:
                errors.append("direct_read_only cannot propose writes or emit source evidence")
            if packet["sensitivity"] != "restricted":
                errors.append(
                    "unclassified direct_read_only content must remain restricted"
                )
            if packet["recommended_next_handoff"] != "apex_chief_of_staff":
                errors.append("direct_read_only handoff must return to Agent 007")
            if packet.get("schema_version") == "2.1" and packet.get("mode") != (
                "direct_read_only"
            ):
                errors.append("2.1 direct_read_only handoff mode must be direct_read_only")
        else:
            if packet["delegation_id"] is None:
                errors.append("delegated handoff requires delegation_id")
            else:
                delegation, delegation_errors = self._validated_delegation(
                    packet,
                    active_leases,
                    delegations,
                    constraints,
                    private_constraints,
                )
                errors.extend(delegation_errors)

        if delegation is not None:
            if (
                SENSITIVITY[packet["sensitivity"]]
                < SENSITIVITY[delegation["sensitivity"]]
            ):
                errors.append("handoff sensitivity is lower than its delegation")
            allowed_evidence = delegation["allowed_evidence"]
            for item in packet["evidence"]:
                if item not in allowed_evidence:
                    errors.append(
                        "handoff evidence does not exactly match delegated evidence"
                    )
                if item["owner_brain"] != packet["owner_brain"]:
                    errors.append("handoff evidence crosses the owner brain")
                if SENSITIVITY[item["sensitivity"]] > SENSITIVITY[packet["sensitivity"]]:
                    errors.append("handoff sensitivity is lower than its evidence")
                if (
                    SENSITIVITY[item["sensitivity"]]
                    < SENSITIVITY[delegation["sensitivity"]]
                ):
                    errors.append("handoff evidence sensitivity is lower than its delegation")
            if packet["status"] == "completed":
                if delegation["allowed_evidence"] and not packet["evidence"]:
                    errors.append("completed handoff must return source-linked evidence")
                if len(packet["validation"]) < len(delegation["definition_of_done"]):
                    errors.append(
                        "completed handoff must validate every definition-of-done criterion"
                    )
            allowed_actions = set(delegation["allowed_actions"])
            for field, action in ACTION_FIELDS.items():
                if packet[field] and action not in allowed_actions:
                    errors.append(
                        f"handoff field {field} requires delegated action {action!r}"
                    )

        if packet.get("schema_version") == "2.1":
            for field in ["mode", "artifacts", "criterion_validation"]:
                if field not in packet:
                    errors.append(f"2.1 handoff requires field {field}")
            record_ids: set[str] = set()
            artifact_types: set[str] = set()
            delegated_source_refs = {item["source_ref"] for item in packet["evidence"]}
            for artifact in packet.get("artifacts", []):
                artifact_type = artifact["artifact_type"]
                artifact_types.add(artifact_type)
                if artifact_type not in set(meta.get("artifact_types", [])):
                    errors.append(
                        f"artifact type {artifact_type!r} is not registered to {packet['agent']}"
                    )
                for record in artifact["records"]:
                    record_id = record["record_id"]
                    if record_id in record_ids:
                        errors.append(f"duplicate artifact record_id {record_id!r}")
                    record_ids.add(record_id)
                    if not record["fields"]:
                        errors.append(
                            f"artifact record {record_id!r} must contain structured fields"
                        )
                    if not set(record["source_refs"]).issubset(delegated_source_refs):
                        errors.append(
                            f"artifact record {record_id!r} cites undelegated evidence"
                        )
            criterion_items = packet.get("criterion_validation", [])
            criterion_ids = [item["criterion_id"] for item in criterion_items]
            if len(criterion_ids) != len(set(criterion_ids)):
                errors.append("criterion_validation criterion_id values must be unique")
            for item in criterion_items:
                if not set(item["evidence_record_ids"]).issubset(record_ids):
                    errors.append(
                        f"criterion {item['criterion_id']!r} cites an unknown artifact record"
                    )
            if packet["status"] == "completed":
                if not packet.get("artifacts"):
                    errors.append("completed 2.1 handoff requires typed artifacts")
                if delegation is not None:
                    required_types = set(delegation["required_artifact_types"])
                    if not required_types.issubset(artifact_types):
                        errors.append(
                            "completed 2.1 handoff is missing a required artifact type"
                        )
                    required_criteria = delegation["definition_of_done_ids"]
                    if set(criterion_ids) != set(required_criteria):
                        errors.append(
                            "completed 2.1 handoff must validate every stable criterion ID"
                        )
                    if any(item["status"] != "passed" for item in criterion_items):
                        errors.append(
                            "completed 2.1 handoff requires every criterion to pass"
                        )

        delegated_targets = set(delegation["allowed_write_targets"]) if delegation else set()
        for proposed in packet["proposed_writes"]:
            if proposed["target"] not in set(meta["write_targets"]):
                errors.append(
                    f"write target {proposed['target']!r} is outside {packet['agent']}'s allowlist"
                )
            if delegation is not None and proposed["target"] not in delegated_targets:
                errors.append("proposed write exceeds originating delegation")
            if proposed["writer_agent"] not in self._eligible_writers(
                packet["owner_brain"], proposed["target"]
            ):
                errors.append(
                    "proposed writer is not eligible for the target at the deployed stage"
                )
            if delegation is not None and proposed["writer_agent"] != delegation["writer_agent"]:
                errors.append("proposed writer must match originating delegation")
            if packet.get("schema_version") == "2.1":
                required_proposal = [
                    "operation",
                    "record_type",
                    "artifact_record_ids",
                    "idempotency_key",
                    "expected_version",
                ]
                for field in required_proposal:
                    if field not in proposed:
                        errors.append(f"2.1 proposed write requires field {field}")
                if not set(proposed.get("artifact_record_ids", [])).issubset(record_ids):
                    errors.append("2.1 proposed write cites an unknown artifact record")
                if delegation is not None:
                    allowed_operations = set(
                        delegation["mutation_contract"]["allowed_operations"]
                    )
                    if proposed.get("operation") not in allowed_operations:
                        errors.append(
                            "2.1 proposed-write operation exceeds mutation contract"
                        )
                    if (
                        delegation["mutation_contract"]["require_expected_version"]
                        and proposed.get("expected_version") is None
                    ):
                        errors.append(
                            "2.1 mutation contract requires an expected version"
                        )
            lease_packet = {
                **packet,
                **proposed,
                "write_target": proposed["target"],
            }
            errors.extend(
                self._lease_match_errors(lease_packet, proposed["target"], active_leases)
            )

        next_agent = packet["recommended_next_handoff"]
        permitted = {*self.rosters[meta["brain"]], "apex_chief_of_staff"}
        if next_agent is not None and next_agent not in permitted:
            errors.append(f"recommended handoff {next_agent!r} crosses or bypasses the roster")
        if (
            delegation is not None
            and next_agent not in {None, "apex_chief_of_staff"}
            and "handoff" not in delegation["allowed_actions"]
        ):
            errors.append("specialist-to-specialist handoff requires delegated action 'handoff'")
        return errors

    def _roundtable_errors(
        self,
        packet: dict[str, Any],
        active_leases: list[dict[str, Any]],
        delegations: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
    ) -> list[str]:
        brain = packet["owner_brain"]
        errors: list[str] = []
        if packet["roundtable_namespace"] != f"{brain}::Roundtable":
            errors.append(f"roundtable must be {brain}::Roundtable")
        if packet["status"] == "resolved":
            if not packet["resolution"]:
                errors.append("resolved roundtable memo requires a resolution")
            if packet["confidence"] == "unknown":
                errors.append("resolved roundtable memo cannot have unknown confidence")
        elif packet["resolution"] is not None:
            errors.append("unresolved roundtable memo must not claim a resolution")
        if packet["status"] == "blocked" and not packet.get("body"):
            errors.append("blocked roundtable memo requires a blocker explanation")
        allowed = self.rosters[brain]
        if packet["from_agent"] not in allowed:
            errors.append("roundtable sender is not a member of the owner brain")
        invalid = set(packet["to_agents"]) - allowed
        if invalid:
            errors.append(f"roundtable recipients cross the owner brain: {sorted(invalid)}")
        delegation_packet = {
            "delegation_id": packet["delegation_id"],
            "mission_id": packet["mission_id"],
            "resource_id": packet["resource_id"],
            "agent": packet["from_agent"],
            "owner_brain": packet["owner_brain"],
            "memory_namespace": self.agents.get(packet["from_agent"], {}).get(
                "memory_namespace", ""
            ),
        }
        delegation, delegation_errors = self._validated_delegation(
            delegation_packet,
            active_leases,
            delegations,
            constraints,
            private_constraints,
        )
        errors.extend(delegation_errors)
        if delegation is not None:
            if (
                SENSITIVITY[packet["sensitivity"]]
                < SENSITIVITY[delegation["sensitivity"]]
            ):
                errors.append("roundtable sensitivity is lower than its delegation")
            allowed_evidence = delegation["allowed_evidence"]
            for item in packet["evidence"]:
                if item not in allowed_evidence:
                    errors.append(
                        "roundtable evidence does not exactly match originating delegation"
                    )
                if item["owner_brain"] != brain:
                    errors.append("roundtable evidence crosses the owner brain")
                if SENSITIVITY[item["sensitivity"]] > SENSITIVITY[packet["sensitivity"]]:
                    errors.append("roundtable sensitivity is lower than its evidence")
                if (
                    SENSITIVITY[item["sensitivity"]]
                    < SENSITIVITY[delegation["sensitivity"]]
                ):
                    errors.append("roundtable evidence sensitivity is lower than delegation")
            action_for_type = {
                "ask": "handoff",
                "challenge": "challenge",
                "handoff": "handoff",
                "information": "analyze",
                "conflict": "challenge",
            }[packet["message_type"]]
            if action_for_type not in delegation["allowed_actions"]:
                errors.append(
                    f"roundtable message type {packet['message_type']!r} requires "
                    f"delegated action {action_for_type!r}"
                )
        timestamp = self._parse_timestamp(packet["timestamp"], "timestamp", errors)
        now = datetime.now(timezone.utc)
        if timestamp and timestamp > now + timedelta(minutes=5):
            errors.append("roundtable timestamp is in the future")
        target = self.roundtable_targets[brain]
        if packet["writer_agent"] is None:
            if packet["writer_lease_id"] is not None or packet["write_target"] is not None:
                errors.append("advisory roundtable memo cannot name a lease or target")
        else:
            if packet["writer_agent"] != "apex_chief_of_staff":
                errors.append("only Agent 007 may write a shadow-stage roundtable memo")
            if packet["write_target"] != target:
                errors.append(f"roundtable write target must be {target}")
            errors.extend(self._lease_match_errors(packet, target, active_leases))
            lease = self._matching_lease(packet, active_leases)
            if lease is not None and timestamp is not None:
                errors.extend(
                    self._timestamp_within_lease_errors(
                        timestamp, "timestamp", lease
                    )
                )
        return errors

    def _writer_lease_errors(self, packet: dict[str, Any]) -> list[str]:
        errors = self._registered_target_errors(packet)
        issued = self._parse_timestamp(packet["issued_at"], "issued_at", errors)
        expires = None
        if packet["expires_at"] is not None:
            expires = self._parse_timestamp(packet["expires_at"], "expires_at", errors)
        if issued and expires and expires <= issued:
            errors.append("writer lease expires_at must be after issued_at")
        if packet["status"] == "active" and expires is None:
            errors.append("active writer lease requires expires_at")
        if issued and expires and (expires - issued) > timedelta(hours=24):
            errors.append("writer lease lifetime exceeds 24 hours")
        if (
            packet["status"] == "active"
            and issued
            and issued > datetime.now(timezone.utc) + timedelta(minutes=5)
        ):
            errors.append("active writer lease is not yet valid")
        if packet["status"] == "active" and expires and expires <= datetime.now(timezone.utc):
            errors.append("active writer lease is expired")
        return errors

    def _memory_record_errors(
        self,
        packet: dict[str, Any],
        active_leases: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        private_constraints: list[dict[str, Any]],
        mutation_results: list[dict[str, Any]],
    ) -> list[str]:
        brain = packet["owner_brain"]
        owners = [
            agent
            for agent in self.rosters[brain]
            if self.agents[agent]["memory_namespace"] == packet["memory_namespace"]
        ]
        if len(owners) != 1:
            return ["memory namespace does not resolve to exactly one owner-brain agent"]
        owner = owners[0]
        errors: list[str] = []
        if packet["write_target"] not in self.agents[owner]["write_targets"]:
            errors.append("memory target is outside the namespace owner's allowlist")
        if packet["writer_agent"] not in self._eligible_writers(
            brain, packet["write_target"]
        ):
            errors.append(
                "memory writer is not eligible for the target at the deployed stage"
            )
        created_at = self._parse_timestamp(packet["created_at"], "created_at", errors)
        if created_at and created_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            errors.append("memory record created_at is in the future")
        errors.extend(
            self._evidence_errors(
                packet["source_refs"],
                brain,
                packet["sensitivity"],
                constraints,
                private_constraints,
                mission_id=packet["mission_id"],
                resource_id=packet["resource_id"],
                agent=owner,
                requested_actions=("propose",),
            )
        )
        errors.extend(self._lease_match_errors(packet, packet["write_target"], active_leases))
        lease = self._matching_lease(packet, active_leases)
        if lease is not None and created_at is not None:
            errors.extend(
                self._timestamp_within_lease_errors(
                    created_at, "created_at", lease
                )
            )
        if packet["status"] == "proposed" and packet["mutation_result_id"] is not None:
            errors.append("proposed memory record cannot claim a mutation result")
        if packet["status"] in {"written", "superseded", "retracted"}:
            matches = [
                result
                for result in mutation_results
                if isinstance(result, dict)
                and result.get("result_id") == packet["mutation_result_id"]
            ]
            if len(matches) != 1:
                errors.append("mutated memory record requires one linked mutation result")
            else:
                result = matches[0]
                result_errors = self.validate(
                    "mutation_result.schema.json", result, active_leases
                )
                if result_errors:
                    errors.extend(f"linked mutation result invalid: {item}" for item in result_errors)
                for field in [
                    "mission_id",
                    "resource_id",
                    "owner_brain",
                    "writer_agent",
                    "writer_lease_id",
                    "write_target",
                ]:
                    if result.get(field) != packet[field]:
                        errors.append(f"linked mutation result field {field} does not match")
                if result.get("status") != "verified":
                    errors.append("linked memory mutation result must be verified")
        return errors

    def _cross_brain_errors(self, packet: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if packet["source_brain"] == packet["destination_brain"]:
            errors.append("cross-brain constraint packet must name two different brains")
        if packet["destination_agent"] not in self.rosters[packet["destination_brain"]]:
            errors.append("cross-brain destination agent is outside destination roster")
        if not re.fullmatch(r"[0-9a-f]{64}", packet["source_proof_hash"]):
            errors.append("source_proof_hash must be a lowercase SHA-256 digest")
        if "\n" in packet["constraint_summary"]:
            errors.append("constraint summary must be one minimized line")
        errors.extend(self._expiring_packet_errors(packet, maximum_hours=168))
        return errors

    def _private_constraint_errors(self, packet: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if packet["owner_brain"] != "JEOS":
            errors.append("brain-private sensitive constraints are JEOS-only")
        if packet["destination_agent"] not in self.rosters[packet["owner_brain"]]:
            errors.append("private constraint destination agent is outside owner brain")
        else:
            profile = (
                f"{packet['constraint_type']}:{packet.get('use_mode')}"
                if packet.get("use_mode")
                else packet["constraint_type"]
            )
            allowed = set(
                self.agents[packet["destination_agent"]].get(
                    "private_constraint_profiles", []
                )
            )
            if packet.get("schema_version") == "2.1":
                if "use_mode" not in packet:
                    errors.append("2.1 private constraint requires use_mode")
                elif profile not in allowed:
                    errors.append(
                        "private constraint profile is not allowed for destination agent"
                    )
            elif not any(item.startswith(f"{packet['constraint_type']}:") for item in allowed):
                errors.append(
                    "private constraint type is not allowed for destination agent"
                )
        if not re.fullmatch(r"[0-9a-f]{64}", packet["source_proof_hash"]):
            errors.append("source_proof_hash must be a lowercase SHA-256 digest")
        if "\n" in packet["constraint_summary"]:
            errors.append("constraint summary must be one minimized line")
        errors.extend(self._expiring_packet_errors(packet, maximum_hours=168))
        return errors

    def _expiring_packet_errors(
        self, packet: dict[str, Any], maximum_hours: int
    ) -> list[str]:
        errors: list[str] = []
        issued = self._parse_timestamp(packet["issued_at"], "issued_at", errors)
        expires = self._parse_timestamp(packet["expires_at"], "expires_at", errors)
        now = datetime.now(timezone.utc)
        if issued and expires:
            if expires <= issued:
                errors.append("constraint expires_at must be after issued_at")
            if (expires - issued).total_seconds() > maximum_hours * 3600:
                errors.append("constraint lifetime exceeds maximum")
            if issued > now + timedelta(minutes=5):
                errors.append("constraint packet is not yet valid")
            if expires <= now:
                errors.append("constraint packet is expired")
        return errors

    def _mutation_result_errors(
        self, packet: dict[str, Any], active_leases: list[dict[str, Any]]
    ) -> list[str]:
        errors = self._registered_target_errors(packet)
        verified_at: datetime | None = None
        if packet["status"] == "verified":
            if not packet["observed_state"]:
                errors.append("verified mutation requires observed target state")
            if packet["expected_state_verified"] is not True:
                errors.append("verified mutation must affirm the expected state")
            if packet["observed_state"] != packet["expected_state"]:
                errors.append(
                    "verified mutation observed_state must exactly match expected_state"
                )
            if not packet["readback_evidence"]:
                errors.append("verified mutation requires readback evidence")
            if not packet["verified_at"]:
                errors.append("verified mutation requires a verification timestamp")
            else:
                verified_at = self._parse_timestamp(
                    packet["verified_at"], "verified_at", errors
                )
            if packet["rollback_test_status"] != "verified":
                errors.append("verified mutation requires a verified rollback test")
            if not packet["rollback_evidence"]:
                errors.append("verified mutation requires rollback-test evidence")
            if packet["error"] is not None:
                errors.append("verified mutation cannot contain an error")
        if packet["status"] == "failed" and not packet["error"]:
            errors.append("failed mutation requires an error")
        if packet["status"] == "rolled_back":
            if not packet["observed_state"] or not packet["readback_evidence"]:
                errors.append("rolled-back mutation requires observed state and readback evidence")
            if packet["rollback_test_status"] != "verified" or not packet["rollback_evidence"]:
                errors.append("rolled-back mutation requires verified rollback evidence")
            if not packet["verified_at"]:
                errors.append("rolled-back mutation requires a verification timestamp")
            else:
                verified_at = self._parse_timestamp(
                    packet["verified_at"], "verified_at", errors
                )
        if packet["status"] not in {"verified", "rolled_back"} and packet["verified_at"] is not None:
            errors.append("unverified mutation must not claim a verification timestamp")
        errors.extend(self._lease_match_errors(packet, packet["write_target"], active_leases))
        lease = self._matching_lease(packet, active_leases)
        if lease is not None and verified_at is not None:
            errors.extend(
                self._timestamp_within_lease_errors(
                    verified_at, "verified_at", lease
                )
            )
        return errors

    @staticmethod
    def _canonical_identifier(value: str) -> str:
        return unicodedata.normalize("NFKC", value).strip().casefold()

    def _identifier_errors(self, packet: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field in [
            "delegation_id",
            "mission_id",
            "resource_id",
            "lease_id",
            "packet_id",
            "record_id",
            "result_id",
            "memo_id",
        ]:
            value = packet.get(field)
            if not isinstance(value, str):
                continue
            if value != unicodedata.normalize("NFKC", value):
                errors.append(f"{field} must use canonical Unicode")
            if value != value.strip() or any(character.isspace() for character in value):
                errors.append(f"{field} must not contain whitespace")
            if any(unicodedata.category(character).startswith("C") for character in value):
                errors.append(f"{field} must not contain control characters")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value):
                errors.append(f"{field} must use the canonical ASCII identifier alphabet")
        return errors

    @staticmethod
    def _matching_lease(
        packet: dict[str, Any], active_leases: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        lease_id = packet.get("writer_lease_id")
        matches = [
            lease
            for lease in active_leases
            if isinstance(lease, dict) and lease.get("lease_id") == lease_id
        ]
        return matches[0] if len(matches) == 1 else None

    def _timestamp_within_lease_errors(
        self, timestamp: datetime, field: str, lease: dict[str, Any]
    ) -> list[str]:
        errors: list[str] = []
        issued = self._parse_timestamp(lease["issued_at"], "lease.issued_at", errors)
        expires = None
        if lease["expires_at"] is not None:
            expires = self._parse_timestamp(
                lease["expires_at"], "lease.expires_at", errors
            )
        if issued and timestamp < issued:
            errors.append(f"{field} precedes writer-lease issuance")
        if expires and timestamp > expires:
            errors.append(f"{field} occurs after writer-lease expiry")
        if timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
            errors.append(f"{field} is in the future")
        return errors

    @staticmethod
    def _parse_timestamp(value: str, field: str, errors: list[str]) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            errors.append(f"{field} must be an ISO-8601 timestamp")
            return None
        if parsed.tzinfo is None:
            errors.append(f"{field} must include a timezone")
            return None
        return parsed.astimezone(timezone.utc)


def _read_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an Agent 007 packet.")
    parser.add_argument("schema", choices=sorted(PacketGuard().schemas))
    parser.add_argument("packet", help="JSON packet path, or - for stdin")
    parser.add_argument("--leases", help="JSON array of writer leases")
    parser.add_argument("--delegations", help="JSON array of delegation packets")
    parser.add_argument("--constraints", help="JSON array of cross-brain constraints")
    parser.add_argument("--private-constraints", help="JSON array of brain-private constraints")
    parser.add_argument("--mutation-results", help="JSON array of mutation results")
    args = parser.parse_args(argv)

    guard = PacketGuard()
    kwargs = {
        "active_leases": _read_json(args.leases) if args.leases else None,
        "delegations": _read_json(args.delegations) if args.delegations else None,
        "constraint_packets": _read_json(args.constraints) if args.constraints else None,
        "private_constraint_packets": (
            _read_json(args.private_constraints) if args.private_constraints else None
        ),
        "mutation_results": (
            _read_json(args.mutation_results) if args.mutation_results else None
        ),
    }
    errors = guard.validate(args.schema, _read_json(args.packet), **kwargs)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 1
    print(json.dumps({"valid": True, "errors": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
