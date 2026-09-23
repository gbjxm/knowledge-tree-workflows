from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()
DEFAULT_VAULT = CONFIG.vault
DEFAULT_LIBRARY_RELATIVE = CONFIG.knowledge_library.relative_to(CONFIG.vault)
CATEGORIES = (
    "故事与剧本",
    "导演与视听语言",
    "摄影美术与现场制作",
    "声音与后期",
    "创作实践与项目复盘",
    "行业观察与灵感素材",
)
RELATION_TYPES = {"前置", "转译", "实现", "制约", "验证", "反馈", "冲突", "互补", "对照"}
BASIS_TYPES = {"来源明示", "现有笔记明示", "多源综合", "Codex综合", "项目验证"}
TABLE_HEADER = ("相关主题", "分类", "关系", "连接理由", "依据")
SAME_HEADING = "同类知识连接"
CROSS_HEADING = "跨域连接"
WIKILINK_RE = re.compile(r"!?(?<!\!)\[\[([^\]]+)\]\]")


@dataclass(frozen=True)
class ConnectionRow:
    target: str
    category: str
    relation: str
    reason: str
    basis: str
    line: int
    section: str


def parse_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    if not text.startswith(("---\n", "---\r\n")):
        return "", {}
    newline = "\r\n" if text.startswith("---\r\n") else "\n"
    closing = text.find(f"{newline}---", 4)
    if closing < 0:
        return "", {}
    raw = text[: closing + len(newline) + 3]
    props: dict[str, str] = {}
    for line in raw.splitlines()[1:]:
        if line == "---" or not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        props[key.strip()] = value.strip().strip("\"'")
    return raw, props


def property_text(raw: str, key: str) -> str:
    lines = raw.splitlines()
    collected: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if not match:
            continue
        collected.append(match.group(1))
        for following in lines[index + 1 :]:
            if following and not following.startswith((" ", "\t")):
                break
            collected.append(following)
        break
    return "\n".join(collected)


def strip_scalar(value: str) -> str:
    return value.strip().strip("\"'").strip()


def property_values(raw: str, key: str) -> list[str]:
    value = property_text(raw, key)
    if not value.strip():
        return []
    lines = value.splitlines()
    inline = lines[0].strip()
    values: list[str] = []
    if inline.startswith("[") and inline.endswith("]"):
        body = inline[1:-1].strip()
        if body:
            values.extend(strip_scalar(item) for item in body.split(","))
    elif inline not in {"", "[]", "null", "~"}:
        values.append(strip_scalar(inline))
    for line in lines[1:]:
        match = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if match:
            values.append(strip_scalar(match.group(1)))
    return [value for value in values if value]


def property_links(raw: str, key: str) -> list[str]:
    return WIKILINK_RE.findall(property_text(raw, key))


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if ".obsidian" not in path.parts and ".trash" not in path.parts
    )


def target_key(target: str) -> str | None:
    target = target.split("|", 1)[0].split("#", 1)[0].strip().replace("\\", "/")
    if not target:
        return None
    suffix = Path(target).suffix.lower()
    if suffix and suffix != ".md":
        return None
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target.strip("/").casefold()


def build_indexes(vault: Path, files: list[Path]) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    by_relative: dict[str, Path] = {}
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        relative = path.relative_to(vault).with_suffix("").as_posix().casefold()
        by_relative[relative] = path
        by_stem[path.stem.casefold()].append(path)
    return by_relative, by_stem


def resolve_link(
    vault: Path,
    source: Path,
    target: str,
    by_relative: dict[str, Path],
    by_stem: dict[str, list[Path]],
) -> Path | None:
    key = target_key(target)
    if key is None:
        return None
    if key in by_relative:
        return by_relative[key]
    local_key = f"{source.parent.relative_to(vault).as_posix().casefold()}/{key}".strip("/")
    if local_key in by_relative:
        return by_relative[local_key]
    matches = by_stem.get(Path(key).name.casefold(), [])
    return matches[0] if len(matches) == 1 else None


