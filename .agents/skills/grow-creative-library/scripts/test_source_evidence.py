from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from audit_source_evidence import audit, sha


class DurableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        self.cache = self.root / "cache"
        self.evidence = self.root / "evidence"
        for path in (self.vault, self.cache, self.evidence / "source-1"):
            path.mkdir(parents=True)
        self.source = self.cache / "source.txt"
        self.note = self.vault / "note.md"
        self.source.write_text("作者只提出一种可能。\n", encoding="utf-8")
        self.note.write_text("# 笔记\n作者认为这是一种可能。\n<!-- source-evidence: source-1 -->\n", encoding="utf-8")
        self.record = {"schema": "source-evidence-v1", "source_id": "source-1",
            "source": {"title": "材料", "locator": "https://example.test/source", "text_sha256": sha(self.source.read_bytes()), "local_text_hint": "cache/source.txt"},
            "note": {"path": "note.md", "sha256": sha(self.note.read_bytes())},
            "coverage": {"version": 1, "source_sha256": sha(self.source.read_bytes()), "note_sha256": sha(self.note.read_bytes()), "scope": [[1, 1]], "items": [{"id": "U1", "item": "讲者假设", "source": {"lines": [1, 1]}, "note": {"lines": [2, 2]}, "status": "保留"}]},
            "review": {"date": "2026-09-12", "scope": "这一个假设"}}
        self.path = self.evidence / "source-1/record.json"
        self.config = SimpleNamespace(workspace=self.root, vault=self.vault, raw_cache=self.cache, source_evidence=self.evidence)

    def run_audit(self):
        self.path.write_text(json.dumps(self.record, ensure_ascii=False), encoding="utf-8")
        before = self.path.read_bytes()
        result = audit(self.config)
        self.assertEqual(before, self.path.read_bytes())
        return result

    def test_matching_record_is_not_semantic_certification(self):
        result = self.run_audit()
        self.assertEqual(result["status"], "record_bindings_valid")
        self.assertFalse(result["content_reverified"])
        self.assertEqual(result["records"][0]["registration"], "closed")

    def test_missing_source_preserves_history_but_cannot_reverify(self):
        self.source.unlink()
        result = self.run_audit()
        self.assertFalse(result["errors"])
        self.assertIn("reverification_unavailable", result["records"][0]["raw_source"])
        self.assertNotIn("registration", result["records"][0])

    def test_same_filename_with_new_content_is_not_rebound(self):
        self.source.write_text("作者现在提出相反意见。", encoding="utf-8")
        result = self.run_audit()
        self.assertEqual(result["records"][0]["raw_source"], "changed_no_automatic_rebind")

    def test_note_change_invalidates_binding(self):
        self.note.write_text("# 笔记\n这必然成立。", encoding="utf-8")
        self.assertEqual(self.run_audit()["status"], "invalid")

    def test_paths_cannot_escape_or_read_noncache(self):
        for hint in ("../outside.txt", "vault/note.md"):
            with self.subTest(hint=hint):
                self.record["source"]["local_text_hint"] = hint
                self.assertTrue(self.run_audit()["errors"])

    def test_coverage_version_binding_and_note_range_are_checked(self):
        original = copy.deepcopy(self.record)
        self.record["coverage"]["note_sha256"] = "0" * 64
        self.assertTrue(self.run_audit()["errors"])
        self.record = original
        self.record["coverage"]["items"][0]["note"]["lines"] = [99, 99]
        self.assertTrue(self.run_audit()["errors"])

    def test_pending_items_survive_and_raw_artifacts_are_rejected(self):
        item = self.record["coverage"]["items"][0]
        item["status"] = "待核"
        item["reason"] = "未取得原画面"
        result = self.run_audit()
        self.assertEqual(result["records"][0]["pending_items"], ["U1"])
        (self.evidence / "transcript.md").write_text("raw text", encoding="utf-8")
        self.assertTrue(self.run_audit()["errors"])

    def test_missing_optional_setting_is_legacy_compatible(self):
        self.config.source_evidence = None
        self.assertEqual(audit(self.config)["status"], "not_configured_legacy_compatible")

    def test_note_backlink_detects_missing_or_wrong_record(self):
        self.assertTrue(audit(self.config)["errors"])
        self.record["source_id"] = "another-source"
        self.assertTrue(self.run_audit()["errors"])

    def test_offline_history_still_rejects_invalid_source_locator(self):
        self.source.unlink()
        self.record["coverage"]["items"][0]["source"]["lines"] = [100, 101]
        self.assertTrue(self.run_audit()["errors"])

    def test_refreshing_hash_does_not_hide_changed_reviewed_prefix(self):
        original = self.note.read_bytes()
        self.record["note"]["reviewed_prefix_bytes"] = len(original)
        self.record["note"]["reviewed_note_sha256"] = sha(original)
        self.note.write_bytes(original.replace('一种可能'.encode(), '必然成立'.encode()))
        fresh = sha(self.note.read_bytes())
        self.record["note"]["sha256"] = fresh
        self.record["coverage"]["note_sha256"] = fresh
        self.assertTrue(self.run_audit()["errors"])


if __name__ == "__main__":
    unittest.main()
