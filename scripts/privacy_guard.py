"""Repository-wide public-source privacy and secret scanner."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

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
LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1"
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
    """Return the repository-relative paths *declared* in ``.gitmodules``.

    This reports a declaration, not a fact, and must never gate a scan — see
    ``gitlink_paths`` for the index-proven set. Its purpose is drift
    detection: comparing the two sets surfaces a ``.gitmodules`` entry that no
    longer matches a real gitlink.
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


def run_git(args: list[str], root: Path = ROOT) -> subprocess.CompletedProcess | None:
    """Run a git command, returning None when git itself is unavailable.

    Minimal containers and extracted source archives may have no git binary at
    all. ``subprocess.run`` raises ``FileNotFoundError`` in that case
    regardless of ``check``, so callers that only inspect ``returncode`` still
    crash. These scanners must degrade to "nothing provable from the index"
    rather than take the whole run down with them.
    """
    try:
        return subprocess.run([*args], cwd=root, capture_output=True, check=False)
    except OSError:
        return None


def index_is_authoritative(root: Path = ROOT) -> bool:
    """Report whether git's index describes ``root`` itself, not an ancestor.

    ``git rev-parse --is-inside-work-tree`` answers "is there a repository
    somewhere above me", which is a weaker question than the one every caller
    here means. An extracted source archive dropped anywhere beneath an
    unrelated checkout answers ``true`` and then reports on the *ancestor's*
    index, under which none of the archive's files are tracked.

    That fails in the worst direction. ``tracked_paths`` returns an empty set
    rather than ``None``, so the caller believes it has a readable index that
    tracks nothing, and every exclusion built on it fires on every path:
    ``repository_files`` yields nothing and the privacy scan passes a tree it
    never opened. Comparing ``--show-toplevel`` to ``root`` keeps the archive
    on the no-index path, where nothing is excluded and everything is scanned.
    """
    probe = run_git(["git", "rev-parse", "--show-toplevel"], root)
    if probe is None or probe.returncode != 0:
        return False
    toplevel = probe.stdout.decode("utf-8", errors="surrogateescape").strip()
    if not toplevel:
        return False
    try:
        return Path(toplevel).resolve() == root.resolve()
    except OSError:
        return False


def _parse_ls_files(stdout: bytes) -> list[tuple[str, str]]:
    """Parse ``git ls-files -s -z`` output into (mode, path) pairs.

    The mode metadata is ASCII, but a path is an arbitrary byte string on
    POSIX — git happily tracks filenames that are not valid UTF-8. Decoding
    the whole entry strictly raises ``UnicodeDecodeError`` and takes down the
    entire scan over one unrelated filename, so the two halves are decoded
    separately and the path round-trips through ``surrogateescape``.
    """
    entries: list[tuple[str, str]] = []
    for entry in stdout.split(b"\0"):
        if not entry:
            continue
        metadata, _, name = entry.partition(b"\t")
        fields = metadata.decode("ascii", errors="replace").split()
        if not fields:
            continue
        entries.append((fields[0], name.decode("utf-8", errors="surrogateescape")))
    return entries


def gitlink_paths(root: Path = ROOT) -> frozenset[str]:
    """Return the repository-relative paths the git index proves are submodules.

    Derived from the ``160000`` index mode, never from ``.gitmodules`` text: a
    stale or malformed ``path =`` entry naming a tracked regular directory
    would otherwise exclude first-party files from every scan that consults
    this. Returns empty where no gitlink is provable — outside a git work
    tree, or where git is not installed.
    """
    if not index_is_authoritative(root):
        return frozenset()
    listing = run_git(["git", "ls-files", "-s", "-z"], root)
    if listing is None or listing.returncode != 0:
        return frozenset()
    return frozenset(
        name for mode, name in _parse_ls_files(listing.stdout) if mode == GITLINK_MODE
    )


def tracked_paths(root: Path = ROOT) -> frozenset[str] | None:
    """Return every repository-relative path the index tracks, or None.

    Lets a caller tell this repository's own files from installed dependency
    content that merely shares a directory name.

    ``None`` means the index could not be read at all — an extracted archive,
    no git binary, or an index belonging to some ancestor repository rather
    than to ``root`` — and is deliberately distinct from an empty set. The two
    demand opposite fallbacks: an unreadable index means nothing can be ruled
    *out*, while an empty index means nothing is tracked. Collapsing them into
    one empty set makes every path look untracked, which silently disables any
    exclusion built on this.
    """
    if not index_is_authoritative(root):
        return None
    listing = run_git(["git", "ls-files", "-s", "-z"], root)
    if listing is None or listing.returncode != 0:
        return None
    return frozenset(name for _mode, name in _parse_ls_files(listing.stdout))


