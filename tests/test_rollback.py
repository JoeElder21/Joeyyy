from pathlib import Path
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
RETIRED_NATIVE_FILES = {
    ".codex/agents/apex_grademaster.toml",
    ".codex/agents/apex_countwise.toml",
    ".codex/agents/apex_signalkeeper.toml",
    ".codex/agents/apex_ascent_90.toml",
    ".codex/agents/apex_forgewright.toml",
    ".codex/agents/jeos_examiner.toml",
    ".codex/agents/jeos_tempo.toml",
    ".codex/agents/jeos_shepherd.toml",
    ".codex/agents/jeos_hearthkeeper.toml",
    ".codex/agents/jeos_lifewright.toml",
}


class RollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "config" / "specialist_corps.toml").open("rb") as source:
            cls.manifest = tomllib.load(source)
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        cls.has_git_history = probe.returncode == 0 and probe.stdout.strip() == "true"

    def test_rollback_sha_is_full_and_pinned(self):
        rollback = self.manifest["rollback_parent"]
        self.assertRegex(rollback, r"^[0-9a-f]{40}$")
        for entry in self.manifest["retired"].values():
            self.assertEqual(entry["rollback_commit"], rollback)

    def test_rollback_commit_contains_retired_native_files_when_history_is_available(self):
        if not self.has_git_history:
            self.skipTest("local artifact has no Git history; CI checkout validates this gate")
        rollback = self.manifest["rollback_parent"]
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", rollback],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        prior_paths = set(result.stdout.splitlines())
        self.assertTrue(RETIRED_NATIVE_FILES.issubset(prior_paths))
        current_paths = {
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file()
        }
        self.assertTrue(RETIRED_NATIVE_FILES.isdisjoint(current_paths))


if __name__ == "__main__":
    unittest.main()
