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
# NB: distinct from is_vendored() below, which means "inside a gitlink submodule".
# This concerns vendored *documentation* tracked directly by this repository.
CONTACT_HEURISTIC_PATTERNS = frozenset({"email address", "street address"})
# RFC 2606 / RFC 6761 names, reserved so they can never route to a real mailbox.
# domain.com, email.com, mail.com, acme.com and yourcompany.com are deliberately NOT
# here: they look like filler but are live registered domains, so exempting them would
# waive a real address.
RESERVED_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.net",
        "example.org",
        "example.edu",
        "example",
        "test",
        "invalid",
        "localhost",
        "local",
    }
)
RESERVED_EMAIL_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
# Complete fixture addresses, matched whole and case-insensitively. A word-level
# allowlist is unsafe here: a common street word appearing anywhere after the house
# number would waive a real address that merely happens to contain it.
FIXTURE_STREET_ADDRESSES = frozenset(
    f"{number} {name} {suffix}"
    for number, name in (("123", "main"), ("456", "oak"), ("1", "example"), ("1", "test"))
    for suffix in ("st", "street", "ave", "avenue")
)
EMAIL_MATCH = PATTERNS["email address"]
STREET_MATCH = PATTERNS["street address"]


def _email_is_reserved(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].lower()
    return domain in RESERVED_EMAIL_DOMAINS or domain.endswith(RESERVED_EMAIL_SUFFIXES)


def _street_is_fixture(address: str) -> bool:
    normalized = " ".join(address.split()).strip(".,").lower()
    return normalized in FIXTURE_STREET_ADDRESSES


def vendored_contact_findings(text: str) -> list[str]:
    """Contact matches in vendored docs that are not recognized reserved examples."""
    labels = []
    for match in EMAIL_MATCH.finditer(text):
        if not _email_is_reserved(match.group(0)):
            labels.append("email address")
    for match in STREET_MATCH.finditer(text):
        if not _street_is_fixture(match.group(0)):
            labels.append("street address")
    return labels
DOCUMENTATION_ONLY_PREFIXES = (Path(".claude/agents/awesome-claude-agents"),)
# Credential assignments in vendored docs are checked by value rather than waived by
# path, so a real secret committed under a vendored prefix is still caught. Only a
# quoted literal counts: in these samples an unquoted right-hand side is always an
# expression rather than a secret — a request-header lookup, a Terraform variable
# reference, or a type annotation — and carries no literal value to leak.
VENDORED_CREDENTIAL_LITERAL = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
    r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token)"
    r"\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)
