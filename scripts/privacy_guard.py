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
# A hostname exemption is only safe if it covers the entire host. Anything in
# this class ends one: a port, a path, a query, a fragment, a closing quote,
# whitespace, or the end of the input.
HOST_END = r"(?=[:/?#\s\"']|$)"
LFS_POINTER_PREFIX = "version https://git-lfs.github.com/" "spec/v1"
PATTERNS = {
    "secret token": re.compile(
        r"\b(?:(?:sk|gh[opusr]|github_pat|xox[baprs]|npm)[-_][A-Za-z0-9_-]{12,}"
        r"|AIza[A-Za-z0-9_-]{20,})\b"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "cloud access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    # A private Terraform Enterprise host names an employer or client's own
    # installation, which AGENTS.md forbids publishing. The public SaaS endpoint
    # (app.terraform.io) identifies nobody and is deliberately not flagged, nor
    # are placeholder hosts, so this repository's own documentation stays clean.
    "private connector endpoint": re.compile(
        r"(?i)\btfe?[_-]?address[\"']?\s*[:=]\s*[\"']?https?://"
        # Each public/loopback exemption must consume the WHOLE hostname. A
        # trailing word boundary matched before a dot, so localhost.corp and
        # app.terraform.io.corp -- real private hosts that merely start with an
        # exempt name -- were silently excused. HOST_END requires a port, path,
        # query, fragment, quote, whitespace or end of input to follow.
        r"(?!app\.terraform\.io" + HOST_END + r")"
        r"(?!localhost" + HOST_END + r")"
        r"(?!127\.0\.0\.1" + HOST_END + r")"
        r"(?!0\.0\.0\.0" + HOST_END + r")"
        # IPv6 loopback and unspecified, in the bracketed URL form.
        r"(?!\[(?:::1|::)\]" + HOST_END + r")"
        r"(?!<)(?!your[-_.])(?!example\.)(?!\S*\.example\b)"
        # A private installation is just as often an IPv4 literal, a bracketed
        # IPv6 literal, or a single-label intranet name as a dotted FQDN.
        # Requiring a dot and an alphabetic TLD missed all three, which is the
        # majority of the private cases this pattern exists for. IPv6 is the
        # most likely form for a ULA-addressed internal Terraform Enterprise
        # install, so it must be matched, not just the v4 literal.
        r"(?:\[[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*\](?::\d+)?"
        r"|\d{1,3}(?:\.\d{1,3}){3}"
        r"|[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}"
        r"|[A-Za-z0-9][A-Za-z0-9-]*)"
    ),
    # Connector identifiers. AGENTS.md forbids these in this public repository
    # alongside credentials: a tenant or client id names Joe's actual cloud
    # tenancy and app registration. They are not secrets, so they are reported
    # separately, but they must not be published either. GUID-shaped or opaque
    # values only -- a placeholder like "<your-tenant-id>" is not flagged.
    "connector identifier": re.compile(
        r"(?i)\b(?:azure[_-]?tenant[_-]?id|azure[_-]?client[_-]?id"
        r"|azure[_-]?subscription[_-]?id|aps[_-]?client[_-]?id"
        r"|gdrive[_-]?client[_-]?id)"
        # The closing quote of a JSON key sits between the name and the colon.
        # Without it, {"AZURE_TENANT_ID":"<guid>"} -- the ordinary way this
        # configuration is stored -- bypassed the guard entirely.
        r"[\"']?\s*[:=]\s*[\"']?"
        # GUID, opaque token, or -- for Azure -- the tenant *domain* form,
        # which is neither and was therefore invisible. The domain branch
        # accepts a single dot: a verified custom tenant domain is an ordinary
        # one-dot company domain, and requiring two dots caught only the
        # *.onmicrosoft.com default while missing every custom one. Only the
        # RFC-reserved placeholder domains are excused; a vendor's fictional
        # company name is not one of them, and treating it as such would
        # excuse the exact form this pattern exists to catch.
        r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        r"|(?!your[-_.])(?!<)(?!example\.)(?!\S*\.example\b)"
        r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
        r"|[A-Za-z0-9_-]{16,})[\"']?"
    ),
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
        # As above: allow the closing quote of a JSON key before the delimiter.
        r"[\"']?\s*[:=]\s*(?:[\"'][^\"']{8,}[\"']|[^\s#\"',}]{8,})"
    ),
    # Organization and workspace slugs. These sit apart from "connector
    # identifier" because that pattern's opaque-value branch requires 16+
    # characters -- reasonable for a GUID or an API-style id, but wrong here:
    # a real Terraform organization is an ordinary short slug like
    # "client-prod", which named the client and passed the guard untouched.
    # A short value is only safe to ignore when it is recognisably a
    # placeholder, so the exclusions carry the whole weight and are explicit.
    "connector organization": re.compile(
        r"(?i)\b(?:tfe?[_-]?organization|tfe?[_-]?workspace"
        r"|terraform[_-]?organization)"
        r"[\"']?\s*[:=]\s*[\"']?"
        r"(?!your[-_.])(?!my[-_.])(?!<)(?!example[-_.\s\"']?)(?!placeholder\b)"
        r"(?!org\b)(?!organization\b)(?!workspace\b)(?!name\b)(?!\.\.\.)"
        r"[A-Za-z0-9][A-Za-z0-9_-]{2,}"
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


# A placeholder only counts when it stands as a complete lexical unit. These
# are the characters that would make it a prefix or suffix of something longer.
_TOKEN_CHAR = r"[\w.@:/+-]"


# Both normalisers accept a quoted key as well as a bare one. YAML and TOML
# each allow the mapping key to be quoted -- "AZURE_CLIENT_SECRET": |- and
# "AZURE_CLIENT_SECRET" = """...""" are valid and both parsers reconstruct the
# value -- so a key-grammar that only matched bare identifiers reopened the
# exact bypass each fold was written to close, one quote character later.
_KEY = r"[\"']?[A-Za-z_][A-Za-z0-9_.-]*[\"']?"

_BLOCK_SCALAR_HEADER = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>" + _KEY + r")\s*:\s*"
    # YAML lets the indentation indicator and the chomping indicator appear in
    # either order -- "|2-" and "|-2" are both valid headers, and a parser
    # reconstructs the value from both. Accepting only one order left the other
    # unfolded, which is the same bypass this function exists to close.
    r"[|>](?:\d+[+-]?|[+-]\d*)?\s*(?:#.*)?$"
)


