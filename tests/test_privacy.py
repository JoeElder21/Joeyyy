from pathlib import Path
import re
import tempfile
import unittest

from scripts.privacy_guard import repository_files, scan_repository


ROOT = Path(__file__).resolve().parents[1]
# Vendored third-party documentation. Mirrors DOCUMENTATION_ONLY_PREFIXES in
# scripts/privacy_guard.py. Restated here rather than imported so that loosening the
# guard cannot silently loosen this test too. Only the heuristic patterns below are
# skipped for these paths; credential-shaped patterns stay armed everywhere and are
# asserted by test_vendored_documentation_exemption_is_narrow.
DOCUMENTATION_ONLY_PREFIXES = (Path(".claude/agents/awesome-claude-agents"),)
# Contact and location heuristics only. Credential assignment is NOT waived by path:
# it is re-checked by value below, so a real secret under a vendored prefix still
# fails. Keep that distinction when editing.
CONTACT_HEURISTIC_CHECKS = {
    "email address",
    "phone number",
    "street address",
}
# Complete placeholder forms, matched against the WHOLE literal. A substring test
# would waive any live credential containing a common word; keep these anchored.
PLACEHOLDER_VALUE_PATTERNS = (
    re.compile(
        r"\A(?i:test|example|sample|dummy|fake|placeholder|redacted|changeme"
        r"|change[-_]me|foo|bar|baz|x{3,})[a-z0-9]*(?:[-_][a-z0-9]+)?\Z"
    ),
    re.compile(r"(?i)\A(?:pass)?word\Z|\A(?:secret|token|credential)s?\Z"),
    re.compile(r"(?i)\A(?:sk|pk|rk)_test_[a-z0-9]+\Z"),
    re.compile(r"\A<[^>]+>\Z"),
    re.compile(r"\A\{\{[^}]+\}\}\Z"),
    re.compile(r"(?i)\A\$\{?[a-z_][a-z0-9_]*\}?\Z"),
    re.compile(
        r"(?i)\A(?:your|my|the)[-_]"
        r"(?:api[-_]?key|access[-_]?token|token|secret|password|credential|key|value)s?\Z"
    ),
)
CREDENTIAL_LITERAL = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
    r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token)"
    r"\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)


def is_vendored_documentation(relative: Path) -> bool:
    return any(
        prefix == relative or prefix in relative.parents
        for prefix in DOCUMENTATION_ONLY_PREFIXES
    )


PLACEHOLDER_MAX_LENGTH = 20


def non_placeholder_credentials(text: str) -> list[str]:
    return [
        match.group(1)
        for match in CREDENTIAL_LITERAL.finditer(text)
        if len(match.group(1)) > PLACEHOLDER_MAX_LENGTH
        or not any(p.match(match.group(1)) for p in PLACEHOLDER_VALUE_PATTERNS)
    ]


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
            relative = path.relative_to(ROOT)
            vendored = is_vendored_documentation(relative)
            text = path.read_text(encoding="utf-8")
            for label, pattern in prohibited.items():
                if vendored and label in CONTACT_HEURISTIC_CHECKS:
                    continue
                if vendored and label == "generic credential assignment":
                    # Not waived — re-checked by value, so live secrets still fail.
                    with self.subTest(path=relative, check="vendored credential value"):
                        self.assertEqual(non_placeholder_credentials(text), [])
                    continue
                with self.subTest(path=relative, check=label):
                    self.assertIsNone(pattern.search(text))

    def test_vendored_documentation_exemption_is_narrow(self):
        """The vendored-docs exemption must not disarm credential-shaped patterns."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vendored = root / ".claude" / "agents" / "awesome-claude-agents"
            vendored.mkdir(parents=True)
            # Heuristic matches here are documentation noise and must be tolerated.
            # Literals are split so this test file itself stays clean under the guard.
            sample_email = "test@" + "example.com"
            sample_street = "123 Main" + " St"
            sample_password = "pass" + "word=" + "placeholder-value"
            (vendored / "agent.md").write_text(
                "Contact " + sample_email + " at " + sample_street + "\n"
                + sample_password + "\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
            self.assertEqual(findings, [], findings)

            # A provider-specific token in the same tree must still be caught.
            token = "gh" + "o_" + ("A" * 24)
            (vendored / "leak.md").write_text(token + "\n", encoding="utf-8")
            findings = scan_repository(root)
            self.assertTrue(
                any("leak.md" in f and "secret token" in f for f in findings), findings
            )
            (vendored / "leak.md").unlink()

            # A provider-agnostic credential must also be caught, even though the
            # generic detector is relaxed for placeholder literals in this tree.
            # Each of these embeds a word that appears in the placeholder forms;
            # none is a complete placeholder, so all must still be reported.
            key_name = "api" + "_key"
            live_values = [
                "live-production-key-4938291",
                "my-secret-live-prod-4938291",
                "prod-password-rotate-2026",
                "attacker-test-key-99331",
                # Begins with a dummy word but carries a live-looking tail.
                "testing-servers-real-key-771",
                "Example-Corp-LIVE-KEY-88213",
                # Split so this file stays clean under the guard's own token pattern.
                "sk" + "_test_but_actually_live-9931-REALKEY",
            ]
            for index, value in enumerate(live_values):
                leak = vendored / f"generic{index}.md"
                leak.write_text(f'{key_name}="{value}"\n', encoding="utf-8")
                findings = scan_repository(root)
                self.assertTrue(
                    any(leak.name in f and "credential assignment" in f for f in findings),
                    f"{value!r} was not reported: {findings}",
                )
                leak.unlink()

            # Complete placeholder forms must still pass.
            for value in ["testpass123", "password", "sk_test_123", "your-api-key"]:
                doc = vendored / "ph.md"
                doc.write_text(f'{key_name}="{value}"\n', encoding="utf-8")
                findings = scan_repository(root)
                self.assertEqual(findings, [], f"{value!r} should be treated as filler")
                doc.unlink()
            findings = scan_repository(root)
        self.assertEqual(findings, [], findings)

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
