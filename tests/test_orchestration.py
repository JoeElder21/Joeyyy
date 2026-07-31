"""Tests for the orchestration wave: LangGraph lifecycle/cadence/HITL graphs,
AutoGen debates and cadence chats, the JEOS knowledge graph, and the MCP
mount registry. Heavy-dependency tests skip cleanly for stdlib CI."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from scripts.agent_runtime import CHIEF, AuditLedger, load_roster
from scripts.jeos_knowledge import GraphAccessDenied, JeosKnowledgeGraph
from scripts.orchestration_graphs import ACTIVE_GATES, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


@unittest.skipUnless(_available("langgraph"), "langgraph not installed")
class LifecycleGraphTests(unittest.TestCase):
    def test_shadow_advances_only_when_every_gate_holds(self):
        from scripts.orchestration_graphs import build_lifecycle_graph

        graph = build_lifecycle_graph()
        satisfied = graph.invoke(
            {
                "agent": "apex_war_architect",
                "stage": "shadow",
                "gates": dict.fromkeys(ACTIVE_GATES, True),
            }
        )
        self.assertEqual(satisfied["stage"], "active")

        missing = graph.invoke(
            {
                "agent": "apex_war_architect",
                "stage": "shadow",
                "gates": dict.fromkeys(ACTIVE_GATES[:-1], True),
            }
        )
        self.assertEqual(missing["stage"], "shadow")
        self.assertTrue(any("unsatisfied" in line for line in missing["decision_log"]))

        violated = graph.invoke(
            {
                "agent": "apex_war_architect",
                "stage": "active",
                "violation": "wrote outside its lease",
            }
        )
        self.assertEqual(violated["stage"], "restricted")


@unittest.skipUnless(_available("langgraph"), "langgraph not installed")
class CadenceAndMissionGraphTests(unittest.TestCase):
    def test_cadence_graph_follows_manifest_order_with_integrator_last(self):
        from scripts.orchestration_graphs import build_cadence_graph

        manifest = load_manifest("apex", ROOT)
        route = next(r for r in manifest["cadence_routes"] if r["cadence"] == "daily")
        graph = build_cadence_graph("apex", "daily", lambda agent, state: {"note": f"{agent} ran"})
        outcome = graph.invoke({"cadence": "daily"})
        ran = [step["agent"] for step in outcome["steps"]]
        self.assertEqual(ran, list(route["order"]) + [route["integrator"]])
        self.assertEqual(ran[-1], "apex_chief_of_staff")

    def test_mission_graph_interrupts_before_irreversible_and_resumes(self):
        from scripts.orchestration_graphs import build_mission_graph

        graph = build_mission_graph()
        config = {"configurable": {"thread_id": "mission-1"}}
        paused = graph.invoke(
            {"mission": "file the submittal", "irreversible_action": "submit to LFUCG"},
            config,
        )
        self.assertEqual(
            paused["actions"], ["planned", "reversible work done"]
        )  # stopped before the irreversible node
        graph.update_state(config, {"approved_by_joe": True})
        resumed = graph.invoke(None, config)
        self.assertIn("irreversible executed: submit to LFUCG", resumed["actions"])


@unittest.skipUnless(
    _available("autogen_agentchat") and _available("autogen_ext"),
    "autogen not installed",
)
class GroupDebateTests(unittest.TestCase):
    def _client(self, turns: list[str]):
        from autogen_ext.models.replay import ReplayChatCompletionClient

        return ReplayChatCompletionClient(turns)

    def test_registered_challenge_pair_actually_debates(self):
        import asyncio

        from scripts.group_debate import build_challenge_debate

        team = build_challenge_debate(
            "APEX",
            ("apex_war_architect", "apex_intelligence_forge"),
            self._client(
                [
                    "Campaign two is the highest-leverage move this quarter.",
                    "The source record does not support that: two of three cited "
                    "opportunities are stale. TERMINATE",
                ]
            ),
            max_turns=2,
        )
        result = asyncio.run(team.run(task="Debate: is campaign two the right focus?"))
        speakers = {message.source for message in result.messages}
        self.assertIn("apex_war_architect", speakers)
        self.assertIn("apex_intelligence_forge", speakers)

    def test_unregistered_and_cross_brain_pairs_are_refused(self):
        from scripts.group_debate import DebateRefused, build_challenge_debate

        with self.assertRaises(DebateRefused):
            build_challenge_debate(
                "APEX",
                ("apex_war_architect", "apex_delivery_commander")
                if not self._pair_registered("apex_war_architect", "apex_delivery_commander")
                else ("apex_deal_engine", "apex_systems_blacksmith"),
                self._client(["x"]),
            )
        with self.assertRaises(DebateRefused):
            build_challenge_debate(
                "APEX",
                ("apex_war_architect", "jeos_life_architect"),
                self._client(["x"]),
            )

    @staticmethod
    def _pair_registered(a: str, b: str) -> bool:
        manifest = load_manifest("apex", ROOT)
        return any(
            frozenset(item["agents"]) == frozenset((a, b))
            for item in manifest.get("challenge_pairs", [])
        )

    def test_cadence_chat_speaks_in_manifest_order(self):
        from scripts.group_debate import build_cadence_chat

        manifest = load_manifest("apex", ROOT)
        route = next(r for r in manifest["cadence_routes"] if r["cadence"] == "daily")
        team = build_cadence_chat("APEX", "daily", self._client(["a", "b", "c", "d"]))
        names = [participant.name for participant in team._participants]
        self.assertEqual(names, list(route["order"]) + [route["integrator"]])


class GroupChatPlanTests(unittest.TestCase):
    """Planner is stdlib (no SDK needed) — ported from Codex PR #11."""

    def test_plan_uses_canonical_roster_order_and_subsets(self):
        from scripts.group_debate import plan_brain_chat

        plan = plan_brain_chat("APEX", ["apex_intelligence_forge", "apex_deal_engine"])
        self.assertEqual(plan.speaker_order, ("apex_deal_engine", "apex_intelligence_forge"))
        self.assertEqual(plan.manager, CHIEF)

    def test_plan_rejects_mixed_brain_unknown_and_empty(self):
        from scripts.group_debate import DebateRefused, plan_brain_chat

        with self.assertRaises(DebateRefused):
            plan_brain_chat("APEX", ["apex_war_architect", "jeos_life_architect"])
        with self.assertRaises(DebateRefused):
            plan_brain_chat("JEOS", ["not_registered"])
        with self.assertRaises(DebateRefused):
            plan_brain_chat("JEOS", [])


