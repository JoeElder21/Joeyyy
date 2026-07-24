"""Preflight a same-brain AutoGen challenge pair without granting tool access.

This is deliberately a *plan* runner, rather than a model runner.  A plan can
be created in CI with synthetic packet references; execution requires a
separately configured AutoGen model client and remains unavailable until the
specialists clear their active-stage acceptance gates.  Keeping that boundary
in code prevents a framework install from silently becoming connector access.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "specialist_corps.toml"


class ChallengePlanError(ValueError):
    """Raised when a requested AutoGen challenge violates the corps contract."""


def _manifest() -> dict[str, Any]:
    with MANIFEST.open("rb") as source:
        return tomllib.load(source)


def _challenge_pairs(manifest: dict[str, Any]) -> set[tuple[str, ...]]:
    return {tuple(item["agents"]) for item in manifest["challenge_pairs"]}


def build_plan(brain: str, agents: list[str], mission_id: str, evidence_refs: list[str]) -> dict[str, Any]:
    """Return a fail-closed AutoGen execution plan from registered metadata."""
    manifest = _manifest()
    if brain not in {"APEX", "JEOS"}:
        raise ChallengePlanError("brain must be APEX or JEOS")
    if len(agents) < 2 or len(set(agents)) != len(agents):
        raise ChallengePlanError("a challenge needs two or more distinct specialists")
    if not mission_id or not evidence_refs:
        raise ChallengePlanError("mission_id and one or more packet evidence references are required")

    roster = set(manifest[f"{brain.lower()}_roster"])
    unknown_or_cross_brain = [agent for agent in agents if agent not in roster]
    if unknown_or_cross_brain:
        raise ChallengePlanError(
            f"all specialists must be registered in {brain}: {unknown_or_cross_brain}"
        )
    if tuple(agents) not in _challenge_pairs(manifest):
        raise ChallengePlanError("agent order is not a registered same-brain challenge pair")
    if any(manifest["agents"][agent]["status"] != "shadow" for agent in agents):
        raise ChallengePlanError("this preflight supports shadow-stage specialists only")

    return {
        "runtime": "microsoft/autogen",
        "runtime_distribution": "autogen-agentchat",
        "execution_state": "preflight_only",
        "mission_id": mission_id,
        "owner_brain": brain,
        "agents": agents,
        "evidence_refs": evidence_refs,
        "connector_policy": "packet_only_no_direct_connectors",
        "tool_access": "none",
        "writer": "apex_chief_of_staff",
        "external_actions_performed": False,
        "required_before_execution": [
            "schema-valid v2.1 delegation packet per specialist",
            "runtime model client configured outside this public repository",
            "controlled real-mission and connector-isolation acceptance evidence",
            "Agent 007 integration of schema-valid handoff packets",
        ],
        "rollback": "Discard this plan; no model, connector, or mutation was invoked.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain", required=True, choices=("APEX", "JEOS"))
    parser.add_argument("--agents", required=True, nargs="+", help="Registered pair in manifest order")
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--evidence-ref", required=True, action="append", dest="evidence_refs")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.brain, args.agents, args.mission_id, args.evidence_refs)
    except ChallengePlanError as exc:
        print(f"challenge preflight rejected: {exc}", file=sys.stderr)
        return 2
    try:
        plan["autogen_version"] = importlib.metadata.version("autogen-agentchat")
    except importlib.metadata.PackageNotFoundError:
        plan["autogen_version"] = None
        plan["runtime_availability"] = "not installed in this environment"
    else:
        plan["runtime_availability"] = "installed; execution remains gated"
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
