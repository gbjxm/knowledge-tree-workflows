from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validate_note import (
    check_common, check_episode, check_involved_categories, check_mastery_extension, check_map,
    check_overview, check_source_architecture, check_topic, check_v21_source,
    parse_frontmatter,
)


class InvolvedCategoryTests(unittest.TestCase):
    def test_valid_categories_pass(self) -> None:
        raw = "---\n分类: 故事与剧本\n涉及分类: [故事与剧本, 导演与视听语言]\n---"
        errors: list[str] = []
        check_involved_categories(raw, {"分类": "故事与剧本"}, errors)
        self.assertEqual(errors, [])

    def test_primary_category_is_required(self) -> None:
        raw = "---\n分类: 故事与剧本\n涉及分类: [导演与视听语言]\n---"
        errors: list[str] = []
        check_involved_categories(raw, {"分类": "故事与剧本"}, errors)
        self.assertTrue(any("自己的分类" in error for error in errors))

    def test_duplicate_and_invalid_categories_fail(self) -> None:
        raw = "---\n分类: 故事与剧本\n涉及分类: [故事与剧本, 故事与剧本, 第七类]\n---"
        errors: list[str] = []
        check_involved_categories(raw, {"分类": "故事与剧本"}, errors)
        self.assertTrue(any("重复" in error for error in errors))
        self.assertTrue(any("六类合法值" in error for error in errors))


class SourceArchitectureTests(unittest.TestCase):
    def test_complete_source_architecture_passes(self) -> None:
        errors: list[str] = []
        check_source_architecture(
            {"笔记架构": "课程分层", "聚合单位": "课", "架构状态": "已确认"},
            errors,
        )
        self.assertEqual(errors, [])

    def test_partial_source_architecture_fails(self) -> None:
        errors: list[str] = []
        check_source_architecture({"笔记架构": "单篇材料"}, errors)
        self.assertTrue(any("聚合单位" in error for error in errors))
        self.assertTrue(any("架构状态" in error for error in errors))


class GroupedLessonTests(unittest.TestCase):
    def base_props(self) -> dict[str, str]:
        return {
            "类型": "分集笔记",
            "课程": "测试课程",
            "分集": "P5-P6",
            "主题": "测试主题",
            "BV": "BVtest",
            "P": "5",
            "包含P": "[5, 6]",
            "复习状态": "待复习",
            "笔记架构": "课程分层",
            "聚合单位": "课",
            "架构状态": "已确认",
        }

    def base_text(self) -> str:
        return """# 测试课
视频：[P5](https://www.bilibili.com/video/BVtest?p=5)｜[P6](https://www.bilibili.com/video/BVtest?p=6)
## 分集脉络
- P5
- P6
## 时间线笔记
- 00:00
## 复习区
- [ ] #复习 任务一
- [ ] #创作练习 任务二
"""

    def test_grouped_lesson_passes(self) -> None:
        errors: list[str] = []
        check_episode(self.base_text(), self.base_props(), errors)
        self.assertEqual(errors, [])

    def test_duplicate_and_missing_page_links_fail(self) -> None:
        props = self.base_props()
        props["包含P"] = "[5, 5, 7]"
        errors: list[str] = []
        check_episode(self.base_text(), props, errors)
        self.assertTrue(any("重复" in error for error in errors))
        self.assertTrue(any("缺少这些 P" in error for error in errors))