class JeosKnowledgeGraphTests(unittest.TestCase):
    def _graph(self, tmp: str) -> JeosKnowledgeGraph:
        return JeosKnowledgeGraph(
            Path(tmp) / "graph",
            load_roster(ROOT),
            AuditLedger(Path(tmp) / "audit.jsonl"),
        )

    def test_writer_lock_read_lock_and_tag_query_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._graph(tmp)
            graph.write_page(
                "jeos_reflection_forge",
                "JEOS/Pattern-Hypotheses",
                "Energy dips after late scope calls",
                "Three of four low-energy mornings followed evening scope calls.",
                tags=["pattern-hypothesis"],
                links=["Energy Ledger"],
            )
            graph.write_page(
                "jeos_reflection_forge",
                "JEOS/Pattern-Hypotheses",
                "Old hypothesis",
                "Stale entry.",
                tags=["pattern-hypothesis"],
                date=dt.date.today() - dt.timedelta(days=90),
            )
            with self.assertRaises(GraphAccessDenied):
                graph.write_page("jeos_momentum_engine", "JEOS/Pattern-Hypotheses", "x", "y")
            with self.assertRaises(GraphAccessDenied):
                graph.query_by_tag("apex_intelligence_forge", "pattern-hypothesis")

            recent = graph.query_by_tag(
                "jeos_reflection_forge", "pattern-hypothesis", since_days=30
            )
            self.assertEqual(len(recent), 1)
            everything = graph.query_by_tag(CHIEF, "pattern-hypothesis")
            self.assertEqual(len(everything), 2)
            self.assertEqual(len(graph.backlinks(CHIEF, "Energy Ledger")), 1)

    def test_journal_appends_dated_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._graph(tmp)
            path = graph.journal("jeos_life_architect", "Weekly plan drafted.")
            self.assertIn("Weekly plan drafted.", path.read_text(encoding="utf-8"))
            with self.assertRaises(GraphAccessDenied):
                graph.journal("apex_deal_engine", "not allowed")


