from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import release_core as release
from portable_manifest import create_manifest, verify_manifest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

class ReleaseFixture:
    def create_fixture(self):
        configured_cache = release.target_config(PACKAGE_ROOT).raw_cache
        fixture_parent = release.bounded_path(
            PACKAGE_ROOT, configured_cache.relative_to(PACKAGE_ROOT).as_posix() + "/release-tests", exists=False
        )
        fixture_parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="knowledge-tree-release-test-", dir=fixture_parent)
        self.addCleanup(self.temp.cleanup)
        self.scratch = Path(self.temp.name)
        self.root = self.scratch / "tree"
        self.root.mkdir()
        self.modules = release.load_modules(PACKAGE_ROOT / release.MODULE_MANIFEST)
        for name in self.modules["include"]["files"]:
            source = PACKAGE_ROOT / name
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file():
                shutil.copyfile(source, target)
            else:
                target.write_text("# fixture\n", encoding="utf-8")
        self.config = {
            "version": 2, "workspace": "..", "vault": "Vault", "vault_name": "Fixture",
            "knowledge_library": "Vault/Library", "source_notes": "Vault/Sources",
            "raw_cache": ".runtime/raw-cache", "prompt_box": "Vault/prompts.md",
            "obsidian_cli": None, "skills_root": "skills", "source_evidence": "evidence/sources",
        }
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        for folder in ("Vault/.obsidian", "Vault/Library", "Vault/Sources", ".runtime/raw-cache",
                       "evidence/sources", "docs"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / "Vault/prompts.md").write_text("# Prompts\n", encoding="utf-8")
        (self.root / "Vault/film-preview-content.md").write_text("# Existing user film content\n", encoding="utf-8")
        for number in range(205):
            (self.root / f"Vault/Sources/note-{number:03}.md").write_text(f"# Source {number}\n", encoding="utf-8")
        (self.root / "docs/readme.md").write_text("# Guide\n", encoding="utf-8")
        for module in self.modules["modules"]:
            folder = self.root / "skills" / module["name"]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "SKILL.md").write_text(f"---\nname: {module['name']}\ndescription: Fixture workflow.\n---\n", encoding="utf-8")
        loader = Path("skills/operate-personal-knowledge-tree/scripts/knowledge_tree_config.py")
        (self.root / loader).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE_ROOT / loader, self.root / loader)
        # Record an initial historical snapshot before a legitimate additional note.
        baseline = self.root / "manifest/vault-before-migration.json"
        rows = [{"path": p.relative_to(self.root / "Vault").as_posix(), "size": p.stat().st_size,
                 "sha256": release.sha256(p)} for p in (self.root / "Vault").rglob("*") if p.is_file()]
        write_json(baseline, {"version": 1, "files": rows})
        (self.root / "Vault/Sources/later.md").write_text("# Legitimate later note\n", encoding="utf-8")
        self.zip_path = self.scratch / "portable.zip"

    def make_and_extract(self):
        result = release.make_package(self.root, self.zip_path, None, False)
        self.assertTrue(result["extracted_verified"])
        destination = self.scratch / "new-drive"
        with zipfile.ZipFile(self.zip_path) as archive:
            archive.extractall(destination)
        return destination / self.root.name

class ReleaseTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_fixture()

    def test_zone_configuration_serializes_and_survives_portable_release(self):
        baseline = self.root / "manifest/vault-before-migration.json"
        before = baseline.read_bytes()
        self.config.update({"creation_root": "Vault/Library/创作区", "learning_root": "Vault/Library/学习区", "source_notes": "Vault/Library/学习区"})
        for field in ("creation_root", "learning_root"):
            (self.root / self.config[field]).mkdir(parents=True)
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        serialized = release.config_paths(self.root)
        self.assertEqual(serialized["creation_root"], self.config["creation_root"])
        self.assertEqual(serialized["learning_root"], self.config["learning_root"])
        unpacked = self.make_and_extract()
        restored = release.target_config(unpacked)
        self.assertEqual(restored.creation_root, unpacked / self.config["creation_root"])
        self.assertEqual(restored.learning_root, unpacked / self.config["learning_root"])
        self.assertEqual(restored.control_root, restored.knowledge_library / "00-待归档与知识地图")
        self.assertEqual(baseline.read_bytes(), before)
        self.assertEqual((unpacked / "manifest/vault-before-migration.json").read_bytes(), before)

    def test_configured_evidence_requires_its_trusted_checker(self):
        unpacked = self.make_and_extract()
        checker = release.TRUSTED_ROOT / 'skills/grow-creative-library/scripts/audit_source_evidence.py'
        original = Path.is_file
        def missing_checker(path):
            return False if path == checker else original(path)
        with mock.patch.object(Path, 'is_file', missing_checker):
            daily = release.daily_check(self.root, skip_audits=True)
            released = release.verify_release(unpacked, unpacked / release.PACKAGE_MANIFEST)
        self.assertFalse(daily['ok'], daily)
        self.assertFalse(released['ok'], released)
        self.assertTrue(any('checker is missing' in e for e in daily['errors']))
        self.assertTrue(any('checker is missing' in e for e in released['dependency_errors']))

    def test_daily_dynamic_count_passes_while_migration_diff_and_baseline_remain(self):
        baseline = self.root / "manifest/vault-before-migration.json"
        before = baseline.read_bytes()
        result = release.daily_check(self.root, skip_audits=True)
        self.assertTrue(result["ok"], result)
        self.assertGreater(result["markdown"], 200)
        self.assertEqual(result["migration_baseline"], "not_compared")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify_manifest(self.root / "Vault", baseline), 1)
        self.assertEqual(before, baseline.read_bytes())

    def test_preview_is_read_only_and_defaults_to_eight_core_modules(self):
        staging_parent = self.root / self.config["raw_cache"] / "release-staging"
        self.assertFalse(staging_parent.exists())
        before = {p.relative_to(self.root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        result = release.make_package(self.root, self.zip_path, None, True)
        self.assertEqual(len(result["modules"]), 8)
        self.assertNotIn("generate-film-breakdown-report", result["modules"])
        self.assertIn("Vault/film-preview-content.md", result["files"])
        self.assertFalse(self.zip_path.exists())
        after = {p.relative_to(self.root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(staging_parent.exists())

    def test_configured_staging_ignores_system_temp_and_covers_extraction_in_memory(self):
        expected_parent = (self.root / self.config["raw_cache"] / "release-staging").resolve()
        other_temp = self.scratch / "unused-system-temp"
        archive_bytes = io.BytesIO()
        original_zip, original_hash = zipfile.ZipFile, release.sha256
        original_verify = release.verify_release
        verified_roots = []

        def memory_zip(path, mode="r", *args, **kwargs):
            self.assertEqual(Path(path).resolve(), self.zip_path.resolve())
            if mode == "x":
                return original_zip(archive_bytes, "w", *args, **kwargs)
            self.assertEqual(mode, "r")
            return original_zip(io.BytesIO(archive_bytes.getvalue()), "r", *args, **kwargs)

        def memory_output_hash(path):
            if Path(path).resolve() == self.zip_path.resolve():
                return hashlib.sha256(archive_bytes.getvalue()).hexdigest()
            return original_hash(path)

        def record_verification(root, manifest):
            actual_root = root.resolve()
            self.assertTrue(actual_root.is_relative_to(expected_parent))
            verified_roots.append(actual_root)
            return original_verify(root, manifest)

        with mock.patch.dict(os.environ, {"TEMP": str(other_temp), "TMP": str(other_temp)}), \
             mock.patch.object(tempfile, "gettempdir", side_effect=AssertionError("Host TEMP must not be consulted")), \
             mock.patch.object(zipfile, "ZipFile", side_effect=memory_zip), \
             mock.patch.object(release, "sha256", side_effect=memory_output_hash), \
             mock.patch.object(release, "verify_release", side_effect=record_verification):
            result = release.make_package(self.root, self.zip_path, None, False)
        self.assertTrue(result["extracted_verified"])
        self.assertEqual(Path(result["staging_parent"]).resolve(), expected_parent)
        self.assertEqual(len(verified_roots), 2)
        self.assertEqual(verified_roots[0].parent, verified_roots[1].parent.parent)
        self.assertEqual(verified_roots[1].parent.name, "verify-extracted")
        self.assertFalse(other_temp.exists())
        self.assertFalse(self.zip_path.exists(), "This test must not create a ZIP file")
        self.assertTrue(expected_parent.is_dir())
        self.assertEqual(list(expected_parent.iterdir()), [])

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows junction test")
    def test_configured_staging_junction_escape_is_rejected(self):
        outside_cache = self.scratch / "outside-configured-cache"
        outside_cache.mkdir()
        staging_parent = self.root / self.config["raw_cache"] / "release-staging"
        command = "New-Item -ItemType Junction -Path '" + str(staging_parent).replace("'", "''") + "' -Target '" + str(outside_cache).replace("'", "''") + "' | Out-Null"
        created = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True)
        self.assertEqual(created.returncode, 0)
        with self.assertRaisesRegex(release.ReleaseError, "Reparse"):
            release.make_package(self.root, self.zip_path, None, False)
        self.assertEqual(list(outside_cache.iterdir()), [])
        self.assertFalse(self.zip_path.exists())

    def test_encrypted_secrets_backups_and_raw_data_are_excluded_without_reading(self):
        forbidden = ["Secrets/vendor.clixml", "development-backups/old.txt",
                     ".runtime/raw-cache/audio.mp3", ".git/config", ".learnings/private.md"]
        for name in forbidden:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic-private-data")
        original_open, original_copy = Path.open, shutil.copyfile
        forbidden_paths = {str((self.root / n).resolve()) for n in forbidden}
        def guarded_open(path, *args, **kwargs):
            if str(path.resolve()) in forbidden_paths:
                raise AssertionError("Attempted to read an excluded private artifact")
            return original_open(path, *args, **kwargs)
        def guarded_copy(source, dest, *args, **kwargs):
            if str(Path(source).resolve()) in forbidden_paths:
                raise AssertionError("Attempted to copy an excluded private artifact")
            return original_copy(source, dest, *args, **kwargs)
        with mock.patch.object(Path, "open", guarded_open), mock.patch.object(shutil, "copyfile", guarded_copy):
            result = release.make_package(self.root, self.zip_path, None, False)
        self.assertTrue(result["ok"])
        with zipfile.ZipFile(self.zip_path) as archive:
            names = set(archive.namelist())
        self.assertTrue(all(self.root.name + "/" + name not in names for name in forbidden))

    def test_protected_vault_credentials_or_raw_files_fail_without_read_or_removal(self):
        original_open = Path.open
        for name in ("Vault/credential.clixml", "Vault/.env", "Vault/transcript.md"):
            target = self.root / name
            target.write_bytes(b"synthetic-protected-content")
            before = target.stat().st_size
            def guarded_open(path, *args, **kwargs):
                if path.resolve() == target.resolve():
                    raise AssertionError("Protected content must not be opened")
                return original_open(path, *args, **kwargs)
            with self.subTest(name=name), mock.patch.object(Path, "open", guarded_open):
                with self.assertRaisesRegex(release.ReleaseError, "Protected Vault"):
                    release.make_package(self.root, self.zip_path, None, True)
                self.assertTrue(target.exists())
                self.assertEqual(target.stat().st_size, before)
                self.assertFalse(self.zip_path.exists())
            target.unlink()

    def test_shared_loader_rejects_evidence_parent_of_raw_cache(self):
        self.config["source_evidence"] = ".runtime"
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        with self.assertRaisesRegex(release.ReleaseError, "source_evidence"):
            release.config_paths(self.root)

    def test_verification_never_executes_code_from_target_root(self):
        for name in ("skills/operate-personal-knowledge-tree/scripts/knowledge_tree_config.py",
                     "skills/grow-creative-library/scripts/audit_source_evidence.py",
                     "scripts/quick_validate.py"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("raise AssertionError('Untrusted target code executed')\n", encoding="utf-8")
        self.assertEqual(release.config_paths(self.root)["vault"], "Vault")
        self.assertTrue(release.daily_check(self.root, skip_audits=True)["ok"])
        moved = self.make_and_extract()
        self.assertTrue(release.verify_release(moved, moved / release.PACKAGE_MANIFEST)["ok"])

    def test_zip_relocates_with_empty_cache_scaffolds_and_exact_manifest(self):
        moved = self.make_and_extract()
        self.assertTrue((moved / ".runtime/raw-cache").is_dir())
        self.assertEqual(list((moved / ".runtime/raw-cache").iterdir()), [])
        checked = release.verify_release(moved, moved / release.PACKAGE_MANIFEST)
        self.assertTrue(checked["ok"], checked)
        self.assertTrue(release.daily_check(moved, skip_audits=True)["ok"])
        payload = release.load_json(moved / release.PACKAGE_MANIFEST)
        self.assertNotIn(release.PACKAGE_MANIFEST, {r["path"] for r in payload["files"]})

    def test_release_detects_tampered_missing_and_extra_files(self):
        moved = self.make_and_extract()
        note = moved / "Vault/Sources/note-001.md"
        before = note.read_bytes()
        note.write_text("changed", encoding="utf-8")
        self.assertIn("Vault/Sources/note-001.md", release.verify_release(moved, moved / release.PACKAGE_MANIFEST)["changed"])
        note.write_bytes(before)
        note.unlink()
        self.assertIn("Vault/Sources/note-001.md", release.verify_release(moved, moved / release.PACKAGE_MANIFEST)["missing"])
        note.write_bytes(before)
        extra = moved / "extra.txt"
        extra.write_text("unapproved", encoding="utf-8")
        self.assertIn("extra.txt", release.verify_release(moved, moved / release.PACKAGE_MANIFEST)["extra"])

    def test_release_rejects_disallowed_credential_file_without_reading(self):
        moved = self.make_and_extract()
        extra = moved / "added.clixml"
        extra.write_bytes(b"synthetic-encrypted-data")
        with mock.patch.object(Path, "open", side_effect=AssertionError("Credential must not be read")):
            # Inventory is intentionally metadata-only and prunes the credential before opening anything.
            files, dirs, forbidden = release.release_inventory(moved, {".runtime", ".runtime/raw-cache"})
        self.assertIn("added.clixml", forbidden)

    def test_existing_zip_and_inside_workspace_output_are_rejected(self):
        self.zip_path.write_bytes(b"old archive")
        with self.assertRaises(release.ReleaseError):
            release.make_package(self.root, self.zip_path, None, False)
        self.assertEqual(self.zip_path.read_bytes(), b"old archive")
        with self.assertRaises(release.ReleaseError):
            release.make_package(self.root, self.root / "inside.zip", None, True)

    def test_relative_parent_escape_in_allowlist_is_rejected(self):
        data = release.load_json(self.root / release.MODULE_MANIFEST)
        data["include"]["files"].append("../outside.txt")
        write_json(self.root / release.MODULE_MANIFEST, data)
        with self.assertRaises(release.ReleaseError):
            release.release_selection(self.root)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows junction test")
    def test_junction_escape_is_rejected_before_copy(self):
        outside = self.scratch / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("fixture", encoding="utf-8")
        junction = self.root / "docs" / "escaped"
        command = "New-Item -ItemType Junction -Path '" + str(junction).replace("'", "''") + "' -Target '" + str(outside).replace("'", "''") + "' | Out-Null"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True)
        self.assertEqual(result.returncode, 0)
        with self.assertRaisesRegex(release.ReleaseError, "Reparse"):
            release.release_selection(self.root)

    def test_baseline_create_and_manifest_overwrite_are_blocked(self):
        with self.assertRaises(ValueError):
            create_manifest(self.root / "Vault", self.root / "manifest/vault-before-migration.json")
        output = self.scratch / "ordinary.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(create_manifest(self.root / "Vault", output), 0)
        before = output.read_bytes()
        with self.assertRaises(ValueError):
            create_manifest(self.root / "Vault", output)
        self.assertEqual(before, output.read_bytes())

    def test_preview_dependencies_are_visible_but_apply_never_writes(self):
        target = self.scratch / "installed"
        result = release.install_modules(self.root, target, ["generate-film-breakdown-report"], False)
        unit = result["preview_units"][0]
        self.assertEqual(set(unit["members"]), {"generate-film-breakdown-report", "operate-film-breakdown-library"})
        for names in (["generate-film-breakdown-report"], ["grow-creative-library", "operate-film-breakdown-library"]):
            with self.assertRaises(release.ReleaseError):
                release.install_modules(self.root, target, names, True)
        self.assertFalse(target.exists())

    def test_default_install_eight_preserves_old_preview_entry(self):
        target = self.scratch / "installed"
        old = target / "generate-film-breakdown-report" / "SKILL.md"
        old.parent.mkdir(parents=True)
        old.write_text("previous local preview", encoding="utf-8")
        result = release.install_modules(self.root, target, None, True)
        self.assertEqual(result["count"], 8)
        self.assertEqual(old.read_text(encoding="utf-8"), "previous local preview")

    def test_missing_selected_dependency_fails_before_writes(self):
        target = self.scratch / "installed"
        with self.assertRaisesRegex(release.ReleaseError, "dependencies"):
            release.install_modules(self.root, target, ["bilibili-study-notes"], True)
        self.assertFalse(target.exists())

    def test_missing_source_skill_cannot_report_installed(self):
        (self.root / "skills/operate-personal-knowledge-tree/SKILL.md").unlink()
        target = self.scratch / "installed"
        with self.assertRaisesRegex(release.ReleaseError, "Invalid source Skill"):
            release.install_modules(self.root, target, None, True)
        self.assertFalse(target.exists())

    def test_install_cannot_target_a_canonical_subdirectory(self):
        target = self.root / "skills" / "nested-install"
        with self.assertRaisesRegex(release.ReleaseError, "canonical"):
            release.install_modules(self.root, target, None, True)
        self.assertFalse(target.exists())

    def test_transitive_dependency_missing_behind_existing_core_is_rejected(self):
        target = self.scratch / "installed"
        for name in ("operate-personal-knowledge-tree", "grow-creative-library"):
            (target / name).mkdir(parents=True)
            shutil.copyfile(self.root / "skills" / name / "SKILL.md", target / name / "SKILL.md")
        with self.assertRaisesRegex(release.ReleaseError, "internalize-film-knowledge"):
            release.install_modules(self.root, target, ["bilibili-study-notes"], True)
        self.assertFalse((target / "bilibili-study-notes").exists())
        stable = release.select_modules(self.modules)
        self.assertEqual(release.dependency_errors(stable, {m["name"] for m in stable}, self.modules["modules"]), [])

if __name__ == "__main__":
    unittest.main()
