from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from knowledge_tree_config import load_config
from obsidian_cli import ObsidianCLI
from knowledge_tree_state import read_global_state, read_state, resolve_action_context


CONFIG = load_config()
WORKSPACE = CONFIG.workspace
VAULT = CONFIG.vault
CONTROL_ROOT = CONFIG.control_root
NORTH_STAR = CONTROL_ROOT / "我的知识树北极星.md"
TREE_STATUS = CONTROL_ROOT / "知识树状态.md"
SKILLS_ROOT = CONFIG.skills_root
VALIDATOR = SKILLS_ROOT / "grow-creative-library" / "scripts" / "validate_note.py"
AUDITOR = SKILLS_ROOT / "grow-creative-library" / "scripts" / "audit_knowledge_system.py"
CONNECTION_AUDITOR = (
    SKILLS_ROOT / "weave-film-knowledge-connections" / "scripts" / "audit_connections.py"
)
RAW_NAMES = {"metadata.json", "transcript.md", "subtitle.json", "audio.m4s"}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def read_event() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def parse_frontmatter(text: str) -> dict[str, str]:
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


def extract_section(text: str, heading: str, max_chars: int = 700) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    body = re.sub(r"\n{3,}", "\n\n", match.group(1).strip())
    return body[:max_chars]


def build_session_context(
    north_star: Path = NORTH_STAR, status: Path = TREE_STATUS, limit: int = 2500,
    *, current_task: str = "", selected_source: str = "", related_blockers: list[str] | None = None,
    vault: Path | None = None, library: Path | None = None, learning_requested: bool = False,
) -> str:
    if not north_star.exists():
        return "个人影视知识树控制文件尚未建立；在写入知识前先检查 AGENTS.md。"

    if library is None and (north_star != NORTH_STAR or status != TREE_STATUS):
        global_state = read_global_state(north_star, status)
        state = {"global_state": global_state, **resolve_action_context(
            global_state, current_task=current_task, related_blockers=related_blockers or [],
            learning_requested=learning_requested)}
    else:
        state = read_state(vault or VAULT, library or CONFIG.knowledge_library, north_star=north_star,
                           status=status, current_task=current_task, selected_source=selected_source,
                           related_blockers=related_blockers or [], learning_requested=learning_requested)
    global_state = state["global_state"]
    north = global_state["north_star"]
    lines = [
        "个人影视知识树运行上下文：",
        "- 优先级：用户当前任务最高；全局背景和系统建议不覆盖当前对话授权范围。",
        "- 当前对话任务：" + (current_task or "未传入；须以本次用户消息为准，不能从历史状态推定当前任务"),
        f"- 系统目的：{north.get('系统目的', '让个人影视创作知识逐渐完整')}",
        f"- 当前重点：{north.get('当前重点', '故事与剧本')}",
        f"- 总体策略：{north.get('总体策略', '六类均衡')}",
        f"- Codex角色：{north.get('Codex角色', '知识导师与研究员')}",
        f"- 默认知识形态：{north.get('默认知识形态', '原理 + 方法 + 案例')}",
        "- 约束：明确想学时由 internalize-film-knowledge 按困惑讲解，明确请求检验才提问；默认只在对话中进行，明确要求保存才回写；知识收尾由 weave-film-knowledge-connections 处理正式关系候选，按已有授权和关系契约写入；北极星和个人偏好变更必须先确认；旧笔记按触碰升级。",
    ]
    if global_state["valid"]:
        confirmed = state.get("global_confirmed") or []
        lines.append("- 已确认的全局待办：" + ("；".join(item["title"] + "（依据：" + item["basis"] + "）" for item in confirmed) or "暂无"))
        pending = state.get("pending_choices") or []
        lines.append("- 待选择的全局事项（未采用）：" + ("；".join(item["title"] for item in pending) or "暂无"))
    else:
        lines.append("- 全局待办读取失败：" + "; ".join(global_state["errors"]))
    suggestion = state["system_suggestion"]
    lines.extend(["- 系统建议（未采用）：" + suggestion["text"], "- 建议依据：" + suggestion["basis"]])
    context = "\n".join(lines)
    return context[:limit]


def snapshot_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    root = Path(tempfile.gettempdir()) / "codex-knowledge-tree"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.json"


def current_snapshot() -> dict[str, list[int]]:
    snapshot: dict[str, list[int]] = {}
    if not VAULT.exists():
        return snapshot
    for path in VAULT.rglob("*.md"):
        if ".obsidian" in path.parts or ".trash" in path.parts:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[str(path.resolve())] = [stat.st_mtime_ns, stat.st_size]
    return snapshot


def save_snapshot(session_id: str) -> None:
    path = snapshot_path(session_id)
    path.write_text(json.dumps(current_snapshot(), ensure_ascii=False), encoding="utf-8")


