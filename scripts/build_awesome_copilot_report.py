"""Build the awesome-copilot selection report PDF.

The PDF itself is deliberately not tracked: scripts/privacy_guard.py forbids
non-source artifacts and non-UTF-8 files in this public tree. This generator is
the tracked source of truth -- run it to reproduce the report.

    pip install reportlab
    python scripts/build_awesome_copilot_report.py

Output: docs/reports/AWESOME_COPILOT_SELECTION_REPORT.pdf (gitignored).
"""

import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_gates import measure_test_suite, run_gate  # noqa: E402

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

OUT = str(Path(__file__).resolve().parents[1] / "docs" / "reports"
           / "AWESOME_COPILOT_SELECTION_REPORT.pdf")

INK = colors.HexColor("#14161A")
MUTED = colors.HexColor("#5A6270")
RULE = colors.HexColor("#D4D8E0")
ACCENT = colors.HexColor("#1F4E79")
BAND = colors.HexColor("#EEF1F6")
KEEP = colors.HexColor("#1B6B4A")
DROP = colors.HexColor("#8A5A00")

# The decision date is fixed history; every gate result, test count, pin and
# tracked-inventory figure below is measured when this runs. Labelling all of it
# with the original date would falsely timestamp regenerated evidence.
_today = _dt.date.today()
# %-d is a POSIX no-padding extension; on Windows strftime raises ValueError,
# and it would do so at import time, before the PDF could be generated.
BUILD_DATE = f"{_today.day} {_today.strftime('%B %Y')}"


