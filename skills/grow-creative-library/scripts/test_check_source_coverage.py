from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from check_source_coverage import check_coverage, main, sha256


class CoverageTests(unittest.TestCase):
    source = "只在空间狭窄时删侧面机位。\n庭院案例：两人间距远，无法侧拍。\n\n楼上案例：两人靠近，恢复侧面双人机位。\n".encode("utf-8")
    note = "# 笔记\n只在空间狭窄时删侧面机位。\n庭院无法侧拍；楼上靠近后恢复。\n".encode("utf-8")

    def manifest(self):
        return {
            "version": 1, "source_sha256": sha256(self.source), "note_sha256": sha256(self.note),
            "scope": [[1, 4]],
            "items": [
                {"id": "U1", "item": "删机位的限定条件", "source": {"lines": [1, 1], "quote": "只在空间狭窄时"},
                 "note": {"lines": [2, 2], "quote": "只在空间狭窄时"}, "status": "保留"},
                {"id": "U2", "item": "庭院与楼上的条件对照", "source": {"lines": [2, 4]},
                 "note": {"lines": [3, 3]}, "status": "合并", "reason": "两个案例在同一对照句中保留。"},
            ],
        }

    def check(self, manifest=None, source=None, note=None):
        return check_coverage(self.source if source is None else source,
                              self.note if note is None else note,
                              self.manifest() if manifest is None else manifest)

    def test_valid_retained_and_merged_registration_is_not_semantic_approval(self):
        report = self.check()
        self.assertEqual(report["result"], "closed")
        self.assertEqual(report["semantic_review"], "required")
        self.assertEqual(report["unregistered_ranges"], [])

    def test_empty_inventory_is_invalid(self):
        manifest = self.manifest()
        manifest["items"] = []
        report = self.check(manifest)
        self.assertEqual(report["result"], "invalid")
        self.assertTrue(any(e["code"] == "items" for e in report["errors"]))

    def test_missing_example_lines_remain_unregistered(self):
        manifest = self.manifest()
        manifest["items"][1]["source"]["lines"] = [2, 2]
        report = self.check(manifest)
        self.assertEqual(report["result"], "open")
        self.assertEqual(report["unregistered_ranges"], [[4, 4]])

    def test_source_or_note_changes_invalidate_old_manifest(self):
        for source, note in ((self.source + b"\n", self.note), (self.source, self.note + b"\n")):
            with self.subTest(source_changed=source != self.source):
                report = self.check(source=source, note=note)
                self.assertEqual(report["result"], "invalid")
                self.assertTrue(any(e["code"] == "stale_input" for e in report["errors"]))

    def test_out_of_bounds_reversed_and_bool_line_numbers_fail(self):
        for interval in ([0, 1], [3, 2], [1, 99], [True, 2]):
            manifest = self.manifest()
            manifest["items"][0]["note"]["lines"] = interval
            with self.subTest(interval=interval):
                self.assertEqual(self.check(manifest)["result"], "invalid")

    def test_unrelated_locator_quote_is_rejected(self):
        manifest = self.manifest()
        manifest["items"][0]["note"]["lines"] = [3, 3]
        report = self.check(manifest)
        self.assertTrue(any(e["code"] == "quote" for e in report["errors"]))

    def test_changed_qualification_anchor_is_rejected_even_with_fresh_hash(self):
        note = self.note.replace("只在空间狭窄时".encode(), "始终".encode())
        manifest = self.manifest()
        manifest["note_sha256"] = sha256(note)
        report = self.check(manifest, note=note)
        self.assertTrue(any(e["code"] == "quote" for e in report["errors"]))

    def test_pending_items_without_note_keep_registration_open(self):
        for status in ("待补", "待核"):
            manifest = self.manifest()
            item = manifest["items"][0]
            item.update(status=status, reason="限定条件需要回听。")
            del item["note"]
            report = self.check(manifest)
            self.assertEqual(report["result"], "open")
            self.assertEqual(report["pending_items"][0]["id"], "U1")

    def test_retained_item_requires_note_and_merged_requires_reason(self):
        manifest = self.manifest()
        del manifest["items"][0]["note"]
        del manifest["items"][1]["reason"]
        self.assertEqual(self.check(manifest)["result"], "invalid")

    def test_source_mapping_must_stay_inside_declared_scope(self):
        manifest = self.manifest()
        manifest["scope"] = [[1, 2]]
        self.assertEqual(self.check(manifest)["result"], "invalid")

    def test_duplicate_id_and_invalid_status_fail_without_crashing(self):
        manifest = self.manifest()
        manifest["items"][1]["id"] = "U1"
        manifest["items"][0]["status"] = []
        self.assertEqual(self.check(manifest)["result"], "invalid")

    def test_blank_scope_and_binary_source_fail(self):
        manifest = self.manifest()
        manifest["scope"] = [[3, 3]]
        self.assertEqual(self.check(manifest)["result"], "invalid")
        self.assertEqual(self.check(source=b"\xff")["result"], "invalid")

    def test_scope_can_be_an_explicit_partial_review(self):
        manifest = self.manifest()
        manifest["scope"] = [[1, 1]]
        manifest["items"] = manifest["items"][:1]
        self.assertEqual(self.check(manifest)["result"], "closed")

    def test_cli_writes_only_stdout_and_returns_pending_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, note, coverage = root / "source.txt", root / "note.md", root / "coverage.json"
            source.write_bytes(self.source)
            note.write_bytes(self.note)
            manifest = self.manifest()
            manifest["items"][0].update(status="待核", reason="原声尚待回听。")
            coverage.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--source", str(source), "--note", str(note), "--coverage", str(coverage)])
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.getvalue())["result"], "open")
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_invalid_json_returns_invalid_exit_code(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.txt"
            source.write_bytes(self.source)
            coverage = Path(folder) / "coverage.json"
            coverage.write_text("{", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--source", str(source), "--note", str(source), "--coverage", str(coverage)]), 2)


if __name__ == "__main__":
    unittest.main()
