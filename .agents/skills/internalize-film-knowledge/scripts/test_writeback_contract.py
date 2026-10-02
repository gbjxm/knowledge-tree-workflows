from __future__ import annotations

import re
import unittest
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "writeback-contract"


def props(text: str) -> dict[str, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, flags=re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line and not line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


class WritebackContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8-sig")

    def test_authorized_partial_record_preserves_prior_content_without_assigning_task(self) -> None:
        text = self.read("topic-partial.md")
        metadata = props(text)
        self.assertEqual(metadata["掌握状态"], "未检验")
        self.assertEqual(metadata["最近检验"], "2026-07-10")
        self.assertIn("受保护核心命题", text)
        self.assertIn("受保护旧理解", text)
        self.assertEqual(text.count("### 内化检验记录"), 1)
        self.assertEqual(len(re.findall(r"^- \[ \] #复习", text, flags=re.MULTILINE)), 0)

    def test_transfer_does_not_claim_project_validation(self) -> None:
        text = self.read("topic-transfer.md")
        metadata = props(text)
        self.assertEqual(metadata["掌握状态"], "能迁移")
        self.assertEqual(metadata["证据状态"], "单一来源")
        self.assertIn("尚无真实项目证据", text)
        self.assertEqual(text.count("### 内化检验记录"), 1)

    def test_source_only_writeback_creates_no_topic_link(self) -> None:
        text = self.read("source-only.md")
        metadata = props(text)
        self.assertEqual(metadata["理解状态"], "理解中")
        self.assertEqual(metadata["关键问题状态"], "已回答")
        self.assertNotIn("[[", text)
        self.assertEqual(text.count("### 内化检验记录"), 1)


if __name__ == "__main__":
    unittest.main()
