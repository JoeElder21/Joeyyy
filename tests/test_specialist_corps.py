from pathlib import Path
import json
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".codex" / "agents"
MANIFEST_PATH = ROOT / "config" / "specialist_corps.toml"
REGISTRY_PATH = ROOT / "docs" / "AGENT_REGISTRY.md"
PROTOCOL_PATH = ROOT / "docs" / "SPECIALIST_CORPS_PROTOCOL.md"
COMMUNITY_PATH = ROOT / "docs" / "AGENT_COMMUNITY_PROTOCOL.md"
AUDIT_PATH = ROOT / "docs" / "MENTAL_LOAD_AUDIT_2026-07-23.md"
ACCEPTANCE_PATH = ROOT / "docs" / "SPECIALIST_ACCEPTANCE_TESTS.md"

APEX = [
    "apex_grademaster",
    "apex_countwise",
    "apex_signalkeeper",
    "apex_ascent_90",
    "apex_forgewright",
]
JEOS = [
    "jeos_examiner",
    "jeos_tempo",
    "jeos_shepherd",
    "jeos_hearthkeeper",
    "jeos_lifewright",
]


class SpecialistCorpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with MANIFEST_PATH.open("rb") as source:
            cls.manifest = tomllib.load(source)
        cls.agents = {}
        for name in APEX + JEOS:
            with (AGENT_DIR / f"{name}.toml").open("rb") as source:
                cls.agents[name] = tomllib.load(source)
        cls.registry = REGISTRY_PATH.read_text(encoding="utf-8")
        cls.protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
        cls.community = COMMUNITY_PATH.read_text(encoding="utf-8")

    def test_exactly_five_unique_agents_per_brain(self):
        self.assertEqual(self.manifest["apex_roster"], APEX)
        self.assertEqual(self.manifest["jeos_roster"], JEOS)
        self.assertEqual(len(set(APEX + JEOS)), 10)

    def test_every_specialist_has_required_native_fields(self):
        for expected_name, agent in self.agents.items():
            with self.subTest(agent=expected_name):
                self.assertEqual(agent["name"], expected_name)
                self.assertTrue(agent["description"].strip())
                self.assertTrue(agent["developer_instructions"].strip())
                self.assertEqual(agent["sandbox_mode"], "read-only")

    def test_apex_agents_are_brain_locked(self):
        for name in APEX:
            instructions = self.agents[name]["developer_instructions"]
            with self.subTest(agent=name):
                self.assertIn("Owner brain: APEX ONLY", instructions)
                self.assertIn("Only Agent 007 may cross the brain boundary", instructions)
                self.assertRegex(instructions, r"Never (?:search for, )?read.*JEOS|Never search for, read.*JEOS")
                self.assertIn("All communication stays inside APEX", instructions)

    def test_jeos_agents_are_brain_locked(self):
        for name in JEOS:
            instructions = self.agents[name]["developer_instructions"]
            with self.subTest(agent=name):
                self.assertIn("Owner brain: JEOS ONLY", instructions)
                self.assertIn("Only Agent 007 may cross the brain boundary", instructions)
                self.assertRegex(instructions, r"Never (?:search for, )?read.*APEX|Never search for, read.*APEX")
                self.assertIn("All communication stays inside JEOS", instructions)

    def test_agent_007_is_sole_cross_brain_executor(self):
        governance = self.manifest["governance"]
        self.assertEqual(governance["sole_cross_brain_agent"], "apex_chief_of_staff")
        self.assertEqual(governance["designated_executor"], "apex_chief_of_staff")
        self.assertFalse(governance["continuous_runtime_claim"])

    def test_toolsmiths_are_separate_and_forbid_collaboration(self):
        apex = self.agents["apex_forgewright"]["developer_instructions"]
        jeos = self.agents["jeos_lifewright"]["developer_instructions"]
        self.assertIn("Never collaborate with LIFEWRIGHT", apex)
        self.assertIn("Never collaborate with FORGEWRIGHT", jeos)
        self.assertNotEqual(
            self.agents["apex_forgewright"]["name"],
            self.agents["jeos_lifewright"]["name"],
        )

    def test_rainmaker_is_dormant_not_core(self):
        bench = self.manifest["bench"]["apex_rainmaker"]
        self.assertEqual(bench["status"], "dormant")
        self.assertNotIn("apex_rainmaker", APEX)
        self.assertEqual(bench["native_file"], "")

    def test_manifest_files_and_brains_match(self):
        for name in APEX + JEOS:
            entry = self.manifest["agents"][name]
            expected_brain = "APEX" if name in APEX else "JEOS"
            with self.subTest(agent=name):
                self.assertEqual(entry["brain"], expected_brain)
                self.assertEqual(entry["status"], "shadow")
                self.assertEqual(entry["file"], f".codex/agents/{name}.toml")
                self.assertTrue((ROOT / entry["file"]).is_file())

    def test_challenge_pairs_never_mix_brains(self):
        for pair in self.manifest["challenge_pairs"]:
            allowed = set(APEX if pair["brain"] == "APEX" else JEOS)
            with self.subTest(pair=pair["agents"]):
                self.assertTrue(set(pair["agents"]).issubset(allowed))

    def test_schemas_parse_and_define_required_fields(self):
        expected = {
            "delegation_packet.schema.json": {"mission_id", "agent", "owner_brain", "mission"},
            "handoff_packet.schema.json": {"mission_id", "agent", "owner_brain", "status"},
            "roundtable_memo.schema.json": {"memo_id", "owner_brain", "from_agent", "to_agents"},
        }
        for filename, required in expected.items():
            with (ROOT / "schemas" / filename).open(encoding="utf-8") as source:
                schema = json.load(source)
            with self.subTest(schema=filename):
                self.assertEqual(schema["type"], "object")
                self.assertTrue(required.issubset(set(schema["required"])))
                self.assertFalse(schema["additionalProperties"])

    def test_registry_and_protocol_name_every_agent(self):
        for name in APEX + JEOS:
            with self.subTest(agent=name):
                self.assertIn(name, self.registry)
        for alias in [
            "GRADEMASTER",
            "COUNTWISE",
            "SIGNALKEEPER",
            "ASCENT-90",
            "FORGEWRIGHT",
            "EXAMINER",
            "TEMPO",
            "SHEPHERD",
            "HEARTHKEEPER",
            "LIFEWRIGHT",
        ]:
            with self.subTest(alias=alias):
                self.assertIn(alias, self.protocol)

    def test_agent_007_knows_rosters_and_packet_contracts(self):
        with (AGENT_DIR / "apex_chief_of_staff.toml").open("rb") as source:
            instructions = tomllib.load(source)["developer_instructions"]
        for phrase in [
            "<specialist_corps>",
            "config/specialist_corps.toml",
            "apex_grademaster",
            "jeos_examiner",
            "schemas/delegation_packet.schema.json",
            "schemas/handoff_packet.schema.json",
            "sole cross-brain agent",
            "continuously operating",
        ]:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, instructions)

    def test_lifecycle_is_honest(self):
        lifecycle = self.manifest["lifecycle"]
        self.assertEqual(lifecycle["deployed_stage"], "shadow")
        self.assertIn("controlled real mission", lifecycle["active_gate"])
        self.assertIn("Observed net value", lifecycle["value_gate"])
        self.assertIn("shadow", self.registry)
        self.assertIn("controlled real mission", self.protocol)

    def test_public_artifacts_have_no_obvious_private_source_leaks(self):
        paths = [
            *AGENT_DIR.glob("apex_*.toml"),
            *AGENT_DIR.glob("jeos_*.toml"),
            MANIFEST_PATH,
            REGISTRY_PATH,
            PROTOCOL_PATH,
            COMMUNITY_PATH,
            AUDIT_PATH,
            ACCEPTANCE_PATH,
            ROOT / "templates" / "specialist-handoff.md",
        ]
        prohibited = {
            "trigger identifier": re.compile(r"\btrig_[A-Za-z0-9_-]+\b", re.IGNORECASE),
            "personal email": re.compile(r"\b[A-Z0-9._%+-]+@(gmail|yahoo|outlook)\.com\b", re.IGNORECASE),
            "raw Drive link": re.compile(r"https://(?:drive|docs)\.google\.com/", re.IGNORECASE),
            "street address": re.compile(
                r"\b\d{2,6}\s+[A-Za-z0-9.' -]+\s(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Boulevard|Blvd)\b",
                re.IGNORECASE,
            ),
            "exact currency amount": re.compile(r"[$]\s?\d[\d,]*(?:\.\d{2})?"),
        }
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for label, pattern in prohibited.items():
                with self.subTest(path=path, check=label):
                    self.assertIsNone(pattern.search(text))

    def test_required_operating_documents_exist(self):
        for path in [PROTOCOL_PATH, AUDIT_PATH, ACCEPTANCE_PATH]:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 500)


if __name__ == "__main__":
    unittest.main()
