"""The evaluation harness must stay honest and must not leak into validation.

Record: docs/EVALUATION_HARNESS.md. These tests run without deepeval installed —
that degradation is itself part of the contract, so it is asserted here.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
sys.path.insert(0, str(EVALS))

import harness  # noqa: E402 - path shim above is deliberate


class ModeInventoryTests(unittest.TestCase):
    """Modes are derived from the manifests, never restated."""

    def test_every_roster_mode_is_inventoried(self):
        modes = harness.load_modes()
        self.assertGreater(len(modes), 0)
        for brain in harness.BRAINS:
            with self.subTest(brain=brain):
                self.assertTrue(any(mode.brain == brain for mode in modes))

    def test_mode_keys_are_unique(self):
        keys = [mode.key for mode in harness.load_modes()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_inventory_carries_the_fields_the_gate_needs(self):
        for mode in harness.load_modes():
            with self.subTest(mode=mode.key):
                self.assertTrue(mode.memory_namespace)
                self.assertTrue(mode.write_targets)
                self.assertTrue(mode.connector_policy)

    def test_behavioral_proof_requires_passed_runs_not_case_files(self):
        # The honesty property. An earlier version derived the flag from case
        # files existing, so authoring 39 JSON files would have reported the
        # corps proven without one evaluation having run.
        coverage = harness.build_coverage()
        # Give every mode a case, and no mode a passing run.
        coverage.covered = {mode.key: Path("synthetic") for mode in coverage.modes}
        summary = coverage.summary()
        self.assertTrue(summary["cases_complete"], "inventory should read complete")
        self.assertFalse(
            summary["behavioral_modes_proven"],
            "case files are inventory; promotion needs recorded passing runs",
        )
        self.assertEqual(summary["modes_proven"], 0)
        self.assertTrue(summary["promotion_blockers"])

    def test_the_summary_states_which_gates_it_does_not_model(self):
        # The rename is only half the fix. `behavioral_modes_proven` is an
        # accurate name for "each mode passed once", but a reader still needs to
        # see, in the same object, that the acceptance gates additionally
        # require repeated missions, connector-isolation evidence, and mutation
        # readback -- none of which any single run produces.
        summary = harness.build_coverage().summary()
        self.assertNotIn(
            "promotion_ready",
            summary,
            "a name that overstates what was measured reads as evidence and is not",
        )
        self.assertTrue(summary["gates_not_modelled"])
        joined = " ".join(summary["gates_not_modelled"]).lower()
        for gate in ("longitudinal", "connector-isolation", "readback"):
            self.assertIn(gate, joined)

    def test_modes_carry_the_manifest_responsibility_not_only_a_class_id(self):
        # Mirrored specialists share generic class ids on purpose, so a role
        # judge given only `class_id` cannot tell an APEX campaign from a JEOS
        # personal outcome -- both architects are `strategy`.
        modes = harness.load_modes()
        for mode in modes:
            with self.subTest(mode=mode.key):
                self.assertTrue(mode.responsibility, f"{mode.agent} has no responsibility")
        by_class: dict[str, set[str]] = {}
        for mode in modes:
            by_class.setdefault(mode.class_id, set()).add(mode.responsibility)
        shared = {cls: seen for cls, seen in by_class.items() if len(seen) > 1}
        self.assertTrue(
            shared,
            "if no class id is shared across differing responsibilities, this "
            "distinction is untested and the finding should be re-examined",
        )

    def test_behavioral_proof_only_when_every_mode_has_a_passing_run(self):
        coverage = harness.build_coverage()
        coverage.covered = {mode.key: Path("synthetic") for mode in coverage.modes}
        coverage.passed = {mode.key: "run-1" for mode in coverage.modes}
        self.assertTrue(coverage.summary()["behavioral_modes_proven"])
        # One mode losing its run is enough to block the whole corps.
        coverage.passed.pop(coverage.modes[0].key)
        self.assertFalse(coverage.summary()["behavioral_modes_proven"])

    def test_an_empty_corps_proves_nothing(self):
        # `not self.unproven` is vacuously true on an empty list; readiness must
        # not fall out of having nothing to prove.
        self.assertFalse(harness.Coverage().summary()["behavioral_modes_proven"])

    def test_a_new_mode_reads_as_uncovered_not_as_missing(self):
        # The whole point of deriving from the manifests: adding a mode must move
        # the denominator, so it cannot be silently skipped.
        coverage = harness.build_coverage()
        self.assertEqual(
            len(coverage.modes),
            len(coverage.covered) + len(coverage.uncovered),
        )


class CaseIntegrityTests(unittest.TestCase):
    """A case that does not trace to a real mode and a real gate is not evidence."""

    REQUIRED = (
        "mode_key",
        "title",
        "mission",
        "expected_artifacts",
        "expected_behaviors",
        "forbidden_behaviors",
        "provenance",
    )

    def test_cases_declare_every_required_field(self):
        for key, case in harness.load_cases().items():
            for field in self.REQUIRED:
                with self.subTest(case=key, field=field):
                    self.assertIn(field, case)
                    self.assertTrue(case[field])

    def test_cases_target_real_modes(self):
        # build_coverage raises if a case names a mode the roster does not define.
        harness.build_coverage()

    def test_case_metrics_are_mapped_to_recorded_criteria(self):
        for key, case in harness.load_cases().items():
            with self.subTest(case=key):
                metrics = harness.metrics_for(case)
                for name in harness.BASELINE_METRICS:
                    self.assertIn(name, metrics)
                for name in metrics:
                    self.assertIn(name, harness.METRIC_CONTRACT)

    def test_case_artifacts_exist_in_the_brain_manifest(self):
        # Two of the three seed cases originally named artifact types that no
        # manifest declares (`qa_findings`, `reflection_note`). PacketGuard would
        # have rejected any handoff emitting them, so those cases could never
        # have become lawful completed missions — the harness would have been
        # generating unpassable evidence requirements.
        #
        # The harness derives modes from the manifests precisely so they cannot
        # drift; artifacts were the one field still hand-written, and they drifted
        # immediately. Deriving is only safe where it is enforced.
        modes = {mode.key: mode for mode in harness.load_modes()}
        for key, case in harness.load_cases().items():
            registered = set(modes[key].artifact_types)
            for artifact in case.get("expected_artifacts", []):
                with self.subTest(case=key, artifact=artifact):
                    self.assertIn(
                        artifact,
                        registered,
                        f"{key}: {artifact!r} is not a registered artifact type "
                        f"({sorted(registered)})",
                    )

    def test_every_case_forbids_cross_brain_leakage(self):
        for key, case in harness.load_cases().items():
            forbidden = " ".join(case["forbidden_behaviors"]).lower()
            with self.subTest(case=key):
                self.assertIn("brain" if "brain" in forbidden else "namespace", forbidden)

    def test_case_files_are_valid_json_with_stable_keys(self):
        for path in sorted((EVALS / "cases").glob("*.json")):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)


class PacketValidityMetricTests(unittest.TestCase):
    """The one metric that needs no model must actually work, in both directions.

    A metric that only ever returns 0 would fail every evaluation and look
    rigorous; one that only ever returns 1 would pass everything and look clean.
    Both directions are asserted against real packets built by the contract
    suite, so this metric is judged by the same fixtures the runtime is.
    """

    @classmethod
    def setUpClass(cls):
        from tests.test_packet_contracts import PacketContractTests

        PacketContractTests.setUpClass()
        cls.contracts = PacketContractTests
        instance = PacketContractTests(
            "test_valid_delegation_and_handoff_are_bound_to_lease_and_origin"
        )
        cls.delegation, cls.handoff = instance.v21_readonly_pair()

    def test_valid_packet_scores_one(self):
        from packet_validity import score_packet

        verdict = score_packet(self.handoff, delegations=[self.delegation])
        self.assertEqual(verdict.score, 1.0)
        self.assertTrue(verdict.passed)
        self.assertEqual(verdict.errors, ())

    def test_malformed_packet_scores_zero_with_reasons(self):
        from packet_validity import score_packet

        verdict = score_packet({"schema_version": "2.1"})
        self.assertEqual(verdict.score, 0.0)
        self.assertFalse(verdict.passed)
        self.assertTrue(verdict.errors)
        self.assertIn("PacketGuard", verdict.reason())

    def test_absent_packet_is_a_failure_not_an_error(self):
        # A specialist that emits nothing must score zero, not crash the run.
        from packet_validity import score_packet

        verdict = score_packet(None)
        self.assertEqual(verdict.score, 0.0)
        self.assertIn("no packet", verdict.reason())

    def test_legacy_schema_version_is_rejected(self):
        # v2.0 packets are refused by the runtime; the metric must agree with it
        # rather than keep its own opinion.
        from packet_validity import score_packet

        verdict = score_packet(self.contracts.handoff, active_leases=[self.contracts.lease])
        self.assertEqual(verdict.score, 0.0)

    def test_score_is_binary(self):
        # Validity is not a matter of degree: partial credit would let a
        # specialist average past a boundary the runtime enforces absolutely.
        from packet_validity import score_packet

        for packet in (None, {}, {"schema_version": "2.1"}, self.handoff):
            with self.subTest(packet=type(packet).__name__):
                score = score_packet(packet, delegations=[self.delegation]).score
                self.assertIn(score, (0.0, 1.0))

    def test_metric_builder_degrades_without_a_runtime(self):
        import packet_validity

        built = packet_validity.build_metric()
        if not harness.deepeval_available():
            self.assertIsNone(built)


class HonestyContractTests(unittest.TestCase):
    """The harness must refuse to produce evidence it does not have."""

    def test_harness_imports_without_an_evaluation_runtime(self):
        # If this test runs at all, harness imported. Assert the probe is honest
        # rather than hardcoded optimistic.
        self.assertIsInstance(harness.deepeval_available(), bool)

    def test_specialist_dispatch_is_not_stubbed_with_canned_output(self):
        # A stub returning fixed text would make every evaluation pass while
        # attesting to nothing. Assert the refusal is still in place.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("NotImplementedError", source)
        self.assertIn("_invoke_specialist", source)

    def test_dispatch_contract_supplies_observations_not_just_expectations(self):
        # packet_validity needs the emitted packet and tool_correctness needs the
        # observed trace. Supplying only expectations means neither metric can
        # ever fail, which is worse than not running them.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("tools_called=tools_called", source)
        self.assertIn('"packet": emitted_packet', source)
        # And the originating delegation, without which PacketGuard refuses
        # every lawful handoff as "not uniquely validated".
        self.assertIn('"delegations": delegations', source)

    def test_judged_metrics_are_gated_by_a_branch_not_by_list_order(self):
        # Position in a metrics list is not a gate: `assert_test` runs every
        # metric it is handed, so an earlier version that merely put
        # packet_validity first still paid for a full set of judge calls on a
        # packet the runtime would refuse. The gate has to be a branch.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        gate = source.index("verdict = score_packet(")
        judged = source.index("assert_test(")
        self.assertLess(gate, judged, "packet validity must be decided before any judge runs")
        self.assertIn("if not verdict.passed:", source)
        self.assertIn("pytest.fail(", source)

    def test_the_case_context_reaches_the_judges(self):
        # The JEOS weekly-reflection seed permits a professional-deadline
        # reference only via its context. A judge that cannot see the context is
        # told to reject that reference as detail beyond the mission -- a false
        # failure built into the metric.
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("LLMTestCaseParams.CONTEXT", source)

    def test_the_role_judge_reads_the_registered_responsibility(self):
        source = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        self.assertIn("mode.responsibility", source)

    def test_the_run_artifact_retains_scores_for_passing_tests(self):
        # pytest's default `junit_logging=no` omits captured output for PASSING
        # tests, so every judge score and reason on a successful run was
        # discarded -- while evals/README.md calls the published directory the
        # "scored result". An artifact recording "passed" without what it
        # scored cannot be the promotion evidence the gate asks for.
        source = (EVALS / "run_evaluations.py").read_text(encoding="utf-8")
        self.assertIn("junit_logging=all", source)
        self.assertIn("junit_log_passing_tests=True", source)

    def test_runner_documents_that_results_leave_the_repository(self):
        source = (EVALS / "run_evaluations.py").read_text(encoding="utf-8")
        self.assertIn("Evaluations", source)
        self.assertIn("gitignored", source)

    def test_output_directory_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("evals/output/", ignore)

    def test_evaluation_suite_is_outside_unittest_discovery(self):
        # `unittest discover -s tests` must never import deepeval.
        self.assertFalse((ROOT / "tests" / "test_specialist_modes.py").exists())
        self.assertTrue((EVALS / "test_specialist_modes.py").exists())


class ThresholdIntegrityTests(unittest.TestCase):
    """A case must not be able to disarm the gates it is measured against."""

    def test_a_zero_threshold_is_refused(self):
        # Judge scores are nonnegative, so `case_criteria: 0.0` passes that gate
        # unconditionally -- including for an output exhibiting every forbidden
        # behaviour the case names -- after which the run is recorded as
        # acceptance evidence. A case could lower its own bar and still be
        # counted as proving the mode.
        for metric in ("case_criteria", "brain_isolation", "packet_validity"):
            with self.subTest(metric=metric):
                with self.assertRaises(ValueError) as raised:
                    harness.validate_thresholds({"thresholds": {metric: 0.0}})
                self.assertIn("below the minimum", str(raised.exception))

    def test_a_negative_threshold_is_refused(self):
        with self.assertRaises(ValueError):
            harness.validate_thresholds({"thresholds": {"role_adherence": -1}})

    def test_a_threshold_no_judge_can_reach_is_refused(self):
        # The opposite failure: a case that can never pass is not a stricter
        # gate, it is a broken one, and it would read as an unproven mode
        # forever without saying why.
        with self.assertRaises(ValueError):
            harness.validate_thresholds({"thresholds": {"case_criteria": 1.5}})

    def test_a_threshold_for_an_unmapped_metric_is_refused(self):
        with self.assertRaises(ValueError):
            harness.validate_thresholds({"thresholds": {"vibes": 1.0}})

    def test_a_boolean_is_not_a_threshold(self):
        # `True` is 1.0 under `isinstance(x, int)`, so it would otherwise sail
        # through as a passing threshold.
        with self.assertRaises(ValueError):
            harness.validate_thresholds({"thresholds": {"case_criteria": True}})

    def test_a_case_may_demand_more_than_the_default(self):
        # The floor is a floor, not a fixed value.
        harness.validate_thresholds({"thresholds": {"role_adherence": 0.95}})
        harness.validate_thresholds({"thresholds": {}})
        harness.validate_thresholds({})

    def test_every_shipped_case_satisfies_the_minima(self):
        # load_cases() validates on load, so this asserts the seed cases are
        # loadable at all -- and would fail loudly if one were edited below the
        # floor rather than silently recording a weakened run as evidence.
        cases = harness.load_cases()
        self.assertTrue(cases)
        for key, case in cases.items():
            with self.subTest(mode=key):
                harness.validate_thresholds(case, source=key)

    def test_the_minima_cover_every_metric_in_the_contract(self):
        # A metric with no floor is a metric a case can set to zero. The
        # contract and the minima have to be changed as a set.
        missing = sorted(set(harness.METRIC_CONTRACT) - set(harness.MINIMUM_THRESHOLDS))
        self.assertEqual(missing, [], f"no minimum threshold declared for {missing}")


class PacketIdentityTests(unittest.TestCase):
    """A packet must belong to the mode the run says it proves."""

    def setUp(self):
        self.mode = next(
            m
            for m in harness.load_modes()
            if m.key.endswith("apex_war_architect/operating_campaign")
        )
        self.good = {
            "agent": self.mode.agent,
            "owner_brain": self.mode.brain,
            "mode": self.mode.mode,
        }

    def test_a_matching_pair_is_accepted(self):
        self.assertEqual(harness.identity_errors(self.mode, self.good, [self.good]), [])

    def test_another_specialists_packet_is_refused(self):
        # score_packet proves the packet and its delegation agree WITH EACH
        # OTHER; nothing compared either with the mode under evaluation. A
        # lawful War Architect pair would pass while a Delivery Commander case
        # was being run, and the wrong specialist's packet would record the
        # requested mode as proven.
        wrong = dict(self.good, agent="apex_delivery_commander")
        self.assertTrue(harness.identity_errors(self.mode, wrong, []))

    def test_the_other_brains_packet_is_refused(self):
        self.assertTrue(harness.identity_errors(self.mode, dict(self.good, owner_brain="JEOS"), []))

    def test_a_foreign_delegation_is_refused_too(self):
        # The chain, not only the emitted packet.
        self.assertTrue(
            harness.identity_errors(self.mode, self.good, [dict(self.good, mode="other_mode")])
        )

    def test_an_absent_field_is_not_a_mismatch(self):
        # Packet kinds differ in which identity fields they carry. Treating
        # absence as failure would reject lawful packets; treating a DIFFERENCE
        # as acceptable is the hole being closed.
        self.assertEqual(harness.identity_errors(self.mode, {"agent": self.mode.agent}, []), [])

    def test_a_non_object_packet_is_refused(self):
        self.assertTrue(harness.identity_errors(self.mode, "not a packet", []))


if __name__ == "__main__":
    unittest.main()
