"""Behavioral tests using isolated sources; never edits the live Vault."""
from __future__ import annotations
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from knowledge_evidence import (load_corpus, make_review, full_evidence, validate_application,
                                section_blocks, resolve_link, candidates, atomic_json)
from knowledge_followup import followup, snapshot_state, run_followup


def note(title, body, kind="主题笔记", extra=""):
    return ("---\n类型: " + kind + "\n材料类型: 专业资料汇编\n分类: 摄影美术与现场制作\n"
            "完整程度: 部分摘录\n证据状态: 单一来源\n" + extra + "\n---\n# " + title + "\n\n" + body)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.sources = self.vault / "sources"
        self.cache = self.root / "raw-cache"
        for d in (self.library, self.sources, self.cache):
            d.mkdir(parents=True)
        self.config = dict(vault=str(self.vault), knowledge_library=str(self.library),
                           source_notes=str(self.sources), raw_cache=str(self.cache))
        self.topic = self.library / "连续性.md"
        self.source = self.sources / "服装研究.md"
        self.topic.write_text(note("服装连续性",
            "## 知识单元\n### 服装状态链\n服装身份与剧情时间通过状态链记录，跨镜检查服装颜色与污损。\n"
            "## 适用边界\n服装颜色随光源合理改变不等于身份改变；应先排除光线。\n",
            extra='来源材料: ["[[sources/服装研究]]"]'), encoding="utf-8")
        self.source.write_text(note("服装研究",
            "## 核心观点\n服装状态反映人物身份与剧情时间。\n"
            "## 来源组与可靠性\n"
            "| 来源 | 支持内容 | 边界 |\n|---|---|---|\n"
            "| [服装协会](https://example.invalid/costume) | 服装颜色与污损状态链支持剧情时间 | 仅案例，不是通用处方 |\n"
            "| [空间协会](https://example.invalid/space) | 空间通道与家具尺度 | 不能替代建筑校验 |\n",
            kind="材料总览", extra='已沉淀主题: ["[[library/连续性]]"]'), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def corpus(self, cache=False):
        return load_corpus(self.config, write_index=cache)

    def test_source_only_new_content_discoverable(self):
        x = self.corpus()
        before = x["snapshot"]
        p = self.sources / "新文章.md"
        p.write_text(note("液态镜头", "## 方法\n液态镜头参数是独立方法，固定对照曝光。\n",
                          "材料总览", "沉淀状态: 未沉淀"), encoding="utf-8")
        x = self.corpus()
        self.assertNotEqual(before, x["snapshot"])
        rows = candidates(x, "液态镜头参数")
        self.assertEqual(rows[0]["key"], "sources/新文章.md")
        r = make_review(x, "检查液态镜头", ["液态镜头参数"])
        self.assertEqual(r["documents"][r["evidence"][0]["document_id"]]["source_status"], "未沉淀")
        self.assertFalse(r["facets"][0]["source_gap"])

    def test_preserves_facets_including_gap(self):
        r = make_review(self.corpus(), "审查", ["服装状态链", "锂电池电解液配方"])
        self.assertEqual(len(r["facets"]), 2)
        self.assertEqual(r["facets"][1]["status"], "gap")
        self.assertEqual(r["coverage_status"], "awaiting_application_review")

    def test_no_role_only_match(self):
        r = make_review(self.corpus(), "审查", ["星系坐标超算"], role="C", stage="视觉设计")
        self.assertEqual(r["facets"][0]["evidence_ids"], [])

    def test_context_cannot_overwrite_question(self):
        x = self.corpus()
        self.assertEqual(candidates(x, "星系坐标超算", role="C", context_hint="服装状态链"), [])

    def test_whole_block_and_line_locations(self):
        x = self.corpus()
        for d in x["documents"].values():
            lines = (self.vault / d["path"]).read_text(encoding="utf-8").splitlines()
            for b in d["blocks"]:
                self.assertEqual(b["text"], "\n".join(lines[b["line_start"]-1:b["line_end"]]))
        rows = [b for b in x["documents"]["sources/服装研究.md"]["blocks"] if b["references"] and not b.get("routing_only")]
        self.assertEqual(len(rows), 2)
        self.assertIn("仅案例", rows[0]["references"][0]["limits"])
        self.assertEqual(rows[0]["references"][0]["verification"], "local_record_only")

    def test_fences_and_skipped_heading_levels(self):
        ticks = chr(96) * 3
        text = "# T\n\n## 复习区\n\n#### 自测问题\n不应索引\n\n## 方法\n\n" + ticks + "\n## not a heading\n" + ticks + "\n例外不能省略。\n"
        blocks = section_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertIn("## not a heading", blocks[0]["text"])

    def test_budget_never_truncates_boundary(self):
        self.source.write_text(note("液态镜头", "## 核心观点\n" + "液态镜头的条件。" * 800 +
                                   "但有毒材料不适用。\n", "材料总览"), encoding="utf-8")
        x = self.corpus()
        r = make_review(x, "审查", ["液态镜头"], budget=2500)
        item = next(e for e in r["evidence"] if r["documents"][e["document_id"]]["title"] == "液态镜头")
        self.assertTrue(item["read_required"])
        self.assertEqual(item["excerpt"], "")
        full = full_evidence(x, item["id"])
        self.assertIn("但有毒材料不适用", full["excerpt"])

    def test_same_stat_change_invalidates_evidence(self):
        x = self.corpus(cache=True)
        eid = x["documents"]["sources/服装研究.md"]["blocks"][0]["id"]
        stat = self.source.stat()
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("剧情时间", "真实年代"), encoding="utf-8")
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(self.source.stat().st_size, stat.st_size)
        new = self.corpus()
        self.assertNotEqual(new["snapshot"], x["snapshot"])
        with self.assertRaises(ValueError):
            full_evidence(new, eid)

    def test_cache_injection_not_used(self):
        x = self.corpus(cache=True)
        p = self.cache / "knowledge-retrieval/evidence-index-v1.json"
        forged = dict(x)
        forged["documents"] = {"outside": {"text": "forged evidence"}}
        p.write_text(json.dumps(forged), encoding="utf-8")
        fresh = self.corpus()
        self.assertNotIn("outside", fresh["documents"])
        self.assertEqual(fresh, x)

    def test_followup_changes_deletions_renames(self):
        old = self.corpus()
        renamed = self.sources / "改名.md"
        self.source.rename(renamed)
        new = self.corpus()
        r = followup(new, snapshot_state(old))
        self.assertEqual(r["changes"]["renamed"], [{"from":"sources/服装研究.md", "to":"sources/改名.md"}])
        self.assertIn("library/连续性.md", r["affected_topics"])
        self.assertTrue(r["previous_review_packs_stale"])

    def test_revocation_excluded_but_reported(self):
        old = self.corpus()
        eid = old["documents"]["sources/服装研究.md"]["blocks"][0]["id"]
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("类型: 材料总览", "类型: 材料总览\n状态: 撤回"), encoding="utf-8")
        new = self.corpus()
        self.assertFalse(candidates(new, "服装", keys=["sources/服装研究.md"]))
        with self.assertRaises(ValueError):
            full_evidence(new, eid)
        self.assertIn("library/连续性.md", followup(new, snapshot_state(old))["affected_topics"])

    def test_checkpoints_do_not_clear_pending(self):
        self.source.write_text(note("服装研究", "## 核心观点\n服装污损可反映剧情变化。", "材料总览"), encoding="utf-8")
        self.topic.unlink()
        first = run_followup(self.config, checkpoint=True)
        second = run_followup(self.config, checkpoint=True)
        self.assertTrue(any(i["kind"] == "source_not_integrated" for i in second["issues"]))
        self.assertEqual(second["changes"]["added"], [])
        self.assertEqual(second["semantic_links_written"], 0)
        self.assertEqual(first["status"], "needs_review")

    def test_invalid_checkpoint_not_replaced(self):
        p = self.cache / "knowledge-retrieval/followup-state-v1.json"
        p.parent.mkdir(parents=True)
        p.write_text("{invalid", encoding="utf-8")
        with self.assertRaises(ValueError):
            run_followup(self.config, checkpoint=True)
        self.assertEqual(p.read_text(), "{invalid")

    def test_duplicate_sources_and_one_way_links(self):
        (self.sources / "duplicate.md").write_bytes(self.source.read_bytes())
        x = self.corpus()
        r = followup(x)
        self.assertEqual(len(r["exact_duplicates"]), 1)
        self.assertTrue(any(i["kind"] == "one_way_source_link" for i in r["issues"]))
        self.assertEqual(r["semantic_links_written"], 0)

    def test_ambiguous_and_explicit_missing_link(self):
        documents = {"sources/a/X.md": {}, "sources/b/X.md": {}}
        self.assertEqual(resolve_link("X", self.topic, documents, self.vault)[1], "ambiguous")
        self.assertEqual(resolve_link("missing/X", self.topic, documents, self.vault)[1], "missing")
        self.assertEqual(resolve_link("C:/secret", self.topic, documents, self.vault)[1], "outside")

    def test_outside_index_not_reported_as_missing(self):
        p = self.vault / "旧项目.md"
        p.write_text("# existing", encoding="utf-8")
        self.assertEqual(resolve_link("旧项目", self.topic, {}, self.vault)[1], "exists_outside_index")

    def test_application_trace_rejects_fake_or_missing(self):
        x = self.corpus()
        r = make_review(x, "审查", ["服装状态链"])
        good = {"checks": [{"facet_id":"Q1", "status":"applied", "project_observation":"外套连续两镜污损相反",
                            "judgment":"需要核对剧情时间", "reason":"按状态链比较",
                            "evidence_ids":r["facets"][0]["evidence_ids"]}],
                "read_evidence_ids": [e["id"] for e in r["evidence"]]}
        self.assertTrue(validate_application(x, r, good)["traceability_pass"])
        self.assertEqual(validate_application(x, r, good)["semantic_quality"], "not_machine_verified")
        bad = copy.deepcopy(good)
        bad["checks"][0]["evidence_ids"] = ["fake-id"]
        self.assertFalse(validate_application(x, r, bad)["traceability_pass"])
        self.assertFalse(validate_application(x, r, {"checks":[]})["all_facets_answered"])
        old = copy.deepcopy(r)
        old["snapshot"] = "old"
        self.assertFalse(validate_application(x, old, good)["traceability_pass"])

    def test_unrelated_source_not_forced_to_connect(self):
        p = self.sources / "远方宇宙.md"
        p.write_text(note("星系坐标", "## 核心观点\n星系坐标与引力透镜。", "材料总览"), encoding="utf-8")
        x = self.corpus()
        r = followup(x, include_candidates=True)
        item = next(c for c in r["comparisons"] if c["source"].endswith("远方宇宙.md"))
        self.assertEqual(item["candidates"], [])
        self.assertEqual(r["semantic_links_written"], 0)

    def test_contradictory_sources_preserved_for_comparison(self):
        p = self.sources / "反例.md"
        p.write_text(note("服装连续性反例", "## 服装颜色条件\n服装颜色随光源变化不应机械锁死。", "材料总览"), encoding="utf-8")
        x = self.corpus()
        rows = candidates(x, "服装颜色", limit=20)
        self.assertIn("sources/反例.md", {r["key"] for r in rows})
        r = followup(x, include_candidates=True)
        self.assertEqual(r["semantic_links_written"], 0)
        self.assertIn("冲突", next(c["decision_needed"] for c in r["comparisons"] if c["source"].endswith("反例.md")))

    def test_historical_missing_dependency_survives_checkpoint(self):
        old = snapshot_state(self.corpus())
        self.source.unlink()
        x = self.corpus()
        new = snapshot_state(x, old)
        self.assertIn("sources/服装研究.md", new["dependencies"]["library/连续性.md"])
        r = followup(x, new)
        self.assertTrue(any(i["kind"] == "broken_link" for i in r["issues"]))

    def test_changed_linked_source_pending_survives_checkpoint(self):
        run_followup(self.config, checkpoint=True)
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("剧情时间", "人物身份"), encoding="utf-8")
        first = run_followup(self.config, checkpoint=True)
        second = run_followup(self.config, checkpoint=True)
        self.assertIn("library/连续性.md", first["affected_topics"])
        self.assertIn("library/连续性.md", second["affected_topics"])
        with self.assertRaises(ValueError):
            run_followup(self.config, checkpoint=True, reviewed_topics=["library/连续性.md"], expected_snapshot="old", review_reason="已读")
        run_followup(self.config, checkpoint=True, reviewed_topics=["library/连续性.md"],
                     expected_snapshot=second["snapshot"], review_reason="已比较新来源，旧主题方法仍适用")
        self.assertEqual(run_followup(self.config)["affected_topics"], [])

    def test_review_does_not_claim_to_cover_unstated_dimensions(self):
        r = make_review(self.corpus(), "整个剧本全部审查", [])
        self.assertFalse(r["checklist_explicit"])
        self.assertEqual(r["checklist_scope"], "caller_defined_not_automatically_exhaustive")


if __name__ == "__main__":
    unittest.main()