class OptionalLearningTests(unittest.TestCase):
    def source(self, extra: str = "", version: str = "2.1") -> str:
        return f"""---
类型: 分集笔记
分类: 故事与剧本
状态: 已整理
材料类型: 课程
信息来源: 测试字幕
完整程度: 已整理
整理日期: 2026-09-22
知识库版本: {version}
课程: 测试课程
分集: P1
主题: 人物
BV: BVtest
P: 1
适用阶段: [故事骨架]
沉淀状态: 已沉淀
已沉淀主题: ['[[主题]]']
待沉淀主题: []
{extra}---
# 来源
视频：[P1](https://www.bilibili.com/video/BVtest?p=1)
## 时间线笔记
00:00 人物的行动需要具体处境。
"""

    def topic(self, extra: str = "", version: str = "2.1") -> str:
        evidence = "证据状态: 单一来源\n" if version == "2.1" else ""
        external = "## 外部补充与分歧\n暂无外部补充。\n" if version == "2.1" else ""
        return f"""---
类型: 主题笔记
分类: 故事与剧本
状态: 持续积累
材料类型: 主题沉淀
信息来源: 来源笔记
完整程度: 已整理
整理日期: 2026-09-22
知识库版本: {version}
主题域: 人物
解决问题: 如何判断人物行动
适用阶段: [故事骨架]
来源材料: ['[[来源]]']
关联项目: []
知识状态: 已提炼
成熟度: 种子
上位主题: []
相关主题: []
最后复核: 2026-09-22
{evidence}{extra}---
# 主题
## 核心命题
结合处境判断人物行动。
## 适用边界
不能只按观众偏好判断人物是否可信。
## 学习材料
[[来源]]
## 内容导览
从处境到选择。
## 知识单元
选择需要面对具体阻力。
{external}## 项目应用与验证
尚未进行项目验证。
"""

    def validate(self, text: str) -> list[str]:
        raw, props = parse_frontmatter(text)
        errors: list[str] = []
        check_common(text, props, errors)
        if props["类型"] == "分集笔记":
            check_episode(text, props, errors)
        else:
            check_topic(text, raw, props, errors)
        return errors

    def test_v2_and_v21_source_and_topic_work_without_learning_extensions(self) -> None:
        for version in ("2", "2.1"):
            for factory in (self.source, self.topic):
                with self.subTest(version=version, factory=factory.__name__):
                    self.assertEqual(self.validate(factory(version=version)), [])

    def test_legacy_learning_content_is_still_compatible(self) -> None:
        source = self.source("复习状态: 待复习\n理解状态: 理解中\n关键问题状态: 已回答\n")
        source += "## 关键问题\n人物行动为什么离不开处境？\n## 复习区\n- [ ] #复习 用户已有任务\n"
        topic = self.topic() + "## 我的默认做法\n用户已有做法。\n## 我的理解、疑问与联想\n真实旧理解。\n## 复习区\n- [ ] #复习 已采用任务\n"
        self.assertEqual(self.validate(source), [])
        self.assertEqual(self.validate(topic), [])

    def test_empty_legacy_learning_fields_stay_compatible(self) -> None:
        self.assertEqual(self.validate(self.source("理解状态:\n关键问题状态:\n复习状态:\n")), [])

    def test_invalid_existing_learning_states_fail(self) -> None:
        for key in ("理解状态", "关键问题状态"):
            with self.subTest(key=key):
                self.assertTrue(any(key in error for error in self.validate(self.source(f"{key}: 随便\n"))))

    def test_pending_question_requires_meaningful_question_not_empty_heading(self) -> None:
        source = self.source("关键问题状态: 待回答\n")
        for suffix in ("", "## 关键问题\n", "## 关键问题\n<!-- 待填写 -->\n", "## 关键问题\n待回答\n"):
            with self.subTest(suffix=suffix):
                self.assertTrue(any("关键问题" in error for error in self.validate(source + suffix)))
        self.assertEqual(self.validate(source + "## 关键问题\n人物的愿望何时会变成行动？\n"), [])

    def test_real_question_in_callout_title_is_preserved_but_label_is_not_content(self) -> None:
        for state in ("待回答", "已回答"):
            source = self.source(f"关键问题状态: {state}\n")
            with self.subTest(state=state):
                self.assertEqual(self.validate(source + "## 关键问题\n> [!question] 人物变化为什么需要后果？\n"), [])
                self.assertEqual(self.validate(source + "## 关键问题\n> [!question]+ 人物变化为什么需要后果？\n"), [])
                self.assertTrue(any("占位" in error for error in self.validate(source + "## 关键问题\n> [!question] 当前关键问题\n")))

    def test_answered_state_retains_original_question(self) -> None:
        source = self.source("理解状态: 已理解\n关键问题状态: 已回答\n")
        for suffix in ("", "## 关键问题\n<!-- 已回答 -->\n", "### 内化检验记录\n用户已经理解了人物行动。\n"):
            with self.subTest(suffix=suffix):
                self.assertTrue(any("关键问题" in error for error in self.validate(source + suffix)))
        valid_record = "## 关键问题\n人物变化为什么需要后果？\n## 我的理解、疑问与联想\n### 内化检验记录\n2026-09-22：用户解释了后果能使选择可观察，核心关系准确。\n"
        self.assertEqual(self.validate(source + valid_record), [])

    def test_source_link_remains_required(self) -> None:
        text = self.source().replace("视频：[P1](https://www.bilibili.com/video/BVtest?p=1)\n", "")
        self.assertTrue(any("视频来源" in error for error in self.validate(text)))

    def test_overview_dataview_does_not_require_review_column(self) -> None:
        text = "## 材料简介\n课程概要。\n## 分集矩阵\n```dataview\nTABLE P, 分集, 主题, 状态, 信息来源, 完整程度\n```\n"
        errors: list[str] = []
        check_overview(text, {}, errors)
        self.assertEqual(errors, [])

    def test_mastery_pair_date_and_record_remain_required(self) -> None:
        cases = (
            ("掌握状态: 能复述\n", "同时包含"),
            ("掌握状态: 能复述\n最近检验:\n", "填写 最近检验"),
            ("掌握状态: 已精通\n最近检验:\n", "掌握状态必须"),
            ("掌握状态: 能复述\n最近检验: 2026-02-30\n", "有效"),
            ("掌握状态: 能复述\n最近检验: 2026-09-22\n", "内化检验记录"),
        )
        for extra, message in cases:
            with self.subTest(extra=extra):
                self.assertTrue(any(message in error for error in self.validate(self.topic(extra))))

    def test_empty_mastery_record_fails_but_freeform_old_record_passes(self) -> None:
        topic = self.topic("掌握状态: 能复述\n最近检验: 2026-09-22\n")
        for record in ("", "<!-- 待记录 -->", "#### 2026-09-22\n- 问题：\n- 核心回答：待补充\n- 诊断：暂无"):
            with self.subTest(record=record):
                self.assertTrue(any("占位" in error for error in self.validate(topic + "### 内化检验记录\n" + record)))
        old_record = "### 内化检验记录\n2026-09-22：用户解释了选择如何改变后续处境，核心关系准确。\n"
        self.assertEqual(self.validate(topic + old_record), [])


