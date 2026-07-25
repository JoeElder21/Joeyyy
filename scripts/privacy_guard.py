"""Repository-wide public-source privacy and secret scanner."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
GITLINK_MODE = "160000"
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
    "credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
        r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token)"
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


def submodule_paths(root: Path = ROOT) -> frozenset[str]:
    """Return the repository-relative paths declared in ``.gitmodules``.

    Parsed from the file rather than assumed from a directory name so the set
    tracks whatever is actually declared. Missing file means no submodules.
    """
    gitmodules = root / ".gitmodules"
    if not gitmodules.exists():
        return frozenset()
    return frozenset(
        match.group(1).strip()
        for match in re.finditer(
            r"^\s*path\s*=\s*(.+?)\s*$",
            gitmodules.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def is_vendored(path: Path, root: Path = ROOT) -> bool:
    """Report whether ``path`` lies inside a vendored third-party submodule.

    Submodules record only a gitlink commit here, so their file contents are
    never published by this repository and fall outside the public-source
    privacy contract this scanner enforces — upstream placeholder addresses
    and maintainer contacts are the upstream project's to police.

    Scoped to the declared submodule paths themselves, so this repository's
    own files under ``vendor/`` (its README) stay covered by the contract.
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(
        relative.is_relative_to(submodule) for submodule in submodule_paths(root)
    )


def repository_files(root: Path = ROOT) -> list[Path]:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip() == "true":
        # -s exposes the index mode so gitlinks can be dropped by mode. Testing
        # the filesystem instead (``is_file()``) would also silently drop a
        # tracked dangling symlink — e.g. ``token.json -> /home/joe/secret`` —
        # which is exactly the kind of entry this scanner exists to catch.
        tracked = subprocess.run(
            ["git", "ls-files", "-s", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout.split(b"\0")
        paths: list[Path] = []
        for entry in tracked:
            if not entry:
                continue
            metadata, _, name = entry.decode("utf-8").partition("\t")
            if metadata.split()[0] == GITLINK_MODE:
                continue
            path = root / name
            if not is_vendored(path, root):
                paths.append(path)
        return paths
    return [
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and not is_vendored(path, root)
    ]


def scan_repository(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in repository_files(root):
        relative = path.relative_to(root)
        if path.name.lower() in PROHIBITED_FILENAMES:
            findings.append(f"{relative}: prohibited private filename")
        if path.suffix.lower() in PROHIBITED_ARTIFACT_SUFFIXES:
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
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative}: possible {label}")
    return findings


def main() -> int:
    findings = scan_repository()
    if findings:
        print("\n".join(findings))
        return 1
    print("Privacy guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
