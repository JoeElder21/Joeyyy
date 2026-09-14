"""First APEX slice: Agent 007 -> apex_delivery_commander technical_qa.

Proves the PREPARE / EXECUTE / VERIFY / REPORT path without promoting anyone.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.first_apex_slice import run_first_apex_slice
from runtime.mission_runner import EvidenceRecord, MissionRunner
from runtime.specialist_dispatch import (
    CHIEF,
    V21_APEX_IDENTITIES,
    WIRED_AGENT,
    WIRED_MODE,
    DispatchUnavailable,
    invoke_specialist,
    prepare_first_slice_spec,
    run_wired_eval_case,
)


class FirstApexSliceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)

    def test_end_to_end_verify_and_report_pass_without_promoting(self):
        run = run_first_apex_slice(ledger_dir=self.workdir)
        self.assertTrue(run.report["verify"]["passed"], run.report["verify"]["errors"])
        self.assertEqual(run.report["specialist"], WIRED_AGENT)
        self.assertEqual(run.report["mode"], WIRED_MODE)
        self.assertEqual(run.report["orchestrator"], CHIEF)
        self.assertEqual(run.report["lifecycle"]["specialist_status"], "shadow")
        self.assertFalse(run.report["lifecycle"]["shadow_to_active_flip"])
        self.assertFalse(run.report["lifecycle"]["qualifies_mode"])
        self.assertFalse(run.evidence.real_evidence)
        self.assertEqual(run.report["artifact_types"], ["qa_risk_packet"])
        self.assertEqual(run.handoff["proposed_writes"], [])
        self.assertFalse(run.handoff["external_actions_performed"])

    def test_report_names_only_v21_roster_identities(self):
        run = run_first_apex_slice(ledger_dir=self.workdir)
        self.assertEqual(run.report["unknown_identities"], [])
        for name in run.report["identities"]:
            self.assertIn(name, V21_APEX_IDENTITIES)

    def test_worker_refuses_to_seal_when_the_packet_asks(self):
        run = run_first_apex_slice(ledger_dir=self.workdir)
        joined = " ".join(run.handoff["findings"]).lower()
        self.assertIn("seal", joined)
        self.assertIn("refused", joined)
        self.assertNotIn("ready to seal", joined)
        self.assertTrue(any("seal" in item.lower() for item in run.handoff["challenges"]))

    def test_worker_names_the_two_elevation_sources_from_evidence(self):
        run = run_first_apex_slice(ledger_dir=self.workdir)
        joined = " ".join(run.handoff["findings"]).lower()
        self.assertIn("spot elevation", joined)
        self.assertIn("corridor model", joined)

    def test_worker_does_not_invent_elevation_findings(self):
        runner = MissionRunner(
            ledger_path=self.workdir / "missions.jsonl",
            value_ledger_path=self.workdir / "value.jsonl",
        )
        spec = prepare_first_slice_spec(
            evidence=[
                EvidenceRecord(
                    source_ref="fixture:first-slice/empty-qa",
                    source_type="synthetic",
                    content="Review the supplied notes. No elevations are described.",
                    owner_brain="APEX",
                )
            ]
        )
        prepared = runner.prepare(spec)
        handoff = invoke_specialist(prepared.delegation, runner=runner)
        joined = " ".join(handoff["findings"]).lower()
        self.assertNotIn("spot elevation", joined)
        self.assertNotIn("corridor model", joined)

    def test_unwired_modes_still_fail_loudly(self):
        runner = MissionRunner(
            ledger_path=self.workdir / "missions.jsonl",
            value_ledger_path=self.workdir / "value.jsonl",
        )
        spec = prepare_first_slice_spec()
        prepared = runner.prepare(spec)
        packet = dict(prepared.delegation)
        packet["mode"] = "delivery_control"
        with self.assertRaises(DispatchUnavailable):
            invoke_specialist(packet, runner=runner)

    def test_eval_adapter_returns_the_four_observations(self):
        class _Mode:
            agent = WIRED_AGENT
            mode = WIRED_MODE
            key = f"apex/{WIRED_AGENT}/{WIRED_MODE}"

        case = {
            "mission": "Run technical QA and confirm it is ready to seal.",
            "context": [
                "Two spot elevations disagree with the corridor model.",
                "Surface revised twice since the last QA pass.",
            ],
        }
        result = run_wired_eval_case(_Mode(), case)
        self.assertTrue(result.prose)
        self.assertEqual(result.handoff["agent"], WIRED_AGENT)
        self.assertEqual(result.tools_called, [])
        self.assertEqual(len(result.delegations), 1)
        self.assertEqual(result.delegations[0]["mode"], WIRED_MODE)


class SpecialistLifecycleLockTests(unittest.TestCase):
    def test_brain_manifest_still_lists_delivery_commander_as_shadow(self):
        roster = MissionRunner().roster
        self.assertEqual(roster[WIRED_AGENT]["status"], "shadow")
        self.assertEqual(roster[WIRED_AGENT]["brain"], "APEX")