class LearningAuditTests(unittest.TestCase):
    source = OptionalLearningTests.source
    topic = OptionalLearningTests.topic
    def run_audit(self, source: str, topic: str) -> tuple[int, str]:
        import audit_knowledge_system as audit
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            (vault / "来源.md").write_text(source, encoding="utf-8")
            (vault / "主题.md").write_text(topic, encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", ["audit", "--vault", str(vault), "--strict"]), contextlib.redirect_stdout(output):
                code = audit.main()
            return code, output.getvalue()

    def test_audit_accepts_missing_learning_fields_without_pending_queue(self) -> None:
        code, output = self.run_audit(self.source(), self.topic())
        self.assertEqual(code, 0, output)
        self.assertIn("待理解: 0；待回答: 0", output)
        self.assertIn("未检验=1", output)

    def test_audit_keeps_dangling_and_reverse_source_checks(self) -> None:
        code, output = self.run_audit(self.source(), self.topic().replace("[[来源]]", "[[不存在来源]]"))
        self.assertEqual(code, 1)
        self.assertIn("失效链接", output)
        self.assertIn("缺少主题到来源的回链", output)

    def test_audit_rejects_invalid_optional_state_and_empty_mastery_record(self) -> None:
        source = self.source("理解状态: 已精通\n关键问题状态: 待回答\n")
        topic = self.topic("掌握状态: 能复述\n最近检验: 2026-09-22\n") + "### 内化检验记录\n<!-- 待记录 -->\n"
        code, output = self.run_audit(source, topic)
        self.assertEqual(code, 1)
        self.assertIn("理解状态必须", output)
        self.assertIn("关键问题", output)
        self.assertIn("占位", output)



class ModernNavigationTests(unittest.TestCase):
    def test_modern_map_needs_no_learning_queues(self) -> None:
        for category in ("个人知识树", "故事与剧本"):
            errors: list[str] = []
            text = "# 导航\n## 知识骨架\n按用途组织。\n## 真实知识入口\n[[已有笔记]]\n"
            check_map(text, {"知识库版本": "2.1", "分类": category}, errors)
            self.assertEqual(errors, [])

    def test_modern_map_requires_both_sections_and_valid_version(self) -> None:
        errors: list[str] = []
        check_map("## 知识骨架\n", {"知识库版本": "2.1", "分类": "故事与剧本"}, errors)
        self.assertTrue(any("真实知识入口" in error for error in errors))
        errors = []
        check_map("## 知识骨架\n## 真实知识入口\n", {"分类": "个人知识树"}, errors)
        self.assertTrue(any("知识库版本" in error for error in errors))

    def test_legacy_map_contract_remains_supported(self) -> None:
        text = "\n".join("## " + heading for heading in ("当前学习焦点", "六类知识骨架", "最近生长的知识", "待理解材料", "待复习与练习"))
        errors: list[str] = []
        check_map(text, {"知识库版本": "2.1", "分类": "个人知识树"}, errors)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
