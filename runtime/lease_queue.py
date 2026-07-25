"""Celery per-target mutation queues — build ticket #3, queue layer.

Celery is imported lazily; the stdlib CI environment never needs it. Each
canonical lease key maps to its own Celery queue with worker concurrency one,
so mutations to the same brain/target/resource serialize naturally — the
single-writer rule enforced by infrastructure, not convention. The lease and
admission checks from ``runtime/writer_lease.py`` still run inside the task:
the queue adds ordering, never bypasses the gate.

Offline/tests: ``make_app(eager=True)`` runs tasks in-process with full
admission semantics. Workstation activation: point ``broker`` at Redis and
start one worker per queue (``celery -A ... worker -Q <queue> -c 1``).
"""

from __future__ import annotations

from typing import Any, Callable

from .writer_lease import LeaseRegistry, MutationAdmission, canonical_key


def queue_name(lease: dict) -> str:
    key = canonical_key(lease["owner_brain"], lease["write_target"], lease["resource_id"])
    return "mut." + key.replace("/", ".").lower()


def make_app(broker: str | None = None, eager: bool = False):
    """Build the Celery app plus a governed ``submit_mutation`` entry point."""
    from celery import Celery

    app = Celery("joeyyy_mutations", broker=broker or "memory://")
    app.conf.task_always_eager = eager
    app.conf.task_eager_propagates = eager

    registry = LeaseRegistry()
    admission = MutationAdmission(registry=registry)

    @app.task(name="runtime.execute_mutation", bind=True)
    def execute_mutation(self, lease: dict, description: str) -> dict:
        key = admission.admit(lease)
        try:
            # The mutation callable is resolved by the worker environment; in
            # this repository the execution step is Agent 007's, so the task
            # records the admitted mutation and returns it for readback.
            return {"key": key, "lease_id": lease["lease_id"], "description": description}
        except Exception:
            admission.complete(key, readback_confirmed=False)
            raise

    def submit_mutation(
        lease: dict,
        description: str,
        readback: Callable[[dict], bool],
    ) -> dict:
        """Queue a mutation on its per-key queue, then close via readback."""
        result = execute_mutation.apply_async(
            args=[lease, description], queue=queue_name(lease)
        )
        outcome: dict[str, Any] = result.get() if app.conf.task_always_eager else {
            "key": canonical_key(
                lease["owner_brain"], lease["write_target"], lease["resource_id"]
            ),
            "task_id": result.id,
            "status": "queued",
        }
        if app.conf.task_always_eager:
            confirmed = bool(readback(outcome))
            closed = admission.complete(outcome["key"], readback_confirmed=confirmed)
            outcome["lease_status"] = closed["status"]
        return outcome

    return {
        "app": app,
        "registry": registry,
        "admission": admission,
        "execute_mutation": execute_mutation,
        "submit_mutation": submit_mutation,
    }
