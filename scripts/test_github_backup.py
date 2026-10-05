from __future__ import annotations
import json
from pathlib import Path
import unittest
from unittest import mock

import github_backup as backup
import release_core as release
from test_release import ReleaseFixture, write_json


class LocalGit(backup.Github):
    def __init__(self, remote, private=True):
        super().__init__({"repository": "fixture/tree", "branch": "main"})
        self.url = str(remote)
        self.private = private

    def preflight(self):
        return {"repository": self.repository, "private": self.private,
                "visibility": "private" if self.private else "public", "branch": self.branch,
                "author": "Fixture", "email": "fixture@example.invalid"}

    def manifest(self, sha):
        return json.loads(self.git("--git-dir=" + self.url, "show",
                                   sha + ":" + release.PACKAGE_MANIFEST))


def verify_fixture(root):
    # Fixture notes omit the domain schema. Real executions always use full_validate.
    return release.verify_release(root, root / release.PACKAGE_MANIFEST)


class GithubPreflightTests(unittest.TestCase):
    def setUp(self):
        self.transport = backup.Github({"repository": "fixture/tree", "branch": "main"})
        self.info = {"full_name": "fixture/tree", "private": True, "visibility": "private",
                     "archived": False, "disabled": False, "permissions": {"push": True}}
        self.user = {"login": "Fixture", "id": 123}

    def assert_blocked(self, info, message):
        with mock.patch.object(self.transport, "api", return_value=info) as api, \
                mock.patch.object(backup, "run") as command:
            with self.assertRaisesRegex(backup.BackupError, message):
                self.transport.preflight()
            self.assertEqual(api.call_count, 1)
            command.assert_not_called()

    def test_private_and_public_report_actual_visibility(self):
        for private, visibility in ((True, "private"), (False, "public")):
            with self.subTest(visibility=visibility):
                info = {**self.info, "private": private, "visibility": visibility}
                with mock.patch.object(self.transport, "api", side_effect=[info, self.user]) as api, \
                        mock.patch.object(backup, "run") as command:
                    target = self.transport.preflight()
                self.assertIs(target["private"], private)
                self.assertEqual(target["visibility"], visibility)
                self.assertEqual(target["repository"], "fixture/tree")
                self.assertEqual(target["email"], "123+Fixture@users.noreply.github.com")
                command.assert_called_once_with(["git", "check-ref-format", "refs/heads/main"])
                self.assertEqual(api.call_args_list, [mock.call("repos/fixture/tree"), mock.call("user")])

    def test_repository_identity_remains_exact_and_case_insensitive(self):
        self.assert_blocked({**self.info, "full_name": "fixture/other"}, "configured repository")
        info = {**self.info, "full_name": "Fixture/Tree"}
        with mock.patch.object(self.transport, "api", side_effect=[info, self.user]), \
                mock.patch.object(backup, "run"):
            self.assertEqual(self.transport.preflight()["repository"], "Fixture/Tree")

    def test_missing_malformed_internal_and_conflicting_visibility_block(self):
        invalid = [{k: v for k, v in self.info.items() if k != field}
                   for field in ("private", "visibility")]
        invalid.extend({**self.info, "private": value} for value in (None, 1, 0, "true", []))
        invalid.extend({**self.info, "visibility": value} for value in (None, "internal", "PRIVATE", []))
        invalid.extend(({**self.info, "private": True, "visibility": "public"},
                        {**self.info, "private": False, "visibility": "private"}))
        for info in invalid:
            with self.subTest(info=info):
                self.assert_blocked(info, "consistent public/private")

    def test_archived_disabled_and_unconfirmed_push_block_for_both_visibilities(self):
        for private, visibility in ((True, "private"), (False, "public")):
            valid = {**self.info, "private": private, "visibility": visibility}
            invalid = [{**valid, "archived": value} for value in (True, None, "false", 0)]
            invalid.append({k: v for k, v in valid.items() if k != "archived"})
            invalid.extend({**valid, "disabled": value} for value in (True, None, "false", 0))
            invalid.append({k: v for k, v in valid.items() if k != "disabled"})
            invalid.extend({**valid, "permissions": value} for value in (None, [], {}))
            invalid.append({k: v for k, v in valid.items() if k != "permissions"})
            invalid.extend({**valid, "permissions": {"push": value}} for value in (False, None, 1, "true"))
            for info in invalid:
                with self.subTest(visibility=visibility, info=info):
                    self.assert_blocked(info, "unarchived, enabled, with confirmed push")

    def test_non_object_and_missing_repository_identity_block(self):
        for info in (None, [], "fixture/tree", {}, {**self.info, "full_name": None}):
            with self.subTest(info=info):
                self.assert_blocked(info, "configured repository")

    def test_invalid_branch_still_blocks_before_author_lookup(self):
        self.transport.branch = "bad..branch"
        with mock.patch.object(self.transport, "api", return_value=self.info) as api, \
                mock.patch.object(backup, "run", side_effect=backup.BackupError("invalid ref")):
            with self.assertRaisesRegex(backup.BackupError, "invalid ref"):
                self.transport.preflight()
            self.assertEqual(api.call_count, 1)


class BackupTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_fixture()
        self.config["github_backup"] = {"repository": "fixture/tree", "branch": "main"}
        write_json(self.root / ".codex/knowledge-tree.json", self.config)
        self.remote = self.scratch / "remote.git"
        backup.run(["git", "init", "--bare", "--initial-branch=main", str(self.remote)])
        self.transport = LocalGit(self.remote)
        self.service = backup.Backup(self.root, self.transport, verify_fixture)

    def test_public_snapshot_and_read_only_restore_record_actual_visibility(self):
        self.transport.private = False
        preview = self.service.preview()
        self.assertIs(preview["target"]["private"], False)
        self.assertEqual(preview["target"]["visibility"], "public")
        self.assertFalse(self.service.base.exists())
        receipt = self.service.execute()
        saved = json.loads((Path(receipt["directory"]) / "receipt.json").read_text(encoding="utf-8"))
        self.assertIs(saved["target"]["private"], False)
        self.assertEqual(saved["target"]["visibility"], "public")
        self.assertTrue(saved["verified"])
        refs = self.transport.refs()
        restored = self.service.execute(receipt["commit"])
        self.assertEqual(refs, self.transport.refs())
        self.assertIs(restored["target"]["private"], False)
        self.assertEqual(restored["target"]["visibility"], "public")
        self.assertTrue(restored["verified"])

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
