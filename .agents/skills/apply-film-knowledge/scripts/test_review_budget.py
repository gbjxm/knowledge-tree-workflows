"""Review budgets preserve full evidence or an explicit same-scope read request."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from knowledge_evidence import candidates, full_evidence, load_corpus, make_review
from knowledge_scope import make_scope


def note(title, body, extra=""):
    return ("---\n类型: 来源笔记\n材料类型: 专业文章\n分类: 故事与剧本\n"
            + extra + "\n---\n# " + title + "\n\n" + body + "\n")


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


class ReviewBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.creation = self.vault / "knowledge/creation"
        self.learning = self.vault / "knowledge/learning"
        self.role = self.creation / "B-故事与剧本"
        self.shared = self.creation / "岗位共用"
        self.cache = self.root / "cache"
        for path in (self.role, self.shared, self.learning, self.cache):
            path.mkdir(parents=True)
        self.config = dict(vault=str(self.vault), knowledge_library=str(self.vault / "knowledge"),
                           creation_root=str(self.creation), learning_root=str(self.learning),
                           source_notes=str(self.learning), raw_cache=str(self.cache))
        self.scope = make_scope(self.config, "B")
        self.path = self.role / "稳定人物.md"
        self.body = "人物稳定可以通过行动承受压力。只有场景已经建立选择，才能判断该方法适用。"
        self.path.write_text(note("稳定人物", "## 稳定人物方法\n" + self.body), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def add_navigation(self, path, title, body, count):
        targets = []
        for i in range(count):
            filename = f"学习材料{i:03d}及其条件说明"
            (self.learning / (filename + ".md")).write_text(
                "---\n类型: 主题笔记\n---\n# 不能进入本次正文\n学习区独有内容\n", encoding="utf-8")
            targets.append("[[knowledge/learning/" + filename + "]]")
        extra = "已沉淀主题: " + json.dumps(targets, ensure_ascii=False)
        path.write_text(note(title, body, extra), encoding="utf-8")

    def corpus(self):
        return load_corpus(self.config, scope=self.scope)

    def review(self, corpus, budget=9000, query="稳定人物"):
        return make_review(corpus, query, [query], role="B", budget=budget)

    def primary(self, review):
        wanted = review["facets"][0]["evidence_ids"][0]
        return next(item for item in review["evidence"] if item["id"] == wanted)

    def test_unrelated_navigation_cannot_evict_complete_method(self):
        self.add_navigation(self.shared / "索引.md", "量子计算导航", "## 量子协议\n量子纠缠协议说明。", 80)
        corpus = self.corpus()
        review = self.review(corpus, budget=3000)
        self.assertEqual(review["out_of_scope_links"], [])
        self.assertEqual(review["out_of_scope_link_summary"]["omitted_unrelated"], 80)
        self.assertEqual(review["out_of_scope_link_summary"]["omitted_for_budget"], 0)
        self.assertEqual(self.primary(review)["excerpt"], self.body)
        self.assertNotIn("continuation", self.primary(review))
        self.assertFalse(review["requires_more_reading"])
        self.assertFalse(review["budget_exceeded"])
        self.assertLessEqual(size(review), 3000)

    def test_relevant_navigation_is_shortened_before_body(self):
        self.add_navigation(self.path, "稳定人物", "## 稳定人物方法\n" + self.body, 80)
        review = self.review(self.corpus(), budget=3000)
        summary = review["out_of_scope_link_summary"]
        self.assertEqual(summary["relevant"], 80)
        self.assertEqual(summary["returned"] + summary["omitted_for_budget"], 80)
        self.assertGreater(summary["omitted_for_budget"], 0)
        self.assertFalse(summary["relevant_complete"])
        self.assertEqual(self.primary(review)["excerpt"], self.body)
        self.assertFalse(review["budget_exceeded"])
        self.assertLessEqual(size(review), 3000)

    def test_relevant_navigation_remains_when_budget_allows(self):
        self.add_navigation(self.path, "稳定人物", "## 稳定人物方法\n" + self.body, 1)
        review = self.review(self.corpus())
        self.assertEqual(len(review["out_of_scope_links"]), 1)
        self.assertEqual(review["out_of_scope_link_summary"]["omitted_for_budget"], 0)
        self.assertTrue(review["out_of_scope_link_summary"]["relevant_complete"])
        self.assertEqual(review["scope"], self.scope)
        self.assertNotIn("学习区独有内容", json.dumps(review, ensure_ascii=False))

    def test_gap_does_not_return_whole_corpus_navigation(self):
        self.add_navigation(self.path, "稳定人物", "## 稳定人物方法\n" + self.body, 40)
        review = self.review(self.corpus(), query="黑洞磁场")
        self.assertEqual(review["facets"][0]["status"], "gap")
        self.assertEqual(review["out_of_scope_links"], [])
        self.assertEqual(review["out_of_scope_link_summary"]["omitted_unrelated"], 40)

    def test_deferred_long_source_has_complete_same_scope_request(self):
        body = "稳定人物需要检查实际行动。" * 200 + "最后条件：不能把观众未获知的信息当作已知。"
        self.path.write_text(note("稳定人物", "## 稳定人物方法\n" + body), encoding="utf-8")
        corpus = self.corpus()
        review = self.review(corpus)
        item = self.primary(review)
        self.assertEqual(item["excerpt"], "")
        self.assertTrue(item["read_required"])
        self.assertTrue(review["requires_more_reading"])
        self.assertEqual(item["continuation"], dict(mode="evidence", read_id=item["id"],
                                                   snapshot=corpus["snapshot"], scope=self.scope))
        restored = full_evidence(corpus, item["continuation"]["read_id"])
        self.assertEqual(restored["excerpt"], body)
        self.assertIn("最后条件", restored["excerpt"])

    def test_budget_deferral_includes_request_in_final_size(self):
        body = "稳定人物需要核对当前选择及其实际代价。" * 70 + "最后条件：例外必须保留。"
        self.assertLess(len(body), 1800)
        self.path.write_text(note("稳定人物", "## 稳定人物方法\n" + body), encoding="utf-8")
        corpus = self.corpus()
        full = self.review(corpus, budget=50000)
        budget = size(full) - 700
        limited = self.review(corpus, budget=budget)
        item = self.primary(limited)
        self.assertTrue(item["read_required"])
        self.assertTrue(limited["requires_more_reading"])
        self.assertEqual(item["excerpt"], "")
        self.assertLessEqual(size(limited), budget)
        self.assertFalse(limited["budget_exceeded"])
        self.assertEqual(item["continuation"]["scope"], self.scope)
        self.assertEqual(full_evidence(corpus, item["id"])["excerpt"], body)

    def test_tiny_budget_keeps_evidence_and_table_context_locators(self):
        rows = ["| 原则 | 说明 |", "|---|---|"]
        rows += [f"| 其他技术{i} | 参数{i} |" for i in range(9)]
        rows += ["| 稳定人物 | 行动体现选择 |"]
        body = "## 方法对照\n只用于已写清行动的场景。\n\n" + "\n".join(rows) + "\n\n最后条件：旁人看法不能替代角色行动。"
        self.path.write_text(note("人物方法表", body), encoding="utf-8")
        corpus = self.corpus()
        generous = self.review(corpus, budget=50000)
        tiny = self.review(corpus, budget=100)
        self.assertTrue(tiny["budget_exceeded"])
        self.assertGreater(size(tiny), 100)
        self.assertEqual(generous["facets"], tiny["facets"])
        self.assertEqual([e["id"] for e in generous["evidence"]], [e["id"] for e in tiny["evidence"]])
        main = self.primary(tiny)
        self.assertEqual(main["fragment_kind"], "table_row")
        self.assertTrue(main["parent_id"])
        self.assertTrue(main["context_ids"])
        items = {e["id"]: e for e in tiny["evidence"]}
        self.assertTrue(set(main["context_ids"]).issubset(items))
        self.assertTrue(any("最后条件" in full_evidence(corpus, context_id)["excerpt"]
                            for context_id in main["context_ids"]))
        for item in items.values():
            if item["read_required"]:
                self.assertEqual(item["excerpt"], "")
                self.assertEqual(item["continuation"]["scope"], self.scope)
                self.assertEqual(item["continuation"]["snapshot"], corpus["snapshot"])
            else:
                self.assertEqual(item["excerpt"], full_evidence(corpus, item["id"])["excerpt"])

    def test_tiny_budget_does_not_defer_a_body_smaller_than_its_request(self):
        review = self.review(self.corpus(), budget=100)
        self.assertTrue(review["budget_exceeded"])
        self.assertGreater(size(review), 100)
        self.assertEqual(self.primary(review)["excerpt"], self.body)
        self.assertFalse(review["requires_more_reading"])
        self.assertNotIn("continuation", self.primary(review))

    def test_budget_does_not_mutate_corpus_scope_or_ranking(self):
        self.add_navigation(self.path, "稳定人物", "## 稳定人物方法\n" + self.body, 60)
        corpus = self.corpus()
        before = copy.deepcopy(corpus)
        ranked_before = candidates(corpus, "稳定人物")
        small = self.review(corpus, budget=100)
        large = self.review(corpus, budget=50000)
        self.assertEqual(before, corpus)
        self.assertEqual(ranked_before, candidates(corpus, "稳定人物"))
        self.assertEqual(small["facets"], large["facets"])
        self.assertEqual(small["scope"], large["scope"])
        self.assertEqual(small["snapshot"], large["snapshot"])


if __name__ == "__main__":
    unittest.main()
