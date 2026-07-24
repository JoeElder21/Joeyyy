"""Cadence routes as Prefect flows.

Incorporates PrefectHQ/prefect (pinned in requirements/runtime-orchestration.txt)
as the scheduler for the brain manifests' [[cadence_routes]]: each route
becomes a flow whose tasks run in manifest order with the integrator last,
every step audit-logged. Flows run locally today (offline, injected step
executor); attaching them to a Prefect work pool with the cron schedules
below is the activation step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from scripts.agent_runtime import AuditLedger
from scripts.orchestration_graphs import load_manifest

ROOT = Path(__file__).resolve().parents[1]

# Cadence -> cron, America/New_York. Daily runs precede Joe's morning brief;
# weekly aligns with the Friday review pair; monthly on the first weekday.
CADENCE_SCHEDULES = {
    "daily": "0 7 * * 1-5",
    "weekly": "0 15 * * 5",
    "monthly": "0 8 1 * *",
}

try:  # degrade cleanly when the runtime stack is not installed
    from prefect import flow, task

    PREFECT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in stdlib CI
    PREFECT_AVAILABLE = False


if PREFECT_AVAILABLE:

    def build_cadence_flow(
        brain: str,
        cadence: str,
        step_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
        ledger: AuditLedger | None = None,
        root: Path = ROOT,
    ):
        """One cadence route as a Prefect flow (manifest order, integrator last)."""
        manifest = load_manifest(brain, root)
        route = next(
            item for item in manifest["cadence_routes"] if item["cadence"] == cadence
        )
        order = list(route["order"]) + [route["integrator"]]

        @task(name=f"{brain}-{cadence}-step")
        def run_step(agent: str, state: dict[str, Any]) -> dict[str, Any]:
            record = step_fn(agent, state)
            if ledger is not None:
                ledger.append(
                    "cadence_step",
                    {"brain": brain, "cadence": cadence, "agent": agent},
                )
            return {"agent": agent, **record}

        @flow(name=f"{brain}-{cadence}-cadence")
        def cadence_flow() -> dict[str, Any]:
            state: dict[str, Any] = {"cadence": cadence, "steps": []}
            for agent in order:
                state["steps"].append(run_step(agent, state))
            if ledger is not None:
                ledger.append(
                    "cadence_complete",
                    {"brain": brain, "cadence": cadence,
                     "agents": [step["agent"] for step in state["steps"]]},
                )
            return state

        return cadence_flow

    def deployment_specs(root: Path = ROOT) -> list[dict[str, Any]]:
        """Activation blueprint: every manifest route with its cron schedule."""
        specs = []
        for brain in ("apex", "jeos"):
            manifest = load_manifest(brain, root)
            for route in manifest.get("cadence_routes", []):
                specs.append({
                    "flow": f"{brain}-{route['cadence']}-cadence",
                    "cron": CADENCE_SCHEDULES.get(route["cadence"], ""),
                    "timezone": "America/New_York",
                    "order": list(route["order"]) + [route["integrator"]],
                })
        return specs
