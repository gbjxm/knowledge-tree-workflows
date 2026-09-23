from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config
from validate_note import check_mastery_extension, check_optional_learning_states, check_v21_source


CONFIG = load_config()

SOURCE_TYPES = {"材料总览", "分集笔记"}
V2_SOURCE_PROPERTIES = {"适用阶段", "沉淀状态", "已沉淀主题", "待沉淀主题"}
V2_TOPIC_PROPERTIES = {
    "解决问题",
    "适用阶段",
    "知识状态",
    "成熟度",
    "上位主题",
    "相关主题",
    "最后复核",
}
V21_TOPIC_PROPERTIES = {"证据状态"}
MASTERY_STATES = ("未检验", "能复述", "能辨析", "能迁移")
PROJECT_PROPERTIES = {
    "项目",
    "项目阶段",
    "适用阶段",
    "当前问题",
    "调用知识",
    "验证状态",
    "复盘日期",
}
WIKILINK_RE = re.compile(r"!?(?<!\!)\[\[([^\]]+)\]\]")


def parse_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
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
        props[key.strip()] = value.strip()
    return raw, props


def is_v2(props: dict[str, str]) -> bool:
    return props.get("知识库版本", "").strip().strip('"\'') in {"2", "2.0", "2.1"}


def is_v21(props: dict[str, str]) -> bool:
    return props.get("知识库版本", "").strip().strip('"\'') == "2.1"


def property_has_value(raw: str, key: str) -> bool:
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline and inline not in {"[]", "null", "~"}:
            return True
        for following in lines[index + 1 :]:
            if following and not following.startswith((" ", "\t")):
                break
            if re.match(r"^\s+-\s+\S", following):
                return True
        return False
    return False


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
        return source if "#" in target and not target.split("#", 1)[0].strip() else None

    if key in by_relative:
        return by_relative[key]

    source_relative = source.parent.relative_to(vault).as_posix().casefold()
    local_key = f"{source_relative}/{key}".strip("/")
    if local_key in by_relative:
        return by_relative[local_key]

    stem = Path(key).name.casefold()
    matches = by_stem.get(stem, [])
    if len(matches) == 1:
        return matches[0]
    return None


