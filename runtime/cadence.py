"""Cadence route engine — build ticket #2, stdlib-pure core.

Loads the ``[[cadence_routes]]`` tables from the brain manifests
(``brains/apex/agents.toml``, ``brains/jeos/agents.toml``) — the manifests
stay the single source of truth; nothing is duplicated here — and turns a
(brain, cadence) pair into an ordered, validated delegation plan.

Honesty rules enforced in code (from docs/BRAIN_CADENCE_RUNBOOK.md):

- Specialists are never invoked from this engine. Each step yields a
  delegation-packet skeleton for Agent 007 to execute in a verified runtime.
  A run whose specialist steps are unexecuted is reported ``partial``, never
  complete, and never backfilled with invented activity.
- Brain lock: every step's agent must belong to the route's brain; the
  integrator is always last and is always Agent 007's native name.
- Single-mode execution: each delegation names exactly one registered
  contract mode from the owning agent's manifest entry.

The runnable part of a cadence — the repository hygiene sweep from
``trial/TICKET-005-recurring-cadence-job.md`` — is implemented here for real:
three checks, one appended ISO-dated status line, append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
INTEGRATOR = "apex_chief_of_staff"

HYGIENE_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("unittest", (sys.executable, "-m", "unittest", "discover", "-s", "tests")),
    ("privacy_guard", (sys.executable, "scripts/privacy_guard.py")),
    ("corps_validation", (sys.executable, "scripts/validate_specialist_corps.py")),
)


def load_brain_manifest(brain: str) -> dict:
    path = ROOT / "brains" / brain.lower() / "agents.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


@dataclass
class DelegationStep:
    """One specialist step: a packet skeleton, not an invocation."""

    agent: str
    registered_modes: list[str]
    selected_mode: str | None = None
    executed: bool = False
    artifact_types: list[str] = field(default_factory=list)

    def select_mode(self, mode: str) -> None:
        if mode not in self.registered_modes:
            raise ValueError(
                f"{self.agent}: mode {mode!r} is not a registered contract mode "
                f"(registered: {self.registered_modes})"
            )
        self.selected_mode = mode


@dataclass
class CadenceRun:
    brain: str
    cadence: str
    steps: list[DelegationStep]
    integrator: str
    hygiene_results: dict[str, bool] = field(default_factory=dict)

    @property
    def status(self) -> str:
        """complete only when every specialist step actually executed."""
        if not self.steps:
            return "empty"
        return "complete" if all(step.executed for step in self.steps) else "partial"


def build_cadence_run(brain: str, cadence: str) -> CadenceRun:
    """Build the ordered, validated delegation plan for one cadence cycle."""
    manifest = load_brain_manifest(brain)
    routes = [r for r in manifest.get("cadence_routes", []) if r["cadence"] == cadence]
    if len(routes) != 1:
        raise ValueError(
            f"{brain}/{cadence}: expected exactly one cadence route, found {len(routes)}"
        )
    route = routes[0]
    roster = set(manifest["roster"])
    agents = manifest["agents"]
    prefix = manifest["namespace_prefix"].split("::")[0].lower() + "_"

    steps: list[DelegationStep] = []
    for agent_name in route["order"]:
        if agent_name not in roster:
            raise ValueError(f"{brain}/{cadence}: {agent_name} is not on the {brain} roster")
        if not agent_name.startswith(prefix):
            raise ValueError(f"{brain}/{cadence}: {agent_name} violates the brain lock")
        entry = agents[agent_name]
        steps.append(
            DelegationStep(
                agent=agent_name,
                registered_modes=list(entry.get("modes", [])),
                artifact_types=list(entry.get("artifact_types", [])),
            )
        )

    integrator = route["integrator"]
    if integrator != INTEGRATOR:
        raise ValueError(
            f"{brain}/{cadence}: integrator must be {INTEGRATOR}, found {integrator}"
        )
    return CadenceRun(brain=brain, cadence=cadence, steps=steps, integrator=integrator)


def run_hygiene_sweep(
    checks: tuple[tuple[str, tuple[str, ...]], ...] = HYGIENE_CHECKS,
    log_path: Path | None = None,
    today: _dt.date | None = None,
) -> dict[str, bool]:
    """TICKET-005: run the checks, append exactly one dated line, append-only.

    A failure is reported as a failure — checks are never retried into
    silence. Returns {check_name: passed}.
    """
    results: dict[str, bool] = {}
    for name, command in checks:
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True
        )
        results[name] = completed.returncode == 0

    log_path = log_path or (ROOT / "trial" / "output" / "cadence-log.md")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    date = (today or _dt.date.today()).isoformat()
    summary = " ".join(f"{name}={'pass' if ok else 'FAIL'}" for name, ok in results.items())
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {date}: {summary}\n")
    return results


def status_line(run: CadenceRun) -> str:
    """One honest, human-readable line for the run record."""
    executed = sum(1 for s in run.steps if s.executed)
    hygiene = (
        " hygiene["
        + " ".join(f"{k}={'pass' if v else 'FAIL'}" for k, v in run.hygiene_results.items())
        + "]"
        if run.hygiene_results
        else ""
    )
    return (
        f"{run.brain}/{run.cadence}: {run.status} "
        f"({executed}/{len(run.steps)} specialist steps executed, "
        f"integrator {run.integrator}){hygiene}"
    )
