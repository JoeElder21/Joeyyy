"""Gate measurement helpers for the awesome-copilot selection report.

These live apart from scripts/build_awesome_copilot_report.py because that
module builds the PDF at import time: importing it to test a helper would run
every gate and rewrite the document, and it imports reportlab, which CI does
not install -- so a test that reached into it errored in CI while passing on
any machine that happens to have the package. Keeping the measurement logic
here makes the honesty rules below directly testable, on stdlib alone.

The rule these enforce: never render an unrun check as a clean one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def unverified_note(output: str) -> str:
    """Name the items a passing gate did not actually probe.

    `"valid": true` only means the registry is internally consistent. A mount
    declaring verify_offline = true whose probe could not run comes back with a
    status of "unverified (...)", and collapsing that to a bare "passed"
    publishes an unrun check as a clean one. Surface it in the same row.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        # Non-JSON gate output: report the literal marker rather than claiming
        # there is nothing unverified.
        return (" (output reports unverified items)"
                if "unverified" in output else "")

    if not isinstance(payload, dict):
        return ""
    # "registered" is ALSO an unprobed state, and the larger one: every
    # verify_offline = false mount reports it. Naming only the "unverified"
    # ones published a row reading "not probed: filesystem, governance" while
    # github, postgres, gdrive, civil3d, terraform and azure had equally never
    # been contacted -- an incomplete clean scope, which is the same defect as
    # a bare "passed" one level down.
    def unprobed(entry: dict) -> bool:
        status = str(entry.get("status", ""))
        return status.startswith("unverified") or status == "registered"

    names = sorted(
        str(entry.get("name", "unnamed"))
        for section in payload.values() if isinstance(section, list)
        for entry in section
        if isinstance(entry, dict) and unprobed(entry)
    )
    return f" (not probed: {', '.join(names)})" if names else ""


