"""Runtime-stack verification tests.

These tests always validate the stdlib-reachable contracts (script syntax,
tier manifest consistency with the requirements files). Checks that need the
installed runtime stack skip cleanly when a package is absent so the stdlib
CI environment stays green.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class RuntimeStackTests(unittest.TestCase):
    def test_verify_script_runs_and_reports_valid(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_runtime_stack.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["valid"])
        self.assertGreater(report["toml_files_checked"], 0)

    def test_requirements_files_cover_the_declared_tiers(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import verify_runtime_stack
        finally:
            sys.path.pop(0)
        for tier, packages in verify_runtime_stack.RUNTIME_STACK.items():
            requirements = ROOT / "requirements" / f"runtime-{tier}.txt"
            self.assertTrue(requirements.exists(), f"missing {requirements}")
            # Split on every PEP 508 separator, not just `==` and `>=`. Each
            # manifest entry was bare until `mcp<2` was added, so an entry
            # carrying any other specifier read as a package literally named
            # "mcp<2" and the tier it covers looked undeclared. The comparison
            # is about which distribution is listed, never its version range.
            declared = {
                re.split(r"[<>=!~;\[]", line.split("#", 1)[0], maxsplit=1)[0].strip().lower()
                for line in requirements.read_text(encoding="utf-8").splitlines()
                if line.split("#", 1)[0].strip()
            }
            for _module, dist in packages:
                self.assertIn(dist.lower(), declared, f"{dist} not declared for tier {tier}")

    def test_toml_exclusions_match_relative_paths_not_absolute_ones(self) -> None:
        """A checkout sitting under a node_modules/.git directory still gets checked.

        The dependency-directory exclusion must be applied to the
        repository-relative path. Testing the absolute path would skip every
        file in such a checkout, reporting `valid` with nothing checked.
        """
        import shutil
        import tempfile

        if shutil.which("git") is None:
            self.skipTest("no git binary; this fixture builds a real checkout")

        sys.path.insert(0, str(ROOT))
        try:
            from scripts import verify_runtime_stack
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            # The repository root itself lives under a "node_modules" segment.
            nested = Path(directory) / "node_modules" / "checkout"
            nested.mkdir(parents=True)
            (nested / "pyproject.toml").write_text('[tool.x]\nk = "v"\n', encoding="utf-8")
            (nested / "node_modules").mkdir()
            (nested / "node_modules" / "dep.toml").write_text(
                "this is not valid toml\n", encoding="utf-8"
            )

            # A real index, because the exclusion is now defined against one:
            # installed dependency content is what is untracked, and with no
            # index at all every file is validated instead. A bare temp
            # directory would exercise that fallback rather than this rule.
            def run(*args: str) -> None:
                subprocess.run(args, cwd=nested, check=True, capture_output=True)

            run("git", "init", "-q", ".")
            run("git", "config", "user.email", "runtime-stack-fixture")
            run("git", "config", "user.name", "runtime-stack-fixture")
            run("git", "add", "pyproject.toml")
            run("git", "commit", "-qm", "fixture")

            original = verify_runtime_stack.ROOT
            verify_runtime_stack.ROOT = nested
            try:
                checked, errors = verify_runtime_stack.enforce_toml()
            finally:
                verify_runtime_stack.ROOT = original

        self.assertEqual(errors, [])
        self.assertEqual(len(checked), 1, f"expected only the root manifest, got {checked}")
        self.assertIn("pyproject.toml", checked[0])

    @unittest.skipUnless(_module_available("jsonschema"), "jsonschema not installed")
    def test_jsonschema_enforces_every_schema_and_fixture(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import verify_runtime_stack
        finally:
            sys.path.pop(0)
        checked, errors = verify_runtime_stack.enforce_schemas()
        self.assertEqual(errors, [])
        self.assertEqual(len(checked), len(list((ROOT / "schemas").glob("*.schema.json"))))

    @unittest.skipUnless(_module_available("pydantic"), "pydantic not installed")
    def test_pydantic_rejects_malformed_handoff_packet(self) -> None:
        import pydantic

        class HandoffEnvelope(pydantic.BaseModel):
            model_config = pydantic.ConfigDict(extra="forbid")
            packet_contract_version: str
            from_agent: str
            to_agent: str

        with self.assertRaises(pydantic.ValidationError):
            HandoffEnvelope.model_validate({"packet_contract_version": "2.1"})


if __name__ == "__main__":
    unittest.main()
