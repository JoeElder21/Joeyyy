import os
import re
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
        # Genuinely malformed YAML (unbalanced flow) must fall through, not raise.
        self.assertEqual(yaml_reconstructed_values("{a: [1, 2}\n"), "")
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
            **({} if _yaml is None else {
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

        import scripts.privacy_guard as guard

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
            if not gated and "_yaml is None" not in body:
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
                with mock.patch.object(guard, "yaml_reconstructed_values",
                                       lambda text: ""):
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
