"""Native runtime layer tests: pydantic packet models, Claude-native governed
dispatch, and the governance MCP server.

The Claude dispatch handler is duck-typed and stdlib-testable; pydantic and
MCP tests skip cleanly when those packages are absent so stdlib CI stays
green.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

from scripts.agent_runtime import AuditLedger, load_roster
from scripts.claude_runtime import (
    AUDIT_TOOL,
    DELEGATE_TOOL,
    RETURN_TOOL,
    governed_tool_definitions,
    handle_tool_use,
)
from scripts.packet_guard import PacketGuard
from tests.test_agent_runtime import _v21_pair

ROOT = Path(__file__).resolve().parents[1]


def _available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _block(name: str, payload: dict) -> types.SimpleNamespace:
    return types.SimpleNamespace(type="tool_use", id="toolu_test", name=name, input=payload)


class ClaudeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = PacketGuard(ROOT)
        cls.roster = load_roster(ROOT)
        cls.delegation, cls.handoff_return = _v21_pair()

    def test_tool_definitions_cover_dispatch_return_and_audit(self):
        tools = governed_tool_definitions(self.roster)
        names = {tool["name"] for tool in tools}
        self.assertEqual(names, {DELEGATE_TOOL, RETURN_TOOL, AUDIT_TOOL})
        delegate = next(tool for tool in tools if tool["name"] == DELEGATE_TOOL)
        targets = delegate["input_schema"]["properties"]["target"]["enum"]
        self.assertEqual(len(targets), 10)
        self.assertNotIn("apex_chief_of_staff", targets)

    def test_delegate_tool_admits_valid_and_rejects_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            admitted = handle_tool_use(
                _block(DELEGATE_TOOL, {
                    "target": "apex_war_architect",
                    "packet_json": json.dumps(self.delegation),
                }),
                self.roster, self.guard, ledger,
            )
            self.assertFalse(admitted["is_error"])
            self.assertIn('"admitted": true', admitted["content"])

            legacy = deepcopy(self.delegation)
            legacy["schema_version"] = "2.0"
            rejected = handle_tool_use(
                _block(DELEGATE_TOOL, {
                    "target": "apex_war_architect",
                    "packet_json": json.dumps(legacy),
                }),
                self.roster, self.guard, ledger,
            )
            self.assertTrue(rejected["is_error"])
            self.assertIn("legacy", rejected["content"])
            self.assertEqual(ledger.verify(), [])

    def test_return_tool_flags_unevidenced_completion(self):
        broken = deepcopy(self.handoff_return)
        broken["artifacts"][0]["records"][0]["source_refs"] = []
        outcome = handle_tool_use(
            _block(RETURN_TOOL, {
                "handoff_json": json.dumps(broken),
                "delegation_json": json.dumps(self.delegation),
            }),
            self.roster, self.guard,
        )
        self.assertTrue(outcome["is_error"])
        self.assertIn("source evidence", outcome["content"])

    def test_audit_tool_and_unknown_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / "audit.jsonl")
            ledger.append("probe", {"n": 1})
            intact = handle_tool_use(
                _block(AUDIT_TOOL, {}), self.roster, self.guard, ledger
            )
            self.assertFalse(intact["is_error"])
        unknown = handle_tool_use(
            _block("no_such_tool", {}), self.roster, self.guard
        )
        self.assertTrue(unknown["is_error"])


@unittest.skipUnless(_available("pydantic"), "pydantic not installed")
class PacketModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delegation, cls.handoff_return = _v21_pair()

    def test_models_accept_canonical_fixture_and_run_guard(self):
        from scripts.packet_models import DelegationPacket

        model = DelegationPacket.model_validate(self.delegation)
        self.assertEqual(model.agent, "apex_war_architect")
        self.assertEqual(model.validate_with_guard(), [])

    def test_models_reject_missing_required_and_extra_fields(self):
        from pydantic import ValidationError

        from scripts.packet_models import DelegationPacket

        missing = deepcopy(self.delegation)
        del missing["delegation_id"]
        with self.assertRaises(ValidationError):
            DelegationPacket.model_validate(missing)

        extra = deepcopy(self.delegation)
        extra["smuggled_field"] = "x"
        with self.assertRaises(ValidationError):
            DelegationPacket.model_validate(extra)

    def test_parse_packet_maps_schema_names(self):
        from scripts.packet_models import parse_packet

        model = parse_packet("handoff_packet.schema.json", self.handoff_return)
        self.assertEqual(model.__schema_name__, "handoff_packet.schema.json")
        with self.assertRaises(KeyError):
            parse_packet("unknown.schema.json", {})


@unittest.skipUnless(_available("mcp"), "mcp SDK not installed")
class GovernanceMcpServerTests(unittest.TestCase):
    def test_server_exposes_exactly_the_governed_tools(self):
        import asyncio

        from scripts.governance_mcp_server import build_server

        with tempfile.TemporaryDirectory() as tmp:
            server = build_server(ROOT, Path(tmp) / "audit.jsonl")
            tools = asyncio.run(server.list_tools())
            names = {tool.name for tool in tools}
            self.assertEqual(
                names,
                {
                    "validate_packet",
                    "admit_delegation_packet",
                    "validate_handoff_return",
                    "verify_audit_ledger",
                    "list_registered_roster",
                },
            )

    def test_tool_functions_enforce_fail_closed_admission(self):
        from scripts.governance_mcp_server import _tool_functions

        delegation, _ = _v21_pair()
        with tempfile.TemporaryDirectory() as tmp:
            tools = _tool_functions(
                PacketGuard(ROOT), load_roster(ROOT),
                AuditLedger(Path(tmp) / "audit.jsonl"),
            )
            admitted = json.loads(
                tools["admit_delegation_packet"](
                    "apex_war_architect", json.dumps(delegation)
                )
            )
            self.assertTrue(admitted["admitted"])

            legacy = deepcopy(delegation)
            legacy["schema_version"] = "2.0"
            rejected = json.loads(
                tools["admit_delegation_packet"](
                    "apex_war_architect", json.dumps(legacy)
                )
            )
            self.assertFalse(rejected["admitted"])
            self.assertTrue(any("legacy" in item for item in rejected["errors"]))

            roster_listing = json.loads(tools["list_registered_roster"]())
            self.assertEqual(len(roster_listing), 11)


if __name__ == "__main__":
    unittest.main()
