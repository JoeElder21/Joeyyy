"""Denial-first tests for the trusted launcher: every refusal path is proven
before any activation path is trusted. Stdlib-only — always runs in CI."""

from __future__ import annotations

import json
import time
from pathlib import Path
import tempfile
import unittest

from scripts.agent_runtime import AuditLedger
from scripts.trusted_launcher import (
    BASELINE_ENV, LaunchDenied, ManifestUnavailable,
    authorize, connector_stages, issue_grant, mount_env, specialist_stage,
    stage_permits_connector,
)

ROOT = Path(__file__).resolve().parents[1]


class TrustedLauncherTests(unittest.TestCase):
    def _env(self, tmp: str):
        key = Path(tmp) / "launch_key"
        ledger = AuditLedger(Path(tmp) / "launcher.jsonl")
        return key, ledger

    def test_a_shadow_specialist_cannot_be_granted_a_mount(self):
        """Being on a mount's allowlist is necessary, not sufficient.

        Those lists record which specialist WILL own a mount once promoted.
        Making them executable without a lifecycle check handed mutation-capable
        connectors -- the repository-wide filesystem mount among them -- to
        agents the contract confines to analysis and proposed writes. Every
        rostered specialist is `shadow`, so in practice Agent 007 is the only
        identity that can hold a grant, which is the documented arrangement.
        """
        import tomllib

        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        scoped = [(m["name"], agent) for m in mounts
                  for agent in m.get("agents", [])
                  if agent != "*" and specialist_stage(agent) is not None]
        self.assertTrue(scoped, "no rostered specialist appears on any mount")

        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            for mount, agent in scoped:
                with self.subTest(mount=mount, agent=agent):
                    with self.assertRaises(LaunchDenied) as caught:
                        issue_grant(mount, 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent=agent, ledger=ledger)
                    self.assertIn("lifecycle stage", str(caught.exception))
            # Every refusal is recorded; a denied mint is exactly the event an
            # audit should surface.
            events = [json.loads(line)["event"]
                      for line in (Path(tmp) / "launcher.jsonl")
                      .read_text(encoding="utf-8").splitlines()]
            self.assertEqual(set(events), {"grant_denied"})
            self.assertEqual(len(events), len(scoped))

    def test_the_designated_executor_is_not_stage_gated(self):
        """Agent 007 is not a rostered specialist. It is the designated
        executor, which is the whole reason the specialists are restricted."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            path = issue_grant("terraform", 30, key_path=key,
                               out_dir=Path(tmp) / "grants",
                               agent="apex_chief_of_staff", ledger=ledger)
            self.assertTrue(path.exists())
            self.assertIsNone(specialist_stage("apex_chief_of_staff"))

    def test_only_service_stages_permit_a_connector(self):
        """Eligibility is membership, not position in the stage list.

        The ordinal test this replaces was wrong in the one direction that
        matters: candidate, shadow, active, value-proven, restricted,
        deprecated, retired means every ADMINISTRATIVE EXIT sorts after
        `active` and compared as a promotion. A specialist the lifecycle graph
        moved to `restricted` for writing outside its lease kept full connector
        eligibility, as did a deprecated or retired one.

        Asserted over every stage the corps declares, so a stage added later is
        covered without editing this test."""
        import tomllib

        with (ROOT / "config" / "specialist_corps.toml").open("rb") as source:
            declared = tomllib.load(source)["lifecycle"]["stages"]

        for stage in declared:
            with self.subTest(stage=stage):
                self.assertEqual(
                    stage_permits_connector(stage), stage in connector_stages())

        for exit_stage in ("restricted", "deprecated", "retired"):
            with self.subTest(stage=exit_stage):
                self.assertIn(exit_stage, declared)
                self.assertFalse(
                    stage_permits_connector(exit_stage),
                    "an administrative exit must revoke connector eligibility",
                )
        self.assertFalse(stage_permits_connector("not-a-stage"))
        # Not a rostered specialist -> not stage-gated at all.
        self.assertTrue(stage_permits_connector(None))

    def test_lifecycle_is_revalidated_when_the_grant_is_consumed(self):
        """A grant is short-lived but not instantaneous.

        Eligibility can be withdrawn inside its window: a specialist that was
        `active` at mint and `restricted` at launch would otherwise still be
        authorized, because the signature, expiry and allowlist all still check
        out. An administrative restriction has to revoke OUTSTANDING access,
        not merely prevent new grants."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with mock.patch.object(launcher, "specialist_stage",
                                   lambda agent, corps=None: "active"):
                grant = issue_grant("filesystem", 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent="apex_systems_blacksmith",
                                    ledger=ledger)
            self.assertTrue(grant.exists(), "mint must succeed while eligible")

            # Every exit stage must revoke it, not just the reported one.
            for withdrawn in ("restricted", "deprecated", "retired"):
                with self.subTest(stage=withdrawn):
                    with mock.patch.object(launcher, "specialist_stage",
                                           lambda agent, corps=None, s=withdrawn: s):
                        with self.assertRaises(LaunchDenied) as caught:
                            authorize("filesystem", grant_path=grant,
                                      key_path=key, ledger=ledger)
                    self.assertIn("lifecycle stage", str(caught.exception))

            # And the grant still works while eligibility holds, so the check
            # is a revocation rather than a blanket refusal.
            with mock.patch.object(launcher, "specialist_stage",
                                   lambda agent, corps=None: "active"):
                authorize("filesystem", grant_path=grant, key_path=key,
                          ledger=ledger)

    def test_an_unreadable_brain_manifest_denies_rather_than_falls_back(self):
        """Deleting a file must not be a way to gain authority.

        Returning {} on a read failure was a fail-OPEN: with no per-agent entry
        found, resolution fell back to the corps-wide deployed_stage, so the
        moment that snapshot reads `active` an unreadable or deleted manifest
        made every allowlisted roster specialist connector-eligible -- including
        one whose authoritative status is shadow or restricted. The agent's real
        status is exactly what could not be read."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with mock.patch.object(
                launcher, "_brain_manifest",
                side_effect=ManifestUnavailable("brains/apex/agents.toml: gone"),
            ):
                # Mint-time refusal.
                with self.assertRaises(LaunchDenied) as caught:
                    issue_grant("filesystem", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_systems_blacksmith", ledger=ledger)
                self.assertIn("cannot resolve the lifecycle stage",
                              str(caught.exception))

            # And at consumption: a grant minted while readable must not survive
            # the manifest becoming unreadable afterwards.
            with mock.patch.object(launcher, "specialist_stage",
                                   lambda agent, corps=None: "active"):
                grant = issue_grant("filesystem", 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent="apex_systems_blacksmith",
                                    ledger=ledger)
            with mock.patch.object(
                launcher, "_brain_manifest",
                side_effect=ManifestUnavailable("brains/apex/agents.toml: gone"),
            ):
                with self.assertRaises(LaunchDenied) as caught:
                    authorize("filesystem", grant_path=grant, key_path=key,
                              ledger=ledger)
                self.assertIn("cannot resolve the lifecycle stage",
                              str(caught.exception))

    def test_lifecycle_resolves_from_the_named_agent_not_the_snapshot(self):
        """A promotion is per agent; a restriction must not be widened.

        Reading the corps-wide deployed_stage was wrong both ways: an
        individually promoted specialist was denied, and moving the snapshot to
        `active` would have made every still-shadow allowlisted specialist
        eligible at once."""
        import tomllib

        with (ROOT / "config" / "specialist_corps.toml").open("rb") as source:
            corps = tomllib.load(source)

        for key in ("apex_brain_manifest", "jeos_brain_manifest"):
            with (ROOT / corps[key]).open("rb") as source:
                entries = tomllib.load(source).get("agents", {})
            for agent, entry in entries.items():
                if not isinstance(entry, dict) or "status" not in entry:
                    continue
                with self.subTest(agent=agent):
                    resolved = specialist_stage(agent)
                    self.assertIn(
                        resolved, {entry["status"],
                                   corps["lifecycle"]["deployed_stage"]})
                    # Whichever it took, it must not grant more than the
                    # agent's own recorded status allows.
                    if not stage_permits_connector(entry["status"]):
                        self.assertFalse(stage_permits_connector(resolved))

        # An agent with no per-agent entry falls back to the snapshot; the
        # NAMED designated executor is not stage-gated at all.
        snapshot_only = {
            "apex_roster": ["apex_probe"],
            "jeos_roster": [],
            "governance": {"designated_executor": "apex_chief_of_staff"},
            "lifecycle": {"deployed_stage": "shadow"},
        }
        self.assertEqual(
            specialist_stage("apex_probe", corps=snapshot_only), "shadow")
        self.assertIsNone(
            specialist_stage("apex_chief_of_staff", corps=snapshot_only))

    def test_grant_for_an_agent_scoped_mount_needs_an_identity(self):
        """The identity lives in the signed grant, so it must be supplied when
        the grant is minted -- which only Joe's machine can do."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied) as caught:
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants", ledger=ledger)
            self.assertIn("--agent is required", str(caught.exception))

    def test_grant_cannot_be_minted_for_a_non_allowlisted_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            for identity in ("jeos_life_architect", "apex_systems_blacksmith",
                             "not_an_agent"):
                with self.subTest(agent=identity):
                    with self.assertRaises(LaunchDenied) as caught:
                        issue_grant("terraform", 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent=identity, ledger=ledger)
                    self.assertIn("is not on", str(caught.exception))

    def test_a_permissive_snapshot_cannot_stand_in_for_a_missing_record(self):
        """The snapshot fallback is only safe while the snapshot denies.

        Two shapes leave `per_agent` unset without anything being malformed:
        the corps file omits the owning brain-manifest path, or the manifest is
        readable but has no entry for this agent. Both then inherited the
        corps-wide `deployed_stage`. That is harmless at `shadow` and a
        fail-open the moment the snapshot reads `active` -- it hands a
        connector to every allowlisted specialist whose promotion nobody
        recorded, which is exactly the widening `specialist_stage` says it
        exists to prevent: a per-agent promotion must be recorded per agent."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        base = {
            "apex_roster": ["apex_probe"],
            "jeos_roster": [],
            "governance": {"designated_executor": "apex_chief_of_staff"},
        }
        for permissive in sorted(connector_stages()):
            corps = {**base, "lifecycle": {"deployed_stage": permissive}}
            with self.subTest(snapshot=permissive, shape="no manifest path"):
                self.assertFalse(stage_permits_connector(
                    specialist_stage("apex_probe", corps=corps)))
            with_path = {**corps, "apex_brain_manifest": "brains/apex/agents.toml"}
            with mock.patch.object(
                    launcher, "_brain_manifest",
                    lambda path: {"brain": "APEX", "agents": {}}):
                with self.subTest(snapshot=permissive, shape="no agent entry"):
                    self.assertFalse(stage_permits_connector(
                        specialist_stage("apex_probe", corps=with_path)))

        # A DENYING snapshot must still be inherited -- that fallback is the
        # normal case and removing it would deny nothing extra while making
        # every unpromoted specialist look like a configuration error.
        denying = {**base, "lifecycle": {"deployed_stage": "shadow"}}
        self.assertEqual(specialist_stage("apex_probe", corps=denying), "shadow")

    def test_an_unauthenticated_agent_is_logged_as_a_claim_not_an_identity(self):
        """The hash chain is only as good as what it attributes.

        A grant-free wildcard mount has no signature over `--agent`, so nothing
        authenticates it. Writing it into the same `agent` field a grant-backed
        launch uses preserved a caller-chosen string as verified audit
        evidence -- worse than recording nothing, because the chain then
        vouches for it."""
        with tempfile.TemporaryDirectory() as tmp:
            _, ledger = self._env(tmp)
            authorize("governance", None, ledger=ledger, agent="forged-identity")
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([e["event"] for e in entries], ["launch_authorized"])
            detail = entries[-1]["detail"]
            self.assertNotIn(
                "agent", detail,
                "an unauthenticated string must not occupy the field a signed "
                "identity occupies")
            self.assertEqual(detail["claimed_agent"], "forged-identity")
            self.assertIs(detail["agent_authenticated"], False)
            self.assertEqual(ledger.verify(), [])

        # A grant-backed launch still records an authenticated identity, so the
        # two are distinguishable in the ledger rather than uniformly hedged.
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            from unittest import mock

            import scripts.trusted_launcher as launcher
            with mock.patch.object(launcher, "specialist_stage",
                                   lambda agent, corps=None: "active"):
                grant = issue_grant("filesystem", 30, key_path=key,
                                    out_dir=Path(tmp) / "grants",
                                    agent="apex_systems_blacksmith",
                                    ledger=ledger)
                authorize("filesystem", grant_path=grant, key_path=key,
                          ledger=ledger)
            granted = [
                json.loads(line) for line
                in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ][-1]
            self.assertEqual(granted["detail"].get("agent"),
                             "apex_systems_blacksmith")

    def test_a_grant_is_never_signed_without_a_readable_disclosure(self):
        """The gate has to run on the path it guards, not beside it.

        `grant_scope` was validated in verify_mcp_mounts.py only, so the
        AUTHORIZATION path itself was unprotected: a runtime registry with a
        missing, blank or non-string scope still produced a signed grant, and
        the mint output showed an empty disclosure for a whole-server
        authority. Joe signs at mint time, so mint time is where the disclosure
        has to exist."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        unusable = {"missing": None, "empty": "", "blank": "   ",
                    "integer": 1, "boolean": True}
        for label, scope in unusable.items():
            spec = {"name": "probe", "agents": ["apex_chief_of_staff"],
                    "command": ["true"], "require_grant": True}
            if scope is not None:
                spec["grant_scope"] = scope
            with tempfile.TemporaryDirectory() as tmp:
                key, ledger = self._env(tmp)
                with mock.patch.object(launcher, "_load_mounts",
                                       lambda s=spec: {"probe": s}):
                    with self.subTest(scope=label):
                        with self.assertRaises(LaunchDenied) as caught:
                            issue_grant("probe", 30, key_path=key,
                                        out_dir=Path(tmp) / "grants",
                                        agent="apex_chief_of_staff",
                                        ledger=ledger)
                        self.assertIn("grant_scope", str(caught.exception))
                        events = [
                            json.loads(line)["event"] for line
                            in ledger.path.read_text(
                                encoding="utf-8").splitlines() if line.strip()
                        ]
                        self.assertEqual(events, ["grant_denied"])
                        self.assertFalse(
                            list((Path(tmp) / "grants").glob("*.json")),
                            "no grant file may exist after a refusal")

        # The real registry still mints, so this refuses an unusable
        # disclosure rather than refusing everything.
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            self.assertTrue(
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants",
                            agent="apex_chief_of_staff", ledger=ledger).exists())

    def test_a_malformed_brain_manifest_table_is_denied(self):
        """The corps roster got a shape check; the brain manifest did not.

        `agents = 1` is valid TOML and raised a bare AttributeError from the
        chained lookup. Both callers convert only ManifestUnavailable, so a
        partial manifest update produced a traceback and no audited denial --
        the same loud-but-unauditable failure, in the one loader that had not
        yet been given the treatment."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        corps = {
            "apex_roster": ["apex_probe"], "jeos_roster": [],
            "apex_brain_manifest": "brains/apex/agents.toml",
            "governance": {"designated_executor": "apex_chief_of_staff"},
            "lifecycle": {"deployed_stage": "shadow",
                          "connector_stages": ["active", "value-proven"]},
        }
        for label, agents in {"scalar": 1, "string": "x",
                              "list": ["a"], "boolean": True}.items():
            with mock.patch.object(
                    launcher, "_brain_manifest",
                    lambda path, a=agents: {"brain": "APEX", "agents": a}):
                with self.subTest(agents=label):
                    with self.assertRaises(ManifestUnavailable):
                        specialist_stage("apex_probe", corps=corps)

        # A well-formed table still resolves.
        with mock.patch.object(
                launcher, "_brain_manifest",
                lambda path: {"brain": "APEX",
                              "agents": {"apex_probe": {"status": "shadow"}}}):
            self.assertEqual(specialist_stage("apex_probe", corps=corps),
                             "shadow")

    def test_a_manifest_must_declare_the_brain_it_speaks_for(self):
        """Brain-locking is only real if the file is checked, not the path.

        The stage was read from whatever sat at the APEX path. A manifest
        swapped into the wrong path -- structurally valid, declaring the other
        brain, carrying an `active` entry for the requested identity -- then
        supplied authority for an agent it does not own, and the connector gate
        opened on the strength of the wrong brain's records. Each manifest
        names its own brain; take it at that word or refuse."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        corps = {
            "apex_roster": ["apex_probe"],
            "jeos_roster": ["jeos_probe"],
            "apex_brain_manifest": "brains/apex/agents.toml",
            "jeos_brain_manifest": "brains/jeos/agents.toml",
            "governance": {"designated_executor": "apex_chief_of_staff"},
            "lifecycle": {"deployed_stage": "shadow",
                          "connector_stages": ["active", "value-proven"]},
        }
        # Both directions, and the missing-declaration case.
        wrong = {
            "apex path declares JEOS":
                ("apex_probe", {"brain": "JEOS",
                                "agents": {"apex_probe": {"status": "active"}}}),
            "jeos path declares APEX":
                ("jeos_probe", {"brain": "APEX",
                                "agents": {"jeos_probe": {"status": "active"}}}),
            "no brain declared":
                ("apex_probe", {"agents": {"apex_probe": {"status": "active"}}}),
        }
        for label, (agent, manifest) in wrong.items():
            with mock.patch.object(launcher, "_brain_manifest",
                                   lambda path, m=manifest: m):
                with self.subTest(case=label):
                    with self.assertRaises(ManifestUnavailable) as caught:
                        specialist_stage(agent, corps=corps)
                    self.assertIn("brain", str(caught.exception))

        # The correctly-declared manifest still resolves, so this refuses a
        # mismatch rather than refusing everything.
        right = {"brain": "APEX", "agents": {"apex_probe": {"status": "shadow"}}}
        with mock.patch.object(launcher, "_brain_manifest", lambda path: right):
            self.assertEqual(specialist_stage("apex_probe", corps=corps),
                             "shadow")
        # And the real registry keeps working.
        self.assertEqual(specialist_stage("apex_systems_blacksmith"), "shadow")
        self.assertEqual(specialist_stage("jeos_life_architect"), "shadow")

    def test_a_scalar_allowlist_is_not_a_wildcard(self):
        """Python string membership made `"*" in "*"` true.

        `agents = "*"` is syntactically valid TOML and a plausible typo, and it
        was read as a WILDCARD: `issue_grant()` minted a null-identity grant
        and `authorize()` accepted it, bypassing the identity check and the
        lifecycle gate together. Any scalar does it -- a string contains every
        substring of itself -- so this is about the TYPE, not about `*`."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        malformed = {
            "scalar wildcard": "*",
            "scalar agent name": "apex_chief_of_staff",
            "integer": 1,
            "list holding a blank": ["", "apex_chief_of_staff"],
            "list holding a non-string": ["apex_chief_of_staff", 2],
        }
        for label, agents in malformed.items():
            spec = {"name": "probe", "agents": agents,
                    "command": ["true"], "require_grant": True}
            with tempfile.TemporaryDirectory() as tmp:
                key, ledger = self._env(tmp)
                with mock.patch.object(launcher, "_load_mounts",
                                       lambda spec=spec: {"probe": spec}):
                    with self.subTest(allowlist=label):
                        with self.assertRaises(LaunchDenied) as caught:
                            issue_grant("probe", 30, key_path=key,
                                        out_dir=Path(tmp) / "grants",
                                        ledger=ledger)
                        self.assertIn("allowlist", str(caught.exception))
                    events = [
                        json.loads(line)["event"] for line
                        in ledger.path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    self.assertEqual(events, ["grant_denied"])

        # A real wildcard mount must still launch without a grant, or this has
        # broken the one case the wildcard exists for.
        with tempfile.TemporaryDirectory() as tmp:
            _, ledger = self._env(tmp)
            authorize("governance", None, ledger=ledger)

    def test_a_structurally_invalid_registry_is_denied_and_audited(self):
        """Valid TOML is not the same as a usable registry.

        A roster mistyped as a scalar during a partial edit parses fine and
        then raised a bare TypeError out of `specialist_stage`. Both callers
        convert only `ManifestUnavailable`, so the CLI printed a traceback and
        wrote no denial event — the same loud-but-unauditable failure the
        loaders were fixed for, one layer up. Type errors are authorization
        failures here, not crashes."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        malformed = {
            "roster is a scalar": {"apex_roster": 1, "jeos_roster": []},
            "roster holds non-strings": {"apex_roster": ["a", 3],
                                         "jeos_roster": []},
            "roster is a table": {"apex_roster": {"a": 1}, "jeos_roster": []},
            "other roster malformed": {"apex_roster": [], "jeos_roster": 2},
        }
        for label, corps in malformed.items():
            with self.subTest(registry=label):
                with self.assertRaises(ManifestUnavailable):
                    specialist_stage("apex_systems_blacksmith", corps=corps)

        # And it must reach the ledger as a denial through the normal path,
        # which is the half a bare exception type does not prove.
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with mock.patch.object(
                    launcher, "_corps",
                    lambda: {"apex_roster": 1, "jeos_roster": []}):
                with self.assertRaises(LaunchDenied):
                    issue_grant("filesystem", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_systems_blacksmith", ledger=ledger)
            events = [json.loads(line)["event"] for line
                      in ledger.path.read_text(encoding="utf-8").splitlines()
                      if line.strip()]
            self.assertEqual(events, ["grant_denied"])
            self.assertEqual(ledger.verify(), [])

    def test_an_identity_in_both_rosters_is_refused(self):
        """Brain-locking means exactly one owner, so "both" is not a tie-break.

        Preferring APEX silently let the more permissive of two manifests
        decide: an APEX entry reading `active` beat an authoritative JEOS
        `restricted`, and the specialist could mint and consume a connector
        grant. That is the same widening the owning-brain lookup was introduced
        to stop, reached from the other side."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        corps = {
            "apex_roster": ["both_probe"],
            "jeos_roster": ["both_probe"],
            "apex_brain_manifest": "brains/apex/agents.toml",
            "jeos_brain_manifest": "brains/jeos/agents.toml",
            "governance": {"designated_executor": "apex_chief_of_staff"},
            "lifecycle": {"deployed_stage": "active",
                          "connector_stages": ["active", "value-proven"]},
        }

        # Whichever brain holds the permissive entry, the answer is refusal --
        # so this cannot pass by accident of which manifest is read first.
        for permissive in ("apex", "jeos"):
            def manifest(path, permissive=permissive):
                status = "active" if permissive in path else "restricted"
                return {"brain": "JEOS" if "jeos" in path else "APEX",
                        "agents": {"both_probe": {"status": status}}}
            with mock.patch.object(launcher, "_brain_manifest", manifest):
                with self.subTest(permissive_brain=permissive):
                    with self.assertRaises(ManifestUnavailable) as caught:
                        specialist_stage("both_probe", corps=corps)
                    self.assertIn("both", str(caught.exception))

        # A single-roster identity in the same registry still resolves, so the
        # check refuses ambiguity rather than refusing everything.
        single = {**corps, "jeos_roster": []}
        with mock.patch.object(
                launcher, "_brain_manifest",
                lambda path: {"brain": "APEX",
                              "agents": {"both_probe": {"status": "shadow"}}}):
            self.assertEqual(specialist_stage("both_probe", corps=single),
                             "shadow")

    def test_connector_eligibility_is_read_from_the_registry(self):
        """Governance rules belong in the configuration the runtime reads.

        `.github/instructions/agent-safety.instructions.md` is an active
        standard here, and this allowlist is a governance rule: hardcoding it
        meant the corps registry and its validators could accept a renamed or
        added stage while the launcher went on enforcing a stale set — denying
        the intended stage, or keeping authority for a removed one. It fails
        closed rather than falling back, because a silent default is the exact
        failure the key exists to remove."""
        import tomllib

        with (ROOT / "config" / "specialist_corps.toml").open("rb") as source:
            declared = tomllib.load(source)["lifecycle"]["connector_stages"]
        self.assertEqual(connector_stages(), frozenset(declared))

        # The registry decides, not the module: a registry naming a different
        # set must change the answer.
        renamed = {"lifecycle": {"connector_stages": ["in-service"]}}
        self.assertTrue(stage_permits_connector("in-service", corps=renamed))
        self.assertFalse(stage_permits_connector("active", corps=renamed))

        # Absent or malformed must deny, never default.
        for label, lifecycle in (
            ("missing", {}),
            ("empty", {"connector_stages": []}),
            ("not a list", {"connector_stages": "active"}),
            ("non-string member", {"connector_stages": ["active", 3]}),
            ("empty member", {"connector_stages": [""]}),
        ):
            with self.subTest(registry=label):
                with self.assertRaises(ManifestUnavailable):
                    connector_stages({"lifecycle": lifecycle})

    def test_only_the_named_executor_escapes_the_lifecycle_gate(self):
        """The exemption belongs to an identity, not to a gap in the registry.

        Keying it on "absent from the roster" meant a corps file that stays
        syntactically VALID while missing a roster array -- what a partial
        write leaves behind -- silently reclassified every allowlisted shadow
        specialist as the one identity that is not stage-gated. Nothing raised,
        because nothing was malformed, so the malformed-file denial added last
        round does not cover this at all. Fail closed on any identity whose
        lifecycle the registry cannot account for."""
        partial = {
            "jeos_roster": ["jeos_life_architect"],   # apex_roster lost
            "governance": {"designated_executor": "apex_chief_of_staff"},
            "lifecycle": {"deployed_stage": "shadow"},
        }
        for agent in ("apex_systems_blacksmith", "apex_delivery_commander"):
            with self.subTest(agent=agent):
                stage = specialist_stage(agent, corps=partial)
                self.assertFalse(
                    stage_permits_connector(stage),
                    "a specialist erased from the roster must not inherit the "
                    "designated executor's exemption",
                )
        # The named executor still is not stage-gated.
        self.assertIsNone(specialist_stage("apex_chief_of_staff", corps=partial))

        # And if the governance block itself is lost, nobody is exempt --
        # including the executor. An exemption that survives the disappearance
        # of the record naming it is not an exemption, it is a default.
        headless = {"jeos_roster": [], "lifecycle": {"deployed_stage": "shadow"}}
        for agent in ("apex_chief_of_staff", "apex_systems_blacksmith"):
            with self.subTest(agent=agent, registry="no governance block"):
                self.assertFalse(
                    stage_permits_connector(
                        specialist_stage(agent, corps=headless)))

        # The real registry must still resolve both kinds correctly.
        self.assertIsNone(specialist_stage("apex_chief_of_staff"))
        self.assertEqual(specialist_stage("apex_systems_blacksmith"), "shadow")

    def test_a_signed_grant_states_the_surface_it_authorizes(self):
        """A grant names a MOUNT, and a mount is an entire server.

        Nothing in the launcher mediates individual tool calls, so a grant
        minted for an Azure inventory task equally authorizes deletion, RBAC
        and credential tools. Leaving that to be inferred from `purpose` asks
        Joe to sign a blast radius he was never shown, so every grant-gated
        mount declares it, the mint path prints it, and the verifier fails a
        gated mount that does not."""
        import tomllib

        import scripts.trusted_launcher as launcher

        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]

        gated = [m for m in mounts if m.get("require_grant")]
        self.assertTrue(gated, "no grant-gated mounts found; test is vacuous")
        for mount in gated:
            with self.subTest(mount=mount["name"]):
                scope = mount.get("grant_scope", "")
                self.assertTrue(
                    scope.strip(),
                    "a grant-gated mount must declare what a grant authorizes")
                # It must describe the surface, not restate the purpose: the
                # point is the part a reader would otherwise assume away.
                self.assertIn("grant does not narrow", scope)
                # And the mint path must read the same string, not a summary.
                self.assertEqual(launcher._grant_scope(mount["name"]), scope)

        # An unknown mount yields "", which the verifier treats as a failure
        # rather than as a narrow scope.
        self.assertEqual(launcher._grant_scope("no-such-mount"), "")

    def test_stage_resolution_reads_only_the_owning_brains_manifest(self):
        """One brain's files must not decide the other brain's authority.

        Walking apex-then-jeos meant an unreadable APEX manifest raised before
        a JEOS specialist's own healthy record was ever consulted, so every
        JEOS specialist was denied by a fault in a brain it does not belong to.
        AGENTS.md separates the brains precisely to prevent that coupling, and
        Agent 007 is the only identity that crosses it. A read failure is still
        an authorization failure -- but only for the brain that owns the agent.
        """
        from unittest import mock

        import scripts.trusted_launcher as launcher

        corps = {
            "apex_roster": ["apex_probe"],
            "jeos_roster": ["jeos_probe"],
            "apex_brain_manifest": "brains/apex/agents.toml",
            "jeos_brain_manifest": "brains/jeos/agents.toml",
            "lifecycle": {"deployed_stage": "shadow"},
        }

        def one_brain_broken(broken: str):
            def load(path: str) -> dict:
                if broken in path:
                    raise ManifestUnavailable(f"{path}: gone")
                jeos = "jeos" in path
                agent = "jeos_probe" if jeos else "apex_probe"
                # The manifest must declare the brain it speaks for; a fixture
                # that omits it is refused, which is the point of that check.
                return {"brain": "JEOS" if jeos else "APEX",
                        "agents": {agent: {"status": "shadow"}}}
            return load

        # Either brain may be the broken one; the healthy brain must resolve
        # and the broken brain's own agent must still be denied.
        for broken, healthy_agent, denied_agent in (
            ("apex", "jeos_probe", "apex_probe"),
            ("jeos", "apex_probe", "jeos_probe"),
        ):
            with self.subTest(broken=broken):
                with mock.patch.object(launcher, "_brain_manifest",
                                       side_effect=one_brain_broken(broken)):
                    self.assertEqual(
                        specialist_stage(healthy_agent, corps=corps), "shadow",
                        "a healthy brain's records must be readable while the "
                        "other brain's manifest is broken",
                    )
                    with self.assertRaises(ManifestUnavailable):
                        specialist_stage(denied_agent, corps=corps)

    def test_an_unreadable_mount_registry_is_denied_and_audited(self):
        """The corps loader was fixed and the SECOND bare loader was not.

        `_load_mounts()` sits on the same authorization path and opened the
        file bare, so a missing or half-written `mcp_mounts.toml` still
        terminated the CLI with a traceback instead of its denial JSON and
        appended no denial event — the same loud-but-unauditable failure, one
        loader over. Both entry points are asserted, and both failure shapes:
        the file is absent, or present and unparseable."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        broken_registries = {
            "missing": None,
            "malformed": "[mounts\nname = ",
            "no mounts table": "unrelated = 1\n",
        }
        for label, contents in broken_registries.items():
            with tempfile.TemporaryDirectory() as tmp:
                key, ledger = self._env(tmp)
                registry = Path(tmp) / "mcp_mounts.toml"
                if contents is not None:
                    registry.write_text(contents, encoding="utf-8")
                with mock.patch.object(launcher, "MOUNTS", registry):
                    with self.subTest(registry=label, path="issue_grant"):
                        with self.assertRaises(LaunchDenied) as caught:
                            issue_grant("filesystem", 30, key_path=key,
                                        out_dir=Path(tmp) / "grants",
                                        agent="apex_chief_of_staff",
                                        ledger=ledger)
                        self.assertIn("mount registry", str(caught.exception))
                    with self.subTest(registry=label, path="authorize"):
                        with self.assertRaises(LaunchDenied):
                            authorize("governance", None, ledger=ledger)

                events = [
                    json.loads(line)["event"] for line
                    in ledger.path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                self.assertEqual(events, ["grant_denied", "launch_denied"],
                                 f"{label}: {events}")
                self.assertEqual(ledger.verify(), [])

    def test_an_unreadable_corps_registry_is_denied_and_audited(self):
        """A failure the module promises to record must not escape as a
        traceback.

        `_corps()` opened the registry bare, so a missing or half-written
        `specialist_corps.toml` terminated the CLI with OSError/TOMLDecodeError
        instead of its denial JSON -- and skipped the ledger append every
        refusal is supposed to leave. That failed loudly but not auditably,
        which is the one combination an audit trail cannot survive."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            missing = Path(tmp) / "absent_corps.toml"
            with mock.patch.object(launcher, "CORPS", missing):
                with self.assertRaises(LaunchDenied) as caught:
                    issue_grant("filesystem", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_systems_blacksmith", ledger=ledger)
            self.assertIn("cannot resolve the lifecycle stage",
                          str(caught.exception))
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([e["event"] for e in entries], ["grant_denied"])
            self.assertEqual(ledger.verify(), [])

            # Half-written TOML is the likelier failure and must behave the same.
            broken = Path(tmp) / "broken_corps.toml"
            broken.write_text("[lifecycle\ndeployed_stage = ", encoding="utf-8")
            with mock.patch.object(launcher, "CORPS", broken):
                with self.assertRaises(LaunchDenied):
                    issue_grant("filesystem", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_systems_blacksmith", ledger=ledger)
            self.assertEqual(ledger.verify(), [])

    def test_grant_time_denials_reach_the_ledger(self):
        """The module promises every denial is recorded. Grant-time refusals were
        raised directly, so an attempt to mint authority for a shadow specialist
        left no hash-chained evidence -- the very event an audit should surface."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants",
                            agent="apex_systems_blacksmith", ledger=ledger)
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            denials = [e for e in entries if e["event"] == "grant_denied"]
            self.assertTrue(denials, entries)
            self.assertEqual(denials[-1]["detail"]["agent"],
                             "apex_systems_blacksmith")
            self.assertEqual(denials[-1]["detail"]["mount"], "terraform")
            self.assertEqual(ledger.verify(), [])

    def test_caller_cannot_claim_an_identity_it_was_not_granted(self):
        """The whole point of signing the identity. An earlier version read it
        from a CLI flag, so any holder of a valid grant could assert Agent 007."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            with self.assertRaises(LaunchDenied) as caught:
                authorize("terraform", grant, key_path=key, ledger=ledger,
                          agent="apex_systems_blacksmith")
            self.assertIn("grant authorizes", str(caught.exception))

    def test_editing_the_identity_in_a_grant_breaks_its_signature(self):
        """The agent field is inside the HMAC payload, so tampering is caught by
        the signature check rather than by trusting the file."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("azure", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            body = json.loads(grant.read_text())
            body["agent"] = "apex_systems_blacksmith"
            tampered = Path(tmp) / "tampered.json"
            tampered.write_text(json.dumps(body))
            with self.assertRaisesRegex(LaunchDenied, "signature invalid"):
                authorize("azure", tampered, key_path=key, ledger=ledger)

    def test_denied_identity_is_recorded_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("azure", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            with self.assertRaises(LaunchDenied):
                authorize("azure", grant, key_path=key, ledger=ledger,
                          agent="jeos_energy_director")
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            denials = [e for e in entries if e["event"] == "launch_denied"]
            self.assertTrue(denials)
            self.assertEqual(denials[-1]["detail"]["agent"],
                             "jeos_energy_director")

    def test_signed_identity_authorizes_and_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff")
            spec = authorize("terraform", grant, key_path=key, ledger=ledger)
            self.assertIn("hashicorp/terraform-mcp-server", " ".join(spec["command"]))
            entries = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            granted = [e for e in entries if e["event"] == "launch_authorized"]
            self.assertEqual(granted[-1]["detail"]["agent"],
                             "apex_chief_of_staff")

    def test_agent_scoped_mounts_all_require_a_grant(self):
        """A non-wildcard mount that skipped grants would fall back to an
        unauthenticated caller-supplied identity. This invariant keeps the
        signed path the only path for every agent-scoped mount."""
        import tomllib
        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            for mount in tomllib.load(source)["mounts"]:
                if "*" in mount.get("agents", []):
                    continue
                with self.subTest(mount=mount["name"]):
                    self.assertTrue(
                        mount.get("require_grant"),
                        f"{mount['name']} is agent-scoped but grant-free, so its "
                        "identity would be unauthenticated",
                    )

    def test_an_agent_scoped_mount_without_grant_gating_is_denied(self):
        """The invariant above is enforced at RUNTIME, not only over the
        committed file.

        `test_agent_scoped_mounts_all_require_a_grant` proves today's registry
        is consistent. It cannot speak for a registry edited between releases,
        half-applied, or merged from two branches -- and on that path the old
        code resolved the ambiguity the wrong way: it accepted the caller's own
        --agent, filed it as `agent_authenticated: false`, and started a
        write-capable mount with nothing Joe had signed. An ambiguous registry
        is an authorization failure."""
        from unittest import mock

        import scripts.trusted_launcher as launcher

        for label, spec in {
            "require_grant absent": {
                "name": "probe", "agents": ["apex_chief_of_staff"],
                "command": ["true"], "write": True},
            "require_grant false": {
                "name": "probe", "agents": ["apex_chief_of_staff"],
                "command": ["true"], "require_grant": False},
        }.items():
            with tempfile.TemporaryDirectory() as tmp:
                key, ledger = self._env(tmp)
                with mock.patch.object(launcher, "_load_mounts",
                                       lambda s=spec: {"probe": s}), \
                        mock.patch.object(launcher, "specialist_stage",
                                          lambda agent, corps=None: "active"):
                    with self.subTest(registry=label):
                        with self.assertRaises(LaunchDenied) as caught:
                            authorize("probe", None, key_path=key,
                                      ledger=ledger,
                                      agent="apex_chief_of_staff")
                        self.assertIn("agent-scoped", str(caught.exception))
                        self.assertIn("grant", str(caught.exception))

    def test_wildcard_mount_still_launches_without_an_agent(self):
        """governance is agents = ["*"]; requiring an identity there would break
        the read-only path that needs no grant."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            spec = authorize("governance", None, key_path=key, ledger=ledger)
            self.assertTrue(spec["command"])

    def test_write_capable_mount_is_denied_without_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaisesRegex(LaunchDenied, "requires a signed"):
                authorize("civil3d", None, key, ledger)
            events = [json.loads(l)["event"]
                      for l in ledger.path.read_text().splitlines()]
            self.assertEqual(events, ["launch_denied"])

    def test_unregistered_mount_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaisesRegex(LaunchDenied, "not registered"):
                authorize("shadow_it_server", None, key, ledger)

    def test_tampered_expired_and_reused_grants_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant_path = issue_grant("civil3d", 30, key, Path(tmp), now=1_000_000,
                                     agent="apex_chief_of_staff")

            tampered = json.loads(grant_path.read_text())
            tampered["mount"] = "github"
            bad = Path(tmp) / "tampered.json"
            bad.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(LaunchDenied, "signature invalid"):
                authorize("github", bad, key, ledger, now=1_000_060)

            with self.assertRaisesRegex(LaunchDenied, "expired"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_000 + 31 * 60)

            # civil3d is agent-scoped, so the allowlist check now applies to it
            # too: an identity is required even with a valid grant.
            spec = authorize("civil3d", grant_path, key, ledger, now=1_000_060)
            self.assertEqual(spec["name"], "civil3d")
            with self.assertRaisesRegex(LaunchDenied, "already consumed"):
                authorize("civil3d", grant_path, key, ledger, now=1_000_120)
            self.assertEqual(ledger.verify(), [])

    def test_grant_for_wrong_mount_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant_path = issue_grant("filesystem", 30, key, Path(tmp), now=2_000_000,
                                     agent="apex_chief_of_staff")
            with self.assertRaisesRegex(LaunchDenied, "is for 'filesystem'"):
                authorize("civil3d", grant_path, key, ledger, now=2_000_060)

    def test_read_only_governance_mount_needs_no_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            spec = authorize("governance", None, key, ledger)
            self.assertEqual(spec["name"], "governance")


    def test_post_signature_denials_name_the_signed_identity(self):
        """--agent is optional at launch. Once the signature verifies, the
        signed identity is known, so an expired or already-consumed grant must
        be attributed to it -- otherwise the audit cannot say which authorized
        identity presented a stale grant."""
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            grant = issue_grant("terraform", 30, key_path=key,
                                out_dir=Path(tmp) / "grants",
                                agent="apex_chief_of_staff", ledger=ledger)

            # Expired: launched without --agent, so only the signature knows.
            with self.assertRaises(LaunchDenied):
                authorize("terraform", grant, key_path=key, ledger=ledger,
                          now=time.time() + 10_000)
            # Consumed: authorize once, then replay, again without --agent.
            authorize("terraform", grant, key_path=key, ledger=ledger)
            with self.assertRaises(LaunchDenied):
                authorize("terraform", grant, key_path=key, ledger=ledger)

            denials = [
                json.loads(line)
                for line in ledger.path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line)["event"] == "launch_denied"
            ]
            reasons = {d["detail"]["reason"] for d in denials}
            self.assertTrue(any("expired" in r for r in reasons), reasons)
            self.assertTrue(any("consumed" in r for r in reasons), reasons)
            for denial in denials:
                with self.subTest(reason=denial["detail"]["reason"]):
                    self.assertEqual(
                        denial["detail"].get("agent"), "apex_chief_of_staff")
                    self.assertEqual(
                        denial["detail"].get("agent_source"), "signed-grant")

    def test_denials_never_touch_the_machine_local_ledger(self):
        """Synthetic denials must not contaminate the evidence they validate.
        Exercises the denial paths with an explicit temporary ledger and asserts
        the real audit/launcher.jsonl is byte-for-byte unchanged -- a missing
        `ledger` argument silently falls back to it."""
        from scripts.trusted_launcher import DEFAULT_LEDGER

        before = (DEFAULT_LEDGER.read_bytes()
                  if DEFAULT_LEDGER.exists() else None)
        with tempfile.TemporaryDirectory() as tmp:
            key, ledger = self._env(tmp)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants", ledger=ledger)
            with self.assertRaises(LaunchDenied):
                issue_grant("terraform", 30, key_path=key,
                            out_dir=Path(tmp) / "grants",
                            agent="jeos_life_architect", ledger=ledger)
            with self.assertRaises(LaunchDenied):
                authorize("terraform", None, key_path=key, ledger=ledger)
            self.assertTrue(ledger.path.exists(), "temp ledger took the writes")
        after = (DEFAULT_LEDGER.read_bytes()
                 if DEFAULT_LEDGER.exists() else None)
        self.assertEqual(before, after,
                         "a denial path wrote to the machine-local ledger")


    def test_a_mount_sees_only_its_declared_credentials(self):
        """The launcher passed a copy of the whole process environment, so
        starting the Azure mount handed a freshly downloaded npm package every
        other credential on the machine. A mount now gets the baseline plus
        exactly what it declares."""
        import os

        planted = {
            "TFE" + "_TOKEN": "tfe-value",
            "GITHUB" + "_PERSONAL_ACCESS_TOKEN": "gh-value",
            "AZURE" + "_CLIENT_SECRET": "az-value",
            "PATH": os.environ.get("PATH", "/usr/bin"),
        }
        original = {k: os.environ.get(k) for k in planted}
        try:
            os.environ.update(planted)
            azure = mount_env({"env": ["AZURE" + "_CLIENT_SECRET"]})
            self.assertIn("AZURE" + "_CLIENT_SECRET", azure)
            self.assertNotIn("TFE" + "_TOKEN", azure)
            self.assertNotIn("GITHUB" + "_PERSONAL_ACCESS_TOKEN", azure)
            self.assertIn("PATH", azure)

            # A mount declaring nothing gets no credentials at all.
            bare = mount_env({})
            self.assertTrue(set(bare) <= set(BASELINE_ENV))
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_every_credentialed_mount_declares_its_env(self):
        """A mount whose activation names a credential must declare it, or the
        launcher will start it without the variable it needs -- and a mount that
        declares extras would widen its own blast radius silently."""
        import re
        import tomllib

        with (Path(__file__).resolve().parents[1]
              / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        for mount in mounts:
            named = set(re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b",
                                   " ".join(mount["command"])))
            declared = set(mount.get("env", []))
            with self.subTest(mount=mount["name"]):
                self.assertTrue(
                    named <= declared,
                    f"{mount['name']} forwards {sorted(named - declared)} in its "
                    f"command but does not declare them in env",
                )


if __name__ == "__main__":
    unittest.main()
