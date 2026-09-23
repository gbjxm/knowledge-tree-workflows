from __future__ import annotations
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from test_release import ReleaseFixture
import release_core as release

def ps_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"

@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
class SelectiveInstallTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_fixture()
        self.target = self.scratch / "target"
        self.script = self.root / "scripts/install-skills.ps1"

    def invoke(self, arguments=""):
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                   KNOWLEDGE_TREE_CONFIG=str(self.root / ".codex/knowledge-tree.json"))
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
             f"& {ps_literal(self.script)} -TargetSkillsRoot {ps_literal(self.target)} {arguments}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)

    def test_default_is_eight_stable_preview_only(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["count"], 8)
        self.assertFalse(report["apply"])
        self.assertFalse(self.target.exists())

    def test_exact_selection_apply_with_dependencies(self):
        release.install_modules(self.root, self.target, None, True)
        old_preview = self.target / "generate-film-breakdown-report" / "SKILL.md"
        old_preview.parent.mkdir()
        old_preview.write_text("existing user preview", encoding="utf-8")
        result = self.invoke("-SkillNames @('grow-creative-library','bilibili-study-notes') -Apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["selected"], ["grow-creative-library", "bilibili-study-notes"])
        self.assertEqual(len(list(self.target.iterdir())), 9)
        self.assertEqual(old_preview.read_text(encoding="utf-8"), "existing user preview")

    def test_empty_unknown_duplicate_or_preview_apply_cannot_fall_back_to_all(self):
        for selection in ("@()", "@('')", "@('not-a-skill')", "@('../grow-creative-library')",
                          "@('grow-creative-library','grow-creative-library')",
                          "@('generate-film-breakdown-report')"):
            with self.subTest(selection=selection):
                result = self.invoke(f"-SkillNames {selection} -Apply")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.target.exists())

    def test_release_cannot_skip_security_audits(self):
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                 str(self.root / "scripts/verify.ps1"), "-Mode", "Release", "-SkipAudits"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Daily", result.stderr)

if __name__ == "__main__":
    unittest.main()
