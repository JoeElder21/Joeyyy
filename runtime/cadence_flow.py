"""Prefect flows over the cadence engine — build ticket #2, scheduling layer.

Prefect is imported lazily so the stdlib CI environment stays importable.
Two flows:

- ``hygiene_sweep_flow`` — the fully-real recurring job from
  trial/TICKET-005: three repository checks, one appended ISO-dated log line,
  append-only, failures reported as failures. Schedule with
  ``cron="0 7 * * 1-5"`` (America/New_York) per the ticket.
- ``cadence_flow`` — builds the ordered delegation plan for one (brain,
  cadence) cycle from the brain manifest, runs the hygiene sweep as its
  runnable step, and returns an honest run record. Specialist steps are
  emitted as delegation-packet skeletons for Agent 007 to execute in a
  verified runtime; the flow reports ``partial`` until they are. The weekly
  APEX wrapper matches trial/TICKET-002's Monday review (``cron="0 8 * * 1"``).

Serve both on the workstation with::

    from runtime.cadence_flow import serve_cadences
    serve_cadences()
"""

from __future__ import annotations

from .cadence import (
    CadenceRun,
    build_cadence_run,
    run_hygiene_sweep,
    status_line,
)


def _prefect():
    from prefect import flow, task

    return flow, task


def build_flows():
    """Construct and return the Prefect flows (requires prefect)."""
    flow, task = _prefect()

    @task(name="build-delegation-plan")
    def build_plan(brain: str, cadence: str) -> CadenceRun:
        return build_cadence_run(brain, cadence)

    @task(name="hygiene-sweep", retries=0)  # honesty: a failed check is never retried into silence
    def hygiene(run: CadenceRun) -> CadenceRun:
        run.hygiene_results = run_hygiene_sweep()
        return run

    @task(name="emit-run-record")
    def record(run: CadenceRun) -> str:
        return status_line(run)

    @flow(name="hygiene-sweep")
    def hygiene_sweep_flow() -> dict[str, bool]:
        return run_hygiene_sweep()

    @flow(name="cadence")
    def cadence_flow(brain: str, cadence: str, with_hygiene: bool = True) -> str:
        run = build_plan(brain, cadence)
        if with_hygiene:
            run = hygiene(run)
        return record(run)

    @flow(name="weekly-apex-cadence")
    def weekly_apex_flow() -> str:
        return cadence_flow("apex", "weekly")

    return {
        "hygiene_sweep_flow": hygiene_sweep_flow,
        "cadence_flow": cadence_flow,
        "weekly_apex_flow": weekly_apex_flow,
    }


def serve_cadences() -> None:  # pragma: no cover - workstation entry point
    """Serve the scheduled deployments (blocks; run on the workstation)."""
    from prefect import serve

    flows = build_flows()
    serve(
        flows["hygiene_sweep_flow"].to_deployment(
            name="ticket-005-hygiene", cron="0 7 * * 1-5", timezone="America/New_York"
        ),
        flows["weekly_apex_flow"].to_deployment(
            name="weekly-apex-review", cron="0 8 * * 1", timezone="America/New_York"
        ),
    )