def missing_dependency_note(output: str) -> str:
    """Say when a passing gate ran against an empty runtime.

    `verify_runtime_stack.py` validates TOML and schemas, which can all pass on
    a machine where none of the declared runtime packages is installed -- it
    reports `installed_count: 0` with 20 entries in `missing` and still exits 0
    with `"valid": true`. Rendering that as a clean runtime-stack pass presents
    a machine with no orchestration runtime as a verified one.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    missing = payload.get("missing")
    if not isinstance(missing, list) or not missing:
        return ""
    installed = payload.get("installed_count")
    total = (installed + len(missing)) if isinstance(installed, int) else None
    scope = f"{len(missing)} of {total}" if total else f"{len(missing)}"
    return (f" (runtime not installed: {scope} declared packages missing, "
            "so this checks declarations only)")


def static_validation_note(output: str) -> str:
    """Say when a passing gate exercised nothing live.

    `validate_specialist_corps.py` reports, on every normal build,
    `connectors_called: false`, `named_agents_invoked: false`,
    `real_missions_completed: false` and
    `validation_mode: static_contract_and_synthetic_packet` -- and the row
    rendered as a bare `passed, "valid": true`. A reader could not tell that no
    connector was contacted, no named agent ran, and no real mission was
    completed. The neighbouring gates disclose unprobed mounts and absent
    packages; this one disclosed the largest scope limit of the three by saying
    nothing. Same rule, same row: never render an unrun check as a clean one.
    """
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    unexercised = [
        label for key, label in (
            ("connectors_called", "no connector called"),
            ("named_agents_invoked", "no named agent invoked"),
            ("real_missions_completed", "no real mission completed"),
        )
        if payload.get(key) is False
    ]
    mode = payload.get("validation_mode")
    if not unexercised and not isinstance(mode, str):
        return ""
    parts = list(unexercised)
    if isinstance(mode, str) and mode:
        parts.append(f"mode: {mode.replace('_', ' ')}")
    return f" ({'; '.join(parts)})" if parts else ""


def failure_detail(completed) -> str:
    """The most informative line available from a failed gate.

    These gates print JSON, so the first output line is "{" -- taking it
    produced rows reading `FAILED (exit 1) — {`, which names nothing. Prefer a
    parsed error, then a substantive stderr line, and fall back to raw output
    only when neither exists.
    """
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("errors", "error", "failures", "problems"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return "; ".join(str(item) for item in value[:3])
            if isinstance(value, str) and value.strip():
                return value.strip()
        # The actionable reason for a failed mount lives only in
        # mounts[*].status. With no top-level error key the substantive-line
        # fallback filtered out every quoted status line and returned "{", so
        # the row read `FAILED (exit 1) — {` -- the exact uninformative output
        # that fallback was added to prevent.
        #
        # Match by EXCLUSION, not by keyword. Allowlisting "fail"/"error" meant
        # each newly introduced failure status had to be remembered here, and
        # the very next one ("undeclared grant scope") was not -- it contains
        # neither word, so the row regressed to `FAILED (exit 1) — },`. The
        # healthy vocabulary is small and stable; anything outside it, in a
        # gate that already exited non-zero, is by definition the reason.
        healthy = ("verified", "registered", "unverified")
        failures = [
            f"{entry.get('name', 'unnamed')}: {entry['status']}"
            for section in payload.values() if isinstance(section, list)
            for entry in section
            if isinstance(entry, dict)
            and isinstance(entry.get("status"), str)
            and not entry["status"].lower().startswith(healthy)
        ]
        if failures:
            return "; ".join(failures[:3])

    def substantive(stream: str) -> str | None:
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        useful = [line for line in lines
                  if line not in "{}[]," and not line.startswith('"')]
        if not useful:
            return None
        # A traceback's informative line is its last, not its first: "Traceback
        # (most recent call last):" names nothing.
        if useful[0].startswith("Traceback (most recent call last)"):
            return useful[-1]
        return useful[0]

    found = substantive(completed.stderr) or substantive(completed.stdout)
    if found:
        return found
    remainder = (completed.stderr + completed.stdout).strip()
    return remainder.splitlines()[0] if remainder else "no output"


def run_gate(script: str) -> str:
    """Run one validation script and report its real outcome.

    These rows used to be hardcoded "Passed" / '"valid": true', so a report
    regenerated while a gate was failing still published success -- in the one
    document meant to serve as verification evidence.
    """
    path = ROOT / "scripts" / script
    try:
        completed = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            capture_output=True, text=True, timeout=600, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"not measured at build time ({type(error).__name__})"

    # Paragraph() parses its input as XML-ish markup, so a finding naming a real
    # file such as docs/R&D<draft>.pdf would raise a parse error and destroy the
    # very PDF meant to record the failure. Escape anything derived from output.
    if completed.returncode != 0:
        return escape(
            f"FAILED (exit {completed.returncode}) — "
            f"{failure_detail(completed)[:110]}")

    output = completed.stdout.strip()
    if not output:
        return "passed"
    note = (unverified_note(output) + missing_dependency_note(output)
            + static_validation_note(output))
    if '"valid": true' in output:
        checked = re.search(r'"(\w+_checked)":\s*(\d+)', output)
        detail = (f" — {checked.group(2)} {checked.group(1).replace('_', ' ')}"
                  if checked else "")
        return escape(f'passed, "valid": true{detail}{note}')
    return escape(f"passed — {output.splitlines()[-1][:90]}{note}")


def measure_test_suite() -> str:
    """Run the suite and report what it actually did.

    The count was previously hardcoded, so every regenerated report published a
    stale figure the moment a test was added -- in a document whose whole
    purpose is to be change evidence. Never fabricate a result here: if the
    suite cannot run, say so.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=ROOT,
            capture_output=True, text=True, timeout=900, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"not measured at build time ({type(error).__name__})"

    output = completed.stderr + completed.stdout
    ran = re.search(r"Ran (\d+) tests?", output)
    if not ran:
        return "not measured at build time (unrecognised output)"
    count = ran.group(1)
    if completed.returncode != 0:
        failures = re.search(r"(FAILED \([^)]*\))", output)
        return escape(
            f"{count} tests, {failures.group(1) if failures else 'FAILED'}")
    skipped = re.search(r"skipped=(\d+)", output)
    tail = f" ({skipped.group(1)} skipped)" if skipped else ""
    return f"{count} tests, OK{tail}"


def count_tracked(pattern: str) -> int:
    """Count tracked files matching a git pathspec, at build time."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-files", pattern], cwd=root,
                             capture_output=True, text=True, check=False)
    except OSError:
        return -1
    # A non-zero exit -- an extracted source archive with no .git, an
    # unreadable or corrupt index -- produces empty stdout, and counting that
    # as 0 published "the tree carries 0 markdown files" as a measurement. The
    # sibling `count_tracked_at` and the delta already report -1 for
    # unavailable, so this was the one path that turned a failed command into a
    # confident number. Absence of output is not evidence of absence of files.
    if out.returncode != 0:
        return -1
    return len([line for line in out.stdout.splitlines() if line.strip()])


def count_tracked_at(ref: str, pattern: str) -> int:
    """Count matching tracked files at a git ref, for honest before/after deltas."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref],
                             cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return -1
    if out.returncode != 0:
        return -1
    suffix = pattern.lstrip("*")
    return len([l for l in out.stdout.splitlines() if l.endswith(suffix)])


# The tip of main immediately before this work began. Pinned deliberately: a
# merge-base against a moving main collapses to the merged tip once this lands,
# which would silently rewrite the report's headline delta to zero and destroy
# the change evidence it exists to carry.
PRE_INSTALL_BASELINE = "89a2c1531765355843a1f3ed64ced85cf5d8aed6"
# The FIRST commit of this installation work. Pinned for one reason: it is the
# only stable way to tell an upstream tip from this branch. `_merged_upstream_tips`
# reads every merge's second parent, which is correct while merges bring main
# INTO this branch -- but once GitHub integrates the PR, that merge's second
# parent is this branch, so every file the branch added would be counted as
# having come from elsewhere and the published delta would collapse to zero,
# in the report whose whole purpose is to be installation evidence. A commit
# that contains BRANCH_ROOT is this work, not upstream.
BRANCH_ROOT = "7e2f52418cc8ea6221289d71368c45cf18fc69ff"


