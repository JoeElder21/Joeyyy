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
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

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
    # Replacing only "/" left "\" live as a separator on the documented Windows
    # workstation, so `--run-id ..\..\name` escaped the gitignored output tree and
    # could drop coverage and JUnit evidence — carrying private mission context —
    # anywhere in a public repository. Reject every separator and traversal
    # component rather than sanitising one of them.
    cleaned = stamp.strip()
    if any(part in cleaned for part in ("/", "\\", "..", "\0")) or Path(cleaned).is_absolute():
        raise UnsafeRun(
            f"--run-id {stamp!r} contains a path separator or traversal component. "
            "Run results carry private mission context and must stay inside "
            "evals/output/."
        )
    if cleaned in {".", ".."} or cleaned.startswith("."):
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


def provenance() -> dict:
    """What produced this result, recorded so a score stays interpretable.

    A run directory previously held the case inventory and a caller-chosen id
    and nothing about the implementation that generated it. After a prompt
    edit, a model-alias change, or a deepeval upgrade, a passing artifact could
    not say which specialist and which judge it attested to — so it could not
    serve as the rollback evidence the acceptance gate treats it as.

    Everything here is read from the environment rather than declared, and
    anything that cannot be established is recorded as unknown rather than
    guessed. `dispatch_wired: false` is the load-bearing entry today: it says
    in the artifact itself that no specialist was actually invoked.
    """
    record: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "dispatch_wired": False,
    }
    try:
        record["commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        ).stdout.strip()
        record["tree_dirty"] = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
                cwd=Path(__file__).resolve().parent,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        # A result produced outside a checkout is still a result; it just
        # cannot claim a commit. Saying so beats omitting the field.
        record["commit"] = "unknown"
        record["tree_dirty"] = "unknown"

    for package in ("deepeval", "pytest"):
        try:
            record[f"{package}_version"] = metadata.version(package)
        except metadata.PackageNotFoundError:
            record[f"{package}_version"] = "not installed"

    # The judge model is whatever DeepEval resolves from the environment. It is
    # recorded, never defaulted -- an artifact that names the wrong judge is
    # worse than one that admits it does not know.
    record["judge_model"] = os.environ.get("DEEPEVAL_JUDGE_MODEL") or os.environ.get(
        "OPENAI_MODEL_NAME", "unset (deepeval default)"
    )
    record["specialist_model"] = "n/a (dispatch not wired)"
    return record


def coverage_report() -> dict:
    coverage = build_coverage()
    cases = load_cases()
    report = coverage.summary()
    report["provenance"] = provenance()
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
    # Belt and braces: even with the name validated, confirm the resolved path
    # is genuinely inside the gitignored tree before anything is written.
    if not out_dir.resolve().is_relative_to(OUTPUT_ROOT.resolve()):
        raise UnsafeRun(f"{out_dir} resolves outside {OUTPUT_ROOT}; refusing to write evidence")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise UnsafeRun(
            f"{out_dir} already holds results. Choose a new --run-id rather than "
            "overwriting recorded evidence."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    # Written before the run so a crashed run still leaves its inventory, and
    # rewritten afterwards from the actual results -- see below.
    (out_dir / "coverage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    results = out_dir / "results.xml"
    code = pytest.main([str(target), "-q", f"--junitxml={results}"])

    # Without this, every published run reported `modes_proven: 0` permanently:
    # coverage.json was written before pytest and nothing read results.xml
    # afterwards, so the harness could never record the passing-run evidence its
    # own gate demands. A gate whose evidence can never be produced is not a
    # gate, it is a wall.
    report = _record_passes(report, results, identifier)
    (out_dir / "coverage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"\nResults written to {out_dir}.\n"
        f"{report['modes_proven']}/{report['modes_total']} material modes have a "
        f"recorded passing run in {identifier}.\n"
        f"Publish this directory to the '{DRIVE_FOLDER_NAME}' folder on Drive "
        "through the approved connector; do not commit it.",
    )
    return int(code)


def _record_passes(report: dict, results: Path, identifier: str) -> dict:
    """Fold the run's actual outcomes back into the coverage summary.

    Reads the JUnit XML pytest just wrote, so a pass is recorded because a test
    passed rather than because a case file exists. A test that errored, failed,
    or was skipped records nothing: `skipped` matters here because the whole
    suite skips when no evaluation runtime is installed, and counting a skip as
    a pass would let an uninstalled dependency attest the corps.
    """
    coverage = build_coverage()
    if results.exists():
        for case in ElementTree.parse(results).getroot().iter("testcase"):
            key = _mode_key_from(case.get("name") or "")
            if not key:
                continue
            if any(child.tag in {"failure", "error", "skipped"} for child in case):
                continue
            coverage.passed[key] = identifier
    updated = coverage.summary()
    # Preserve the descriptive sections the pre-run report carried.
    for extra in ("metric_contract", "cases", "deepeval_available", "provenance"):
        if extra in report:
            updated[extra] = report[extra]
    updated["run_id"] = identifier
    return updated


def _mode_key_from(test_name: str) -> str:
    """Recover the mode key from a parametrized test id, e.g. `test_x[apex/a/b]`."""
    if "[" not in test_name or not test_name.rstrip().endswith("]"):
        return ""
    return test_name[test_name.index("[") + 1 : test_name.rindex("]")]


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
