from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import record_application as recorder
from record_application import NativeVerifier, apply_plan, build_plan, load_topic_methods, plan_summary


def topic_text(title: str) -> str:
    return f"""---
类型: 主题笔记
分类: 故事与剧本
状态: 持续积累
材料类型: 主题沉淀
信息来源: 隔离测试夹具
完整程度: 已整理
整理日期: 2026-10-03
知识库版本: 2.1
主题域: 人物
来源材料: []
关联项目: []
解决问题: 测试 {title}
适用阶段: [故事骨架]
知识状态: 已提炼
成熟度: 种子
上位主题: []
相关主题: []
最后复核: 2026-10-03
证据状态: 单一来源
掌握状态: 未检验
最近检验:
---

# {title}

## 核心命题
人物行动需要具体处境。
## 适用边界
不能只按观众偏好判断人物是否可信。
## 学习材料
隔离夹具，无外部事实认证。
## 内容导览
从处境到选择。
## 知识单元
选择需要面对具体阻力。
## 外部补充与分歧
暂无。
## 项目应用与验证

| 项目 | 阶段与问题 | 本次调用 | 结果 | 回写 |
|---|---|---|---|---|
|  |  |  | 待验证 |  |
"""


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class RecordApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.creation = self.library / "创作区"
        self.story = self.creation / "B-故事与剧本"
        self.sources = self.library / "学习区"
        self.cache = self.root / "cache"
        for directory in (self.story, self.sources, self.cache, self.vault / ".obsidian", self.root / "skills"):
            directory.mkdir(parents=True, exist_ok=True)
        self.prompt_box = self.vault / "prompt-box.md"
        self.executable = self.root / "Obsidian.com"
        self.prompt_box.write_text("# prompts\n", encoding="utf-8")
        self.executable.write_text("never execute this registry/CLI double", encoding="utf-8")
        self.topic_a = self.story / "主题甲.md"
        self.topic_b = self.story / "主题乙.md"
        self.topic_a.write_text(topic_text("主题甲"), encoding="utf-8")
        self.topic_b.write_text(topic_text("主题乙"), encoding="utf-8")
        self.config = self.root / "knowledge-tree.json"
        self.config.write_text(json.dumps({
            "version": 2, "workspace": ".", "vault": "vault", "vault_name": "vault",
            "knowledge_library": "vault/library", "source_notes": "vault/library/学习区",
            "learning_root": "vault/library/学习区", "creation_root": "vault/library/创作区",
            "raw_cache": "cache", "prompt_box": "vault/prompt-box.md",
            "obsidian_cli": "Obsidian.com", "skills_root": "skills",
        }, ensure_ascii=False), encoding="utf-8")
        self.registry = self.root / "registry.json"
        self.reset_registry()

    def reset_registry(self):
        self.registry.write_text(json.dumps({"vaults": {"fixture": {"path": str(self.vault)}}}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def make_plan(self, topics=None, status="有效", observable=True, **overrides):
        inputs = dict(config_path=self.config, project="测试短片", problem="人物转变不可信",
                      stage="故事骨架", topic_names=topics or ["主题甲"], method="检查选择与后果",
                      action="把结尾宣言改成两次有代价的选择", result="夹具试读者能复述人物为何改变",
                      conditions="同一剧本版本、三名夹具试读者；不代表真实项目结果",
                      status=status, observable=observable, record_date="2026-10-03", record_key="")
        inputs.update(overrides)
        return build_plan(**inputs)

    def native(self, plan):
        verifier = NativeVerifier(plan.config)
        verifier.cli.registry_path = self.registry
        return verifier

    def execute(self, arguments, timeout=15):
        from obsidian_cli import CliResult
        if arguments == ["vault", "info=path"]:
            return CliResult(0, str(self.vault))
        if arguments[0] == "eval":
            relative = json.loads(re.search(r"const p=(.*?);const f", arguments[1]).group(1))
            path = self.vault / relative
            if not path.exists():
                return CliResult(1, stderr="fixture target missing")
            return CliResult(0, "=> " + json.dumps({"path": relative, "text": path.read_bytes().decode("utf-8-sig")}, ensure_ascii=False))
        self.fail(f"unexpected CLI double request: {arguments}")

    def commit(self, plan, **kwargs):
        native = kwargs.pop("native", self.native(plan))
        with patch.object(native.cli, "_execute", side_effect=self.execute):
            return apply_plan(plan, plan.plan_id, native=native, **kwargs)

    def hashes(self, plan):
        return {path: digest(path) for path in plan.changes}

    def test_preview_does_not_write_and_shows_exact_diffs(self):
        before = digest(self.topic_a)
        plan = self.make_plan()
        summary = plan_summary(plan)
        self.assertEqual("preview", summary["mode"])
        self.assertEqual(before, digest(self.topic_a))
        self.assertFalse(plan.application_path.exists())
        self.assertEqual(plan.plan_id, summary["plan_id"])
        self.assertIn("检查选择与后果", "\n".join(item["unified_diff"] for item in summary["diffs"]))
        self.assertTrue(all("before_hash" in item and "after_hash" in item for item in summary["diffs"]))

    def test_metadata_discovery_leaves_unselected_bodies_unread_and_target_bytes_read_once(self):
        source = self.sources / "未选来源.md"
        learning = self.sources / "未选学习主题.md"
        source.write_bytes("---\n类型: 来源笔记\n---\n".encode("utf-8") + b"\xff unread source body")
        learning.write_bytes("---\n类型: 主题笔记\n---\n# 学习目录标题\n".encode("utf-8") + b"\xff unread topic body")
        counts = {}
        reader = Path.read_bytes
        def read(path):
            counts[path] = counts.get(path, 0) + 1
            if path in (source, learning):
                self.fail("unselected body read through read_bytes")
            return reader(path)
        with patch.object(Path, "read_bytes", read):
            plan = self.make_plan()
        self.assertEqual(1, counts[self.topic_a])
        self.assertNotIn(self.topic_b, counts)
        self.assertIn(self.topic_a, plan.changes)

    def test_exact_path_avoids_unselected_directory_discovery(self):
        selected = self.topic_a.relative_to(self.vault).as_posix()
        metadata = recorder.discover_metadata
        visited = []
        def discover(path, **kwargs):
            visited.append(path)
            return metadata(path, **kwargs)
        with patch.object(recorder, "discover_metadata", side_effect=discover):
            self.make_plan(topics=[selected])
        self.assertEqual([self.topic_a], visited)

    def test_writeback_is_bidirectional_and_idempotent(self):
        first = self.commit(self.make_plan())
        app_path = Path(first["application_path"])
        app_after = app_path.read_text(encoding="utf-8")
        self.assertIn("检查选择与后果", app_after)
        self.assertNotIn("待在实际记录中说明", app_after)
        self.assertIn("[[library/创作区/B-故事与剧本/主题甲]]", app_after)
        topic_after = self.topic_a.read_text(encoding="utf-8")
        self.assertIn("[[library/创作区/岗位共用/项目经验/项目应用/", topic_after)
        self.assertIn("证据状态: 单一来源", topic_after)
        self.assertFalse(first["evidence_status_changed"])
        hashes = {self.topic_a: digest(self.topic_a), app_path: digest(app_path)}
        second = self.commit(self.make_plan())
        self.assertEqual(0, second["changed_count"])
        self.assertEqual(hashes, {path: digest(path) for path in hashes})
        marker = f"apply-film-knowledge:{second['application_id']}:BEGIN"
        self.assertEqual(1, self.topic_a.read_text(encoding="utf-8").count(marker))

    def test_distinct_methods_and_reason_are_saved_to_correct_topics(self):
        key = self.topic_b.relative_to(self.vault).as_posix()
        plan = self.make_plan(topics=["主题甲", "主题乙"], topic_methods={key: {"method": "区分观察与原因", "reason": "结果不能直接证明成因"}})
        self.commit(plan)
        app = plan.application_path.read_text(encoding="utf-8")
        for text in ("检查选择与后果", "区分观察与原因", "结果不能直接证明成因"):
            self.assertIn(text, app)
        self.assertNotIn("区分观察与原因", self.topic_a.read_text(encoding="utf-8"))
        self.assertIn("区分观察与原因", self.topic_b.read_text(encoding="utf-8"))

    def test_literal_method_characters_are_safe(self):
        method = "检查 A|B\n路径 C:\\shots\\1 与 \\g<1>"
        plan = self.make_plan(method=method)
        self.commit(plan)
        self.commit(self.make_plan(method=method))
        for path in (self.topic_a, plan.application_path):
            text = path.read_text(encoding="utf-8")
            self.assertIn("A&#124;B<br>", text)
            self.assertIn("C:\\shots\\1", text)
            self.assertIn("\\g<1>", text)

    def test_non_pending_status_requires_observable_result(self):
        with self.assertRaisesRegex(ValueError, "可观察结果"):
            self.make_plan(status="有效", observable=False)

    def test_plan_id_missing_mismatched_or_changed_refuses_all_writes(self):
        for expected in (None, "wrong"):
            plan = self.make_plan()
            before = self.hashes(plan)
            with self.assertRaisesRegex(ValueError, "expected-plan-id"):
                apply_plan(plan, expected)
            self.assertEqual(before, self.hashes(plan))
        plan.changes[self.topic_a] += "\nnew candidate\n"
        with self.assertRaisesRegex(ValueError, "身份"):
            apply_plan(plan, plan.plan_id)
        self.assertFalse(plan.application_path.exists())

    def test_prewrite_concurrent_change_is_preserved(self):
        plan = self.make_plan()
        self.topic_a.write_bytes(self.topic_a.read_bytes() + b"\nexternal edit\n")
        changed = digest(self.topic_a)
        with self.assertRaisesRegex(RuntimeError, "并发"):
            self.commit(plan)
        self.assertEqual(changed, digest(self.topic_a))
        self.assertFalse(plan.application_path.exists())

    def test_concurrent_change_between_files_rolls_back_only_our_edits(self):
        plan = self.make_plan(topics=["主题甲", "主题乙"])
        before = self.hashes(plan)
        writer = recorder.write_atomic
        first = min((self.topic_a, self.topic_b), key=lambda path: str(path).casefold())
        later = self.topic_b if first == self.topic_a else self.topic_a
        count = 0
        def change_later(path, text):
            nonlocal count
            writer(path, text)
            count += 1
            if count == 1:
                later.write_bytes(later.read_bytes() + b"\nexternal later\n")
        with patch.object(recorder, "write_atomic", side_effect=change_later):
            with self.assertRaisesRegex(RuntimeError, "外部并发内容未覆盖"):
                self.commit(plan)
        self.assertEqual(before[first], digest(first))
        self.assertIn(b"external later", later.read_bytes())
        self.assertFalse(plan.application_path.exists())

    def test_concurrent_edit_to_written_file_is_not_overwritten_by_rollback(self):
        plan = self.make_plan(topics=["主题甲", "主题乙"])
        native = self.native(plan)
        calls = 0
        edited = []
        original_verify = native.verify_note
        def verify_and_edit(path, text):
            nonlocal calls
            original_verify(path, text)
            calls += 1
            if calls == 1:
                path.write_bytes(path.read_bytes() + b"\nexternal saved\n")
                edited.append(path)
            if calls == 2:
                raise RuntimeError("injected later native failure")
        with patch.object(native, "verify_note", side_effect=verify_and_edit):
            with self.assertRaisesRegex(RuntimeError, "外部并发内容未覆盖"):
                self.commit(plan, native=native)
        self.assertIn(b"external saved", edited[0].read_bytes())
        other = self.topic_b if edited[0] == self.topic_a else self.topic_a
        self.assertEqual(plan.before_hashes[other], digest(other))

    def test_multi_file_failure_restores_exact_hashes(self):
        plan = self.make_plan(topics=["主题甲", "主题乙"])
        before = self.hashes(plan)
        with self.assertRaisesRegex(RuntimeError, "全部文件已恢复"):
            self.commit(plan, fail_after=2)
        self.assertEqual(before, self.hashes(plan))

    def test_native_failure_after_new_application_restores_all_and_removes_new_file(self):
        plan = self.make_plan()
        before = self.hashes(plan)
        native = self.native(plan)
        original_verify = native.verify_note
        def verify(path, text):
            original_verify(path, text)
            if path == plan.application_path:
                raise RuntimeError("native fixture mismatch")
        with patch.object(native, "verify_note", side_effect=verify):
            with self.assertRaisesRegex(RuntimeError, "全部文件已恢复"):
                self.commit(plan, native=native)
        self.assertEqual(before, self.hashes(plan))
        self.assertFalse(plan.application_path.exists())

    def test_postwrite_validation_failure_rolls_back(self):
        plan = self.make_plan()
        before = self.hashes(plan)
        validator = recorder.validate_text
        calls = 0
        def validate(text, path=None):
            nonlocal calls
            calls += 1
            return ["injected postwrite validation failure"] if calls > len(plan.changes) else validator(text, path)
        with patch.object(recorder, "validate_text", side_effect=validate):
            with self.assertRaisesRegex(RuntimeError, "全部文件已恢复"):
                self.commit(plan)
        self.assertEqual(before, self.hashes(plan))

    def test_invalid_candidate_stops_before_plan_or_writes(self):
        self.topic_a.write_text(topic_text("主题甲").replace("## 核心命题", "## 缺失核心"), encoding="utf-8")
        before = digest(self.topic_a)
        with self.assertRaisesRegex(ValueError, "候选笔记校验失败"):
            self.make_plan()
        self.assertEqual(before, digest(self.topic_a))

    def test_outside_managed_content_unknown_yaml_bom_and_crlf_are_preserved(self):
        plan = self.make_plan()
        self.commit(plan)
        app = plan.application_path.read_text(encoding="utf-8")
        app = app.replace("应用记录ID:", "个人标签: 我保留的属性\n个人多行: |\n  原话一\n  原话二\n应用记录ID:")
        begin = f"<!-- apply-film-knowledge:{plan.application_id}:BEGIN -->"
        app = app.replace(begin, "我在受管块之前的原话。\n\n" + begin)
        app += "\n我在受管块之后的原话。\n"
        plan.application_path.write_bytes(b"\xef\xbb\xbf" + app.replace("\n", "\r\n").encode("utf-8"))
        self.topic_a.write_bytes(b"\xef\xbb\xbf" + self.topic_a.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        revised = self.make_plan(method="更新的方法")
        self.commit(revised)
        raw = revised.application_path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("个人标签: 我保留的属性\r\n个人多行: |\r\n  原话一\r\n  原话二\r\n".encode("utf-8"), raw)
        self.assertIn("我在受管块之前的原话。\r\n\r\n".encode("utf-8"), raw)
        self.assertTrue(raw.endswith("我在受管块之后的原话。\r\n".encode("utf-8")))
        self.assertTrue(self.topic_a.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(0, self.commit(self.make_plan(method="更新的方法"))["changed_count"])

    def test_record_key_keeps_existing_file_when_problem_changes(self):
        plan = self.make_plan(record_key="stable-fixture")
        self.commit(plan)
        next_plan = self.make_plan(record_key="stable-fixture", problem="更新后的具体问题")
        self.assertEqual(plan.application_path, next_plan.application_path)
        self.commit(next_plan)
        self.assertIn("更新后的具体问题", plan.application_path.read_text(encoding="utf-8"))

    def test_record_key_topic_set_change_refuses_without_removing_old_backlinks(self):
        plan = self.make_plan(record_key="stable-topic-set")
        self.commit(plan)
        for path in (self.topic_a, plan.application_path):
            path.write_bytes(path.read_bytes() + "\n个人原话补充：保留当前内容。\n".encode("utf-8"))
        paths = (self.topic_a, self.topic_b, plan.application_path)
        before = {path: path.read_bytes() for path in paths}
        with self.assertRaisesRegex(ValueError, "目标集合.*旧回链移除范围须显式采用"):
            self.make_plan(topics=["主题乙"], record_key="stable-topic-set")
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertIn(plan.application_id, self.topic_a.read_text(encoding="utf-8"))
        self.assertNotIn(plan.application_id, self.topic_b.read_text(encoding="utf-8"))

    def test_damaged_duplicate_or_nested_markers_block(self):
        plan = self.make_plan()
        self.commit(plan)
        base = self.topic_a.read_text(encoding="utf-8")
        begin = f"<!-- apply-film-knowledge:{plan.application_id}:BEGIN -->"
        end = f"<!-- apply-film-knowledge:{plan.application_id}:END -->"
        variants = (base.replace(end, ""), base + begin + end,
                    base.replace(begin, begin + "<!-- apply-film-knowledge:OTHER:BEGIN -->"))
        for variant in variants:
            self.topic_a.write_text(variant, encoding="utf-8")
            with self.subTest(variant=variant[-80:]), self.assertRaisesRegex(ValueError, "标记"):
                self.make_plan()

    def test_ambiguous_titles_require_exact_path(self):
        duplicate = self.sources / "同名.md"
        duplicate.write_text(topic_text("主题甲"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "歧义"):
            self.make_plan()
        plan = self.make_plan(topics=[self.topic_a.relative_to(self.vault).as_posix()])
        self.assertIn(self.topic_a, plan.changes)
        self.assertNotIn(duplicate, plan.changes)

    def test_unknown_path_empty_method_duplicate_json_keys_and_extra_fields_refused(self):
        key = self.topic_a.relative_to(self.vault).as_posix()
        mappings = ({"../outside.md": {"method": "x"}}, {"主题甲.md": {"method": "x"}},
                    {key: {"method": " "}}, {key: {"method": "x", "unexpected": "x"}},
                    {key: {"method": "x", "reason": 7}})
        for mapping in mappings:
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                self.make_plan(topic_methods=mapping)
        path = self.root / "methods.json"
        path.write_text('{"same":{},"same":{}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "重复键"):
            load_topic_methods(path)

    def test_topic_methods_file_is_supported_by_cli_preview(self):
        path = self.root / "methods.json"
        path.write_text(json.dumps({self.topic_a.relative_to(self.vault).as_posix():
                                  {"method": "逐主题文件中的方法", "reason": "夹具中的适用理由"}}, ensure_ascii=False), encoding="utf-8")
        arguments = ["--config", str(self.config), "--project", "夹具", "--problem", "问题",
                     "--stage", "故事骨架", "--topic", "主题甲", "--method", "默认方法",
                     "--topic-methods-file", str(path), "--action", "尚未执行"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, recorder.main(arguments))
        preview = json.loads(out.getvalue())
        self.assertTrue(all("逐主题文件中的方法" in item["unified_diff"] for item in preview["diffs"]))
        self.assertFalse(any(path.name.startswith("夹具-") for path in self.vault.rglob("*.md")))

    def test_missing_cli_and_wrong_registry_or_cli_target_refuse_writes(self):
        from obsidian_cli import CliResult
        for mode in ("missing", "registry", "cli"):
            plan = self.make_plan()
            before = self.hashes(plan)
            native = self.native(plan)
            if mode == "missing":
                native.cli.executable = None
            if mode == "registry":
                self.registry.write_text(json.dumps({"vaults": {"wrong": {"path": str(self.root / "wrong" / "vault")}}}), encoding="utf-8")
            handler = (lambda arguments, timeout=15: CliResult(0, str(self.root / "other"))) if mode == "cli" else self.execute
            with patch.object(native.cli, "_execute", side_effect=handler):
                with self.assertRaisesRegex(RuntimeError, "身份不可用"):
                    apply_plan(plan, plan.plan_id, native=native)
            self.assertEqual(before, self.hashes(plan))
            self.reset_registry()

    def test_cli_preview_compatibility_and_write_requires_plan_identity(self):
        arguments = ["--config", str(self.config), "--project", "夹具", "--problem", "问题",
                     "--stage", "故事骨架", "--topic", "主题甲", "--method", "具体方法", "--action", "尚未执行"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, recorder.main(arguments))
        preview = json.loads(out.getvalue())
        self.assertEqual("preview", preview["mode"])
        self.assertIn("plan_id", preview)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, recorder.main(arguments + ["--confirm-writeback"]))
        self.assertEqual([], list((self.creation / "岗位共用").rglob("*.md")))


if __name__ == "__main__":
    unittest.main()
