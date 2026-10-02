"""Read global state and derive task-local suggestions without writing any state."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

SOURCE_TYPES = {"材料总览", "分集笔记"}
ACTION_SECTIONS = {"confirmed_actions": "已确认的全局待办", "pending_choices": "待选择的全局事项"}
GAP_LABELS = {"空白", "待补", "缺失", "未覆盖", "待补充"}


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    props: dict[str, str] = {}
    for line in match.group(1).splitlines() if match else []:
        if line and not line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            props[key.strip()] = value.strip().strip("\"'")
    return props


def section(text: str, heading: str) -> str | None:
    found = re.search(rf"^##\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^##\s+|\Z)", text, re.M | re.S)
    return found.group(1).strip() if found else None


def question_text(text: str) -> str:
    """Read the current source question, skipping callout chrome and empty quotes."""
    body = section(text, "关键问题") or ""
    for raw in body.splitlines():
        line = re.sub(r"^\s*>\s?", "", raw).strip()
        if not line:
            continue
        callout = re.match(r"^\[!question\][+-]?\s*(.*?)\s*$", line)
        if callout:
            title = callout.group(1).strip()
            if re.search(r"[?？]", title):
                return title
            continue
        if line.startswith(("[!", "<!--", "#", "```")):
            continue
        return re.sub(r"^(?:[-*]|\d+\.)\s+", "", line)
    return ""


def table_cells(line: str) -> list[str]:
    # Wiki aliases may contain pipes; escaped pipes are ordinary text too.
    parts: list[str] = []
    current: list[str] = []
    in_wiki = False
    index = 0
    body = line.strip().strip("|")
    while index < len(body):
        if body[index:index + 2] == "\\|":
            current.append("|"); index += 2; continue
        if body[index:index + 2] == "[[":
            in_wiki = True
        elif body[index:index + 2] == "]]":
            in_wiki = False
        if body[index] == "|" and not in_wiki:
            parts.append("".join(current).strip()); current = []
        else:
            current.append(body[index])
        index += 1
    parts.append("".join(current).strip())
    return parts


def action_table(text: str, heading: str) -> tuple[list[dict[str, str]], list[str]]:
    body = section(text, heading)
    if body is None:
        return [], [f"缺少全局状态节：{heading}"]
    rows = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return [], [f"{heading}缺少事项表；空队列也须保留表头与分隔行"]
    header = table_cells(rows[0])
    divider = table_cells(rows[1])
    if header not in (["标识", "事项", "依据"], ["ID", "事项", "依据"]):
        return [], [f"{heading}表头应为：标识、事项、依据"]
    if len(divider) != 3 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in divider):
        return [], [f"{heading}表格分隔行无效"]
    result: list[dict[str, str]] = []
    errors: list[str] = []
    for line in rows[2:]:
        cells = table_cells(line)
        if len(cells) == 3 and cells[0] in {"", "—", "-"} and cells[1] in {"暂无", "无", ""}:
            continue
        if len(cells) != 3 or not all(cells):
            errors.append(f"{heading}存在缺字段或多列的事项：{line.strip()}")
            continue
        result.append({"id": cells[0], "title": cells[1], "basis": cells[2]})
    return result, errors


def read_global_state(north_star: Path, status: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        north = parse_frontmatter(north_star.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError) as exc:
        north = {}; errors.append(f"北极星不可读：{exc}")
    if not north.get("当前重点"):
        errors.append("北极星缺少当前重点，不能静默指定学习方向")
    try:
        status_text = status.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        status_text = ""; errors.append(f"全局状态不可读：{exc}")
    payload: dict[str, Any] = {"north_star": north, "focus": north.get("当前重点", ""),
                              "status_path": str(status), "errors": errors}
    seen: set[str] = set()
    for key, heading in ACTION_SECTIONS.items():
        rows, table_errors = action_table(status_text, heading)
        errors.extend(table_errors)
        for row in rows:
            if row["id"] in seen:
                errors.append(f"全局事项标识重复：{row['id']}")
            seen.add(row["id"])
        payload[key] = rows
    payload["valid"] = not errors
    # A partial parse must never masquerade as an empty or confirmed queue.
    if errors:
        payload["confirmed_actions"] = None
        payload["pending_choices"] = None
    return payload


def source_learning_record(path: Path, vault: Path) -> dict[str, Any]:
    path, vault = path.resolve(), vault.resolve()
    if not path.is_relative_to(vault):
        return {"status": "invalid", "path": str(path), "reason": "所选来源不在选定Vault内"}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return {"status": "invalid", "path": str(path), "reason": str(exc)}
    props = parse_frontmatter(text)
    record = {"path": path.relative_to(vault).as_posix(), "question": question_text(text),
              "understanding": props.get("理解状态", ""), "question_state": props.get("关键问题状态", ""),
              "category": props.get("分类", "")}
    if props.get("类型") not in SOURCE_TYPES:
        return {**record, "status": "not_source", "reason": "所选笔记不是来源材料"}
    if props.get("关键问题状态") == "不适用":
        return {**record, "status": "not_applicable", "reason": "所选来源的历史关键问题标为不适用；需要学习时直接围绕本次内容展开"}
    if props.get("关键问题状态") != "待回答":
        return {**record, "status": "not_pending", "reason": "所选来源没有已登记的待答问题"}
    if not record["question"]:
        return {**record, "status": "missing_question", "reason": "待回答标记没有可读的当前问题，不能把callout标题当问题"}
    return {**record, "status": "selected_pending"}


def map_gaps(library: Path, focus: str) -> list[dict[str, str]]:
    """Only explicit map gaps, never a gap inferred from topic counts."""
    found: list[dict[str, str]] = []
    # New layouts keep professional maps together; old layouts remain readable.
    maps = set(library.glob("*/00-*地图.md"))
    maps.update((library / "00-待归档与知识地图" / "专业索引").glob("00-*地图.md"))
    for path in sorted(maps):
        text = path.read_text(encoding="utf-8-sig")
        props = parse_frontmatter(text)
        body = section(text, "知识骨架") or ""
        for line in body.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = table_cells(line)
            if len(cells) >= 4 and cells[-1] in GAP_LABELS:
                found.append({"category": props.get("分类", ""), "question": cells[1],
                              "path": str(path), "basis": line.strip()})
    return sorted(found, key=lambda gap: (gap["category"] != focus, gap["path"], gap["question"]))


def resolve_action_context(global_state: dict[str, Any], *, current_task: str = "",
                           selected_source: dict[str, Any] | None = None,
                           related_blockers: Sequence[str] = (), review_target: dict[str, Any] | None = None,
                           gaps: Sequence[dict[str, str]] = (), learning_requested: bool = False) -> dict[str, Any]:
    source = selected_source or {}
    target = review_target or {}
    if related_blockers:
        suggestion = {"kind": "related_blocker", "text": str(related_blockers[0]), "basis": "显式传入的当前相关阻塞"}
    elif source.get("status") in {"invalid", "not_source", "missing_question"}:
        suggestion = {"kind": "selected_source_unavailable", "text": "当前所选来源或已登记学习记录需核对：" + source["reason"], "basis": str(source.get("path", ""))}
    elif learning_requested and source.get("status") == "selected_pending":
        suggestion = {"kind": "selected_source_question", "text": source["question"], "basis": source["path"]}
    elif learning_requested and source.get("status") in {"not_pending", "not_applicable"}:
        suggestion = {"kind": "selected_source_learning", "text": "围绕所选来源开展本次讲解或讨论；明确请求检验时再提问。", "basis": source["path"]}
    elif current_task and not learning_requested:
        suggestion = {"kind": "current_task", "text": "按当前任务推进；需要学习支持时再明确来源或主题。", "basis": "当前对话目标优先，背景学习队列不抢占"}
    elif not global_state.get("valid"):
        suggestion = {"kind": "state_unavailable", "text": "全局待办读取失败，先核对状态表；不把它当作暂无待办。", "basis": "; ".join(global_state.get("errors", []))}
    elif not learning_requested:
        suggestion = {"kind": "learning_not_requested", "text": "本次未请求学习建议；只展示知识与状态信息。", "basis": "启动、入库、收尾和普通周复盘不自动选题"}
    elif target.get("status") == "selected" and target.get("mastery_state") != "能迁移":
        suggestion = {"kind": "focus_mastery", "text": str(target.get("suggested_question", "")), "basis": str(target.get("relative_path", ""))}
    elif gaps:
        gap = gaps[0]
        suggestion = {"kind": "map_gap", "text": "核对地图中已记录的具体缺口：" + gap["question"], "basis": gap["path"] + "：" + gap["basis"]}
    else:
        suggestion = {"kind": "no_selected_gap", "text": "暂无有依据的自动学习建议；可从当前创作问题或明确选中的材料开始。", "basis": "未把篇数少、未答历史题或语义孤岛自动当成任务"}
    confirmed = global_state.get("confirmed_actions") if global_state.get("valid") else None
    if current_task:
        effective = {"kind": "current_task", "text": current_task, "adopted": True, "basis": "只读当前对话参数，不写入全局待办"}
    elif confirmed:
        effective = {"kind": "global_confirmed", "text": confirmed[0]["title"], "adopted": True, "basis": confirmed[0]["basis"]}
    else:
        effective = {**suggestion, "adopted": False}
    return {"current_task": current_task or None, "learning_requested": learning_requested, "global_confirmed": confirmed,
            "pending_choices": global_state.get("pending_choices"), "selected_source": source or None,
            "system_suggestion": {**suggestion, "adopted": False}, "effective_action": effective,
            "rule": "当前任务优先；已确认全局事项、待选择事项与系统建议分别展示。"}


def read_state(vault: Path, library: Path, *, north_star: Path | None = None, status: Path | None = None,
               current_task: str = "", selected_source: str = "", related_blockers: Sequence[str] = (),
               review_target: dict[str, Any] | None = None, learning_requested: bool = False) -> dict[str, Any]:
    vault, library = vault.resolve(), library.resolve()
    if not library.is_relative_to(vault):
        raise ValueError("Knowledge library must stay inside the selected vault")
    control = library / "00-待归档与知识地图"
    north_star = north_star or control / "我的知识树北极星.md"
    status = status or control / "知识树状态.md"
    if not north_star.resolve().is_relative_to(library) or not status.resolve().is_relative_to(library):
        raise ValueError("State and North Star must stay inside the selected knowledge library")
    global_state = read_global_state(north_star, status)
    source = None
    if selected_source:
        source_path = Path(selected_source)
        source = source_learning_record(source_path if source_path.is_absolute() else vault / source_path, vault)
    if not learning_requested:
        review_target = {"status": "not_requested"}
    elif selected_source:
        # A selected source owns this learning turn; do not pick an unrelated topic.
        review_target = {"status": "source_selected"}
    elif review_target is None:
        scripts = Path(__file__).resolve().parents[2] / "internalize-film-knowledge" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from select_review_target import choose
        review_target = choose(vault, library=library, north_star=north_star) if global_state.get("focus") else {"status": "no_target"}
    gaps = map_gaps(library, global_state.get("focus", ""))
    input_errors = [source["reason"]] if source and source.get("status") in {"invalid", "not_source", "missing_question"} else []
    return {"global_state": global_state, "input_errors": input_errors, "review_target": review_target, "map_gaps": gaps,
            **resolve_action_context(global_state, current_task=current_task, selected_source=source,
                                     related_blockers=related_blockers, review_target=review_target, gaps=gaps,
                                     learning_requested=learning_requested)}


def main() -> int:
    from knowledge_tree_config import load_config
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=config.vault)
    parser.add_argument("--library", type=Path, default=config.knowledge_library)
    parser.add_argument("--current-task", default="")
    parser.add_argument("--source", default="", help="Explicit selected important source, absolute or vault-relative")
    parser.add_argument("--blocker", action="append", default=[], help="Explicit current-related blocker only")
    parser.add_argument("--learning", action="store_true", help="Explicit learning suggestion request for this call only")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    state = read_state(args.vault, args.library, current_task=args.current_task, selected_source=args.source, related_blockers=args.blocker, learning_requested=args.learning)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print("当前任务：" + (state["current_task"] or "未指定（只展示全局背景）"))
        print("已确认全局待办：" + json.dumps(state["global_confirmed"], ensure_ascii=False))
        print("系统建议（未采用）：" + state["system_suggestion"]["text"])
        for error in state["global_state"]["errors"]:
            print("ERROR: " + error)
    return 0 if state["global_state"]["valid"] and not state["input_errors"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
