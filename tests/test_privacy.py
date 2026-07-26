import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.privacy_guard import (
    MAX_EMITTED_VALUES,
    MAX_PARSE_BYTES,
    PATTERNS,
    TRUNCATION_MARKER,
    PLACEHOLDER_LITERALS,
    applicable_patterns,
    fold_block_scalars,
    fold_toml_multiline,
    gitlink_paths,
    is_vendored,
    repository_files,
    scan_paths,
    scan_repository,
    strip_known_placeholders,
    strip_yaml_node_properties,
    strip_yaml_tags,
    toml_reconstructed_values,
    yaml_reconstructed_values,
)

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - environment-dependent
    _yaml = None

# `scripts/privacy_guard.py` degrades to regex normalisation when PyYAML is
# absent, and the repository's stated property is that the whole suite runs
# stdlib-only with dependency-gated tests skipping cleanly. Tests that assert
# PARSER behaviour must degrade the same way the scanner does, or adding a
# coverage dependency silently converts a stdlib-only suite into eight
# failures. CI installs PyYAML, so the parser path is still exercised there --
# it is gated, not abandoned.
needs_yaml = unittest.skipIf(_yaml is None, "PyYAML not installed")


def _have_yaml() -> bool:
    """Whether the parser is importable RIGHT NOW.

    The module-level `_yaml` binding is captured at import, so an inline guard
    written against it does not degrade when the import is blocked later --
    which made inline-gated cases run anyway under the dependency simulation
    and, worse, meant the gate check trusted them instead of verifying them.
    """
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".github" / "skills"


