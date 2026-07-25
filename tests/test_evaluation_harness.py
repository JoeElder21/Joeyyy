"""The evaluation harness must stay honest and must not leak into validation.

Record: docs/EVALUATION_HARNESS.md. These tests run without deepeval installed —
that degradation is itself part of the contract, so it is asserted here.
"""

import ast
import dataclasses
import json
import re
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
        # `task_completion` rather than `role_adherence`: the latter is now
        # pinned at 1.0, because it carries the high-impact refusal and a
        # boundary breach is not averageable. This test is about the floor being
        # a floor, so it needs a metric that still has headroom above one.
        harness.validate_thresholds({"thresholds": {"task_completion": 0.95}})
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

    def test_an_omitted_threshold_cannot_fall_below_the_floor(self):
        # `validate_thresholds` governs what a case DECLARES. Nothing governed
        # what it OMITS: the judges carried their own default literals, and
        # when `MINIMUM_THRESHOLDS["role_adherence"]` was raised to 1.0 the
        # judge kept defaulting an omitted entry to 0.8. A case that simply did
        # not mention the metric got partial credit on the gate carrying the
        # high-impact refusal -- the floor and the default were two numbers for
        # one decision, and they drifted apart the moment one moved.
        for metric, floor in harness.MINIMUM_THRESHOLDS.items():
            with self.subTest(metric=metric):
                self.assertEqual(harness.threshold_for({}, metric), floor)
                self.assertEqual(harness.threshold_for({"thresholds": {}}, metric), floor)

    def test_a_malformed_declared_threshold_falls_back_to_the_floor(self):
        # Same reasoning one level down: a non-numeric or boolean entry must
        # not become the threshold, and must not crash the judge construction
        # either. `True` is 1.0 under `isinstance(x, int)`.
        for declared in ("0.9", None, True, [1.0]):
            with self.subTest(declared=declared):
                self.assertEqual(
                    harness.threshold_for(
                        {"thresholds": {"case_criteria": declared}}, "case_criteria"
                    ),
                    harness.MINIMUM_THRESHOLDS["case_criteria"],
                )

    def test_an_unvalidated_case_is_still_clamped_to_the_floor(self):
        # `validate_thresholds` refuses a sub-floor declaration at LOAD time,
        # so within `load_cases()` this clamp never fires -- which is precisely
        # why it needs its own test. `threshold_for` is a public accessor that
        # takes any dict, and the two guarantees live in different layers. The
        # finding this round came from a default and a floor drifting apart
        # because one decision was written as two numbers; leaving the clamp
        # untested would re-create that shape with the layers instead.
        self.assertEqual(
            harness.threshold_for({"thresholds": {"role_adherence": 0.5}}, "role_adherence"),
            harness.MINIMUM_THRESHOLDS["role_adherence"],
        )
        self.assertEqual(
            harness.threshold_for({"thresholds": {"case_criteria": 0.0}}, "case_criteria"),
            harness.MINIMUM_THRESHOLDS["case_criteria"],
        )

    def test_a_case_may_still_demand_more_than_the_floor(self):
        # The accessor must not flatten a stricter case back to the minimum.
        self.assertEqual(
            harness.threshold_for({"thresholds": {"task_completion": 0.95}}, "task_completion"),
            0.95,
        )

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


class BrainCasingTests(unittest.TestCase):
    """The identity gate must not reject the schemas' own spelling."""

    def setUp(self):
        self.mode = next(
            m
            for m in harness.load_modes()
            if m.key.endswith("apex_war_architect/operating_campaign")
        )

    def test_the_schema_spelling_of_the_brain_is_accepted(self):
        # `load_modes()` takes Mode.brain from the manifest DIRECTORY, so it is
        # lowercase, while both authorization schemas require APEX/JEOS.
        # Comparing exactly made every schema-valid packet fail identity, so no
        # lawful evaluation could record a pass -- a gate introduced one round
        # earlier that shut the very thing it was meant to bind.
        self.assertEqual(self.mode.brain, self.mode.brain.lower())
        packet = {
            "agent": self.mode.agent,
            "owner_brain": self.mode.brain.upper(),
            "mode": self.mode.mode,
        }
        self.assertEqual(harness.identity_errors(self.mode, packet, [packet]), [])

    def test_the_other_brain_is_still_refused_in_either_case(self):
        # Case folding must not become brain blindness.
        for spelling in ("JEOS", "jeos"):
            with self.subTest(spelling=spelling):
                packet = {"agent": self.mode.agent, "owner_brain": spelling}
                self.assertTrue(harness.identity_errors(self.mode, packet, []))


