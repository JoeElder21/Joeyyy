"""Behavioral evaluation harness for the mirrored specialist corps.

The repository's 256 tests are *structural* — they prove a specialist cannot
misbehave (schema validity, brain isolation, fail-closed admission, lease
serialization). None of them prove a specialist *does the job*. That gap is what
blocks shadow-to-active promotion: `docs/SPECIALIST_ACCEPTANCE_TESTS.md` requires
"one controlled real mission per material mode", and without a harness that
judgment can only be made by hand, with no regression signal when a prompt
changes.

This module is the inventory and mapping layer. It is stdlib-pure and imports
cleanly without deepeval installed, so repository validation never depends on an
evaluation runtime or a model key — the same degradation contract as
`scripts/verify_runtime_stack.py`.

Material modes are derived from the brain manifests rather than restated here.
A mode added to `brains/*/agents.toml` immediately shows as uncovered instead of
being silently missed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BRAINS = ("apex", "jeos")
CASE_DIR = Path(__file__).resolve().parent / "cases"

# DeepEval metric names mapped to the acceptance criteria already written down in
# this repository. The mapping is the point: an evaluation that does not trace to
# a recorded gate is not evidence for promotion.
METRIC_CONTRACT = {
    "tool_correctness": (
        "Right tools, right arguments. Enforces connector_policy "
        "'packet_only_no_direct_connectors' and the runtime connector-isolation "
        "requirement of the active gate."
    ),
    "task_completion": (
        "Did the mode produce its declared artifact_types? Enforces the "
        "docs/SPECIALIST_ACCEPTANCE_TESTS.md value gate."
    ),
    "role_adherence": (
        "Did the specialist stay inside its responsibility and refuse to expand "
        "its own authority? Enforces the AGENTS.md chain of command."
    ),
    "brain_isolation": (
        "Did the specialist reference only its own brain's namespace, write "
        "targets, and roundtable? Custom metric — no off-the-shelf equivalent."
    ),
    "packet_validity": (
        "Is the emitted handoff/delegation packet schema-valid against schemas/? "
        "Deterministic pre-check; runs before any model-judged metric."
    ),
}

# Every mode is judged on these; a mode may add more in its case file.
BASELINE_METRICS = ("packet_validity", "role_adherence", "brain_isolation")


@dataclass(frozen=True)
class Mode:
    """One material mode of one specialist — the unit the active gate counts."""

    brain: str
    agent: str
    mode: str
    class_id: str
    roster_id: str
    status: str
    memory_namespace: str
    write_targets: tuple[str, ...]
    artifact_types: tuple[str, ...]
    connector_policy: str

    @property
    def key(self) -> str:
        return f"{self.brain}/{self.agent}/{self.mode}"


@dataclass
class Coverage:
    """What the harness can and cannot currently attest."""

    modes: list[Mode] = field(default_factory=list)
    covered: dict[str, Path] = field(default_factory=dict)

    @property
    def uncovered(self) -> list[Mode]:
        return [mode for mode in self.modes if mode.key not in self.covered]

    @property
    def percent(self) -> float:
        if not self.modes:
            return 0.0
        return 100.0 * len(self.covered) / len(self.modes)

    def summary(self) -> dict:
        return {
            "modes_total": len(self.modes),
            "modes_covered": len(self.covered),
            "modes_uncovered": len(self.uncovered),
            "coverage_percent": round(self.percent, 1),
            "uncovered_keys": [mode.key for mode in self.uncovered],
            "promotion_ready": not self.uncovered,
        }


def load_modes(root: Path = ROOT) -> list[Mode]:
    """Derive every material mode from the brain-owned manifests."""
    modes: list[Mode] = []
    for brain in BRAINS:
        manifest = root / "brains" / brain / "agents.toml"
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        for agent, spec in data.get("agents", {}).items():
            for mode in spec.get("modes", []):
                modes.append(
                    Mode(
                        brain=brain,
                        agent=agent,
                        mode=mode,
                        class_id=spec.get("class_id", ""),
                        roster_id=spec.get("roster_id", ""),
                        status=spec.get("status", ""),
                        memory_namespace=spec.get("memory_namespace", ""),
                        write_targets=tuple(spec.get("write_targets", [])),
                        artifact_types=tuple(spec.get("artifact_types", [])),
                        connector_policy=spec.get("connector_policy", ""),
                    )
                )
    return sorted(modes, key=lambda m: m.key)


def load_cases(case_dir: Path = CASE_DIR) -> dict[str, dict]:
    """Load golden cases keyed by mode key. Missing directory is not an error."""
    cases: dict[str, dict] = {}
    if not case_dir.is_dir():
        return cases
    for path in sorted(case_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = payload.get("mode_key")
        if not key:
            raise ValueError(f"{path.name}: case file is missing 'mode_key'")
        if key in cases:
            raise ValueError(f"{path.name}: duplicate case for mode {key}")
        payload["_source"] = str(path.relative_to(case_dir.parent))
        cases[key] = payload
    return cases


def build_coverage(root: Path = ROOT, case_dir: Path = CASE_DIR) -> Coverage:
    modes = load_modes(root)
    cases = load_cases(case_dir)
    known = {mode.key for mode in modes}
    for key in cases:
        if key not in known:
            raise ValueError(
                f"case targets unknown mode {key!r}; the roster is authoritative"
            )
    covered = {key: Path(cases[key]["_source"]) for key in cases}
    return Coverage(modes=modes, covered=covered)


def metrics_for(case: dict) -> tuple[str, ...]:
    """Baseline metrics plus whatever the case adds, order-stable, deduped."""
    declared = tuple(case.get("metrics", ()))
    ordered = list(BASELINE_METRICS) + [m for m in declared if m not in BASELINE_METRICS]
    unknown = [m for m in ordered if m not in METRIC_CONTRACT]
    if unknown:
        raise ValueError(f"case declares unmapped metrics: {sorted(unknown)}")
    return tuple(ordered)


def deepeval_available() -> bool:
    """True when a real evaluation runtime is installed. Never assumed."""
    try:  # degrade cleanly when the evaluation stack is not installed
        import deepeval  # noqa: F401 - availability probe
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    print(json.dumps(build_coverage().summary(), indent=2))
