"""Regression tests for exact text identity, fences, source kinds and CLI conflicts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from knowledge_evidence import load_corpus
from knowledge_review import read_request, review_scoped
from read_knowledge_section import read_section
from retrieve_knowledge import (_bind_readings, load_config, load_topics, retrieve,
                                retrieve_scoped)


class ReadingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("vault/.obsidian", "vault/library/creation/B-故事与剧本",
                     "vault/library/learning", "cache", "skills", ".codex"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "vault/box.md").write_bytes(b"# box")
        self.cp = self.root / ".codex/knowledge-tree.json"
        self.payload = {
            "version": 2, "workspace": "..", "vault": "vault", "vault_name": "identity-fixture",
            "knowledge_library": "vault/library", "creation_root": "vault/library/creation",
            "learning_root": "vault/library/learning", "source_notes": "vault/library/learning",
            "raw_cache": "cache", "prompt_box": "vault/box.md", "skills_root": "skills",
            "obsidian_cli": None,
        }
        self.write_config(self.payload)
        self.path = self.root / "vault/library/creation/B-故事与剧本/方法.md"

    def write_config(self, payload):
        self.cp.write_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.config = load_config(self.cp)

    def write_note(self, body, kind="主题笔记", newline="\n"):
        value = f"---\n类型: {kind}\n分类: 故事与剧本\n---\n# 稳定人物\n{body}\n"
        self.path.write_bytes(value.replace("\n", newline).encode("utf-8"))

    def quick(self, *, no_cache=True):
        return retrieve_scoped(self.config, "稳定人物", role="B", no_cache=no_cache)

    def test_complete_multiline_crlf_is_not_a_truncated_preview(self):
        self.write_note("## 方法与案例\n稳定人物通过行动检验。\n只适用于已知条件。", newline="\r\n")
        card = self.quick()["candidates"][0]
        item = card["method_chunks"][0]
        self.assertEqual(item["content"].splitlines(), ["稳定人物通过行动检验。", "只适用于已知条件。"])
        self.assertFalse(item["truncated"])
        self.assertFalse(item["read_required"])
        self.assertIsNone(item["continuation"])
        self.assertFalse(card["read_required"])

    def fence_body(self):
        return ("## 方法与案例\n### 稳定人物方法\n稳定人物通过行动检验。\n"
                "```text\n```not-a-closing-fence\n## 适用边界\n这行仍属于代码。\n```\n"
                "真实方法末尾：稳定人物只适用当前条件。\n"
                "## 适用边界\n真正边界不能遗漏。")

    def test_nonclosing_fence_line_cannot_relocate_final_condition(self):
        self.write_note(self.fence_body())  # LF isolates this from newline normalization.
        card = self.quick()["candidates"][0]
        item = next(e for e in card["method_chunks"] if e["heading"] == "稳定人物方法")
        self.assertIn("真实方法末尾", item["content"])
        self.assertIn("## 适用边界\n这行仍属于代码", item["content"])
        self.assertFalse(item["truncated"])
        self.assertFalse(item["read_required"])
        self.assertEqual(card["boundary"], "真正边界不能遗漏。")

    def test_section_and_evidence_use_the_real_closing_fence(self):
        self.write_note(self.fence_body())
        quick = self.quick()
        out = read_section(self.cp, self.path, "稳定人物方法", scope=quick["scope"])
        self.assertIn("真实方法末尾", out["content"])
        self.assertIn("## 适用边界\n这行仍属于代码", out["content"])
        self.assertNotIn("真正边界不能遗漏", out["content"])
        self.assertFalse(out["read_required"])
        corpus = load_corpus(self.config, scope=quick["scope"])
        doc = next(iter(corpus["documents"].values()))
        block = next(b for b in doc["blocks"] if b["heading"] == "稳定人物方法")
        self.assertIn("真实方法末尾", block["text"])
        self.assertEqual(block["text"], out["content"])

    def test_all_indexed_source_kinds_keep_source_identity_in_section_reader(self):
        for kind in ("来源笔记", "材料总览", "分集笔记", "来源地图"):
            with self.subTest(kind=kind):
                self.write_note("## 稳定人物方法\n稳定人物通过行动受到检验。", kind=kind)
                pack, corpus = review_scoped(self.config, "稳定人物", ["稳定人物"], role="B", no_cache=True)
                doc = next(iter(corpus["documents"].values()))
                self.assertEqual(doc["kind"], "source")
                request = {"mode": "section", "path": str(self.path), "heading": "稳定人物方法",
                           "scope": pack["scope"], "snapshot": pack["snapshot"],
                           "document_hash": hashlib.sha256(self.path.read_bytes()).hexdigest()}
                out = read_request(self.config, request, self.cp)
                self.assertEqual(out["kind"], "source")
                self.assertEqual(out["content"], "稳定人物通过行动受到检验。")

    def test_legacy_cache_same_size_mtime_change_cannot_bind_stale_excerpt(self):
        legacy = {key: value for key, value in self.payload.items()
                  if key not in {"creation_root", "learning_root"}}
        self.write_config(legacy)
        self.write_note("## 方法与案例\n稳定人物保持原则。")
        self.quick(no_cache=False)  # Keep this cache; do not make the test pass by deleting it.
        cache_path = self.root / "cache/knowledge-retrieval/index-v2.json"
        self.assertTrue(cache_path.is_file())
        old_stat = self.path.stat()
        raw = self.path.read_bytes()
        changed = raw.replace("保持原则".encode("utf-8"), "放弃原则".encode("utf-8"))
        self.assertEqual(len(raw), len(changed))
        self.path.write_bytes(changed)
        os.utime(self.path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.assertEqual(self.path.stat().st_mtime_ns, old_stat.st_mtime_ns)
        self.assertEqual(self.path.stat().st_size, old_stat.st_size)
        current = self.quick(no_cache=False)
        card = current["candidates"][0]
        self.assertEqual(card["method_chunks"][0]["content"], "稳定人物放弃原则。")
        self.assertNotIn("保持原则", json.dumps(card, ensure_ascii=False))
        self.assertEqual(card["document_hash"], hashlib.sha256(changed).hexdigest())

    def test_binding_rejects_candidate_built_before_document_change(self):
        self.write_note("## 方法与案例\n稳定人物保持原则。")
        topics = load_topics(Path(self.config["knowledge_library"]))
        result = retrieve(topics, "稳定人物", "", 1, role="B")
        self.assertTrue(result["candidates"])
        self.write_note("## 方法与案例\n稳定人物放弃原则。")
        corpus = load_corpus(self.config)
        with self.assertRaisesRegex(ValueError, "变化|陈旧|版本|重新"):
            _bind_readings(result, corpus)

    def test_read_request_rejects_abbreviated_conflicting_cli_options(self):
        self.write_note("## 方法与案例\n" + "稳定人物需要体现行动。" * 200)
        request = self.quick()["candidates"][0]["method_chunks"][0]["continuation"]
        self.assertIsNotNone(request)
        base = [sys.executable, "-B", "-X", "utf8", str(Path(__file__).with_name("knowledge_review.py")),
                "--config", str(self.cp), "--read-request", json.dumps(request, ensure_ascii=False)]
        for extra in (["--ro", "C"], ["--quer", ""],
                      ["--incl", str(self.root / "vault/library/learning")]):
            with self.subTest(extra=extra):
                proc = subprocess.run(base + extra, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn('"content":', proc.stdout)


if __name__ == "__main__":
    unittest.main()