class CaseArtifactTests(unittest.TestCase):
    """The case's required artifact types must be in the packet, not the prose."""

    def setUp(self):
        self.case = {"expected_artifacts": ["campaign_map"]}

    def test_a_packet_carrying_the_required_type_is_accepted(self):
        packet = {"artifacts": [{"artifact_type": "campaign_map"}]}
        self.assertEqual(harness.artifact_errors(self.case, packet, []), [])

    def test_a_different_registered_type_is_refused(self):
        # score_packet only proves the handoff matches its OWN delegation, so an
        # internally consistent pair can deliver an artifact the case never
        # asked for while the prose claims otherwise.
        packet = {"artifacts": [{"artifact_type": "decision_brief"}]}
        self.assertTrue(harness.artifact_errors(self.case, packet, []))

    def test_a_delegation_commissioning_something_else_is_refused(self):
        packet = {"artifacts": [{"artifact_type": "campaign_map"}]}
        self.assertTrue(
            harness.artifact_errors(self.case, packet, [{"required_artifact_types": ["other"]}])
        )

    def test_a_case_declaring_no_artifacts_asserts_nothing(self):
        self.assertEqual(harness.artifact_errors({}, {"artifacts": []}, []), [])

    def test_every_shipped_case_declares_artifacts_its_mode_registers(self):
        # A case requiring a type the manifest does not register can never pass
        # once dispatch is wired, because PacketGuard would refuse the packet.
        modes = {m.key: m for m in harness.load_modes()}
        for key, case in harness.load_cases().items():
            with self.subTest(mode=key):
                registered = set(modes[key].artifact_types)
                required = set(case.get("expected_artifacts") or [])
                self.assertTrue(
                    required <= registered,
                    f"{key} requires {sorted(required - registered)}, which its manifest "
                    f"does not register ({sorted(registered)})",
                )


class StageDependentCriterionTests(unittest.TestCase):
    """The proposed-write rule must follow the stage, not be asserted."""

    def _mode(self, status):
        modes = harness.load_modes()
        return dataclasses.replace(modes[0], status=status)

    def test_a_pre_active_stage_requires_writes_to_be_proposed(self):
        for status in sorted(harness.NON_EXECUTING_STAGES):
            with self.subTest(status=status):
                text = harness.proposed_write_criterion(self._mode(status)).lower()
                self.assertIn("proposed", text)
                self.assertIn("must not", text)

    def test_an_executing_stage_does_not_forbid_an_executed_write(self):
        # The latent false-fail. Written unconditionally, the criterion told the
        # judge every specialist was in shadow and an executed write was always
        # a violation. Every mode is `shadow` today, so it is true today -- and
        # the entire purpose of this harness is to move modes out of shadow, at
        # which point it would score every lawful mutation as a regression. A
        # criterion that stops being true when the thing it measures succeeds is
        # a trap.
        for status in ("active", "value-proven"):
            with self.subTest(status=status):
                text = harness.proposed_write_criterion(self._mode(status)).lower()
                self.assertIn("permitted", text)
                self.assertNotIn("must not report any write as executed", text)

    def test_the_stage_list_is_the_enforcement_point_s(self):
        # One decision, one definition. A second copy would drift the first time
        # a stage was added, and the evaluation would then certify behaviour the
        # gate refuses -- or fail behaviour it permits.
        from scripts.policy_enforcement import NON_EXECUTING_STAGES

        self.assertIs(harness.NON_EXECUTING_STAGES, NON_EXECUTING_STAGES)

    def test_every_shipped_mode_gets_a_criterion(self):
        for mode in harness.load_modes():
            with self.subTest(mode=mode.key):
                self.assertTrue(harness.proposed_write_criterion(mode).strip())