# The unquoted `.env` / shell form, which carries real secrets just as often - a
# key name, an equals sign, and a bare value with no quotes around it. Captured
# separately because the quoted rule above cannot see it.
VENDORED_CREDENTIAL_BARE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
    r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token)"
    r"\s*[:=]\s*([^\s#\"']{8,})"
)
# Unquoted right-hand sides are classified against a CLOSED allowlist of the exact
# expressions that appear in the vendored tree, not by a heuristic.
#
# Every structural heuristic tried here leaked, each in the same way: it searched for
# some marker of "code" inside the value, and a real secret containing that marker was
# waived. A dot waived every JWT; identifier shape waived every alphanumeric key; a
# bracket waived any password containing punctuation. The set of things a secret can
# look like is open, so it cannot be enumerated — but the set of expressions actually
# present here is small and closed, so that is what gets enumerated instead.
#
# A sync that introduces a new unquoted expression fails the guard. That is intended:
# a human should look at it and add it deliberately rather than have a rule guess.
VENDORED_BARE_EXPRESSIONS = frozenset(
    {
        "Annotated[str",
        "Password",
        "encode_token(",
        "password",
        "request.META.get(",
        "self.jwt_manager.create_access_token(user)",
        "tokens[:access_token]",
        "var.database_password",
    }
)
# Complete placeholder forms. These must match the WHOLE literal, never a substring:
# a substring test would waive a live credential that merely happens to contain a
# common word, so a real secret would silently pass here.
PLACEHOLDER_VALUE_PATTERNS = (
    # Conventional dummy values: testpass123, example-key, dummy_token_1. At most one
    # trailing segment is allowed: an unbounded tail would waive live values that
    # merely begin with a dummy word, e.g. "testing-servers-real-key-771".
    # Only the dummy word itself is case-insensitive. The tail is deliberately
    # lowercase-only: mixed case signals generated entropy, not documentation filler,
    # so "test-aKq93LmZx0Pp" is reported while "testpass123" is not.
    re.compile(
        r"\A(?i:test|example|sample|dummy|fake|placeholder|redacted|changeme"
        r"|change[-_]me|foo|bar|baz|x{3,})[a-z0-9]*(?:[-_][a-z0-9]+)?\Z"
    ),
    # Bare words used as their own sample value: password, secret, token.
    re.compile(r"(?i)\A(?:pass)?word\Z|\A(?:secret|token|credential)s?\Z"),
    # Vendor test-mode keys, which are non-live by construction: sk_test_123.
    re.compile(r"(?i)\A(?:sk|pk|rk)_test_[a-z0-9]+\Z"),
    # Fill-me-in markers: <your-api-key>, {{token}}, ${API_KEY}, $API_KEY.
    re.compile(r"\A<[^>]+>\Z"),
    re.compile(r"\A\{\{[^}]+\}\}\Z"),
    re.compile(r"(?i)\A\$\{?[a-z_][a-z0-9_]*\}?\Z"),
    # your-api-key / my_token, where the whole value is the instruction. The trailing
    # noun is enumerated on purpose: a trailing wildcard here would waive live values
    # such as a "my-secret-<env>-<digits>" key.
    re.compile(
        r"(?i)\A(?:your|my|the)[-_]"
        r"(?:api[-_]?key|access[-_]?token|token|secret|password|credential|key|value)s?\Z"
    ),
)


PLACEHOLDER_MAX_LENGTH = 20


def is_placeholder_value(value: str) -> bool:
    """True when the whole literal is a recognized documentation placeholder.

    Length-capped as a backstop: real credentials are long, and a short dummy value
    is the only thing these forms are meant to cover.
    """
    if len(value) > PLACEHOLDER_MAX_LENGTH:
        return False
    return any(pattern.match(value) for pattern in PLACEHOLDER_VALUE_PATTERNS)


def is_vendored_documentation(relative: Path) -> bool:
    return any(
        prefix == relative or prefix in relative.parents
        for prefix in DOCUMENTATION_ONLY_PREFIXES
    )


def applicable_patterns(relative: Path) -> dict[str, re.Pattern[str]]:
    """Return the patterns enforced wholesale for ``relative``.

    Vendored documentation drops the contact heuristics and the blanket
    credential-assignment pattern; the latter is replaced by the stricter,
    value-aware :func:`vendored_credential_findings` rather than dropped outright.
    """
    if not is_vendored_documentation(relative):
        return PATTERNS
    return {
        label: pattern
        for label, pattern in PATTERNS.items()
        if label not in CONTACT_HEURISTIC_PATTERNS and label != "credential assignment"
    }


def vendored_credential_findings(text: str) -> list[str]:
    """Credential literals in vendored docs that are not recognized placeholders."""
    labels = []
    for match in VENDORED_CREDENTIAL_LITERAL.finditer(text):
        if not is_placeholder_value(match.group(1)):
            labels.append("credential assignment")
    for match in VENDORED_CREDENTIAL_BARE.finditer(text):
        # Drop a trailing separator left by the surrounding source line, so that e.g.
        # a bare `password,` is classified on the word itself.
        value = match.group(1).rstrip(",;")
        if value in VENDORED_BARE_EXPRESSIONS or is_placeholder_value(value):
            continue
        labels.append("credential assignment")
    return labels




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
        for label, pattern in applicable_patterns(relative).items():
            if pattern.search(text):
                findings.append(f"{relative}: possible {label}")
        if is_vendored_documentation(relative):
            # Credential and contact matches are re-checked by value here rather than
            # waived by path, so a real secret or a real address committed under the
            # vendored prefix is still reported.
            for label in vendored_credential_findings(text):
                findings.append(f"{relative}: possible {label}")
            for label in vendored_contact_findings(text):
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