def is_vendored(
    path: Path, root: Path = ROOT, gitlinks: frozenset[str] | None = None
) -> bool:
    """Report whether ``path`` lies inside a vendored third-party submodule.

    Submodules record only a gitlink commit here, so their file contents are
    never published by this repository and fall outside the public-source
    privacy contract this scanner enforces — upstream placeholder addresses
    and maintainer contacts are the upstream project's to police.

    Scoped to index-proven gitlinks, so this repository's own files under
    ``vendor/`` (its README) stay covered by the contract, and so a drifted
    ``.gitmodules`` cannot exclude anything.

    This is for filesystem walks, which do descend into a checked-out
    submodule's working tree. Scans driven by ``git ls-files`` do not need it:
    that listing never recurses into a submodule's own index.

    Pass ``gitlinks`` from ``gitlink_paths()`` when calling this in a loop.
    Recomputing it per path spawns two git processes per file — measured at
    86,634 processes and 174 seconds for a single pass over a checkout with
    the submodules initialized.
    """
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if gitlinks is None:
        gitlinks = gitlink_paths(root)
    return any(relative.is_relative_to(gitlink) for gitlink in gitlinks)


def repository_files(root: Path = ROOT) -> list[Path]:
    # index_is_authoritative rather than a bare work-tree probe: an archive
    # extracted beneath an unrelated checkout would otherwise list that
    # repository's index, find none of these files tracked, and return an
    # empty file list — a scan of nothing, reported as a pass.
    #
    # run_git rather than subprocess.run: with no git binary installed the
    # latter raises FileNotFoundError regardless of check=False, taking down a
    # scan that should instead fall back to walking the filesystem.
    listing = None
    if index_is_authoritative(root):
        # -s exposes the index mode so gitlinks can be dropped by mode. Testing
        # the filesystem instead (``is_file()``) would also silently drop a
        # tracked dangling symlink — e.g. ``token.json -> /home/joe/secret`` —
        # which is exactly the kind of entry this scanner exists to catch.
        listing = run_git(["git", "ls-files", "-s", "-z"], root)
    if listing is not None and listing.returncode == 0:
        # The index mode is the only evidence used here. `.gitmodules` text is
        # deliberately not consulted: a stale or malformed `path =` entry
        # naming a tracked regular directory would otherwise exclude
        # first-party files this repository really does publish. Submodule
        # contents never reach this list anyway — `git ls-files` does not
        # recurse into a submodule's own index.
        return [
            root / name
            for mode, name in _parse_ls_files(listing.stdout)
            if mode != GITLINK_MODE
        ]
    gitlinks = gitlink_paths(root)
    return [
        path
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and not is_vendored(path, root, gitlinks)
    ]


def scan_repository(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    # A submodule's *path* is tracked by this repository even though its
    # contents are not, so the name itself is published and stays subject to
    # every rule that governs published text. Excluding gitlinks from the
    # content scan must not exclude them from these: a submodule added as
    # `token.json` would otherwise pass a scan that exists to forbid exactly
    # that name.
    #
    # The pattern set applies to the path string too, not only the filename
    # and suffix rules. A path is free-form text this repository publishes: a
    # submodule named after a client contact carries that person's name and
    # address in the path itself without matching any prohibited filename, and
    # with no `.gitmodules` entry to catch it incidentally there is nothing
    # else in the scan that would ever read it.
    for name in sorted(gitlink_paths(root)):
        relative = Path(name)
        if relative.name.lower() in PROHIBITED_FILENAMES:
            findings.append(f"{relative}: prohibited private filename (submodule path)")
        if relative.suffix.lower() in PROHIBITED_ARTIFACT_SUFFIXES:
            findings.append(
                f"{relative}: non-source artifact type is not allowed in this public repository"
            )
        for label, pattern in PATTERNS.items():
            if pattern.search(name):
                findings.append(f"{relative}: possible {label} (submodule path)")
    for path in repository_files(root):
        relative = path.relative_to(root)
        if path.name.lower() in PROHIBITED_FILENAMES:
            findings.append(f"{relative}: prohibited private filename")
        if path.suffix.lower() in PROHIBITED_ARTIFACT_SUFFIXES:
            findings.append(
                f"{relative}: non-source artifact type is not allowed in this public repository"
            )
        try:
            if path.is_symlink():
                # What git publishes for a symlink is the *target string* it
                # stores as the blob, not the bytes of whatever that string
                # resolves to. Reading through would scan the wrong content
                # entirely: a link named innocuously and pointing at a benign
                # existing file still publishes its target path, which may
                # carry a client name, an address, or a private directory
                # layout. Dangling links are covered too — os.readlink needs
                # no target.
                raw = os.readlink(path).encode("utf-8", errors="surrogateescape")
            else:
                raw = path.read_bytes()
        except OSError as exc:
            findings.append(f"{relative}: unreadable ({exc})")
            continue
        if b"\0" in raw:
            findings.append(
                f"{relative}: binary file is not allowed in this public source tree"
            )
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                f"{relative}: non-UTF-8 file is not allowed in this public source tree"
            )
            continue
        if text.startswith(LFS_POINTER_PREFIX):
            findings.append(
                f"{relative}: Git LFS pointer is not allowed in this public source tree"
            )
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