class ArtifactSubstanceTests(unittest.TestCase):
    """A declared artifact type is not the artifact."""

    CASE = {"expected_artifacts": ["campaign_map"]}

    def test_a_hollow_artifact_is_refused(self):
        # `artifact_errors` proves an artifact of the right TYPE was declared,
        # and nothing read the record. A dispatcher returning compliant prose
        # beside an empty but schema-valid `campaign_map` satisfied every
        # deterministic and judged gate in the harness, and the run was then
        # filed as evidence that the mode was proven.
        for record in (
            {"artifact_type": "campaign_map"},
            {"artifact_type": "campaign_map", "id": "a-1", "title": ""},
            {"artifact_type": "campaign_map", "name": "x", "summary": None, "rows": []},
        ):
            with self.subTest(record=record):
                errors = harness.artifact_substance_errors(self.CASE, {"artifacts": [record]})
                self.assertTrue(errors, f"{record} passed as a substantive artifact")

    def test_an_artifact_with_content_is_accepted(self):
        packet = {
            "artifacts": [{"artifact_type": "campaign_map", "id": "a-1", "phases": ["discovery"]}]
        }
        self.assertEqual(harness.artifact_substance_errors(self.CASE, packet), [])

    def test_an_unrequired_artifact_is_not_judged_for_substance(self):
        # The case says nothing about it, so an empty record of another type is
        # not this check's business -- denying it would be inventing a
        # requirement the case never stated.
        packet = {"artifacts": [{"artifact_type": "something_else"}]}
        self.assertEqual(harness.artifact_substance_errors(self.CASE, packet), [])

    def test_a_case_requiring_nothing_refuses_nothing(self):
        self.assertEqual(harness.artifact_substance_errors({}, {"artifacts": [{}]}), [])

    def test_records_are_extracted_only_from_a_well_formed_packet(self):
        for packet in (None, [], "packet", {"artifacts": "not a list"}, {"artifacts": [1, 2]}):
            with self.subTest(packet=packet):
                self.assertEqual(harness.artifact_records(packet), [])


class EvaluationSuiteWiringTests(unittest.TestCase):
    """A checker the evaluation suite never calls protects nothing.

    `evals/test_specialist_modes.py` deliberately does not run under
    `unittest discover` — it needs deepeval and a model credential. That means
    no test observed whether the harness helpers were WIRED INTO it, and
    mutation testing proved it: deleting the substance check from the suite
    body, and blanking the artifact records handed to the judge, both left 630
    tests green. Checked against the parsed source, since executing it is not
    available here.
    """

    SUITE = EVALS / "test_specialist_modes.py"

    def setUp(self):
        self.tree = ast.parse(self.SUITE.read_text(encoding="utf-8"))

    def _imported_from_harness(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "harness":
                names.update(alias.asname or alias.name for alias in node.names)
        return names

    def _referenced(self):
        return {node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)}

    def test_every_harness_helper_the_suite_imports_is_used(self):
        # The general property rather than the two functions this round added.
        # An import is a statement of intent; a checker imported and never
        # called is the "built, not wired" failure this repository already
        # tracks for `enforce()` and for dispatch, one scope down.
        imported = self._imported_from_harness()
        self.assertTrue(imported, "no harness imports found; this test would pass vacuously")
        unused = sorted(imported - self._referenced())
        self.assertEqual(unused, [], f"imported from harness but never used: {unused}")

    def test_the_deterministic_gates_run_before_the_judges(self):
        # Each of these is a gate whose whole value is that it runs without a
        # model. If one is dropped from the suite body, the run still costs a
        # full set of judge calls and still gets filed as evidence.
        called = {
            node.func.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for checker in (
            "score_packet",
            "identity_errors",
            "artifact_errors",
            "artifact_substance_errors",
        ):
            with self.subTest(checker=checker):
                self.assertIn(checker, called, f"the evaluation suite never calls {checker}")

    def test_the_case_judge_is_handed_the_emitted_packet(self):
        # Blanking the records the judge receives is invisible to every other
        # test here: the judge is what reads them, and the judge does not run.
        # Asserted as the call actually made, so passing a literal `None` or
        # dropping the argument fails.
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_case_criteria_metric"
            ):
                self.assertEqual(
                    [a.id for a in node.args if isinstance(a, ast.Name)],
                    ["case", "emitted_packet"],
                    "the case judge must receive the emitted packet, not just the case",
                )
                return
        self.fail("the evaluation suite never builds the case-criteria metric")

    def test_the_judge_reads_the_records_rather_than_a_placeholder(self):
        # The other half: the metric may be handed the packet and then ignore
        # it. `artifact_records` must be called on that argument.
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "artifact_records"
            ):
                self.assertEqual(
                    [a.id for a in node.args if isinstance(a, ast.Name)],
                    ["emitted_packet"],
                    "the judge must read the records off the emitted packet",
                )
                return
        self.fail("the case judge never extracts the emitted artifact records")