_TOML_MULTILINE = re.compile(
    r"(?P<key>" + _KEY + r")\s*=\s*"
    r"(?P<q>\"{3}|'{3})(?P<body>[\s\S]*?)(?P=q)"
)


def fold_toml_multiline(text: str) -> str:
    """Rewrite TOML multiline strings onto one single-quoted-style line.

    The value branches expect an ordinary quoted or bare token, so a valid
    TOML basic/literal multiline string --

        AZURE_CLIENT_SECRET = \"\"\"the actual secret\"\"\"

    -- matched neither: the quoted branch stopped at the second delimiter
    quote, and the bare branch rejects quotes outright. `tomllib` reconstructs
    the credential from it, so the guard has to see it too. As with YAML block
    scalars, this is normalised once here instead of complicating every
    pattern, and appended so line-oriented checks still see the original.
    """
    folded = []
    for match in _TOML_MULTILINE.finditer(text):
        body = match.group("body").strip()
        if not body:
            continue
        # Collapse to one line and drop inner quotes so the ordinary quoted
        # branch can bracket the whole value.
        flat = " ".join(body.replace('"', " ").replace("'", " ").split())
        if flat:
            folded.append(f'{match.group("key")} = "{flat}"')
    return text + "\n" + "\n".join(folded) if folded else text


def fold_block_scalars(text: str) -> str:
    """Rewrite YAML block scalars onto their key line before scanning.

    Every value pattern reads a key and its value from one line. A YAML block
    scalar puts them on different lines --

        AZURE_CLIENT_SECRET: |-
          <the actual secret>

    -- so the value branch saw only the "|-" marker and the file scanned clean,
    even though any YAML parser reconstructs the credential. Folding is done
    here, once, rather than by teaching every pattern to span lines.

    The folded copy is appended rather than substituted, so line-oriented
    checks elsewhere still see the original text.
    """
    if "|" not in text and ">" not in text:
        return text
    lines = text.splitlines()
    folded: list[str] = []
    index = 0
    while index < len(lines):
        header = _BLOCK_SCALAR_HEADER.match(lines[index])
        if not header:
            index += 1
            continue
        base = len(header.group("indent"))
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if not line.strip():
                body.append("")
                cursor += 1
                continue
            if len(line) - len(line.lstrip()) <= base:
                break
            body.append(line.strip())
            cursor += 1
        if body:
            folded.append(f"{header.group('key')}: {' '.join(body).strip()}")
        index = cursor
    return text + "\n" + "\n".join(folded) if folded else text


def strip_known_placeholders(relative: Path, text: str) -> str:
    """Remove the exact documented false-positive snippets for one file.

    Matching is boundary-anchored, not substring. A bare str.replace() deleted
    an approved literal wherever it appeared, including as the *prefix* of a
    longer real value: the approved e-mail placeholder followed by a further
    dotted company domain left only that company's domain behind, and the scan
    reported nothing -- even though the same text is caught as an address in
    any other file. The literal must now be flanked by something that cannot
    continue a token. (The example is described rather than written out: this
    file is scanned by its own patterns.)

    Everything else in the file is still scanned by every pattern.
    """
    for literal in PLACEHOLDER_LITERALS.get(relative, ()):
        text = re.sub(
            rf"(?<!{_TOKEN_CHAR}){re.escape(literal)}(?!{_TOKEN_CHAR})",
            "",
            text,
        )
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
        scannable = strip_known_placeholders(
            relative, fold_toml_multiline(fold_block_scalars(text)))
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
    # A directory destination must reach the children the recursion produced.
    # Mapping only the parent key meant a downloaded bundle scanned
    # `--as .github/instructions` matched no child against the allowlists, so an
    # approved file inside it reported its own documented placeholders and
    # pre-install intake of a bundle was impossible.
    resolved: dict[Path, Path] = {}
    for given, dest in (destinations or {}).items():
        anchor = given if given.is_absolute() else (root / given)
        resolved[anchor] = dest
        if anchor.is_dir():
            for child in targets:
                try:
                    suffix = child.relative_to(anchor)
                except ValueError:
                    continue
                resolved[child] = dest / suffix
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
