"""Identity scanning, declared transitive provenance and scope isolation."""
from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_dependencies import load_dependency_catalog, calculate_dependency_impact
from knowledge_followup import run_followup


def note(kind, fields="", body="正文。"):
    return f"---\n类型: {kind}\n状态: 已整理\n{fields}\n---\n# 正式笔记\n\n{body}\n"


class DependencyPropagationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dependency-propagation-")
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.library = self.vault / "knowledge"
        self.learning = self.library / "learning"
        self.creation = self.library / "creation"
        self.cache = self.root / "raw-cache"
        self.evidence = self.root / "evidence"
        for path in (self.learning, self.creation, self.cache, self.evidence):
            path.mkdir(parents=True)
        self.config = {"workspace": str(self.root), "vault": str(self.vault),
                       "knowledge_library": str(self.library), "source_notes": str(self.learning),
                       "learning_root": str(self.learning), "creation_root": str(self.creation),
                       "raw_cache": str(self.cache), "source_evidence": str(self.evidence)}
        self.source = self.learning / "原课.md"
        self.summary = self.learning / "综合稿.md"
        self.topic = self.creation / "方法.md"
        self.application = self.creation / "项目应用.md"
        self.source.write_text(note("分集笔记", body="未点名学习正文秘密标记。"), encoding="utf-8")
        self.summary.write_text(note("主题笔记", '来源材料: ["[[knowledge/learning/原课]]"]'), encoding="utf-8")
        self.topic.write_text(note("主题笔记", '派生自: "[[knowledge/learning/综合稿]]"', body="## 方法\n根据条件判断。"), encoding="utf-8")
        self.application.write_text(note("项目应用", '调用知识: ["[[knowledge/creation/方法]]"]'), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def catalog(self):
        return load_dependency_catalog(self.config)

    def previous(self, catalog=None, pending=()):
        catalog = catalog or self.catalog()
        return {"version": 2, "vault": str(self.vault), "files": {k: n["hash"] for k, n in catalog["nodes"].items()},
                "dependencies": {}, "dependency_catalog": catalog, "pending_dependency_reviews": list(pending)}

    def test_multilayer_reaches_theme_and_project_application(self):
        previous = self.previous()
        self.source.write_text(self.source.read_text(encoding="utf-8") + "来源新增条件。", encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["affected_applications"], ["knowledge/creation/项目应用.md"])
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])
        application = next(item for item in impact["pending_reviews"] if item["kind"] == "application")
        self.assertEqual(application["chain"], ["knowledge/learning/原课.md", "knowledge/learning/综合稿.md", "knowledge/creation/方法.md", "knowledge/creation/项目应用.md"])
        self.assertTrue(all(row["source_binding"] == "unresolved" for row in impact["affected_methods"]))

    def test_added_source_resolves_existing_declaration_and_propagates(self):
        source_bytes = self.source.read_bytes()
        self.source.unlink()
        previous = self.previous()
        self.assertTrue(any(item["reason"] == "missing" for item in previous["dependency_catalog"]["unresolved"]))
        protected = {path: path.read_bytes() for path in (self.summary, self.topic, self.application)}
        self.source.write_bytes(source_bytes)
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["changes"]["added"], ["knowledge/learning/原课.md"])
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])
        self.assertEqual(impact["affected_applications"], ["knowledge/creation/项目应用.md"])
        application = next(item for item in impact["pending_reviews"] if item["target"] == "knowledge/creation/项目应用.md")
        self.assertEqual(application["chain"], ["knowledge/learning/原课.md", "knowledge/learning/综合稿.md",
                                                "knowledge/creation/方法.md", "knowledge/creation/项目应用.md"])
        self.assertTrue(all(item["status"] == "pending_content_review" for item in impact["pending_reviews"]))
        self.assertTrue(all(item["source_binding"] == "unresolved" for item in impact["affected_methods"]))
        self.assertTrue(all(path.read_bytes() == original for path, original in protected.items()))

    def test_unrelated_added_source_does_not_invalidate_every_topic(self):
        previous = self.previous()
        (self.learning / "无关来源.md").write_text(note("来源笔记"), encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["changes"]["added"], ["knowledge/learning/无关来源.md"])
        self.assertEqual(impact["changes"]["dependency_edges_added"], [])
        self.assertEqual(impact["affected_topics"], [])
        self.assertEqual(impact["affected_applications"], [])
        self.assertEqual(impact["pending_reviews"], [])

    def test_new_edge_reviews_dependent_itself_without_invalidating_siblings(self):
        self.topic.write_text(note("主题笔记", body="尚未声明来源。"), encoding="utf-8")
        previous = self.previous()
        self.topic.write_text(note("主题笔记", '派生自: "[[knowledge/learning/原课]]"', body="尚未声明来源。"), encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])
        self.assertNotIn("knowledge/learning/综合稿.md", impact["affected_topics"])
        review = next(item for item in impact["pending_reviews"] if item["target"] == "knowledge/creation/方法.md")
        self.assertEqual(review["trigger_reason"], "declared_dependency_added")
        self.assertEqual(review["chain"], ["knowledge/learning/原课.md", "knowledge/creation/方法.md"])
        self.assertIn("knowledge/creation/项目应用.md", impact["affected_applications"])
        self.assertFalse(impact["knowledge_modified"])

    def test_ambiguous_declaration_becomes_resolved_without_dependent_byte_change(self):
        course_directory = self.learning / "课程"
        course_directory.mkdir()
        moved_source = course_directory / self.source.name
        self.source.rename(moved_source)
        self.source = moved_source
        duplicate = self.creation / "原课.md"
        duplicate.write_text(note("分集笔记", body="同名另来源。"), encoding="utf-8")
        self.summary.write_text(note("主题笔记", '来源材料: ["[[原课]]"]'), encoding="utf-8")
        previous = self.previous()
        self.assertTrue(any(item["reason"] == "ambiguous" for item in previous["dependency_catalog"]["unresolved"]))
        summary_bytes = self.summary.read_bytes()
        duplicate.unlink()
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["changes"]["added"], [])
        self.assertEqual(impact["changes"]["modified"], [])
        self.assertTrue(any(edge["dependent"] == "knowledge/learning/综合稿.md"
                            for edge in impact["changes"]["dependency_edges_added"]))
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])
        self.assertIn("knowledge/creation/项目应用.md", impact["affected_applications"])
        self.assertEqual(self.summary.read_bytes(), summary_bytes)
        current = self.catalog()
        repeated = calculate_dependency_impact(current, self.previous(current, impact["pending_reviews"]))
        self.assertEqual(repeated["pending_reviews"], impact["pending_reviews"])

    def test_saved_empty_catalog_is_a_baseline_but_initial_inventory_is_not(self):
        current = self.catalog()
        first = calculate_dependency_impact(current)
        self.assertTrue(first["baseline_missing"])
        self.assertEqual(first["changes"]["added"], [])
        self.assertEqual(first["changes"]["dependency_edges_added"], [])
        empty_catalog = dict(current, nodes={}, edges=[], unresolved=[])
        previous = self.previous(empty_catalog)
        impact = calculate_dependency_impact(current, previous)
        self.assertFalse(impact["baseline_missing"])
        self.assertEqual(set(impact["changes"]["added"]), set(current["nodes"]))
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])

    def test_learning_body_not_decoded_even_if_invalid_utf8(self):
        self.source.write_bytes(b"---\n" + "类型: 分集笔记\n".encode() + b"---\n\xff\xfe forbidden body")
        catalog = self.catalog()
        self.assertEqual(catalog["errors"], [])
        self.assertNotIn("blocks", catalog["nodes"]["knowledge/learning/原课.md"])
        self.assertFalse(catalog["body_read_permission"])

    def test_zoned_default_body_scope_stays_creative(self):
        report = run_followup(self.config, suggest=True)
        self.assertEqual(report["body_scope"]["paths"], ["knowledge/creation"])
        self.assertFalse(any(row["source"].startswith("knowledge/learning/") for row in report["comparisons"]))
        self.assertFalse(report["identity_scope"]["body_read_permission"])
        self.assertIn("knowledge/learning/原课.md", self.catalog()["nodes"])
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_explicit_include_only_opens_named_learning_file(self):
        report = run_followup(self.config, include_paths=["knowledge/learning/原课.md"], suggest=True)
        self.assertEqual(report["body_scope"]["include_paths"], ["knowledge/learning/原课.md"])
        self.assertNotIn("knowledge/learning/综合稿.md", report["body_scope"]["paths"])
        self.assertTrue(any(row["source"] == "knowledge/learning/原课.md" for row in report["comparisons"]))

    def test_identity_only_never_calls_content_loader_or_candidates(self):
        with patch("knowledge_followup.load_corpus", side_effect=AssertionError("body loader called")), \
             patch("knowledge_followup.candidates", side_effect=AssertionError("scoring called")):
            report = run_followup(self.config, identity_only=True)
        self.assertFalse(report["checkpoint_saved"])
        with self.assertRaises(ValueError):
            run_followup(self.config, identity_only=True, checkpoint=True)

    def test_navigation_never_builds_dependency(self):
        route = self.creation / "地图.md"
        route.write_text(note("来源地图", '来源材料: ["[[knowledge/learning/原课]]"]', body="[[knowledge/learning/原课]]"), encoding="utf-8")
        self.topic.write_text(note("主题笔记", body="导航 [[knowledge/learning/原课]]"), encoding="utf-8")
        catalog = self.catalog()
        self.assertFalse(any(edge["dependent"] in {"knowledge/creation/地图.md", "knowledge/creation/方法.md"} for edge in catalog["edges"]))

    def test_cycles_are_finite_and_do_not_create_mutual_evidence(self):
        self.source.write_text(note("分集笔记", '来源材料: ["[[knowledge/learning/综合稿]]"]'), encoding="utf-8")
        previous = self.previous()
        self.source.write_text(self.source.read_text(encoding="utf-8") + "变化", encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["cycle_nodes"], ["knowledge/learning/原课.md", "knowledge/learning/综合稿.md"])
        self.assertLessEqual(len(impact["pending_reviews"]), 4)
        self.assertFalse(impact["knowledge_modified"])

    def test_deletion_propagates_historical_chain_and_pending_persists(self):
        previous = self.previous()
        self.source.unlink()
        catalog = self.catalog()
        impact = calculate_dependency_impact(catalog, previous)
        self.assertIn("knowledge/creation/项目应用.md", impact["affected_applications"])
        again = calculate_dependency_impact(catalog, self.previous(catalog, impact["pending_reviews"]))
        self.assertEqual(again["pending_reviews"], impact["pending_reviews"])

    def test_removed_declaration_not_accumulated_as_active_graph(self):
        previous = self.previous()
        self.topic.write_text(note("主题笔记", body="移除来源声明。"), encoding="utf-8")
        catalog = self.catalog()
        self.assertFalse(any(edge["dependent"] == "knowledge/creation/方法.md" for edge in catalog["edges"]))
        current = self.previous(catalog)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "新变化", encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), current)
        self.assertNotIn("knowledge/creation/方法.md", impact["affected_topics"])

    def test_unique_rename_only_reports_candidate_without_rebinding(self):
        previous = self.previous()
        renamed = self.learning / "改名课.md"
        self.source.rename(renamed)
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["changes"]["renamed"][0]["status"], "identity_candidate_not_rebound")
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])
        self.assertIn("原课", self.summary.read_text(encoding="utf-8"))

    def test_ambiguous_rename_stays_unresolved(self):
        previous = self.previous()
        data = self.source.read_bytes()
        self.source.unlink()
        for name in ("新一.md", "新二.md"):
            (self.learning / name).write_bytes(data)
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["changes"]["renamed"], [])
        self.assertEqual(len(impact["changes"]["ambiguous_renames"]), 1)

    def test_revocation_propagates_but_never_changes_application(self):
        previous = self.previous()
        original = self.application.read_bytes()
        self.source.write_text(note("分集笔记").replace("已整理", "已撤回"), encoding="utf-8")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertIn("knowledge/learning/原课.md", impact["revoked"])
        self.assertIn("knowledge/creation/项目应用.md", impact["affected_applications"])
        self.assertEqual(self.application.read_bytes(), original)

    def evidence_record(self, hint="raw-cache/source.txt"):
        target = self.evidence / "sample"
        target.mkdir()
        raw = self.cache / "source.txt"
        raw.write_bytes(b"acquired original source")
        record = {"schema": "source-evidence-v1", "source_id": "sample-source", "source": {
            "kind": "book", "local_text_hint": hint, "text_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()},
            "note": {"path": "knowledge/learning/原课.md", "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest()}}
        (target / "record.json").write_text(json.dumps(record), encoding="utf-8")
        return raw

    def test_missing_original_marks_history_unverifiable_and_propagates(self):
        raw = self.evidence_record()
        previous = self.previous()
        raw.unlink()
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertEqual(impact["unavailable_source_inputs"], ["evidence:sample-source"])
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])

    def test_input_hash_change_detected_even_when_record_unchanged(self):
        raw = self.evidence_record()
        previous = self.previous()
        raw.write_bytes(b"wrong source under same name")
        impact = calculate_dependency_impact(self.catalog(), previous)
        self.assertIn("evidence:sample-source", impact["changes"]["modified"])
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])

    def test_note_binding_mismatch_is_not_recognized_as_fresh_review(self):
        self.evidence_record()
        self.source.write_text(self.source.read_text(encoding="utf-8") + "正文已经改变而证据未续核。", encoding="utf-8")
        catalog = self.catalog()
        self.assertEqual(catalog["nodes"]["evidence:sample-source"]["note_binding_status"], "hash_mismatch")
        impact = calculate_dependency_impact(catalog)
        self.assertIn("knowledge/creation/方法.md", impact["affected_topics"])

    def test_original_outside_cache_not_opened(self):
        self.evidence_record("outside.txt")
        external = self.root / "outside.txt"
        external.write_bytes(b"private external source")
        catalog = self.catalog()
        self.assertTrue(any(item["reason"] == "outside_configured_raw_cache" for item in catalog["errors"]))
        self.assertIsNone(catalog["nodes"]["evidence:sample-source"]["inputs"][0]["actual_hash"])

    def test_v1_checkpoint_upgrade_keeps_pending_and_global_learning_presence(self):
        catalog = self.catalog()
        state = {"version": 1, "vault": str(self.vault), "snapshot": "old", "files": {
            key: node["hash"] for key, node in catalog["nodes"].items()}, "dependencies": {},
            "pending_topic_reviews": ["knowledge/creation/旧待核.md"]}
        checkpoint = self.cache / "knowledge-retrieval/followup-state-v1.json"
        checkpoint.parent.mkdir()
        checkpoint.write_text(json.dumps(state), encoding="utf-8")
        report = run_followup(self.config, checkpoint=True)
        self.assertEqual(report["changes"]["removed"], [])
        upgraded = json.loads(checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(upgraded["version"], 2)
        self.assertIn("knowledge/creation/旧待核.md", upgraded["pending_topic_reviews"])
        self.assertIn("knowledge/learning/原课.md", upgraded["dependency_catalog"]["nodes"])

    def test_config_root_escape_rejected(self):
        config = dict(self.config, source_notes=str(self.root))
        with self.assertRaises(ValueError):
            load_dependency_catalog(config)

    def test_configured_prompt_box_identity_is_tracked_without_body_scope(self):
        prompt_box = self.vault / "prompt-box.md"
        prompt_box.write_text(note("提示词盒"), encoding="utf-8")
        self.summary.write_text(note("主题笔记", '来源材料: ["[[prompt-box]]"]'), encoding="utf-8")
        self.config["prompt_box"] = str(prompt_box)
        catalog = self.catalog()
        self.assertIn("prompt-box.md", catalog["nodes"])
        self.assertTrue(any(edge["dependency"] == "prompt-box.md" for edge in catalog["edges"]))
        report = run_followup(self.config)
        self.assertEqual(report["body_scope"]["paths"], ["knowledge/creation"])


if __name__ == "__main__":
    unittest.main()
