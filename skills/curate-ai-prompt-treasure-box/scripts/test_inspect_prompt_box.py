from __future__ import annotations

import unittest

from inspect_prompt_box import (
    CATEGORIES,
    compare_candidate,
    inspect_quick_index,
    inspect_structure,
    parse_entries,
)


def valid_markdown() -> str:
    rows = []
    for category in CATEGORIES:
        value = "[[#测试条目|测试条目]]" if category == "影视创作" else "暂无"
        rows.append(f"> **{category}**：{value}")
    sections = []
    for category in CATEGORIES:
        sections.append(f"## {category}\n")
        if category == "影视创作":
            sections.append(
                """### 测试条目

- 用途：生成一个镜头描述。
- 标签：镜头
- 来源：用户提供（未附链接）
- 收录日期：2026-07-18
- 适用场景：镜头设计。
- 适用边界：需要提供场景任务。
- 验证状态：未验证

**可复制整理版**

```text
请生成一个镜头描述
```

> [!quote]- 原始提示词
> 请生成一个镜头描述
"""
            )
    return (
        "# 小陌的AI百宝箱\n\n"
        "<!-- prompt-box-index:start -->\n> [!abstract]+ 快速目录\n"
        + "\n".join(rows)
        + "\n<!-- prompt-box-index:end -->\n\n"
        + "\n".join(sections)
    )


class PromptBoxInspectionTests(unittest.TestCase):
    def test_valid_structure_and_index(self) -> None:
        markdown = valid_markdown()
        entries, outside = parse_entries(markdown)
        structure = inspect_structure(markdown, entries, outside)
        index = inspect_quick_index(markdown, entries)
        self.assertEqual(1, len(entries))
        self.assertFalse(structure["entry_errors"])
        self.assertTrue(index["ok"])

    def test_exact_candidate_is_detected(self) -> None:
        entries, _ = parse_entries(valid_markdown())
        result = compare_candidate("请生成一个镜头描述", entries, 0.82)
        self.assertEqual("测试条目", result["exact_matches"][0]["title"])

    def test_stale_index_link_fails(self) -> None:
        markdown = valid_markdown().replace(
            "[[#测试条目|测试条目]]", "[[#不存在|不存在]]", 1
        )
        entries, _ = parse_entries(markdown)
        report = inspect_quick_index(markdown, entries)
        self.assertFalse(report["ok"])
        self.assertIn("不存在", report["stale_links"])


if __name__ == "__main__":
    unittest.main()
