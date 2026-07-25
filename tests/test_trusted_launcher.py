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
    BASELINE_ENV, CONNECTOR_STAGES, LaunchDenied, ManifestUnavailable,
    authorize, issue_grant, mount_env, specialist_stage,
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
                    stage_permits_connector(stage), stage in CONNECTOR_STAGES)

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
        for permissive in sorted(CONNECTOR_STAGES):
            corps = {**base, "lifecycle": {"deployed_stage": permissive}}
            with self.subTest(snapshot=permissive, shape="no manifest path"):
                self.assertFalse(stage_permits_connector(
                    specialist_stage("apex_probe", corps=corps)))
            with_path = {**corps, "apex_brain_manifest": "brains/apex/agents.toml"}
            with mock.patch.object(launcher, "_brain_manifest",
                                   lambda path: {"agents": {}}):
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
                agent = "jeos_probe" if "jeos" in path else "apex_probe"
                return {"agents": {agent: {"status": "shadow"}}}
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
