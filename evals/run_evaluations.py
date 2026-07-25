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


def run_id(stamp: str | None) -> str:
    """Run identifier. Passed in rather than read from the clock so a run is
    reproducible and a re-run can be pinned to the mission it evidences."""
    return stamp or "unstamped"


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

    # Executed by pytest so DeepEval owns metric evaluation, caching, and
    # thresholds rather than this script reimplementing them.
    import pytest

    target = Path(__file__).resolve().parent / "test_specialist_modes.py"
    out_dir = OUTPUT_ROOT / run_id(stamp)
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
        help="Run identifier used for the output directory, e.g. a mission id.",
    )
    args = parser.parse_args(argv)

    if args.coverage:
        print(json.dumps(coverage_report(), indent=2))
        return 0
    return execute(args.stamp)


if __name__ == "__main__":
    raise SystemExit(main())
