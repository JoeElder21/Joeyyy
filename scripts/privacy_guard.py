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
# A hostname exemption is only safe if it covers the entire host. Anything in
# this class ends one: a port, a path, a query, a fragment, a closing quote,
# whitespace, or the end of the input.
HOST_END = r"(?=[:/?#\s\"']|$)"
# The same idea for a quoted or bare VALUE: an exclusion is only safe when it
# covers the entire value, not a prefix of one.
VALUE_END = r"(?=[\s\"',}\]#]|$)"
LFS_POINTER_PREFIX = "version https://git-lfs.github.com/spec/v1"
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
        # Each exclusion must consume the WHOLE value. Written as bare
        # prefixes, the your-/my-/example- lookaheads exempted every real slug
        # that merely begins with one, so an organization named for a client
        # and prefixed "my-" was excused by the prefix alone. VALUE_END anchors
        # each exemption to the end of the value, the same repair already made
        # to the hostname exemptions above. (Described rather than written out:
        # this file is scanned by its own patterns.)
        r"(?!(?:your|my|our|the|some|a)[-_.]?(?:org|organization|workspace|"
        r"name|company|team|tenant|client)?" + VALUE_END + r")"
        r"(?!example[-_.]?(?:org|organization|workspace|name)?" + VALUE_END + r")"
        r"(?!<)(?!placeholder" + VALUE_END + r")"
        r"(?!org" + VALUE_END + r")(?!organization" + VALUE_END + r")"
        r"(?!workspace" + VALUE_END + r")(?!name" + VALUE_END + r")"
        r"(?!\.\.\.)"
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
    # The sequence-entry prefix is part of `indent` on purpose: for
    # `- KEY: |-` the block body is indented relative to the KEY, not to the
    # dash, so counting the dash keeps the body-indent comparison right.
    # Without this branch a credential inside a YAML sequence mapping -- an
    # ordinary shape for a list of connector entries -- never reached the
    # value patterns at all.
    r"^(?P<indent>[ \t]*(?:-[ \t]+)?)(?P<key>" + _KEY + r")\s*:\s*"
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


# A YAML node's "properties" are its tag and its anchor, in either order and
# either or both present. Both sit between the key and the value.
_YAML_PROPERTY = r"(?:!(?:!\w+|<[^>]*>|[\w.-]*)|&[\w.-]+)"
_YAML_NODE_PROPERTIES = re.compile(
    r"(?m)^(?P<lead>[ \t]*(?:-[ \t]+)?" + _KEY + r"[ \t]*:[ \t]*)"
    r"(?:" + _YAML_PROPERTY + r"[ \t]+)+"
)
_YAML_ANCHOR_DEF = re.compile(
    r"(?m)^[ \t]*(?:-[ \t]+)?" + _KEY + r"[ \t]*:[ \t]*"
    r"(?:!(?:!\w+|<[^>]*>|[\w.-]*)[ \t]+)?"
    r"&(?P<name>[\w.-]+)[ \t]+(?P<value>\S.*?)[ \t]*$"
)
_YAML_ALIAS = re.compile(r"(?m)(?P<lead>:[ \t]*)\*(?P<name>[\w.-]+)[ \t]*$")


# Parsing beats pattern-matching for a format that has a grammar. Six review
# rounds each found a different token or container that hid a value from the
# line-oriented patterns -- TOML multiline strings, quoted keys, block scalars
# in two indicator orders, explicit tags, sequence entries, anchors, aliases,
# and flow mappings. Each fix was correct and each was bypassed by the next
# construct, because a regex approximates the grammar and the grammar keeps
# winning.
#
# So the value extraction below asks a real parser what the document MEANS, and
# scans that. The regex normalisers are kept underneath as a fallback: PyYAML
# is not in every environment, and losing all coverage when it is absent would
# trade a partial gap for a total one.
MAX_PARSE_BYTES = 2_000_000
# Hard ceiling on reconstructed values, so a hostile alias graph cannot turn
# the privacy gate into the outage.
MAX_EMITTED_VALUES = 20_000


def _yaml_loader():
    """A safe loader that tolerates tags it does not know.

    Unknown tags (`!secret`, `!<tag:...>`) raise under the plain safe loader,
    which would drop the whole document back to the regex path -- exactly the
    documents most likely to be hiding something behind a custom tag.
    """
    import yaml

    class _Tolerant(yaml.SafeLoader):
        pass

    _Tolerant.add_multi_constructor(
        "", lambda loader, suffix, node: _construct_unknown(loader, node))
    _Tolerant.add_multi_constructor(
        "tag:", lambda loader, suffix, node: _construct_unknown(loader, node))
    return _Tolerant


def _construct_unknown(loader, node):
    import yaml

    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


def yaml_reconstructed_values(text: str) -> str:
    """`key: value` lines for every scalar a YAML parser actually produces.

    Anchors, aliases, tags, block scalars, flow mappings and sequence entries
    are all resolved by the parser, so the patterns see the value the
    application would receive rather than the syntax that carried it. Returns
    "" when the text is not YAML, is too large, or PyYAML is unavailable --
    every one of which leaves the regex normalisers in charge.
    """
    if len(text.encode("utf-8", errors="ignore")) > MAX_PARSE_BYTES:
        return ""
    try:
        import yaml
    except ImportError:
        return ""

    lines: list[str] = []
    # An alias is a SHARED REFERENCE, so a five-line file with four levels of
    # ten-way aliasing expands to hundreds of thousands of emitted characters
    # without ever increasing recursion depth. MAX_PARSE_BYTES bounds the input
    # and the RecursionError handler bounds the depth; neither bounds this.
    # Both a visited set (each shared subtree walked once) and a hard output
    # budget are needed: the set alone still permits a wide flat structure.
    seen: set[int] = set()
    budget = [MAX_EMITTED_VALUES]

    def walk(node, key=None):
        if budget[0] <= 0:
            return
        if isinstance(node, (dict, list, tuple)):
            marker = id(node)
            if marker in seen:
                return
            seen.add(marker)
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, child_key)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, key)
        elif node is not None and key is not None:
            budget[0] -= 1
            lines.append(_reconstructed(key, ":", node))

    try:
        # An alias bomb expands geometrically; the size cap plus these guards
        # keep a hostile document from taking the scan down instead of being
        # reported by it.
        for document in yaml.load_all(text, Loader=_yaml_loader()):
            walk(document)
    except (Exception, RecursionError):  # noqa: BLE001 - any parse failure falls back
        return ""
    return "\n".join(line for line in lines if line)


