"""Drift locks for docs/RECONCILIATION_2026-07-24.md."""

from __future__ import annotations

import re
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.cadence import build_cadence_run  # noqa: E402
from runtime.lifecycle import (  # noqa: E402
    AgentLifecycleState,
    ModeEvidence,
    Stage,
    evaluate_promotion,
)
from scripts import orchestration_graphs  # noqa: E402


class ReconciliationTests(unittest.TestCase):
    def test_cadence_orders_agree_across_both_streams(self):
        """runtime.cadence and the scripts/ layer must consume identical orders."""
        for brain in ("apex", "jeos"):
            manifest = tomllib.loads(
                (ROOT / "brains" / brain / "agents.toml").read_text(encoding="utf-8")
            )
            for route in manifest["cadence_routes"]:
                run = build_cadence_run(brain, route["cadence"])
                self.assertEqual(
                    [step.agent for step in run.steps],
                    route["order"],
                    f"{brain}/{route['cadence']} diverged from the manifest order",
                )
                self.assertEqual(run.integrator, route["integrator"])

    def test_ticket_4_absorption_is_real(self):
        """The Codex debate modules exist and define their builders."""
        debate = (ROOT / "scripts" / "group_debate.py").read_text(encoding="utf-8")
        self.assertIn("def ", debate)
        self.assertIn("challenge", debate.lower())
        self.assertTrue((ROOT / "scripts" / "autogen_challenge_pair.py").exists())

    def test_every_autogen_module_targets_the_pinned_api(self):
        """A module that exists is not a module that runs.

        Ticket 4 was closed against `scripts/group_debate.py` for six days while
        it imported `autogen_agentchat` (AutoGen 0.4+) and the repository pinned
        `autogen-agentchat<0.3`, which provides `autogen`. No installation of the
        declared set could execute it, and the existence check above could not
        tell. `autogen_ext`, which its tests also needed, was in no manifest.

        This locks the whole repository onto one AutoGen line: whichever line the
        root manifest pins, every module must import. Splitting them again fails
        here rather than six days later.
        """
        pin = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        legacy_pin = "autogen-agentchat>=0.2.35,<0.3" in pin.replace(" ", "")
        self.assertTrue(
            legacy_pin,
            "requirements.txt no longer pins the 0.2 line; update this lock and "
            "migrate every autogen module together rather than one at a time",
        )

        # Compiled with re.M rather than passed to assertNotRegex, which uses
        # re.search with no flags: `^` would then match only the start of the
        # whole file, so an indented import inside a try: block — which is
        # exactly how every one of these modules imports autogen — could never
        # be detected. The first version of this lock had that bug and passed
        # against a deliberately reintroduced regression.
        any_autogen = re.compile(r"^\s*(from|import)\s+autogen", re.M)
        forbidden = re.compile(r"^\s*(from|import)\s+(autogen_agentchat|autogen_ext)\b", re.M)

        modules = sorted([*(ROOT / "runtime").glob("*.py"), *(ROOT / "scripts").glob("*.py")])
        importers = [p for p in modules if any_autogen.search(p.read_text(encoding="utf-8"))]
        self.assertTrue(importers, "no module imports autogen at all")

        for path in importers:
            with self.subTest(module=path.name):
                hit = forbidden.search(path.read_text(encoding="utf-8"))
                self.assertIsNone(
                    hit,
                    f"{path.name} imports {hit.group(2) if hit else ''}, which the "
                    "pinned 0.2 distribution does not provide",
                )

    def test_lifecycle_gate_parity(self):
        """scripts/ must not re-implement or under-implement the gate logic.

        Locks the seam rule: runtime/lifecycle.py is the sole gate authority.
        Every field the runtime gates read must be reachable from a graph gate
        flag, so a gate added in runtime/ cannot be silently ignored here.
        """
        mapped = set(orchestration_graphs.AGENT_GATE_FIELDS.values())
        mode_mapped = set(orchestration_graphs.MODE_GATE_FIELDS.values())

        # Fields the runtime shadow -> active gate actually consults.
        required_agent_fields = set(orchestration_graphs.ACTIVE_AGENT_GATE_FIELDS.values()) | {
            "connector_isolation_runtime_verified",
            "joe_approved_activation",
        }
        required_mode_fields = {
            "real_mission_completed",
            "boundary_behavior_verified",
            "handoff_schema_valid",
            "writer_lease_compliant",
            "readback_verified",
        }
        self.assertTrue(
            required_agent_fields.issubset(mapped),
            f"graph drops runtime agent gates: {sorted(required_agent_fields - mapped)}",
        )
        self.assertTrue(
            required_mode_fields.issubset(mode_mapped),
            f"graph drops runtime mode gates: {sorted(required_mode_fields - mode_mapped)}",
        )

        # Every mapped field must exist on the runtime dataclasses.
        for field in mapped:
            self.assertIn(field, AgentLifecycleState.__dataclass_fields__)
        for field in mode_mapped:
            self.assertIn(field, ModeEvidence.__dataclass_fields__)

        # Stage vocabulary and promotion table are derived, not restated.
        self.assertEqual(orchestration_graphs.LIFECYCLE_STAGES, [stage.value for stage in Stage])

    def test_graph_projection_agrees_with_runtime_verdict(self):
        """Every gate flag must be load-bearing on both promotions."""
        cases = (
            ("candidate", orchestration_graphs.SHADOW_GATES),
            ("shadow", orchestration_graphs.ACTIVE_GATES),
        )
        for stage, required in cases:
            for dropped in (None, *required):
                gates = {gate: gate != dropped for gate in required}
                projected = orchestration_graphs.to_runtime_state(
                    {"agent": "apex_war_architect", "brain": "APEX", "stage": stage, "gates": gates}
                )
                self.assertEqual(
                    evaluate_promotion(projected).allowed,
                    dropped is None,
                    f"from {stage}: dropping {dropped!r} must block promotion",
                )

    def test_graph_cannot_promote_without_joe_approval(self):
        """The regression this parity lock exists to prevent."""
        gates = dict.fromkeys(orchestration_graphs.ACTIVE_GATES, True)
        gates["joe_approved_activation"] = False
        state = orchestration_graphs.to_runtime_state(
            {"agent": "apex_war_architect", "brain": "APEX", "stage": "shadow", "gates": gates}
        )
        result = evaluate_promotion(state)
        self.assertFalse(result.allowed)
        self.assertTrue(any("Joe's explicit approval" in failure for failure in result.failures))

    def test_reconciliation_record_names_the_canonical_homes(self):
        record = (ROOT / "docs" / "RECONCILIATION_2026-07-24.md").read_text(encoding="utf-8")
        for phrase in (
            "runtime/lifecycle.py",
            "runtime/cadence.py",
            "runtime/writer_lease.py",
            "closed as absorbed",
            "no memory layer is active",
        ):
            self.assertIn(phrase, record)


if __name__ == "__main__":
    unittest.main()
