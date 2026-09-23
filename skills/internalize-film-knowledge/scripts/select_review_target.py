from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


CONFIG = load_config()
DEFAULT_VAULT = CONFIG.vault
DEFAULT_LIBRARY = CONFIG.knowledge_library
DEFAULT_NORTH_STAR = CONFIG.control_root / "我的知识树北极星.md"
TOPIC_VERSIONS = {"2", "2.0", "2.1"}
MASTERY_ORDER = {"未检验": 0, "能复述": 1, "能辨析": 2, "能迁移": 3}
REQUIRED_PROPERTIES = {
    "类型",
    "分类",
    "状态",
    "材料类型",
    "信息来源",
    "完整程度",
    "整理日期",
    "知识库版本",
    "主题域",
    "解决问题",
    "适用阶段",
    "来源材料",
    "关联项目",
    "知识状态",
    "成熟度",
    "上位主题",
    "相关主题",
    "最后复核",
}
REQUIRED_HEADINGS = {
    "核心命题",
    "适用边界",
    "学习材料",
    "内容导览",
    "知识单元",
    "项目应用与验证",
}


@dataclass(frozen=True)
class Topic:
    path: Path
    relative_path: str
    title: str
    category: str
    version: str
    mastery: str
    last_review: str
    core_proposition: str
    solution_problem: str
    source_question: str
    mastery_fields_present: bool
    missing_properties: tuple[str, ...]
    missing_headings: tuple[str, ...]

    @property
    def compatible(self) -> bool:
        return self.version in TOPIC_VERSIONS and not self.missing_properties and not self.missing_headings


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, flags=re.DOTALL)
    if not match:
        return {}
    props: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        props[key.strip()] = value.strip().strip("\"'")
    return props


def headings(text: str) -> set[str]:
    return set(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))


