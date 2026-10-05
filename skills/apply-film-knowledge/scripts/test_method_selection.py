"""Method selection must share review body eligibility and retain exact reads."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from knowledge_evidence import candidates, load_corpus, make_review
from knowledge_review import read_request
from retrieve_knowledge import load_config, load_topics, retrieve, retrieve_scoped


class MethodSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.creation = self.vault / "library/creation/C-导演与视觉"
        self.learning = self.vault / "library/learning"
        for folder in (self.creation, self.learning, self.vault / ".obsidian", self.root / "cache", self.root / "skills", self.root / ".codex"):
            folder.mkdir(parents=True)
        (self.vault / "box.md").write_text("# box", encoding="utf-8")
        self.cp = self.root / ".codex/knowledge-tree.json"
        self.cp.write_text(json.dumps({
            "version": 2, "workspace": "..", "vault": "vault", "vault_name": "fixture",
            "knowledge_library": "vault/library", "creation_root": "vault/library/creation",
            "learning_root": "vault/library/learning", "source_notes": "vault/library/learning",
            "raw_cache": "cache", "prompt_box": "vault/box.md", "skills_root": "skills", "obsidian_cli": None,
        }), encoding="utf-8")
        self.config = load_config(self.cp)

    def write(self, title, body, *, problem="", learning=False):
        path = (self.learning if learning else self.creation) / (title + ".md")
        path.write_text(f"---\n类型: 主题笔记\n分类: 导演与视听语言\n解决问题: {problem}\n---\n"
                        f"# {title}\n{body}\n", encoding="utf-8")
        return path

    def quick(self, question):
        return retrieve_scoped(self.config, question, role="C2", no_cache=True)

    def test_metadata_hit_does_not_fall_back_to_irrelevant_first_chunk(self):
        self.write("声音桥与底噪衔接", "## 核心命题\n声音桥与底噪衔接需要保留来源条件。\n"
                   "## 知识单元\n### 文件管理\n保留文件名称和版本号码。",
                   problem="声音桥与底噪衔接怎样修正")
        result = self.quick("声音桥与底噪衔接怎样修正？")
        self.assertTrue(result["gap"])
        self.assertTrue(result["candidates"])  # Related reading survives; it is not a direct answer.
        self.assertTrue(result["method_gap"])
        self.assertTrue(result["method_gap_reason"])
        card = result["candidates"][0]
        self.assertTrue(card["method_gap"])
        self.assertEqual(card["method_chunks"], [])
        self.assertEqual(card["minimal_action"], "")

    def test_definition_table_is_not_a_repair_method(self):
        self.write("视线与画面方向", "## 核心命题\n视线与画面方向需要区分。\n## 知识单元\n"
                   "### 专业术语表\n| 专业术语 | 定义 | 典型用途 | 误区 |\n|---|---|---|---|\n"
                   "| 视线与画面方向 | 空间连续 | 双人相对 | 方向不能混淆 |",
                   problem="视线与画面方向怎样修正")
        card = self.quick("视线与画面方向怎样修正？")["candidates"][0]
        self.assertTrue(card["method_gap"])
        self.assertEqual(card["method_chunks"], [])

    def test_quick_and_review_share_body_primary_eligibility(self):
        self.write("声音桥与底噪衔接", "## 核心命题\n声音桥与底噪衔接服务空间理解。\n"
                   "## 知识单元\n### 概念\n声音桥与底噪衔接是连续的声音关系。\n"
                   "### 衔接方法\n先比较剪口底噪，再安排声音桥与底噪衔接，最后审听声源是否被误读。\n"
                   "## 适用边界\n没有实际音频不能认证听感。",
                   problem="声音桥与底噪衔接怎样处理")
        question = "声音桥与底噪衔接怎样处理？"
        quick = self.quick(question)
        corpus = load_corpus(self.config, scope=quick["scope"])
        review = make_review(corpus, question, [])
        ids = review["facets"][0]["evidence_ids"]
        chunks = quick["candidates"][0]["method_chunks"]
        self.assertEqual([item["id"] for item in chunks], ids)
        self.assertEqual(chunks[0]["heading"], "衔接方法")
        self.assertEqual(chunks[0]["section_role_hint"], "method")
        self.assertEqual(chunks[0]["selection_status"], "needs_semantic_review")
        self.assertFalse(quick["method_gap"])
        self.assertNotIn("sufficient", quick)

    def test_concept_lookup_preserves_explanatory_use(self):
        self.write("声音桥与底噪衔接", "## 知识单元\n### 概念\n"
                   "声音桥与底噪衔接可以延续注意，但不证明两场同时。",
                   problem="声音桥与底噪衔接")
        chunk = self.quick("声音桥与底噪衔接")["candidates"][0]["method_chunks"][0]
        self.assertEqual(chunk["section_role_hint"], "concept")
        self.assertEqual(chunk["selection_status"], "needs_semantic_review")

    def test_cross_discipline_actual_method_survives(self):
        self.write("剧本场景方法", "## 知识单元\n### 声画衔接方法\n"
                   "声音延续可以构成声音转场；先用听觉视点交代声源，再放回场景审听。\n"
                   "## 适用边界\n声音桥不证明两个场景同时。",
                   problem="声音延续怎样交代声源")
        card = self.quick("声音延续怎样交代声源？")["candidates"][0]
        self.assertFalse(card["method_gap"])
        self.assertEqual(card["method_chunks"][0]["heading"], "声画衔接方法")

    def test_procedure_table_row_keeps_header_and_common_condition(self):
        rows = ["| 诊断对象 | 检查步骤 | 处理边界 |", "|---|---|---|"]
        rows += [f"| 服装状态链{i} | 先比较同一人物与同一时段 | 不改变已采用身份 |" for i in range(12)]
        self.write("服装状态链", "## 知识单元\n### 服装检查方法\n" + "\n".join(rows) +
                   "\n\n所有比较仅限同一剧情时段；不能合并平行世界。",
                   problem="服装状态链怎样比较")
        result = self.quick("服装状态链怎样比较？")
        card = result["candidates"][0]
        chunk = card["method_chunks"][0]
        self.assertEqual(chunk["fragment_kind"], "table_row")
        self.assertTrue(chunk["context_ids"])
        contexts = {item["id"]: item for item in card["context_evidence"]}
        self.assertTrue(set(chunk["context_ids"]) <= set(contexts))
        self.assertTrue(any("诊断对象" in item["excerpt"] for item in contexts.values()))
        self.assertTrue(any("不能合并平行世界" in item["excerpt"] for item in contexts.values()))
        corpus = load_corpus(self.config, scope=result["scope"])
        by_id = {block["id"]: block for doc in corpus["documents"].values() for block in doc["blocks"]}
        self.assertEqual(chunk["content"], by_id[chunk["id"]]["text"])
        self.assertEqual(chunk["line_start"], chunk["line_end"])

    def test_definition_in_action_cell_or_mixed_header_keeps_actual_steps(self):
        for header in ("| 诊断对象 | 检查步骤 | 处理边界 |", "| 诊断对象 | 定义 | 检查步骤 |"):
            with self.subTest(header=header):
                self.write("声源衔接", "## 知识单元\n### 声源衔接方法\n" + header +
                           "\n|---|---|---|\n| 声源衔接 | 先定义声源归属 | 再比较底噪衔接 |",
                           problem="声源衔接怎样处理")
                chunk = self.quick("声源衔接怎样处理？")["candidates"][0]["method_chunks"][0]
                self.assertEqual(chunk["section_role_hint"], "method")

    def test_duplicate_long_headings_use_exact_evidence_continuation(self):
        self.write("服装状态链", "## 知识单元\n### 检查方法\n" +
                   "服装状态链要比较同一人物。" * 100 + "仅适用于白天。\n"
                   "### 检查方法\n" + "服装状态链要比较同一时段。" * 100 + "仅适用于夜晚。",
                   problem="服装状态链怎样检查")
        result = self.quick("服装状态链怎样检查？")
        chunks = result["candidates"][0]["method_chunks"]
        self.assertEqual(len(chunks), 2)
        self.assertNotEqual(chunks[0]["id"], chunks[1]["id"])
        for chunk in chunks:
            request = chunk["continuation"]
            self.assertEqual(request["mode"], "evidence")
            out = read_request(self.config, request, self.cp)
            self.assertEqual(out["evidence"]["id"], chunk["id"])
            self.assertTrue(out["evidence"]["excerpt"].endswith(("仅适用于白天。", "仅适用于夜晚。")))

    def test_legacy_pure_api_uses_same_eligibility_without_fake_ids(self):
        self.write("声音桥与底噪衔接", "## 知识单元\n### 概念\n声音桥与底噪衔接形成连续。\n"
                   "### 衔接方法\n先比较剪口，再安排声音桥与底噪衔接。",
                   problem="声音桥与底噪衔接怎样处理")
        question = "声音桥与底噪衔接怎样处理？"
        direct = retrieve(load_topics(self.creation), question)
        scoped = self.quick(question)
        direct_chunk = direct["candidates"][0]["method_chunks"][0]
        scoped_chunk = scoped["candidates"][0]["method_chunks"][0]
        self.assertEqual(direct_chunk["heading"], scoped_chunk["heading"])
        self.assertNotIn("id", direct_chunk)
        self.assertIn("id", scoped_chunk)

    def test_learning_method_is_not_read_to_fill_a_creative_gap(self):
        self.write("声音桥与底噪衔接", "## 核心命题\n声音桥与底噪衔接应保持连续。\n"
                   "## 知识单元\n### 文件管理\n保留文件名称。",
                   problem="声音桥与底噪衔接怎样处理")
        self.write("学习来源", "## 知识单元\n### 衔接方法\n"
                   "先比较剪口再安排声音桥与底噪衔接。", learning=True)
        result = self.quick("声音桥与底噪衔接怎样处理？")
        self.assertTrue(result["method_gap"])
        self.assertTrue(all("learning" not in path for path in result["scope"]["paths"]))


if __name__ == "__main__":
    unittest.main()
