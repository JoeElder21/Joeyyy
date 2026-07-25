from pathlib import Path
import re
import tempfile
import unittest

from scripts.privacy_guard import (
    PLACEHOLDER_LITERALS,
    VENDORED_DOC_RELAXATIONS,
    applicable_patterns,
    repository_files,
    scan_repository,
    strip_known_placeholders,
)


ROOT = Path(__file__).resolve().parents[1]

# This module's `prohibited` labels differ from privacy_guard.PATTERNS labels;
# map ours onto theirs so the two relaxation sets cannot drift apart.
LABEL_ALIASES = {
    "generic credential assignment": "credential assignment",
    "email address": "email address",
}


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
            relaxed = VENDORED_DOC_RELAXATIONS.get(relative_path, frozenset())
            for label, pattern in prohibited.items():
                if LABEL_ALIASES.get(label) in relaxed:
                    continue
                with self.subTest(path=relative_path, check=label):
                    self.assertIsNone(pattern.search(text))

    def test_unlisted_instruction_file_gets_the_full_pattern_set(self):
        """Regression: a directory-wide exemption once let any file under
        .github/instructions/ bypass the email and credential heuristics, so a
        hand-authored or newly discovered file could publish real data
        silently. Relaxations are pinned per file; an unlisted one is scanned
        in full."""
        unlisted = Path(".github/instructions/local.instructions.md")
        self.assertNotIn(unlisted, VENDORED_DOC_RELAXATIONS)
        self.assertEqual(
            set(applicable_patterns(unlisted)),
            set(applicable_patterns(Path("scripts/anything.py"))),
        )

    def test_relaxations_are_narrow_and_per_pattern(self):
        """Each relaxed file gives up only the one pattern it needs, and only
        low-confidence prose heuristics are ever relaxed."""
        allowed_to_relax = {"credential assignment", "email address"}
        for path, relaxed in VENDORED_DOC_RELAXATIONS.items():
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertTrue(relaxed)
                self.assertLessEqual(len(relaxed), 1)
                self.assertTrue(relaxed <= allowed_to_relax)
                remaining = set(applicable_patterns(path))
                for high_confidence in (
                    "secret token", "cloud access key", "private key",
                    "phone number", "street address", "raw Drive or Docs link",
                ):
                    self.assertIn(high_confidence, remaining)

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