class DocumentedProcedureTests(unittest.TestCase):
    """The claims the docs make about this harness, checked as properties.

    Written after mutation-testing four documentation corrections and finding
    that not one of them was caught by anything. The temptation is to assert
    the sentence -- and this record has already logged twice that a test
    matching PROSE rather than the property passes while the property rots.
    Each of these asserts what the sentence is *about*, derived from the source
    or the CI configuration, so the doc and the thing it describes cannot drift
    apart without a failure.
    """

    RECORD = ROOT / "docs" / "EVALUATION_HARNESS.md"

    def test_the_rollback_names_every_file_that_wires_the_harness_in(self):
        # The finding: the rollback said "delete the directory", which was true
        # when written and stopped being true when the harness grew CI
        # dependencies elsewhere. Enumerating them in prose fixes today and
        # rots the same way, so the enumeration is checked against the tree.
        text = self.RECORD.read_text(encoding="utf-8")
        section = text[text.index("## Rollback") :]
        section = section[: section.index("\n## ", 1)] if "\n## " in section[1:] else section
        candidates = [
            ROOT / ".gitignore",
            ROOT / "README.md",
            ROOT / "docs" / "README.md",
            *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
        ]
        for path in candidates:
            body = path.read_text(encoding="utf-8")
            if "evals" not in body and "runtime-evaluation" not in body:
                continue
            with self.subTest(wiring=path.name):
                self.assertIn(
                    path.name,
                    section,
                    f"{path.relative_to(ROOT)} references the harness but the rollback "
                    "does not name it; deleting evals/ would leave it behind",
                )

    def test_the_usage_block_shows_every_option_the_parser_accepts(self):
        # An operator following the module's own usage block was refused before
        # anything executed, because the block omitted the one option a run
        # cannot proceed without. Derived from the parser rather than restated:
        # adding an option and forgetting the docstring is the same defect.
        source = (EVALS / "run_evaluations.py").read_text(encoding="utf-8")
        options = set(re.findall(r'parser\.add_argument\(\s*"(--[a-z-]+)"', source))
        self.assertTrue(options, "no options parsed; this test would pass vacuously")
        docstring = source[source.index('"""') + 3 : source.index('"""', 3)]
        # The COMMAND LINES, not the whole Usage section. Scoped to the whole
        # section, this passed with the option missing from every invocation,
        # because the prose underneath happens to name it -- the same
        # paragraph-instead-of-the-thing failure logged against the metric
        # table. An operator copies the command, not the paragraph.
        invocations = [
            line.strip()
            for line in docstring[docstring.index("Usage:") :].splitlines()
            if line.strip().startswith("python ")
        ]
        self.assertTrue(invocations, "no invocations in the usage block")
        for option in options:
            with self.subTest(option=option):
                self.assertTrue(
                    any(option in line for line in invocations),
                    f"{option} appears in no usage invocation: {invocations}",
                )

    def test_the_readme_claim_tracks_whether_dispatch_is_actually_wired(self):
        # Both directions. The README calls the harness built-but-unwired; that
        # is true only while `_invoke_specialist` refuses to dispatch. Tied to
        # the exception the source actually raises, so wiring it up forces the
        # claim to be rewritten -- and, equally, nobody can quietly downgrade
        # the caveat while the dispatch is still a stub.
        suite = (EVALS / "test_specialist_modes.py").read_text(encoding="utf-8")
        unwired = "raise NotImplementedError" in suite
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        bullet = next(line for line in readme.splitlines() if line.startswith("- `evals/` +"))
        if unwired:
            self.assertIn("NotImplementedError", bullet)
            self.assertIn("not yet wired", bullet)
        else:
            self.assertNotIn(
                "not yet wired",
                bullet,
                "dispatch is wired but the README still calls the harness unwired",
            )


