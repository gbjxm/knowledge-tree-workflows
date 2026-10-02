#!/usr/bin/env python3
"""Preview or transactionally record a film-knowledge project application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from retrieve_knowledge import load_config, load_topics, resolve_config


VALID_STATUSES = {"待验证", "有效", "部分有效", "无效"}
PROJECT_APPLICATION_RELATIVE = Path("05-创作实践与项目复盘") / "项目应用"


@dataclass
class WritePlan:
    application_id: str
    application_path: Path
    changes: dict[Path, str]
    before_hashes: dict[Path, str | None]
    evidence_upgrade_proposal: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def safe_filename(value: str, fallback: str = "项目") -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", value).strip(" .-")
    value = re.sub(r"\s+", " ", value)
    return value[:36] or fallback


def application_id(project: str, problem: str, stage: str, record_key: str = "") -> str:
    source = record_key or "\0".join((project.strip(), problem.strip(), stage.strip()))
    return "AFK-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12].upper()


def relative_wikilink(path: Path, library: Path) -> str:
    return path.relative_to(library).with_suffix("").as_posix()


def render_managed_application(
    *,
    app_id: str,
    project: str,
    problem: str,
    stage: str,
    topics: list[tuple[str, str]],
    action: str,
    result: str,
    conditions: str,
    status: str,
    observable: bool,
    record_date: str,
) -> tuple[str, str]:
    topic_yaml = "\n".join(f"  - {yaml_quote(f'[[{link}]]')}" for _, link in topics)
    topic_rows = "\n".join(
        f"| [[{link}|{title}]] | 待在实际记录中说明 | 解决本轮问题所需的已有方法 |"
        for title, link in topics
    )
    proposal = "可提出，需单独审查" if observable and status != "待验证" else "不提出"

    prefix = f"""---
类型: 项目应用
分类: 创作实践与项目复盘
状态: 进行中
材料类型: 个人实践
信息来源: 项目记录
完整程度: 持续积累
整理日期: {record_date}
知识库版本: 2.1
应用记录ID: {yaml_quote(app_id)}
项目: {yaml_quote(project)}
项目阶段: {yaml_quote(stage)}
适用阶段:
  - {yaml_quote(stage)}
当前问题: {yaml_quote(problem)}
调用知识:
{topic_yaml}
验证状态: {yaml_quote(status)}
可观察结果: {str(observable).lower()}
复盘日期: {record_date}
---

# {project} - {problem}

"""
    managed = f"""<!-- apply-film-knowledge:{app_id}:BEGIN -->
## 本轮目标

- 当前阶段：{stage}
- 要解决的具体问题：{problem}
- 完成标准：以用户提供的可观察标准为准；未提供时保持待验证。

## 调用的知识

| 主题 | 实际调用的方法 | 为什么适用于本轮 |
|---|---|---|
{topic_rows}

## 本轮决策与执行

| 实际改动 | 为什么这样做 | 影响条件 | 预期结果 |
|---|---|---|---|
| {action or '尚未提供'} | 调用现有主题方法处理当前问题 | {conditions or '尚未提供'} | 由本轮目标定义 |

## 结果与证据

- 实际结果：{result or '尚无可观察结果'}
- 可观察差异：{'已由用户明确提供' if observable else '尚未提供'}
- 验证状态：{status}
- 证据升级提议：{proposal}；本记录不会自动修改主题 `证据状态`。

## 问题与下一轮

- 本轮卡点：待用户补充。
- 下一步最小改动：根据结果只改变一个主要变量。

## 回写知识库

- 本记录只增加项目应用双向入口。
- 核心命题、方法或边界的实质改写交给 `grow-creative-library`。
- 新增或改义正式关系交给 `weave-film-knowledge-connections`。

## 一分钟复盘

