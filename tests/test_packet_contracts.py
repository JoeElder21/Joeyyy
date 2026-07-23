from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.packet_guard import PacketGuard


ROOT = Path(__file__).resolve().parents[1]


def evidence(ref="synthetic-goals-v1", brain="APEX", sensitivity="internal", source_type="synthetic"):
    return {
        "source_ref": ref,
        "owner_brain": brain,
        "source_type": source_type,
        "scope_verified_by": "apex_chief_of_staff",
        "sensitivity": sensitivity,
    }


class PacketContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        now = datetime.now(timezone.utc)
        issued_at = (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        expires_at = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        cls.guard = PacketGuard(ROOT)
        cls.lease = {
            "schema_version": "2.0",
            "lease_id": "lease-1",
            "mission_id": "mission-1",
            "resource_id": "resource-1",
            "owner_brain": "APEX",
            "writer_agent": "apex_chief_of_staff",
            "write_target": "APEX/Strategy-Campaigns",
            "issued_by": "apex_chief_of_staff",
            "issued_at": issued_at,
            "expires_at": expires_at,
            "status": "active",
            "expected_state": "One campaign row.",
            "validation_readback": "Read by mission ID.",
            "rollback": "Delete by mission ID.",
            "sensitivity": "internal",
        }
        cls.delegation = {
            "schema_version": "2.0",
            "delegation_id": "delegation-1",
            "mission_id": "mission-1",
            "resource_id": "resource-1",
            "agent": "apex_war_architect",
            "owner_brain": "APEX",
            "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
            "roundtable_namespace": "APEX::Roundtable",
            "mission": "Build a weekly operating campaign.",
            "definition_of_done": ["Three priorities with owners and stop rules."],
            "allowed_evidence": [evidence()],
            "allowed_read_namespaces": ["APEX::Strategy-Campaigns::apex_war_architect"],
            "allowed_write_targets": ["APEX/Strategy-Campaigns"],
            "prohibited_scope": ["JEOS", "binding commitments"],
            "allowed_actions": [
                "analyze",
                "read_packet_evidence",
                "propose",
                "challenge",
                "handoff",
            ],
            "writer_agent": "apex_chief_of_staff",
            "writer_lease_id": "lease-1",
            "deadline": None,
            "dependencies": [],
            "risk_flags": [],
            "approval_level": "L1",
            "sensitivity": "internal",
            "return_schema": "schemas/handoff_packet.schema.json",
        }
        cls.handoff = {
            "schema_version": "2.0",
            "delegation_id": "delegation-1",
            "mission_id": "mission-1",
            "resource_id": "resource-1",
            "agent": "apex_war_architect",
            "owner_brain": "APEX",
            "memory_namespace": "APEX::Strategy-Campaigns::apex_war_architect",
            "invocation_mode": "delegated",
            "external_actions_performed": False,
            "status": "completed",
            "findings": ["Priority one is source-backed."],
            "evidence": [evidence()],
            "tests": ["priority-count"],
            "assumptions": [],
            "blockers": [],
            "challenges": [],
            "proposed_writes": [
                {
                    "target": "APEX/Strategy-Campaigns",
                    "expected_state": "One campaign row.",
                    "validation_readback": "Read by mission ID.",
                    "rollback": "Delete by mission ID.",
                    "writer_agent": "apex_chief_of_staff",
                    "writer_lease_id": "lease-1",
                }
            ],
            "validation": ["Source and target match."],
            "confidence": "source-backed",
            "sensitivity": "internal",
            "recommended_next_handoff": "apex_intelligence_forge",
        }

    def assertValid(self, schema_name, packet, leases=None, **kwargs):
        self.assertEqual(
            self.guard.validate(schema_name, packet, leases, **kwargs),
            [],
        )

    def assertInvalid(self, schema_name, packet, leases=None, **kwargs):
        self.assertNotEqual(
            self.guard.validate(schema_name, packet, leases, **kwargs),
            [],
        )

    def v21_readonly_pair(self):
        delegation = deepcopy(self.delegation)
        delegation.update(
            {
                "schema_version": "2.1",
                "allowed_write_targets": [],
                "writer_agent": None,
                "writer_lease_id": None,
                "mode": "operating_campaign",
                "definition_of_done_ids": ["campaign-source-proof"],
                "required_artifact_types": ["campaign_map"],
                "mutation_contract": {
                    "allowed_operations": [],
                    "require_idempotency_key": True,
                    "require_expected_version": True,
                },
            }
        )
        handoff = deepcopy(self.handoff)
        record_id = "campaign-map-record-1"
        handoff.update(
            {
                "schema_version": "2.1",
                "mode": "operating_campaign",
                "artifacts": [
                    {
                        "artifact_type": "campaign_map",
                        "records": [
                            {
                                "record_id": record_id,
                                "record_type": "campaign_record",
                                "source_refs": ["synthetic-goals-v1"],
                                "as_of": None,
                                "source_locator": "synthetic-goals-v1",
                                "revision": "synthetic-v1",
                                "content_hash": None,
                                "fields": {"priority": "Source-backed priority one."},
                                "confidence": "source-backed",
                            }
                        ],
                    }
                ],
                "criterion_validation": [
                    {
                        "criterion_id": "campaign-source-proof",
                        "status": "passed",
                        "evidence_record_ids": [record_id],
                        "note": "The campaign record cites delegated evidence.",
                    }
                ],
                "proposed_writes": [],
                "recommended_next_handoff": "apex_chief_of_staff",
            }
        )
        return delegation, handoff

    def test_valid_delegation_and_handoff_are_bound_to_lease_and_origin(self):
        self.assertValid("delegation_packet.schema.json", self.delegation, [self.lease])
        self.assertValid(
            "handoff_packet.schema.json",
            self.handoff,
            [self.lease],
            delegations=[self.delegation],
        )

    def test_v21_typed_readonly_contract_is_mode_and_criterion_bound(self):
        delegation, handoff = self.v21_readonly_pair()
        self.assertValid("delegation_packet.schema.json", delegation)
        self.assertValid(
            "handoff_packet.schema.json",
            handoff,
            delegations=[delegation],
        )

        wrong_mode = deepcopy(delegation)
        wrong_mode["mode"] = "unregistered_mode"
        self.assertInvalid("delegation_packet.schema.json", wrong_mode)

        missing_artifact = deepcopy(handoff)
        missing_artifact["artifacts"] = []
        self.assertInvalid(
            "handoff_packet.schema.json",
            missing_artifact,
            delegations=[delegation],
        )

        wrong_criterion = deepcopy(handoff)
        wrong_criterion["criterion_validation"][0]["criterion_id"] = "other-criterion"
        self.assertInvalid(
            "handoff_packet.schema.json",
            wrong_criterion,
            delegations=[delegation],
        )

        undelegated_source = deepcopy(handoff)
        undelegated_source["artifacts"][0]["records"][0]["source_refs"] = [
            "undelegated-source"
        ]
        self.assertInvalid(
            "handoff_packet.schema.json",
            undelegated_source,
            delegations=[delegation],
        )

    def test_v21_deterministic_write_and_shadow_writer_eligibility(self):
        delegation, handoff = self.v21_readonly_pair()
        delegation.update(
            {
                "allowed_write_targets": ["APEX/Strategy-Campaigns"],
                "writer_agent": "apex_chief_of_staff",
                "writer_lease_id": "lease-1",
                "mutation_contract": {
                    "allowed_operations": ["upsert"],
                    "require_idempotency_key": True,
                    "require_expected_version": True,
                },
            }
        )
        handoff["proposed_writes"] = [
            {
                "target": "APEX/Strategy-Campaigns",
                "expected_state": "One campaign row.",
                "validation_readback": "Read by mission ID.",
                "rollback": "Delete by mission ID.",
                "writer_agent": "apex_chief_of_staff",
                "writer_lease_id": "lease-1",
                "operation": "upsert",
                "record_type": "campaign_record",
                "artifact_record_ids": ["campaign-map-record-1"],
                "idempotency_key": "mission-1:resource-1:campaign-record-1",
                "expected_version": "synthetic-v0",
            }
        ]
        self.assertValid(
            "delegation_packet.schema.json",
            delegation,
            [self.lease],
        )
        self.assertValid(
            "handoff_packet.schema.json",
            handoff,
            [self.lease],
            delegations=[delegation],
        )

        missing_version = deepcopy(handoff)
        missing_version["proposed_writes"][0]["expected_version"] = None
        self.assertInvalid(
            "handoff_packet.schema.json",
            missing_version,
            [self.lease],
            delegations=[delegation],
        )

        wrong_operation = deepcopy(handoff)
        wrong_operation["proposed_writes"][0]["operation"] = "replace"
        self.assertInvalid(
            "handoff_packet.schema.json",
            wrong_operation,
            [self.lease],
            delegations=[delegation],
        )

        self.assertEqual(
            self.guard._eligible_writers("APEX", "APEX/Strategy-Campaigns"),
            {"apex_chief_of_staff"},
        )

    def test_write_bearing_packets_fail_closed_without_ledgers(self):
        self.assertInvalid("delegation_packet.schema.json", self.delegation)
        self.assertInvalid("handoff_packet.schema.json", self.handoff, [self.lease])

    def test_relational_agent_brain_namespace_roundtable_and_target_are_enforced(self):
        mutations = {
            "wrong brain": ("owner_brain", "JEOS"),
            "wrong namespace": ("memory_namespace", "APEX::Other::agent"),
            "wrong roundtable": ("roundtable_namespace", "JEOS::Roundtable"),
            "unregistered target": ("allowed_write_targets", ["APEX/Not-Allowed"]),
            "cross-brain read": ("allowed_read_namespaces", ["JEOS::Life-Architecture"]),
            "other-agent memory": (
                "allowed_read_namespaces",
                ["APEX::Opportunity-Pipeline::apex_deal_engine"],
            ),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                bad = deepcopy(self.delegation)
                bad[field] = value
                self.assertInvalid("delegation_packet.schema.json", bad, [self.lease])

    def test_evidence_owner_and_sensitivity_cannot_cross_or_downgrade(self):
        wrong_brain = deepcopy(self.delegation)
        wrong_brain["allowed_evidence"] = [
            evidence("JEOS/private-journal", "JEOS", "internal", "runtime_record")
        ]
        self.assertInvalid("delegation_packet.schema.json", wrong_brain, [self.lease])
        downgraded = deepcopy(self.delegation)
        downgraded["allowed_evidence"] = [
            evidence("restricted-source", "APEX", "restricted", "runtime_record")
        ]
        self.assertInvalid("delegation_packet.schema.json", downgraded, [self.lease])
        sensitive_ref = "JEOS/SSN-redacted"
        mislabeled = deepcopy(self.delegation)
        mislabeled["allowed_evidence"] = [
            evidence(sensitive_ref, "APEX", "internal", "runtime_record")
        ]
        errors = self.guard.validate(
            "delegation_packet.schema.json", mislabeled, [self.lease]
        )
        self.assertTrue(errors)
        self.assertNotIn(sensitive_ref, " ".join(errors))

    def test_max_items_and_allowed_actions_are_structurally_enforced(self):
        too_many = deepcopy(self.delegation)
        too_many["allowed_write_targets"] = [
            "APEX/Strategy-Campaigns",
            "APEX/Decision-Log",
        ]
        self.assertInvalid("delegation_packet.schema.json", too_many, [self.lease])
        bad_action = deepcopy(self.delegation)
        bad_action["allowed_actions"] = ["analyze", "delete"]
        self.assertInvalid("delegation_packet.schema.json", bad_action, [self.lease])
        no_actions = deepcopy(self.delegation)
        no_actions["allowed_actions"] = []
        self.assertInvalid("delegation_packet.schema.json", no_actions, [self.lease])
        two_writes = deepcopy(self.handoff)
        two_writes["proposed_writes"].append(deepcopy(two_writes["proposed_writes"][0]))
        self.assertInvalid(
            "handoff_packet.schema.json",
            two_writes,
            [self.lease],
            delegations=[self.delegation],
        )

    def test_read_only_delegation_has_no_writer_or_lease(self):
        packet = deepcopy(self.delegation)
        packet["allowed_write_targets"] = []
        packet["writer_agent"] = None
        packet["writer_lease_id"] = None
        self.assertValid("delegation_packet.schema.json", packet)
        packet["writer_agent"] = "apex_chief_of_staff"
        self.assertInvalid("delegation_packet.schema.json", packet)

    def test_handoff_cannot_expand_delegated_write_scope(self):
        expanded = deepcopy(self.handoff)
        expanded["proposed_writes"][0]["target"] = "APEX/Decision-Log"
        lease = deepcopy(self.lease)
        lease["lease_id"] = "lease-decision"
        lease["write_target"] = "APEX/Decision-Log"
        expanded["proposed_writes"][0]["writer_lease_id"] = "lease-decision"
        self.assertInvalid(
            "handoff_packet.schema.json",
            expanded,
            [self.lease, lease],
            delegations=[self.delegation],
        )

    def test_handoff_cannot_expand_delegated_actions(self):
        analyze_only = deepcopy(self.delegation)
        analyze_only["allowed_actions"] = ["analyze", "read_packet_evidence"]
        for field, value in [
            ("challenges", ["Challenge the current assumption."]),
            ("proposed_writes", deepcopy(self.handoff["proposed_writes"])),
            ("recommended_next_handoff", "apex_intelligence_forge"),
        ]:
            with self.subTest(field=field):
                handoff = deepcopy(self.handoff)
                handoff["challenges"] = []
                handoff["proposed_writes"] = []
                handoff["recommended_next_handoff"] = "apex_chief_of_staff"
                handoff[field] = value
                self.assertInvalid(
                    "handoff_packet.schema.json",
                    handoff,
                    [self.lease],
                    delegations=[analyze_only],
                )

    def test_handoff_terms_and_sensitivity_must_match_lease(self):
        for field, value in [
            ("expected_state", "Different state."),
            ("validation_readback", "Unrelated read."),
            ("rollback", "No rollback."),
        ]:
            with self.subTest(field=field):
                bad = deepcopy(self.handoff)
                bad["proposed_writes"][0][field] = value
                self.assertInvalid(
                    "handoff_packet.schema.json",
                    bad,
                    [self.lease],
                    delegations=[self.delegation],
                )

    def test_handoff_cannot_downgrade_delegation_or_evidence_metadata(self):
        restricted = deepcopy(self.delegation)
        restricted["sensitivity"] = "restricted"
        restricted["allowed_evidence"] = [
            evidence("restricted-source", "APEX", "restricted", "runtime_record")
        ]
        restricted_lease = deepcopy(self.lease)
        restricted_lease["sensitivity"] = "restricted"
        downgraded = deepcopy(self.handoff)
        downgraded.update(
            {
                "status": "partial",
                "sensitivity": "public",
                "evidence": [],
                "proposed_writes": [],
                "recommended_next_handoff": "apex_chief_of_staff",
            }
        )
        self.assertInvalid(
            "handoff_packet.schema.json",
            downgraded,
            [restricted_lease],
            delegations=[restricted],
        )
        relabeled = deepcopy(self.handoff)
        relabeled["evidence"] = [
            evidence("synthetic-goals-v1", "APEX", "internal", "runtime_record")
        ]
        self.assertInvalid(
            "handoff_packet.schema.json",
            relabeled,
            [self.lease],
            delegations=[self.delegation],
        )
        forged_derived = deepcopy(self.handoff)
        forged_derived["evidence"] = [
            evidence("JEOS/private-journal", "APEX", "internal", "derived")
        ]
        self.assertInvalid(
            "handoff_packet.schema.json",
            forged_derived,
            [self.lease],
            delegations=[self.delegation],
        )

    def test_direct_read_only_uses_sentinels_and_returns_to_agent_007(self):
        direct = deepcopy(self.handoff)
        direct.update(
            {
                "delegation_id": None,
                "invocation_mode": "direct_read_only",
                "mission_id": "direct:apex_war_architect",
                "resource_id": "current-message",
                "status": "partial",
                "evidence": [],
                "proposed_writes": [],
                "sensitivity": "restricted",
                "recommended_next_handoff": "apex_chief_of_staff",
            }
        )
        self.assertValid("handoff_packet.schema.json", direct)
        downgraded = deepcopy(direct)
        downgraded["sensitivity"] = "public"
        self.assertInvalid("handoff_packet.schema.json", downgraded)
        direct["proposed_writes"] = deepcopy(self.handoff["proposed_writes"])
        self.assertInvalid("handoff_packet.schema.json", direct, [self.lease])

    def test_boundary_blocked_emits_no_source_content(self):
        blocked = deepcopy(self.handoff)
        blocked.update(
            {
                "status": "boundary_blocked",
                "findings": [],
                "evidence": [],
                "tests": [],
                "assumptions": [],
                "challenges": [],
                "proposed_writes": [],
                "validation": [],
                "blockers": ["BOUNDARY_SCOPE_REJECTED"],
                "confidence": "unknown",
                "recommended_next_handoff": "apex_chief_of_staff",
            }
        )
        self.assertValid(
            "handoff_packet.schema.json",
            blocked,
            [self.lease],
            delegations=[self.delegation],
        )
        blocked["findings"] = ["Opposite-brain raw fact."]
        self.assertInvalid(
            "handoff_packet.schema.json",
            blocked,
            [self.lease],
            delegations=[self.delegation],
        )
        blocked = deepcopy(blocked)
        blocked["findings"] = []
        blocked["tests"] = ["Opposite-brain raw fact."]
        self.assertInvalid(
            "handoff_packet.schema.json",
            blocked,
            [self.lease],
            delegations=[self.delegation],
        )
        blocked["tests"] = []
        blocked["blockers"] = ["Raw opposite-brain text."]
        self.assertInvalid(
            "handoff_packet.schema.json",
            blocked,
            [self.lease],
            delegations=[self.delegation],
        )

    def test_completion_status_requires_truthful_proof(self):
        for field, value in [
            ("blockers", ["Critical source missing."]),
            ("findings", []),
            ("tests", []),
            ("validation", []),
            ("evidence", []),
            ("confidence", "unknown"),
        ]:
            with self.subTest(field=field):
                bad = deepcopy(self.handoff)
                bad[field] = value
                self.assertInvalid(
                    "handoff_packet.schema.json",
                    bad,
                    [self.lease],
                    delegations=[self.delegation],
                )
        blocked = deepcopy(self.handoff)
        blocked.update(
            {
                "status": "blocked",
                "blockers": [],
                "proposed_writes": [],
                "recommended_next_handoff": "apex_chief_of_staff",
            }
        )
        self.assertInvalid(
            "handoff_packet.schema.json",
            blocked,
            [self.lease],
            delegations=[self.delegation],
        )

    def test_lease_ledger_rejects_malformed_duplicates_and_resource_collisions(self):
        self.assertTrue(self.guard.validate_lease_ledger([None, {"status": "active"}]))
        duplicate_id = deepcopy(self.lease)
        duplicate_id["resource_id"] = "other"
        self.assertTrue(self.guard.validate_lease_ledger([self.lease, duplicate_id]))
        cross_mission = deepcopy(self.lease)
        cross_mission["lease_id"] = "lease-2"
        cross_mission["mission_id"] = "mission-2"
        errors = self.guard.validate_lease_ledger([self.lease, cross_mission])
        self.assertTrue(any("canonical resource" in item for item in errors))
        aliased = deepcopy(self.lease)
        aliased["lease_id"] = "lease-3"
        aliased["resource_id"] = "resource-1 "
        self.assertTrue(self.guard.validate_lease_ledger([self.lease, aliased]))
        homoglyph = deepcopy(self.lease)
        homoglyph["lease_id"] = "lease-4"
        homoglyph["resource_id"] = "r\u0435source-1"
        self.assertTrue(self.guard.validate_lease_ledger([self.lease, homoglyph]))

    def test_expired_active_writer_lease_is_rejected(self):
        expired = deepcopy(self.lease)
        expired["issued_at"] = "2020-01-01T00:00:00Z"
        expired["expires_at"] = "2020-01-02T00:00:00Z"
        self.assertInvalid("writer_lease.schema.json", expired)
        self.assertInvalid("delegation_packet.schema.json", self.delegation, [expired])
        no_expiry = deepcopy(self.lease)
        no_expiry["expires_at"] = None
        self.assertInvalid("writer_lease.schema.json", no_expiry)
        too_long = deepcopy(self.lease)
        too_long["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).isoformat().replace("+00:00", "Z")
        self.assertInvalid("writer_lease.schema.json", too_long)

    def test_roundtable_is_delegation_bound_and_same_brain(self):
        readonly = deepcopy(self.delegation)
        readonly["allowed_write_targets"] = []
        readonly["writer_agent"] = None
        readonly["writer_lease_id"] = None
        memo = {
            "schema_version": "2.0",
            "memo_id": "memo-1",
            "delegation_id": "delegation-1",
            "mission_id": "mission-1",
            "timestamp": self.lease["issued_at"],
            "owner_brain": "APEX",
            "roundtable_namespace": "APEX::Roundtable",
            "resource_id": "resource-1",
            "from_agent": "apex_war_architect",
            "to_agents": ["apex_intelligence_forge"],
            "subject": "Challenge the evidence.",
            "message_type": "challenge",
            "body": "Check current-source support.",
            "evidence": [evidence()],
            "confidence": "judgment",
            "owner": "apex_chief_of_staff",
            "due": None,
            "writer_agent": None,
            "writer_lease_id": None,
            "write_target": None,
            "status": "open",
            "approval_level": "L0",
            "sensitivity": "internal",
            "resolution": None,
            "tags": ["strategy"],
        }
        self.assertValid(
            "roundtable_memo.schema.json", memo, delegations=[readonly]
        )
        mixed = deepcopy(memo)
        mixed["to_agents"] = ["jeos_life_architect"]
        self.assertInvalid(
            "roundtable_memo.schema.json", mixed, delegations=[readonly]
        )
        downgraded = deepcopy(memo)
        restricted = deepcopy(readonly)
        restricted["sensitivity"] = "restricted"
        restricted["allowed_evidence"] = [
            evidence("restricted-source", "APEX", "restricted")
        ]
        downgraded["sensitivity"] = "public"
        downgraded["evidence"] = []
        self.assertInvalid(
            "roundtable_memo.schema.json",
            downgraded,
            delegations=[restricted],
        )
        resolved_without_truth = deepcopy(memo)
        resolved_without_truth["status"] = "resolved"
        resolved_without_truth["resolution"] = None
        resolved_without_truth["confidence"] = "unknown"
        self.assertInvalid(
            "roundtable_memo.schema.json",
            resolved_without_truth,
            delegations=[readonly],
        )

    def test_roundtable_writer_requires_live_registered_lease(self):
        memo = {
            "schema_version": "2.0",
            "memo_id": "memo-2",
            "delegation_id": "delegation-1",
            "mission_id": "mission-1",
            "timestamp": self.lease["issued_at"],
            "owner_brain": "APEX",
            "roundtable_namespace": "APEX::Roundtable",
            "resource_id": "resource-1",
            "from_agent": "apex_war_architect",
            "to_agents": ["apex_intelligence_forge"],
            "subject": "Challenge.",
            "message_type": "challenge",
            "body": "Check evidence.",
            "evidence": [evidence()],
            "confidence": "source-backed",
            "owner": "apex_chief_of_staff",
            "due": None,
            "writer_agent": "apex_chief_of_staff",
            "writer_lease_id": "roundtable-lease",
            "write_target": "APEX/Roundtable",
            "status": "open",
            "approval_level": "L0",
            "sensitivity": "internal",
            "resolution": None,
            "tags": ["strategy"],
        }
        self.assertInvalid(
            "roundtable_memo.schema.json",
            memo,
            [self.lease],
            delegations=[self.delegation],
        )
        rt_lease = deepcopy(self.lease)
        rt_lease["lease_id"] = "roundtable-lease"
        rt_lease["write_target"] = "APEX/Roundtable"
        self.assertValid(
            "roundtable_memo.schema.json",
            memo,
            [self.lease, rt_lease],
            delegations=[self.delegation],
        )

    def test_memory_record_sources_are_brain_scoped_and_verified_is_separate(self):
        lease = {
            **self.lease,
            "lease_id": "lease-memory",
            "mission_id": "mission-memory",
            "resource_id": "resource-memory",
            "owner_brain": "JEOS",
            "write_target": "JEOS/Reflection-Ledger",
            "expected_state": "One lesson.",
            "validation_readback": "Read record-1.",
            "rollback": "Retract record-1.",
            "sensitivity": "confidential",
        }
        record = {
            "schema_version": "2.0",
            "record_id": "record-1",
            "mission_id": "mission-memory",
            "resource_id": "resource-memory",
            "owner_brain": "JEOS",
            "memory_namespace": "JEOS::Reflection-Ledger::jeos_reflection_forge",
            "record_type": "lesson",
            "content_summary": "Synthetic lesson.",
            "source_refs": [evidence("synthetic-reflection-v1", "JEOS", "confidential")],
            "write_target": "JEOS/Reflection-Ledger",
            "writer_agent": "apex_chief_of_staff",
            "writer_lease_id": "lease-memory",
            "mutation_result_id": None,
            "created_at": self.lease["issued_at"],
            "sensitivity": "confidential",
            "validation_readback": "Read record-1.",
            "rollback": "Retract record-1.",
            "status": "proposed",
        }
        self.assertValid("memory_record.schema.json", record, [lease])
        contaminated = deepcopy(record)
        contaminated["source_refs"] = [
            evidence("APEX/client-secret-file", "APEX", "confidential", "runtime_record")
        ]
        self.assertInvalid("memory_record.schema.json", contaminated, [lease])
        verified = deepcopy(record)
        verified["status"] = "verified"
        self.assertInvalid("memory_record.schema.json", verified, [lease])

    def test_cross_and_private_constraints_are_scoped_fresh_and_resolvable(self):
        now = datetime.now(timezone.utc)
        issued = now.isoformat().replace("+00:00", "Z")
        expires = (now + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        cross = {
            "schema_version": "2.0",
            "packet_id": "cross-1",
            "created_by": "apex_chief_of_staff",
            "mission_id": "mission-jeos",
            "resource_id": "resource-jeos",
            "source_brain": "APEX",
            "destination_brain": "JEOS",
            "destination_agent": "jeos_life_architect",
            "constraint_type": "time_window",
            "constraint_summary": "One unavailable time window.",
            "allowed_uses": ["Avoid that window."],
            "permitted_actions": [
                "analyze",
                "read_packet_evidence",
                "draft",
                "propose",
                "challenge",
                "handoff",
            ],
            "raw_source_payload_included": False,
            "source_proof_hash": "a" * 64,
            "sensitivity": "confidential",
            "issued_at": issued,
            "replay_policy": "single_mission_resource",
            "expires_at": expires,
        }
        private = {
            "schema_version": "2.0",
            "packet_id": "private-1",
            "created_by": "apex_chief_of_staff",
            "mission_id": "mission-jeos",
            "resource_id": "resource-jeos",
            "owner_brain": "JEOS",
            "destination_agent": "jeos_life_architect",
            "constraint_type": "finance_limit",
            "constraint_summary": "Use a low-cost option.",
            "allowed_uses": ["Compare options within the limit."],
            "permitted_actions": [
                "analyze",
                "read_packet_evidence",
                "draft",
                "propose",
                "challenge",
                "handoff",
            ],
            "raw_source_payload_included": False,
            "source_proof_hash": "b" * 64,
            "sensitivity": "confidential",
            "issued_at": issued,
            "replay_policy": "single_mission_resource",
            "expires_at": expires,
        }
        self.assertValid("cross_brain_constraint_packet.schema.json", cross)
        self.assertValid("brain_private_constraint_packet.schema.json", private)
        private_v21 = deepcopy(private)
        private_v21.update(
            {
                "schema_version": "2.1",
                "use_mode": "life_planning",
            }
        )
        self.assertValid("brain_private_constraint_packet.schema.json", private_v21)
        wrong_profile = deepcopy(private_v21)
        wrong_profile["use_mode"] = "capacity_only"
        self.assertInvalid("brain_private_constraint_packet.schema.json", wrong_profile)
        wrong_destination = deepcopy(private_v21)
        wrong_destination["destination_agent"] = "jeos_reflection_forge"
        self.assertInvalid(
            "brain_private_constraint_packet.schema.json",
            wrong_destination,
        )

        delegation = {
            **deepcopy(self.delegation),
            "delegation_id": "delegation-jeos",
            "mission_id": "mission-jeos",
            "resource_id": "resource-jeos",
            "agent": "jeos_life_architect",
            "owner_brain": "JEOS",
            "memory_namespace": "JEOS::Life-Architecture::jeos_life_architect",
            "roundtable_namespace": "JEOS::Roundtable",
            "allowed_read_namespaces": ["JEOS::Life-Architecture::jeos_life_architect"],
            "allowed_write_targets": [],
            "writer_agent": None,
            "writer_lease_id": None,
            "sensitivity": "confidential",
            "allowed_evidence": [
                evidence("cross-1", "JEOS", "confidential", "cross_brain_constraint"),
                evidence("private-1", "JEOS", "confidential", "brain_private_constraint"),
            ],
        }
        self.assertValid(
            "delegation_packet.schema.json",
            delegation,
            constraint_packets=[cross],
            private_constraint_packets=[private],
        )
        replay = deepcopy(delegation)
        replay["mission_id"] = "other-mission"
        self.assertInvalid(
            "delegation_packet.schema.json",
            replay,
            constraint_packets=[cross],
            private_constraint_packets=[private],
        )
        downgraded = deepcopy(delegation)
        downgraded["allowed_evidence"][1]["sensitivity"] = "internal"
        self.assertInvalid(
            "delegation_packet.schema.json",
            downgraded,
            constraint_packets=[cross],
            private_constraint_packets=[private],
        )
        overreach = deepcopy(delegation)
        narrow_private = deepcopy(private)
        narrow_private["permitted_actions"] = ["analyze"]
        self.assertInvalid(
            "delegation_packet.schema.json",
            overreach,
            constraint_packets=[cross],
            private_constraint_packets=[narrow_private],
        )
        wrong_brain = deepcopy(private)
        wrong_brain["owner_brain"] = "APEX"
        wrong_brain["destination_agent"] = "apex_war_architect"
        self.assertInvalid("brain_private_constraint_packet.schema.json", wrong_brain)
        future_cross = deepcopy(cross)
        future_cross["issued_at"] = (
            now + timedelta(days=30)
        ).isoformat().replace("+00:00", "Z")
        future_cross["expires_at"] = (
            now + timedelta(days=31)
        ).isoformat().replace("+00:00", "Z")
        self.assertInvalid("cross_brain_constraint_packet.schema.json", future_cross)
        future_private = deepcopy(private)
        future_private["issued_at"] = future_cross["issued_at"]
        future_private["expires_at"] = future_cross["expires_at"]
        self.assertInvalid("brain_private_constraint_packet.schema.json", future_private)
        too_long = deepcopy(cross)
        too_long["constraint_summary"] = "x" * 241
        self.assertInvalid("cross_brain_constraint_packet.schema.json", too_long)

    def test_verified_mutation_binds_proof_and_lease_terms(self):
        result = {
            "schema_version": "2.0",
            "result_id": "result-1",
            "mission_id": "mission-1",
            "resource_id": "resource-1",
            "owner_brain": "APEX",
            "writer_agent": "apex_chief_of_staff",
            "writer_lease_id": "lease-1",
            "write_target": "APEX/Strategy-Campaigns",
            "status": "verified",
            "expected_state": "One campaign row.",
            "expected_state_verified": True,
            "observed_state": "One campaign row.",
            "readback_evidence": ["readback://synthetic/mission-1"],
            "verified_at": self.lease["issued_at"],
            "rollback_method": "Delete by mission ID.",
            "rollback_test_status": "verified",
            "rollback_evidence": ["rollback-test://synthetic/lease-1"],
            "error": None,
            "sensitivity": "internal",
        }
        self.assertValid("mutation_result.schema.json", result, [self.lease])
        for field, value in [
            ("expected_state", "Different state."),
            ("expected_state_verified", False),
            ("observed_state", None),
            ("readback_evidence", []),
            ("verified_at", None),
            ("rollback_method", "No rollback."),
            ("rollback_test_status", "not_tested"),
            ("rollback_evidence", []),
            ("sensitivity", "public"),
        ]:
            with self.subTest(field=field):
                bad = deepcopy(result)
                bad[field] = value
                self.assertInvalid("mutation_result.schema.json", bad, [self.lease])
        before_lease = deepcopy(result)
        before_lease["verified_at"] = "1900-01-01T00:00:00Z"
        self.assertInvalid("mutation_result.schema.json", before_lease, [self.lease])
        future = deepcopy(result)
        future["verified_at"] = "2099-01-01T00:00:00Z"
        self.assertInvalid("mutation_result.schema.json", future, [self.lease])

    def test_cli_fails_closed_and_validates_a_real_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet_path = Path(tmp) / "packet.json"
            lease_path = Path(tmp) / "leases.json"
            packet_path.write_text(json.dumps(self.delegation), encoding="utf-8")
            lease_path.write_text(json.dumps([self.lease]), encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "packet_guard.py"),
                "delegation_packet.schema.json",
                str(packet_path),
                "--leases",
                str(lease_path),
            ]
            valid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            packet_path.write_text("{}", encoding="utf-8")
            invalid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