class McpMountRegistryTests(unittest.TestCase):
    def test_mounts_are_complete_and_policy_shaped(self):
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        names = {mount["name"] for mount in mounts}
        self.assertIn("governance", names)
        self.assertIn("filesystem", names)
        self.assertIn("civil3d", names)
        self.assertIn("terraform", names)
        self.assertIn("azure", names)
        for mount in mounts:
            self.assertTrue(mount["command"], mount["name"])
            self.assertTrue(mount["agents"], mount["name"])
            self.assertTrue(mount["purpose"], mount["name"])
            if not mount.get("verify_offline"):
                self.assertTrue(mount.get("activation"), mount["name"])

    def test_offline_verifiable_mounts_declare_the_tools_they_must_offer(self):
        # Without a declared contract, verification asserted only that a process
        # started and answered. An offline-verifiable mount is the one case
        # where the expectation can actually be checked, so it must state one.
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        for mount in mounts:
            if mount.get("verify_offline"):
                with self.subTest(mount=mount["name"]):
                    self.assertTrue(
                        mount.get("expected_tools"),
                        f"{mount['name']} can be probed but declares no expected_tools",
                    )

    def test_a_mount_offering_no_tools_is_not_verified(self):
        # The defect: status was set to "verified" the moment list_tools()
        # returned, whatever it returned. A server whose tool registration had
        # regressed completed the handshake, listed nothing, and reported
        # verified -- CI green, connector unconfirmed.
        from scripts.verify_mcp_mounts import _verdict

        mount = {"name": "governance", "expected_tools": ["validate_packet"]}
        self.assertNotEqual(_verdict(mount, []), "verified")
        self.assertIn("no tools", _verdict(mount, []))
        self.assertNotEqual(_verdict({"name": "x"}, []), "verified")

    def test_a_mount_missing_a_declared_tool_is_not_verified(self):
        from scripts.verify_mcp_mounts import _verdict

        mount = {"name": "governance", "expected_tools": ["validate_packet", "gone"]}
        verdict = _verdict(mount, ["validate_packet"])
        self.assertIn("missing declared tools: gone", verdict)

    def test_extra_upstream_tools_do_not_fail_the_mount(self):
        # `expected_tools` is a required subset, not a full listing. Asserting
        # the exact set would turn any additive upstream release into a CI
        # failure, which is how a gate gets disabled rather than fixed.
        from scripts.verify_mcp_mounts import _verdict

        mount = {"name": "filesystem", "expected_tools": ["read_text_file"]}
        self.assertEqual(_verdict(mount, ["read_text_file", "brand_new_tool"]), "verified")

    def test_infrastructure_mounts_are_apex_locked_and_grant_gated(self):
        """Terraform and Azure touch professional infrastructure, so they must
        never be reachable from a JEOS specialist and never launch ungranted.

        They are also restricted to apex_chief_of_staff alone: every APEX
        specialist is still lifecycle stage `shadow`, where the contract makes
        Agent 007 the sole executor of mutations. Listing a shadow specialist on
        a mutation-capable cloud mount would exceed its authority, so widen this
        only alongside a lifecycle promotion.
        """
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = {m["name"]: m for m in tomllib.load(source)["mounts"]}
        for name in ("terraform", "azure"):
            mount = mounts[name]
            with self.subTest(mount=name):
                self.assertTrue(mount.get("require_grant"))
                self.assertNotIn("*", mount["agents"])
                self.assertEqual(mount["agents"], ["apex_chief_of_staff"])
                for agent in mount["agents"]:
                    self.assertFalse(
                        agent.startswith("jeos_"),
                        f"{name} must stay out of the JEOS brain, got {agent}",
                    )

    def test_declared_env_covers_every_variable_the_mount_documents(self):
        """The launcher passes a mount only the variables it declares in `env`,
        so an undeclared one is silently dropped at launch.

        Both places a mount names its variables are checked: the `-e NAME` flags
        in its own command line, and the variable names written into its
        `activation` note. A mount whose documentation promises a variable the
        registry does not declare launches degraded -- either failing to
        authenticate, or, worse, falling back to a server-side default and
        quietly talking to the wrong host.
        """
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        for mount in mounts:
            declared = set(mount.get("env", []))
            command = list(mount["command"])
            forwarded = {
                command[index + 1]
                for index, token in enumerate(command)
                if token == "-e" and index + 1 < len(command) and "=" not in command[index + 1]
            }
            # Drop file paths first: docs/CIVIL3D_MCP_BUILDOUT.md is shaped
            # exactly like a variable name and is not one.
            prose = re.sub(r"\S*/\S*\.\w+", " ", mount.get("activation", ""))
            documented = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", prose))
            with self.subTest(mount=mount["name"]):
                self.assertLessEqual(
                    forwarded,
                    declared,
                    f"{mount['name']} forwards {sorted(forwarded - declared)} "
                    "with -e but does not declare it in env",
                )
                self.assertLessEqual(
                    documented,
                    declared,
                    f"{mount['name']} documents "
                    f"{sorted(documented - declared)} in its activation note "
                    "but does not declare it in env",
                )

    def test_launcher_passes_every_declared_variable_through(self):
        """The declaration above is only worth anything if the launcher honours
        it, so assert the real allowlist behaviour rather than the config."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import trusted_launcher
        finally:
            sys.path.pop(0)
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        probes = {
            name: f"probe-{name.lower()}" for mount in mounts for name in mount.get("env", [])
        }
        with mock.patch.dict(os.environ, {**probes, "UNRELATED_SECRET": "no"}, clear=False):
            for mount in mounts:
                passed = trusted_launcher.mount_env(mount)
                with self.subTest(mount=mount["name"]):
                    for name in mount.get("env", []):
                        self.assertEqual(passed.get(name), probes[name])
                    self.assertNotIn("UNRELATED_SECRET", passed)

    def test_networked_mounts_receive_transport_variables(self):
        """A mount that fetches its own package or image must still be able to
        reach the network through a proxy.

        Filtering the environment closed a credential-spill path but also
        removed HTTP_PROXY / HTTPS_PROXY / NO_PROXY, so on a proxied
        workstation authorization succeeded and the launch then failed at
        download. Proxy variables are opt-in rather than baseline because a
        proxy URL can carry credentials in its userinfo, so a purely local
        mount must not see one."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import trusted_launcher
        finally:
            sys.path.pop(0)
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]

        transport = {
            name: f"http://proxy.invalid/{name.lower()}" for name in trusted_launcher.NETWORK_ENV
        }
        with mock.patch.dict(os.environ, transport, clear=False):
            for mount in mounts:
                passed = trusted_launcher.mount_env(mount)
                networked = bool(mount.get("network"))
                with self.subTest(mount=mount["name"], networked=networked):
                    for name in trusted_launcher.NETWORK_ENV:
                        if networked:
                            self.assertEqual(passed.get(name), transport[name])
                        else:
                            self.assertNotIn(name, passed)

    def test_every_fetching_mount_declares_network(self):
        """The declaration has to track the command, or a future npx/docker
        mount silently loses its transport configuration the same way."""
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        for mount in mounts:
            fetches = mount["command"][0] in {"npx", "npm", "docker", "podman", "uvx"}
            with self.subTest(mount=mount["name"]):
                self.assertEqual(
                    bool(mount.get("network")),
                    fetches,
                    f"{mount['name']} runs {mount['command'][0]}; "
                    "network must be declared exactly when the mount fetches",
                )

    def test_registry_records_the_planners_real_tool_surface(self):
        """docs/AGENT_REGISTRY.md is what a reviewer audits mutation risk
        against. Describing these agents' tools as "the upstream list" was
        false in both directions -- it hid the removals AND the additions."""
        registry = (ROOT / "docs" / "AGENT_REGISTRY.md").read_text(encoding="utf-8")
        for agent, must_appear, must_not in (
            ("task-planner", ("`agent`", "`read`", "`edit/editFiles`"), ()),
            ("task-researcher", ("`read`",), ()),
        ):
            row = next(
                (line for line in registry.splitlines() if line.startswith(f"| `{agent}`")), None
            )
            with self.subTest(agent=agent):
                self.assertIsNotNone(row, f"no registry row for {agent}")
                self.assertNotIn(
                    "Upstream list", row, "the declared surface is a local override, not upstream"
                )
                for token in must_appear:
                    self.assertIn(token, row)
                for token in must_not:
                    self.assertNotIn(token, row)

    def test_mount_commands_pin_immutable_versions(self):
        """A mutable tag lets a mount's tool surface change with no commit,
        which defeats the point of the approved-mounts registry. Reference
        servers fetched by bare package name are exempt; anything carrying an
        explicit version must not use a floating one.

        Container images additionally need a digest: a tag is mutable even when
        it is not called `latest`, so a retag of `1.1.0` would swap the code a
        later authorized launch executes with no repository change.
        """
        floating = {"latest", "main", "master", "edge", "next", "canary"}
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        for mount in mounts:
            for token in mount["command"]:
                if "@" not in token and ":" not in token:
                    continue
                separator = "@" if token.rsplit("@", 1)[-1] and "@" in token[1:] else ":"
                tag = token.rsplit(separator, 1)[-1]
                with self.subTest(mount=mount["name"], token=token):
                    self.assertNotIn(
                        tag.lower(),
                        floating,
                        f"{mount['name']} pins a mutable tag in {token!r}",
                    )

    def test_container_images_are_pinned_by_digest(self):
        """Only images this PR introduces are required to carry a digest.
        `ghcr.io/github/github-mcp-server` predates it and is unpinned entirely;
        that is a real gap of the same class, flagged for a separate change
        rather than silently altered here."""
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = {m["name"]: m for m in tomllib.load(source)["mounts"]}
        for name in ("terraform",):
            command = " ".join(mounts[name]["command"])
            with self.subTest(mount=name):
                self.assertIn("@sha256:", command)