def _branch_point() -> str:
    """The pinned pre-install commit, or "" when it is not reachable.

    There is deliberately no merge-base fallback. Falling back to
    merge-base(HEAD, main) reproduced the very defect the pin was added to fix:
    once this work merges, that resolves to the merged tip and the delta silently
    becomes zero. In a shallow clone the honest answer is that the figure cannot
    be computed, and the report says so rather than printing a confident zero.
    """
    root = Path(__file__).resolve().parents[1]
    try:
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{PRE_INSTALL_BASELINE}^{{commit}}"],
            cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return PRE_INSTALL_BASELINE if known.returncode == 0 else ""


def _tracked_set_at(ref: str, suffix: str) -> set[str] | None:
    """The tracked paths with `suffix` at `ref`, or None if unreadable."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref],
                             cwd=root, capture_output=True, text=True,
                             check=False)
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return {line for line in out.stdout.splitlines() if line.endswith(suffix)}


class _Unanswerable(Exception):
    """This clone cannot classify a merge tip, so no delta can be published."""


def _known(commit: str) -> bool:
    """Whether this clone actually has `commit`."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                             cwd=root, capture_output=True, text=True,
                             check=False)
    except OSError:
        return False
    return out.returncode == 0


def _contains(commit: str, ancestor: str) -> bool | None:
    """True/False if answerable, None if this clone cannot tell.

    In a shallow clone the anchor commit is absent entirely and `merge-base`
    exits non-zero -- which is indistinguishable, to a boolean, from "not an
    ancestor". Collapsing the two made an unanswerable question read as "no",
    so a tip that IS this branch would be treated as upstream and every file
    the branch added would be subtracted from its own delta. An unanswerable
    question is reported, never guessed.
    """
    root = Path(__file__).resolve().parents[1]
    if not _known(commit) or not _known(ancestor):
        return None
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, commit],
            cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return out.returncode == 0


def _merged_upstream_tips() -> list[str]:
    """The main tips this branch has merged in, from the merges' second parents.

    Subtracting only the pinned baseline attributed every file that arrived
    from main to this branch: at the time of writing the baseline held 46
    markdown files, the merged main tip held 58, and HEAD held 78 -- so the
    report published "adds 32" for a branch that adds 20, in the one document
    meant to serve as installation evidence.

    A merge's second parent is a permanent record of the tip that was merged,
    unlike merge-base, which collapses. But it is only an UPSTREAM tip while
    merges run main-into-branch; the integration merge that lands this PR has
    this branch as its second parent, and counting that would put every file
    the branch added into "came from elsewhere" and publish a delta of zero --
    the same erasure, from the other direction. A tip that contains
    BRANCH_ROOT is this work, so it is excluded.
    """
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(
            ["git", "rev-list", "--merges", "--parents", "HEAD"],
            cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return []
    if out.returncode != 0:
        return []
    seconds = [parts[2] for parts in
               (line.split() for line in out.stdout.splitlines())
               if len(parts) >= 3]
    tips = []
    for tip in seconds:
        verdict = _contains(tip, BRANCH_ROOT)
        if verdict is None:
            # Cannot tell whether this tip is our own work. Refusing to answer
            # is the only safe option: including it may erase the branch's
            # delta, excluding it may inflate it. `_markdown_added` reports the
            # figure as unmeasurable instead of publishing either guess.
            raise _Unanswerable(tip)
        if not verdict:
            tips.append(tip)
    return tips


MARKDOWN_NOW = count_tracked("*.md")
_BASE = _branch_point()


def _markdown_added() -> int:
    """Markdown files this branch itself introduced, or -1 if unmeasurable.

    A file counts only if it was at neither the pre-install baseline nor any
    upstream tip merged in since. Anything else is somebody else's work being
    published as evidence for this one.
    """
    if not _BASE:
        return -1
    here = _tracked_set_at("HEAD", ".md")
    baseline = _tracked_set_at(_BASE, ".md")
    if here is None or baseline is None:
        return -1
    elsewhere = set(baseline)
    try:
        tips = _merged_upstream_tips()
    except _Unanswerable:
        return -1
    for tip in tips:
        merged = _tracked_set_at(tip, ".md")
        if merged is None:
            # Cannot prove which side a file came from, so do not guess.
            return -1
        elsewhere |= merged
    return len(here - elsewhere)


MARKDOWN_PRE_INSTALL = count_tracked_at(_BASE, "*.md") if _BASE else -1
_MD_BEFORE = MARKDOWN_PRE_INSTALL
MARKDOWN_ADDED = _markdown_added()
