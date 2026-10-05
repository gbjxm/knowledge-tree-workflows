#!/usr/bin/env python3
"""Preview or transactionally record a film-knowledge project application."""

from __future__ import annotations

import argparse
import difflib
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

from retrieve_knowledge import SKILLS_ROOT, load_config, resolve_config

VALIDATION_SCRIPTS = SKILLS_ROOT / "grow-creative-library" / "scripts"
if str(VALIDATION_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(VALIDATION_SCRIPTS))
from validate_note import parse_frontmatter, property_values, validate_text


VALID_STATUSES = {"待验证", "有效", "部分有效", "无效"}
PROJECT_APPLICATION_RELATIVE = Path("05-创作实践与项目复盘") / "项目应用"


@dataclass
class WritePlan:
    application_id: str
    application_path: Path
    changes: dict[Path, str]
    before_hashes: dict[Path, str | None]
    evidence_upgrade_proposal: bool
    originals: dict[Path, bytes | None]
    config_path: Path
    config_hash: str
    config: dict[str, Any]
    plan_id: str = ""


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


def table_cell(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("|", "&#124;").replace("\n", "<br>")


def discover_metadata(path: Path, *, title: bool = False) -> tuple[dict[str, str], str]:
    """Read bounded metadata; source bodies and unselected topic bodies stay unread."""
    remaining = 65536
    with path.open("rb") as stream:
        first = stream.readline(remaining + 1)
        remaining -= len(first)
        if remaining < 0 or first.removeprefix(b"\xef\xbb\xbf").strip() != b"---":
            return {}, path.stem
        header = [first]
        while remaining > 0:
            line = stream.readline(remaining + 1)
            remaining -= len(line)
            if not line or remaining < 0:
                return {}, path.stem
            header.append(line)
            if line.strip() == b"---":
                break
        else:
            return {}, path.stem
        _, props = parse_frontmatter(b"".join(header).decode("utf-8-sig"))
        if not title or props.get("类型", "").strip().strip('"\'') != "主题笔记":
            return props, path.stem
        while remaining > 0:
            line = stream.readline(remaining + 1)
            remaining -= len(line)
            if not line or remaining < 0:
                break
            match = re.match(rb"^#[ \t]+([^\r\n]+)", line)
            if match:
                return props, match.group(1).decode("utf-8").strip()
    return props, path.stem


def _marker_span(text: str, app_id: str, required: bool = False) -> tuple[int, int] | None:
    open_id = None
    for marker in re.finditer(r"<!-- apply-film-knowledge:([^:\r\n]+):(BEGIN|END) -->", text):
        identity, kind = marker.groups()
        if kind == "BEGIN":
            if open_id is not None:
                raise ValueError("受管记录标记发生嵌套，停止覆盖")
            open_id = identity
        elif open_id != identity:
            raise ValueError("受管记录标记不成对，停止覆盖")
        else:
            open_id = None
    if open_id is not None:
        raise ValueError("受管记录标记缺失或损坏，停止覆盖")
    begin = f"<!-- apply-film-knowledge:{app_id}:BEGIN -->"
    end = f"<!-- apply-film-knowledge:{app_id}:END -->"
    starts, ends = text.count(begin), text.count(end)
    if not starts and not ends:
        if required or f"apply-film-knowledge:{app_id}:" in text:
            raise ValueError("目标记录的受管标记缺失或损坏，停止覆盖")
        return None
    if starts != 1 or ends != 1 or text.find(end) < text.find(begin):
        raise ValueError("目标记录的受管标记重复、倒置或损坏，停止覆盖")
    start, stop = text.index(begin), text.index(end) + len(end)
    inner = text[start + len(begin):stop - len(end)]
    if "<!-- apply-film-knowledge:" in inner:
        raise ValueError("受管记录标记发生嵌套，停止覆盖")
    return start, stop


def _merge_frontmatter(existing: str, generated: str) -> str:
    pattern = re.compile(r"\A---\r?\n(.*?)\r?\n---(?=\r?\n|\Z)", re.DOTALL)
    old, new = pattern.match(existing), pattern.match(generated)
    if not old or not new:
        raise ValueError("应用记录缺少可识别的 YAML，停止覆盖")
    newline = "\r\n" if "\r\n" in old.group(0) else "\n"
    old_lines = old.group(1).splitlines(keepends=True)
    new_lines = new.group(1).splitlines(keepends=True)
    key_pattern = re.compile(r"^([^\s:#][^:]*):")

    def chunks(lines):
        result = []
        for line in lines:
            match = key_pattern.match(line)
            if match:
                result.append((match.group(1), [line]))
            elif result:
                result[-1][1].append(line)
            else:
                result.append((None, [line]))
        return result

    generated_fields = {key: "".join(lines).rstrip("\r\n") for key, lines in chunks(new_lines) if key}
    output, seen = [], set()
    for key, lines in chunks(old_lines):
        if key not in generated_fields:
            output.append("".join(lines))
            continue
        if key in seen:
            raise ValueError("应用记录的受管 YAML 属性重复，停止覆盖")
        seen.add(key)
        output.append(generated_fields[key].replace("\r\n", "\n").replace("\n", newline) + newline)
        # Comments and spacing belong to the user, including those after an owned field.
        trailing = [line for line in lines[1:] if not line.strip() or line.lstrip().startswith("#")]
        output.extend(trailing)
    body = "".join(output)
    for key, value in generated_fields.items():
        if key not in seen:
            body += ("" if body.endswith(("\n", "\r")) else newline) + value.replace("\r\n", "\n").replace("\n", newline) + newline
    frontmatter = "---" + newline + body + ("" if body.endswith(("\n", "\r")) else newline) + "---"
    suffix = existing[old.end():]
    new_title = re.search(r"(?m)^#[ \t]+[^\r\n]+", generated[new.end():])
    if new_title:
        suffix = re.sub(r"(?m)^#[ \t]+[^\r\n]+", lambda _: new_title.group(0), suffix, count=1)
    return frontmatter + suffix


def render_managed_application(
    *,
    app_id: str,
    project: str,
    problem: str,
    stage: str,
    topics: list[tuple[str, str, str, str]],
    action: str,
    result: str,
    conditions: str,
    status: str,
    observable: bool,
    record_date: str,
) -> tuple[str, str]:
    topic_yaml = "\n".join(f"  - {yaml_quote(f'[[{link}]]')}" for _, link, _, _ in topics)
    topic_rows = "\n".join(
        f"| [[{link}|{table_cell(title)}]] | {table_cell(method)} | {table_cell(reason or '未单独提供；结合本轮问题与影响条件核对')} |"
        for title, link, method, reason in topics
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
| {table_cell(action or '尚未提供')} | 调用现有主题方法处理当前问题 | {table_cell(conditions or '尚未提供')} | 由本轮目标定义 |

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

    span = _marker_span(existing, app_id, required=True)
    newline = "\r\n" if "\r\n" in existing else "\n"
    replacement = managed.replace("\n", newline)
    updated = existing[:span[0]] + replacement + existing[span[1]:]
    return _merge_frontmatter(updated, prefix)


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
        f"| [[{app_link}|{table_cell(project)}]] | {table_cell(stage)}：{table_cell(problem)} | {table_cell(method)} "
        f"| {status} | [[{app_link}#回写知识库|项目记录]] |"
    )
    block = f"{begin}\n{row}\n{end}"

    newline = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\n", newline)
    span = _marker_span(text, app_id)
    if span:
        return text[:span[0]] + block + text[span[1]:]

    section_match = re.search(
        r"(?ms)^## 项目应用与验证[^\S\r\n]*\r?\n(.*?)(?=^##\s|\Z)", text
    )
    if not section_match:
        return text + (
            "\n\n## 项目应用与验证\n\n"
            "| 项目 | 阶段与问题 | 本次调用 | 结果 | 回写 |\n"
            "|---|---|---|---|---|\n"
            f"{block.replace(chr(13) + chr(10), chr(10))}\n"
        ).replace("\n", newline)

    section = section_match.group(0)
    replacement = section + ("" if section.endswith(("\n", "\r")) else newline) + block + newline + newline
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
    topic_methods: dict[str, dict[str, str]] | None = None,
) -> WritePlan:
    if status not in VALID_STATUSES:
        raise ValueError(f"无效验证状态: {status}")
    if status != "待验证" and not observable:
        raise ValueError("没有可观察结果时，验证状态只能保持待验证")
    if observable and not result.strip():
        raise ValueError("标记可观察结果时必须提供 --result")
    if not method.strip() or not project.strip() or not problem.strip() or not stage.strip():
        raise ValueError("项目、问题、阶段和实际方法不能为空")
    date.fromisoformat(record_date)
    config_path = config_path.resolve()
    config_raw = config_path.read_bytes()
    config = load_config(config_path)
    if config_path.read_bytes() != config_raw:
        raise ValueError("读取期间配置发生变化，停止生成候选")
    library = Path(config["knowledge_library"]).expanduser().resolve()
    vault = Path(config["vault"]).resolve()
    discovered: dict[Path, str] = {}
    directory_loaded = False

    def discover(path: Path) -> None:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(library) or not resolved.is_relative_to(vault):
            raise ValueError(f"主题路径越出配置范围: {path}")
        props, title = discover_metadata(path, title=True)
        if props.get("类型", "").strip().strip('"\'') == "主题笔记":
            discovered[resolved] = title

    selected: list[Path] = []
    for selector in topic_names:
        selector = selector.strip()
        candidate = Path(selector)
        candidate = candidate.resolve() if candidate.is_absolute() else (vault / candidate).resolve()
        matches = []
        if candidate.suffix.lower() == ".md" and candidate.is_file():
            discover(candidate)
            if candidate in discovered:
                matches = [candidate]
        if not matches:
            if not directory_loaded:
                for path in sorted(library.rglob("*.md"), key=lambda item: str(item).casefold()):
                    if not set(path.relative_to(library).parts) & {".obsidian", ".trash"}:
                        discover(path)
                directory_loaded = True
            matches = [path for path, title in discovered.items() if title == selector]
        if len(matches) != 1:
            kind = "歧义" if matches else "不存在或越界"
            raise ValueError(f"目标主题{kind}，请使用 Vault 内准确路径: {selector}")
        if matches[0] in selected:
            raise ValueError("目标主题重复")
        selected.append(matches[0])
    if not selected:
        raise ValueError("至少需要一个目标主题")
    original_topics: dict[Path, bytes] = {}
    for path in selected:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        header, props = parse_frontmatter(text)
        heading = re.search(r"(?m)^#[ \t]+([^\r\n]+)", text[len(header):])
        actual_title = heading.group(1).strip() if heading else path.stem
        if props.get("类型", "").strip().strip('"\'') != "主题笔记" or actual_title != discovered[path]:
            raise ValueError("目标主题在发现后发生变化，请重新生成预览")
        original_topics[path] = raw
    methods = {path: {"method": method, "reason": ""} for path in selected}
    for key, entry in (topic_methods or {}).items():
        if not isinstance(key, str) or Path(key).is_absolute() or ".." in Path(key).parts:
            raise ValueError("逐主题方法键必须是 Vault 内准确相对路径")
        path = (vault / key).resolve()
        if path not in methods or path.relative_to(vault).as_posix() != key:
            raise ValueError(f"逐主题方法包含未选中或非准确路径: {key}")
        if not isinstance(entry, dict) or set(entry) - {"method", "reason"}:
            raise ValueError("逐主题方法仅接受 method 与可选 reason")
        if not isinstance(entry.get("method"), str) or not entry["method"].strip():
            raise ValueError("逐主题实际方法不能为空")
        if not isinstance(entry.get("reason", ""), str):
            raise ValueError("逐主题适用理由必须是文字")
        methods[path] = {"method": entry["method"], "reason": entry.get("reason", "")}

    app_id = application_id(project, problem, stage, record_key)
    app_dir = (Path(config["creation_root"]) / "岗位共用" / "项目经验" / "项目应用"
               if config.get("creation_root") else library / PROJECT_APPLICATION_RELATIVE)
    filename = f"{safe_filename(project)}-{safe_filename(problem)}-{app_id}.md"
    app_path = app_dir / filename
    app_originals: dict[Path, bytes] = {}
    if app_dir.exists():
        for path in sorted(app_dir.glob("*.md")):
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(app_dir.resolve()) or not resolved.is_relative_to(vault):
                raise ValueError("项目应用路径越出配置范围")
            props, _ = discover_metadata(path)
            if props.get("应用记录ID", "").strip().strip('"\'') == app_id:
                app_originals[resolved] = path.read_bytes()
    if len(app_originals) > 1:
        raise ValueError("相同应用记录 ID 对应多个文件，停止覆盖")
    if app_originals:
        app_path = next(iter(app_originals))
    elif app_path.exists():
        # A filename collision without the matching identity must never be adopted.
        raise ValueError("目标项目应用已存在但不含匹配的受管记录 ID，停止覆盖")
    app_path = app_path.resolve()
    if not app_path.is_relative_to(vault):
        raise ValueError("项目应用目标越出活动 Vault")
    link_root = vault if config.get("creation_root") else library
    app_link = relative_wikilink(app_path, link_root)
    topic_links = [(discovered[path], relative_wikilink(path, link_root),
                    methods[path]["method"], methods[path]["reason"]) for path in selected]
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

    original_app = app_originals.get(app_path)
    existing_app = original_app.decode("utf-8-sig") if original_app is not None else None
    if existing_app is not None:
        old_header, _ = parse_frontmatter(existing_app)
        old_targets = set(property_values(old_header, "调用知识"))
        next_targets = {f"[[{relative_wikilink(path, link_root)}]]" for path in selected}
        if old_targets != next_targets:
            raise ValueError("同一应用记录的调用知识目标集合发生变化；旧回链移除范围须显式采用，当前停止预览和写入")
    originals: dict[Path, bytes | None] = {app_path: original_app}
    changes: dict[Path, str] = {
        app_path: merge_application(existing_app, prefix, managed, app_id)
    }
    for topic_path in selected:
        original = original_topics[topic_path]
        originals[topic_path] = original
        current = original.decode("utf-8-sig")
        changes[topic_path] = upsert_topic_application(
            current,
            app_id=app_id,
            app_link=app_link,
            project=project,
            stage=stage,
            problem=problem,
            method=methods[topic_path]["method"],
            status=status,
        )
    # Preserve a file's BOM; unchanged user regions retain their original line endings.
    for path, original in originals.items():
        if original is not None and original.startswith(b"\xef\xbb\xbf"):
            changes[path] = "\ufeff" + changes[path]
    plan = WritePlan(
        application_id=app_id,
        application_path=app_path,
        changes=changes,
        before_hashes={path: sha256_bytes(raw) if raw is not None else None for path, raw in originals.items()},
        evidence_upgrade_proposal=observable and status != "待验证",
        originals=originals,
        config_path=config_path,
        config_hash=sha256_bytes(config_raw),
        config=config,
    )
    validate_candidates(plan)
    plan.plan_id = plan_identity(plan)
    return plan


