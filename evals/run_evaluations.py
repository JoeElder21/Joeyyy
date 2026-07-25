"""Evaluation runner: reports coverage, executes available cases, writes results.

Results are written to `evals/output/<run-id>/` — gitignored — and published to
the **Evaluations** folder on Joe's Drive by Agent 007 through the approved Drive
connector.

Results deliberately never land in this repository. Evaluation inputs and
transcripts are the private material that `docs/PRIVACY_AND_DATA_BOUNDARIES.md`
exists to keep out of a public tree, and this script holds no Drive credential of
its own — publication is a connector action under the packet-only policy, not a
library call. That is the same boundary every other write in this system crosses.

Usage:
    python evals/run_evaluations.py --coverage        # inventory only, no model
    python evals/run_evaluations.py                   # run cases (needs deepeval)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (  # noqa: E402 - path shim above is deliberate
    METRIC_CONTRACT,
    build_coverage,
    deepeval_available,
    load_cases,
    metrics_for,
)

OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DRIVE_FOLDER_NAME = "Evaluations"


class UnsafeRun(Exception):
    """The run cannot proceed without destroying evidence or leaking data."""


def run_id(stamp: str | None) -> str:
    """Run identifier. Passed in rather than read from the clock so a run is
    reproducible and a re-run can be pinned to the mission it evidences.

    Required, not defaulted. An earlier version fell back to `unstamped`, so two
    runs without `--run-id` wrote to the same directory and the second silently
    overwrote the first — destroying the evidence and the rollback trail that
    the acceptance gate depends on. Evidence that can be overwritten in place is
    not evidence.
    """
    if not stamp or not stamp.strip():
        raise UnsafeRun(
            "--run-id is required: name the run after the mission it evidences. "
            "Without it, a second run overwrites the first's results in place."
        )
    cleaned = stamp.strip().replace("/", "-")
    if cleaned in {".", ".."}:
        raise UnsafeRun(f"--run-id {stamp!r} is not a usable directory name")
    return cleaned


def assert_telemetry_disabled() -> None:
    """Refuse to run while DeepEval would upload evaluation data.

    `requirements/runtime-evaluation.txt` records cloud logging as a condition,
    not a preference, and `docs/PRIVACY_AND_DATA_BOUNDARIES.md` treats mission
    context as exactly the material that must not leave. But a condition written
    in a requirements comment enforces nothing: the runner previously proceeded
    the moment the package imported, so following the documented command was
    enough to ship private mission context to Confident AI.

    Opting out is set here rather than merely checked, because a run that
    silently uploads is worse than a run that refuses. `setdefault` semantics
    are deliberate — an explicit contrary choice by Joe still wins, and is
    reported rather than overridden.
    """
    for name in ("DEEPEVAL_TELEMETRY_OPT_OUT", "DEEPEVAL_DISABLE_PROGRESS_BAR"):
        os.environ.setdefault(name, "YES")
    if os.environ.get("DEEPEVAL_TELEMETRY_OPT_OUT", "").upper() not in {"YES", "1", "TRUE"}:
        raise UnsafeRun(
            "DEEPEVAL_TELEMETRY_OPT_OUT is explicitly disabled; refusing to run. "
            "Evaluation inputs are the private material the data boundary protects."
        )
    if os.environ.get("CONFIDENT_API_KEY"):
        raise UnsafeRun(
            "CONFIDENT_API_KEY is set, so results would be logged to the Confident AI "
            "cloud. Unset it, or record an explicit decision to disclose before running."
        )


def coverage_report() -> dict:
    coverage = build_coverage()
    cases = load_cases()
    report = coverage.summary()
    report["metric_contract"] = METRIC_CONTRACT
    report["cases"] = {
        key: {
            "title": case.get("title", ""),
            "source": case.get("_source", ""),
            "metrics": list(metrics_for(case)),
            "provenance": case.get("provenance", ""),
        }
        for key, case in sorted(cases.items())
    }
    report["deepeval_available"] = deepeval_available()
    return report


def execute(stamp: str | None) -> int:
    """Execute the available cases. Refuses to fabricate a result without a
    runtime — an unproven mode must read as unproven, not as passing."""
    report = coverage_report()
    if not report["deepeval_available"]:
        print(
            "No evaluation runtime installed. Install with:\n"
            "    python -m pip install -r requirements/runtime-evaluation.txt\n"
            "and provide a model for the judge metrics. Coverage inventory below.\n",
            file=sys.stderr,
        )
        print(json.dumps(report, indent=2))
        return 2

    # Both of these raise rather than warn. A run that uploads private mission
    # context, or one that overwrites the previous run's evidence, is worse than
    # no run at all — and neither is recoverable after the fact.
    assert_telemetry_disabled()
    identifier = run_id(stamp)

    # Executed by pytest so DeepEval owns metric evaluation, caching, and
    # thresholds rather than this script reimplementing them.
    import pytest

    target = Path(__file__).resolve().parent / "test_specialist_modes.py"
    out_dir = OUTPUT_ROOT / identifier
    if out_dir.exists() and any(out_dir.iterdir()):
        raise UnsafeRun(
            f"{out_dir} already holds results. Choose a new --run-id rather than "
            "overwriting recorded evidence."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    code = pytest.main([str(target), "-q", f"--junitxml={out_dir / 'results.xml'}"])
    print(
        f"\nResults written to {out_dir}.\n"
        f"Publish this directory to the '{DRIVE_FOLDER_NAME}' folder on Drive "
        "through the approved connector; do not commit it.",
    )
    return int(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Print the mode-coverage inventory and exit without running cases.",
    )
    parser.add_argument(
        "--run-id",
        dest="stamp",
        help="Required. Run identifier used for the output directory, e.g. a mission id.",
    )
    args = parser.parse_args(argv)

    if args.coverage:
        print(json.dumps(coverage_report(), indent=2))
        return 0
    try:
        return execute(args.stamp)
    except UnsafeRun as refusal:
        print(f"refusing to run: {refusal}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
