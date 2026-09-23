from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from knowledge_tree_config import load_config
from obsidian_cli import ObsidianCLI
from knowledge_tree_state import question_text, read_state, resolve_action_context

CONFIG = load_config()
SKILLS_ROOT = CONFIG.skills_root
INTERNALIZE_SCRIPTS = SKILLS_ROOT / "internalize-film-knowledge" / "scripts"
if str(INTERNALIZE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INTERNALIZE_SCRIPTS))

WEAVE_SCRIPTS = SKILLS_ROOT / "weave-film-knowledge-connections" / "scripts"
if str(WEAVE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WEAVE_SCRIPTS))

from select_review_target import MASTERY_ORDER
from audit_connections import audit as audit_cross_domain_connections


CATEGORIES = (
    "故事与剧本",
    "导演与视听语言",
    "摄影美术与现场制作",
    "声音与后期",
    "创作实践与项目复盘",
    "行业观察与灵感素材",
)
SOURCE_TYPES = {"材料总览", "分集笔记"}


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, flags=re.DOTALL)
    if not match:
        return {}
    props: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        props[key.strip()] = value.strip().strip('"\'')
    return props


def extract_section(text: str, heading: str) -> str:
    if heading == "关键问题":
        return question_text(text)
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    for line in match.group(1).splitlines():
        clean = re.sub(r"^\s*(?:[-*]>|\d+\.)\s*", "", line).strip()
        if clean and not clean.startswith("<!--"):
            return clean
    return ""


