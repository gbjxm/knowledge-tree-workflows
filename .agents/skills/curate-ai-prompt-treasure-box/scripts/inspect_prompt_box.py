#!/usr/bin/env python3
"""Read-only structure and duplicate inspection for the AI prompt treasure box."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()

CATEGORIES = [
    "思考与决策",
    "学习与内化",
    "阅读与研究",
    "创意与策划",
    "对话与提问优化",
    "影视创作",
    "待分类",
]

REQUIRED_FIELDS = [
    "用途",
    "标签",
    "来源",
    "收录日期",
    "适用场景",
    "适用边界",
    "验证状态",
]

INDEX_START = "<!-- prompt-box-index:start -->"
INDEX_END = "<!-- prompt-box-index:end -->"
INDEX_LINK_PATTERN = re.compile(r"\[\[#([^\]|]+)\|([^\]]+)\]\]")


@dataclass
class Entry:
    category: str
    title: str
    body: str
    organized: str
    original: str
    fenced_texts: list[str]

    @property
    def comparison_texts(self) -> list[str]:
        values = [self.organized, self.original, *self.fenced_texts]
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = normalize(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(value)
        return result


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"```(?:text)?", "", text)
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text


def extract_fenced_text(body: str, heading: str) -> str:
    pattern = rf"^\*\*{re.escape(heading)}\*\*\s*\n+```(?:text)?\s*\n(.*?)\n```"
    match = re.search(pattern, body, flags=re.DOTALL | re.MULTILINE)
    return match.group(1).strip() if match else ""


def extract_original(body: str) -> str:
    marker = re.search(r"^> \[!quote\]- 原始提示词\s*$", body, flags=re.MULTILINE)
    if not marker:
        return ""
    lines: list[str] = []
    for line in body[marker.end() :].splitlines()[1:]:
        if line.startswith("> "):
            lines.append(line[2:])
        elif line == ">":
            lines.append("")
        else:
            break
    return "\n".join(lines).strip()


def parse_entries(markdown: str) -> tuple[list[Entry], list[str]]:
    category_matches = list(re.finditer(r"^## (.+?)\s*$", markdown, flags=re.MULTILINE))
    entries: list[Entry] = []
    entries_outside_categories: list[str] = []

    known_ranges: list[tuple[int, int, str]] = []
    for index, match in enumerate(category_matches):
        end = category_matches[index + 1].start() if index + 1 < len(category_matches) else len(markdown)
        category = match.group(1).strip()
        if category in CATEGORIES:
            known_ranges.append((match.end(), end, category))

    for start, end, category in known_ranges:
        section = markdown[start:end]
        heading_matches = list(re.finditer(r"^### (.+?)\s*$", section, flags=re.MULTILINE))
        for index, match in enumerate(heading_matches):
            body_end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(section)
            body = section[match.end() : body_end].strip()
            entries.append(
                Entry(
                    category=category,
                    title=match.group(1).strip(),
                    body=body,
                    organized=extract_fenced_text(body, "可复制整理版"),
                    original=extract_original(body),
                    fenced_texts=[
                        value.strip()
                        for value in re.findall(r"```(?:text)?\s*\n(.*?)\n```", body, flags=re.DOTALL)
                        if value.strip()
                    ],
                )
            )

    for match in re.finditer(r"^### (.+?)\s*$", markdown, flags=re.MULTILINE):
        if not any(start <= match.start() < end for start, end, _ in known_ranges):
            entries_outside_categories.append(match.group(1).strip())

    return entries, entries_outside_categories


def inspect_structure(markdown: str, entries: list[Entry], outside: list[str]) -> dict:
    present_categories = re.findall(r"^## (.+?)\s*$", markdown, flags=re.MULTILINE)
    missing_categories = [category for category in CATEGORIES if category not in present_categories]
    duplicate_categories = sorted({c for c in CATEGORIES if present_categories.count(c) > 1})

    title_counts: dict[str, int] = {}
    entry_errors: list[dict] = []
    for entry in entries:
        title_counts[entry.title] = title_counts.get(entry.title, 0) + 1
        missing_fields = [
            field for field in REQUIRED_FIELDS if not re.search(rf"^- {re.escape(field)}：", entry.body, re.MULTILINE)
        ]
        if not entry.organized:
            missing_fields.append("可复制整理版")
        if not entry.original:
            missing_fields.append("原始提示词")
        if missing_fields:
            entry_errors.append(
                {"category": entry.category, "title": entry.title, "missing": missing_fields}
            )

    return {
        "category_order": [c for c in present_categories if c in CATEGORIES],
        "missing_categories": missing_categories,
        "duplicate_categories": duplicate_categories,
        "entries_outside_categories": outside,
        "duplicate_titles": sorted(title for title, count in title_counts.items() if count > 1),
        "entry_errors": entry_errors,
    }


def inspect_quick_index(markdown: str, entries: list[Entry]) -> dict:
    start_count = markdown.count(INDEX_START)
    end_count = markdown.count(INDEX_END)
    report = {
        "start_marker_count": start_count,
        "end_marker_count": end_count,
        "marker_order_error": False,
        "category_order": [],
        "category_order_mismatch": False,
        "missing_categories": [],
        "duplicate_categories": [],
        "extra_categories": [],
        "missing_entries": [],
        "stale_links": [],
        "duplicate_links": [],
        "alias_mismatches": [],
        "order_mismatches": [],
        "empty_category_text_errors": [],
        "ok": False,
    }
    if start_count != 1 or end_count != 1:
        return report

    start = markdown.index(INDEX_START) + len(INDEX_START)
    end = markdown.index(INDEX_END)
    if start >= end:
        report["marker_order_error"] = True
        return report

    block = markdown[start:end]
    rows = re.findall(r"^> \*\*(.+?)\*\*：(.*)$", block, flags=re.MULTILINE)
    row_categories = [category.strip() for category, _ in rows]
    report["category_order"] = row_categories
    report["category_order_mismatch"] = row_categories != CATEGORIES
    report["missing_categories"] = [category for category in CATEGORIES if category not in row_categories]
    report["duplicate_categories"] = sorted(
        category for category in CATEGORIES if row_categories.count(category) > 1
    )
    report["extra_categories"] = sorted(
        {category for category in row_categories if category not in CATEGORIES}
    )

    expected_by_category = {category: [] for category in CATEGORIES}
    for entry in entries:
        expected_by_category[entry.category].append(entry.title)

    actual_by_category = {category: [] for category in CATEGORIES}
    all_links: list[tuple[str, str]] = []
    row_text = {category: content.strip() for category, content in rows if category in CATEGORIES}
    for category, content in rows:
        links = INDEX_LINK_PATTERN.findall(content)
        all_links.extend(links)
        if category in actual_by_category:
            actual_by_category[category].extend(target.strip() for target, _ in links)

    expected_titles = [entry.title for entry in entries]
    actual_targets = [target.strip() for target, _ in all_links]
    report["missing_entries"] = [title for title in expected_titles if title not in actual_targets]
    report["stale_links"] = sorted({target for target in actual_targets if target not in expected_titles})
    report["duplicate_links"] = sorted(
        {target for target in actual_targets if actual_targets.count(target) > 1}
    )
    report["alias_mismatches"] = [
        {"target": target.strip(), "alias": alias.strip()}
        for target, alias in all_links
        if target.strip() != alias.strip()
    ]

    for category in CATEGORIES:
        expected = expected_by_category[category]
        actual = actual_by_category[category]
        if row_categories.count(category) == 1 and actual != expected:
            report["order_mismatches"].append(
                {"category": category, "expected": expected, "actual": actual}
            )
        if not expected and row_categories.count(category) == 1 and row_text.get(category) != "暂无":
            report["empty_category_text_errors"].append(category)

    report["ok"] = not any(
        [
            report["marker_order_error"],
            report["category_order_mismatch"],
            report["missing_categories"],
            report["duplicate_categories"],
            report["extra_categories"],
            report["missing_entries"],
            report["stale_links"],
            report["duplicate_links"],
            report["alias_mismatches"],
            report["order_mismatches"],
            report["empty_category_text_errors"],
        ]
    )
    return report


def read_candidate(args: argparse.Namespace) -> str:
    selected = sum(bool(value) for value in [args.candidate_file, args.candidate_stdin])
    if selected > 1:
        raise ValueError("Use only one candidate input method")
    if args.candidate_file:
        return Path(args.candidate_file).read_text(encoding="utf-8")
    if args.candidate_stdin:
        return sys.stdin.read()
    return ""


def compare_candidate(candidate: str, entries: list[Entry], threshold: float) -> dict:
    normalized_candidate = normalize(candidate)
    if not normalized_candidate:
        return {"provided": False, "exact_matches": [], "similar_matches": []}

    exact: list[dict] = []
    similar: list[dict] = []
    for entry in entries:
        best = 0.0
        for text in entry.comparison_texts:
            normalized_entry = normalize(text)
            if normalized_candidate == normalized_entry:
                best = 1.0
                break
            best = max(best, difflib.SequenceMatcher(None, normalized_candidate, normalized_entry).ratio())
        item = {"category": entry.category, "title": entry.title, "similarity": round(best, 4)}
        if best == 1.0:
            exact.append(item)
        elif best >= threshold:
            similar.append(item)

    similar.sort(key=lambda item: item["similarity"], reverse=True)
    return {"provided": True, "exact_matches": exact, "similar_matches": similar[:5]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--note", type=Path, default=CONFIG.prompt_box, help="Path to 小陌的AI百宝箱.md")
    parser.add_argument("--check", action="store_true", help="Report structure without a candidate")
    parser.add_argument("--candidate-file", help="UTF-8 file containing one candidate prompt")
    parser.add_argument("--candidate-stdin", action="store_true", help="Read one candidate prompt from stdin")
    parser.add_argument("--threshold", type=float, default=0.82, help="Near-duplicate threshold")
    args = parser.parse_args()

    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")

    note = args.note.resolve()
    if not note.is_file():
        parser.error(f"note not found: {note}")

    markdown = note.read_text(encoding="utf-8")
    entries, outside = parse_entries(markdown)
    try:
        candidate = read_candidate(args)
    except ValueError as error:
        parser.error(str(error))

    quick_index = inspect_quick_index(markdown, entries)
    report = {
        "note": str(note),
        "entry_count": len(entries),
        "structure": inspect_structure(markdown, entries, outside),
        "quick_index": quick_index,
        "candidate": compare_candidate(candidate, entries, args.threshold),
    }
    structure_ok = not any(
        [
            report["structure"]["missing_categories"],
            report["structure"]["duplicate_categories"],
            report["structure"]["entries_outside_categories"],
            report["structure"]["duplicate_titles"],
            report["structure"]["entry_errors"],
        ]
    )
    report["ok"] = structure_ok and quick_index["ok"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
