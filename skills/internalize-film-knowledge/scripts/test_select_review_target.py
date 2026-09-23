from __future__ import annotations

import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from select_review_target import choose


def topic_text(
    title: str,
    category: str,
    mastery: str | None = None,
    review_date: str = "",
    version: str = "2.1",
) -> str:
    mastery_lines = "" if mastery is None else f"掌握状态: {mastery}\n最近检验: {review_date}\n"
    evidence = "证据状态: 单一来源\n" if version == "2.1" else ""
    external = "\n## 外部补充与分歧\n\n- 无\n" if version == "2.1" else ""
    return f"""---
类型: 主题笔记
分类: {category}
状态: 持续积累
材料类型: 主题沉淀
信息来源: 模拟
完整程度: 持续积累
整理日期: 2026-07-10
知识库版本: {version}
主题域: 测试
解决问题: 如何理解{title}
适用阶段: []
来源材料: []
关联项目: []
知识状态: 已提炼
成熟度: 种子
上位主题: []
相关主题: []
最后复核: 2026-07-10
{evidence}{mastery_lines}---

# {title}

## 核心命题

{title}的核心因果。

## 适用边界

- 测试边界。

## 学习材料

- 模拟来源。

## 内容导览

- 模拟导览。

## 知识单元

- 模拟知识。
{external}
## 我的默认做法

- 模拟做法。

## 项目应用与验证

- 待验证。

## 我的理解、疑问与联想

> [!question] 我的疑问
> {title}最重要的边界是什么？

## 复习区

- [ ] #复习 模拟任务。
"""


class SelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.library = self.vault / "影视创作知识库"
        self.library.mkdir(parents=True)
        north = self.library / "00-待归档与知识地图" / "我的知识树北极星.md"
        north.parent.mkdir(parents=True)
        north.write_text("---\n当前重点: 故事与剧本\n---\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_topic(self, folder: str, title: str, **kwargs: object) -> Path:
        path = self.library / folder / f"{title}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(topic_text(title, **kwargs), encoding="utf-8")
        return path

    def choose(self, *, explicit: str = "", category: str = ""):
        return choose(
            self.vault,
            explicit=explicit,
            category=category,
            library=self.library,
            north_star=self.library / "00-待归档与知识地图" / "我的知识树北极星.md",
        )

    def test_explicit_topic_wins(self) -> None:
        self.write_topic("01", "甲", category="故事与剧本", mastery="未检验")
        target = self.write_topic("02", "乙", category="导演与视听语言", mastery="能辨析", review_date="2026-07-01")
        result = self.choose(explicit="乙")
        self.assertEqual(result["status"], "selected")
        self.assertEqual(Path(str(result["path"])), target.resolve())

    def test_current_focus_precedes_lower_other_category(self) -> None:
        self.write_topic("01", "剧本主题", category="故事与剧本", mastery="能复述", review_date="2026-07-02")
        self.write_topic("02", "摄影主题", category="摄影美术与现场制作", mastery="未检验")
        result = self.choose()
        self.assertEqual(result["title"], "剧本主题")

    def test_lowest_mastery_within_focus(self) -> None:
        self.write_topic("01", "已辨析", category="故事与剧本", mastery="能辨析", review_date="2026-06-01")
        self.write_topic("01", "未检验", category="故事与剧本", mastery=None)
        result = self.choose()
        self.assertEqual(result["title"], "未检验")
        self.assertEqual(result["mastery_state"], "未检验")
        self.assertTrue(result["needs_mastery_fields"])

    def test_oldest_review_date_precedes_filename(self) -> None:
        self.write_topic("01", "较新", category="故事与剧本", mastery="能复述", review_date="2026-07-08")
        self.write_topic("01", "较旧", category="故事与剧本", mastery="能复述", review_date="2026-06-08")
        result = self.choose()
        self.assertEqual(result["title"], "较旧")

    def test_legacy_is_skipped_automatically(self) -> None:
        legacy = self.library / "旧主题.md"
        legacy.write_text("---\n类型: 主题笔记\n分类: 故事与剧本\n---\n# 旧主题\n", encoding="utf-8")
        self.write_topic("01", "兼容主题", category="故事与剧本", mastery="能复述", review_date="2026-07-01")
        result = self.choose()
        self.assertEqual(result["title"], "兼容主题")

    def test_explicit_legacy_requires_previewed_upgrade(self) -> None:
        legacy = self.library / "旧主题.md"
        legacy.write_text("---\n类型: 主题笔记\n分类: 故事与剧本\n---\n# 旧主题\n", encoding="utf-8")
        result = self.choose(explicit="旧主题")
        self.assertEqual(result["status"], "requires_upgrade")
        self.assertEqual(result["knowledge_version"], "legacy")

    def test_library_outside_selected_vault_fails_closed(self) -> None:
        outside = self.vault.parent / "outside-library"
        with self.assertRaisesRegex(ValueError, "inside the selected vault"):
            choose(
                self.vault,
                library=outside,
                north_star=outside / "我的知识树北极星.md",
            )

    def test_open_question_does_not_override_mastery_question(self) -> None:
        self.write_topic("01", "人物", category="故事与剧本", mastery="未检验")
        result = self.choose()
        self.assertIn("核心因果关系", result["suggested_question"])
        self.assertEqual(result["open_question"], "人物最重要的边界是什么？")
        self.assertNotEqual(result["suggested_question"], result["open_question"])

    def test_mastered_topic_needs_explicit_review(self) -> None:
        self.write_topic("01", "人物", category="故事与剧本", mastery="能迁移")
        self.assertEqual(self.choose()["status"], "no_target")
        self.assertEqual(self.choose(explicit="人物")["status"], "selected")


    def test_topic_without_learning_sections_is_compatible_and_read_only(self) -> None:
        target = self.write_topic("01", "知识正文", category="故事与剧本", mastery=None)
        text = target.read_text(encoding="utf-8")
        for heading in ("我的默认做法", "我的理解、疑问与联想", "复习区"):
            text = re.sub(rf"^## {heading}\n.*?(?=^## |\Z)", "", text, flags=re.MULTILINE | re.DOTALL)
        target.write_text(text, encoding="utf-8")
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        result = self.choose(explicit="知识正文")
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["mastery_state"], "未检验")
        self.assertTrue(result["needs_mastery_fields"])
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), before)

    def test_missing_knowledge_body_still_requires_upgrade(self) -> None:
        target = self.write_topic("01", "残缺主题", category="故事与剧本", mastery=None)
        text = target.read_text(encoding="utf-8").replace("## 知识单元", "## 尚未整理")
        target.write_text(text, encoding="utf-8")
        result = self.choose(explicit="残缺主题")
        self.assertEqual(result["status"], "requires_upgrade")
        self.assertIn("知识单元", result["missing_headings"])


    def test_configured_learning_zone_limits_automatic_target_only(self) -> None:
        creation = self.write_topic("创作区/导演", "优先但创作专用", category="故事与剧本", mastery="未检验")
        learning = self.write_topic("学习区/专题", "本次可学", category="声音与后期", mastery="能复述", review_date="2026-07-01")
        configured = SimpleNamespace(vault=self.vault.resolve(), knowledge_library=self.library.resolve(), learning_root=learning.parent.parent)
        with patch("select_review_target.CONFIG", configured):
            automatic = self.choose()
            explicit = self.choose(explicit="优先但创作专用")
        self.assertEqual(Path(str(automatic["path"])), learning.resolve())
        self.assertEqual(Path(str(explicit["path"])), creation.resolve())
        self.assertEqual(automatic["current_focus"], "故事与剧本")

    def test_learning_zone_keeps_public_north_star_and_rejects_outside_override(self) -> None:
        learning = self.write_topic("学习区", "学习主题", category="故事与剧本", mastery=None)
        result = choose(self.vault, library=self.library, learning_root=learning.parent)
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["current_focus"], "故事与剧本")
        for invalid in (self.vault, self.library, self.vault / "外部学习"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Learning root"):
                choose(self.vault, library=self.library, learning_root=invalid)

    def test_configured_zone_does_not_leak_to_another_library(self) -> None:
        self.write_topic("01", "兼容旧库", category="故事与剧本", mastery=None)
        configured = SimpleNamespace(vault=self.vault.resolve(), knowledge_library=self.vault / "另一知识库", learning_root=self.vault / "另一知识库/学习区")
        with patch("select_review_target.CONFIG", configured):
            result = self.choose()
        self.assertEqual(result["title"], "兼容旧库")


if __name__ == "__main__":
    unittest.main()
