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
# Patterns that match the shape of a real credential and effectively never fire on
# documentation. These stay armed everywhere, including vendored trees.
HIGH_CONFIDENCE_PATTERNS = frozenset(
    {"secret token", "private key", "cloud access key", "bearer credential"}
)
# Contact heuristics re-checked by value in vendored paths. Phone numbers are NOT in
# this set: nothing in the vendored tree matches that pattern, so it stays armed
# everywhere at no cost. Address and email matches are re-examined individually by
# vendored_contact_findings rather than waived wholesale - a path-wide skip would
# suppress a real employee address or postal address committed to this public repo.
CONTACT_HEURISTIC_PATTERNS = frozenset({"email address", "street address"})
# RFC 2606 / RFC 6761 names reserved so they can never route to a real mailbox.
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
        "domain.com",
        "email.com",
        "mail.com",
        "yourcompany.com",
        "acme.com",
    }
)
RESERVED_EMAIL_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
# Street names used as documentation fixtures rather than real locations.
FIXTURE_STREET_NAMES = frozenset(
    {"main", "oak", "elm", "test", "example", "sample", "fake", "any", "first", "second"}
)
EMAIL_MATCH = PATTERNS["email address"]
STREET_MATCH = PATTERNS["street address"]


def _email_is_reserved(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].lower()
    return domain in RESERVED_EMAIL_DOMAINS or domain.endswith(RESERVED_EMAIL_SUFFIXES)


def _street_is_fixture(address: str) -> bool:
    words = [word.strip(".,").lower() for word in address.split()]
    return any(word in FIXTURE_STREET_NAMES for word in words[1:])


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
# Deciding which unquoted values are code, rather than which are secrets. An allowlist
# of "safe" secret characters fails open: base64 and URL-safe keys carry +, /, = and .,
# so requiring word characters alone silently waived them. Detect the expression forms
# instead - a call, a subscript, an attribute lookup, a trailing separator - and treat
# everything else as a candidate credential.
CODE_EXPRESSION = re.compile(
    r"[()\[\]{}]"          # call, subscript, literal, or f-string braces
    r"|\.[A-Za-z_]"        # attribute lookup: obj.attr
    r"|::|->|=>"           # scope / lambda / arrow operators
    r"|[,;]\s*\Z"          # trailing separator left by the surrounding code
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
        value = match.group(1)
        if not CODE_EXPRESSION.search(value) and not is_placeholder_value(value):
            labels.append("credential assignment")
    return labels


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
        for label, pattern in applicable_patterns(relative).items():
            if pattern.search(text):
                findings.append(f"{relative}: possible {label}")
        if is_vendored_documentation(relative):
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