def extract_callout_question(text: str) -> str:
    match = re.search(
        r"^>\s*\[!question\][^\r\n]*\r?\n>\s*(.+?)\s*$",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def markdown_files(vault: Path) -> list[Path]:
    return sorted(
        path
        for path in vault.rglob("*.md")
        if ".obsidian" not in path.parts and ".trash" not in path.parts
    )


def cli_count(cli: ObsidianCLI, command: str) -> int | None:
    result = cli.run([command, "total"], timeout=10)
    if result.returncode != 0:
        return None
    match = re.search(r"\d+", result.stdout)
    return int(match.group()) if match else None


def coverage_label(count: int, stable: int) -> str:
    if count == 0:
        return "尚无主题入口；具体缺口须核地图"
    return "已有主题入口；覆盖与深度须核地图"


def choose_next_action(
    *,
    connection_report: dict[str, object],
    conflicts: list[str],
    unanswered: list[dict[str, str]],
    pending_understanding: list[dict[str, str]],
    review_target: dict[str, object],
    topic_counts: Counter[str],
    global_state: dict[str, object] | None = None,
    current_task: str = "",
    selected_source: dict[str, object] | None = None,
    related_blockers: list[str] | None = None,
    map_gap_items: list[dict[str, str]] | None = None,
    learning_requested: bool = False,
) -> str:
    # Retain the old call signature for consumers, but backlog/counts are diagnostics only.
    context = resolve_action_context(
        global_state or {"valid": True, "confirmed_actions": [], "pending_choices": []},
        current_task=current_task, selected_source=selected_source,
        related_blockers=related_blockers or [], review_target=review_target, gaps=map_gap_items or [],
        learning_requested=learning_requested,
    )
    return str(context["effective_action"]["text"])


def collect_state(
    vault: Path,
    vault_name: str = CONFIG.vault_name,
    library: Path = CONFIG.knowledge_library,
    *,
    current_task: str = "",
    selected_source: str = "",
    related_blockers: list[str] | None = None,
    include_cli: bool = True,
    learning_requested: bool = False,
) -> dict[str, object]:
    vault = vault.resolve()
    library = library.resolve()
    if library != vault and not library.is_relative_to(vault):
        raise ValueError(f"Knowledge library must stay inside the selected vault: {library}")
    topic_counts: Counter[str] = Counter()
    stable_counts: Counter[str] = Counter()
    pending_understanding: list[dict[str, str]] = []
    unanswered: list[dict[str, str]] = []
    pending_deposit: list[str] = []
    weak_evidence: list[str] = []
    conflicts: list[str] = []
    open_topic_questions: list[dict[str, str]] = []
    mastery_counts: Counter[str] = Counter()
    maturity_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    source_understanding_inventory: list[dict[str, str]] = []
    source_queue_issues: list[dict[str, str]] = []

    for path in markdown_files(vault):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        props = parse_frontmatter(text)
        note_type = props.get("类型", "")
        relative = path.relative_to(vault).as_posix()

        if note_type == "主题笔记" and (path == library or library in path.parents):
            category = props.get("分类", "未分类")
            topic_counts[category] += 1
            if props.get("成熟度") == "稳定":
                stable_counts[category] += 1
            maturity_counts[props.get("成熟度", "未标注")] += 1
            evidence = props.get("证据状态", "")
            evidence_counts[evidence or "未标注"] += 1
            if evidence in {"", "单一来源"}:
                weak_evidence.append(relative)
            if evidence == "存在争议":
                conflicts.append(relative)
            mastery = props.get("掌握状态", "").strip()
            if mastery not in MASTERY_ORDER:
                mastery = "未检验"
            mastery_counts[mastery] += 1
            question = extract_callout_question(text)
            if question:
                open_topic_questions.append(
                    {"path": relative, "question": question, "category": category}
                )

        if note_type in SOURCE_TYPES:
            understanding = props.get("理解状态", "")
            question_state = props.get("关键问题状态", "")
            question = extract_section(text, "关键问题")
            source_understanding_inventory.append({"path": relative, "state": understanding, "question_state": question_state})
            if understanding and understanding != "已理解" and question_state != "不适用":
                pending_understanding.append(
                    {"path": relative, "state": understanding, "question": question}
                )
            if question_state == "待回答":
                if question:
                    unanswered.append({"path": relative, "question": question})
                else:
                    source_queue_issues.append({"path": relative, "reason": "待回答标记缺少当前问题正文"})
            if props.get("沉淀状态") and props.get("沉淀状态") != "已沉淀":
                pending_deposit.append(relative)

    metrics = {key: None for key in ("unresolved", "orphans", "deadends", "tasks")}
    if include_cli:
        cli = ObsidianCLI(vault_name=vault_name, vault_path=vault)
        metrics.update({key: cli_count(cli, key) for key in ("unresolved", "orphans", "deadends")})
        task_result = cli.run(["tasks", "todo", "total"], timeout=10)
        task_match = re.search(r"\d+", task_result.stdout) if task_result.returncode == 0 else None
        metrics["tasks"] = int(task_match.group()) if task_match else None

    coverage = {
        category: {
            "topics": topic_counts[category],
            "stable": stable_counts[category],
            "status": coverage_label(topic_counts[category], stable_counts[category]),
        }
        for category in CATEGORIES
    }
    try:
        connection_report = audit_cross_domain_connections(
            vault,
            library_relative=library.relative_to(vault),
        )
    except (OSError, ValueError):
        connection_report = {
            "connected_topics": 0,
            "edge_count": 0,
            "island_count": 0,
            "islands": [],
            "same_category_edge_count": 0,
            "cross_category_edge_count": 0,
            "navigation_hint_count": 0,
            "semantic_island_count": 0,
            "error_count": 0,
        }

    action_context = read_state(
        vault, library, current_task=current_task, selected_source=selected_source,
        related_blockers=related_blockers or [], learning_requested=learning_requested,
    )

    return {
        "coverage": coverage,
        "pending_understanding": pending_understanding,
        "unanswered_questions": unanswered,
        "pending_deposit": pending_deposit,
        "weak_evidence": weak_evidence,
        "conflicts": conflicts,
        "open_topic_questions": open_topic_questions,
        "mastery": {state: mastery_counts[state] for state in MASTERY_ORDER},
        "maturity": dict(maturity_counts),
        "evidence": dict(evidence_counts),
        "source_understanding_inventory": source_understanding_inventory,
        "source_queue_issues": source_queue_issues,
        "connections": connection_report,
        "review_target": action_context["review_target"],
        "cli": metrics,
        "action_context": action_context,
        "next_action": action_context["effective_action"]["text"],
        "next_action_adopted": action_context["effective_action"]["adopted"],
        "system_suggestion": action_context["system_suggestion"],
    }


def render_markdown(state: dict[str, object]) -> str:
    lines = [
        "# 知识树周复盘",
        "",
        "## 六类覆盖",
        "",
        "| 分类 | 主题数 | 成熟度标为稳定 | 入口盘点 |",
        "|---|---:|---:|---|",
    ]
    coverage = state["coverage"]
    assert isinstance(coverage, dict)
    for category in CATEGORIES:
        item = coverage[category]
        lines.append(f"| {category} | {item['topics']} | {item['stable']} | {item['status']} |")

    metrics = state["cli"]
    assert isinstance(metrics, dict)
    mastery = state["mastery"]
    assert isinstance(mastery, dict)
    connections = state["connections"]
    assert isinstance(connections, dict)
    lines.extend(
        [
            "",
            "## 内化状态",
            "",
            "| 未检验 | 能复述 | 能辨析 | 能迁移 |",
            "|---:|---:|---:|---:|",
            f"| {mastery['未检验']} | {mastery['能复述']} | {mastery['能辨析']} | {mastery['能迁移']} |",
            "",
            "## 知识关系",
            "",
            f"- 正式同类语义关系：{connections.get('same_category_edge_count', 0)}",
            f"- 正式跨域关系：{connections.get('cross_category_edge_count', connections.get('edge_count', 0))}",
            f"- 尚未正式化的导航或普通提示指向：{connections.get('navigation_hint_count', 0)}",
            f"- 语义孤岛：{connections.get('semantic_island_count', connections.get('island_count', 0))}（不是自动缺陷）",
            f"- 关系结构错误：{connections.get('error_count', 0)}",
            "",
            "## 队列与健康",
            "",
            f"- 待理解材料：{len(state['pending_understanding'])}",
            f"- 待回答关键问题：{len(state['unanswered_questions'])}",
            f"- 待沉淀材料：{len(state['pending_deposit'])}",
            f"- 单一来源或未标证据主题：{len(state['weak_evidence'])}",
            f"- 存在争议主题：{len(state['conflicts'])}",
            f"- 未完成任务：{metrics.get('tasks', '不可用')}",
            f"- 全库未解析链接：{metrics.get('unresolved', '不可用')}",
            f"- 全库孤立笔记：{metrics.get('orphans', '不可用')}",
            f"- 全库无出链笔记：{metrics.get('deadends', '不可用')}",
            "",
            "## 当前任务、全局事项与系统建议",
            "",
            "系统建议不是用户已采用的全局待办；当前任务优先。",
        ]
    )
    context = state.get("action_context", {})
    if context:
        lines.append("- 当前任务：" + str(context.get("current_task") or "未传入；只展示全局背景"))
        global_state = context.get("global_state", {})
        if not global_state.get("valid"):
            lines.append("- 全局事项不可读：" + "; ".join(global_state.get("errors", [])))
        else:
            confirmed = context.get("global_confirmed") or []
            lines.append("- 已确认的全局待办：" + ("；".join(item["title"] for item in confirmed) or "暂无"))
            lines.append("- 待选择的全局事项：" + "；".join(item["title"] for item in context.get("pending_choices", [])))
        suggestion = context["system_suggestion"]
        lines.extend(["- 系统建议（未采用）：" + suggestion["text"], "- 建议依据：" + suggestion["basis"]])
    else:
        lines.append("- 系统建议（未采用）：" + str(state.get("next_action", "")))
    lines.extend(["", "成熟度计数：" + json.dumps(state.get("maturity", {}), ensure_ascii=False),
                  "证据状态计数：" + json.dumps(state.get("evidence", {}), ensure_ascii=False)])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only weekly review for the personal knowledge tree.")
    parser.add_argument("--vault", type=Path, default=CONFIG.vault)
    parser.add_argument("--library", type=Path, default=CONFIG.knowledge_library)
    parser.add_argument("--vault-name", default=CONFIG.vault_name)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--current-task", default="", help="Read-only current conversation objective; never persisted")
    parser.add_argument("--source", default="", help="Explicit selected important source, absolute or vault-relative")
    parser.add_argument("--blocker", action="append", default=[], help="Explicit current-related blocker")
    parser.add_argument("--learning", action="store_true", help="Explicit learning suggestion request for this call only")
    parser.add_argument("--local-only", action="store_true", help="Local Markdown only; do not call Obsidian or run followup")
    args = parser.parse_args()

    state = collect_state(args.vault, args.vault_name, args.library, current_task=args.current_task,
                          selected_source=args.source, related_blockers=args.blocker, include_cli=not args.local_only,
                          learning_requested=args.learning)
    evidence_scripts = Path(__file__).resolve().parents[2] / "apply-film-knowledge" / "scripts"
    if str(evidence_scripts) not in sys.path:
        sys.path.insert(0, str(evidence_scripts))
    from knowledge_followup import run_followup
    if args.local_only:
        state["knowledge_followup"] = {"status": "not_checked", "reason": "显式本地只读模式未调用Obsidian或补查"}
    elif args.vault.resolve() != CONFIG.vault.resolve() or args.library.resolve() != CONFIG.knowledge_library.resolve():
        state["knowledge_followup"] = {"status": "not_checked", "reason": "覆盖路径与配置不同，避免混入另一知识库"}
    else:
        report = run_followup(CONFIG.as_dict())
        state["knowledge_followup"] = {k: report[k] for k in ("status", "baseline_missing", "inventory", "changes", "affected_topics")}
        state["knowledge_followup"]["issue_count"] = len(report["issues"])
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(state))
        followup_state = state["knowledge_followup"]
        print("\n## 新材料与关联补查\n")
        print("- 状态：" + followup_state["status"])
        print("- 待复核项：" + str(followup_state.get("issue_count", "未检查")))
        print("- 受影响主题：" + str(len(followup_state.get("affected_topics", []))))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