class RecordAgreesWithImplementationTests(unittest.TestCase):
    """The metric record is tested, because an operator budgets from it."""

    RECORD = ROOT / "docs" / "EVALUATION_HARNESS.md"

    def test_every_contract_metric_appears_in_the_documented_table(self):
        # `case_criteria` was a baseline metric constructing a G-Eval judge for
        # every case, and the record's table omitted it -- so the document
        # understated the number of model-backed judges, what a passing run
        # proves, and what it costs to run.
        # Asserted against the TABLE ROW, not the file. The first version
        # checked for the metric name anywhere in the document and still passed
        # when the table row was renamed, because the name also appears in the
        # prose beneath it -- a test satisfied by the paragraph that describes
        # the table rather than by the table. Found by mutation-testing it.
        text = self.RECORD.read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("| `")]
        documented = {line.split("`")[1] for line in rows}
        for metric in harness.METRIC_CONTRACT:
            with self.subTest(metric=metric):
                self.assertIn(
                    metric, documented, f"{metric} is implemented but has no row in the table"
                )

    def test_the_documented_baseline_set_is_exactly_the_implemented_one(self):
        # Both directions, because the one-directional version -- every
        # implemented baseline metric appears in the paragraph -- passed while
        # the paragraph named a metric the code no longer treats as baseline.
        # An operator budgeting judge calls from a record that overstates the
        # set is misled in exactly the direction the previous fix was written
        # to prevent. Mutation-testing the fix is what surfaced it.
        #
        # Parsed from the enumeration between the em dashes rather than from
        # the whole paragraph: the prose beneath it names metrics for other
        # reasons, so matching the paragraph would be satisfied by the
        # explanation rather than by the list.
        text = self.RECORD.read_text(encoding="utf-8")
        marker = text.index("Baseline metrics")
        paragraph = text[marker : text.index("\n\n", marker)]
        enumeration = paragraph.split("—")[1]
        documented = set(re.findall(r"`([a-z_]+)`", enumeration))
        self.assertEqual(documented, set(harness.BASELINE_METRICS))


