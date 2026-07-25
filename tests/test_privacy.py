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
# Phone is deliberately absent: it stays armed everywhere. Email and street matches
# are re-checked by value below rather than waived by path.
CONTACT_HEURISTIC_CHECKS = {
    "email address",
    "street address",
}
RESERVED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "example.edu",
    "example",
    "test",
    "invalid",
    "localhost",
    "local",
    # domain.com / email.com / mail.com / acme.com / yourcompany.com are deliberately
    # absent: they read as filler but are live registered domains.
}
RESERVED_EMAIL_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
# Whole addresses, not words. A word-level allowlist waives any real address that
# happens to contain a common street word.
FIXTURE_STREET_ADDRESSES = frozenset(
    f"{number} {name} {suffix}"
    for number, name in (("123", "main"), ("456", "oak"), ("1", "example"), ("1", "test"))
    for suffix in ("st", "street", "ave", "avenue")
)


def unreserved_contacts(text: str, prohibited: dict) -> list[str]:
    """Email and street matches that are not recognized reserved examples."""
    found = []
    for match in prohibited["email address"].finditer(text):
        domain = match.group(0).rsplit("@", 1)[-1].lower()
        if domain not in RESERVED_EMAIL_DOMAINS and not domain.endswith(
            RESERVED_EMAIL_SUFFIXES
        ):
            found.append(match.group(0))
    for match in prohibited["street address"].finditer(text):
        normalized = " ".join(match.group(0).split()).strip(".,").lower()
        if normalized not in FIXTURE_STREET_ADDRESSES:
            found.append(match.group(0))
    return found
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
# Unquoted .env / shell form. An unquoted value only looks like a credential when it
# is one opaque run of word characters; anything with a dot, bracket, paren or comma
# is code rather than a secret.
CREDENTIAL_BARE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password"
    r"|aws[_-]?secret[_-]?access[_-]?key|npm[_-]?token)"
    r"\s*[:=]\s*([^\s#\"']{8,})"
)
# Detect code expressions rather than allowlisting secret characters: base64 and
# URL-safe keys contain +, /, = and ., so a word-character allowlist fails open.
# A CLOSED allowlist of the exact unquoted expressions present in the vendored tree.
# Restated here rather than imported, like the rest of this mirror. Every structural
# heuristic tried previously leaked: a dot waived JWTs, identifier shape waived
# alphanumeric keys, a bracket waived punctuated passwords. What a secret can look like
# is open-ended; what appears here is not.
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


def is_vendored_documentation(relative: Path) -> bool:
    return any(
        prefix == relative or prefix in relative.parents
        for prefix in DOCUMENTATION_ONLY_PREFIXES
    )


PLACEHOLDER_MAX_LENGTH = 20


def _is_filler(value: str) -> bool:
    return len(value) <= PLACEHOLDER_MAX_LENGTH and any(
        p.match(value) for p in PLACEHOLDER_VALUE_PATTERNS
    )


def _bare_value_is_credential(raw: str) -> bool:
    value = raw.rstrip(",;")
    return value not in VENDORED_BARE_EXPRESSIONS and not _is_filler(value)


def non_placeholder_credentials(text: str) -> list[str]:
    found = [m.group(1) for m in CREDENTIAL_LITERAL.finditer(text) if not _is_filler(m.group(1))]
    found += [
        m.group(1)
        for m in CREDENTIAL_BARE.finditer(text)
        if _bare_value_is_credential(m.group(1))
    ]
    return found


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
                    # Not waived — only RFC-reserved examples and fixture addresses
                    # are tolerated, so real contact data still fails.
                    with self.subTest(path=relative, check="vendored contact value"):
                        self.assertEqual(unreserved_contacts(text, prohibited), [])
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
                # Base64 / URL-safe shapes: punctuation must not buy an exemption.
                "QWxhZGRpbjpvcGVuIHNlc2FtZQ==",
                "ab+cd/ef1234567890=",
                # Split so this file stays clean under the guard's own token pattern.
                "sk" + "_test_but_actually_live-9931-REALKEY",
            ]
            # Both the quoted form and the unquoted .env/shell form must be caught.
            for index, value in enumerate(live_values):
                for form, body in (
                    ("quoted", f'{key_name}="{value}"\n'),
                    ("bare", f"{key_name}={value}\n"),
                ):
                    leak = vendored / f"generic{index}.md"
                    leak.write_text(body, encoding="utf-8")
                    findings = scan_repository(root)
                    self.assertTrue(
                        any(
                            leak.name in f and "credential assignment" in f
                            for f in findings
                        ),
                        f"{form} {value!r} was not reported: {findings}",
                    )
                    leak.unlink()

            # Real contact data under the vendored prefix must still be reported;
            # the exemption covers reserved examples only, not the path.
            for index, contact in enumerate(
                [
                    "Contact " + "employee@" + "realcompany.com",
                    "Reach " + "j.doe@" + "clientfirm.co.uk",
                    "Office at 3300 Lakeside" + " Drive",
                ]
            ):
                doc = vendored / f"contact{index}.md"
                doc.write_text(contact + "\n", encoding="utf-8")
                findings = scan_repository(root)
                self.assertTrue(findings, f"{contact!r} was not reported")
                doc.unlink()

            # Reserved examples and fixture addresses stay quiet.
            for benign in [
                "Contact " + "test@" + "example.com",
                "Write to " + "admin@" + "example.org",
                "123 Main" + " St",
                "456 Oak" + " Ave",
            ]:
                doc = vendored / "benign.md"
                doc.write_text(benign + "\n", encoding="utf-8")
                findings = scan_repository(root)
                self.assertEqual(findings, [], f"{benign!r} is a reserved example")
                doc.unlink()

            # Unquoted expressions are code, not secrets, and must stay quiet.
            for expression in [
                "var.database_password",
                "self.jwt_manager.create_access_token(user)",
                "request.META.get('HTTP_X_API_KEY')",
                "Annotated[str,",
            ]:
                doc = vendored / "expr.md"
                doc.write_text(f"{key_name} = {expression}\n", encoding="utf-8")
                findings = scan_repository(root)
                self.assertEqual(findings, [], f"{expression!r} is code, not a secret")
                doc.unlink()

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