def _reconstructed(key, delimiter: str, value) -> str:
    """One `key <delim> "value"` line, quoted and quote-free.

    Emitting the value bare meant a reconstructed value that itself contains a
    quote -- which is exactly what an escaped delimiter produces -- terminated
    the bare-value branch early and was never matched. Quoting it and stripping
    inner quotes lets the quoted branch bracket the whole thing.
    """
    flat = " ".join(str(value).replace('"', " ").replace("'", " ").split())
    return f'{key} {delimiter} "{flat}"' if flat else ""


def toml_reconstructed_values(text: str) -> str:
    """`key = value` lines for every scalar tomllib actually produces.

    The same argument as the YAML side, one format over. A quoted TOML key may
    carry Unicode escapes (`"AZURE\\u005fCLIENT\\u005fSECRET"`), and a multiline
    basic string may contain an ESCAPED triple quote that a non-greedy regex
    reads as the closing delimiter -- so the fold emitted only the prefix and
    the credential after it was never scanned. Both are decoded correctly by
    the parser and by nothing short of one.

    Returns "" when the text is not TOML, which leaves the regex fold in charge.
    """
    if len(text.encode("utf-8", errors="ignore")) > MAX_PARSE_BYTES:
        return ""
    try:
        import tomllib

        document = tomllib.loads(text)
    except Exception:  # noqa: BLE001 - any parse failure falls back
        return ""

    lines: list[str] = []
    budget = [MAX_EMITTED_VALUES]

    def walk(node, key=None):
        if budget[0] <= 0:
            return
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, child_key)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, key)
        elif node is not None and key is not None:
            budget[0] -= 1
            lines.append(_reconstructed(key, "=", node))

    walk(document)
    return "\n".join(line for line in lines if line)


def strip_yaml_node_properties(text: str) -> str:
    """Resolve YAML aliases, then drop tags and anchors, so the VALUE is scanned.

    Three things can sit between a key and its value, and each one hid the
    value from the assignment patterns:

    * an explicit tag -- `KEY: !!str <secret>`. The bare-value branch matched
      the tag and stopped at the following space. `!!binary` is itself eight
      characters, so it even satisfied the length minimum: the scan reported a
      finding while having examined nothing.
    * an anchor -- `KEY: &tid <guid>`. Same shape, different token, and it
      composes with a tag in either order.
    * an alias -- `KEY: *tid`. Here the value genuinely lives elsewhere, so
      stripping alone is not enough; the anchor definition is substituted in,
      which is what a parser hands the application.

    A YAML parser discards the properties and keeps the value, so this does too.
    Anchor definitions are resolved first, because a definition line carries the
    anchor AND the value together.
    """
    anchors = {
        match.group("name"): match.group("value")
        for match in _YAML_ANCHOR_DEF.finditer(text)
    }
    if anchors:
        text = _YAML_ALIAS.sub(
            lambda m: m.group("lead") + anchors.get(m.group("name"), "*" + m.group("name")),
            text,
        )
    return _YAML_NODE_PROPERTIES.sub(lambda m: m.group("lead"), text)


# Retained name: the pipeline and tests referred to tag stripping before
# anchors and aliases were found to be the same defect in different tokens.
strip_yaml_tags = strip_yaml_node_properties


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
    findings.extend(_scan_files(repository_files(root), root))
    return findings


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
            if path.is_symlink():
                # What git publishes for a symlink is the *target string* it
                # stores as the blob, not the bytes of whatever that string
                # resolves to. Reading through would scan the wrong content
                # entirely: a link named innocuously and pointing at a benign
                # existing file still publishes its target path, which may
                # carry a client name, an address, or a private directory
                # layout. Dangling links are covered too -- os.readlink needs
                # no target. (Merged from main; the destination-aware scan
                # must not lose it.)
                raw = os.readlink(path).encode("utf-8", errors="surrogateescape")
            else:
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
        # Parser output FIRST, regex normalisation underneath. The parser is
        # authoritative where it works; the normalisers stay so a missing
        # PyYAML, a non-YAML file, or an oversized document degrades to partial
        # coverage rather than none.
        scannable = strip_known_placeholders(
            relative,
            fold_toml_multiline(fold_block_scalars(strip_yaml_node_properties(text)))
            + "\n" + yaml_reconstructed_values(text)
            + "\n" + toml_reconstructed_values(text))
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
        if candidate.is_dir() and not candidate.is_symlink():
            targets.extend(
                child for child in sorted(candidate.rglob("*"))
                # is_symlink() as well as is_file(): a DANGLING link answers
                # False to is_file(), so the recursion dropped exactly the
                # entry _scan_files() knows how to handle -- it scans a link's
                # target string, which is what git publishes. A bundle holding
                # `notes -> /home/<client>/private` passed the pre-install gate
                # while scanning that same link directly reported it.
                if (child.is_file() or child.is_symlink())
                and ".git" not in child.parts
                and "__pycache__" not in child.parts
            )
        elif candidate.is_file() or candidate.is_symlink():
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