def changed_since_snapshot(session_id: str) -> list[Path]:
    path = snapshot_path(session_id)
    if not path.exists():
        return []
    try:
        before = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    after = current_snapshot()
    return sorted(Path(item) for item, state in after.items() if before.get(item) != state)


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(flatten_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(flatten_strings(item))
        return result
    return []


def explicit_markdown_paths(payload: dict[str, Any]) -> list[Path]:
    haystack = "\n".join(flatten_strings(payload.get("tool_input", {}))).casefold()
    if ".md" not in haystack:
        return []
    found: list[Path] = []
    for path in VAULT.rglob("*.md"):
        absolute = str(path).casefold()
        relative = path.relative_to(VAULT).as_posix().casefold()
        if absolute in haystack or relative in haystack:
            found.append(path.resolve())
    return sorted(set(found))


def validate_notes(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    environment = {**os.environ, "PYTHONUTF8": "1"}
    for path in sorted(set(paths)):
        if not path.exists() or path.suffix.lower() != ".md" or not within(path, VAULT):
            continue
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        if completed.returncode:
            detail = (completed.stdout or completed.stderr).strip()
            errors.append(f"{path.relative_to(VAULT)}\n{detail}")
    return errors


def check_final_folders(changed: list[Path]) -> list[str]:
    errors: list[str] = []
    roots = sorted({CONFIG.source_notes.resolve(), CONFIG.knowledge_library.resolve()}, key=lambda path: len(path.parts))
    scan_roots: list[Path] = []
    for root in roots:
        if any(root.is_relative_to(parent) for parent in scan_roots):
            continue
        scan_roots.append(root)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.name.lower() in RAW_NAMES:
                errors.append(f"最终目录混入原始产物：{path.relative_to(VAULT)}")
    naked = re.compile(r"^(?:视频|来源)[:：]\s*https?://", flags=re.MULTILINE)
    for path in changed:
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        if naked.search(text):
            errors.append(f"存在裸视频来源链接：{path.relative_to(VAULT)}")
    return errors


def strict_audit() -> list[str]:
    environment = {**os.environ, "PYTHONUTF8": "1"}
    completed = subprocess.run(
        [
            sys.executable,
            str(AUDITOR),
            "--vault",
            str(VAULT),
            "--scope",
            str(CONFIG.knowledge_library.relative_to(CONFIG.vault)),
            "--strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    if completed.returncode:
        return [(completed.stdout or completed.stderr).strip()]
    return []


def connection_audit(paths: list[Path] | None = None) -> list[str]:
    environment = {**os.environ, "PYTHONUTF8": "1"}
    command = [
        sys.executable,
        str(CONNECTION_AUDITOR),
        "--vault",
        str(VAULT),
        "--strict",
    ]
    if paths is not None:
        topic_paths: list[Path] = []
        for path in sorted(set(paths)):
            if not path.exists() or path.suffix.lower() != ".md" or not within(path, VAULT):
                continue
            try:
                props = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError):
                continue
            if props.get("类型") == "主题笔记":
                topic_paths.append(path)
        if not topic_paths:
            return []
        for path in topic_paths:
            command.extend(["--topic", str(path)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    if completed.returncode:
        return [(completed.stdout or completed.stderr).strip()]
    return []


def run_cli_health_checks() -> None:
    cli = ObsidianCLI(
        executable=CONFIG.obsidian_cli,
        vault_name=CONFIG.vault_name,
        vault_path=CONFIG.vault,
    )
    for command in ("unresolved", "orphans", "deadends"):
        cli.run([command, "total"], timeout=8)
    cli.run(["tasks", "todo", "total"], timeout=8)


def post_tool_response(errors: list[str]) -> dict[str, Any]:
    detail = "\n\n".join(errors)[:5000]
    return {
        "decision": "block",
        "reason": "知识树笔记写入后的校验未通过，请先修正。",
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"以下笔记校验失败，请修正后再继续：\n{detail}",
        },
    }


def stop_response(errors: list[str], stop_hook_active: bool) -> dict[str, Any]:
    if not errors or stop_hook_active:
        return {}
    detail = "\n\n".join(errors)[:5000]
    return {
        "decision": "block",
        "reason": f"知识树结束校验失败。修正以下问题并重新验证：\n{detail}",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="Read-only startup context preview; no snapshots or global writes")
        parser.add_argument("--context", action="store_true")
        parser.add_argument("--current-task", default="")
        parser.add_argument("--source", default="")
        parser.add_argument("--blocker", action="append", default=[])
        parser.add_argument("--learning", action="store_true", help="Explicit learning suggestion request for this call only")
        args = parser.parse_args()
        if not args.context:
            parser.error("CLI preview requires --context")
        print(build_session_context(current_task=args.current_task, selected_source=args.source, related_blockers=args.blocker, learning_requested=args.learning))
        return 0
    event = read_event()
    event_name = event.get("hook_event_name", "")
    cwd = Path(event.get("cwd") or WORKSPACE)

    if not within(cwd, WORKSPACE):
        if event_name == "Stop":
            emit({})
        return 0

    session_id = str(event.get("session_id", "unknown"))
    if event_name == "SessionStart":
        save_snapshot(session_id)
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": build_session_context(
                        current_task=str(event.get("current_task") or ""),
                        selected_source=str(event.get("selected_source") or ""),
                        learning_requested=event.get("learning_requested") is True,
                    ),
                }
            }
        )
        return 0

    if event_name == "PostToolUse":
        paths = explicit_markdown_paths(event)
        if not paths:
            paths = changed_since_snapshot(session_id)
        errors = validate_notes(paths) + check_final_folders(paths) + connection_audit(paths)
        if errors:
            emit(post_tool_response(errors))
        return 0

    if event_name == "Stop":
        changed = changed_since_snapshot(session_id)
        errors = validate_notes(changed)
        errors.extend(check_final_folders(changed))
        errors.extend(strict_audit())
        errors.extend(connection_audit())
        run_cli_health_checks()
        emit(stop_response(errors, bool(event.get("stop_hook_active"))))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
