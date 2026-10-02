"""Follow-up scope and completion semantics; fixtures use an isolated temp Vault."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_followup as module
from knowledge_evidence import load_corpus


def note(title, kind, extra="", body=""):
    return (f"---\n类型: {kind}\n材料类型: 测试资料\n{extra}\n---\n"
            f"# {title}\n\n{body or '## 核心观点' + chr(10) + title}\n")


class FollowupSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="followup-semantics-")
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.sources = self.vault / "sources"
        self.cache = self.root / "raw-cache"
        for path in (self.library, self.sources, self.cache):
            path.mkdir(parents=True)
        self.config = {"vault": str(self.vault), "knowledge_library": str(self.library),
                       "source_notes": str(self.sources), "raw_cache": str(self.cache)}
        self.topic = self.library / "主题.md"
        self.topic.write_text(note("主题", "主题笔记", body="## 方法\n比较条件。\n[出处](https://example.invalid/topic)"), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def add_source(self, name, kind="材料总览", extra=""):
        path = self.sources / f"{name}.md"
        path.write_text(note(name, kind, extra), encoding="utf-8")
        return path

    def add_pending_sources(self, count=17):
        for i in range(count):
            self.add_source(f"未整合{i:02d}")

    def corpus(self):
        return load_corpus(self.config, write_index=False)

    def cli_report(self, *args):
        output = io.StringIO()
        with patch.object(module, "resolve_config", return_value=self.root / "config.json"), \
             patch.object(module, "load_config", return_value=self.config), \
             patch.object(sys, "argv", ["knowledge_followup.py", *args]), \
             contextlib.redirect_stdout(output):
            code = module.main()
        return code, json.loads(output.getvalue())

    def test_navigation_provenance_and_unclassified_links_remain_open(self):
        for name, kind in (("导航", "来源地图"), ("资料", "材料总览"),
                           ("课次", "分集笔记"), ("文章", "来源笔记"), ("未知", "未定义类型")):
            self.add_source(name, kind, '已沉淀主题: ["[[library/主题]]"]')
        report = module.followup(self.corpus())
        items = {i["document_type"]: i for i in report["issues"] if i["kind"] == "one_way_source_link"}
        self.assertEqual(len(items), 5)
        self.assertEqual(items["来源地图"]["link_role"], "navigation")
        for kind in ("材料总览", "分集笔记", "来源笔记"):
            self.assertEqual(items[kind]["link_role"], "provenance")
        self.assertEqual(items["未定义类型"]["link_role"], "unclassified")
        self.assertEqual(report["issue_summary"]["one_way_by_role"],
                         {"navigation": 1, "provenance": 3, "unclassified": 1})
        self.assertEqual(report["issue_summary"]["total"], 5)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["semantic_links_written"], 0)

    def test_existing_outside_index_and_missing_remain_distinct(self):
        external = self.vault / "private" / "项目记录.md"
        external.parent.mkdir()
        external.write_text(note("项目记录", "项目资料"), encoding="utf-8")
        self.topic.write_text(note("主题", "主题笔记",
                                  '来源材料: ["[[private/项目记录]]", "[[不存在的资料]]"]'), encoding="utf-8")
        report = module.followup(self.corpus())
        links = {i["target"]: i for i in report["issues"] if "target" in i}
        self.assertEqual(links["private/项目记录"]["kind"], "outside_index")
        self.assertEqual(links["private/项目记录"]["reason"], "exists_outside_index")
        self.assertEqual(links["不存在的资料"]["kind"], "broken_link")
        self.assertEqual(links["不存在的资料"]["reason"], "missing")
        self.assertEqual(report["issue_summary"]["by_kind"]["outside_index"], 1)
        self.assertEqual(report["issue_summary"]["by_kind"]["broken_link"], 1)

    def test_seventeen_pending_limit_is_display_not_progress(self):
        self.add_pending_sources()
        corpus = self.corpus()
        previous = module.snapshot_state(corpus)
        first = module.followup(corpus, previous, 12, True)
        second = module.followup(corpus, previous, 12, True)
        expanded = module.followup(corpus, previous, 17, True)
        summary = first["comparison_scope"]
        self.assertEqual((summary["eligible"], summary["shown"], summary["deferred"]), (17, 12, 5))
        self.assertFalse(summary["advances_review_progress"])
        self.assertEqual(first["comparisons"], second["comparisons"])
        self.assertEqual((len(expanded["comparisons"]), expanded["deferred_comparisons"]), (17, 0))
        self.assertEqual(expanded["issue_summary"]["by_kind"]["source_not_integrated"], 17)
        self.assertEqual(expanded["status"], "needs_review")

    def test_without_suggest_deferred_counts_pending_not_hidden_page(self):
        self.add_pending_sources()
        report = module.followup(self.corpus(), limit=12, include_candidates=False)
        self.assertEqual(report["comparisons"], [])
        self.assertEqual(report["deferred_comparisons"], 17)
        self.assertEqual(report["comparison_scope"]["deferred_meaning"], "sources_awaiting_comparison")
        self.assertFalse(report["comparison_scope"]["suggest"])

    def test_cli_full_expands_issues_only_and_success_is_not_completion(self):
        self.add_pending_sources(22)
        normal_code, normal = self.cli_report("--suggest")
        full_code, full = self.cli_report("--suggest", "--full")
        wide_code, wide = self.cli_report("--suggest", "--full", "--limit", "22")
        self.assertEqual((normal_code, full_code, wide_code), (0, 0, 0))
        self.assertEqual((normal["issue_count"], len(normal["issues"]), len(full["issues"])), (22, 20, 22))
        self.assertEqual(normal["comparisons"], full["comparisons"])
        self.assertEqual((len(full["comparisons"]), len(wide["comparisons"])), (12, 22))
        self.assertEqual(wide["deferred_comparisons"], 0)
        self.assertEqual(wide["status"], "needs_review")

    def test_default_report_does_not_write_cache(self):
        self.add_pending_sources()
        report = module.run_followup(self.config, suggest=True)
        self.assertFalse(report["checkpoint_saved"])
        self.assertEqual(list(self.cache.rglob("*")), [])

    def test_checkpoint_preserves_pending_comparisons_and_affected_topics(self):
        self.add_pending_sources()
        linked = self.add_source("已引用", extra='已沉淀主题: ["[[library/主题]]"]')
        self.topic.write_text(note("主题", "主题笔记", '来源材料: ["[[sources/已引用]]"]'), encoding="utf-8")
        module.run_followup(self.config, checkpoint=True, suggest=True)
        linked.write_text(linked.read_text(encoding="utf-8") + "\n新增适用边界。\n", encoding="utf-8")
        changed = module.run_followup(self.config, checkpoint=True, suggest=True)
        repeated = module.run_followup(self.config, checkpoint=True, suggest=True)
        again = module.run_followup(self.config, checkpoint=True, suggest=True)
        self.assertEqual(changed["affected_topics"], ["library/主题.md"])
        self.assertEqual(repeated["affected_topics"], changed["affected_topics"])
        self.assertEqual(repeated["comparisons"], again["comparisons"])
        self.assertEqual(repeated["issue_summary"]["by_kind"]["source_not_integrated"], 17)
        self.assertEqual(repeated["issue_summary"]["affected_topic_reviews"], 1)
        self.assertFalse(repeated["issue_summary"]["affected_topics_in_issue_total"])
        self.assertEqual(repeated["changes"], {"added": [], "modified": [], "removed": [], "renamed": []})
        state = json.loads((self.cache / "knowledge-retrieval/followup-state-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(state["pending_topic_reviews"], ["library/主题.md"])
        self.assertNotIn("last_content_review", state)
        self.assertEqual(repeated["status"], "needs_review")

    def test_retired_and_explicitly_independent_sources_are_not_new_pending(self):
        self.add_source("已撤回", extra="状态: 已撤回")
        self.add_source("独立", extra="关联检查: 独立保留\n独立理由: 范围与本库主题不同")
        report = module.followup(self.corpus(), include_candidates=True)
        self.assertEqual(report["revoked"], ["sources/已撤回.md"])
        self.assertEqual(report["issue_summary"]["by_kind"].get("source_not_integrated", 0), 0)
        self.assertEqual(report["comparisons"], [])


if __name__ == "__main__":
    unittest.main()
