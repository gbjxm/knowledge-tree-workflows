from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audit_connections import audit


class ConnectionAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.library = self.vault / "影视创作知识库"
        self.library.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def relation_section(heading: str, rows: list[tuple[str, str, str, str, str]] | None) -> str:
        if rows is None:
            return ""
        row_lines = "\n".join(
            f"| [[{target}]] | {target_category} | {relation} | {reason} | {basis} |"
            for target, target_category, relation, reason, basis in rows
        )
        return (
            f"\n### {heading}\n\n"
            "| 相关主题 | 分类 | 关系 | 连接理由 | 依据 |\n"
            "|---|---|---|---|---|\n"
            f"{row_lines}\n"
        )

    def write_topic(
        self,
        folder: str,
        title: str,
        category: str,
        related: list[str] | None = None,
        involved: list[str] | None = None,
        same_rows: list[tuple[str, str, str, str, str]] | None = None,
        cross_rows: list[tuple[str, str, str, str, str]] | None = None,
        body: str = "这是一段有实质内容的测试命题。",
        library: Path | None = None,
    ) -> Path:
        root = library or self.library
        path = root / folder / f"{title}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        related_lines = "\n".join(f'  - "[[{item}]]"' for item in (related or []))
        involved_lines = "\n".join(f"  - {item}" for item in (involved or []))
        text = (
            "---\n"
            "类型: 主题笔记\n"
            f"分类: {category}\n"
            "状态: 持续积累\n"
            "材料类型: 主题沉淀\n"
            "信息来源: 测试\n"
            "完整程度: 持续积累\n"
            "整理日期: 2026-07-12\n"
            "知识库版本: 2.1\n"
            "主题域: 测试\n"
            "解决问题: 测试问题\n"
            "适用阶段: []\n"
            "来源材料: []\n"
            "关联项目: []\n"
            "知识状态: 已提炼\n"
            "成熟度: 种子\n"
            "上位主题: []\n"
            f"相关主题:{chr(10) + related_lines if related_lines else ' []'}\n"
            "最后复核: 2026-07-12\n"
            "证据状态: 单一来源\n"
            "横向能力: []\n"
            "掌握状态: 未检验\n"
            "最近检验:\n"
            + (f"涉及分类:\n{involved_lines}\n" if involved is not None else "")
            + "---\n\n"
            f"# {title}\n\n"
            f"{body}\n\n"
            "## 相关知识\n"
            + self.relation_section("同类知识连接", same_rows)
            + self.relation_section("跨域连接", cross_rows)
        )
        path.write_text(text, encoding="utf-8")
        return path

    def make_valid_cross_pair(self) -> tuple[Path, Path]:
        a = self.write_topic(
            "01-故事与剧本",
            "主题甲",
            "故事与剧本",
            ["影视创作知识库/02-导演与视听语言/主题乙"],
            ["故事与剧本", "导演与视听语言"],
            cross_rows=[("影视创作知识库/02-导演与视听语言/主题乙", "导演与视听语言", "转译", "把事件变成空间行动", "Codex综合")],
        )
        b = self.write_topic(
            "02-导演与视听语言",
            "主题乙",
            "导演与视听语言",
            ["影视创作知识库/01-故事与剧本/主题甲"],
            ["故事与剧本", "导演与视听语言"],
            cross_rows=[("影视创作知识库/01-故事与剧本/主题甲", "故事与剧本", "前置", "先确认场景发生什么变化", "Codex综合")],
        )
        return a, b

    def make_valid_same_pair(self) -> tuple[Path, Path]:
        a = self.write_topic(
            "01-故事与剧本",
            "主题甲",
            "故事与剧本",
            ["主题乙"],
            same_rows=[("主题乙", "故事与剧本", "互补", "人物与世界共同限定行动", "现有笔记明示")],
        )
        b = self.write_topic(
            "01-故事与剧本",
            "主题乙",
            "故事与剧本",
            ["主题甲"],
            same_rows=[("主题甲", "故事与剧本", "对照", "从另一侧检查同一行动", "现有笔记明示")],
        )
        return a, b

    def error_messages(self, **kwargs: object) -> list[str]:
        kwargs.setdefault("library_relative", self.library.relative_to(self.vault))
        return [item["message"] for item in audit(self.vault, **kwargs)["errors"]]

    def test_valid_reciprocal_cross_connection(self) -> None:
        self.make_valid_cross_pair()
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["cross_category_edge_count"], 1)
        self.assertEqual(report["semantic_edge_count"], 1)
        self.assertEqual(report["edge_count"], 1)

    def test_valid_reciprocal_same_category_connection(self) -> None:
        self.make_valid_same_pair()
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["same_category_edge_count"], 1)
        self.assertEqual(report["cross_category_edge_count"], 0)
        self.assertEqual(report["semantic_connected_topics"], 2)

    def test_one_way_navigation_hint_is_allowed(self) -> None:
        self.write_topic("02-导演与视听语言", "总表", "导演与视听语言", ["专题"])
        self.write_topic("02-导演与视听语言", "专题", "导演与视听语言")
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["navigation_hint_count"], 1)
        self.assertEqual(report["semantic_edge_count"], 0)

    def test_missing_reciprocal_property_is_reported(self) -> None:
        self.make_valid_cross_pair()
        target = self.library / "02-导演与视听语言" / "主题乙.md"
        target.write_text(target.read_text(encoding="utf-8").replace('  - "[[影视创作知识库/01-故事与剧本/主题甲]]"\n', ""), encoding="utf-8")
        self.assertTrue(any("缺少相关主题回链" in message for message in self.error_messages()))

    def test_missing_reciprocal_formal_same_connection_is_reported(self) -> None:
        self.make_valid_same_pair()
        target = self.library / "01-故事与剧本" / "主题乙.md"
        text = target.read_text(encoding="utf-8")
        start = text.index("\n### 同类知识连接")
        target.write_text(text[:start] + "\n", encoding="utf-8")
        self.assertTrue(any("缺少正文同类知识连接回链" in message for message in self.error_messages()))

    def test_invalid_relation_and_basis_are_reported(self) -> None:
        self.make_valid_cross_pair()
        source = self.library / "01-故事与剧本" / "主题甲.md"
        text = source.read_text(encoding="utf-8").replace("| 转译 |", "| 相似 |").replace("| Codex综合 |", "| 关键词 |")
        source.write_text(text, encoding="utf-8")
        messages = self.error_messages()
        self.assertTrue(any("关系无效" in message for message in messages))
        self.assertTrue(any("依据无效" in message for message in messages))

    def test_involved_categories_only_follow_cross_rows(self) -> None:
        self.make_valid_same_pair()
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        first = self.library / "01-故事与剧本" / "主题甲.md"
        text = first.read_text(encoding="utf-8").replace("最近检验:\n---", "最近检验:\n涉及分类:\n  - 故事与剧本\n---")
        first.write_text(text, encoding="utf-8")
        self.assertTrue(any("没有正文跨域连接" in message for message in self.error_messages()))

    def test_wrong_section_for_same_category_is_reported(self) -> None:
        self.make_valid_same_pair()
        first = self.library / "01-故事与剧本" / "主题甲.md"
        first.write_text(first.read_text(encoding="utf-8").replace("### 同类知识连接", "### 跨域连接"), encoding="utf-8")
        self.assertTrue(any("应写入“同类知识连接”" in message for message in self.error_messages()))

    def test_dangling_target_is_reported(self) -> None:
        self.write_topic(
            "01-故事与剧本",
            "主题甲",
            "故事与剧本",
            ["影视创作知识库/04-声音与后期/不存在"],
            ["故事与剧本", "声音与后期"],
            cross_rows=[("影视创作知识库/04-声音与后期/不存在", "声音与后期", "实现", "用声音实现信息隐藏", "来源明示")],
        )
        self.assertTrue(any("无法解析" in message for message in self.error_messages()))

    def test_heading_only_target_is_not_substantive(self) -> None:
        self.write_topic(
            "01-故事与剧本",
            "主题甲",
            "故事与剧本",
            ["主题乙"],
            same_rows=[("主题乙", "故事与剧本", "互补", "共同解决问题", "Codex综合")],
        )
        self.write_topic(
            "01-故事与剧本",
            "主题乙",
            "故事与剧本",
            ["主题甲"],
            same_rows=[("主题甲", "故事与剧本", "互补", "共同解决问题", "Codex综合")],
            body="",
        )
        self.assertTrue(any("不是有实质内容" in message for message in self.error_messages()))

    def test_custom_library_relative_path(self) -> None:
        custom = self.vault / "自定义知识区"
        custom.mkdir()
        self.write_topic("01-故事与剧本", "主题甲", "故事与剧本", library=custom)
        report = audit(self.vault, library_relative=Path("自定义知识区"))
        self.assertEqual(report["audited_topics"], 1)
        self.assertEqual(report["error_count"], 0)

    def test_legacy_topic_without_formal_connections_is_compatible(self) -> None:
        path = self.write_topic("01-故事与剧本", "旧主题", "故事与剧本")
        text = path.read_text(encoding="utf-8").replace("知识库版本: 2.1", "知识库版本: 2")
        path.write_text(text, encoding="utf-8")
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["semantic_island_count"], 1)


    def test_same_category_across_role_and_learning_folders_stays_same_category(self) -> None:
        self.write_topic(
            "创作区/导演", "角色甲", "故事与剧本", ["学习乙"],
            same_rows=[("学习乙", "故事与剧本", "互补", "人物与世界共同限定行动", "现有笔记明示")],
        )
        self.write_topic(
            "学习区/课程", "学习乙", "故事与剧本", ["角色甲"],
            same_rows=[("角色甲", "故事与剧本", "对照", "从另一侧检查同一行动", "现有笔记明示")],
        )
        report = audit(self.vault, library_relative=self.library.relative_to(self.vault))
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["same_category_edge_count"], 1)
        self.assertEqual(report["cross_category_edge_count"], 0)


if __name__ == "__main__":
    unittest.main()