def validate_candidates(plan: WritePlan) -> None:
    for path, text in plan.changes.items():
        if not path.resolve().is_relative_to(Path(plan.config["vault"]).resolve()):
            raise ValueError(f"反馈目标越出配置范围: {path}")
        errors = validate_text(text, path)
        if errors:
            raise ValueError(f"候选笔记校验失败: {path}: " + "；".join(errors))


def plan_identity(plan: WritePlan) -> str:
    identity = {"config": str(plan.config_path), "config_hash": plan.config_hash,
                "application_id": plan.application_id,
                "files": [{"path": str(path), "before": plan.before_hashes[path],
                           "after": sha256_bytes(text.encode("utf-8"))}
                          for path, text in sorted(plan.changes.items(), key=lambda item: str(item[0]).casefold())]}
    return "AFK-PLAN-" + sha256_bytes(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def load_topic_methods(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"逐主题方法 JSON 含重复键: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("逐主题方法 JSON 必须是路径到方法对象的映射")
    return value


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


class NativeVerifier:
    """Verify the configured native Vault without installing or refreshing anything."""

    def __init__(self, config: dict[str, Any]):
        from obsidian_cli import ObsidianCLI
        self.vault = Path(config["vault"]).resolve()
        executable = Path(config["obsidian_cli"]) if config.get("obsidian_cli") else None
        self.cli = ObsidianCLI(executable, config["vault_name"], self.vault)

    def verify_target(self) -> None:
        result = self.cli.verify_target()
        if result.returncode:
            raise RuntimeError("Obsidian 身份不可用，拒绝反馈写入: " + (result.stderr or result.stdout))

    def verify_note(self, path: Path, expected: str) -> None:
        relative = path.relative_to(self.vault).as_posix()
        code = ("(async()=>{const p=" + json.dumps(relative, ensure_ascii=False) +
                ";const f=app.vault.getAbstractFileByPath(p);if(!f)throw new Error('Feedback target missing');"
                "return JSON.stringify({path:f.path,text:await app.vault.read(f)});})()")
        result = self.cli.run(["eval", "code=" + code])
        if result.returncode:
            raise RuntimeError("Obsidian 原生回读失败: " + (result.stderr or result.stdout))
        try:
            raw_result = result.stdout.removeprefix("=> ")
            payload = json.loads(raw_result)
            if isinstance(payload, str):
                payload = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Obsidian 原生回读没有返回可验证正文") from exc
        actual = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(actual, str) or payload.get("path") != relative or actual.removeprefix("\ufeff") != expected.removeprefix("\ufeff"):
            raise RuntimeError("Obsidian 原生正文与候选不一致")


def _assert_unchanged(plan: WritePlan, path: Path) -> None:
    vault = Path(plan.config["vault"]).resolve()
    if path.resolve() != path or not path.resolve().is_relative_to(vault):
        raise RuntimeError(f"反馈目标路径发生变化或越界: {path}")
    if file_hash(path) != plan.before_hashes[path]:
        raise RuntimeError(f"反馈目标存在并发修改，停止覆盖: {path}")


def apply_plan(plan: WritePlan, expected_plan_id: str | None = None, *, fail_after: int = 0,
               native: NativeVerifier | None = None) -> dict[str, Any]:
    if not expected_plan_id or expected_plan_id != plan.plan_id or plan_identity(plan) != plan.plan_id:
        raise ValueError("必须携带匹配预览的 --expected-plan-id；候选身份不一致，零写入")
    if file_hash(plan.config_path) != plan.config_hash:
        raise RuntimeError("知识树配置已变化，停止写入")
    validate_candidates(plan)
    for path in plan.changes:
        original = plan.originals[path]
        if (sha256_bytes(original) if original is not None else None) != plan.before_hashes[path]:
            raise ValueError("候选的恢复原稿与预览身份不一致")
        _assert_unchanged(plan, path)
    native = native if native is not None else NativeVerifier(plan.config)
    native.verify_target()
    # Verify again after native identity checks, which can take time.
    for path in plan.changes:
        _assert_unchanged(plan, path)
    changed: list[Path] = []
    touched: list[Path] = []
    try:
        for path in sorted(plan.changes, key=lambda item: str(item).casefold()):
            new_text = plan.changes[path]
            new_bytes = new_text.encode("utf-8")
            _assert_unchanged(plan, path)
            if plan.originals[path] == new_bytes:
                continue
            touched.append(path)
            write_atomic(path, new_text)
            changed.append(path)
            if file_hash(path) != sha256_bytes(new_bytes):
                raise RuntimeError(f"写后正文哈希不一致: {path}")
            errors = validate_text(path.read_bytes().decode("utf-8-sig"), path)
            if errors:
                raise RuntimeError(f"写后笔记校验失败: {path}: " + "；".join(errors))
            native.verify_note(path, new_text)
            if fail_after and len(changed) >= fail_after:
                raise RuntimeError(f"模拟写入失败: 已写 {len(changed)} 个文件")
        # Native reading may overlap an external edit. Do not report a stale success.
        for path, text in plan.changes.items():
            if file_hash(path) != sha256_bytes(text.encode("utf-8")):
                raise RuntimeError(f"反馈提交期间发生并发修改: {path}")
    except Exception as exc:
        rollback_errors: list[str] = []
        concurrent: list[str] = []
        for path in reversed(touched):
            original = plan.originals[path]
            try:
                current_hash = file_hash(path)
                if current_hash == plan.before_hashes[path]:
                    continue
                if path.resolve() != path or current_hash != sha256_bytes(plan.changes[path].encode("utf-8")):
                    concurrent.append(str(path))
                    continue
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic_bytes(path, original)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic boundary
                rollback_errors.append(f"{path}: {rollback_exc}")

        mismatches = [
            str(path) for path, expected in plan.before_hashes.items() if file_hash(path) != expected
        ]
        if rollback_errors or mismatches or concurrent:
            raise RuntimeError(
                f"写回失败且回滚未完全恢复；外部并发内容未覆盖: {exc}; "
                f"rollback_errors={rollback_errors}; concurrent={concurrent}; mismatches={mismatches}"
            ) from exc
        raise RuntimeError(f"写回失败，全部文件已恢复: {exc}") from exc

    return {
        "application_id": plan.application_id,
        "plan_id": plan.plan_id,
        "application_path": str(plan.application_path),
        "changed_files": [str(path) for path in changed],
        "changed_count": len(changed),
        "evidence_upgrade_proposal": plan.evidence_upgrade_proposal,
        "evidence_status_changed": False,
        "candidate_validation": "passed",
        "native_readback": "passed_for_changed_files",
    }


def plan_summary(plan: WritePlan) -> dict[str, Any]:
    diffs = []
    for path in sorted(plan.changes, key=lambda item: str(item).casefold()):
        before = plan.originals[path]
        before_text = before.decode("utf-8-sig") if before is not None else ""
        after = plan.changes[path].removeprefix("\ufeff")
        diffs.append({"path": str(path), "before_hash": plan.before_hashes[path],
                      "after_hash": sha256_bytes(plan.changes[path].encode("utf-8")),
                      "unified_diff": "".join(difflib.unified_diff(
                          before_text.splitlines(keepends=True), after.splitlines(keepends=True),
                          fromfile=str(path) + " (before)", tofile=str(path) + " (candidate)"))})
    return {
        "mode": "preview",
        "application_id": plan.application_id,
        "plan_id": plan.plan_id,
        "application_path": str(plan.application_path),
        "affected_files": [str(path) for path in sorted(plan.changes, key=lambda item: str(item).casefold())],
        "affected_count": len(plan.changes),
        "evidence_upgrade_proposal": plan.evidence_upgrade_proposal,
        "evidence_status_changed": False,
        "candidate_validation": "passed",
        "diffs": diffs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--topic", action="append", required=True, dest="topics")
    parser.add_argument("--method", required=True)
    parser.add_argument("--topic-methods-file", type=Path,
                        help="可选 JSON：Vault准确相对路径到 {method, reason?}，覆盖共享方法")
    parser.add_argument("--action", required=True)
    parser.add_argument("--result", default="")
    parser.add_argument("--conditions", default="")
    parser.add_argument("--status", choices=sorted(VALID_STATUSES), default="待验证")
    parser.add_argument("--observable-result", action="store_true")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--record-key", default="")
    parser.add_argument("--config")
    parser.add_argument("--confirm-writeback", action="store_true")
    parser.add_argument("--expected-plan-id", help="写入时必须原样传回已预览的 plan_id")
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
            topic_methods=load_topic_methods(args.topic_methods_file),
        )
        if not args.confirm_writeback:
            print(json.dumps(plan_summary(plan), ensure_ascii=False, indent=2))
            return 0
        result = apply_plan(plan, args.expected_plan_id, fail_after=args.fail_after)
        result["mode"] = "writeback"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
