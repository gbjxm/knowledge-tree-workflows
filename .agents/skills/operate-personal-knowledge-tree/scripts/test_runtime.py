from __future__ import annotations

import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_tree_runtime as runtime
import weekly_review


class RuntimeTests(unittest.TestCase):
    def test_session_context_is_compact_and_personal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            north = root / "north.md"
            status = root / "status.md"
            north.write_text(
                "---\n当前重点: 故事与剧本\n总体策略: 六类均衡\n"
                "Codex角色: 知识导师与研究员\n默认知识形态: 原理 + 方法 + 案例\n---\n"
                "# 北极星\n",
                encoding="utf-8",
            )
            status.write_text(
                "# 状态\n\n## 已确认的全局待办\n\n| 标识 | 事项 | 依据 |\n|---|---|---|\n"
                "| G01 | 全局确认事项 | 用户明确采用 |\n\n"
                "## 待选择的全局事项\n\n| 标识 | 事项 | 依据 |\n|---|---|---|\n\n暂无。\n\n"
                "## 唯一下一步行动\n旧的行动不能再次派工。\n",
                encoding="utf-8",
            )
            context = runtime.build_session_context(north, status, 2500)
            self.assertIn("故事与剧本", context)
            self.assertIn("六类均衡", context)
            self.assertIn("全局确认事项", context)
            self.assertNotIn("旧的行动不能再次派工", context)
            self.assertIn("internalize-film-knowledge", context)
            self.assertIn("weave-film-knowledge-connections", context)
            self.assertLessEqual(len(context), 2500)

    def test_runtime_task_switch_uses_shared_readonly_global_state(self) -> None:
        from test_knowledge_tree_state import EMPTY_TABLES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            north, status = root / "north.md", root / "status.md"
            north.write_text("---\n当前重点: 故事与剧本\n---\n", encoding="utf-8")
            status.write_text(EMPTY_TABLES, encoding="utf-8")
            before = status.read_bytes()
            a = runtime.build_session_context(north, status, current_task="任务甲")
            b = runtime.build_session_context(north, status, current_task="任务乙")
            self.assertIn("任务甲", a)
            self.assertNotIn("任务乙", a)
            self.assertIn("任务乙", b)
            self.assertEqual(status.read_bytes(), before)

    def test_context_routes_learning_flag_without_writing(self) -> None:
        with patch.object(runtime, "build_session_context", return_value="preview") as context, patch(
            "sys.argv", ["knowledge_tree_runtime.py", "--context", "--learning"]
        ), patch("builtins.print"), patch.object(runtime, "save_snapshot", side_effect=AssertionError("preview must not write")):
            self.assertEqual(runtime.main(), 0)
        self.assertTrue(context.call_args.kwargs["learning_requested"])
        with patch.object(runtime, "build_session_context", return_value="preview") as context, patch(
            "sys.argv", ["knowledge_tree_runtime.py", "--context", "--source", "source.md"]
        ), patch("builtins.print"):
            self.assertEqual(runtime.main(), 0)
        self.assertFalse(context.call_args.kwargs["learning_requested"])

    def test_stop_hook_does_not_loop(self) -> None:
        self.assertEqual(runtime.stop_response(["失败"], True), {})
        self.assertEqual(runtime.stop_response([], False), {})
        self.assertEqual(runtime.stop_response(["失败"], False)["decision"], "block")

    def test_within_workspace_boundary(self) -> None:
        root = Path(tempfile.gettempdir()) / "knowledge-tree-root"
        self.assertTrue(runtime.within(root / "child", root))
        self.assertFalse(runtime.within(root.parent / "elsewhere", root))

    def test_post_tool_feedback_contains_context(self) -> None:
        response = runtime.post_tool_response(["note.md\nERROR"])
        self.assertEqual(response["decision"], "block")
        self.assertIn("note.md", response["hookSpecificOutput"]["additionalContext"])

    def test_extract_legacy_topic_question(self) -> None:
        text = "> [!question] 我的疑问\n> 最小变化链要保留什么？\n"
        self.assertEqual(
            weekly_review.extract_callout_question(text), "最小变化链要保留什么？"
        )

    def test_weekly_review_renders_separate_relation_metrics(self) -> None:
        state = {
            "coverage": {
                category: {"topics": 0, "stable": 0, "status": "空白"}
                for category in weekly_review.CATEGORIES
            },
            "mastery": {state: 0 for state in weekly_review.MASTERY_ORDER},
            "connections": {
                "same_category_edge_count": 2,
                "cross_category_edge_count": 3,
                "navigation_hint_count": 4,
                "semantic_island_count": 1,
                "error_count": 0,
            },
            "pending_understanding": [],
            "unanswered_questions": [],
            "pending_deposit": [],
            "weak_evidence": [],
            "conflicts": [],
            "cli": {"tasks": 0, "unresolved": 0, "orphans": 0, "deadends": 0},
            "next_action": "保持当前行动。",
        }
        rendered = weekly_review.render_markdown(state)
        self.assertIn("## 知识关系", rendered)
        self.assertIn("正式同类语义关系：2", rendered)
        self.assertIn("正式跨域关系：3", rendered)
        self.assertIn("导航或普通提示指向：4", rendered)


    def test_nested_source_root_is_scanned_once_and_creation_sources_still_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            library = vault / "知识库"
            learning = library / "学习区"
            creation = library / "创作区"
            for folder in (learning, creation):
                folder.mkdir(parents=True)
                (folder / "metadata.json").write_text("{}", encoding="utf-8")
            configured = SimpleNamespace(source_notes=learning, knowledge_library=library)
            with patch.object(runtime, "CONFIG", configured), patch.object(runtime, "VAULT", vault):
                errors = runtime.check_final_folders([])
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("创作区" in error for error in errors))
            self.assertTrue(any("学习区" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
