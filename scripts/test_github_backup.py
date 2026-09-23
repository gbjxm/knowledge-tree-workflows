from __future__ import annotations
import json
from pathlib import Path
import unittest
from unittest import mock

import github_backup as backup
import release_core as release
from test_release import ReleaseFixture, write_json


class LocalGit(backup.Github):
    def __init__(self, remote):
        super().__init__({"repository": "fixture/tree", "branch": "main"})
        self.url = str(remote)

    def preflight(self):
        return {"repository": self.repository, "private": True, "branch": self.branch,
                "author": "Fixture", "email": "fixture@example.invalid"}

    def manifest(self, sha):
        return json.loads(self.git("--git-dir=" + self.url, "show",
                                   sha + ":" + release.PACKAGE_MANIFEST))


def verify_fixture(root):
    # Fixture notes omit the domain schema. Real executions always use full_validate.
    return release.verify_release(root, root / release.PACKAGE_MANIFEST)


class BackupTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_fixture()
        self.config["github_backup"] = {"repository": "fixture/tree", "branch": "main"}
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        self.remote = self.scratch / "remote.git"
        backup.run(["git", "init", "--bare", "--initial-branch=main", str(self.remote)])
        self.transport = LocalGit(self.remote)
        self.service = backup.Backup(self.root, self.transport, verify_fixture)

    def test_empty_noop_and_add_edit_delete_preserve_bytes(self):
        note = self.root / "Vault/Sources/中文 有空格.md"
        note.write_bytes(b"\xef\xbb\xbf# Mixed\r\nline\nend\r\n")
        (self.root / "Vault/empty-folder").mkdir()
        preview = self.service.preview()
        self.assertFalse(self.service.base.exists())
        self.assertTrue(preview["payload_changed"])
        first = self.service.execute()
        self.assertTrue(first["verified"])
        restored = Path(first["restore_path"])
        self.assertEqual((restored / note.relative_to(self.root)).read_bytes(), note.read_bytes())
        self.assertTrue((restored / "Vault/empty-folder").is_dir())
        self.assertFalse((restored / ".git").exists())
        self.assertFalse((restored / ".gitattributes").exists())
        self.assertEqual(len(release.target_config(restored).github_backup), 2)
        again = self.service.execute()
        self.assertFalse(again["new_commit"])
        self.assertEqual(first["commit"], again["commit"])
        note.write_bytes(b"changed\n")
        deleted = self.root / "Vault/Sources/note-000.md"
        deleted.unlink()
        added = self.root / "Vault/Sources/new.md"
        added.write_bytes(b"new\r\n")
        preview = self.service.preview()
        self.assertIn(deleted.relative_to(self.root).as_posix(), preview["changes"]["deleted"])
        changed = self.service.execute()
        restore = Path(changed["restore_path"])
        self.assertFalse((restore / deleted.relative_to(self.root)).exists())
        self.assertEqual((restore / added.relative_to(self.root)).read_bytes(), b"new\r\n")
        self.assertEqual((restore / note.relative_to(self.root)).read_bytes(), b"changed\n")
        before_refs = self.transport.refs()
        manual = self.service.execute(first["commit"])
        self.assertEqual(before_refs, self.transport.refs())
        self.assertEqual(Path(manual["restore_path"]).joinpath(note.relative_to(self.root)).read_bytes(),
                         b"\xef\xbb\xbf# Mixed\r\nline\nend\r\n")

    def test_snapshot_edit_aborts_before_push(self):
        original = backup.shutil.copyfile
        fired = []
        def editing(src, dst, *args, **kwargs):
            result = original(src, dst, *args, **kwargs)
            if not fired and Path(src) == self.root / "Vault/prompts.md":
                Path(src).write_text("# concurrent edit\n", encoding="utf-8")
                fired.append(True)
            return result
        with mock.patch.object(backup.shutil, "copyfile", side_effect=editing):
            with self.assertRaisesRegex(backup.BackupError, "changed during snapshot"):
                self.service.execute()
        self.assertEqual(self.transport.refs(), {})

    def test_push_failure_and_unknown_remote(self):
        original = self.transport.push
        with mock.patch.object(self.transport, "push", side_effect=backup.BackupError("simulated network failure")):
            with self.assertRaisesRegex(backup.BackupError, "push:"):
                self.service.execute()
        self.assertEqual(self.transport.refs(), {})
        self.assertFalse(self.service.state().get("verified_commit"))
        # A failed first upload is known but the empty remote should be safely retryable.
        first = self.service.execute()
        work = Path(first["directory"]) / "remote-clone"
        tree = self.transport.git("rev-parse", first["commit"] + "^{tree}", cwd=work).decode().strip()
        unexpected = self.transport.git("-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                                        "commit-tree", tree, "-p", first["commit"], "-m", "unrelated edit",
                                        cwd=work).decode().strip()
        original(work, unexpected, "refs/heads/main")
        with self.assertRaisesRegex(backup.BackupError, "Unrecognized remote commit"):
            self.service.execute()
        self.assertEqual(self.transport.refs()["refs/heads/main"], unexpected)

    def test_network_error_after_push_can_resume(self):
        original = self.transport.push
        def pushed_then_error(work, source, destination):
            original(work, source, destination)
            raise backup.BackupError("connection lost after remote accepted")
        with mock.patch.object(self.transport, "push", side_effect=pushed_then_error):
            with self.assertRaisesRegex(backup.BackupError, "connection lost"):
                self.service.execute()
        pending = self.service.state()["pending_commit"]
        resumed = self.service.execute()
        self.assertEqual(resumed["commit"], pending)
        self.assertFalse(resumed["new_commit"])

    def test_secret_and_large_file_blocked(self):
        path = self.root / "Vault/.obsidian/plugin-config.json"
        write_json(path, {"api_key": "fixture-secret"})
        with self.assertRaisesRegex(backup.BackupError, "secret-like"):
            self.service.preview()
        path.unlink()
        with mock.patch.object(backup, "MAX_FILE", 10):
            with self.assertRaisesRegex(backup.BackupError, "limit"):
                self.service.preview()
        self.assertEqual(self.transport.refs(), {})

    def test_restore_missing_and_tampered_are_not_verified(self):
        first = self.service.execute()
        original = backup.export_commit
        for mode in ("missing", "changed"):
            def broken(*args, **kwargs):
                result = original(*args, **kwargs)
                target = args[3] / "Vault/Sources/later.md"
                if mode == "missing":
                    target.unlink()
                else:
                    target.write_bytes(b"tampered")
                return result
            refs = self.transport.refs()
            with mock.patch.object(backup, "export_commit", side_effect=broken):
                with self.assertRaisesRegex(backup.BackupError, "Validation failed"):
                    self.service.execute(first["commit"])
            self.assertEqual(refs, self.transport.refs())

    def test_restore_failure_after_push_creates_no_tag(self):
        count = []
        def validate(root):
            count.append(root.name)
            if root.name == "restored":
                return {"ok": False, "reason": "simulated restored file failure"}
            return verify_fixture(root)
        self.service.validator = validate
        with self.assertRaisesRegex(backup.BackupError, "Validation failed"):
            self.service.execute()
        refs = self.transport.refs()
        self.assertIn("refs/heads/main", refs)
        self.assertFalse(any(ref.startswith("refs/tags/") for ref in refs))
        self.assertFalse(self.service.state().get("verified_commit"))

    def test_config_and_path_escape_fail_closed(self):
        self.config["github_backup"]["token"] = "do-not-save"
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        with self.assertRaises(Exception):
            release.target_config(self.root)
        self.config.pop("github_backup")
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        self.assertIsNone(release.target_config(self.root).github_backup)
        with self.assertRaises(Exception):
            release.bounded_path(self.root, "../escape", exists=False)

    def test_cold_clone_recreates_empty_directories(self):
        first = self.service.execute()
        clone = self.scratch / "cold-clone"
        self.transport.clone(clone)
        self.transport.git("checkout", "--detach", first["commit"], cwd=clone)
        self.assertFalse((clone / ".runtime/raw-cache").exists())
        backup.prepare_clone_directories(clone)
        loaded = release.target_config(clone)
        self.assertTrue(loaded.raw_cache.is_dir())
        self.assertTrue((clone / "Vault/.obsidian").is_dir())
        self.assertEqual(loaded.workspace, clone)


if __name__ == "__main__":
    unittest.main()