class SelectionReportBaselineTests(unittest.TestCase):
    """The generator is change evidence, so a figure it cannot compute must
    read as unavailable rather than as a confident zero."""

    def test_branch_point_has_no_moving_fallback(self):
        # The measurement logic lives in report_gates.py, not in the PDF
        # builder: that module imports reportlab, which CI does not install.
        source = (ROOT / "scripts" / "report_gates.py").read_text(encoding="utf-8")
        start = source.index("def _branch_point()")
        end = source.index("MARKDOWN_NOW =")
        body = source[start:end]
        # Inspect executable code only: the rationale legitimately explains why
        # the merge-base fallback was removed, and matching prose makes this
        # test fail on its own reasoning. Stripping "the first docstring" was
        # not enough -- a second helper landed in this slice and its docstring
        # tripped the check. Drop every comment and string literal instead, so
        # the assertion is about what the code CALLS, at any number of helpers.
        import io
        import tokenize

        kept = []
        try:
            for token in tokenize.generate_tokens(io.StringIO(body).readline):
                if token.type in (tokenize.COMMENT, tokenize.STRING):
                    continue
                kept.append(token.string)
        except tokenize.TokenError:
            kept = [body]  # unparseable slice: fall back to the raw text
        body = " ".join(kept)
        self.assertNotIn(
            "merge-base",
            body,
            "a merge-base fallback recreates the moving baseline it replaced: "
            "once this work merges it resolves to the merged tip and the delta "
            "silently becomes zero",
        )
        self.assertIn("PRE_INSTALL_BASELINE", body)

    def test_a_failed_file_count_reads_as_unmeasured_not_as_zero(self):
        """Empty output from a failed command is not a measurement of zero.

        `count_tracked` ignored git's exit code, so an extracted archive with
        no `.git`, or a corrupt index, produced a confident "the tree carries 0
        markdown files" — while the sibling `count_tracked_at` and the delta
        both correctly reported unavailable. This is the report's own rule one
        level down: never render an unrun check as a clean one."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import report_gates
        finally:
            sys.path.pop(0)

        real_run = report_gates.subprocess.run

        def failing(cmd, **kwargs):
            if cmd[:2] == ["git", "ls-files"]:
                return type(
                    "R",
                    (),
                    {"returncode": 128, "stdout": "", "stderr": "fatal: not a git repository"},
                )()
            return real_run(cmd, **kwargs)

        with mock.patch.object(report_gates.subprocess, "run", failing):
            self.assertEqual(report_gates.count_tracked("*.md"), -1)
        # The healthy path must still return a real count, or this asserts
        # nothing about the failure being distinguishable.
        self.assertGreater(report_gates.count_tracked("*.md"), 0)

    def test_the_integration_merge_is_not_read_as_an_upstream_tip(self):
        """The remedy collapsed in exactly the case its docstring claimed.

        `_merged_upstream_tips` reads every merge's second parent, which is
        right while merges bring main INTO this branch. Once GitHub integrates
        the PR, that merge's second parent is this branch -- so every file the
        branch added would count as having come from elsewhere and the
        published delta would read zero, in the document whose whole purpose is
        installation evidence.

        Skips rather than fails where the anchors are absent. A shallow clone
        has neither, and the first version of this test asserted reachability
        unconditionally: it passed in CI (`fetch-depth: 0`) and failed in any
        `--depth 1` checkout. `_branch_point` already reports the figure as
        unmeasurable there; the test has to agree rather than demand history
        the clone does not have."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import report_gates
        finally:
            sys.path.pop(0)

        if not report_gates._known(report_gates.BRANCH_ROOT):
            self.assertEqual(
                report_gates.MARKDOWN_ADDED,
                -1,
                "with the anchor absent the delta must read unmeasurable, never a number",
            )
            self.skipTest("shallow clone: the branch anchor is not present")

        for tip in report_gates._merged_upstream_tips():
            with self.subTest(tip=tip[:10]):
                self.assertIs(
                    report_gates._contains(tip, report_gates.BRANCH_ROOT),
                    False,
                    "a commit containing this branch's first commit is this "
                    "work, not an upstream tip",
                )

        self.assertIs(
            report_gates._contains("HEAD", report_gates.BRANCH_ROOT),
            True,
            "BRANCH_ROOT must be an ancestor of HEAD or the anchor is wrong",
        )
        self.assertIs(
            report_gates._contains(report_gates.PRE_INSTALL_BASELINE, report_gates.BRANCH_ROOT),
            False,
        )
        self.assertGreater(report_gates.MARKDOWN_ADDED, 0)

    def test_an_unanswerable_history_reports_no_delta_rather_than_a_wrong_one(self):
        """A shallow clone cannot classify a merge tip at all.

        `merge-base --is-ancestor` exits non-zero both when the answer is "no"
        and when the commit is absent, and collapsing those to a boolean made
        an unanswerable question read as "not this branch" -- the answer that
        erases the branch's own delta. Unknown is now its own result."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import report_gates
        finally:
            sys.path.pop(0)

        absent = "0" * 40
        self.assertFalse(report_gates._known(absent))
        self.assertIsNone(report_gates._contains("HEAD", absent))
        self.assertIsNone(report_gates._contains(absent, "HEAD"))

        with mock.patch.object(report_gates, "BRANCH_ROOT", absent):
            self.assertEqual(report_gates._markdown_added(), -1)

    def test_the_delta_excludes_work_that_arrived_from_main(self):
        """The headline figure must measure THIS branch, not the merge.

        Subtracting only the pinned baseline attributed every file that came in
        from main to this work: the baseline held 46 markdown files, the merged
        main tip held 58, HEAD held 78 — so the report published "adds 32" for
        a branch that adds 20, in the one document meant to be installation
        evidence. A merge's second parent is a permanent record of the upstream
        tip, so unlike merge-base it survives this work landing."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import report_gates
        finally:
            sys.path.pop(0)
        namespace = vars(report_gates)

        added = namespace["MARKDOWN_ADDED"]
        now = namespace["MARKDOWN_NOW"]
        baseline = namespace["_MD_BEFORE"]
        if not namespace["_BASE"]:
            self.skipTest("not on a feature branch — run on a PR branch")
        try:
            tips = namespace["_merged_upstream_tips"]()
        except report_gates._Unanswerable:
            # `MARKDOWN_ADDED` already reports -1 for this clone; erroring here
            # would fail the mandated validation surface in every `--depth 1`
            # checkout, which the sibling tests above deliberately skip.
            self.assertEqual(added, -1)
            self.skipTest("shallow clone: a merged tip cannot be classified")
        if baseline < 0:
            self.skipTest("pre-install baseline unreachable in this clone")

        self.assertGreaterEqual(added, 0)
        # The naive figure counts everything since the baseline. Whenever a
        # merge has brought work in, the honest figure must be strictly
        # smaller -- that difference IS the defect, so assert it rather than a
        # fixed number that drifts with main.
        if tips:
            self.assertLess(
                added,
                now - baseline,
                "with upstream merges present, the delta must exclude the "
                "files that arrived from main",
            )
        self.assertLessEqual(added, now - baseline)

    def test_a_passing_gate_still_names_what_it_could_not_probe(self):
        """`"valid": true` means the registry is self-consistent, not that every
        mount was reached. A mount whose offline probe could not run comes back
        "unverified", and rendering that row as a bare "passed" publishes an
        unrun check as a clean one."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from report_gates import unverified_note
        finally:
            sys.path.pop(0)

        stalled = json.dumps(
            {
                "mounts": [
                    {"name": "governance", "status": "unverified (mcp package not installed)"},
                    {"name": "github", "status": "registered"},
                    {"name": "filesystem", "status": "unverified (mcp package not installed)"},
                    {"name": "reached-mount", "status": "verified (3 tools)"},
                ],
                "valid": True,
            }
        )
        note = unverified_note(stalled)
        self.assertIn("governance", note)
        self.assertIn("filesystem", note)
        # "registered" is ALSO unprobed, and the larger group. An earlier
        # version of this test asserted github must be ABSENT here, which
        # encoded the defect: the row then advertised a clean scope covering
        # two mounts while six others had equally never been contacted.
        self.assertIn("github", note)
        # A mount that really was probed must not appear. (Named so it is not a
        # substring of the note's own "not probed:" prefix -- the first version
        # of this assertion matched that and passed for the wrong reason.)
        self.assertNotIn("reached-mount", note)

        clean = json.dumps(
            {
                "mounts": [{"name": "github", "status": "verified (12 tools)"}],
                "valid": True,
            }
        )
        self.assertEqual(unverified_note(clean), "")

        # Non-JSON output must not be read as "nothing unverified".
        self.assertNotEqual(unverified_note("2 unverified mounts"), "")
        self.assertEqual(unverified_note("all mounts reached"), "")

    def test_a_passing_gate_says_when_the_runtime_is_absent(self):
        """TOML and schema checks pass on a machine where none of the declared
        runtime packages is installed, and the gate still exits 0 with
        `"valid": true`. Rendering that as a clean runtime-stack pass presents
        a machine with no orchestration runtime as a verified one."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from report_gates import missing_dependency_note
        finally:
            sys.path.pop(0)

        empty = json.dumps(
            {
                "valid": True,
                "installed_count": 0,
                "missing": [f"pkg{n}" for n in range(20)],
                "toml_files_checked": 18,
            }
        )
        note = missing_dependency_note(empty)
        self.assertIn("20 of 20", note)
        self.assertIn("declarations only", note)

        full = json.dumps({"valid": True, "installed_count": 20, "missing": []})
        self.assertEqual(missing_dependency_note(full), "")

        partial = json.dumps(
            {"valid": True, "installed_count": 18, "missing": ["crewai", "prefect"]}
        )
        self.assertIn("2 of 20", missing_dependency_note(partial))

    def test_a_grant_scope_must_be_readable_not_merely_truthy(self):
        """This field is the only blast-radius disclosure before signing.

        The check was a truthiness test, so `1`, `true` and `"   "` all passed
        while telling Joe nothing at the moment he authorizes a whole-server
        grant. An unreadable disclosure is worse than none, because it looks
        like one."""
        import subprocess

        registry = ROOT / "config" / "mcp_mounts.toml"
        original = registry.read_text(encoding="utf-8")
        unusable = {
            "blank string": 'grant_scope = "   "',
            "empty string": 'grant_scope = ""',
            "integer": "grant_scope = 1",
            "boolean": "grant_scope = true",
        }
        try:
            for label, replacement in unusable.items():
                lines, replaced = [], False
                for line in original.splitlines():
                    if line.startswith("grant_scope") and not replaced:
                        lines.append(replacement)
                        replaced = True
                    else:
                        lines.append(line)
                self.assertTrue(replaced, "no grant_scope line to replace")
                registry.write_text("\n".join(lines) + "\n", encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "verify_mcp_mounts.py")],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                with self.subTest(value=label):
                    self.assertNotEqual(completed.returncode, 0, label)
                    self.assertIn("undeclared grant scope", completed.stdout)
        finally:
            registry.write_text(original, encoding="utf-8")

        restored = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_mcp_mounts.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(restored.returncode, 0, restored.stdout[-300:])

    def test_the_mount_verifier_fails_an_undeclared_grant_scope(self):
        """The declaration has to be enforced, or it is a convention.

        `grant_scope` states the blast radius a signature actually authorizes.
        If a new grant-gated mount can be added without one, the next Terraform
        or Azure equivalent lands with its surface unstated and nothing
        notices -- which is the situation this field exists to end."""
        import subprocess
        import tomllib

        raw = (ROOT / "config" / "mcp_mounts.toml").read_text(encoding="utf-8")
        stripped = "\n".join(
            line for line in raw.splitlines() if not line.startswith("grant_scope")
        )
        # Sanity: the strip must actually remove something, or the negative
        # case below proves nothing.
        gated = [m for m in tomllib.loads(stripped)["mounts"] if m.get("require_grant")]
        self.assertTrue(gated)
        self.assertTrue(all("grant_scope" not in m for m in gated))

        registry = ROOT / "config" / "mcp_mounts.toml"
        backup = raw
        try:
            registry.write_text(stripped, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_mcp_mounts.py")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            registry.write_text(backup, encoding="utf-8")

        self.assertNotEqual(completed.returncode, 0, "an undeclared grant scope must fail the gate")
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["valid"])
        self.assertIn(
            "undeclared grant scope", [entry.get("status") for entry in payload["mounts"]]
        )

        # And the unmodified registry must still pass, so the check is a real
        # gate rather than a permanent failure.
        restored = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_mcp_mounts.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(restored.returncode, 0, restored.stdout[-400:])

    def test_the_corps_row_discloses_that_nothing_live_ran(self):
        """The largest scope limit of the three gates disclosed nothing.

        `validate_specialist_corps.py` reports, on every normal build, that no
        connector was called, no named agent invoked and no real mission
        completed — and the row rendered as a bare `passed, "valid": true`. The
        neighbouring gates already name unprobed mounts and absent packages;
        this one stayed silent about the biggest limitation, in the document
        whose stated rule is that an unrun check is never rendered clean."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from report_gates import run_gate, static_validation_note
        finally:
            sys.path.pop(0)

        payload = json.dumps(
            {
                "valid": True,
                "connectors_called": False,
                "named_agents_invoked": False,
                "real_missions_completed": False,
                "validation_mode": "static_contract_and_synthetic_packet",
            }
        )
        note = static_validation_note(payload)
        for expected in (
            "no connector called",
            "no named agent invoked",
            "no real mission completed",
            "static contract",
        ):
            with self.subTest(disclosure=expected):
                self.assertIn(expected, note)

        # A gate that DID exercise these must not carry the note, or it is
        # boilerplate rather than a measurement.
        exercised = json.dumps(
            {
                "valid": True,
                "connectors_called": True,
                "named_agents_invoked": True,
                "real_missions_completed": True,
            }
        )
        self.assertEqual(static_validation_note(exercised), "")
        self.assertEqual(static_validation_note("not json"), "")

        # And the real row must carry it, end to end.
        row = run_gate("validate_specialist_corps.py")
        self.assertIn("no connector called", row)

    def test_a_failed_json_gate_row_names_the_actual_error(self):
        """These gates print JSON, so the first output line is "{". Taking it
        produced rows reading `FAILED (exit 1) — {`, which identifies
        nothing in the one document meant to be failure evidence."""
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from report_gates import failure_detail
        finally:
            sys.path.pop(0)

        class Completed:
            def __init__(self, stdout, stderr):
                self.stdout, self.stderr = stdout, stderr

        structured = Completed(
            json.dumps(
                {"valid": False, "errors": ["config/roster.toml: unknown key 'brian'"]}, indent=2
            ),
            "",
        )
        self.assertIn("unknown key", failure_detail(structured))
        self.assertNotEqual(failure_detail(structured).strip(), "{")

        crashed = Completed(
            "{\n}",
            'Traceback (most recent call last):\n  File "x", line 1\n'
            "ValueError: no pin in manifest\n",
        )
        self.assertEqual(failure_detail(crashed), "ValueError: no pin in manifest")

        self.assertEqual(failure_detail(Completed("", "")), "no output")

        # The gate that actually fails in practice -- a mount probe -- carries
        # no top-level error key at all: its reason lives only in
        # mounts[*].status. The substantive-line fallback then discarded every
        # quoted status line and returned "{", reproducing the exact
        # uninformative row it exists to prevent. Assert the shape, not the one
        # key name: any nested list of entries whose status reads as a failure
        # has to reach the row.
        for section in ("mounts", "connectors", "servers"):
            nested = Completed(
                json.dumps(
                    {
                        "valid": False,
                        section: [
                            {"name": "governance", "status": "probe failed: no such file"},
                            {"name": "github", "status": "registered"},
                        ],
                    },
                    indent=2,
                ),
                "",
            )
            with self.subTest(section=section):
                detail = failure_detail(nested)
                self.assertIn("governance", detail)
                self.assertIn("no such file", detail)
                self.assertNotEqual(detail.strip(), "{")
                # A healthy entry must not be reported as a failure.
                self.assertNotIn("github", detail)

        errored = Completed(
            json.dumps(
                {
                    "valid": False,
                    "mounts": [{"name": "postgres", "status": "error: connection refused"}],
                }
            ),
            "",
        )
        self.assertIn("connection refused", failure_detail(errored))

        # Match by EXCLUSION, not by keyword. An allowlist of "fail"/"error"
        # had to be remembered for each new failure status, and the very next
        # one added -- "undeclared grant scope" -- contains neither word, so
        # the row regressed to `FAILED (exit 1) — },`. Assert the property
        # across statuses that share no vocabulary at all.
        for status in (
            "undeclared grant scope",
            "refused by policy",
            "timed out",
            "missing digest pin",
        ):
            nameless = Completed(
                json.dumps(
                    {
                        "valid": False,
                        "mounts": [
                            {"name": "azure", "status": status},
                            {"name": "github", "status": "registered"},
                        ],
                    },
                    indent=2,
                ),
                "",
            )
            with self.subTest(status=status):
                detail = failure_detail(nameless)
                self.assertIn(status, detail)
                self.assertNotIn("github", detail)
                self.assertNotIn("{", detail)
                self.assertNotIn("}", detail)

        # A top-level error key still wins: it is the more specific signal.
        both = Completed(
            json.dumps(
                {
                    "valid": False,
                    "errors": ["registry is malformed"],
                    "mounts": [{"name": "governance", "status": "probe failed: no such file"}],
                }
            ),
            "",
        )
        self.assertIn("registry is malformed", failure_detail(both))

    def test_report_refuses_to_publish_an_inventory_it_cannot_reconcile(self):
        """Counting every tracked path under .github/ as upstream adoption
        misattributes repository-authored files to the pinned inventory, and
        lets a newly vendored file raise the total while the report's own
        rationale tables omit it."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        self.assertIn("def reconcile_with_manifest()", source)
        self.assertIn("reconcile_with_manifest()\n", source)
        # It must run at generation time, not merely be defined.
        self.assertIn("raise SystemExit", source)

    def test_the_report_never_contradicts_the_manifest_it_reports_on(self):
        """The report's standing recommendation told the maintainer to bump the
        pin whenever files are refreshed; the manifest requires the opposite
        for a partial refresh.

        Following the generated report therefore attributed untouched files to
        a commit whose bytes they may not match -- the single claim the report
        and the manifest both rest on. Asserted as agreement between the two
        documents rather than against one sentence, because the failure mode is
        drift between them."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        manifest = (ROOT / ".github" / "AWESOME-COPILOT.md").read_text(encoding="utf-8")
        self.assertIn(
            "manifest-WIDE",
            manifest,
            "the manifest must still state the pin's scope, or there is "
            "nothing for the report to agree with",
        )
        recommendation = source[source.index("Standing recommendation") :]
        self.assertIn(
            "manifest-WIDE",
            recommendation,
            "the report must carry the manifest's pin scope, not a rule of its own",
        )
        self.assertNotIn(
            "whenever files are refreshed",
            recommendation,
            "an unconditional bump instruction contradicts the manifest's partial-refresh rule",
        )

    def test_manifest_parsing_accepts_any_vendored_skill(self):
        """Reconciliation must not abort on a valid intake.

        Matching only the `suggest-awesome-github-copilot-*` family meant that
        vendoring any other skill -- the ordinary outcome of a discovery pass --
        left it unparsed, so reconciliation saw a tracked skill the manifest
        "did not list" and refused to generate the report."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        bullet = re.search(r'skills = re\.findall\(\s*r"([^"]+)"', source)
        self.assertIsNotNone(bullet, "skill bullet pattern not found")
        pattern = re.compile(bullet.group(1), re.MULTILINE)

        manifest = (ROOT / ".github" / "AWESOME-COPILOT.md").read_text(encoding="utf-8")
        self.assertEqual(
            len(pattern.findall(manifest)), 3, "the three discovery skills must still parse"
        )
        self.assertIn(
            "gh-cli",
            pattern.findall(manifest + "\n- `gh-cli/`\n"),
            "a future vendored skill must parse too, or reconciliation "
            "aborts generation on a valid intake",
        )

    def test_planner_agents_scope_reads_to_one_brain(self):
        """These agents' output is returned for persistence, so anything they
        read can be copied into a durable artifact -- which makes an unscoped
        read the same leak as an unscoped write, one step later. AGENTS.md
        makes Agent 007 the sole cross-brain agent, and neither of these is
        that."""
        for name in ("task-planner", "task-researcher"):
            body = (ROOT / ".github" / "agents" / f"{name}.agent.md").read_text(encoding="utf-8")
            with self.subTest(agent=name):
                self.assertNotIn(
                    "throughout the entire workspace",
                    body,
                    "an unscoped read grant lets this agent ingest the other "
                    "brain's records into a persisted artifact",
                )
                self.assertNotIn("across the entire workspace", body)
                self.assertIn("brain", body.lower())
                self.assertIn("audit/*.jsonl", body)

    def test_report_rows_are_reconciled_not_just_counted(self):
        """Reconciling the manifest against the tracked tree is half the check.

        The rationale tables are separate hardcoded lists, so an asset could be
        tracked, listed in the manifest, and still absent from the report --
        counted in the totals but published with no row saying why it was
        selected."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        self.assertIn("def rendered_names()", source)
        for token in ("INSTRUCTION_ROWS", "AGENT_ROWS", "SKILL_ROWS"):
            self.assertIn(token, source)
        self.assertIn("renders no row", source)
        self.assertIn("the manifest does not claim", source)
        # And the check must actually consult the rendered rows.
        self.assertIn("shown = rendered_names()", source)

    def test_researcher_does_not_block_on_user_dialogue(self):
        """It runs as a sub-agent: its result returns to task-planner, not to
        the user. The planner cannot answer a preference question from evidence
        and may not plan until the research is complete, so a comparative task
        deadlocked at its mandatory first step."""
        body = (ROOT / ".github" / "agents" / "task-researcher.agent.md").read_text(
            encoding="utf-8"
        )
        name = "task-researcher"
        self.assertIn("You WILL NOT ask the user questions", body)
        self.assertIn("Decisions for the invoker", body)
        # Assert the PROPERTY, not the three reported sentences: the first fix
        # rewrote one dialogue block and left a near-identical second one
        # untouched a few sections up. Any surviving instruction to question or
        # wait for the user is the same stall.
        import re as _re

        stalling = _re.compile(
            r"(?im)^.*(?:ask (?:the )?user|ask specific questions"
            r"|help user choose|validate user's selection"
            r"|wait for (?:the )?user|confirm with (?:the )?user"
            r"|user doesn't want to iterate).*$"
        )
        offending = [
            line
            for line in stalling.findall(body)
            # The override paragraph explains why it must not happen; that is
            # the fix, not an instance of the defect.
            if not _re.search(
                r"MUST NOT|WILL NOT|not to the user|stall"
                r"|deadlock|rather than ask",
                line,
            )
        ]
        self.assertEqual(offending, [], f"{name}: residual user dialogue")

    def test_planner_artifact_count_is_conditional_not_fixed(self):
        """An unconditional "exactly three" contradicted the rule requiring the
        research document as a fourth artifact on a first-time task. An agent
        resolving that contradiction drops either the research the invoker must
        persist or one of the planning artifacts -- and which one it drops is
        not predictable, which is worse than either."""
        body = (ROOT / ".github" / "agents" / "task-planner.agent.md").read_text(encoding="utf-8")
        self.assertNotIn("exactly three artifacts", body)
        self.assertNotIn("three complete artifacts", body)
        self.assertIn("**four**", body)
        # Every surface that states the count must state the conditional form.
        for line in body.splitlines():
            if "three" in line and "artifact" in line:
                with self.subTest(line=line.strip()[:90]):
                    self.assertTrue(
                        "four" in line or "planning artifact" in line,
                        "a bare three-artifact claim reintroduces the contradiction",
                    )

    def test_discovery_fetches_are_pinned_to_a_resolved_sha(self):
        """The vendored bodies fetch `/main/`, a moving ref: upstream can
        advance between the inventory fetch and the per-file downloads, so the
        comparison, the installed bytes and the recorded pin could each
        describe a different revision. The contract requires one resolved SHA
        per pass, and the preamble has to say so where the fetches are."""
        for skill in sorted((ROOT / ".github" / "skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            with self.subTest(skill=skill.parent.name):
                self.assertIn("resolved SHA", text)
                self.assertIn("moving ref", text)
                # The instruction must appear BEFORE the upstream body that
                # carries the /main/ URLs, or it is not an override.
                self.assertLess(
                    text.index("resolved SHA"),
                    text.index("raw.githubusercontent.com"),
                    "the override must precede the fetches it governs",
                )

    def test_exclusion_labels_derive_from_the_active_pin(self):
        """The headline already says "not enumerated at this pin" when the
        manifest moves to an unknown SHA; these labels kept printing the
        previous pin's plugin/hook/workflow/extension figures beside it, so one
        regenerated report asserted both."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        self.assertIn("def _count_label(", source)
        for hardcoded in ("Plugins (71)", "Hooks (8) and workflows (8)", "Extensions (20)"):
            self.assertNotIn(hardcoded, source)

        # Behavioural: a known pin labels, an unknown pin says nothing.
        inventory = source[
            source.index("UPSTREAM_INVENTORY_BY_PIN") : source.index("def manifest_pin()")
        ]
        label = source[
            source.index("def _count_label(kind: str) -> str:") : source.index(
                "def _cell(value) -> str:"
            )
        ]
        for pin, expect in (("aa280f28", " (71)"), ("zz000000", "")):
            namespace: dict = {}
            exec(inventory, namespace)  # noqa: S102 - reading this module's own source
            namespace["UPSTREAM_INVENTORY"] = namespace["UPSTREAM_INVENTORY_BY_PIN"].get(pin, {})
            exec(label, namespace)  # noqa: S102
            with self.subTest(pin=pin):
                self.assertEqual(namespace["_count_label"]("plugins"), expect)

    def test_gate_rows_come_from_the_importable_helper(self):
        """The report builder runs its gates and writes the PDF at import time,
        so the helpers must live outside it or they cannot be tested without
        regenerating the document."""
        source = (ROOT / "scripts" / "build_awesome_copilot_report.py").read_text(encoding="utf-8")
        self.assertIn("from report_gates import", source)
        self.assertNotIn("def run_gate(", source)


if __name__ == "__main__":
    unittest.main()
