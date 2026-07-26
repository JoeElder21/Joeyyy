from pathlib import Path
import subprocess
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EcosystemRuntimeTests(unittest.TestCase):
    def test_all_named_integrations_are_tracked_and_fail_closed(self):
        with (ROOT / "config" / "ecosystem_runtime.toml").open("rb") as source:
            config = tomllib.load(source)
        records = config["integrations"]
        self.assertEqual(len(records), 15)
        self.assertEqual(config["connector_boundary"], "mcp_packet_only")
        self.assertEqual({record["id"] for record in records}, {
            "microsoft-autogen", "mcp-python-sdk", "openai-agents-python",
            "anthropic-sdk-python", "phoenix", "langfuse", "opentelemetry-python",
            "taskipy", "airflow", "celery", "logseq", "twenty", "plane",
            "aps-sdk-node", "mcp-servers",
        })
        self.assertTrue(all(record["stage"] != "active" for record in records))

    def test_evidence_packet_is_generated_and_current(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_drive_evidence_packet.py", "--check"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (ROOT / "docs" / "DRIVE_ECOSYSTEM_EVIDENCE_PACKET.md").read_text(encoding="utf-8")
        self.assertIn("microsoft/autogen", text)
        self.assertIn("modelcontextprotocol/servers", text)
        self.assertIn("has not been uploaded", text)


if __name__ == "__main__":
    unittest.main()
