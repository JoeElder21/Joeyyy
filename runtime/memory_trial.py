"""Graphiti memory-layer trial harness — build ticket #5.

Frontier-scan decision #2: trial getzep/graphiti (temporal knowledge-graph
memory, first-party MCP server) against the open memory-layer question, one
brain namespace first. The trial itself needs workstation infrastructure —
a FalkorDB (or Neo4j) instance and an LLM provider key — that this
repository cannot and must not fake.

This harness therefore does exactly two honest things:

- ``preconditions()`` reports what is actually present: graphiti-core
  importable, a graph database reachable, an LLM key configured.
- ``run_trial()`` executes the trial only when every precondition holds:
  writes one synthetic episode into the trial group, reads it back
  (readback rule), and returns the evidence. With anything missing it
  returns ``status: blocked`` listing the missing preconditions — a blocked
  trial is reported blocked, never simulated.

Trial scope guard: one brain namespace only (APEX strategy first). The mem0
gateway in ``scripts/memory_layer.py`` remains the governance reference; the
reconciliation record (docs/RECONCILIATION_2026-07-24.md) holds the
comparison criteria both must meet.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import socket

TRIAL_GROUP = "APEX::Strategy-Campaigns"
TRIAL_EPISODE = "Synthetic trial episode: campaign record created for the graphiti memory trial."


def _graphiti_version() -> str | None:
    if importlib.util.find_spec("graphiti_core") is None:
        return None
    try:
        return importlib.metadata.version("graphiti-core")
    except Exception:
        return "unknown"


def _db_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def preconditions(
    db_host: str | None = None, db_port: int | None = None
) -> dict:
    host = db_host or os.environ.get("FALKORDB_HOST", "localhost")
    port = db_port or int(os.environ.get("FALKORDB_PORT", "6379"))
    return {
        "graphiti_core": _graphiti_version(),
        "graph_db": {"host": host, "port": port, "reachable": _db_reachable(host, port)},
        "llm_key_present": bool(
            os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        ),
        "trial_group": TRIAL_GROUP,
    }


def run_trial(db_host: str | None = None, db_port: int | None = None) -> dict:
    """Run the one-namespace trial, or report exactly why it is blocked."""
    checks = preconditions(db_host, db_port)
    missing = []
    if checks["graphiti_core"] is None:
        missing.append("graphiti-core is not installed (requirements/runtime-memory.txt)")
    if not checks["graph_db"]["reachable"]:
        missing.append(
            f"no graph database at {checks['graph_db']['host']}:{checks['graph_db']['port']} "
            "(start FalkorDB on the workstation)"
        )
    if not checks["llm_key_present"]:
        missing.append("no LLM provider key in the environment")
    if missing:
        return {"status": "blocked", "missing": missing, "preconditions": checks}

    # All preconditions hold: perform the real write-and-readback trial.
    import asyncio

    async def _trial() -> dict:
        from graphiti_core import Graphiti
        from graphiti_core.driver.falkordb_driver import FalkorDriver

        driver = FalkorDriver(
            host=checks["graph_db"]["host"], port=checks["graph_db"]["port"]
        )
        graphiti = Graphiti(graph_driver=driver)
        try:
            await graphiti.build_indices_and_constraints()
            episode = await graphiti.add_episode(
                name="trial-episode",
                episode_body=TRIAL_EPISODE,
                source_description="ticket-5 trial harness",
                reference_time=None,
                group_id=TRIAL_GROUP,
            )
            results = await graphiti.search(
                "campaign record trial", group_ids=[TRIAL_GROUP]
            )
            return {
                "status": "completed",
                "episode_uuid": getattr(getattr(episode, "episode", episode), "uuid", None),
                "readback_hits": len(results),
                "readback_confirmed": len(results) > 0,
                "preconditions": checks,
            }
        finally:
            await graphiti.close()

    return asyncio.run(_trial())


if __name__ == "__main__":
    import json

    print(json.dumps(run_trial(), indent=2, default=str))