def extract_h1(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def extract_section_first_line(text: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    for line in match.group(1).splitlines():
        clean = re.sub(r"^\s*(?:[-*]>|\d+\.)\s*", "", line).strip()
        if clean and not clean.startswith(("<!--", "[!")):
            return clean
    return ""


def extract_open_question(text: str) -> str:
    section = re.search(
        r"^##\s+我的理解、疑问与联想\s*$\r?\n(.*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    body = section.group(1) if section else text
    match = re.search(
        r"^>\s*\[!question\][^\r\n]*\r?\n>\s*(.+?)\s*$",
        body,
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def read_topic(path: Path, vault: Path) -> Topic | None:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    props = parse_frontmatter(text)
    if props.get("类型") != "主题笔记":
        return None

    version = props.get("知识库版本", "").strip()
    required = set(REQUIRED_PROPERTIES)
    required_headings = set(REQUIRED_HEADINGS)
    if version == "2.1":
        required.add("证据状态")
        required_headings.add("外部补充与分歧")

    raw_mastery = props.get("掌握状态", "").strip()
    mastery = raw_mastery if raw_mastery in MASTERY_ORDER else "未检验"
    return Topic(
        path=path,
        relative_path=path.relative_to(vault).as_posix(),
        title=extract_h1(text, path.stem),
        category=props.get("分类", "未分类").strip() or "未分类",
        version=version,
        mastery=mastery,
        last_review=props.get("最近检验", "").strip(),
        core_proposition=extract_section_first_line(text, "核心命题"),
        solution_problem=props.get("解决问题", "").strip(),
        source_question=extract_open_question(text),
        mastery_fields_present="掌握状态" in props and "最近检验" in props,
        missing_properties=tuple(sorted(required - props.keys())),
        missing_headings=tuple(sorted(required_headings - headings(text))),
    )


def scan_topics(vault: Path, library: Path) -> list[Topic]:
    vault = vault.resolve()
    library = library.resolve()
    if library != vault and not library.is_relative_to(vault):
        raise ValueError(f"Knowledge library must stay inside the selected vault: {library}")
    if not library.exists():
        return []
    topics: list[Topic] = []
    for path in sorted(library.rglob("*.md")):
        if any(part in {".obsidian", ".trash"} for part in path.parts):
            continue
        topic = read_topic(path, vault)
        if topic:
            topics.append(topic)
    return topics


def current_focus(north_star: Path) -> str:
    try:
        props = parse_frontmatter(north_star.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        return "故事与剧本"
    return props.get("当前重点", "故事与剧本").strip() or "故事与剧本"


def date_key(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def matches_explicit(topic: Topic, query: str, vault: Path) -> bool:
    normalized = query.strip().replace("\\", "/")
    if not normalized:
        return False
    candidates = {
        topic.title.casefold(),
        topic.path.stem.casefold(),
        topic.relative_path.casefold(),
        topic.relative_path.removesuffix(".md").casefold(),
    }
    try:
        query_path = Path(query).resolve()
        if query_path == topic.path.resolve():
            return True
    except OSError:
        pass
    vault_candidate = (vault / normalized).with_suffix(".md") if not normalized.lower().endswith(".md") else vault / normalized
    try:
        if vault_candidate.resolve() == topic.path.resolve():
            return True
    except OSError:
        pass
    return normalized.casefold() in candidates


def suggested_question(topic: Topic) -> str:
    subject = topic.solution_problem or topic.title
    if topic.mastery == "未检验":
        return f"不看笔记，你会怎样用自己的话说清“{subject}”背后的核心因果关系？"
    if topic.mastery == "能复述":
        return f"关于“{topic.title}”，什么情况下这条方法会失效，或者最容易被误用成什么？"
    return f"换到一个你没用过的新故事或新场景，你会怎样应用“{topic.title}”，第一步看什么，为什么？"


def selection_payload(topic: Topic, mode: str, focus: str) -> dict[str, object]:
    return {
        "status": "selected",
        "selection": mode,
        "path": str(topic.path),
        "relative_path": topic.relative_path,
        "title": topic.title,
        "category": topic.category,
        "current_focus": focus,
        "knowledge_version": topic.version,
        "mastery_state": topic.mastery,
        "last_review": topic.last_review,
        "needs_mastery_fields": not topic.mastery_fields_present,
        "source_question": topic.source_question,
        "open_question": topic.source_question,
        "core_proposition": topic.core_proposition,
        "solution_problem": topic.solution_problem,
        "suggested_question": suggested_question(topic),
        "question_basis": "按当前掌握层级生成；主题长期疑问只作背景，不冒充已选来源的当前关键问题",
    }


def choose(
    vault: Path,
    explicit: str = "",
    category: str = "",
    library: Path | None = None,
    north_star: Path | None = None,
    learning_root: Path | None = None,
) -> dict[str, object]:
    vault = vault.resolve()
    library = (library or DEFAULT_LIBRARY).resolve()
    north_star = (north_star or library / "00-待归档与知识地图" / "我的知识树北极星.md").resolve()
    if north_star != library and not north_star.is_relative_to(library):
        raise ValueError(f"North Star must stay inside the selected knowledge library: {north_star}")
    # Only borrow configured zone paths for this exact vault/library pair.
    if learning_root is None and vault == CONFIG.vault and library == CONFIG.knowledge_library:
        learning_root = CONFIG.learning_root
    if learning_root is not None:
        learning_root = learning_root.resolve()
        if learning_root == library or not learning_root.is_relative_to(library):
            raise ValueError(f"Learning root must stay inside the selected knowledge library: {learning_root}")
    # A named topic remains available anywhere in the shared library; automatic
    # learning suggestions only consider the explicitly configured learning zone.
    topics = scan_topics(vault, library if explicit else learning_root or library)
    focus = current_focus(north_star)

    if explicit:
        matches = [topic for topic in topics if matches_explicit(topic, explicit, vault)]
        if not matches:
            return {"status": "not_found", "query": explicit}
        topic = sorted(matches, key=lambda item: item.relative_path.casefold())[0]
        if not topic.compatible:
            return {
                "status": "requires_upgrade",
                "selection": "explicit",
                "path": str(topic.path),
                "relative_path": topic.relative_path,
                "title": topic.title,
                "knowledge_version": topic.version or "legacy",
                "missing_properties": list(topic.missing_properties),
                "missing_headings": list(topic.missing_headings),
                "preview": "当前仍可只读讲解或讨论；仅在明确要求保存且需要结构升级时，预览现有 V2/V2.1 主题契约缺口，确认后再写回。当前未修改文件。",
            }
        return selection_payload(topic, "explicit", focus)

    eligible = [topic for topic in topics if topic.compatible and topic.mastery != "能迁移"]
    if category:
        eligible = [topic for topic in eligible if topic.category == category]
    if not eligible:
        return {"status": "no_target", "category": category or None}

    topic = min(
        eligible,
        key=lambda item: (
            0 if item.category == focus else 1,
            MASTERY_ORDER[item.mastery],
            date_key(item.last_review),
            item.relative_path.casefold(),
        ),
    )
    return selection_payload(topic, "automatic", focus)


def main() -> int:
    parser = argparse.ArgumentParser(description="Select one film-knowledge topic for review without modifying the vault.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--north-star", type=Path, default=None)
    parser.add_argument("--learning-root", type=Path, default=None, help="Optional learning zone within the selected library; defaults to the matching configuration.")
    parser.add_argument("--topic", default="", help="Explicit note title, stem, path, or vault-relative path.")
    parser.add_argument("--category", default="", help="Restrict automatic selection to one category.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = choose(args.vault, args.topic, args.category, args.library, args.north_star, args.learning_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0 if result["status"] in {"selected", "requires_upgrade"} else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
