from __future__ import annotations

import unittest
from collections import Counter

from weekly_review import choose_next_action, render_markdown


class WeeklyReviewTests(unittest.TestCase):
    def base_state(self):
        return {
            "coverage": {
                category: {"topics": 0, "stable": 0, "status": "空白"}
                for category in (
                    "故事与剧本",
                    "导演与视听语言",
                    "摄影美术与现场制作",
                    "声音与后期",
                    "创作实践与项目复盘",
                    "行业观察与灵感素材",
                )
            },
            "mastery": {"未检验": 1, "能复述": 0, "能辨析": 0, "能迁移": 0},
            "connections": {
                "same_category_edge_count": 4,
                "cross_category_edge_count": 3,
                "navigation_hint_count": 5,
                "semantic_island_count": 1,
                "error_count": 0,
            },
            "pending_understanding": [],
            "unanswered_questions": [],
            "pending_deposit": [],
            "weak_evidence": [],
            "conflicts": [],
            "cli": {"tasks": 0, "unresolved": 0, "orphans": 0, "deadends": 0},
            "next_action": "做一件事",
        }

    def test_relation_diagnostics_are_separate(self) -> None:
        rendered = render_markdown(self.base_state())
        self.assertIn("成熟度标为稳定", rendered)
        self.assertNotIn("较强证据 |", rendered)
        self.assertIn("正式同类语义关系：4", rendered)
        self.assertIn("正式跨域关系：3", rendered)
        self.assertIn("导航或普通提示指向：5", rendered)
        self.assertIn("不是自动缺陷", rendered)

    def test_explicit_related_blocker_precedes_unanswered_question(self) -> None:
        action = choose_next_action(
            connection_report={"error_count": 1},
            conflicts=[],
            unanswered=[{"path": "source.md", "question": "回答我"}],
            pending_understanding=[],
            review_target={"status": "selected", "mastery_state": "未检验", "relative_path": "t.md"},
            topic_counts=Counter(),
            related_blockers=["修复本次涉及的关系审计错误"],
        )
        self.assertIn("关系审计", action)

    def test_mastery_precedes_coverage_gap(self) -> None:
        action = choose_next_action(
            connection_report={"error_count": 0},
            conflicts=[],
            unanswered=[],
            pending_understanding=[],
            review_target={
                "status": "selected",
                "mastery_state": "未检验",
                "suggested_question": "解释核心关系",
                "source_question": "",
                "relative_path": "topic.md",
            },
            topic_counts=Counter(), learning_requested=True,
        )
        self.assertIn("解释核心关系", action)

    def test_historical_unanswered_does_not_precede_focus_mastery(self) -> None:
        action = choose_next_action(
            connection_report={"error_count": 0}, conflicts=[],
            unanswered=[{"path": "old.md", "question": "旧的未答题"}],
            pending_understanding=[{"path": "lesson.md", "question": ""}],
            review_target={"status": "selected", "mastery_state": "未检验", "suggested_question": "先解释核心关系"},
            topic_counts=Counter({"声音与后期": 99}), learning_requested=True,
        )
        self.assertEqual(action, "先解释核心关系")

    def test_topic_counts_do_not_invent_gap(self) -> None:
        action = choose_next_action(
            connection_report={"error_count": 0}, conflicts=[], unanswered=[], pending_understanding=[],
            review_target={"status": "no_target"}, topic_counts=Counter({"声音与后期": 99}), learning_requested=True,
        )
        self.assertIn("暂无有依据", action)


if __name__ == "__main__":
    unittest.main()
