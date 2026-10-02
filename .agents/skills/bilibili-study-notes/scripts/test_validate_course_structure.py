from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from validate_course_structure import parse_expected_pages, validate_course_structure


class CourseStructureTests(unittest.TestCase):
    def write_note(self, folder: Path, name: str, start: int, pages: list[int]) -> None:
        page_list = ", ".join(map(str, pages))
        (folder / name).write_text(
            "\n".join(
                (
                    "---",
                    "类型: 分集笔记",
                    "聚合单位: 课",
                    f"P: {start}",
                    f"包含P: [{page_list}]",
                    "---",
                    f"# {name}",
                )
            ),
            encoding="utf-8",
        )

    def test_grouped_pages_cover_expected_range_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            first = "02 - 第二课（P5-P6）.md"
            second = "03 - 第三课（P7-P8）.md"
            (folder / "00 - 课程总览.md").write_text(
                f"[[{Path(first).stem}]]\n[[{Path(second).stem}]]\n", encoding="utf-8"
            )
            self.write_note(folder, first, 5, [5, 6])
            self.write_note(folder, second, 7, [7, 8])
            errors = validate_course_structure(folder, parse_expected_pages("5-8"))
            self.assertEqual(errors, [])

    def test_duplicate_and_missing_pages_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            first = "02 - 第二课（P5-P6）.md"
            second = "03 - 第三课（P6）.md"
            (folder / "00 - 课程总览.md").write_text(
                f"[[{Path(first).stem}]]\n[[{Path(second).stem}]]\n", encoding="utf-8"
            )
            self.write_note(folder, first, 5, [5, 6])
            self.write_note(folder, second, 6, [6])
            errors = validate_course_structure(folder, parse_expected_pages("5-7"))
            self.assertTrue(any("重复归入" in error for error in errors))
            self.assertTrue(any("缺少请求页码" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
