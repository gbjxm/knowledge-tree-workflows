from __future__ import annotations
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock
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

class InstalledConsistencyTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_fixture()
        self.target = self.scratch / "安装 副本"
        release.install_modules(self.root, self.target, None, True)

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                for base in (self.root / "skills", self.target)
                for p in base.rglob("*") if p.is_file()}

    def test_matching_is_read_only(self):
        before = self.snapshot()
        result = release.verify_installed(self.root, self.target)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(len(result["selected"]), 8)
        self.assertFalse(result["writes"])
        self.assertEqual(before, self.snapshot())

    def test_missing_changed_and_extra_are_separate_and_preserved(self):
        (self.target / "bilibili-study-notes/SKILL.md").unlink()
        changed = self.target / "grow-creative-library/SKILL.md"
        changed.write_text("local edit", encoding="utf-8")
        extra = self.target / "apply-film-knowledge/local-custom.md"
        extra.write_text("keep until reviewed", encoding="utf-8")
        before = self.snapshot()
        result = release.verify_installed(self.root, self.target)
        rows = {r["module"]: r for r in result["modules"]}
        self.assertEqual(rows["bilibili-study-notes"]["missing"], ["SKILL.md"])
        self.assertEqual(rows["grow-creative-library"]["changed"], ["SKILL.md"])
        self.assertEqual(rows["apply-film-knowledge"]["extra"], ["local-custom.md"])
        self.assertEqual(result["status"], "differences")
        self.assertEqual(before, self.snapshot())

    def test_missing_target_is_reported_without_creation(self):
        absent = self.scratch / "not-created/skills"
        result = release.verify_installed(self.root, absent)
        self.assertFalse(result["ok"])
        self.assertFalse(result["target_exists"])
        self.assertTrue(all(r["missing"] for r in result["modules"]))
        self.assertFalse(absent.parent.exists())

    def test_partial_selection_reads_only_selected_file_content(self):
        selected = "grow-creative-library"
        original = release.sha256
        def guard(path):
            self.assertIn(selected, path.parts)
            return original(path)
        with mock.patch.object(release, "sha256", side_effect=guard):
            result = release.verify_installed(self.root, self.target, [selected])
        self.assertEqual(result["selected"], [selected])
        self.assertTrue(result["ok"])
        (self.target / "apply-film-knowledge/SKILL.md").unlink()
        with mock.patch.object(release, "sha256", side_effect=guard):
            result = release.verify_installed(self.root, self.target, [selected])
        self.assertFalse(result["ok"])
        self.assertTrue(any("apply-film-knowledge" in e for e in result["dependency_errors"]))
        self.assertEqual(result["modules"][0]["changed"], [])

    def test_ignored_files_preview_and_unrelated_skills_are_not_opened(self):
        cache = self.target / "grow-creative-library/__pycache__"
        cache.mkdir()
        (cache / "cache.pyc").write_bytes(b"cache")
        (self.target / "grow-creative-library/debug.log").write_bytes(b"log")
        (self.target / "grow-creative-library/auth.json").write_bytes(b"credential-placeholder")
        for module in ("generate-film-breakdown-report", "unrelated-skill"):
            folder = self.target / module
            folder.mkdir()
            (folder / "SKILL.md").write_bytes(b"do not inspect")
        original = release.sha256
        def guard(path):
            self.assertNotIn(path.suffix, {".log", ".pyc"})
            self.assertNotEqual(path.name, "auth.json")
            self.assertNotIn("generate-film-breakdown-report", path.parts)
            self.assertNotIn("unrelated-skill", path.parts)
            return original(path)
        with mock.patch.object(release, "sha256", side_effect=guard):
            result = release.verify_installed(self.root, self.target)
        self.assertTrue(result["ok"])
        self.assertEqual(result["ignored_entries"], 3)

    def test_installed_code_is_not_executed(self):
        loader = self.target / "operate-personal-knowledge-tree/scripts/knowledge_tree_config.py"
        loader.write_text("raise AssertionError('target code executed')", encoding="utf-8")
        result = release.verify_installed(self.root, self.target)
        row = next(r for r in result["modules"] if r["module"] == "operate-personal-knowledge-tree")
        self.assertEqual(row["changed"], ["scripts/knowledge_tree_config.py"])

    def test_invalid_selection_cannot_expand_to_all(self):
        before = self.snapshot()
        for names in ([], [""], ["missing"], ["../grow-creative-library"],
                      ["grow-creative-library", "grow-creative-library"],
                      ["generate-film-breakdown-report"]):
            with self.subTest(names=names):
                with self.assertRaises(release.ReleaseError):
                    release.verify_installed(self.root, self.target, names)
        self.assertEqual(before, self.snapshot())

    def test_overlap_and_missing_canonical_entry_fail(self):
        for target in (self.root, self.root / "skills", self.root / "skills/child"):
            with self.assertRaises(release.ReleaseError):
                release.verify_installed(self.root, target)
        (self.root / "skills/grow-creative-library/SKILL.md").unlink()
        with self.assertRaises(release.ReleaseError):
            release.verify_installed(self.root, self.target)

    def test_target_resolution_matches_existing_install_precedence(self):
        profile = self.scratch / "profile"
        profile.mkdir()
        (profile / ".codex").mkdir()
        home = self.scratch / "codex-home"
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(home), "USERPROFILE": str(profile)}, clear=True):
            self.assertEqual(release.installed_target(self.target), self.target)
            self.assertEqual(release.installed_target(None), home / "skills")
        with mock.patch.dict(os.environ, {"USERPROFILE": str(profile)}, clear=True):
            self.assertEqual(release.installed_target(None), profile / ".codex/skills")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(release.ReleaseError):
                release.installed_target(None)
        self.assertFalse(home.exists())

    @unittest.skipUnless(os.name == "nt", "Windows directory junctions")
    def test_target_root_ancestor_nested_and_declared_source_links_fail(self):
        def junction(link, target):
            process = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                     capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        alias = self.scratch / "alias"
        junction(alias, self.target)
        with self.assertRaises(release.ReleaseError):
            release.verify_installed(self.root, alias)
        with self.assertRaises(release.ReleaseError):
            release.verify_installed(self.root, alias / "not-yet-existing")
        nested = self.target / "grow-creative-library/linked"
        junction(nested, self.root / "docs")
        with self.assertRaises(release.ReleaseError):
            release.verify_installed(self.root, self.target)
        os.rmdir(nested)
        source_alias = self.root / "skills-alias"
        junction(source_alias, self.root / "skills")
        config = self.root / ".codex/knowledge-tree.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data["skills_root"] = "skills-alias"
        config.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(release.ReleaseError):
            release.verify_installed(self.root, self.target)

    def test_daily_and_relocated_release_do_not_require_installed_comparison(self):
        with mock.patch.object(release, "verify_installed", side_effect=AssertionError("unexpected install check")):
            self.assertTrue(release.daily_check(self.root, skip_audits=True)["ok"])
            relocated = self.make_and_extract()
            self.assertTrue(release.verify_release(relocated, relocated / release.PACKAGE_MANIFEST)["ok"])

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
    def test_powershell_entry_preserves_three_exit_codes_and_scope(self):
        script = self.root / "scripts/verify.ps1"
        def invoke(extra=(), target=None):
            return subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(script), "-Mode", "Installed", "-TargetSkillsRoot",
                 str(target or self.target), *extra],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
        okay = invoke()
        self.assertEqual(okay.returncode, 0, okay.stderr)
        self.assertEqual(json.loads(okay.stdout)["status"], "consistent")
        custom = self.target / "grow-creative-library/custom.md"
        custom.write_text("keep", encoding="utf-8")
        different = invoke()
        self.assertEqual(different.returncode, 1, different.stderr)
        self.assertEqual(json.loads(different.stdout)["status"], "differences")
        failed = invoke(("-SkillNames", "not-a-module"))
        self.assertEqual(failed.returncode, 2, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["status"], "check_failed")
        partial = invoke(("-SkillNames", "bilibili-study-notes"))
        self.assertEqual(partial.returncode, 0, partial.stderr)
        self.assertEqual(json.loads(partial.stdout)["selected"], ["bilibili-study-notes"])
        absent = self.scratch / "missing-target"
        missing = invoke(target=absent)
        self.assertEqual(missing.returncode, 1, missing.stderr)
        self.assertFalse(absent.exists())
        for invalid in (("-Manifest", "not-used"), ("-SkipAudits",)):
            invalid_result = invoke(invalid)
            self.assertEqual(invalid_result.returncode, 2)
        self.assertEqual(custom.read_text(), "keep")

    @unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell required")
    def test_powershell_empty_array_is_not_default_all(self):
        script = self.root / "scripts/verify.ps1"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
             f"& {ps_literal(script)} -Mode Installed -TargetSkillsRoot {ps_literal(self.target)} -SkillNames @(); exit $LASTEXITCODE"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "check_failed")


if __name__ == "__main__":
    unittest.main()
