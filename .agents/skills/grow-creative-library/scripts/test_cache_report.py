from __future__ import annotations
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import cache_report


class CacheReportTests(unittest.TestCase):
    def setUp(self):
        configured = cache_report.load_config().raw_cache
        self.temp = tempfile.TemporaryDirectory(prefix="cache-report-test-", dir=configured)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.evidence = self.root / "evidence"
        self.cache.mkdir()
        self.evidence.mkdir()
        self.config = SimpleNamespace(workspace=self.root, raw_cache=self.cache,
                                      source_evidence=self.evidence)
        self.original = self.write("bilibili/course/transcript.md", "作者提出一种可能。\n".encode())
        self.corrected = self.write("bilibili/course/人工校正稿.md", "独立校正，不能由普通ASR重建。\n".encode())

    def write(self, name, content):
        path = self.cache / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def record(self, source_id="source-1", path=None, digest=None):
        path = path or self.original
        record = self.evidence / source_id / "record.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        data = {"schema": "source-evidence-v1", "source_id": source_id,
                "source": {"local_text_hint": path.relative_to(self.root).as_posix(),
                           "text_sha256": digest or hashlib.sha256(path.read_bytes()).hexdigest()}}
        record.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return record

    def report(self, root=None):
        return cache_report.collect_report(root or self.cache, self.config, details=True)

    def test_legacy_statistics_and_json_cli_remain_compatible(self):
        self.write("plain", b"abc")
        expected_size = len(self.original.read_bytes()) + len(self.corrected.read_bytes()) + 3
        result = cache_report.collect_report(self.cache, self.config)
        self.assertEqual(set(result), {"cache", "file_count", "bytes", "human_size", "by_extension"})
        self.assertEqual(result["file_count"], 3)
        self.assertEqual(result["bytes"], expected_size)
        self.assertEqual(result["by_extension"]["[无扩展名]"], 3)
        with mock.patch.object(cache_report, "load_config", return_value=self.config):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(cache_report.main(["--json"]), 0)
            self.assertEqual(json.loads(stdout.getvalue()), result)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cache_report.main([str(self.original.parent)])
            self.assertIn("文件数量：2", stdout.getvalue())
            self.assertNotIn("已有来源引用", stdout.getvalue())

    def test_reference_dedup_and_unregistered_corrected_text_is_retained(self):
        self.record()
        self.record("source-2")
        result = self.report()
        files = result["details"]["source_references"]["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(files[0]["references"]), 2)
        self.assertEqual({r["hash_status"] for r in files[0]["references"]}, {"match"})
        self.assertIn("保留", files[0]["retention"])
        group = result["details"]["groups"][0]
        self.assertEqual(group["referenced_file_count"], 1)
        self.assertEqual(group["unassessed_file_count"], 1)
        self.assertIn("暂时保留", group["unassessed_policy"])
        self.assertFalse(result["details"]["content_reverified"])
        self.assertNotIn("cleanup_candidates", result)

    def test_missing_and_changed_sources_do_not_rewrite_records(self):
        record = self.record()
        before = record.read_bytes()
        self.original.write_bytes(b"edited")
        item = self.report()["details"]["source_references"]["files"][0]
        self.assertEqual(item["references"][0]["hash_status"], "mismatch")
        self.assertIn("保留", item["retention"])
        self.original.unlink()
        item = self.report()["details"]["source_references"]["files"][0]
        self.assertFalse(item["exists"])
        self.assertEqual(item["references"][0]["hash_status"], "missing")
        self.assertEqual(record.read_bytes(), before)

    def test_no_source_records_keeps_everything_unassessed(self):
        self.config.source_evidence = None
        result = self.report()
        self.assertEqual(result["details"]["source_references"]["records_seen"], 0)
        self.assertEqual(result["details"]["groups"][0]["unassessed_file_count"], 2)

    def test_only_bound_materials_and_evidence_records_are_opened(self):
        record = self.record()
        note = self.root / "vault/note.md"
        note.parent.mkdir()
        note.write_bytes(b"private note body")
        before = {p: p.read_bytes() for p in [record, note, self.original, self.corrected]}
        original_open = Path.open
        def guarded(path, *args, **kwargs):
            if path not in {record, self.original}:
                self.fail("Unexpected content read: " + str(path))
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", guarded):
            self.report()
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_scope_does_not_expand_to_other_materials(self):
        self.record()
        other = self.write("books/book/extract.txt", b"another source")
        self.record("book", other)
        result = self.report(self.original.parent)
        self.assertEqual(result["file_count"], 2)
        refs = result["details"]["source_references"]
        self.assertEqual(refs["outside_selected_scope"], 1)
        self.assertEqual(len(refs["files"]), 1)

    def test_invalid_escaping_or_sensitive_hints_are_reported_without_reading(self):
        record = self.record()
        for hint in ("cache/../vault/note.md", "vault/note.md", "cache/.env", "C:/outside.txt"):
            data = json.loads(record.read_text())
            data["source"]["local_text_hint"] = hint
            record.write_text(json.dumps(data), encoding="utf-8")
            result = self.report()
            self.assertTrue(result["warnings"])
            self.assertEqual(result["details"]["source_references"]["files"], [])
        record.write_text("{invalid", encoding="utf-8")
        self.assertTrue(self.report()["warnings"])

    def test_invalid_expected_hash_is_not_reported_as_matching(self):
        self.record(digest="not-a-hash")
        item = self.report()["details"]["source_references"]["files"][0]
        self.assertEqual(item["references"][0]["hash_status"], "invalid_expected_hash")

    def test_maintenance_directory_can_contain_protected_source(self):
        source = self.write("knowledge-quality/task/inputs/source.txt", b"reviewed input")
        self.record("experiment-input", source)
        result = self.report()
        group = next(g for g in result["details"]["groups"] if g["path"] == "knowledge-quality/task")
        self.assertIn("维护与试验", group["kind"])
        self.assertEqual(group["referenced_file_count"], 1)
        self.assertIn("保留", result["details"]["source_references"]["files"][0]["retention"])

    def test_directory_link_and_linked_reference_are_not_followed(self):
        external = self.root / "outside"
        external.mkdir()
        (external / "secret.txt").write_bytes(b"outside")
        link = self.cache / "linked"
        if os.name == "nt":
            process = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                                     capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        else:
            link.symlink_to(external, target_is_directory=True)
        record = self.record()
        data = json.loads(record.read_text())
        data["source"]["local_text_hint"] = "cache/linked/secret.txt"
        record.write_text(json.dumps(data), encoding="utf-8")
        original_open = Path.open
        def guarded(path, *args, **kwargs):
            if path.is_relative_to(external) or path.is_relative_to(link):
                self.fail("Followed directory link")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", guarded):
            result = self.report()
            selected = self.report(link)
        self.assertEqual(result["file_count"], 2)
        self.assertTrue(result["warnings"])
        self.assertEqual(result["details"]["source_references"]["files"], [])
        self.assertEqual(selected["file_count"], 0)
        self.assertTrue(selected["warnings"])
        self.assertEqual((external / "secret.txt").read_bytes(), b"outside")


if __name__ == "__main__":
    unittest.main()

