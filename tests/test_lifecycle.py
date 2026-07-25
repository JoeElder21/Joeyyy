"""Tests for the lifecycle gate engine and (when installed) the LangGraph wiring."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.lifecycle import (  # noqa: E402
    AgentLifecycleState,
    ModeEvidence,
    Stage,
    apply,
    evaluate_administrative,
    evaluate_promotion,
)


def _shadow_ready() -> AgentLifecycleState:
    return AgentLifecycleState(
        agent_id="apex_war_architect",
        brain="APEX",
        stage=Stage.CANDIDATE,
        registered=True,
        static_contract_valid=True,
        synthetic_packets_valid=True,
    )


def _active_ready() -> AgentLifecycleState:
    state = _shadow_ready()
    state.stage = Stage.SHADOW
    state.material_modes = [
        ModeEvidence(
            mode="operating_campaign",
            real_mission_completed=True,
            boundary_behavior_verified=True,
            handoff_schema_valid=True,
        ),
        ModeEvidence(
            mode="delegation_topology",
            real_mission_completed=True,
            boundary_behavior_verified=True,
            handoff_schema_valid=True,
            mutation_occurred=True,
            readback_verified=True,
        ),
    ]
    state.connector_isolation_runtime_verified = True
    state.evidence_source = "controlled_real_mission"
    state.joe_approved_activation = True
    return state


class GateEngineTests(unittest.TestCase):
    def test_candidate_promotes_to_shadow_only_with_static_and_synthetic_passes(self):
        state = _shadow_ready()
        result = evaluate_promotion(state)
        self.assertTrue(result.allowed)
        self.assertIs(apply(result, state).stage, Stage.SHADOW)

        bare = AgentLifecycleState("x", "APEX", Stage.CANDIDATE)
        blocked = evaluate_promotion(bare)
        self.assertFalse(blocked.allowed)
        self.assertEqual(len(blocked.failures), 3)

    def test_shadow_to_active_requires_evidence_per_material_mode(self):
        state = _active_ready()
        self.assertTrue(evaluate_promotion(state).allowed)

        state.material_modes[1].readback_verified = False
        result = evaluate_promotion(state)
        self.assertFalse(result.allowed)
        self.assertIn("mutation without verified readback", result.failures[0])

    def test_harness_pass_alone_cannot_promote(self):
        state = _active_ready()
        state.evidence_source = "harness"
        result = evaluate_promotion(state)
        self.assertFalse(result.allowed)
        self.assertTrue(any("harness honesty" in failure for failure in result.failures))

    def test_activation_requires_joes_approval(self):
        state = _active_ready()
        state.joe_approved_activation = False
        result = evaluate_promotion(state)
        self.assertFalse(result.allowed)
        self.assertTrue(any("Joe's explicit approval" in f for f in result.failures))

    def test_value_proven_gate_enforces_gate_11(self):
        state = _active_ready()
        state.stage = Stage.ACTIVE
        result = evaluate_promotion(state)
        self.assertFalse(result.allowed)

        state.return_schema_compliant = True
        state.false_alert_burden_low = True
        state.net_value_positive_after_review = True
        self.assertTrue(evaluate_promotion(state).allowed)

        state.critical_boundary_failures = 1
        self.assertFalse(evaluate_promotion(state).allowed)

    def test_retired_is_terminal_and_administrative_moves_need_reasons(self):
        state = _active_ready()
        state.stage = Stage.ACTIVE
        no_reason = evaluate_administrative(state, Stage.RESTRICTED)
        self.assertFalse(no_reason.allowed)

        state.administrative_reason = "recurring boundary near-miss under review"
        self.assertTrue(evaluate_administrative(state, Stage.RESTRICTED).allowed)

        state.stage = Stage.RETIRED
        self.assertFalse(evaluate_administrative(state, Stage.DEPRECATED).allowed)
        self.assertFalse(evaluate_promotion(state).allowed)

    def test_apply_is_fail_closed(self):
        state = AgentLifecycleState("x", "APEX", Stage.CANDIDATE)
        result = evaluate_promotion(state)
        with self.assertRaises(PermissionError):
            apply(result, state)


@unittest.skipUnless(
    importlib.util.find_spec("langgraph") is not None, "langgraph not installed"
)
class LifecycleGraphTests(unittest.TestCase):
    def test_graph_interrupts_for_joe_then_promotes_after_approval(self):
        from runtime.lifecycle_graph import build_lifecycle_graph

        state = _active_ready()
        state.joe_approved_activation = False
        graph = build_lifecycle_graph()
        config = {"configurable": {"thread_id": state.agent_id}}

        out = graph.invoke({"state": state, "log": []}, config)
        # Interrupted before await_joe: still shadow, awaiting the human checkpoint.
        # The checkpointer copies state, so assert on the graph's own snapshot.
        self.assertIs(out["state"].stage, Stage.SHADOW)
        self.assertEqual(graph.get_state(config).next, ("await_joe",))

        graph.update_state(config, {"joe_approved_activation": True})
        resumed = graph.invoke(None, config)
        self.assertIs(resumed["state"].stage, Stage.ACTIVE)

    def test_graph_never_promotes_on_approval_without_evidence(self):
        from runtime.lifecycle_graph import build_lifecycle_graph

        state = _active_ready()
        state.joe_approved_activation = True
        state.connector_isolation_runtime_verified = False  # approval cannot bypass
        graph = build_lifecycle_graph()
        config = {"configurable": {"thread_id": state.agent_id}}
        out = graph.invoke({"state": state, "log": []}, config)
        self.assertIs(out["state"].stage, Stage.SHADOW)
        self.assertFalse(out["result"].allowed)


if __name__ == "__main__":
    unittest.main()
