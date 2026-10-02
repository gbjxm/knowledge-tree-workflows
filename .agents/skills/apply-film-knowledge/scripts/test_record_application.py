from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from record_application import apply_plan, build_plan, plan_summary


def topic_text(title: str) -> str:
    return f"""---
类型: 主题笔记
分类: 故事与剧本
解决问题: 测试 {title}
适用阶段: [故事骨架]
证据状态: 单一来源
掌握状态: 未检验
---

# {title}

## 核心命题

测试核心命题。

## 适用边界

- 测试边界。

## 项目应用与验证

| 项目 | 阶段与问题 | 本次调用 | 结果 | 回写 |
|---|---|---|---|---|
|  |  |  | 待验证 |  |
"""


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class RecordApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.story = self.library / "01-故事与剧本"
        self.story.mkdir(parents=True)
        self.sources = self.vault / "sources"
        self.cache = self.root / "cache"
        for directory in (self.sources, self.cache, self.vault / ".obsidian"):
            directory.mkdir(parents=True, exist_ok=True)
        self.prompt_box = self.vault / "prompt-box.md"
        self.executable = self.root / "Obsidian.com"
        self.prompt_box.write_text("# prompts\n", encoding="utf-8")
        self.executable.write_text("stub", encoding="utf-8")
        self.topic_a = self.story / "主题甲.md"
        self.topic_b = self.story / "主题乙.md"
        self.topic_a.write_text(topic_text("主题甲"), encoding="utf-8")
        self.topic_b.write_text(topic_text("主题乙"), encoding="utf-8")
        self.config = self.root / "knowledge-tree.json"
        self.config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "workspace": str(self.root),
                    "vault": str(self.vault),
                    "vault_name": "vault",
                    "knowledge_library": str(self.library),
                    "source_notes": str(self.sources),
                    "raw_cache": str(self.cache),
                    "prompt_box": str(self.prompt_box),
                    "obsidian_cli": str(self.executable),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_plan(self, topics: list[str] | None = None, status: str = "有效", observable: bool = True):
        return build_plan(
            config_path=self.config,
            project="测试短片",
            problem="人物转变不可信",
            stage="故事骨架",
            topic_names=topics or ["主题甲"],
            method="检查选择与后果",
            action="把结尾宣言改成两次有代价的选择",
            result="观众能复述人物为何改变",
            conditions="同一剧本版本、三名试读者",
            status=status,
            observable=observable,
            record_date="2026-07-18",
            record_key="",
        )

    def test_preview_does_not_write(self) -> None:
        before = digest(self.topic_a)
        plan = self.make_plan()
        summary = plan_summary(plan)
        self.assertEqual("preview", summary["mode"])
        self.assertEqual(before, digest(self.topic_a))
        self.assertFalse(plan.application_path.exists())

    def test_writeback_is_bidirectional_and_idempotent(self) -> None:
        first = apply_plan(self.make_plan())
        app_path = Path(first["application_path"])
        self.assertTrue(app_path.exists())
        topic_after = self.topic_a.read_text(encoding="utf-8")
        app_after = app_path.read_text(encoding="utf-8")
        self.assertIn("[[05-创作实践与项目复盘/项目应用/", topic_after)
        self.assertIn("[[01-故事与剧本/主题甲]]", app_after)
        self.assertIn("证据状态: 单一来源", topic_after)
        self.assertFalse(first["evidence_status_changed"])

        hashes = {self.topic_a: digest(self.topic_a), app_path: digest(app_path)}
        second = apply_plan(self.make_plan())
        self.assertEqual(0, second["changed_count"])
        self.assertEqual(hashes[self.topic_a], digest(self.topic_a))
        self.assertEqual(hashes[app_path], digest(app_path))
        marker = f"apply-film-knowledge:{second['application_id']}:BEGIN"
        self.assertEqual(1, self.topic_a.read_text(encoding="utf-8").count(marker))

    def test_non_pending_status_requires_observable_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "可观察结果"):
            self.make_plan(status="有效", observable=False)

    def test_multi_file_failure_restores_hashes(self) -> None:
        plan = self.make_plan(topics=["主题甲", "主题乙"])
        before = {path: digest(path) for path in plan.changes}
        with self.assertRaisesRegex(RuntimeError, "全部文件已恢复"):
            apply_plan(plan, fail_after=1)
        after = {path: digest(path) for path in plan.changes}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