class PublicRepositoryPrivacyTests(unittest.TestCase):
    def test_tracked_text_has_no_obvious_private_or_secret_material(self):
        excluded_parts = {"__pycache__", ".git", "node_modules"}
        gitlinks = gitlink_paths(ROOT)
        text_paths = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and not any(part in excluded_parts for part in path.parts)
            and not is_vendored(path, ROOT, gitlinks)
            and path.suffix.lower() in {".md", ".toml", ".json", ".py", ".yml", ".yaml"}
        ]
        prohibited = {
            "secret key": re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"),
            "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            "cloud access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
            "generic credential assignment": re.compile(
                r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']"
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
                r"\b[1-9]\d{1,5}\s+(?:[A-Za-z0-9.'-]+\s+){1,6}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Boulevard|Blvd)\b",
                re.IGNORECASE,
            ),
        }
        for path in text_paths:
            relative_path = path.relative_to(ROOT)
            text = strip_known_placeholders(
                relative_path, path.read_text(encoding="utf-8")
            )
            for label, pattern in prohibited.items():
                with self.subTest(path=relative_path, check=label):
                    self.assertIsNone(pattern.search(text))

    def test_no_file_is_ever_exempt_from_any_pattern(self):
        """Two earlier designs were rejected in review: a directory-wide
        exemption, then a per-file one. Both let a genuine credential into a
        tracked file. Nothing is exempted now -- only exact literal snippets are
        stripped -- so every path must see the complete pattern set."""
        for path in (
            Path(".github/instructions/local.instructions.md"),
            Path(".github/instructions/security-and-owasp.instructions.md"),
            Path("scripts/anything.py"),
            Path("README.md"),
        ):
            with self.subTest(path=path):
                self.assertEqual(set(applicable_patterns(path)), set(PATTERNS))

    def test_real_credential_in_a_relaxed_file_is_still_caught(self):
        """Regression for the second rejected design. Relaxing a whole pattern
        for a whole file meant a real credential appended to that same file
        passed. Stripping only the exact known snippets does not."""
        relaxed_file = Path(
            ".github/instructions/security-and-owasp.instructions.md"
        )
        self.assertIn(relaxed_file, PLACEHOLDER_LITERALS)
        secret = "an" + "ActualPrivateCredential"
        planted = "API" + "_KEY" + ' = "' + secret + '"'
        text = strip_known_placeholders(
            relaxed_file,
            (ROOT / relaxed_file).read_text(encoding="utf-8") + "\n" + planted,
        )
        self.assertIsNotNone(PATTERNS["credential assignment"].search(text))

    def test_stripping_removes_only_the_pinned_snippets(self):
        """Each pinned literal must appear verbatim in its file, and stripping
        must not shorten the file by more than those literals account for."""
        for path, literals in PLACEHOLDER_LITERALS.items():
            original = (ROOT / path).read_text(encoding="utf-8")
            stripped = strip_known_placeholders(path, original)
            # Count boundary-anchored occurrences, which is what stripping
            # now removes. A plain .count() would also tally an appearance
            # inside a longer token -- exactly the case stripping must leave
            # alone -- and would disagree with the code for the wrong reason.
            expected = sum(
                len(lit) * len(re.findall(
                    rf"(?<![\w.@:/+-]){re.escape(lit)}(?![\w.@:/+-])",
                    original))
                for lit in literals
            )
            with self.subTest(path=path):
                self.assertEqual(len(original) - len(stripped), expected)

    def test_untracked_downloaded_file_is_scannable_by_path(self):
        """scan_repository() enumerates via `git ls-files`, so it cannot see a
        file that has just been downloaded -- which made a bare privacy-guard run
        useless as an intake gate for exactly the content intake exists to check.
        scan_paths() takes explicit paths and does not care about tracking."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_dir = root / "downloaded-skill"
            asset_dir.mkdir()
            planted = "API" + "_KEY" + ' = "' + "an" + 'ActualPrivateCredential"'
            (asset_dir / "helper.py").write_text(planted + "\n", encoding="utf-8")
            (asset_dir / "SKILL.md").write_text("nothing notable\n", encoding="utf-8")

            findings = scan_paths([asset_dir], root=root)
            self.assertTrue(
                any("credential assignment" in f for f in findings), findings
            )
            self.assertTrue(any("helper.py" in str(f) for f in findings))
            # The clean sibling must not be reported.
            self.assertFalse(any("SKILL.md" in str(f) for f in findings))

    def test_scan_paths_accepts_a_single_file_and_reports_nothing_when_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clean = root / "notes.md"
            clean.write_text("ordinary prose\n", encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    def test_every_mount_credential_name_is_detectable(self):
        """A mount's activation text names the env vars that unlock it. If the
        guard cannot recognise one of those names in an assignment, a maintainer
        pasting a real value into a tracked file passes the scan. Terraform and
        GitHub tokens carry no distinguishing prefix, so the name is the only
        signal available and this is the whole defence.
        """
        import tomllib

        with (ROOT / "config" / "mcp_mounts.toml").open("rb") as source:
            mounts = tomllib.load(source)["mounts"]
        # Use the shipped pattern, not a copy of it. A duplicate here passes
        # while the real guard regresses -- and it did drift once already, so
        # the JSON-key fix landed in one and not the other.
        pattern = PATTERNS["credential assignment"]
        # Env-var-shaped names the guard must recognise. `_ID` is included:
        # AGENTS.md forbids connector identifiers in this public repository
        # alongside credentials, and an earlier version of this test skipped
        # them -- so AZURE_TENANT_ID and AZURE_CLIENT_ID, which this repository's
        # own headless activation workflow names, went undetected. A tenant or
        # client id is not a secret but it still identifies Joe's real tenancy.
        credential_suffixes = (
            "TOKEN", "SECRET", "KEY", "PASSWORD", "CREDENTIAL", "ID",
        )
        benign = {
            "GDRIVE_CREDENTIALS_PATH",  # a path to a file, not a secret
        }
        seen = 0
        for mount in mounts:
            text = mount.get("activation", "") + " " + " ".join(mount["command"])
            for name in re.findall(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b", text):
                if name in benign or not name.endswith(credential_suffixes):
                    continue
                seen += 1
                with self.subTest(mount=mount["name"], env=name):
                    probe = f'{name} = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"'
                    combined = [
                        PATTERNS["credential assignment"],
                        PATTERNS["connector identifier"],
                    ]
                    self.assertTrue(
                        any(p.search(probe) for p in combined)
                        or pattern.search(f'{name} = "aRealLookingSecretValue"'),
                        f"{mount['name']} activation names {name}, but the "
                        f"credential-assignment pattern cannot detect it",
                    )
        self.assertGreater(seen, 0, "no mount credential names were checked")

    def test_intake_scan_applies_name_checks_to_the_destination(self):
        """`--as` declares where a candidate is bound for. Keying the
        prohibited-name and suffix checks on the temp source name let the
        pre-install gate approve a file that scan_repository() rejects the
        moment it is installed -- the gate passing exactly what the repository
        scan forbids."""
        from scripts.privacy_guard import scan_paths

        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "neutral.txt"
            candidate.write_text("harmless utf-8\n", encoding="utf-8")
            for destination, why in [
                ("credentials.json", "prohibited filename"),
                ("docs/report.pdf", "prohibited artifact suffix"),
            ]:
                with self.subTest(destination=destination):
                    findings = scan_paths(
                        [candidate], destinations={candidate: Path(destination)})
                    self.assertTrue(findings, f"{destination} slipped past the gate")
                    self.assertIn(destination, " ".join(findings))
            allowed = scan_paths(
                [candidate],
                destinations={candidate: Path(".github/instructions/x.instructions.md")})
            self.assertEqual(allowed, [], allowed)

    def test_private_connector_endpoint_is_detected_but_public_one_is_not(self):
        """A private Terraform Enterprise host names an employer or client's own
        installation, which this public repository forbids. The public SaaS
        endpoint identifies nobody, and flagging it would fire on this
        repository's own documentation."""
        pattern = PATTERNS["private connector endpoint"]
        # Probes are assembled at runtime: writing them literally would make
        # this test file itself trip the pattern it is testing.
        name = "TFE" + "_ADDRESS"
        scheme = "https" + "://"
        for host in ("terraform.client-company.com", "tfe.someorg.internal.net",
                     "10.20.30.40", "terraform-internal",
                     # An internal install on a ULA or site-local IPv6 address
                     # is written bracketed in a URL, and identifies the network
                     # just as precisely as the v4 literal above.
                     "[fd00::1234]:443", "[2001:db8:85a3::8a2e:370:7334]"):
            with self.subTest(host=host, expect="flagged"):
                self.assertIsNotNone(
                    pattern.search(f'{name} = "{scheme}{host}"'))
        for probe in (
            f'{name} = "{scheme}app.terraform.io"',
            f'{name} = "<your-tfe-host>"',
            f'{name} = "{scheme}localhost:8080"',
            f'{name} = "{scheme}[::1]:8080"',
            f'{name} = "{scheme}[::]"',
            name,
        ):
            with self.subTest(probe=probe, expect="clean"):
                self.assertIsNone(pattern.search(probe))

    def test_public_host_exemptions_do_not_excuse_suffixed_private_hosts(self):
        """An exemption must consume the whole hostname.

        A trailing word boundary also matches before a dot, so a private host
        that merely starts with an exempt name -- localhost.corp,
        app.terraform.io.corp -- inherited the exemption and passed."""
        pattern = PATTERNS["private connector endpoint"]
        name = "TFE" + "_ADDRESS"
        scheme = "https" + "://"
        for host in ("localhost.corp", "app.terraform.io.corp",
                     "127.0.0.1.corp", "localhost.client-company.net"):
            with self.subTest(host=host, expect="flagged"):
                self.assertIsNotNone(
                    pattern.search(f'{name} = "{scheme}{host}"'))
        # The genuine exemptions must still hold, terminated by a port, a
        # path, a closing quote or end of input.
        for host in ("localhost", "localhost:8080", "app.terraform.io",
                     "app.terraform.io/app/acme", "127.0.0.1"):
            with self.subTest(host=host, expect="clean"):
                self.assertIsNone(
                    pattern.search(f'{name} = "{scheme}{host}"'))

    def test_short_organization_slugs_are_detected(self):
        """A Terraform organization is an ordinary short slug, not a GUID.

        The opaque-value branch of `connector identifier` needs 16+ characters,
        which is right for an id and wrong for an organization: a real name like
        "client-prod" names the client in four fewer characters and passed
        untouched. Short values are only safe when recognisably placeholders,
        so the exclusions carry the whole weight here and are asserted."""
        pattern = PATTERNS["connector organization"]
        for value in ("client-prod", "acme", "northside-utilities"):
            with self.subTest(value=value, expect="flagged"):
                self.assertIsNotNone(
                    pattern.search(f'TFE_ORGANIZATION = "{value}"'))
        for value in ("your-org", "<your-org>", "my-org", "example-org",
                      "placeholder", "organization"):
            with self.subTest(value=value, expect="clean"):
                self.assertIsNone(
                    pattern.search(f'TFE_ORGANIZATION = "{value}"'))

    def test_json_formatted_connector_config_is_not_a_bypass(self):
        """The closing quote of a JSON key sits between name and delimiter.

        Requiring the delimiter to follow the name immediately meant the
        ordinary way this configuration is stored -- a JSON object -- bypassed
        both the identifier and the credential patterns entirely."""
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        secret = "x" * 20
        cases = (
            ("connector identifier", '{"AZURE_TENANT_ID": "%s"}' % guid),
            ("connector identifier", "{'AZURE_CLIENT_ID': '%s'}" % guid),
            ("credential assignment", '{"AZURE_CLIENT_SECRET": "%s"}' % secret),
            ("credential assignment", '{"TFE_TOKEN": "%s"}' % secret),
        )
        for pattern_name, probe in cases:
            with self.subTest(pattern=pattern_name, probe=probe):
                self.assertIsNotNone(PATTERNS[pattern_name].search(probe))

    def test_single_dot_tenant_domains_are_detected(self):
        """A verified custom Azure tenant domain is an ordinary one-dot company
        domain. Requiring two dots caught only the *.onmicrosoft.com default and
        missed every custom one, in both the assignment and JSON forms."""
        pattern = PATTERNS["connector identifier"]
        for value in ("northside-utilities.com", "acme.co.uk",
                      "acme-eng.onmicrosoft.com"):
            for probe in (f'AZURE_TENANT_ID = "{value}"',
                          '{"AZURE_TENANT_ID": "%s"}' % value):
                with self.subTest(value=value, probe=probe, expect="flagged"):
                    self.assertIsNotNone(pattern.search(probe))
        # RESERVED names stay excused -- and only those. `your-tenant.com` was
        # previously asserted clean, which encoded the defect: the `your-`
        # lookahead was an unbounded prefix, so it equally excused
        # `your-corp.internal` and any other real host beginning with it. There
        # is no lexical way to tell a placeholder `your-…` from a registrable
        # one, and this repository's own rule is that uncertain counts as real.
        # The unambiguous placeholder spelling -- angle brackets -- still is.
        for value in ("your-tenant.com", "your-corp.internal",
                      "example.customer.com", "corp.example.evil"):
            with self.subTest(value=value, expect="flagged"):
                self.assertIsNotNone(
                    pattern.search(f'AZURE_TENANT_ID = "{value}"'),
                    "an unreserved host must not be excused by a placeholder "
                    "prefix or infix")
        for value in ("example.com", "tenant.example.com", "<your-tenant>",
                      "tenant.example", "tenant.invalid", "tenant.test"):
            with self.subTest(value=value, expect="clean"):
                self.assertIsNone(
                    pattern.search(f'AZURE_TENANT_ID = "{value}"'))

    def test_yaml_block_scalars_are_folded_before_scanning(self):
        """Every value pattern reads a key and its value from one line, so a
        YAML block scalar split them apart and the value branch saw only the
        "|-" marker -- while any YAML parser reconstructs the credential."""
        secret = "Xy7Q" + "secretValue0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        cases = (
            ("credential assignment", f"AZURE_CLIENT_SECRET: |-\n  {secret}\n"),
            ("credential assignment", "TFE_TOKEN: >-\n  atlasv1.abcdefghijklmnop\n"),
            ("connector identifier", f"AZURE_TENANT_ID: |\n  {guid}\n"),
            # Folded across multiple indented lines, as YAML allows.
            ("credential assignment",
             "TFE_TOKEN: |-\n  atlasv1.\n  abcdefghijklmnop\n"),
            # YAML allows the indentation and chomping indicators in either
            # order. Accepting only one left the other unfolded, which is the
            # same bypass with two extra characters.
            ("credential assignment", f"AZURE_CLIENT_SECRET: |2-\n  {secret}\n"),
            ("credential assignment", f"AZURE_CLIENT_SECRET: |-2\n  {secret}\n"),
            ("credential assignment", "TFE_TOKEN: >2+\n  atlasv1.abcdefghijkl\n"),
        )
        for label, probe in cases:
            with self.subTest(label=label, probe=probe):
                self.assertIsNone(
                    PATTERNS[label].search(probe),
                    "probe must be one the raw patterns genuinely miss, "
                    "otherwise this asserts nothing about folding",
                )
                self.assertIsNotNone(
                    PATTERNS[label].search(fold_block_scalars(probe)))

        # An ordinary prose block must not become a finding.
        prose = "description: |\n  Ordinary prose describing the mount.\n"
        folded = fold_block_scalars(prose)
        self.assertEqual(
            [name for name, pattern in PATTERNS.items() if pattern.search(folded)],
            [],
        )

    def test_toml_multiline_credentials_are_folded_before_scanning(self):
        """tomllib reconstructs the secret from a multiline string, so the
        guard must see it too.

        The value branches expect a quoted or bare token: the quoted branch
        stopped at the second delimiter quote and the bare branch rejects
        quotes outright, so a valid TOML basic/literal multiline string matched
        neither."""
        # Names, delimiters and values are all assembled at runtime. Written
        # literally, these probes would be real findings in this file -- the
        # folding this test exercises is exactly what would catch them.
        secret = "super" + "-secret-value-0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        client_secret = "AZURE" + "_CLIENT_SECRET"
        token = "TFE" + "_TOKEN"
        tenant = "AZURE" + "_TENANT_ID"
        dq, sq = '"' * 3, "'" * 3
        cases = (
            ("credential assignment", f"{client_secret} = {dq}{secret}{dq}"),
            ("credential assignment", f"{client_secret} = {sq}{secret}{sq}"),
            ("credential assignment",
             f"{token} = {dq}atlasv1.abcdefghijklmnop{dq}"),
            ("connector identifier", f"{tenant} = {dq}{guid}{dq}"),
            # Spanning several lines, as TOML allows.
            ("credential assignment",
             f"{client_secret} = {dq}\n  {secret}\n{dq}"),
        )
        for label, probe in cases:
            with self.subTest(label=label, probe=probe):
                self.assertIsNone(
                    PATTERNS[label].search(probe),
                    "probe must be one the raw patterns genuinely miss, "
                    "otherwise this asserts nothing about folding",
                )
                self.assertIsNotNone(
                    PATTERNS[label].search(fold_toml_multiline(probe)))

        # Ordinary multiline prose -- every mount purpose in the registry could
        # be written this way -- must not become a finding.
        prose = f"purpose = {dq}\nOrdinary prose describing a mount.\n{dq}"
        folded = fold_toml_multiline(prose)
        self.assertEqual(
            [name for name, pattern in PATTERNS.items() if pattern.search(folded)],
            [],
        )

    def test_the_scan_pipeline_applies_every_normalisation(self):
        """Folding only helps if the real scan path runs it. Both normalisers
        are asserted end to end, through scan_paths, not in isolation."""
        secret = "super" + "-secret-value-0192"
        name = "AZURE" + "_CLIENT_SECRET"
        dq = '"' * 3
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            toml_file = root / "connector.toml"
            toml_file.write_text(
                f"{name} = {dq}{secret}{dq}\n", encoding="utf-8")
            yaml_file = root / "connector.yaml"
            yaml_file.write_text(
                f"{name}: |2-\n  {secret}\n", encoding="utf-8")
            for path in (toml_file, yaml_file):
                with self.subTest(path=path.name):
                    findings = scan_paths([path], root=root)
                    self.assertTrue(
                        any("credential assignment" in f for f in findings),
                        findings,
                    )

    def test_every_key_and_delimiter_combination_is_normalised(self):
        """Cover the GRID, not the reported cell.

        Each normaliser was fixed for a bare key and then bypassed again by a
        quoted one -- YAML and TOML both allow the mapping key to be quoted,
        and both parsers reconstruct the value either way. Fixing the reported
        example twice in a row is what this asserts against: every combination
        of key style and value delimiter that a parser accepts must fold.

        All fragments are assembled at runtime; written literally, these are
        real findings in this file.
        """
        secret = "Xy7Q" + "secretValue0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        cred = "AZURE" + "_CLIENT_SECRET"
        ident = "AZURE" + "_TENANT_ID"
        dq, sq = '"' * 3, "'" * 3

        cases = []
        # key style x YAML block-scalar indicator
        for key in (cred, f'"{cred}"', f"'{cred}'"):
            for indicator in ("|", "|-", ">", ">-", "|2-", "|-2", ">2+"):
                cases.append(
                    ("credential assignment",
                     f"{key}: {indicator}\n  {secret}\n"))
        # key style x TOML multiline delimiter, for both value classes
        for key_name, label, value in (
            (cred, "credential assignment", secret),
            (ident, "connector identifier", guid),
        ):
            for key in (key_name, f'"{key_name}"', f"'{key_name}'"):
                for delim in (dq, sq):
                    cases.append((label, f"{key} = {delim}{value}{delim}\n"))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases):
                probe = root / f"probe{index}.conf"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(body=body):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any(label in finding for finding in findings),
                        f"{body!r} produced {findings}",
                    )

        # Quoting a key must not turn ordinary prose into a finding either.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, body in enumerate((
                '"description": |\n  Ordinary prose about a mount.\n',
                f"'purpose' = {dq}\nOrdinary prose about a mount.\n{dq}\n",
            )):
                clean = root / f"clean{index}.conf"
                clean.write_text(body, encoding="utf-8")
                with self.subTest(clean=body):
                    self.assertEqual(scan_paths([clean], root=root), [])

    @needs_yaml
    def test_explicit_yaml_tags_do_not_hide_the_value(self):
        """A YAML parser discards the tag and keeps the value, so the scan must.

        `AZURE_CLIENT_SECRET: !!str <secret>` put a token between key and value,
        and the bare-value branch matched the TAG and stopped at the following
        space. `!!binary` is itself eight characters, so it even satisfied the
        minimum length -- the scan looked like it had found something when it
        had examined nothing."""
        secret = "Xy7Q" + "secretValue0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        cred = "AZURE" + "_CLIENT_SECRET"
        ident = "AZURE" + "_TENANT_ID"
        token = "TFE" + "_TOKEN"
        # Every tag form YAML defines, not just the reported "!!str".
        tags = ("!!str", "!!binary", "!secret", "!<tag:example.com,2026:s>")

        cases = []
        for tag in tags:
            cases.append(("credential assignment", f"{cred}: {tag} {secret}\n"))
            cases.append(("connector identifier", f"{ident}: {tag} {guid}\n"))
        # Composed with the other shapes already normalised: a quoted key, a
        # sequence entry, and a tag in front of a block scalar.
        cases += [
            ("credential assignment", f'"{cred}": !!str {secret}\n'),
            ("credential assignment", f"- {token}: !!str atlasv1.abcdefghijkl\n"),
            ("credential assignment", f"{cred}: !!str |-\n  {secret}\n"),
        ]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases):
                probe = root / f"tagged{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(body=body):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any(label in finding for finding in findings),
                        f"{body!r} produced {findings}",
                    )

            clean = root / "clean.yaml"
            clean.write_text(
                "description: !!str Ordinary prose about a mount.\n",
                encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    def test_sequence_entries_are_normalised_like_plain_mappings(self):
        """A YAML sequence mapping is an ordinary shape for a list of connector
        entries, and the block-scalar header rejected its `- ` prefix outright.

        Asserted as a matrix over the container shape rather than the reported
        line: every normalised form has to survive being written as a sequence
        entry, because that prefix sits in front of ALL of them."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        dq = '"' * 3
        bodies = [
            f"- {cred}: |-\n    {secret}\n",
            f'- "{cred}": |-\n    {secret}\n',
            f"- {cred}: >-\n    {secret}\n",
            f"- {cred}: |2-\n    {secret}\n",
            f"- {cred}: !!str {secret}\n",
            f"entries:\n  - {cred}: |-\n      {secret}\n",
            f"- {cred} = {dq}{secret}{dq}\n",
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, body in enumerate(bodies):
                probe = root / f"seq{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(body=body):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any("credential assignment" in f for f in findings),
                        f"{body!r} produced {findings}",
                    )

    def test_recursive_intake_does_not_skip_symlinks(self):
        """_scan_files scans a link's TARGET STRING -- what git publishes -- but
        the recursion filtered on is_file(), which is False for a dangling link.
        The pre-install gate therefore skipped exactly the entry the scanner
        knows how to handle, while scanning that same link directly reported
        it."""
        import os

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            # Assembled at runtime; the target names a person and a private path.
            target = "/home/" + "client-contact" + "@" + "example.invalid/private"
            os.symlink(target, bundle / "notes")
            (bundle / "README.md").write_text("ordinary prose\n", encoding="utf-8")

            findings = scan_paths([bundle], root=root)
            self.assertTrue(
                any("notes" in f for f in findings),
                f"the dangling symlink was skipped: {findings}",
            )
            # Scanning the link directly must agree with scanning its parent --
            # the two paths disagreeing is what made this survivable.
            direct = scan_paths([bundle / "notes"], root=root)
            self.assertEqual(
                sorted(f.split(": ", 1)[1] for f in direct),
                sorted(f.split(": ", 1)[1] for f in findings if "notes" in f),
            )

    @needs_yaml
    def test_yaml_node_properties_and_aliases_do_not_hide_the_value(self):
        """Tag, anchor and alias are three tokens that each sit between a key
        and its value, and each hid it from the assignment patterns.

        The tag case was fixed first and the anchor case was the same defect in
        a different token, so this asserts the whole node-property grammar --
        every token, both orders, composed with the container shapes already
        normalised -- rather than the reported line."""
        secret = "Xy7Q" + "secretValue0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        cred = "AZURE" + "_CLIENT_SECRET"
        ident = "AZURE" + "_TENANT_ID"

        properties = ("!!str", "&anchor", "&anchor !!str", "!!str &anchor",
                      "!secret", "!<tag:example.invalid,2026:s>")
        cases = []
        for prop in properties:
            cases.append(("credential assignment", f"{cred}: {prop} {secret}\n"))
            cases.append(("connector identifier", f"{ident}: {prop} {guid}\n"))
        cases += [
            # Composed with the container shapes normalised in earlier rounds.
            ("credential assignment", f'"{cred}": &a {secret}\n'),
            ("credential assignment", f"- {cred}: &a {secret}\n"),
            ("credential assignment", f"{cred}: &a |-\n  {secret}\n"),
            # An alias defers the value to its anchor; resolving it is what a
            # parser hands the application, so the scan must see it too.
            ("credential assignment", f"defaults: &a {secret}\n{cred}: *a\n"),
        ]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases):
                probe = root / f"node{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(body=body):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any(label in finding for finding in findings),
                        f"{body!r} produced {findings}",
                    )

            clean = root / "clean.yaml"
            clean.write_text(
                "description: &d Ordinary prose about a mount.\nother: *d\n",
                encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

        # The old name stays exported: the pipeline and earlier tests called
        # this tag stripping before anchors turned out to be the same defect.
        self.assertIs(strip_yaml_tags, strip_yaml_node_properties)

    @needs_yaml
    def test_a_parser_reconstructs_values_the_patterns_would_miss(self):
        """Six rounds each found a different construct hiding a value from the
        line-oriented patterns. A regex approximates the YAML grammar and the
        grammar keeps winning, so the value extraction now asks a real parser
        what the document MEANS and scans that.

        These probes are deliberately shapes no normaliser handles: flow
        mappings, flow sequences, nesting, and anchors defined outside a
        mapping value."""
        secret = "Xy7Q" + "secretValue0192"
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        cred = "AZURE" + "_CLIENT_SECRET"
        ident = "AZURE" + "_TENANT_ID"
        cases = [
            ("credential assignment", '{"%s": !!str %s}\n' % (cred, secret)),
            ("credential assignment", '{"%s": &a %s}\n' % (cred, secret)),
            ("credential assignment", '{outer: {"%s": !secret %s}}\n' % (cred, secret)),
            ("credential assignment", "%s: [!!str %s]\n" % (cred, secret)),
            # Anchor defined on a sequence scalar, referenced by a credential key.
            ("credential assignment", f"defaults:\n  - &cred {secret}\n{cred}: *cred\n"),
            ("connector identifier",
             f"a:\n  b:\n    c:\n      {ident}: &t {guid}\n      other: *t\n"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases):
                probe = root / f"parsed{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(body=body):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any(label in finding for finding in findings),
                        f"{body!r} produced {findings}",
                    )

            clean = root / "clean.yaml"
            clean.write_text(
                "description: &d Ordinary prose about a mount.\n"
                "other: *d\nlist: [a, b]\n",
                encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    @needs_yaml
    def test_parser_extraction_degrades_instead_of_failing(self):
        """The parser is authoritative where it works, but it must never take
        the scan down: a non-YAML file, an oversized document or a missing
        PyYAML has to fall through to the regex normalisers rather than raise
        or return a false clean."""
        # Genuinely malformed YAML must be REPORTED as unreconstructed, not
        # silently returned as "". An earlier version asserted "" here, which
        # is what let a credential sitting above a syntax error fall through to
        # regexes that cannot decode it. Whether it matters is the caller's
        # decision -- asserted below, through scan_paths.
        self.assertEqual(
            yaml_reconstructed_values("{a: [1, 2}\n"), TRUNCATION_MARKER)
        # Oversized input is not parsed -- but it is REPORTED, not skipped
        # silently. The earlier version of this line asserted "" here, which
        # encoded the defect: padding a file past the cap dropped the parser
        # and the scan still read clean.
        self.assertEqual(
            yaml_reconstructed_values("x" * 3_000_000), TRUNCATION_MARKER)
        # The property that matters for every other input: never raise, always
        # return a string. Python source, markdown and JSON all reach this.
        for probe in ("def f(:\n  not yaml [", "# heading\n\ntext\n",
                      '{"a": 1}', "", "\x00\x01", "a: *undefined_alias\n"):
            with self.subTest(probe=probe[:20]):
                self.assertIsInstance(yaml_reconstructed_values(probe), str)
        # A document using a tag no constructor knows must still yield values,
        # not drop to "" -- those are the documents most worth reading.
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        self.assertIn(secret, yaml_reconstructed_values(f"{cred}: !custom {secret}\n"))

        # And the caller must only ACT on that report where the destination
        # claims the format: a markdown or Python file that happens not to
        # parse as YAML is fully scanned by the patterns and must stay clean,
        # or every large source file fails the gate on a false finding.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("notes.md", "helper.py", "data.json"):
                probe = root / name
                probe.write_text("def f(:\n  not yaml [\n", encoding="utf-8")
                with self.subTest(destination=name):
                    self.assertEqual(scan_paths([probe], root=root), [])
            broken_yaml = root / "config.yaml"
            broken_yaml.write_text("{a: [1, 2}\n", encoding="utf-8")
            self.assertTrue(
                any("incomplete scan" in finding for finding
                    in scan_paths([broken_yaml], root=root)),
                "a file that declares YAML and does not parse is unscanned")

    def test_toml_escapes_are_decoded_by_a_parser_not_by_the_fold(self):
        """The parser argument, one format over.

        `fold_toml_multiline` approximates the TOML grammar the same way the
        old YAML normalisers approximated theirs, and loses in the same two
        places: a quoted key may spell its own name in Unicode escapes, so no
        pattern matching the literal credential name ever sees it; and a
        multiline basic string may contain an ESCAPED triple quote, which the
        non-greedy fold reads as the closing delimiter -- emitting only the
        harmless prefix and leaving the credential after it unscanned and
        keyless. Both decode correctly in tomllib and in nothing short of one.
        """
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        quotes = '"' * 3
        # Written as escapes so this file does not carry the credential name.
        escaped_key = '"AZURE\\u005fCLIENT\\u005fSECRET"'
        cases = {
            "escaped key": '%s = "%s"\n' % (escaped_key, secret),
            # The prefix before the escaped delimiter is deliberately too short
            # to match anything on its own. The fold emits exactly that prefix,
            # so a longer one lets this case report a finding for the remnant
            # while the credential after it is still never scanned -- passing
            # for the wrong reason, which is the failure mode this round keeps
            # producing.
            "escaped delimiter":
                "%s = %s\nok \\%s %s\n%s\n"
                % (cred, quotes, quotes, secret, quotes),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases.items()):
                probe = root / f"escaped{index}.toml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any("credential assignment" in finding
                            for finding in findings),
                        f"{label}: {body!r} produced {findings}",
                    )
                    # And it must be flagged BECAUSE the credential reached the
                    # scanned text, not because some truncated remnant of the
                    # line happened to look credential-shaped.
                    line = toml_reconstructed_values(body)
                    self.assertIn(secret, line, f"{label}: emitted {line!r}")
                    # A reconstructed value containing a quote must not
                    # terminate the scanned line early -- emitting values bare
                    # was how the escaped delimiter kept hiding even once the
                    # parser was reading it.
                    self.assertEqual(line.count('"'), 2,
                                     f"{label}: unbalanced emission {line!r}")

            clean = root / "clean.toml"
            clean.write_text(
                'name = "governance"\npurpose = "read only registry"\n',
                encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    def test_organization_exclusions_must_consume_the_whole_value(self):
        """A placeholder PREFIX is not a placeholder.

        Written as bare lookaheads, `your-`/`my-`/`example-` exempted every
        real slug that merely began with one, so an organization named for a
        client was excused by two characters in front of it. This is the same
        defect already repaired on the hostname exemptions, and it is asserted
        here as a grid rather than as the one reported value, because the
        exclusion list is where this pattern's entire weight sits."""
        pattern = PATTERNS["connector organization"]
        key = "TFE" + "_ORGANIZATION"
        # Real slugs that happen to start with an approved placeholder word.
        for value in ("my-client-prod", "your-real-client",
                      "example-client-prod", "our-northside-utilities"):
            with self.subTest(value=value, expect="flagged"):
                self.assertIsNotNone(
                    pattern.search('%s = "%s"' % (key, value)),
                    "a placeholder prefix must not exempt the value it prefixes",
                )
        # Every exclusion must still hold for the whole-value form, including
        # the determiners the prefix repair introduced.
        for value in ("your-org", "my-org", "our-org", "the-org", "some-org",
                      "example-org", "your_organization", "my-workspace",
                      "example", "placeholder", "organization", "workspace",
                      "name", "<your-org>", "..."):
            with self.subTest(value=value, expect="clean"):
                self.assertIsNone(
                    pattern.search('%s = "%s"' % (key, value)),
                    "an approved whole-value placeholder must stay clean",
                )

    @needs_yaml
    def test_alias_expansion_is_bounded_so_the_guard_cannot_be_the_outage(self):
        """A YAML alias is a shared reference, not a copy.

        Adding the parser added this: four levels of ten-way aliasing expand to
        hundreds of thousands of emitted characters from five lines, without
        ever increasing recursion depth -- so neither MAX_PARSE_BYTES nor the
        RecursionError handler bounds it. A denial-of-service in the privacy
        gate is a way to stop the gate running, which is a way to land
        unscanned material. Bound the OUTPUT, not just the input."""
        bomb = "a: &a [x, x, x, x, x, x, x, x, x, x]\n"
        for name in "bcdefg":
            previous = chr(ord(name) - 1)
            refs = ", ".join([f"*{previous}"] * 10)
            bomb += f"{name}: &{name} [{refs}]\n"

        emitted = yaml_reconstructed_values(bomb)
        self.assertLess(
            len(emitted.splitlines()), MAX_EMITTED_VALUES + 1,
            "the emission budget must cap a shared-reference expansion",
        )
        self.assertLess(len(emitted), 100_000)
        # Bounding it must not make it useless: an ordinary aliased document
        # still has to give up its value.
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        self.assertIn(
            secret,
            yaml_reconstructed_values(
                f"defaults: &d {secret}\n{cred}: *d\n"))

    @needs_yaml
    def test_an_exhausted_reconstruction_budget_fails_the_scan(self):
        """A bound that stops quietly converts the outage into a bypass.

        The budget added to stop an alias bomb also stops on ORDINARY volume:
        pad a file with 20,000 harmless leaves and everything after them is
        never emitted, while the regex fallback cannot normalise the very
        constructs the parser exists to handle. The file then reports clean --
        so padding became a way to push a credential out of scope. A truncated
        reconstruction is an unfinished check, and this repository's rule is
        that an unfinished check is reported, never passed."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        filler_yaml = "".join(
            f"k{index}: v{index}\n" for index in range(MAX_EMITTED_VALUES + 50))
        filler_toml = "".join(
            f'k{index} = "v{index}"\n'
            for index in range(MAX_EMITTED_VALUES + 50))
        # Both formats, and in each the credential sits in a construct only the
        # parser normalises -- so the fallback genuinely cannot cover for it.
        cases = {
            "padded.yaml": filler_yaml + 'tail: {"%s": !!str %s}\n' % (cred, secret),
            "padded.toml": filler_toml + '"AZURE\\u005fCLIENT\\u005fSECRET" = "%s"\n' % secret,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, body in cases.items():
                probe = root / name
                probe.write_text(body, encoding="utf-8")
                with self.subTest(probe=name):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any("incomplete scan" in finding for finding in findings),
                        f"{name}: truncation reported clean -- {findings}",
                    )

            # The marker must not leak into the report as a pattern hit, and a
            # file that fits inside the budget must stay silent.
            ordinary = root / "ordinary.yaml"
            ordinary.write_text("name: governance\npurpose: read only\n",
                                encoding="utf-8")
            self.assertEqual(scan_paths([ordinary], root=root), [])

        # And the bound it was added for still holds: the alias bomb is walked
        # once per shared subtree, so it stays under budget and is not reported
        # as incomplete. Bounding and failing closed are separate properties.
        bomb = "a: &a [x, x, x, x, x, x, x, x, x, x]\n"
        for name in "bcdefg":
            previous = chr(ord(name) - 1)
            bomb += f"{name}: &{name} [{', '.join(['*' + previous] * 10)}]\n"
        self.assertNotIn(TRUNCATION_MARKER, yaml_reconstructed_values(bomb))

    @needs_yaml
    def test_an_oversized_file_is_reported_not_silently_unparsed(self):
        """The size cap is attacker-selectable, so it must fail closed too.

        Round twenty-two made an exhausted BUDGET report an incomplete scan and
        left the size cap returning "" -- indistinguishable, to the caller,
        from "this file is not YAML". Padding a file past 2 MB therefore
        dropped the parser entirely while the scan still read clean, which is
        the same bypass one limit over. Both limits are unfinished checks."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        pad = "# " + "p" * 200 + "\n"
        tail = 'tail: {"%s": !!str %s}\n' % (cred, secret)
        oversized = pad * (MAX_PARSE_BYTES // len(pad) + 5) + tail
        self.assertGreater(len(oversized.encode("utf-8")), MAX_PARSE_BYTES)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe = root / "oversized.yaml"
            probe.write_text(oversized, encoding="utf-8")
            findings = scan_paths([probe], root=root)
            self.assertTrue(
                any("incomplete scan" in finding for finding in findings),
                f"an oversized file reported clean -- {findings}")

            # The TOML side has the same cap and needs the same answer.
            big_toml = "".join(
                f'# {"p" * 200}\n'
                for _ in range(MAX_PARSE_BYTES // 203 + 5))
            toml_probe = root / "oversized.toml"
            toml_probe.write_text(big_toml, encoding="utf-8")
            self.assertTrue(
                any("incomplete scan" in finding
                    for finding in scan_paths([toml_probe], root=root)))

            # An ordinary file must stay silent, or every scan is "incomplete".
            small = root / "small.yaml"
            small.write_text("name: governance\n", encoding="utf-8")
            self.assertEqual(scan_paths([small], root=root), [])

    def test_the_documented_dependency_contract_matches_requirements(self):
        """A dependency added without updating its contract makes docs false.

        `requirements.txt` gained PyYAML for the guard's parser path, and
        `docs/REPOSITORY_OVERVIEW.md` went on saying it holds "exactly one
        dependency" and that the whole suite runs stdlib-only — which had
        stopped being true, in eight failing tests. Both halves are asserted:
        the overview must name every installed requirement, and the parser
        tests must degrade the way the scanner does so stdlib-only survives."""
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        overview = (ROOT / "docs" / "REPOSITORY_OVERVIEW.md").read_text(
            encoding="utf-8")

        declared = [
            line.split(";")[0].strip()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(declared, "requirements.txt parsed as empty")
        for entry in declared:
            name = re.split(r"[<>=!~\[]", entry, maxsplit=1)[0].strip()
            with self.subTest(package=name):
                self.assertIn(
                    name, overview,
                    "the overview's dependency section must name every "
                    "package CI installs")
        # The stale count claim in particular.
        self.assertNotIn("exactly one dependency", overview)

        # And the suite must still be runnable without the optional package,
        # which is what makes the "stdlib-only" claim true rather than aspirational.
        self.assertIn("needs_yaml", (ROOT / "tests" / "test_privacy.py").read_text(
            encoding="utf-8"))

    def test_only_reserved_names_are_excused_as_example_hosts(self):
        """"Looks like a placeholder" is not a reservation.

        `example.`/`your-`/`.example` were written as unbounded prefixes and
        infixes, so a real customer host beginning with one, or carrying
        `.example` before a later suffix, was excused outright. RFC 2606
        reserves exactly example.com/.net/.org and the .example/.invalid/.test
        TLDs; everything else is a registrable name, and this repository's own
        rule is that uncertain counts as real. Asserted as a grid, because the
        exclusions carry this pattern's entire weight."""
        addr, tenant, scheme = "TFE" + "_ADDRESS", "AZURE" + "_TENANT_ID", "https"
        must_flag = {
            "reserved-looking prefix": f'{addr} = "{scheme}://example.customer.com"',
            "reserved-looking infix": f'{tenant} = "corp.example.evil"',
            "your- prefixed host": f'{addr} = "{scheme}://your-corp.internal"',
            "your- prefixed domain": f'{tenant} = "your-tenant.com"',
            "example as a label": f'{addr} = "{scheme}://example.company.net"',
            "plain private host": f'{addr} = "{scheme}://tfe.clientcorp.com"',
        }
        must_be_clean = {
            "example.com": f'{addr} = "{scheme}://example.com"',
            "subdomain of example.com": f'{tenant} = "tenant.example.com"',
            ".example TLD": f'{addr} = "{scheme}://tfe.example"',
            ".invalid TLD": f'{addr} = "{scheme}://tfe.invalid"',
            ".test TLD": f'{tenant} = "tenant.test"',
            "public SaaS endpoint": f'{addr} = "{scheme}://app.terraform.io"',
            "loopback": f'{addr} = "{scheme}://localhost:8080"',
            "angle-bracket placeholder": f'{tenant} = "<your-tenant-id>"',
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for group, cases, expected in (("flag", must_flag, True),
                                           ("clean", must_be_clean, False)):
                for index, (label, body) in enumerate(cases.items()):
                    probe = root / f"{group}{index}.toml"
                    probe.write_text(body + "\n", encoding="utf-8")
                    with self.subTest(case=label, expect=group):
                        self.assertEqual(
                            bool(scan_paths([probe], root=root)), expected,
                            f"{label}: {body}")

    def test_a_nested_credential_name_is_reconstructed_whole(self):
        """A credential name is routinely split across tables.

        `[AZURE.CLIENT]` then `SECRET = ...` is ordinary, valid, and was
        emitted as bare `SECRET` -- reconstructed by the parser and then thrown
        away one step before it would have been matched. Joining the path is
        necessary but not sufficient: under a deeper table the full join reads
        `a_b_AZURE_CLIENT_SECRET`, and `\\b` does not match between `b` and
        `AZURE`, so the name is present and still unmatchable. Every suffix is
        emitted, and the grid runs to depth so a two-level fix cannot pass."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        cases = {
            "toml table": ("t0.toml", '[AZURE.CLIENT]\nSECRET = "%s"\n' % secret),
            "toml inline table":
                ("t1.toml", 'AZURE = { CLIENT = { SECRET = "%s" } }\n' % secret),
            "toml nested two deep":
                ("t2.toml", '[a.b.AZURE.CLIENT]\nSECRET = "%s"\n' % secret),
            "toml nested four deep":
                ("t3.toml", '[w.x.y.z.AZURE.CLIENT]\nSECRET = "%s"\n' % secret),
            # YAML cases are parser-only, so they carry the same gate every
            # other parser test carries. Gating four tests and then adding a
            # fifth with ungated YAML subtests reintroduced the stdlib-only
            # failure the gate exists to prevent -- in the same round.
            **({} if not _have_yaml() else {
                "yaml nested":
                    ("y0.yaml",
                     "AZURE:\n  CLIENT:\n    SECRET: %s\n" % secret),
                "yaml nested flow":
                    ("y1.yaml",
                     "a: {b: {AZURE: {CLIENT: {SECRET: %s}}}}\n" % secret),
            }),
            "flat control": ("t4.toml", '%s = "%s"\n' % (cred, secret)),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label, (name, body) in cases.items():
                probe = root / name
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any("credential assignment" in finding
                            for finding in findings),
                        f"{label}: {body!r} produced {findings}")

            # Nesting must not invent findings: a registry of ordinary nested
            # tables has to stay silent, or every config file reports.
            clean = root / "clean.toml"
            clean.write_text(
                '[mount.governance]\nname = "governance"\n'
                'purpose = "read only registry"\n', encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    @needs_yaml
    def test_an_alias_is_reconstructed_under_every_key_that_reaches_it(self):
        """Deduplicating by object identity made reconstruction context-free.

        An alias is a shared reference, so a mapping first reached under an
        innocuous key and later aliased beneath a credential-forming one is the
        SAME object at two paths. The round-21 visited set keyed on identity
        alone, so the second path was suppressed and only the harmless one was
        emitted -- a bypass anyone can write: anchor the payload somewhere
        boring, alias it where it counts. The key is now (identity, path)."""
        secret = "Xy7Q" + "secretValue0192"
        cases = {
            "anchored elsewhere, aliased at the credential key":
                "payload: &shared\n  SECRET: %s\nAZURE_CLIENT: *shared\n" % secret,
            "aliased at the credential key only":
                "AZURE_CLIENT: &s\n  SECRET: %s\n" % secret,
            "two aliases, one of them credential-forming":
                "a: &s\n  SECRET: %s\nb: *s\nAZURE_CLIENT: *s\n" % secret,
            "alias nested under a further key":
                "payload: &s\n  SECRET: %s\nouter:\n  AZURE_CLIENT: *s\n" % secret,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(cases.items()):
                probe = root / f"alias{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    findings = scan_paths([probe], root=root)
                    self.assertTrue(
                        any("credential assignment" in finding
                            for finding in findings),
                        f"{label}: {body!r} produced {findings}")

        # The bound this visited set exists for must survive the change: a wide
        # alias graph is still walked once per distinct path, not exponentially.
        bomb = "a: &a [x, x, x, x, x, x, x, x, x, x]\n"
        for name in "bcdefg":
            previous = chr(ord(name) - 1)
            bomb += f"{name}: &{name} [{', '.join(['*' + previous] * 10)}]\n"
        emitted = yaml_reconstructed_values(bomb)
        self.assertLess(len(emitted), 100_000)
        self.assertNotIn(TRUNCATION_MARKER, emitted)
        # And a self-referential document must still terminate rather than
        # recurse forever now that the visit key includes the path.
        self.assertIsInstance(
            yaml_reconstructed_values("a: &a\n  self: *a\n"), str)

    def test_every_parser_dependent_test_carries_the_dependency_gate(self):
        """Gating four tests and then adding a fifth is how this recurs.

        The stdlib-only property is a repository-wide claim, and it breaks the
        moment one new test touches the parser without the gate -- which is
        exactly what happened one round after the gate was introduced, in a
        mixed TOML/YAML test whose YAML subtests were ungated."""
        import ast
        from unittest import mock

        source = (ROOT / "tests" / "test_privacy.py").read_text(encoding="utf-8")
        candidates = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_") or node.name == self._testMethodName:
                continue
            body = ast.get_source_segment(source, node) or ""
            if ".yaml" not in body and "yaml_reconstructed_values" not in body:
                continue
            gated = any(
                getattr(decorator, "id", getattr(decorator, "attr", ""))
                == "needs_yaml"
                for decorator in node.decorator_list)
            if not gated:
                candidates.append(node.name)

        self.assertTrue(candidates,
                        "no ungated YAML-touching tests found; test is vacuous")

        # A source heuristic cannot tell which of these actually NEED the
        # parser -- most are satisfied by the regex normalisers, which is why a
        # blanket "gate anything mentioning .yaml" rule would be wrong. So
        # assert the operational property directly: with reconstruction
        # disabled, exactly as it is when PyYAML is absent, every ungated test
        # must still pass. Anything that fails here belongs behind the gate.
        failures = []
        with open(os.devnull, "w", encoding="utf-8") as quiet:
            for name in candidates:
                # Simulate the REAL condition -- PyYAML absent -- by making the
                # import fail, not by stubbing the reconstruction to "".
                # Stubbing was stricter than reality: the size and syntax
                # checks run before the import and still report, so a test
                # relying on those passes without PyYAML and was being flagged
                # as needing a gate it does not need.
                with mock.patch.dict(sys.modules, {"yaml": None}):
                    result = unittest.TextTestRunner(
                        stream=quiet, verbosity=0,
                    ).run(unittest.TestLoader().loadTestsFromName(
                        name, type(self)))
                if not result.wasSuccessful():
                    failures.append(name)

        self.assertEqual(
            failures, [],
            "these tests need the YAML parser but carry no PyYAML gate, so a "
            "stdlib-only run fails instead of skipping")

    def test_an_extended_placeholder_loses_its_exemption(self):
        """An approved snippet is exempt only where it stands ALONE.

        Stripping removed the key and the delimiter along with the pinned
        sample, so an approved assignment that had been EXTENDED — the sample,
        a concatenation operator, then a second real value — left an unkeyed
        opaque string behind. The credential-assignment pattern had lost its
        key, the secret-token pattern needs a vendor prefix, and the file
        reported clean. Whitespace before the operator satisfied the existing
        boundary check, so nothing caught it."""
        relative = Path(
            ".github/instructions/security-and-owasp.instructions.md")
        placeholder = PLACEHOLDER_LITERALS[relative][0]
        real = "real" + "OpaqueCredentialValue123"

        # Every way an expression can continue, not just the reported one.
        extensions = {
            "concatenation": f"{placeholder} + '{real}'",
            "concatenation, no spaces": f"{placeholder}+'{real}'",
            "implicit adjacency": f"{placeholder} '{real}'",
            "percent formatting": f"{placeholder} % '{real}'",
            "method call": f"{placeholder}.concat('{real}')",
            "line continuation": f"{placeholder} \\\n    + '{real}'",
        }
        for label, line in extensions.items():
            stripped = strip_known_placeholders(relative, line)
            with self.subTest(extension=label):
                self.assertTrue(
                    any(pattern.search(stripped)
                        for pattern in PATTERNS.values()),
                    f"{label}: an extended approved snippet must not stay "
                    f"exempt -- stripped to {stripped!r}")

        # The approved snippet standing alone must still be exempt, in every
        # context it actually appears in: statement terminator, end of line,
        # and inside an object literal.
        for label, line in {
            "terminated": f"const {placeholder};",
            "end of line": f"const {placeholder}\n",
            "object literal": f"{placeholder} }});",
        }.items():
            with self.subTest(standalone=label):
                self.assertFalse(
                    any(pattern.search(strip_known_placeholders(relative, line))
                        for pattern in PATTERNS.values()),
                    f"{label}: the approved snippet itself must stay exempt")

        # And the real tracked files must still pass, which is what stops this
        # from being fixed by simply refusing to strip anything.
        self.assertEqual(scan_repository(ROOT), [])

    @needs_yaml
    def test_the_reconstruction_keeps_every_duplicate_mapping_entry(self):
        """The constructor discards data before the walker ever sees it.

        PyYAML keeps only the LAST entry when a mapping repeats a key, so a
        credential under a duplicated key was dropped by the parser and the
        reconstruction emitted only the benign value. Walking the composed node
        graph preserves every source entry.

        Scoped deliberately to the RECONSTRUCTION. Every scan-level probe I
        built for this was still caught by the raw-text normalisers, so I have
        no demonstration that it was an exploitable bypass -- it is a fidelity
        defect in the authoritative layer, fixed as defence in depth, and this
        test claims exactly that and no more."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        cases = {
            "flow mapping, credential first":
                '{"%s": !!str %s, "%s": harmless}\n' % (cred, secret, cred),
            "block mapping, credential first":
                "%s: %s\n%s: harmless\n" % (cred, secret, cred),
            "duplicate under a shared parent":
                "outer:\n  %s: %s\n  %s: harmless\n" % (cred, secret, cred),
        }
        for label, body in cases.items():
            with self.subTest(case=label):
                emitted = yaml_reconstructed_values(body)
                self.assertIn(
                    secret, emitted,
                    f"{label}: the earlier entry was discarded by the "
                    f"constructor -- emitted {emitted!r}")
                self.assertIn("harmless", emitted,
                              "the later entry must survive too")

    @needs_yaml
    def test_an_unfinished_reconstruction_is_reported_only_where_it_matters(self):
        """Both halves, because each alone is a defect this round found.

        Reporting too little: a `.toml` file whose syntax breaks below a
        credential fell back to regexes that cannot decode an escaped key, and
        read clean. Reporting too much: marking every oversized document failed
        ordinary markdown and Python sources over 2 MB as "incomplete
        reconstruction", which is a false finding, and a gate that cries wolf
        is one people learn to override."""
        secret = "Xy7Q" + "secretValue0192"
        escaped_key = '"AZURE\\u005fCLIENT\\u005fSECRET"'
        oversized = "# " + ("x" * 200 + "\n# ") * (MAX_PARSE_BYTES // 203 + 5)

        must_report = {
            "toml syntax error below a credential":
                ("a.toml", '%s = "%s"\nbroken = [\n' % (escaped_key, secret)),
            "toml unparseable outright": ("b.toml", "= = =\n"),
            # YAML cases need the parser to produce the marker; the TOML and
            # size paths do not, so gate only these and keep the rest running
            # in a stdlib-only environment.
            **({} if not _have_yaml() else {
                "yaml unparseable": ("c.yaml", "{a: [1, 2}\n"),
                "oversized yaml": ("d.yaml", "k: v\n" * 200_000),
            }),
            "oversized toml": ("e.toml", oversized),
        }
        must_stay_clean = {
            "oversized markdown": ("f.md", oversized),
            "oversized python": ("g.py", oversized),
            "unparseable markdown": ("h.md", "def f(:\n  not yaml [\n"),
            "ordinary toml": ("i.toml", 'name = "governance"\n'),
            "ordinary yaml": ("j.yaml", "name: governance\n"),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for group, cases, expected in (("report", must_report, True),
                                           ("clean", must_stay_clean, False)):
                for label, (name, body) in cases.items():
                    probe = root / name
                    probe.write_text(body, encoding="utf-8")
                    with self.subTest(case=label, expect=group):
                        self.assertEqual(
                            bool(scan_paths([probe], root=root)), expected,
                            f"{label}")

    def test_reconstruction_is_bounded_by_depth_not_by_the_stack(self):
        """A deeply nested document must yield a finding, never a crash.

        A ~1000-component dotted key is ordinary valid TOML and raised
        RecursionError straight out of the privacy gate, which is a way to stop
        the scan running rather than be reported by it. Shallower ones still
        generated hundreds of thousands of suffix forms, because suffix
        emission is O(depth) per leaf."""
        import time

        for depth in (200, 1_000, 5_000):
            body = ".".join(f"k{index}" for index in range(depth)) + ' = "v"\n'
            started = time.time()
            emitted = toml_reconstructed_values(body)
            with self.subTest(format="toml", depth=depth):
                self.assertIn(TRUNCATION_MARKER, emitted)
                self.assertLess(len(emitted), 10_000)
                self.assertLess(time.time() - started, 10)

        if _have_yaml():
            deep_yaml = "".join("  " * level + f"k{level}:\n"
                                for level in range(1_200))
            deep_yaml += "  " * 1_200 + "leaf: value\n"
            self.assertIn(TRUNCATION_MARKER,
                          yaml_reconstructed_values(deep_yaml))

        # Ordinary nesting must still reconstruct, or the cap has swallowed the
        # feature it is protecting.
        secret = "Xy7Q" + "secretValue0192"
        self.assertIn(
            secret,
            toml_reconstructed_values('[AZURE.CLIENT]\nSECRET = "%s"\n' % secret))

    def test_private_material_in_a_path_is_reported(self):
        """A path is published exactly as content is.

        A file named for a tenant id or a client's address names that thing in
        the repository listing whatever the file contains. Only the basename
        allowlist and the artifact-suffix rule applied to paths -- while the
        adjacent gitlink handling already ran every pattern over a published
        path string, which is the same string reached by a different code
        path."""
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        address = "client" + "@" + "clientcorp.com"
        flagged = {
            "connector id in the name": f"AZURE_TENANT_ID={guid}.md",
            "address in the name": f"notes-for-{address}.md",
            "connector id in a directory": f"AZURE_TENANT_ID={guid}/README.md",
        }
        clean = {
            "ordinary name": "ordinary-notes.md",
            "reserved placeholder": "tenant.example.com-notes.md",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for group, cases, expected in (("flag", flagged, True),
                                           ("clean", clean, False)):
                for label, name in cases.items():
                    probe = root / "docs" / name
                    probe.parent.mkdir(parents=True, exist_ok=True)
                    probe.write_text("nothing notable\n", encoding="utf-8")
                    with self.subTest(case=label, expect=group):
                        findings = scan_paths([probe], root=root)
                        self.assertEqual(bool(findings), expected, f"{label}")
                        if expected:
                            self.assertTrue(
                                any("in the file path" in finding
                                    for finding in findings),
                                "the finding must say the PATH is the problem")

        # And the tracked tree must still pass, so this cannot be satisfied by
        # a rule that flags ordinary repository paths.
        self.assertEqual(scan_repository(ROOT), [])

    @needs_yaml
    def test_the_walk_is_bounded_by_work_not_only_by_emitted_values(self):
        """A budget that counts only leaves bounds nothing.

        `x: &x {a: *x, b: *x}` emits no scalars at all, so the emitted-value
        budget never decremented — while keying visits on (identity, path),
        which round 25 added to stop an aliased credential being suppressed,
        made every alias branch a distinct visit. The depth cap then enumerated
        an exponential tree and the gate hung on a one-line file. Work is
        charged per node popped now, which is the only quantity that bounds a
        graph walk."""
        import time

        cycles = {
            "two-way scalar-free cycle": "x: &x {a: *x, b: *x}\n",
            "three-way cycle": "x: &x {a: *x, b: *x, c: *x}\n",
            "cycle referenced again": "x: &x {a: *x, b: *x}\ny: *x\nz: *x\n",
            "self-referential mapping": "a: &a\n  self: *a\n",
        }
        for label, body in cycles.items():
            started = time.time()
            emitted = yaml_reconstructed_values(body)
            with self.subTest(case=label):
                self.assertLess(time.time() - started, 15,
                                f"{label}: the walk did not terminate promptly")
                self.assertIsInstance(emitted, str)

        # Bounding must not have cost ordinary reconstruction.
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        self.assertIn(secret, yaml_reconstructed_values(
            "payload: &s %s\n%s: *s\n" % (secret, cred)))

    @needs_yaml
    def test_an_unexpected_node_shape_degrades_instead_of_raising(self):
        """The gate reports; it never aborts.

        A complex mapping key -- `? [a, b]` -- composes to a SequenceNode, and
        putting it into the path made the tuple unhashable, so the visited-set
        lookup raised TypeError straight out of the privacy gate. An untrusted
        intake file must not be able to stop the scan running; the worst it
        should achieve is an incomplete-scan finding."""
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        shapes = {
            "complex sequence key": "? [a, b]\n: {x: y}\n",
            "complex mapping key": "? {a: b}\n: value\n",
            "complex key beside a credential":
                "outer:\n  ? [a, b]\n  : {%s: %s}\n" % (cred, secret),
            "complex key at the root with an alias":
                "? &k [a, b]\n: *k\n",
        }
        for label, body in shapes.items():
            with self.subTest(case=label):
                # The contract is "returns a string", never "raises".
                self.assertIsInstance(yaml_reconstructed_values(body), str)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            probe = root / "complex.yaml"
            probe.write_text(shapes["complex key beside a credential"],
                             encoding="utf-8")
            # And a credential sitting next to the odd shape is still found.
            self.assertTrue(
                any("credential assignment" in finding
                    for finding in scan_paths([probe], root=root)))

    @needs_yaml
    def test_json_is_covered_by_the_completeness_check(self):
        """JSON is a subset of YAML, so the YAML reader is authoritative for it.

        The format gate added last round listed `.yaml`, `.yml` and `.toml` and
        omitted `.json`, so a JSON connector config with an escaped credential
        key and a syntax error after it fell through to raw patterns that
        cannot decode the escapes, and read clean. The patterns already claim
        explicit JSON support; the completeness check has to cover the same
        formats the patterns do."""
        secret = "Xy7Q" + "secretValue0192"
        escaped = '"AZURE\\u005fCLIENT\\u005fSECRET"'
        cases = {
            "escaped key plus trailing garbage":
                ("a.json", '{%s:"%s"} garbage\n' % (escaped, secret), True),
            "escaped key, valid json":
                ("b.json", '{%s:"%s"}\n' % (escaped, secret), True),
            "unparseable json": ("c.json", "{not json\n", True),
            "ordinary json": ("d.json", '{"name":"governance"}\n', False),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label, (name, body, expected) in cases.items():
                probe = root / name
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    self.assertEqual(
                        bool(scan_paths([probe], root=root)), expected, label)

    def test_a_filename_cannot_become_a_scanner_option(self):
        """A path argument must be a path, whatever it is named.

        The changed-file invocation the template prescribes is built from
        filenames, so a repository file called `--help` landed as the scanner's
        first argument: it printed usage, exited 0, and scanned none of the
        remaining paths. A green gate over an unscanned tree, chosen by whoever
        named the file. `--` ends option parsing."""
        import scripts.privacy_guard as guard

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "--help").write_text("harmless\n", encoding="utf-8")
            planted = "API" + "_KEY" + ' = "' + "an" + 'ActualPrivateCredential"'
            (root / "leaky.toml").write_text(planted + "\n", encoding="utf-8")

            # Without `--`, the option-looking name is still interpreted --
            # which is why the template must pass it.
            self.assertEqual(guard.main(["--help"]), 0)

            # With `--`, both are treated as paths and the credential is found.
            # Assert on the REPORT, not just the exit code: without `--`
            # handling, `--` itself is taken as a path and the run exits 1
            # because that path is unreadable -- the right number for the wrong
            # reason, which is how the first version of this test passed
            # against the unfixed commit.
            import contextlib
            import io

            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                code = guard.main(
                    ["--", str(root / "--help"), str(root / "leaky.toml")])
            report = captured.getvalue()

            self.assertEqual(code, 1,
                             "the scan must fail, not print usage and exit 0")
            self.assertIn("credential assignment", report,
                          "the planted credential must be reported")
            self.assertIn("leaky.toml", report)
            self.assertNotIn("usage: privacy_guard.py", report)
            # `--` must have been consumed as the separator, never scanned as a
            # path of its own.
            self.assertNotIn("unreadable", report)

    def test_normalisers_stay_linear_on_hostile_lines(self):
        """A gate that can be stalled is a gate that can be skipped.

        `_TOML_MULTILINE` was unanchored, so its key expression was retried
        from every character of every line; because the key matches greedily
        and then has to find `=`, a long identifier-like line backtracked
        quadratically -- 16,000 characters took over four seconds, so an
        ordinary sub-2 MB markdown or vendored file could stall intake and CI
        before either emitted a finding. A TOML assignment always begins a line
        (inline tables cannot contain newlines), so anchoring is correct as
        well as linear."""
        import time

        # Growth must be roughly linear, not quadratic. Absolute timings vary
        # by machine, so assert the SHAPE: 8x the input must not cost anywhere
        # near 64x the time.
        timings = {}
        for size in (8_000, 64_000):
            probe = "a" * size + "\n"
            started = time.time()
            fold_toml_multiline(probe)
            timings[size] = time.time() - started
        self.assertLess(timings[64_000], 2.0,
                        f"64k of one line took {timings[64_000]:.2f}s")

        # A realistic hostile file: many long non-assignment lines.
        bulk = ("b" * 4_000 + "\n") * 200
        started = time.time()
        fold_toml_multiline(bulk)
        self.assertLess(time.time() - started, 5.0)

        # Anchoring must not have cost the fold its job.
        secret = "Xy7Q" + "secretValue0192"
        cred = "AZURE" + "_CLIENT_SECRET"
        quotes = '"' * 3
        for label, body in {
            "bare key": "%s = %s\n%s\n%s\n" % (cred, quotes, secret, quotes),
            "quoted key": '"%s" = %s\n%s\n%s\n' % (cred, quotes, secret, quotes),
            "indented": "  %s = %s\n%s\n%s\n" % (cred, quotes, secret, quotes),
            "literal delimiter": "%s = '''\n%s\n'''\n" % (cred, secret),
        }.items():
            with self.subTest(form=label):
                self.assertIn(secret, fold_toml_multiline(body))

    @needs_yaml
    def test_normalisation_only_adds_readings_never_removes_one(self):
        """Every normaliser is destructive by design.

        `strip_yaml_node_properties` deletes anchors and tags so the value
        beneath them can be read -- and a credential can live in the deleted
        metadata itself. An anchor NAMED for a cloud access key matched the raw
        text and then vanished from the only copy carrying it, while the
        composed-node reconstruction emits values, not property spellings. The
        raw text is now scanned alongside every normalised copy."""
        akia = "AKIA" + "ABCDEFGHIJKLMNOP"
        token = "gh" + "p_abcdefghijklmnop"
        hidden_in_metadata = {
            "anchor name": "key: &%s benign\n" % akia,
            "tag name": "key: !%s benign\n" % akia,
            "anchor on a sequence entry": "- &%s benign\n" % akia,
            "token as an anchor": "key: &%s benign\n" % token,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, body) in enumerate(hidden_in_metadata.items()):
                probe = root / f"meta{index}.yaml"
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    self.assertTrue(scan_paths([probe], root=root),
                                    f"{label}: {body!r}")

            # An ordinary anchor is still not a finding, so this is not simply
            # "flag every anchor".
            clean = root / "clean.yaml"
            clean.write_text("key: &shared benign\nother: *shared\n",
                             encoding="utf-8")
            self.assertEqual(scan_paths([clean], root=root), [])

    @needs_yaml
    def test_a_keyless_scalar_is_still_scanned(self):
        """A document can BE a scalar, and that one had no key.

        Requiring a key path discarded every decoded value in a top-level
        scalar or a root sequence, so an escaped token in a bare JSON or YAML
        string was invisible -- while the unescaped form is caught by the raw
        scan. The decoded text is the finding; the key is not what made it
        one."""
        cases = {
            "json escaped scalar": ("k0.json", '"gh\\u0070_abcdefghijklmnop"\n'),
            "yaml escaped scalar": ("k1.yaml", '"gh\\x70_abcdefghijklmnop"\n'),
            "root sequence entry": ("k2.yaml", '- "gh\\x70_abcdefghijklmnop"\n'),
            "json array entry": ("k3.json", '["gh\\u0070_abcdefghijklmnop"]\n'),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label, (name, body) in cases.items():
                probe = root / name
                probe.write_text(body, encoding="utf-8")
                with self.subTest(case=label):
                    self.assertTrue(scan_paths([probe], root=root), label)

            for name, body in (("ok.json", '"an ordinary string"\n'),
                               ("ok.yaml", "- just a list entry\n")):
                probe = root / name
                probe.write_text(body, encoding="utf-8")
                with self.subTest(clean=name):
                    self.assertEqual(scan_paths([probe], root=root), [])

    def test_a_reserved_host_exemption_requires_the_expression_to_stop(self):
        """The same continuation trick, one pattern over.

        Round 26 stopped an approved PLACEHOLDER being extended by a
        concatenation operator. The reserved-HOST exemptions had the identical
        hole: the reserved name ends at its closing quote, satisfying HOST_END,
        while the real endpoint is assembled from the literal after it."""
        address = "TFE" + "_ADDRESS"
        scheme = "https"
        must_flag = {
            "concatenated": f'{address} = "{scheme}://example.com" + ".corp.com"',
            "adjacent literal": f'{address} = "{scheme}://example.com" ".corp.com"',
            "formatted": f'{address} = "{scheme}://example.com" %% suffix',
            "loopback continued": f'{address} = "{scheme}://localhost" + ".corp"',
            "saas continued":
                f'{address} = "{scheme}://app.terraform.io" + ".corp"',
            "plain private host": f'{address} = "{scheme}://tfe.clientcorp.com"',
        }
        must_be_clean = {
            "reserved alone": f'{address} = "{scheme}://example.com"',
            "reserved subdomain": f'{address} = "{scheme}://tfe.example.com"',
            "reserved tld": f'{address} = "{scheme}://tfe.invalid"',
            "public saas": f'{address} = "{scheme}://app.terraform.io"',
            "loopback with port": f'{address} = "{scheme}://localhost:8080"',
            "unquoted reserved": f"{address} = {scheme}://example.com",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for group, cases, expected in (("flag", must_flag, True),
                                           ("clean", must_be_clean, False)):
                for index, (label, body) in enumerate(cases.items()):
                    probe = root / f"{group}{index}.py"
                    probe.write_text(body + "\n", encoding="utf-8")
                    with self.subTest(case=label, expect=group):
                        self.assertEqual(
                            bool(scan_paths([probe], root=root)), expected,
                            f"{label}: {body}")

    def test_the_option_separator_keeps_the_options_before_it(self):
        """`--` ends option PARSING; it does not discard the options.

        The first repair returned early on the literal paths, which dropped
        `--as` -- so the documented option-safe form `--as DEST -- <path>`
        skipped the destination check that the same call without the separator
        applies. Both properties have to hold at once: a filename cannot become
        an option, and an option before the separator still counts."""
        import contextlib
        import io

        import scripts.privacy_guard as guard

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            benign = root / "-leading-dash.json"
            benign.write_text('{"ok": 1}\n', encoding="utf-8")

            # The destination check must apply with and without the separator.
            for argv in (["--as", "credentials.json", str(benign)],
                         ["--as", "credentials.json", "--", str(benign)]):
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    code = guard.main(argv)
                with self.subTest(argv=" ".join(argv)):
                    self.assertEqual(code, 1)
                    self.assertIn("prohibited private filename",
                                  captured.getvalue())

            # And the round-28 property must still hold.
            (root / "--help").write_text("harmless\n", encoding="utf-8")
            planted = "API" + "_KEY" + ' = "' + "an" + 'ActualPrivateCredential"'
            (root / "leaky.toml").write_text(planted + "\n", encoding="utf-8")
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                code = guard.main(
                    ["--", str(root / "--help"), str(root / "leaky.toml")])
            self.assertEqual(code, 1)
            self.assertIn("credential assignment", captured.getvalue())
            self.assertNotIn("usage: privacy_guard.py", captured.getvalue())

    def test_a_missing_parser_fails_closed_for_declared_formats(self):
        """The local gate must not be weaker than CI.

        Without PyYAML the reconstruction returned "" and a declared YAML or
        JSON file passed on the fallback regexes, which cannot decode an
        escaped credential key -- so the mandated local command could approve a
        credential-bearing file that CI, where PyYAML is installed, would
        reject. A gate that is more permissive on the developer's machine than
        in CI is the wrong way round: the developer's run is the one that
        happens before the commit."""
        from unittest import mock

        import scripts.privacy_guard as guard

        secret = "Xy7Q" + "secretValue0192"
        escaped = '"AZURE\\u005fCLIENT_SECRET"'
        declared = {
            "yaml": ("p.yaml", "%s: \"%s\"\n" % (escaped, secret)),
            "yml": ("q.yml", "%s: \"%s\"\n" % (escaped, secret)),
            "json": ("r.json", "{%s: \"%s\"}\n" % (escaped, secret)),
        }
        undeclared = {
            "markdown": ("s.md", "ordinary prose\n"),
            "python": ("t.py", "x = 1\n"),
            "toml": ("u.toml", 'name = "governance"\n'),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Simulate the real condition: the import fails.
            with mock.patch.dict(sys.modules, {"yaml": None}):
                for label, (name, body) in declared.items():
                    probe = root / name
                    probe.write_text(body, encoding="utf-8")
                    with self.subTest(declared=label):
                        self.assertTrue(
                            scan_paths([probe], root=root),
                            f"{label}: a declared format with no parser must "
                            f"report an incomplete scan")
                for label, (name, body) in undeclared.items():
                    probe = root / name
                    probe.write_text(body, encoding="utf-8")
                    with self.subTest(undeclared=label):
                        self.assertEqual(
                            scan_paths([probe], root=root), [],
                            f"{label}: a file that never claimed YAML must "
                            f"stay clean without the parser")

    def test_every_exemption_in_every_pattern_rejects_a_continuation(self):
        """Asserted across ALL patterns, because that is the miss.

        Round 30 gave the endpoint pattern a continuation guard and left the
        connector-identifier and organization patterns -- sitting directly
        beneath it, with the same reserved-name exemptions -- without one. The
        same value assembled from a reserved literal plus a second string
        passed both. Fixing one instance of a class and not its siblings is the
        error this whole review keeps finding, so this test enumerates the
        exemption-bearing patterns rather than naming one."""
        address, tenant = "TFE" + "_ADDRESS", "AZURE" + "_TENANT_ID"
        organization, scheme = "TFE" + "_ORGANIZATION", "https"

        # (pattern, exempt value that must stay clean alone, real suffix)
        exemptions = [
            ("private connector endpoint",
             f'{address} = "{scheme}://example.com"', ".corp.com"),
            ("private connector endpoint",
             f'{address} = "{scheme}://tfe.invalid"', ".corp.com"),
            ("private connector endpoint",
             f'{address} = "{scheme}://localhost"', ".corp.com"),
            ("connector identifier",
             f'{tenant} = "tenant.example.com"', ".client.com"),
            ("connector identifier",
             f'{tenant} = "tenant.invalid"', ".client.com"),
            ("connector organization",
             f'{organization} = "your-org"', "-realclient"),
            ("connector organization",
             f'{organization} = "example-org"', "-realclient"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, alone, suffix) in enumerate(exemptions):
                clean_probe = root / f"alone{index}.py"
                clean_probe.write_text(alone + "\n", encoding="utf-8")
                with self.subTest(pattern=label, form="uncontinued"):
                    self.assertEqual(
                        scan_paths([clean_probe], root=root), [],
                        f"{alone}: an exempt value standing alone must stay "
                        f"clean")

                # Every way the expression can continue past the exemption.
                for style, continued in {
                    "concatenated": f'{alone} + "{suffix}"',
                    "adjacent literal": f'{alone} "{suffix}"',
                    "formatted": f"{alone} % suffix",
                }.items():
                    probe = root / f"cont{index}_{style.split()[0]}.py"
                    probe.write_text(continued + "\n", encoding="utf-8")
                    with self.subTest(pattern=label, form=style):
                        self.assertTrue(
                            scan_paths([probe], root=root),
                            f"{continued}: a continued expression must not "
                            f"inherit the exemption")

    def test_placeholder_stripping_requires_whole_token_boundaries(self):
        """A placeholder is only approved as a complete lexical unit.

        Plain substring removal deleted an approved literal wherever it
        appeared, including as the prefix of a longer real value -- which left
        a residue that matched nothing and reported the file clean."""
        relative = Path(
            ".github/instructions/self-explanatory-code-commenting.instructions.md")
        # Assembled at runtime so this file does not carry the address itself.
        placeholder = "username" + "@" + "domain.extension"
        real = placeholder + ".client-corp.com"

        stripped_real = strip_known_placeholders(relative, f"contact {real} today")
        self.assertIsNotNone(
            PATTERNS["email address"].search(stripped_real),
            "a real address that merely starts with the placeholder must "
            "survive stripping and still be reported",
        )
        stripped_placeholder = strip_known_placeholders(
            relative, f"write {placeholder} in the sample")
        self.assertIsNone(
            PATTERNS["email address"].search(stripped_placeholder),
            "the approved placeholder itself must still be stripped",
        )

    def test_connector_identifiers_are_detected_but_placeholders_are_not(self):
        pattern = PATTERNS["connector identifier"]
        guid = "3f2b8c1a-9d4e-4f7a-8b2c-1e5d9a7c3f04"
        for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "APS_CLIENT_ID"):
            with self.subTest(name=name, expect="flagged"):
                self.assertIsNotNone(pattern.search(f'{name} = "{guid}"'))
        # Azure accepts the tenant *domain* form, which is neither a GUID nor a
        # long opaque token and was therefore invisible.
        domain = "customer" + ".onmicrosoft.com"
        with self.subTest(form="tenant domain", expect="flagged"):
            self.assertIsNotNone(
                pattern.search(f'{"AZURE" + "_TENANT_ID"} = "{domain}"'))
        for probe in (f'{"AZURE" + "_TENANT_ID"} = "<your-tenant-id>"',
                      f'{"TFE" + "_ADDRESS"} = "{"https" + "://"}app.terraform.io"'):
            with self.subTest(probe=probe, expect="clean"):
                self.assertIsNone(pattern.search(probe))

    def test_intake_preamble_rejects_real_findings(self):
        """The preamble told a maintainer to pin the tripping snippet in
        PLACEHOLDER_LITERALS. For a genuine credential that makes the gate pass
        while committing the material it exists to stop. It must classify
        first, reject real findings, and treat uncertainty as real."""
        for skill in SKILLS_DIR.glob("suggest-awesome-github-copilot-*/SKILL.md"):
            text = skill.read_text(encoding="utf-8")
            with self.subTest(skill=skill.parent.name):
                self.assertIn("Classify every finding", text)
                self.assertIn("the file is **rejected**", text)
                self.assertIn("Never pin a real value", text)
                self.assertIn("Uncertain counts as real", text)

                # The classification criterion itself has to hold. "It appears
                # in upstream's public documentation" was offered as PROOF of a
                # placeholder, which lets the one case this gate exists for --
                # an accidentally published live credential -- classify itself
                # as safe, two lines after the same preamble declares upstream
                # untrusted. Proof must be a property of the value, not of
                # where it was found.
                self.assertNotIn(
                    "upstream's public documentation, is obviously fabricated",
                    text,
                    "publication is being treated as proof of synthesis")
                self.assertIn("Publication upstream is not proof", text)
                for criterion in ("RFC 2606", "RFC 5737",
                                  "structurally impossible", "revoked"):
                    with self.subTest(criterion=criterion):
                        self.assertIn(criterion, text)

    def test_placeholder_allowlist_has_no_stale_entries(self):
        for relative_path, literals in PLACEHOLDER_LITERALS.items():
            path = ROOT / relative_path
            with self.subTest(path=relative_path):
                self.assertTrue(path.is_file())
                text = path.read_text(encoding="utf-8")
                for literal in literals:
                    self.assertIn(literal, text)

    def test_dedicated_privacy_guard_scans_every_tracked_text_file(self):
        self.assertEqual(scan_repository(ROOT), [])
        scanned = set(repository_files(ROOT))
        self.assertIn(ROOT / ".env.example", scanned) if (ROOT / ".env.example").exists() else None
        self.assertIn(ROOT / "scripts" / "privacy_guard.py", scanned)

    def test_privacy_guard_fails_closed_on_binary_and_unquoted_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "client-confidential-plan.pdf").write_bytes(b"%PDF-\0private-client-data")
            token = "gh" + "o_" + ("A" * 24)
            google_key = "AI" + "za" + ("B" * 32)
            npm_token = "np" + "m_" + ("C" * 24)
            aws_secret = "D" * 40
            bearer = "E" * 32
            key_name = "API" + "_KEY"
            token_name = "ACCESS" + "_TOKEN"
            aws_name = "AWS_SECRET" + "_ACCESS_KEY"
            npm_name = "NPM" + "_TOKEN"
            auth_name = "Authori" + "zation"
            (root / "runtime.conf").write_text(
                key_name
                + "="
                + google_key
                + "\n"
                + token_name
                + "="
                + token
                + "\n"
                + aws_name
                + "="
                + aws_secret
                + "\n"
                + npm_name
                + "="
                + npm_token
                + "\n"
                + auth_name
                + ": Bearer "
                + bearer
                + "\n",
                encoding="utf-8",
            )
            lfs_prefix = "version https://git-lfs.github.com/" + "spec/v1"
            (root / "private-artifact.dat").write_text(
                lfs_prefix + "\noid sha256:" + ("f" * 64) + "\nsize 123456\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        self.assertTrue(any("binary file is not allowed" in finding for finding in findings))
        self.assertTrue(any("secret token" in finding for finding in findings))
        self.assertTrue(any("credential assignment" in finding for finding in findings))
        self.assertTrue(any("bearer credential" in finding for finding in findings))
        self.assertTrue(any("Git LFS pointer" in finding for finding in findings))

    def test_private_runtime_and_secret_filenames_are_not_present(self):
        prohibited_names = {
            ".env",
            "credentials.json",
            "service-account.json",
            "secrets.json",
            "token.json",
            "memory.db",
            "memory.sqlite",
            "memory.sqlite3",
        }
        gitlinks = gitlink_paths(ROOT)
        for path in ROOT.rglob("*"):
            if (
                path.is_file()
                and not {".git", "node_modules"} & set(path.parts)
                and not is_vendored(path, ROOT, gitlinks)
            ):
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertNotIn(path.name.lower(), prohibited_names)

    def test_gitignore_blocks_common_private_runtime_artifacts(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in [
            ".env",
            "*.pem",
            "*.key",
            "runtime-memory/",
            "private-memory/",
            "credentials/",
            "*.sqlite",
            "*.db",
            "brains/apex/memory/*",
            "brains/jeos/memory/*",
        ]:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)

    def test_public_repository_policy_is_referenced_by_both_brains(self):
        apex = (ROOT / "brains" / "apex" / "README.md").read_text(encoding="utf-8")
        jeos = (ROOT / "brains" / "jeos" / "README.md").read_text(encoding="utf-8")
        self.assertIn("repository is public", apex)
        self.assertIn("repository is public", jeos)
        self.assertIn(
            "Private runtime memory",
            (ROOT / "docs" / "PRIVACY_AND_DATA_BOUNDARIES.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