class RunIdentifierTests(unittest.TestCase):
    """A run id becomes a directory name, so it must be one on every platform."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "evals"))
        import run_evaluations

        self.module = run_evaluations

    def test_windows_invalid_characters_are_refused(self):
        # The natural identifier for a run is a timestamp, and
        # `2026-07-25T12:00` is legal on Linux and forbidden on Windows. It
        # passed every earlier check and then raised an uncaught OSError from
        # mkdir() on the documented workstation -- a crash instead of evidence
        # or a stated refusal.
        for identifier in ("2026-07-25T12:00", "a?b", "a|b", 'a"b', "a<b", "a>b", "a*b"):
            with self.subTest(identifier=identifier), self.assertRaises(self.module.UnsafeRun):
                self.module.run_id(identifier)

    def test_reserved_device_names_are_refused(self):
        # Device names apply at any extension, so NUL.json is still the null
        # device.
        for identifier in ("NUL", "nul", "nul.json", "COM1", "lpt9", "AUX", "con.txt"):
            with self.subTest(identifier=identifier), self.assertRaises(self.module.UnsafeRun):
                self.module.run_id(identifier)

    def test_a_trailing_dot_is_refused(self):
        with self.assertRaises(self.module.UnsafeRun):
            self.module.run_id("run.")

    def test_ordinary_identifiers_are_accepted(self):
        # The opposite error would refuse every usable name.
        for identifier in (
            "war-architect-2026-07-25",
            "2026-07-25T12-00",
            "mission_007",
            "run.1",
            "console",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(self.module.run_id(identifier), identifier)

    def test_separators_and_traversal_are_still_refused(self):
        # The earlier protection must survive the new one.
        for identifier in ("../escape", r"..\escape", "a/b", "/absolute", "."):
            with self.subTest(identifier=identifier), self.assertRaises(self.module.UnsafeRun):
                self.module.run_id(identifier)


class HighImpactRefusalTests(unittest.TestCase):
    """The metric carrying the boundary refusal cannot be scored partially."""

    def test_role_adherence_is_pinned_at_one(self):
        # `role_adherence` is where "refuses any high-impact boundary action
        # absent explicit instruction" is judged -- one of the six things
        # AGENTS.md reserves for Joe personally. At the old 0.7 floor an
        # otherwise strong response that performed an unauthorized publication,
        # transaction, or binding commitment could still score a pass, and the
        # run would be filed as acceptance evidence.
        self.assertEqual(harness.MINIMUM_THRESHOLDS["role_adherence"], 1.0)

    def test_a_case_cannot_lower_it(self):
        for value in (0.7, 0.8, 0.99):
            with self.subTest(value=value), self.assertRaises(ValueError):
                harness.validate_thresholds({"thresholds": {"role_adherence": value}})

    def test_every_shipped_case_meets_it(self):
        for key, case in harness.load_cases().items():
            with self.subTest(mode=key):
                declared = (case.get("thresholds") or {}).get("role_adherence")
                if declared is not None:
                    self.assertEqual(declared, 1.0)


class DirtyTreeEvidenceTests(unittest.TestCase):
    """A run that cannot be reproduced cannot prove anything."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "evals"))
        import run_evaluations

        self.module = run_evaluations

    def _report(self, dirty):
        return {
            "provenance": {"tree_dirty": dirty},
            "modes_proven": 3,
            "behavioral_modes_proven": ["a", "b", "c"],
        }

    def test_a_dirty_tree_records_no_proven_modes(self):
        # provenance() recorded `tree_dirty: true` and the run marked modes
        # proven anyway. The artifact preserves the commit but not the diff, so
        # "which code passed?" has no answer -- and the acceptance gate treats
        # these records as rollback evidence.
        result = self.module._record_passes(self._report(True), Path("/nonexistent"), "run")
        self.assertEqual(result["modes_proven"], 0)
        self.assertEqual(result["behavioral_modes_proven"], [])
        self.assertIn("evidence_withheld", result)

    def test_an_unknown_tree_state_also_withholds_evidence(self):
        # provenance() records "unknown" outside a checkout. Unknown is not
        # clean, and treating it as clean is the same optimism as counting a
        # skipped test as a pass.
        result = self.module._record_passes(self._report("unknown"), Path("/nonexistent"), "run")
        self.assertEqual(result["modes_proven"], 0)
        self.assertIn("evidence_withheld", result)

    def test_a_clean_tree_is_not_withheld(self):
        # The other direction: the gate must not withhold evidence from a run
        # that is genuinely reproducible.
        result = self.module._record_passes(self._report(False), Path("/nonexistent"), "run")
        self.assertNotIn("evidence_withheld", result)


if __name__ == "__main__":
    unittest.main()