def split_table_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    in_wikilink = False
    index = 0
    while index < len(value):
        pair = value[index : index + 2]
        if pair == "[[":
            in_wikilink = True
            current.append(pair)
            index += 2
            continue
        if pair == "]]":
            in_wikilink = False
            current.append(pair)
            index += 2
            continue
        char = value[index]
        if char == "|" and not in_wikilink:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def extract_section_rows(text: str, heading: str) -> tuple[list[ConnectionRow], list[str]]:
    match = re.search(
        rf"^###\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^#{{2,3}}\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return [], []
    rows: list[ConnectionRow] = []
    errors: list[str] = []
    table_lines = [
        (text[: match.start(1)].count("\n") + offset + 1, line)
        for offset, line in enumerate(match.group(1).splitlines())
        if line.strip().startswith("|")
    ]
    if not table_lines:
        return [], [f"{heading}标题下缺少 Markdown 表格"]
    header = split_table_row(table_lines[0][1])
    if tuple(header) != TABLE_HEADER:
        errors.append(f"{heading}表头必须是：" + "、".join(TABLE_HEADER))
    for line_number, line in table_lines[1:]:
        cells = split_table_row(line)
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) != 5:
            errors.append(f"第 {line_number} 行必须包含 5 列")
            continue
        links = WIKILINK_RE.findall(cells[0])
        if len(links) != 1:
            errors.append(f"第 {line_number} 行相关主题必须包含且只包含一个 wikilink")
            continue
        rows.append(ConnectionRow(links[0], cells[1], cells[2], cells[3], cells[4], line_number, heading))
    if not rows:
        errors.append(f"{heading}表没有有效数据行")
    return rows, errors


def extract_rows(text: str) -> tuple[list[ConnectionRow], list[str]]:
    rows: list[ConnectionRow] = []
    errors: list[str] = []
    for heading in (SAME_HEADING, CROSS_HEADING):
        section_rows, section_errors = extract_section_rows(text, heading)
        rows.extend(section_rows)
        errors.extend(section_errors)
    return rows, errors


def has_substantive_content(text: str, raw_frontmatter: str) -> bool:
    body = text[len(raw_frontmatter) :] if raw_frontmatter else text
    body = re.sub(
        r"^##\s+相关知识\s*$.*?(?=^##\s+|\Z)",
        "",
        body,
        flags=re.MULTILINE | re.DOTALL,
    )
    for line in body.splitlines():
        value = line.strip()
        if not value or value.startswith("#") or value.startswith("<!--") or value.startswith("-->"):
            continue
        if re.fullmatch(r"\|?\s*:?-{3,}.*", value):
            continue
        return True
    return False


def resolve_topic_argument(
    vault: Path,
    value: str,
    by_relative: dict[str, Path],
    by_stem: dict[str, list[Path]],
) -> Path | None:
    candidate = Path(value)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()
    key = target_key(value)
    if key and key in by_relative:
        return by_relative[key]
    if key:
        matches = by_stem.get(Path(key).name.casefold(), [])
        if len(matches) == 1:
            return matches[0]
    relative = (vault / value).resolve()
    return relative if relative.exists() else None


