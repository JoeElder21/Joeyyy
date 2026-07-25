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

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

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
    "case_criteria": (
        "Did the output meet this case's own expected_artifacts and "
        "expected_behaviors, and avoid every forbidden_behavior? Generic metrics "
        "cannot know case-specific criteria; only the case states them."
    ),
    "packet_validity": (
        "Is the emitted handoff/delegation packet schema-valid against schemas/? "
        "Deterministic pre-check; runs before any model-judged metric."
    ),
}

# Every mode is judged on these; a mode may add more in its case file.
BASELINE_METRICS = ("packet_validity", "role_adherence", "brain_isolation", "case_criteria")


# Acceptance gates from docs/SPECIALIST_ACCEPTANCE_TESTS.md that this harness
# does NOT evaluate and must never be read as attesting. They are longitudinal
# or runtime properties — repeated missions over weeks, evidence that a
# connector handle never reached a specialist, a readback against live target
# state — and no single evaluation run can produce any of them.
#
# Listed as data, and emitted in every summary, because the earlier flag was
# named `promotion_ready` while proving only "each mode passed once". A name
# that overstates what was measured is the same defect as a metric that always
# returns 1: it reads as evidence and is not.
GATES_NOT_MODELLED = (
    "longitudinal mission counts (e.g. four weekly WAR Architect missions, "
    "five Delivery Commander missions, three Systems Blacksmith shadow runs)",
    "runtime connector-isolation evidence (gate 20)",
    "mutation readback and rollback evidence against live target state (gates 9, 14)",
    "net-time and value thresholds measured over weeks",
)


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
    # The manifest's own scope sentence. `class_id` is deliberately generic and
    # shared across mirrored specialists — the APEX War Architect and the JEOS
    # Life Architect are both `strategy` — so judging role adherence by class
    # cannot distinguish professional campaigns from personal outcomes, and
    # would pass work belonging to the other brain's same-class owner.
    responsibility: str = ""

    @property
    def key(self) -> str:
        return f"{self.brain}/{self.agent}/{self.mode}"


@dataclass
class Coverage:
    """What the harness can and cannot currently attest.

    Two separate things, deliberately not conflated:

    - `covered` — a mode has a *case file*. That is inventory.
    - `passed` — a mode has a *recorded passing run*. That is evidence.

    An earlier version computed promotion readiness from `covered` alone, so
    authoring 39 JSON files would have reported the corps ready for promotion
    without a single evaluation having run. That is the exact failure this
    harness exists to prevent — inventory completeness read as behavioural
    evidence — and it was caught in review rather than by the design.
    """

    modes: list[Mode] = field(default_factory=list)
    covered: dict[str, Path] = field(default_factory=dict)
    # Mode key -> run identifier that recorded a pass. Empty until a real run
    # is supplied; nothing here is ever inferred from a case file existing.
    passed: dict[str, str] = field(default_factory=dict)

    @property
    def uncovered(self) -> list[Mode]:
        return [mode for mode in self.modes if mode.key not in self.covered]

    @property
    def unproven(self) -> list[Mode]:
        """Modes with no recorded passing run — the set the active gate cares about."""
        return [mode for mode in self.modes if mode.key not in self.passed]

    @property
    def percent(self) -> float:
        if not self.modes:
            return 0.0
        return 100.0 * len(self.covered) / len(self.modes)

    def summary(self) -> dict:
        blockers = []
        if self.uncovered:
            blockers.append(f"{len(self.uncovered)} material modes have no case")
        if self.unproven:
            blockers.append(f"{len(self.unproven)} material modes have no recorded passing run")
        return {
            "modes_total": len(self.modes),
            "modes_covered": len(self.covered),
            "modes_uncovered": len(self.uncovered),
            "coverage_percent": round(self.percent, 1),
            "uncovered_keys": [mode.key for mode in self.uncovered],
            # Inventory. Says a case exists, never that it passed.
            "cases_complete": not self.uncovered,
            # Evidence, and only of one thing: every material mode has at least
            # one recorded passing run. Formerly `promotion_ready`, which was a
            # claim this harness cannot support — the acceptance gates also
            # require repeated missions, connector-isolation evidence, and
            # mutation readback, none of which a single run produces. The flag
            # was accurate about what it measured and wrong about what it meant.
            "modes_proven": len(self.passed),
            "behavioral_modes_proven": bool(self.modes) and not self.unproven,
            "promotion_blockers": blockers,
            # Emitted on every summary so a reader who sees the flag above also
            # sees what it excludes, in the same object.
            "gates_not_modelled": list(GATES_NOT_MODELLED),
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
                        responsibility=spec.get("responsibility", ""),
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
            raise ValueError(f"case targets unknown mode {key!r}; the roster is authoritative")
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
