from pathlib import Path
import re
import tempfile
import unittest

from scripts.privacy_guard import (
    PATTERNS,
    scan_paths,
    PLACEHOLDER_LITERALS,
    applicable_patterns,
    repository_files,
    scan_repository,
    strip_known_placeholders,
)


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".github" / "skills"


class PublicRepositoryPrivacyTests(unittest.TestCase):
    def test_tracked_text_has_no_obvious_private_or_secret_material(self):
        excluded_parts = {"__pycache__", ".git", "node_modules"}
        text_paths = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and not any(part in excluded_parts for part in path.parts)
            and path.suffix.lower() in {".md", ".toml", ".json", ".py", ".yml", ".yaml"}
        ]
        prohibited = {
            "secret key": re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b"),
            "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            "cloud access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
            "generic credential assignment": re.compile(
                r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']"
            ),
            "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
            "phone number": re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
            "raw Drive or Docs link": re.compile(r"https://(?:drive|docs)\.google\.com/", re.IGNORECASE),
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
            expected = sum(
                len(lit) * original.count(lit) for lit in literals
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
        pattern = re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
            r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token"
            r"|tfe?[_-]?token|terraform[_-]?token"
            r"|gh[_-]?token|github[_-]?token|github[_-]?personal[_-]?access[_-]?token"
            r"|azure[_-]?client[_-]?secret|aps[_-]?client[_-]?secret)"
            r"\s*[:=]\s*(?:[\"'][^\"']{8,}[\"']|[^\s#\"']{8,})"
        )
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
            (root / "client-confidential-plan.pdf").write_bytes(
                b"%PDF-\0private-client-data"
            )
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
        self.assertTrue(
            any("binary file is not allowed" in finding for finding in findings)
        )
        self.assertTrue(
            any("secret token" in finding for finding in findings)
        )
        self.assertTrue(
            any("credential assignment" in finding for finding in findings)
        )
        self.assertTrue(
            any("bearer credential" in finding for finding in findings)
        )
        self.assertTrue(
            any("Git LFS pointer" in finding for finding in findings)
        )

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
        for path in ROOT.rglob("*"):
            if path.is_file() and not {".git", "node_modules"} & set(path.parts):
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
        self.assertIn("Private runtime memory", (ROOT / "docs" / "PRIVACY_AND_DATA_BOUNDARIES.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