def count_tracked(pattern: str) -> int:
    """Count tracked files matching a git pathspec, at build time."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-files", pattern], cwd=root,
                             capture_output=True, text=True, check=False)
    except OSError:
        return -1
    return len([line for line in out.stdout.splitlines() if line.strip()])


def count_adopted(kind: str, pattern: str) -> int:
    """Assets adopted FROM the pinned upstream: manifest-listed AND tracked.

    Globbing the directory counted every file in it, which attributed
    repository-authored agents to the Awesome Copilot inventory the moment a
    sibling change added one. The manifest is what "adopted" means, so the
    count is the intersection and a first-party file simply is not in it.
    """
    return len(manifest_names().get(kind, set()) & tracked_names(pattern))


def count_installed(pattern: str) -> int:
    """Count vendored assets that are actually TRACKED.

    A filesystem glob counted an untracked discovery download as adopted, while
    the report's privacy row runs privacy_guard.py with no arguments -- which
    scans `git ls-files` only. The report could therefore raise its adoption
    total and publish a passing privacy result that never inspected the asset it
    had just counted. Counting and gating now share one scope.

    Tracking is necessary but not sufficient: see reconcile_with_manifest().
    """
    return count_tracked(f".github/{pattern}")


def tracked_names(pattern: str) -> set[str]:
    """Basenames of tracked assets matching a `.github/` pathspec."""
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-files", f".github/{pattern}"], cwd=root,
                             capture_output=True, text=True, check=False)
    except OSError:
        return set()
    names = set()
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skills are directories: .github/skills/<name>/SKILL.md -> <name>
        parts = Path(line).parts
        names.add(parts[-2] if parts[-1] == "SKILL.md" else parts[-1])
    return names


def manifest_names() -> dict[str, set[str]]:
    """The assets the manifest actually claims, by class.

    Counting every tracked path under .github/ as upstream adoption is wrong in
    both directions: a repository-authored file placed in one of these
    directories is attributed to the pinned Awesome Copilot inventory, and a
    newly vendored file raises the count while the report's own tables -- which
    carry each file's selection rationale -- silently omit it. The manifest is
    the authoritative list, so generation reconciles against it.
    """
    manifest = Path(__file__).resolve().parents[1] / ".github" / "AWESOME-COPILOT.md"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return {}
    # Only the inventory tables count. Prose elsewhere in the manifest names
    # files illustratively -- the rejected-exemption discussion cites a
    # hypothetical `local.instructions.md` -- and treating those as claimed
    # assets would fail reconciliation against a file that was never adopted.
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    found = re.findall(
        r"`([A-Za-z0-9._-]+(?:\.instructions\.md|\.agent\.md))`", "\n".join(rows))
    # Every skill bullet, not one hard-coded family. Matching only the
    # `suggest-awesome-github-copilot-*` discovery skills meant that vendoring
    # any other skill -- the ordinary outcome of a discovery pass -- left it
    # unparsed, so reconciliation saw a tracked skill the manifest "did not
    # list" and aborted generation on a perfectly valid intake.
    skills = re.findall(r"^\s*[-*] `([A-Za-z0-9][A-Za-z0-9._-]*)/`",
                        text, re.MULTILINE)
    return {
        "instructions": {n for n in found if n.endswith(".instructions.md")},
        "agents": {n for n in found if n.endswith(".agent.md")},
        "skills": set(skills),
    }


def rendered_names() -> dict[str, set[str]]:
    """The assets the report's own tables actually display.

    Reconciling the manifest against the tracked tree is only half the check:
    the rationale tables below are separate hardcoded lists, so an asset could
    be tracked, listed in the manifest, and still missing from the report --
    counted in the totals but published with no row explaining why it was
    selected. These names are compared too.
    """
    return {
        "instructions": {f"{name}.instructions.md"
                         for name, _glob, _why in INSTRUCTION_ROWS},
        "agents": {f"{name}.agent.md" for name, _role, _note in AGENT_ROWS},
        "skills": {name for name, _fn in SKILL_ROWS},
    }


def reconcile_with_manifest() -> None:
    """Refuse to generate a report whose inventory contradicts the manifest."""
    claimed = manifest_names()
    if not claimed:
        raise SystemExit("cannot read .github/AWESOME-COPILOT.md to reconcile "
                         "the adopted inventory; refusing to publish counts")
    actual = {
        "instructions": tracked_names("instructions/*.instructions.md"),
        "agents": tracked_names("agents/*.agent.md"),
        "skills": tracked_names("skills/*/SKILL.md"),
    }
    shown = rendered_names()
    problems: list[str] = []
    first_party: list[str] = []
    for kind, expected in claimed.items():
        untracked = expected - actual[kind]
        unlisted = actual[kind] - expected
        unrendered = expected - shown[kind]
        extra_rows = shown[kind] - expected
        if untracked:
            problems.append(f"{kind}: in manifest but not tracked: "
                            f"{', '.join(sorted(untracked))}")
        if unlisted:
            # NOT fatal, and deliberately so. `.github/agents/` also holds
            # repository-authored agents that were never upstream; failing here
            # would block report generation on a perfectly valid first-party
            # addition. They are excluded from the adopted counts instead --
            # which is the actual defect this reconciliation exists to fix --
            # and named in the build output so the exclusion is visible rather
            # than silent.
            first_party.append(f"{kind}: not from upstream, excluded from the "
                               f"adopted counts: {', '.join(sorted(unlisted))}")
        if unrendered:
            problems.append(f"{kind}: adopted but this report renders no row "
                            f"for it: {', '.join(sorted(unrendered))}")
        if extra_rows:
            problems.append(f"{kind}: this report renders a row for an asset "
                            f"the manifest does not claim: "
                            f"{', '.join(sorted(extra_rows))}")
    if first_party:
        print("note: " + "; ".join(first_party))
    if problems:
        raise SystemExit(
            "adopted inventory does not match .github/AWESOME-COPILOT.md, so "
            "the report would misattribute assets to the pinned upstream "
            "inventory. Update the manifest (and this report's tables) first:\n  "
            + "\n  ".join(problems))



# Upstream availability totals, keyed by the commit they were enumerated at.
# The displayed pin is read from the manifest, so leaving these hardcoded would
# let a refreshed pin label counts taken from a different revision. An unknown
# pin yields None and the report says the inventory was not enumerated there
# rather than asserting a stale figure.
UPSTREAM_INVENTORY_BY_PIN: dict[str, dict[str, int]] = {
    "aa280f28": {"instructions": 190, "agents": 221, "skills": 391,
                 "plugins": 71, "extensions": 20, "hooks": 8, "workflows": 8},
}


def manifest_pin() -> str:
    """Read the upstream pin from .github/AWESOME-COPILOT.md.

    Hardcoding it here meant every regenerated report kept attributing the
    installed files to the original commit after an approved refresh moved the
    manifest on, making the generator's own provenance stale.
    """
    manifest = Path(__file__).resolve().parents[1] / ".github" / "AWESOME-COPILOT.md"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return "unknown (manifest unreadable)"
    found = re.search(r"Pinned at commit:\*{0,2}\s*`([0-9a-f]{7,40})`", text)
    return found.group(1)[:8] if found else "unknown (no pin in manifest)"


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


MARKDOWN_NOW = count_tracked("*.md")
_BASE = _branch_point()
_MD_BEFORE = count_tracked_at(_BASE, "*.md") if _BASE else -1
MARKDOWN_ADDED = (MARKDOWN_NOW - _MD_BEFORE) if _MD_BEFORE >= 0 else -1

ADOPTED_TOTAL = (
    count_adopted("instructions", "instructions/*.instructions.md")
    + count_adopted("agents", "agents/*.agent.md")
    + count_adopted("skills", "skills/*/SKILL.md")
)

ss = getSampleStyleSheet()


def S(name, parent, **kw):
    return ParagraphStyle(name, parent=ss[parent], **kw)


TITLE = S("t", "Title", fontName="Helvetica-Bold", fontSize=21, leading=25,
          textColor=INK, alignment=TA_LEFT, spaceAfter=2)
SUB = S("s", "Normal", fontSize=10.5, leading=14, textColor=MUTED, spaceAfter=0)
H1 = S("h1", "Heading1", fontName="Helvetica-Bold", fontSize=13.5, leading=17,
       textColor=ACCENT, spaceBefore=17, spaceAfter=6)
H2 = S("h2", "Heading2", fontName="Helvetica-Bold", fontSize=11, leading=14,
       textColor=INK, spaceBefore=11, spaceAfter=4)
BODY = S("b", "BodyText", fontSize=9.7, leading=13.6, textColor=INK,
         spaceAfter=7)
CELL = S("c", "BodyText", fontSize=8.3, leading=10.8, textColor=INK,
         spaceAfter=0)
CELLB = S("cb", "BodyText", fontSize=8.3, leading=10.8, textColor=INK,
          spaceAfter=0, fontName="Helvetica-Bold")
MONO = S("m", "BodyText", fontSize=7.1, leading=9.8, textColor=INK,
         spaceAfter=0, fontName="Courier", wordWrap=None, splitLongWords=0)
NOTE = S("n", "BodyText", fontSize=8.6, leading=12, textColor=MUTED,
         spaceAfter=6)

story = []


def rule(space_after=10):
    story.append(HRFlowable(width="100%", thickness=0.7, color=RULE,
                            spaceBefore=3, spaceAfter=space_after))


def tbl(data, widths, header=True, zebra=True, align=None):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0,
              hAlign="LEFT")
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT)]
    if zebra:
        start = 1 if header else 0
        for i in range(start, len(data)):
            if (i - start) % 2 == 1:
                cmds.append(("BACKGROUND", (0, i), (-1, i), BAND))
    if align:
        cmds += align
    t.setStyle(TableStyle(cmds))
    return t


def hdr(*labels):
    return [Paragraph(f'<font color="white"><b>{x}</b></font>', CELL)
            for x in labels]


# ---------------------------------------------------------------- cover block
story.append(Paragraph("Awesome Copilot — Selection Report", TITLE))
story.append(Paragraph(
    "Which customizations were adopted into <b>JoeElder21/Joeyyy</b>, and why", SUB))
story.append(Spacer(1, 9))

meta = [
    [Paragraph("Prepared for", CELL), Paragraph("Joe Elder", CELLB),
     Paragraph("Decision date", CELL), Paragraph("25 July 2026", CELLB)],
    [Paragraph("Prepared by", CELL), Paragraph("Agent 007 / APEX Chief of Staff", CELLB),
     Paragraph("Pull request", CELL), Paragraph("#26", CELLB)],
    [Paragraph("Upstream source", CELL), Paragraph("github/awesome-copilot", CELLB),
     Paragraph("Pinned commit", CELL), Paragraph(manifest_pin(), MONO)],
    [Paragraph("Built", CELL), Paragraph(BUILD_DATE, CELLB),
     Paragraph("", CELL), Paragraph("", CELL)],
]
story.append(tbl(meta, [0.95 * inch, 2.35 * inch, 0.85 * inch, 1.55 * inch],
                 header=False, zebra=False))
story.append(Spacer(1, 4))
rule()

PIN = manifest_pin()
UPSTREAM_INVENTORY = UPSTREAM_INVENTORY_BY_PIN.get(PIN, {})
PRIMARY_AVAILABLE = sum(
    UPSTREAM_INVENTORY.get(k, 0) for k in ("instructions", "agents", "skills")
) or None


def _cell(value) -> str:
    """Render a count, or an explicit not-enumerated marker."""
    return str(value) if value is not None else "not enumerated at this pin"


def _rate(took, avail) -> str:
    return f"{took / avail * 100:.1f}%" if avail else "—"


# ------------------------------------------------------------------- headline
story.append(Paragraph("1. Upstream inventory considered", H1))
story.append(Paragraph(
    "The collection is far larger than any single repository should absorb. "
    f"Every availability figure below was enumerated at pin <b>{PIN}</b>; the "
    "three primary asset classes are what drove the decision. Adoption counts "
    "are measured from the tracked tree at build time. If the manifest pin "
    "moves to a commit whose inventory has not been enumerated, the "
    "availability column says so rather than reusing an older revision's "
    "totals.", BODY))

inv = [hdr("Asset class", "Available upstream", "Adopted", "Adoption rate")]
for cls, avail, took in [
    ("Instructions", UPSTREAM_INVENTORY.get("instructions"),
     count_adopted("instructions", "instructions/*.instructions.md")),
    ("Agents", UPSTREAM_INVENTORY.get("agents"),
     count_adopted("agents", "agents/*.agent.md")),
    ("Skills", UPSTREAM_INVENTORY.get("skills"),
     count_adopted("skills", "skills/*/SKILL.md")),
]:
    inv.append([
        Paragraph(f"<b>{cls}</b>", CELL),
        Paragraph(f"<b>{_cell(avail)}</b>", CELL),
        Paragraph(f'<font color="#1B6B4A"><b>{took}</b></font>', CELL),
        Paragraph(_rate(took, avail), CELL),
    ])
inv.append([
    Paragraph("<b>Total (primary classes)</b>", CELLB),
    Paragraph(f"<b>{_cell(PRIMARY_AVAILABLE)}</b>", CELLB),
    Paragraph(f'<font color="#1B6B4A"><b>{ADOPTED_TOTAL}</b></font>', CELLB),
    Paragraph(f"<b>{_rate(ADOPTED_TOTAL, PRIMARY_AVAILABLE)}</b>", CELLB),
])
for cls in ("plugins", "extensions", "hooks", "workflows"):
    avail = UPSTREAM_INVENTORY.get(cls)
    inv.append([Paragraph(cls.title(), CELL), Paragraph(_cell(avail), CELL),
                Paragraph("0", CELL), Paragraph("—", CELL)])

story.append(tbl(inv, [2.0 * inch, 1.55 * inch, 1.05 * inch, 1.1 * inch],
                 align=[("ALIGN", (1, 0), (-1, -1), "CENTER"),
                        ("LINEABOVE", (0, 4), (-1, 4), 0.9, INK),
                        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#E4E9F2"))]))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "Plugins, extensions, hooks, and workflows were enumerated but not drawn "
    "from. Plugins are bundles of the same agents and skills, so adopting one "
    "would duplicate individually-chosen files; the rest add runtime "
    "machinery this repository does not need.", NOTE))

# ------------------------------------------------------------- selection basis
story.append(PageBreak())
story.append(Paragraph("2. What Joeyyy actually is", H1))
story.append(Paragraph(
    "Selection was made against the measured shape of the repository rather "
    "than a generic Python profile. These counts are from the tracked tree at "
    "the commit the work started from.", BODY))

prof = [hdr("Signal", "Measured", "Consequence for selection")]
for sig, val, why in [
    ("Python source", "54 files",
     "Language-level standards are relevant; web-framework sets are not."),
    # Every other row in this table describes the tree at PRE_INSTALL_BASELINE.
    # Using the current count here silently mixed two time scopes in one table:
    # the pinned tree holds 46 markdown files and the branch tip far more, so
    # the "selection basis" appeared to have been made against files that did
    # not exist when the selection was made. The current figure belongs to the
    # delta note below, which says so explicitly.
    ("Markdown", f"{_MD_BEFORE} files" if _MD_BEFORE >= 0
     else "not measured (baseline commit unreachable)",
     "Contracts, plans, registries, runbooks. Markdown discipline matters "
     "more here than in a typical code repo."),
    ("GitHub Actions", "1 workflow",
     "One CI surface worth hardening — <font face='Courier' size='7.5'>"
     "validate-agent.yml</font>."),
    ("TOML config", "18 files",
     "Roster, corps, and mount registries are configuration-as-contract."),
    ("JSON schemas", "8 files",
     "Packet validation is already schema-driven; no schema tooling needed."),
    ("Test modules", "24 files",
     "A real gate exists, so anything adopted must pass it."),
    ("Domain", "Multi-agent governance",
     "The single strongest signal — it is what made "
     "<font face='Courier' size='7.5'>agent-safety</font> the highest-value "
     "file in the collection."),
]:
    prof.append([Paragraph(f"<b>{sig}</b>", CELL), Paragraph(val, CELL),
                 Paragraph(why, CELL)])

story.append(tbl(prof, [1.35 * inch, 1.0 * inch, 4.35 * inch]))
story.append(Spacer(1, 5))
_md_delta = (
    f"This branch adds {MARKDOWN_ADDED} markdown files, so the tree now carries "
    f"{MARKDOWN_NOW}."
    if MARKDOWN_ADDED >= 0 else
    f"The tree now carries {MARKDOWN_NOW} markdown files; the delta against the "
    "branch point could not be computed here."
)
story.append(Paragraph(
    "The markdown row above is the count at the pinned pre-install baseline, "
    "matching every other row in that table — it describes the repository the "
    "selection was made against, not the branch tip. The delta and the current "
    "total are the generation-time figures: "
    + _md_delta
    + " All three are measured from the tracked tree and the pinned branch "
      "point, not recorded by hand — an earlier version stated 46 and 60 and "
      "was wrong about both.",
    NOTE))

story.append(PageBreak())

# ------------------------------------------------------------------ adopted
story.append(Paragraph(
    f"3. Instructions adopted "
    f"({count_adopted('instructions', 'instructions/*.instructions.md')} of "
    f"{_cell(UPSTREAM_INVENTORY.get('instructions'))})", H1))
story.append(Paragraph(
    "Each file carries its own <font face='Courier' size='8'>applyTo</font> "
    "glob and is applied automatically to matching files. No wrapper or "
    "registration step is involved.", BODY))

ins = [hdr("File", "applyTo", "Reason selected")]
INSTRUCTION_ROWS = [
    ("agent-safety", "**",
     "Safety boundaries, policy enforcement, and auditability for "
     "tool-calling and multi-agent orchestration. Direct hit on the domain."),
    ("agents", "**/*.agent.md",
     "Conventions for the custom agent definitions this repo now carries."),
    ("agent-skills", "**/skills/**/SKILL.md",
     "Conventions for authoring portable skills; matches the installed set."),
    ("github-actions-ci-cd-best-practices", ".github/workflows/*.y[a]ml",
     "Hardening for the one existing workflow and any successor."),
    ("markdown", "**/*.md",
     "CommonMark 0.31.2 discipline across a markdown-heavy contract tree."),
    ("security-and-owasp", "**",
     "OWASP Top 10 2025 plus AI/LLM-specific guidance."),
    ("self-explanatory-code-commenting", "**",
     "Keeps generated Python comments purposeful rather than redundant."),
    ("code-review-generic", "**",
     "Baseline review checklist; excludes itself from the coding agent."),
    ("task-implementation", "**/.copilot-tracking/changes/*.md",
     "Implementation guidance every plan generated by task-planner loads; "
     "vendored because that reference was otherwise dangling."),
]
for f, glob, why in INSTRUCTION_ROWS:
    ins.append([Paragraph(f, MONO),
                Paragraph(glob, MONO),
                Paragraph(why, CELL)])

story.append(tbl(ins, [2.2 * inch, 1.78 * inch, 2.72 * inch]))

story.append(Paragraph(
    f"4. Agents adopted ({count_adopted('agents', 'agents/*.agent.md')} of "
    f"{_cell(UPSTREAM_INVENTORY.get('agents'))})", H1))
story.append(Paragraph(
    "All three are registered in "
    "<font face='Courier' size='8'>docs/AGENT_REGISTRY.md</font>. They are "
    "editor-plane agents: no brain ownership, memory namespace, write target, "
    "or writer lease. Agent 007 remains the sole write-capable native agent.",
    BODY))
ag = [hdr("File", "Role", "Status and limits")]
AGENT_ROWS = [
    ("prompt-engineer", "Prompt rewriting",
     "<b>candidate.</b> Carries a local override, <font face='Courier' "
     "size='7.5'>tools: []</font>. Upstream omits the field, which grants every "
     "built-in and MCP tool; this agent consumes arbitrary user text, so "
     "all-tools access would let prompt injection reach the repository."),
    ("task-planner", "Implementation planning",
     "<b>candidate.</b> Its declared Terraform / Azure / Docs tool names are "
     "not wired into any Copilot MCP configuration, and unrecognized names are "
     "silently ignored, so those capabilities are unavailable in a normal "
     "session. Registering the mounts served Agent 007, not this agent."),
    ("task-researcher", "Research pass",
     "<b>candidate.</b> Vendored because the planner mandatorily invokes it "
     "before any planning; without it the planner blocks on a missing "
     "dependency on every new task. Same unwired-tool limitation."),
]
for f, role, note in AGENT_ROWS:
    ag.append([Paragraph(f, MONO), Paragraph(role, CELL),
               Paragraph(note, CELL)])
story.append(tbl(ag, [1.55 * inch, 1.0 * inch, 4.15 * inch]))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "<b>Removed after review:</b> "
    "<font face='Courier' size='8'>meta-agentic-project-scaffold</font> was "
    "vendored, then removed. It instructs the agent to pull upstream files and "
    "“do nothing else”, copying them as is — bypassing the intake gates the "
    "repository contract mandates. The three discovery skills cover the same "
    "function and route through intake.", NOTE))

story.append(PageBreak())
story.append(Paragraph(
    f"5. Skills adopted ({count_adopted('skills', 'skills/*/SKILL.md')} of "
    f"{_cell(UPSTREAM_INVENTORY.get('skills'))})", H1))
story.append(Paragraph(
    "All three are discovery skills. This is the deliberate core of the "
    "selection: rather than vendoring a large static subset, the repository "
    "gains the ability to re-query the collection and detect drift against "
    "upstream from inside a session.", BODY))
sk = [hdr("Skill", "Function")]
SKILL_ROWS = [
    ("suggest-awesome-github-copilot-instructions",
     "Compares local instructions against upstream; flags additions and "
     "outdated files."),
    ("suggest-awesome-github-copilot-agents",
     "Same for custom agents, avoiding duplicates already present."),
    ("suggest-awesome-github-copilot-skills",
     "Same for skills."),
]
for s, fn in SKILL_ROWS:
    sk.append([Paragraph(s, MONO), Paragraph(fn, CELL)])

# Every rationale table is now defined, so the inventory can be reconciled
# against the manifest AND against what this report actually renders.
reconcile_with_manifest()

story.append(tbl(sk, [2.95 * inch, 3.75 * inch]))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Each needs a <font face='Courier' size='8'>#fetch</font>-capable tool to "
    "reach raw.githubusercontent.com.", NOTE))

# ----------------------------------------------------------------- exclusions
story.append(Paragraph("6. What was excluded, and why", H1))
story.append(Paragraph(
    (f"{PRIMARY_AVAILABLE - ADOPTED_TOTAL} of the {PRIMARY_AVAILABLE} primary "
     "assets were not adopted."
     if PRIMARY_AVAILABLE else
     "The great majority of the collection was not adopted.")
    + " The exclusions fall into a small number of reasons, each of which is a "
    "positive judgement rather than an oversight.", BODY))

ex = [hdr("Excluded group", "Reason")]
for g, r in [
    ("Framework and platform sets — React, Angular, Vue, .NET, Java, Spring, "
     "Azure Functions, Power Platform, Salesforce, Dataverse",
     "No corresponding surface in this repository. Instructions with "
     "<font face='Courier' size='7.5'>applyTo: '**'</font> would inject "
     "irrelevant standards into every request."),
    ("performance-optimization",
     "Scoped to Core Web Vitals and web frameworks. This is a CLI and "
     "orchestration runtime with no browser surface."),
    ("MCP server authoring sets — Python, Go, Java, Kotlin, Rust, Swift, "
     "PHP, Ruby, TypeScript, C#",
     "This repo consumes MCP servers through the mount registry; it does not "
     "author them. Reconsider if that changes."),
    ("Plugins (71)",
     "Bundles of the same agents and skills. Installing one would duplicate "
     "files already chosen individually and pull in unwanted siblings."),
    ("Hooks (8) and workflows (8)",
     "Add runtime machinery and scheduled automation beyond the requested "
     "scope."),
    ("Extensions (20)",
     "Interactive canvases and dashboards; no fit for a governance repo."),
]:
    ex.append([Paragraph(g, CELL), Paragraph(r, CELL)])
story.append(tbl(ex, [2.5 * inch, 4.2 * inch]))

# ------------------------------------------------------------- privacy guard
story.append(PageBreak())
story.append(Paragraph("7. Interaction with the privacy guard", H1))
story.append(Paragraph(
    "Three adopted files are secure-coding guides, so they legitimately contain "
    "illustrative credential handling and a placeholder address that the prose "
    "heuristics in <font face='Courier' size='8'>scripts/privacy_guard.py"
    "</font> cannot tell from real leakage. <b>No pattern is disabled for any "
    "file.</b> The exact false-positive snippets are stripped as literals and "
    "the complete pattern set then runs on what remains, so a real credential "
    "added to one of those same files is still caught.", BODY))

pg = [hdr("Design", "Verdict", "Why")]
pg.append([
    Paragraph("Directory-wide exemption — skip two patterns for everything "
              "under <font face='Courier' size='7.5'>.github/instructions/"
              "</font>", CELL),
    Paragraph('<font color="#8A5A00"><b>rejected</b></font>', CELL),
    Paragraph("A tracked <font face='Courier' size='7.5'>local.instructions.md"
              "</font> holding a real address and a real credential passed the "
              "scan. Any file later added or hand-authored there inherited the "
              "exemption.", CELL),
])
pg.append([
    Paragraph("Per-file, per-pattern relaxation — one file gives up one "
              "pattern", CELL),
    Paragraph('<font color="#8A5A00"><b>rejected</b></font>', CELL),
    Paragraph("Still too coarse. Disabling a whole pattern for a whole file "
              "meant a genuine credential appended to that same file also "
              "passed.", CELL),
])
pg.append([
    Paragraph("<b>Exact-literal stripping</b> — seven pinned snippets across "
              "three named files, every pattern applied to the rest", CELL),
    Paragraph('<font color="#1B6B4A"><b>in force</b></font>', CELL),
    Paragraph("Only those literal strings are invisible. "
              "<font face='Courier' size='7.5'>applicable_patterns()</font> "
              "returns every pattern for every path, so a future exemption "
              "must be a visible edit to a reviewed function. Both rejected "
              "designs are permanent regression tests.", CELL),
])
story.append(tbl(pg, [2.35 * inch, 0.95 * inch, 3.4 * inch]))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "<b>The guard demonstrated its value during this work.</b> It rejected two "
    "of the author's own additions — a comment inside "
    "<font face='Courier' size='8'>privacy_guard.py</font> and body text in "
    "<font face='Courier' size='8'>.github/AWESOME-COPILOT.md</font> — because "
    "both quoted the credential-shaped examples they were describing. Both "
    "were rewritten.", NOTE))

# ---------------------------------------------------------------- verification
story.append(Paragraph("8. Verification", H1))
story.append(Paragraph(
    "Every row below is produced by running that gate at the moment this "
    "document was generated. Nothing here is a remembered result.", BODY))
ver = [hdr("Gate", "Result at build time")]
for g, r in [
    *(
        (f"scripts/{script}", run_gate(script))
        for script in (
            "privacy_guard.py",
            "validate_specialist_corps.py",
            "verify_runtime_stack.py",
            "verify_mcp_mounts.py",
        )
    ),
    ("python -m unittest discover -s tests", measure_test_suite()),
]:
    ver.append([Paragraph(g, MONO), Paragraph(r, CELL)])
story.append(tbl(ver, [2.6 * inch, 4.1 * inch]))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "CI status is deliberately absent: this generator cannot observe GitHub, so "
    "publishing a CI row here would be an unverified claim. Read it on the pull "
    "request instead.", NOTE))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Scope of change: the adopted instruction, agent, and skill files are "
    "editor-side authoring aids and alter no runtime or brain behaviour. Three "
    "changes to existing behaviour did occur and are not covered by that "
    "statement \u2014 the privacy-guard scoping in section 7; the trusted "
    "launcher, whose grant format now signs the authorized identity, which "
    "enforces each mount's agent allowlist for every non-wildcard mount, "
    "requires --agent when minting a grant, and therefore changes the "
    "pre-existing Civil 3D activation workflow; the Agent 007 "
    "contract, which now activates on either name, emits a changed activation "
    "line, requires the discovery skills to be run rather than listed, and "
    "imposes the five-line ops brief, front-loaded validation, and "
    "policy/behavioral commit split; and two new grant-gated MCP mounts, "
    "registered but not activated. Read this report alongside the commit "
    "history, not in place of it.", NOTE))

# -------------------------------------------------------------------- closing
story.append(Paragraph("9. Standing recommendation", H1))
story.append(Paragraph(
    "Re-run the three discovery skills periodically rather than growing the "
    "vendored set by hand. They report drift against upstream and propose "
    "additions scoped to the repository as it exists at that time, which keeps "
    f"the {_rate(ADOPTED_TOTAL, PRIMARY_AVAILABLE)} adoption rate a deliberate position "
    "rather than a snapshot that "
    "quietly rots. Bump the pinned commit in "
    "<font face='Courier' size='8'>.github/AWESOME-COPILOT.md</font> whenever "
    "files are refreshed.", BODY))
rule(6)
story.append(Paragraph(
    "Upstream content is authored by third-party contributors and carries the "
    "MIT licence. Review any file before relying on it, particularly the "
    "agents, which declare broad tool permissions.", NOTE))


def furniture(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.9 * inch, 0.72 * inch, LETTER[0] - 0.9 * inch, 0.72 * inch)
    canvas.setFont("Helvetica", 7.4)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.9 * inch, 0.55 * inch,
                      "Agent 007 / APEX Chief of Staff  ·  "
                      "awesome-copilot selection report  ·  "
                      "JoeElder21/Joeyyy PR #26")
    canvas.drawRightString(LETTER[0] - 0.9 * inch, 0.55 * inch,
                           f"Page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(
    OUT, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.95 * inch,
    title="Awesome Copilot — Selection Report",
    author="Agent 007 / APEX Chief of Staff",
    subject="Adoption decision for github/awesome-copilot in JoeElder21/Joeyyy",
)
Path(OUT).parent.mkdir(parents=True, exist_ok=True)
doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
print("wrote", OUT)