本轮围绕“{problem}”调用已有知识，实际改动为“{action or '尚未提供'}”，当前结果为“{result or '待验证'}”。
<!-- apply-film-knowledge:{app_id}:END -->"""
    return prefix, managed


def merge_application(existing: str | None, prefix: str, managed: str, app_id: str) -> str:
    default_suffix = "\n\n## 我的补充\n\n<!-- 受管区之外可写个人观察；重复回写不得删除本节内容。 -->\n"
    if existing is None:
        return prefix + managed + default_suffix

    begin = f"<!-- apply-film-knowledge:{app_id}:BEGIN -->"
    end = f"<!-- apply-film-knowledge:{app_id}:END -->"
    start_index = existing.find(begin)
    end_index = existing.find(end)
    if start_index < 0 or end_index < start_index:
        raise ValueError("目标项目应用已存在但不含匹配的受管记录 ID，停止覆盖")
    suffix = existing[end_index + len(end):]
    return prefix + managed + suffix


def upsert_topic_application(
    text: str,
    *,
    app_id: str,
    app_link: str,
    project: str,
    stage: str,
    problem: str,
    method: str,
    status: str,
) -> str:
    begin = f"<!-- apply-film-knowledge:{app_id}:BEGIN -->"
    end = f"<!-- apply-film-knowledge:{app_id}:END -->"
    row = (
        f"| [[{app_link}|{project}]] | {stage}：{problem} | {method or '调用本主题的相关方法'} "
        f"| {status} | [[{app_link}#回写知识库|项目记录]] |"
    )
    block = f"{begin}\n{row}\n{end}"

    existing_pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if existing_pattern.search(text):
        return existing_pattern.sub(block, text, count=1)

    section_match = re.search(
        r"(?ms)^## 项目应用与验证\s*\n(.*?)(?=^##\s|\Z)", text
    )
    if not section_match:
        return text.rstrip() + (
            "\n\n## 项目应用与验证\n\n"
            "| 项目 | 阶段与问题 | 本次调用 | 结果 | 回写 |\n"
            "|---|---|---|---|---|\n"
            f"{block}\n"
        )

    section = section_match.group(0).rstrip()
    replacement = section + "\n" + block + "\n\n"
    return text[:section_match.start()] + replacement + text[section_match.end():]


def build_plan(
    *,
    config_path: Path,
    project: str,
    problem: str,
    stage: str,
    topic_names: list[str],
    method: str,
    action: str,
    result: str,
    conditions: str,
    status: str,
    observable: bool,
    record_date: str,
    record_key: str,
) -> WritePlan:
    if status not in VALID_STATUSES:
        raise ValueError(f"无效验证状态: {status}")
    if status != "待验证" and not observable:
        raise ValueError("没有可观察结果时，验证状态只能保持待验证")
    if observable and not result.strip():
        raise ValueError("标记可观察结果时必须提供 --result")

    config = load_config(config_path)
    library = Path(config["knowledge_library"]).expanduser().resolve()
    topic_index = {topic.title: topic for topic in load_topics(library)}
    missing = sorted(set(topic_names) - set(topic_index))
    if missing:
        raise ValueError("目标主题不存在: " + "、".join(missing))

    app_id = application_id(project, problem, stage, record_key)
    app_dir = (Path(config["creation_root"]) / "岗位共用" / "项目经验" / "项目应用"
               if config.get("creation_root") else library / PROJECT_APPLICATION_RELATIVE)
    filename = f"{safe_filename(project)}-{safe_filename(problem)}-{app_id}.md"
    app_path = app_dir / filename
    link_root = Path(config["vault"]) if config.get("creation_root") else library
    app_link = relative_wikilink(app_path, link_root)
    topic_links = [(title, relative_wikilink(topic_index[title].path, link_root)) for title in topic_names]
    prefix, managed = render_managed_application(
        app_id=app_id,
        project=project,
        problem=problem,
        stage=stage,
        topics=topic_links,
        action=action,
        result=result,
        conditions=conditions,
        status=status,
        observable=observable,
        record_date=record_date,
    )

    existing_app = app_path.read_text(encoding="utf-8-sig") if app_path.exists() else None
    changes: dict[Path, str] = {
        app_path: merge_application(existing_app, prefix, managed, app_id)
    }
    for title in topic_names:
        topic_path = topic_index[title].path
        current = topic_path.read_text(encoding="utf-8-sig")
        changes[topic_path] = upsert_topic_application(
            current,
            app_id=app_id,
            app_link=app_link,
            project=project,
            stage=stage,
            problem=problem,
            method=method,
            status=status,
        )

    return WritePlan(
        application_id=app_id,
        application_path=app_path,
        changes=changes,
        before_hashes={path: file_hash(path) for path in changes},
        evidence_upgrade_proposal=observable and status != "待验证",
    )


def write_atomic(path: Path, text: str) -> None:
    write_atomic_bytes(path, text.encode("utf-8"))


def write_atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def apply_plan(plan: WritePlan, fail_after: int = 0) -> dict[str, Any]:
    originals: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None for path in plan.changes
    }
    changed: list[Path] = []
    try:
        for path in sorted(plan.changes, key=lambda item: str(item).casefold()):
            new_text = plan.changes[path]
            new_bytes = new_text.encode("utf-8")
            if originals[path] == new_bytes:
                continue
            write_atomic(path, new_text)
            changed.append(path)
            if fail_after and len(changed) >= fail_after:
                raise RuntimeError(f"模拟写入失败: 已写 {len(changed)} 个文件")
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in reversed(changed):
            original = originals[path]
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic_bytes(path, original)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic boundary
                rollback_errors.append(f"{path}: {rollback_exc}")

        mismatches = [
            str(path) for path, expected in plan.before_hashes.items() if file_hash(path) != expected
        ]
        if rollback_errors or mismatches:
            raise RuntimeError(
                f"写回失败且回滚未完全恢复: {exc}; rollback_errors={rollback_errors}; mismatches={mismatches}"
            ) from exc
        raise RuntimeError(f"写回失败，全部文件已恢复: {exc}") from exc

    return {
        "application_id": plan.application_id,
        "application_path": str(plan.application_path),
        "changed_files": [str(path) for path in changed],
        "changed_count": len(changed),
        "evidence_upgrade_proposal": plan.evidence_upgrade_proposal,
        "evidence_status_changed": False,
    }


def plan_summary(plan: WritePlan) -> dict[str, Any]:
    return {
        "mode": "preview",
        "application_id": plan.application_id,
        "application_path": str(plan.application_path),
        "affected_files": [str(path) for path in sorted(plan.changes, key=lambda item: str(item).casefold())],
        "affected_count": len(plan.changes),
        "evidence_upgrade_proposal": plan.evidence_upgrade_proposal,
        "evidence_status_changed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--topic", action="append", required=True, dest="topics")
    parser.add_argument("--method", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--result", default="")
    parser.add_argument("--conditions", default="")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), default="待验证")
    parser.add_argument("--observable-result", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--record-key", default="")
    parser.add_argument("--config")
    parser.add_argument("--confirm-writeback", action="store_true")
    parser.add_argument("--fail-after", type=int, default=0, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = resolve_config(args.config)
        plan = build_plan(
            config_path=config_path,
            project=args.project,
            problem=args.problem,
            stage=args.stage,
            topic_names=args.topics,
            method=args.method,
            action=args.action,
            result=args.result,
            conditions=args.conditions,
            status=args.status,
            observable=args.observable_result,
            record_date=args.date,
            record_key=args.record_key,
        )
        if not args.confirm_writeback:
            print(json.dumps(plan_summary(plan), ensure_ascii=False, indent=2))
            return 0
        result = apply_plan(plan, fail_after=args.fail_after)
        result["mode"] = "writeback"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
