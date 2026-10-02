from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    props: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([^:#][^:]*):\s*(.*)$", line)
        if match:
            props[match.group(1).strip()] = match.group(2).strip()
    return props


def parse_pages(value: str) -> list[int]:
    return [int(item) for item in re.findall(r"\d+", value)]


def parse_expected_pages(spec: str | None) -> set[int] | None:
    if not spec:
        return None

    pages: set[int] = set()
    for part in re.split(r"[,，\s]+", spec.strip()):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"页码范围倒序：{part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    return pages


def validate_course_structure(
    course_folder: Path, expected_pages: set[int] | None = None
) -> list[str]:
    errors: list[str] = []
    overview = course_folder / "00 - 课程总览.md"
    overview_text = overview.read_text(encoding="utf-8-sig") if overview.exists() else ""
    if not overview.exists():
        errors.append("缺少 00 - 课程总览.md")

    assignments: dict[int, list[str]] = defaultdict(list)
    ordered_lessons: list[tuple[int, Path]] = []

    for path in sorted(course_folder.rglob("*.md")):
        props = parse_frontmatter(path)
        if props.get("类型") != "分集笔记":
            continue
        unit = props.get("聚合单位", "")
        if unit and unit != "课":
            continue
        if not unit and "包含P" not in props:
            continue

        pages = parse_pages(props.get("包含P", ""))
        if not pages:
            errors.append(f"{path.name}: 课级笔记缺少有效 包含P")
            continue
        if pages != sorted(pages):
            errors.append(f"{path.name}: 包含P 未按升序排列")
        if len(pages) != len(set(pages)):
            errors.append(f"{path.name}: 包含P 存在重复页码")

        start = parse_pages(props.get("P", ""))
        if not start or start[0] != pages[0]:
            errors.append(f"{path.name}: P 必须等于 包含P 的第一个页码")
        else:
            ordered_lessons.append((start[0], path))

        for page in pages:
            assignments[page].append(path.name)

        if overview_text and not re.search(rf"\[\[{re.escape(path.stem)}(?:\||\]\])", overview_text):
            errors.append(f"课程总览缺少课级链接：{path.stem}")

    if not ordered_lessons:
        errors.append("没有找到 聚合单位: 课 的分集笔记")
    starts = [item[0] for item in ordered_lessons]
    if starts != sorted(starts):
        errors.append("课级笔记的起始 P 与文件排序不一致")

    duplicates = {page: names for page, names in assignments.items() if len(names) > 1}
    for page, names in sorted(duplicates.items()):
        errors.append(f"P{page} 被重复归入：{'、'.join(names)}")

    if expected_pages is not None:
        actual = set(assignments)
        missing = sorted(expected_pages - actual)
        extra = sorted(actual - expected_pages)
        if missing:
            errors.append("缺少请求页码：" + "、".join(f"P{page}" for page in missing))
        if extra:
            errors.append("出现范围外页码：" + "、".join(f"P{page}" for page in extra))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate grouped Bilibili course notes.")
    parser.add_argument("course_folder", type=Path)
    parser.add_argument(
        "--expected-pages",
        help="Expected page set, for example 5-19 or 1,2,4-8.",
    )
    args = parser.parse_args()

    folder = args.course_folder.resolve()
    if not folder.is_dir():
        print(f"ERROR: 课程目录不存在：{folder}")
        return 1

    try:
        expected = parse_expected_pages(args.expected_pages)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    errors = validate_course_structure(folder, expected)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    assigned = sorted(expected) if expected is not None else []
    suffix = f"，覆盖 P{assigned[0]}-P{assigned[-1]}" if assigned else ""
    print(f"OK: {folder}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