def display_paths(vault: Path, paths: list[Path], limit: int = 20) -> None:
    for path in paths[:limit]:
        print(f"  - {path.relative_to(vault)}")
    if len(paths) > limit:
        print(f"  - ... 另有 {len(paths) - limit} 项")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an Obsidian creative knowledge system.")
    parser.add_argument("--vault", type=Path, default=CONFIG.vault)
    parser.add_argument("--scope", default=".", help="Relative folder to audit; links still resolve vault-wide.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    vault = args.vault.resolve()
    scope = (vault / args.scope).resolve()
    if not vault.exists() or not scope.exists() or vault not in (scope, *scope.parents):
        raise SystemExit("Vault or scope does not exist, or scope is outside the vault.")

    all_files = markdown_files(vault)
    scoped_files = [path for path in all_files if path == scope or scope in path.parents]
    by_relative, by_stem = build_indexes(vault, all_files)

    type_counts: Counter[str] = Counter()
    v2_count = 0
    v21_count = 0
    empty_notes: list[Path] = []
    pending_sources: list[Path] = []
    pending_understanding: list[Path] = []
    unanswered_questions: list[Path] = []
    weak_evidence: list[Path] = []
    conflicts: list[Path] = []
    topics_without_sources: list[Path] = []
    v2_errors: list[tuple[Path, list[str]]] = []
    dangling: list[tuple[Path, str]] = []
    links_to_empty: list[tuple[Path, Path]] = []
    traceability_errors: list[str] = []
    raw_artifacts: list[Path] = []
    naked_video_links: list[Path] = []
    mastery_counts: Counter[str] = Counter()
    mastery_errors: list[tuple[Path, str]] = []
    learning_errors: list[tuple[Path, str]] = []

    texts: dict[Path, str] = {}
    metadata: dict[Path, tuple[str, dict[str, str]]] = {}
    for path in all_files:
        text = path.read_text(encoding="utf-8-sig")
        texts[path] = text
        metadata[path] = parse_frontmatter(text)

    for path in scoped_files:
        text = texts[path]
        if not text.strip():
            empty_notes.append(path)

        raw, props = metadata[path]
        note_type = props.get("类型", "未分类") or "未分类"
        type_counts[note_type] += 1

        if is_v2(props):
            v2_count += 1
            missing: list[str] = []
            if note_type in SOURCE_TYPES:
                missing = sorted(V2_SOURCE_PROPERTIES - props.keys())
            elif note_type == "主题笔记":
                missing = sorted(V2_TOPIC_PROPERTIES - props.keys())
            elif note_type == "项目应用":
                missing = sorted(PROJECT_PROPERTIES - props.keys())
            if missing:
                v2_errors.append((path, missing))
        if is_v21(props):
            v21_count += 1
            missing = []
            if note_type == "主题笔记":
                missing = sorted(V21_TOPIC_PROPERTIES - props.keys())
            if missing:
                v2_errors.append((path, missing))

        if note_type in SOURCE_TYPES and props.get("沉淀状态", "") != "已沉淀":
            pending_sources.append(path)
        if note_type in SOURCE_TYPES and props.get("理解状态") in {"待理解", "理解中"}:
            pending_understanding.append(path)
        if note_type in SOURCE_TYPES and props.get("关键问题状态") == "待回答":
            unanswered_questions.append(path)
        if note_type == "主题笔记" and not property_has_value(raw, "来源材料"):
            topics_without_sources.append(path)
        if note_type == "主题笔记" and props.get("证据状态", "") in {"", "单一来源"}:
            weak_evidence.append(path)
        if note_type == "主题笔记" and props.get("证据状态", "") == "存在争议":
            conflicts.append(path)
        state_errors: list[str] = []
        check_optional_learning_states(props, state_errors)
        if note_type in SOURCE_TYPES and is_v21(props):
            check_v21_source(text, props, note_type, state_errors)
        learning_errors.extend((path, error) for error in state_errors)
        if note_type == "主题笔记":
            mastery = props.get("掌握状态", "").strip() or "未检验"
            mastery_counts[mastery if mastery in MASTERY_STATES else "未检验"] += 1
            topic_mastery_errors: list[str] = []
            check_mastery_extension(text, props, topic_mastery_errors)
            mastery_errors.extend((path, error) for error in topic_mastery_errors)
        if re.search(r"^(?:视频|来源)[:：]\s*https?://", text, flags=re.MULTILINE):
            naked_video_links.append(path)

        for target in WIKILINK_RE.findall(text):
            resolved = resolve_link(vault, path, target, by_relative, by_stem)
            if resolved is None:
                if target_key(target) is not None:
                    dangling.append((path, target))
                continue
            if not texts.get(resolved, "").strip():
                links_to_empty.append((path, resolved))

    for path in scope.rglob("*"):
        if path.is_file() and path.name.lower() in {
            "metadata.json",
            "transcript.md",
            "subtitle.json",
            "audio.m4s",
        }:
            raw_artifacts.append(path)

    def in_scope(path: Path) -> bool:
        return path == scope or scope in path.parents

    for source in all_files:
        source_raw, source_props = metadata[source]
        if source_props.get("类型") not in SOURCE_TYPES or not is_v2(source_props):
            continue
        for target in property_links(source_raw, "已沉淀主题"):
            topic = resolve_link(vault, source, target, by_relative, by_stem)
            if topic is None:
                continue
            topic_raw, topic_props = metadata[topic]
            if topic_props.get("类型") != "主题笔记":
                if in_scope(source) or in_scope(topic):
                    traceability_errors.append(
                        f"{source.relative_to(vault)} 的已沉淀主题不是主题笔记：{topic.relative_to(vault)}"
                    )
                continue
            reverse_sources = {
                resolve_link(vault, topic, link, by_relative, by_stem)
                for link in property_links(topic_raw, "来源材料")
            }
            if source not in reverse_sources and (in_scope(source) or in_scope(topic)):
                traceability_errors.append(
                    f"{source.relative_to(vault)} -> {topic.relative_to(vault)} 缺少主题到来源的回链"
                )

    for topic in all_files:
        topic_raw, topic_props = metadata[topic]
        if topic_props.get("类型") != "主题笔记" or not is_v2(topic_props):
            continue
        for target in property_links(topic_raw, "来源材料"):
            source = resolve_link(vault, topic, target, by_relative, by_stem)
            if source is None:
                continue
            source_raw, source_props = metadata[source]
            if source_props.get("类型") not in SOURCE_TYPES or not is_v2(source_props):
                continue
            deposited_topics = {
                resolve_link(vault, source, link, by_relative, by_stem)
                for link in property_links(source_raw, "已沉淀主题")
            }
            if topic not in deposited_topics and (in_scope(source) or in_scope(topic)):
                traceability_errors.append(
                    f"{topic.relative_to(vault)} -> {source.relative_to(vault)} 缺少来源到主题的回链"
                )

    print("知识系统审计")
    print(f"Vault: {vault}")
    print(f"Scope: {scope.relative_to(vault) if scope != vault else '.'}")
    print(f"Markdown: {len(scoped_files)}；V2/V2.1: {v2_count}；V2.1: {v21_count}")
    print("类型: " + "，".join(f"{name}={count}" for name, count in sorted(type_counts.items())))
    print(
        f"待沉淀来源: {len(pending_sources)}；待理解: {len(pending_understanding)}；"
        f"待回答: {len(unanswered_questions)}；无来源主题: {len(topics_without_sources)}"
    )
    print(f"证据薄弱: {len(weak_evidence)}；存在争议: {len(conflicts)}")
    print("掌握状态: " + "；".join(f"{state}={mastery_counts[state]}" for state in MASTERY_STATES))
    print(f"空白笔记: {len(empty_notes)}；失效链接: {len(dangling)}；链接到空白笔记: {len(links_to_empty)}")
    print(
        f"V2/V2.1 属性错误: {len(v2_errors)}；沉淀回链错误: {len(traceability_errors)}；"
        f"掌握字段错误: {len(mastery_errors)}；学习字段错误: {len(learning_errors)}；原始产物: {len(raw_artifacts)}；裸视频链接: {len(naked_video_links)}"
    )

    if empty_notes:
        print("\n空白笔记:")
        display_paths(vault, empty_notes)
    if dangling:
        print("\n失效链接:")
        for source, target in dangling[:20]:
            print(f"  - {source.relative_to(vault)} -> [[{target}]]")
        if len(dangling) > 20:
            print(f"  - ... 另有 {len(dangling) - 20} 项")
    if links_to_empty:
        print("\n链接到空白笔记:")
        for source, target in links_to_empty[:20]:
            print(f"  - {source.relative_to(vault)} -> {target.relative_to(vault)}")
    if v2_errors:
        print("\nV2/V2.1 属性错误:")
        for path, missing in v2_errors:
            print(f"  - {path.relative_to(vault)}: 缺少 {'、'.join(missing)}")
    if traceability_errors:
        print("\n沉淀回链错误:")
        for error in traceability_errors[:20]:
            print(f"  - {error}")
    if mastery_errors:
        print("\n掌握字段错误:")
        for path, error in mastery_errors[:20]:
            print(f"  - {path.relative_to(vault)}: {error}")
    if learning_errors:
        print("\n学习字段错误:")
        for path, error in learning_errors[:20]:
            print(f"  - {path.relative_to(vault)}: {error}")
    if raw_artifacts:
        print("\n最终目录中的原始产物:")
        display_paths(vault, raw_artifacts)
    if naked_video_links:
        print("\n裸视频链接:")
        display_paths(vault, naked_video_links)

    critical_count = (
        len(empty_notes)
        + len(dangling)
        + len(links_to_empty)
        + len(v2_errors)
        + len(traceability_errors)
        + len(mastery_errors)
        + len(learning_errors)
        + len(raw_artifacts)
        + len(naked_video_links)
    )
    return 1 if args.strict and critical_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
