from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_tree_state import read_global_state, read_state, source_learning_record
from weekly_review import collect_state


EMPTY_TABLES = """## 已确认的全局待办

| 标识 | 事项 | 依据 |
|---|---|---|

暂无。

## 待选择的全局事项

| 标识 | 事项 | 依据 |
|---|---|---|
| P01 | 旧来源补查 | 历史建议，未采用 |

## 唯一下一步行动

历史建议不能替代当前任务。
"""


class SharedStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name) / "vault"
        self.library = self.vault / "影视创作知识库"
        self.control = self.library / "00-待归档与知识地图"
        self.control.mkdir(parents=True)
        self.north = self.control / "我的知识树北极星.md"
        self.north.write_text("---\n当前重点: 故事与剧本\n总体策略: 六类均衡\n---\n", encoding="utf-8")
        self.status = self.control / "知识树状态.md"
        self.status.write_text(EMPTY_TABLES, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def source(self, title: str, state: str, question: str = "") -> Path:
        path = self.vault / "sources" / f"{title}.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"---\n类型: 分集笔记\n分类: 故事与剧本\n理解状态: 待理解\n关键问题状态: {state}\n---\n\n## 关键问题\n\n{question}\n", encoding="utf-8")
        return path

    def read(self, **kwargs):
        return read_state(self.vault, self.library, review_target={"status": "no_target"}, **kwargs)

    def test_two_current_tasks_do_not_mutate_global_state(self) -> None:
        before = hashlib.sha256(self.status.read_bytes()).hexdigest()
        first = self.read(current_task="核对第一章来源")
        second = self.read(current_task="检查剧本第六场")
        self.assertEqual(first["effective_action"]["text"], "核对第一章来源")
        self.assertEqual(second["effective_action"]["text"], "检查剧本第六场")
        self.assertEqual(first["global_state"], second["global_state"])
        self.assertEqual(before, hashlib.sha256(self.status.read_bytes()).hexdigest())
        self.assertFalse(first["system_suggestion"]["adopted"])

    def test_empty_confirmed_table_does_not_adopt_pending_row(self) -> None:
        state = self.read()
        self.assertEqual(state["global_confirmed"], [])
        self.assertEqual(len(state["pending_choices"]), 1)
        self.assertFalse(state["effective_action"]["adopted"])

    def test_current_task_overrides_confirmed_global_item(self) -> None:
        self.status.write_text(EMPTY_TABLES.replace("暂无。", "| G01 | 全局已选事项 | 用户明确采用 |", 1), encoding="utf-8")
        self.assertEqual(self.read()["effective_action"]["text"], "全局已选事项")
        self.assertEqual(self.read(current_task="用户本次要求") ["effective_action"]["text"], "用户本次要求")

    def test_malformed_table_is_error_not_empty_queue(self) -> None:
        self.status.write_text(EMPTY_TABLES.replace("历史建议，未采用", ""), encoding="utf-8")
        state = self.read()
        self.assertFalse(state["global_state"]["valid"])
        self.assertIsNone(state["global_confirmed"])
        self.assertEqual(state["system_suggestion"]["kind"], "state_unavailable")

    def test_duplicate_id_is_reported(self) -> None:
        self.status.write_text(EMPTY_TABLES.replace("暂无。", "| P01 | 另一事项 | 用户采用 |", 1), encoding="utf-8")
        self.assertIn("标识重复", " ".join(self.read()["global_state"]["errors"]))

    def test_not_applicable_lesson_has_no_pending_question(self) -> None:
        lesson = self.source("课级", "不适用", "随手练习题？")
        state = self.read(selected_source=str(lesson))
        self.assertEqual(state["selected_source"]["status"], "not_applicable")
        self.assertNotEqual(state["system_suggestion"]["kind"], "selected_source_question")
        self.assertNotIn("随手练习", state["system_suggestion"]["text"])

    def test_explicit_source_question_skips_callout_marker(self) -> None:
        source = self.source("当前来源", "待回答", "> [!question] 当前关键问题\n>\n> 这条方法为什么有效？")
        state = self.read(selected_source=str(source), learning_requested=True)
        self.assertEqual(state["system_suggestion"]["text"], "这条方法为什么有效？")
        self.assertEqual(state["system_suggestion"]["kind"], "selected_source_question")

    def test_actual_question_in_callout_title_is_read_without_auto_learning(self) -> None:
        source = self.source("旧格式真实问题", "待回答", "> [!question] 这条方法为什么有效？")
        before = source.read_bytes()
        ordinary = self.read(selected_source=str(source))
        self.assertEqual(ordinary["input_errors"], [])
        self.assertEqual(ordinary["selected_source"]["status"], "selected_pending")
        self.assertEqual(ordinary["system_suggestion"]["kind"], "learning_not_requested")
        requested = self.read(selected_source=str(source), learning_requested=True)
        self.assertEqual(requested["system_suggestion"]["text"], "这条方法为什么有效？")
        self.assertEqual(source.read_bytes(), before)

    def test_callout_label_without_question_remains_missing(self) -> None:
        source = self.source("空题目标签", "待回答", "> [!question] 当前关键问题")
        record = source_learning_record(source, self.vault)
        self.assertEqual(record["status"], "missing_question")

    def test_unselected_historical_question_does_not_take_over(self) -> None:
        self.source("历史来源", "待回答", "历史任务必须先做？")
        state = self.read(current_task="检查当次材料")
        self.assertEqual(state["effective_action"]["text"], "检查当次材料")
        self.assertNotIn("历史任务必须", state["system_suggestion"]["text"])

    def test_only_explicit_current_blocker_precedes_source(self) -> None:
        source = self.source("当前来源", "待回答", "当前题？")
        state = self.read(selected_source=str(source), related_blockers=["本次来源缺关键页"])
        self.assertEqual(state["system_suggestion"]["kind"], "related_blocker")

    def test_source_outside_vault_is_rejected(self) -> None:
        result = source_learning_record(self.vault.parent / "other.md", self.vault)
        self.assertEqual(result["status"], "invalid")
        state = self.read(selected_source=str(self.vault.parent / "other.md"))
        self.assertEqual(state["system_suggestion"]["kind"], "selected_source_unavailable")
        self.assertTrue(state["input_errors"])

    def test_multi_source_seed_is_not_counted_as_mature(self) -> None:
        topic = self.library / "01-故事与剧本" / "主题.md"
        topic.parent.mkdir()
        topic.write_text("---\n类型: 主题笔记\n分类: 故事与剧本\n成熟度: 种子\n证据状态: 多源互证\n掌握状态: 未检验\n---\n# 主题\n", encoding="utf-8")
        lesson = self.source("独立课", "不适用", "可选练习？")
        with patch("weekly_review.ObsidianCLI", side_effect=AssertionError("must not call native Obsidian")):
            state = collect_state(self.vault, library=self.library, include_cli=False)
        self.assertEqual(state["coverage"]["故事与剧本"]["stable"], 0)
        self.assertEqual(state["maturity"]["种子"], 1)
        self.assertEqual(state["evidence"]["多源互证"], 1)
        self.assertEqual(state["pending_understanding"], [])
        self.assertEqual(state["unanswered_questions"], [])
        self.assertEqual(len(state["source_understanding_inventory"]), 1)

    def test_explicit_map_gap_is_used_without_count_inference(self) -> None:
        path = self.library / "01-故事与剧本" / "00-故事与剧本地图.md"
        path.parent.mkdir()
        path.write_text("---\n分类: 故事与剧本\n---\n## 知识骨架\n\n| 子域 | 问题 | 入口 | 覆盖状态 |\n|---|---|---|---|\n| 对白 | 如何处理潜台词？ | 暂无 | 待补 |\n", encoding="utf-8")
        state = self.read(learning_requested=True)
        self.assertEqual(state["system_suggestion"]["kind"], "map_gap")
        self.assertIn("潜台词", state["system_suggestion"]["text"])


    def test_default_read_does_not_call_selector(self) -> None:
        with patch("select_review_target.choose", side_effect=AssertionError("must not select without request")):
            state = read_state(self.vault, self.library)
        self.assertEqual(state["review_target"], {"status": "not_requested"})
        self.assertEqual(state["system_suggestion"]["kind"], "learning_not_requested")
        self.assertFalse(state["learning_requested"])

    def test_selected_source_alone_does_not_ask_historical_question(self) -> None:
        source = self.source("当前来源", "待回答", "不要自动问这道题？")
        with patch("select_review_target.choose", side_effect=AssertionError("must not select")):
            state = read_state(self.vault, self.library, selected_source=str(source))
        self.assertEqual(state["selected_source"]["status"], "selected_pending")
        self.assertEqual(state["system_suggestion"]["kind"], "learning_not_requested")
        self.assertNotIn("不要自动问", state["system_suggestion"]["text"])

    def test_missing_learning_fields_are_valid_and_not_queued(self) -> None:
        source = self.source("纯知识来源", "不适用")
        source.write_text("---\n类型: 分集笔记\n分类: 故事与剧本\n---\n# 知识内容\n", encoding="utf-8")
        with patch("select_review_target.choose", side_effect=AssertionError("must not select")), patch(
            "weekly_review.ObsidianCLI", side_effect=AssertionError("must not call native Obsidian")
        ):
            state = self.read(selected_source=str(source))
            weekly = collect_state(self.vault, library=self.library, include_cli=False)
        self.assertEqual(state["input_errors"], [])
        self.assertEqual(state["selected_source"]["status"], "not_pending")
        self.assertEqual(weekly["pending_understanding"], [])
        self.assertEqual(weekly["unanswered_questions"], [])
        self.assertEqual(weekly["source_queue_issues"], [])

    def test_existing_pending_state_without_question_still_reports_gap(self) -> None:
        source = self.source("损坏学习记录", "待回答")
        state = self.read(selected_source=str(source))
        self.assertEqual(state["selected_source"]["status"], "missing_question")
        self.assertTrue(state["input_errors"])
        self.assertEqual(state["system_suggestion"]["kind"], "selected_source_unavailable")

    def test_explicit_learning_on_plain_source_does_not_pick_unrelated_topic(self) -> None:
        source = self.source("来源", "")
        with patch("select_review_target.choose", side_effect=AssertionError("selected source owns learning")):
            state = read_state(self.vault, self.library, selected_source=str(source), learning_requested=True)
        self.assertEqual(state["review_target"]["status"], "source_selected")
        self.assertEqual(state["system_suggestion"]["kind"], "selected_source_learning")
        self.assertEqual(state["input_errors"], [])

    def test_explicit_learning_selects_once_and_does_not_persist(self) -> None:
        before = {path: path.read_bytes() for path in self.vault.rglob("*.md")}
        target = {"status": "selected", "mastery_state": "未检验", "relative_path": "t.md", "suggested_question": "解释关系"}
        with patch("select_review_target.choose", return_value=target) as selector:
            state = read_state(self.vault, self.library, current_task="请给学习建议", learning_requested=True)
        selector.assert_called_once()
        self.assertEqual(state["system_suggestion"]["text"], "解释关系")
        self.assertEqual(state["effective_action"]["text"], "请给学习建议")
        self.assertFalse(state["system_suggestion"]["adopted"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.vault.rglob("*.md")})
        self.assertFalse(self.read()["learning_requested"])

    def test_weekly_retains_historical_statistics_without_choosing(self) -> None:
        self.source("历史", "待回答", "历史题？")
        with patch("select_review_target.choose", side_effect=AssertionError("must not select")), patch(
            "weekly_review.ObsidianCLI", side_effect=AssertionError("must not call native Obsidian")
        ):
            state = collect_state(self.vault, library=self.library, include_cli=False)
        self.assertEqual(len(state["pending_understanding"]), 1)
        self.assertEqual(len(state["unanswered_questions"]), 1)
        self.assertEqual(state["review_target"]["status"], "not_requested")
        self.assertNotIn("历史题", state["next_action"])

    def test_weekly_explicit_learning_calls_shared_selector_once(self) -> None:
        target = {"status": "selected", "mastery_state": "未检验", "relative_path": "t.md", "suggested_question": "解释关系"}
        with patch("select_review_target.choose", return_value=target) as selector, patch(
            "weekly_review.ObsidianCLI", side_effect=AssertionError("must not call native Obsidian")
        ):
            state = collect_state(self.vault, library=self.library, include_cli=False, learning_requested=True)
        selector.assert_called_once()
        self.assertEqual(state["review_target"], target)
        self.assertEqual(state["system_suggestion"]["text"], "解释关系")

    def test_map_gap_stays_diagnostic_without_learning_request(self) -> None:
        path = self.library / "01-故事与剧本" / "00-故事与剧本地图.md"
        path.parent.mkdir()
        path.write_text("---\n分类: 故事与剧本\n---\n## 知识骨架\n\n| 子域 | 问题 | 入口 | 覆盖状态 |\n|---|---|---|---|\n| 对白 | 潜台词如何成立？ | 暂无 | 待补 |\n", encoding="utf-8")
        state = self.read()
        self.assertEqual(len(state["map_gaps"]), 1)
        self.assertEqual(state["system_suggestion"]["kind"], "learning_not_requested")


    def test_new_common_professional_index_keeps_explicit_map_gaps(self) -> None:
        path = self.control / "专业索引" / "00-故事与剧本地图.md"
        path.parent.mkdir()
        path.write_text("---\n类型: 知识地图\n分类: 故事与剧本\n---\n## 知识骨架\n\n| 子域 | 问题 | 入口 | 覆盖状态 |\n|---|---|---|---|\n| 对白 | 潜台词如何成立？ | 暂无 | 待补 |\n", encoding="utf-8")
        ordinary = self.read()
        learning = self.read(learning_requested=True)
        self.assertEqual(len(ordinary["map_gaps"]), 1)
        self.assertEqual(ordinary["system_suggestion"]["kind"], "learning_not_requested")
        self.assertEqual(learning["system_suggestion"]["kind"], "map_gap")

    def test_both_zones_count_yaml_types_once_and_ignore_personal_navigation(self) -> None:
        for zone in ("创作区", "学习区"):
            folder = self.library / zone / "导演"
            folder.mkdir(parents=True)
            (folder / "来源.md").write_text("---\n类型: 材料总览\n分类: 故事与剧本\n沉淀状态: 未沉淀\n---\n# 来源\n", encoding="utf-8")
            (folder / "主题.md").write_text("---\n类型: 主题笔记\n分类: 声音与后期\n成熟度: 种子\n---\n# 主题\n", encoding="utf-8")
        (self.library / "学习区" / "个人回顾.md").write_text("---\n类型: 个人思考\n理解状态: 待理解\n关键问题状态: 待回答\n---\n# 我的回顾\n", encoding="utf-8")
        (self.library / "学习区" / "入口.md").write_text("---\n类型: 知识地图\n---\n# 入口\n", encoding="utf-8")
        with patch("weekly_review.ObsidianCLI", side_effect=AssertionError("must stay local")):
            weekly = collect_state(self.vault, library=self.library, include_cli=False)
        self.assertEqual(len(weekly["source_understanding_inventory"]), 2)
        self.assertEqual(len(weekly["pending_deposit"]), 2)
        self.assertEqual(weekly["coverage"]["声音与后期"]["topics"], 2)
        self.assertEqual(weekly["coverage"]["导演与视听语言"]["topics"], 0)
        self.assertEqual(weekly["pending_understanding"], [])
        self.assertEqual(weekly["unanswered_questions"], [])
        self.assertEqual(weekly["review_target"], {"status": "not_requested"})

if __name__ == "__main__":
    unittest.main()
