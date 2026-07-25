"""Repository-wide public-source privacy and secret scanner."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PROHIBITED_FILENAMES = {
    ".env",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "token.json",
    "memory.db",
    "memory.sqlite",
    "memory.sqlite3",
}
PROHIBITED_ARTIFACT_SUFFIXES = {
    ".7z",
    ".avi",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".tar",
    ".tif",
    ".tiff",
    ".wav",
    ".xls",
    ".xlsx",
    ".zip",
}
LFS_POINTER_PREFIX = "version https://git-lfs.github.com/" "spec/v1"
PATTERNS = {
    "secret token": re.compile(
        r"\b(?:(?:sk|gh[opusr]|github_pat|xox[baprs]|npm)[-_][A-Za-z0-9_-]{12,}"
        r"|AIza[A-Za-z0-9_-]{20,})\b"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "cloud access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    # Credential-bearing names. A Terraform or GitHub token carries no
    # distinguishing prefix, so for those the name is the only signal there is
    # and "secret token" above cannot help. Every credential env var named in a
    # config/mcp_mounts.toml activation must appear here;
    # tests/test_privacy.py::test_every_mount_credential_name_is_detectable
    # fails when a new mount introduces one that is not covered.
    "credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
        r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token"
        r"|tfe?[_-]?token|terraform[_-]?token"
        r"|gh[_-]?token|github[_-]?token|github[_-]?personal[_-]?access[_-]?token"
        r"|azure[_-]?client[_-]?secret|aps[_-]?client[_-]?secret)"
        r"\s*[:=]\s*(?:[\"'][^\"']{8,}[\"']|[^\s#\"']{8,})"
    ),
    "bearer credential": re.compile(
        r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}"
    ),
    "email address": re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
    ),
    "phone number": re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"
    ),
    "raw Drive or Docs link": re.compile(
        r"https://(?:drive|docs)\.google\.com/", re.IGNORECASE
    ),
    "street address": re.compile(
        r"\b[1-9]\d{1,5}\s+(?:[A-Za-z0-9.'-]+\s+){1,6}"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Boulevard|Blvd)\b",
        re.IGNORECASE,
    ),
}


# Vendored third-party Copilot instruction docs (see .github/AWESOME-COPILOT.md).
# Some are secure-coding guides holding illustrative credential handling and
# placeholder addresses that the prose heuristics cannot tell from real leakage.
#
# NO PATTERN IS EVER DISABLED FOR ANY FILE. Instead, the exact known
# false-positive snippets are removed from the text and the complete pattern set
# then runs on what remains. So a real credential added to one of these files
# later is still caught, because only these literal strings are invisible.
#
# Two earlier designs were rejected in review. A directory-wide exemption let
# any new file under .github/instructions/ bypass two checks entirely. Scoping
# that exemption per file was still too coarse: disabling `credential
# assignment` for a whole file meant a genuine credential appended to it also
# passed. Exact-literal stripping has neither hole.
#
# Literals are assembled at runtime so this source file does not trip PATTERNS.
_K = "API" + "_KEY"
_SK = "sk" + "_live_"
_PW = "pass" + "word"
PLACEHOLDER_LITERALS: dict[Path, tuple[str, ...]] = {
    Path(".github/instructions/security-and-owasp.instructions.md"): (
        _K + " = '" + _SK + "abc123def456'",
        _K + " = process.env." + _K + ";",
        _PW + " = String(req.body." + _PW + ");",
        _PW + ": req.body." + _PW,
    ),
    Path(".github/instructions/code-review-generic.instructions.md"): (
        _K + ' = "' + _SK + 'abc123xyz789"',
        _K + " = process.env." + _K + ";",
    ),
    Path(".github/instructions/self-explanatory-code-commenting.instructions.md"): (
        "username" + "@" + "domain.extension",
    ),
}


def strip_known_placeholders(relative: Path, text: str) -> str:
    """Remove the exact documented false-positive snippets for one file.

    Everything else in the file is still scanned by every pattern.
    """
    for literal in PLACEHOLDER_LITERALS.get(relative, ()):
        text = text.replace(literal, "")
    return text


def applicable_patterns(relative: Path) -> dict[str, re.Pattern[str]]:
    """Every pattern, for every file. No path is ever exempted from a check.

    Retained as the single place a future exemption would have to be introduced,
    so that adding one is a visible change to a reviewed function rather than a
    quiet condition inside the scan loop.
    """
    return PATTERNS


def repository_files(root: Path = ROOT) -> list[Path]:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip() == "true":
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.split(b"\0")
        return [root / item.decode("utf-8") for item in tracked if item]
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts
    ]


def scan_repository(root: Path = ROOT) -> list[str]:
    """Scan every git-tracked text file. See scan_paths() for untracked input."""
    return _scan_files(repository_files(root), root)


def _scan_files(
    paths: list[Path], root: Path = ROOT,
    destinations: dict[Path, Path] | None = None,
) -> list[str]:
    """Scan `paths`. `destinations` maps a scanned path to the repo-relative
    path it is destined for, so a candidate sitting in a temp directory is
    matched against the allowlists under its intended name rather than its
    current one.
    """
    destinations = destinations or {}
    findings: list[str] = []
    for path in paths:
        destination = destinations.get(path)
        if destination is not None:
            relative = destination
        else:
            try:
                relative = path.relative_to(root)
            except ValueError:
                relative = path
        # Name and suffix checks read the EFFECTIVE path, not the source path.
        # Keying them on the temp name let `--as credentials.json` or
        # `--as docs/x.pdf` pass the pre-install gate on a benign temp file that
        # scan_repository() rejects the moment it is installed -- the gate would
        # approve exactly what the repository scan forbids.
        if relative.name.lower() in PROHIBITED_FILENAMES:
            findings.append(f"{relative}: prohibited private filename")
        if relative.suffix.lower() in PROHIBITED_ARTIFACT_SUFFIXES:
            findings.append(
                f"{relative}: non-source artifact type is not allowed in this public repository"
            )
        try:
            raw = path.read_bytes()
        except OSError as exc:
            findings.append(f"{relative}: unreadable ({exc})")
            continue
        if b"\0" in raw:
            findings.append(f"{relative}: binary file is not allowed in this public source tree")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{relative}: non-UTF-8 file is not allowed in this public source tree")
            continue
        if text.startswith(LFS_POINTER_PREFIX):
            findings.append(f"{relative}: Git LFS pointer is not allowed in this public source tree")
        scannable = strip_known_placeholders(relative, text)
        for label, pattern in applicable_patterns(relative).items():
            if pattern.search(scannable):
                findings.append(f"{relative}: possible {label}")
    return findings


def scan_paths(
    paths: list[Path], root: Path = ROOT,
    destinations: dict[Path, Path] | None = None,
) -> list[str]:
    """Scan exactly these paths, tracked or not, recursing into directories.

    `scan_repository()` enumerates via `git ls-files`, so a freshly downloaded
    file is invisible to it until staged. That made it useless as an intake gate
    for the one thing intake exists to check -- newly fetched upstream content,
    bundled executable assets included. Use this to scan candidate files before
    they are added.
    """
    targets: list[Path] = []
    for given in paths:
        candidate = given if given.is_absolute() else (root / given)
        if candidate.is_dir():
            targets.extend(
                child for child in sorted(candidate.rglob("*"))
                if child.is_file()
                and ".git" not in child.parts
                and "__pycache__" not in child.parts
            )
        elif candidate.is_file():
            targets.append(candidate)
        else:
            targets.append(candidate)  # reported as unreadable below
    resolved = {
        (given if given.is_absolute() else (root / given)): dest
        for given, dest in (destinations or {}).items()
    }
    return _scan_files(targets, root, resolved)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(
            "usage: privacy_guard.py [PATH ...] [--as DEST]\n\n"
            "  no arguments  scan every git-tracked text file\n"
            "  PATH ...      scan exactly these files/directories, tracked or\n"
            "                not. Use this on newly downloaded content before\n"
            "                adding it, since tracked-only scanning cannot see it.\n"
            "  --as DEST     treat the single given PATH as though it already sat\n"
            "                at repo-relative DEST. Needed to scan a candidate in\n"
            "                a temp directory against the per-file allowlists, so\n"
            "                intake can run before the file is installed."
        )
        return 0

    destinations: dict[Path, Path] = {}
    if "--as" in argv:
        marker = argv.index("--as")
        if marker + 1 >= len(argv):
            print("--as requires a repo-relative destination path")
            return 2
        destination = Path(argv[marker + 1])
        argv = argv[:marker] + argv[marker + 2:]
        if len(argv) != 1:
            print("--as applies to exactly one PATH")
            return 2
        destinations[Path(argv[0])] = destination

    if argv:
        findings = scan_paths([Path(arg) for arg in argv], destinations=destinations)
        label = f"Privacy guard passed for {len(argv)} given path(s)."
    else:
        findings = scan_repository()
        label = "Privacy guard passed."

    if findings:
        print("\n".join(findings))
        return 1
    print(label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