def audit(
    vault: Path,
    topic_arguments: list[str] | None = None,
    library_relative: Path | str = DEFAULT_LIBRARY_RELATIVE,
) -> dict[str, object]:
    vault = vault.resolve()
    library = (vault / Path(library_relative)).resolve()
    if not vault.exists() or not library.exists() or library != vault and vault not in library.parents:
        raise ValueError("Vault or configured film knowledge library does not exist inside the vault.")

    files = markdown_files(vault)
    by_relative, by_stem = build_indexes(vault, files)
    texts: dict[Path, str] = {}
    metadata: dict[Path, tuple[str, dict[str, str]]] = {}
    topics: list[Path] = []
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        raw, props = parse_frontmatter(text)
        texts[path] = text
        metadata[path] = (raw, props)
        if props.get("类型") == "主题笔记" and (path == library or library in path.parents):
            topics.append(path)

    selected = topics
    if topic_arguments:
        selected = []
        for value in topic_arguments:
            path = resolve_topic_argument(vault, value, by_relative, by_stem)
            if path is None or path not in topics:
                raise ValueError(f"Cannot resolve topic note: {value}")
            selected.append(path)
        selected = sorted(set(selected))

    rows_by_topic: dict[Path, list[ConnectionRow]] = {}
    row_parse_errors: dict[Path, list[str]] = {}
    related_targets: dict[Path, set[Path]] = {}
    unresolved_related: dict[Path, list[str]] = {}
    for path in topics:
        rows, errors = extract_rows(texts[path])
        rows_by_topic[path] = rows
        row_parse_errors[path] = errors
        raw, _ = metadata[path]
        resolved: set[Path] = set()
        unresolved: list[str] = []
        for link in property_links(raw, "相关主题"):
            target = resolve_link(vault, path, link, by_relative, by_stem)
            if target is None:
                unresolved.append(link)
            else:
                resolved.add(target)
        related_targets[path] = resolved
        unresolved_related[path] = unresolved

    errors: list[dict[str, str]] = []
    semantic_edges: set[tuple[str, str]] = set()
    same_edges: set[tuple[str, str]] = set()
    cross_edges: set[tuple[str, str]] = set()
    semantic_connected: set[Path] = set()
    cross_connected: set[Path] = set()
    navigation_hints = 0

    def add_error(path: Path, message: str) -> None:
        errors.append({"path": path.relative_to(vault).as_posix(), "message": message})

    for path in selected:
        raw, props = metadata[path]
        source_category = props.get("分类", "")
        rows = rows_by_topic[path]
        for message in row_parse_errors[path]:
            add_error(path, message)
        for link in unresolved_related[path]:
            add_error(path, f"相关主题无法解析：[[{link}]]")

        row_targets: set[Path] = set()
        cross_row_targets: set[Path] = set()
        cross_row_categories: set[str] = set()
        seen_targets: set[Path] = set()
        for row in rows:
            target = resolve_link(vault, path, row.target, by_relative, by_stem)
            if row.relation not in RELATION_TYPES:
                add_error(path, f"第 {row.line} 行关系无效：{row.relation}")
            if row.basis not in BASIS_TYPES:
                add_error(path, f"第 {row.line} 行依据无效：{row.basis or '空白'}")
            if not row.reason.strip():
                add_error(path, f"第 {row.line} 行缺少连接理由")
            if row.category not in CATEGORIES:
                add_error(path, f"第 {row.line} 行分类无效：{row.category}")
            if target is None:
                add_error(path, f"第 {row.line} 行目标无法解析：[[{row.target}]]")
                continue
            target_raw, target_props = metadata.get(target, ("", {}))
            if target_props.get("类型") != "主题笔记" or not has_substantive_content(texts.get(target, ""), target_raw):
                add_error(path, f"第 {row.line} 行目标不是有实质内容的主题笔记：{target.relative_to(vault)}")
                continue
            target_category = target_props.get("分类", "")
            is_cross = target_category != source_category
            expected_section = CROSS_HEADING if is_cross else SAME_HEADING
            if row.section != expected_section:
                add_error(path, f"第 {row.line} 行应写入“{expected_section}”而不是“{row.section}”")
            if row.category != target_category:
                add_error(path, f"第 {row.line} 行分类与目标属性不一致：{row.category} != {target_category}")
            if target in seen_targets:
                add_error(path, f"重复的正式知识连接：{target.relative_to(vault)}")
            seen_targets.add(target)
            row_targets.add(target)
            if is_cross:
                cross_row_targets.add(target)
                cross_row_categories.add(target_category)
            if target not in related_targets[path]:
                add_error(path, f"正文连接缺少相关主题属性：{target.relative_to(vault)}")
            if path not in related_targets.get(target, set()):
                add_error(path, f"目标缺少相关主题回链：{target.relative_to(vault)}")
            reverse_rows = rows_by_topic.get(target, [])
            reverse_targets = {
                resolve_link(vault, target, reverse.target, by_relative, by_stem)
                for reverse in reverse_rows
                if reverse.section == expected_section
            }
            if path not in reverse_targets:
                add_error(path, f"目标缺少正文{expected_section}回链：{target.relative_to(vault)}")

            row_valid = (
                row.relation in RELATION_TYPES
                and row.basis in BASIS_TYPES
                and bool(row.reason.strip())
                and row.section == expected_section
                and row.category == target_category
                and target in related_targets[path]
                and path in related_targets.get(target, set())
                and path in reverse_targets
            )
            if row_valid:
                edge = tuple(sorted((path.relative_to(vault).as_posix(), target.relative_to(vault).as_posix())))
                semantic_edges.add(edge)
                semantic_connected.update((path, target))
                if is_cross:
                    cross_edges.add(edge)
                    cross_connected.update((path, target))
                else:
                    same_edges.add(edge)

        navigation_hints += len(
            {
                target
                for target in related_targets[path] - row_targets
                if metadata.get(target, ("", {}))[1].get("类型") == "主题笔记"
            }
        )

        cross_property_targets = {
            target
            for target in related_targets[path]
            if metadata.get(target, ("", {}))[1].get("类型") == "主题笔记"
            and metadata[target][1].get("分类") != source_category
        }
        for target in sorted(cross_property_targets - cross_row_targets):
            add_error(path, f"跨分类相关主题缺少正文连接表：{target.relative_to(vault)}")

        involved = property_values(raw, "涉及分类")
        expected = [category for category in CATEGORIES if category == source_category or category in cross_row_categories]
        if cross_row_targets:
            if len(involved) != len(set(involved)):
                add_error(path, "涉及分类存在重复值")
            invalid = [category for category in involved if category not in CATEGORIES]
            if invalid:
                add_error(path, "涉及分类包含无效值：" + "、".join(invalid))
            if involved != expected:
                add_error(path, "涉及分类必须与已确认跨域连接一致；预期：" + "、".join(expected))
        elif involved:
            add_error(path, "没有正文跨域连接时不应保留涉及分类")

    selected_set = set(selected)
    semantic_selected = selected_set & semantic_connected
    cross_selected = selected_set & cross_connected
    semantic_islands = sorted(selected_set - semantic_selected)
    cross_islands = sorted(selected_set - cross_selected)
    return {
        "vault": str(vault),
        "library": str(library),
        "audited_topics": len(selected),
        "semantic_connected_topics": len(semantic_selected),
        "semantic_edge_count": len(semantic_edges),
        "same_category_edge_count": len(same_edges),
        "cross_category_edge_count": len(cross_edges),
        "semantic_island_count": len(semantic_islands),
        "semantic_islands": [path.relative_to(vault).as_posix() for path in semantic_islands],
        "navigation_hint_count": navigation_hints,
        # Compatibility fields keep existing weekly-review consumers on cross-category semantics.
        "connected_topics": len(cross_selected),
        "edge_count": len(cross_edges),
        "island_count": len(cross_islands),
        "islands": [path.relative_to(vault).as_posix() for path in cross_islands],
        "error_count": len(errors),
        "errors": errors,
    }


def render(report: dict[str, object]) -> str:
    lines = [
        "影视知识关系审计",
        f"Vault: {report['vault']}",
        f"Library: {report['library']}",
        (
            f"主题: {report['audited_topics']}；正式连接主题: {report['semantic_connected_topics']}；"
            f"正式语义连接: {report['semantic_edge_count']}（同类 {report['same_category_edge_count']} / "
            f"跨域 {report['cross_category_edge_count']}）；语义孤岛: {report['semantic_island_count']}"
        ),
        f"未正式化导航/提示指向: {report['navigation_hint_count']}；结构错误: {report['error_count']}",
    ]
    errors = report["errors"]
    assert isinstance(errors, list)
    if errors:
        lines.append("")
        lines.append("错误:")
        for item in errors[:30]:
            lines.append(f"  - {item['path']}: {item['message']}")
        if len(errors) > 30:
            lines.append(f"  - ... 另有 {len(errors) - 30} 项")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit for typed semantic topic connections.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_RELATIVE, help="Knowledge-library path relative to the vault.")
    parser.add_argument("--topic", action="append", default=[], help="Topic path or unique title; repeat as needed.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.vault, args.topic, args.library)
    except ValueError as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 1 if args.strict and report["error_count"] else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
