from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_ENV = "KNOWLEDGE_TREE_CONFIG"
CONFIG_RELATIVE = Path(".codex") / "knowledge-tree.json"
SUPPORTED_VERSIONS = {1, 2}
BASE_PATH_FIELDS = (
    "workspace",
    "vault",
    "knowledge_library",
    "source_notes",
    "raw_cache",
    "prompt_box",
    "obsidian_cli",
)


class KnowledgeTreeConfigError(RuntimeError):
    """Raised when the knowledge-tree target cannot be proven safe."""


@dataclass(frozen=True)
class KnowledgeTreeConfig:
    version: int
    workspace: Path
    vault: Path
    vault_name: str
    knowledge_library: Path
    source_notes: Path
    raw_cache: Path
    prompt_box: Path
    obsidian_cli: Path | None
    skills_root: Path
    config_path: Path
    source_evidence: Path | None = None
    creation_root: Path | None = None
    learning_root: Path | None = None
    github_backup: dict[str, str] | None = None

    @property
    def control_root(self) -> Path:
        return self.knowledge_library / "00-待归档与知识地图"

    @property
    def bilibili_cache(self) -> Path:
        return self.raw_cache / "bilibili"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "workspace": str(self.workspace),
            "vault": str(self.vault),
            "vault_name": self.vault_name,
            "knowledge_library": str(self.knowledge_library),
            "source_notes": str(self.source_notes),
            "raw_cache": str(self.raw_cache),
            "prompt_box": str(self.prompt_box),
            "obsidian_cli": str(self.obsidian_cli) if self.obsidian_cli else None,
            "skills_root": str(self.skills_root),
            "config_path": str(self.config_path),
            "source_evidence": str(self.source_evidence) if self.source_evidence else None,
            "creation_root": str(self.creation_root) if self.creation_root else None,
            "learning_root": str(self.learning_root) if self.learning_root else None,
            "github_backup": self.github_backup,
        }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _existing_file(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise KnowledgeTreeConfigError(f"{label}不存在：{path}") from exc
    if not resolved.is_file():
        raise KnowledgeTreeConfigError(f"{label}必须是文件：{resolved}")
    return resolved


def _default_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    script_package_root = Path(__file__).resolve().parents[3]
    candidates.append(script_package_root / CONFIG_RELATIVE)

    cwd = Path.cwd().resolve()
    for root in (cwd, *cwd.parents):
        candidates.append(root / CONFIG_RELATIVE)
    try:
        children = sorted((item for item in cwd.iterdir() if item.is_dir()), key=lambda p: p.name.casefold())
    except OSError:
        children = []
    candidates.extend(child / CONFIG_RELATIVE for child in children)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key not in seen and resolved.is_file():
            seen.add(key)
            unique.append(resolved)
    return unique


def resolve_config_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return _existing_file(Path(path).expanduser(), "知识树配置文件")

    environment_path = os.environ.get(CONFIG_ENV)
    if environment_path:
        candidate = Path(environment_path).expanduser()
        if not candidate.is_absolute():
            raise KnowledgeTreeConfigError(f"{CONFIG_ENV} 必须指向绝对路径：{candidate}")
        return _existing_file(candidate, "知识树配置文件")

    candidates = _default_config_candidates()
    if not candidates:
        raise KnowledgeTreeConfigError(
            "未发现 .codex/knowledge-tree.json；请从便携包根目录运行，"
            f"或用 {CONFIG_ENV} 指向另一份完整配置。"
        )
    if len(candidates) > 1:
        shown = "；".join(str(item) for item in candidates)
        raise KnowledgeTreeConfigError(
            f"发现多份知识树配置，无法安全选择：{shown}。请设置 {CONFIG_ENV}。"
        )
    return candidates[0]


def _path_value(value: Any, field: str, *, base: Path | None, expect_file: bool) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeTreeConfigError(f"配置字段 {field} 必须是非空字符串。")
    candidate = Path(value)
    if base is None:
        if not candidate.is_absolute():
            raise KnowledgeTreeConfigError(f"v1 配置字段 {field} 必须是绝对路径：{value}")
    else:
        if candidate.is_absolute():
            raise KnowledgeTreeConfigError(f"v2 配置字段 {field} 必须是相对路径：{value}")
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KnowledgeTreeConfigError(f"配置字段 {field} 指向的路径不存在：{candidate}") from exc
    if expect_file and not resolved.is_file():
        raise KnowledgeTreeConfigError(f"配置字段 {field} 必须指向文件：{resolved}")
    if not expect_file and not resolved.is_dir():
        raise KnowledgeTreeConfigError(f"配置字段 {field} 必须指向目录：{resolved}")
    return resolved


def _discover_obsidian_cli(workspace: Path) -> Path | None:
    candidates: list[Path] = [workspace / "Obsidian.com", workspace.parent / "Obsidian.com"]
    executable = shutil.which("Obsidian.com")
    if executable:
        candidates.append(Path(executable))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Obsidian" / "Obsidian.com")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Obsidian" / "Obsidian.com")
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _validate_boundaries(config: KnowledgeTreeConfig) -> None:
    if not (config.vault / ".obsidian").is_dir():
        raise KnowledgeTreeConfigError(f"vault 不是有效的 Obsidian 仓库：{config.vault}")
    if not _is_within(config.vault, config.workspace):
        raise KnowledgeTreeConfigError(f"vault 必须位于 workspace 内：{config.vault}")
    for field, candidate in (
        ("knowledge_library", config.knowledge_library),
        ("source_notes", config.source_notes),
        ("prompt_box", config.prompt_box),
    ):
        if not _is_within(candidate, config.vault):
            raise KnowledgeTreeConfigError(f"{field} 必须位于活动仓库内：{candidate}")
    if (config.creation_root is None) != (config.learning_root is None):
        raise KnowledgeTreeConfigError("creation_root 与 learning_root 必须同时配置或同时缺省。")
    for field, zone in (("creation_root", config.creation_root), ("learning_root", config.learning_root)):
        if zone is not None and (zone == config.knowledge_library or not _is_within(zone, config.knowledge_library)):
            raise KnowledgeTreeConfigError(f"{field} 必须是 knowledge_library 内的独立子目录：{zone}")
    if config.creation_root is not None and config.learning_root is not None:
        if (_is_within(config.creation_root, config.learning_root)
                or _is_within(config.learning_root, config.creation_root)):
            raise KnowledgeTreeConfigError("creation_root 与 learning_root 必须是不同且不互相包含的目录。")
    if not _is_within(config.raw_cache, config.workspace):
        raise KnowledgeTreeConfigError(f"raw_cache 必须位于 workspace 内：{config.raw_cache}")
    if _is_within(config.raw_cache, config.vault):
        raise KnowledgeTreeConfigError(f"raw_cache 必须位于活动仓库外：{config.raw_cache}")
    if config.source_evidence is not None:
        evidence = config.source_evidence
        if not _is_within(evidence, config.workspace):
            raise KnowledgeTreeConfigError(f"source_evidence 必须位于 workspace 内：{evidence}")
        if any(_is_within(evidence, other) or _is_within(other, evidence)
               for other in (config.vault, config.raw_cache)):
            raise KnowledgeTreeConfigError("source_evidence 必须与 Vault、raw_cache 分离，不能互相包含。")
    if not _is_within(config.skills_root, config.workspace) and config.version == 2:
        raise KnowledgeTreeConfigError(f"skills_root 必须位于便携工作区内：{config.skills_root}")
    if _is_within(config.skills_root, config.vault):
        raise KnowledgeTreeConfigError(f"skills_root 必须位于活动仓库外：{config.skills_root}")
    if config.version == 2 and not _is_within(config.config_path, config.workspace):
        raise KnowledgeTreeConfigError(f"v2 配置文件必须位于便携工作区内：{config.config_path}")


def load_config(path: Path | str | None = None) -> KnowledgeTreeConfig:
    config_path = resolve_config_path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeTreeConfigError(f"无法读取知识树配置：{config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgeTreeConfigError("知识树配置根节点必须是 JSON 对象。")

    version = payload.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise KnowledgeTreeConfigError(
            f"不支持的知识树配置版本：{version!r}；仅支持 {sorted(SUPPORTED_VERSIONS)}。"
        )
    required = {"version", *BASE_PATH_FIELDS, "vault_name"}
    if version == 2:
        required.add("skills_root")
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise KnowledgeTreeConfigError("知识树配置缺少字段：" + ", ".join(missing))

    vault_name = payload["vault_name"]
    if not isinstance(vault_name, str) or not vault_name.strip():
        raise KnowledgeTreeConfigError("配置字段 vault_name 必须是非空字符串。")

    if version == 1:
        workspace = _path_value(payload["workspace"], "workspace", base=None, expect_file=False)
        base = None
    else:
        workspace = _path_value(
            payload["workspace"], "workspace", base=config_path.parent, expect_file=False
        )
        base = workspace

    directories = {
        field: _path_value(payload[field], field, base=base, expect_file=False)
        for field in ("vault", "knowledge_library", "source_notes", "raw_cache")
    }
    prompt_box = _path_value(payload["prompt_box"], "prompt_box", base=base, expect_file=True)
    source_evidence = None
    if "source_evidence" in payload and payload["source_evidence"] is not None:
        source_evidence = _path_value(
            payload["source_evidence"], "source_evidence", base=base, expect_file=False
        )

    zones: dict[str, Path | None] = {}
    for field in ("creation_root", "learning_root"):
        zones[field] = (
            _path_value(payload[field], field, base=base, expect_file=False)
            if payload.get(field) is not None else None
        )

    if version == 1:
        obsidian_cli = _path_value(payload["obsidian_cli"], "obsidian_cli", base=None, expect_file=True)
        skills_root = Path(__file__).resolve().parents[2]
    else:
        raw_cli = payload["obsidian_cli"]
        if raw_cli is None:
            obsidian_cli = None
        elif raw_cli == "discover":
            obsidian_cli = _discover_obsidian_cli(workspace)
        else:
            obsidian_cli = _path_value(raw_cli, "obsidian_cli", base=workspace, expect_file=True)
        skills_root = _path_value(payload["skills_root"], "skills_root", base=workspace, expect_file=False)

    backup = payload.get("github_backup")
    if backup is not None:
        if not isinstance(backup, dict) or set(backup) != {"repository", "branch"}:
            raise KnowledgeTreeConfigError("github_backup 只允许 repository 与 branch，不保存凭据。")
        repository, branch = backup["repository"], backup["branch"]
        if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
            raise KnowledgeTreeConfigError("github_backup.repository 必须为 owner/repo。")
        if (not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", branch)
                or any(v in branch for v in ("..", "//", "@{"))
                or branch.endswith(("/", ".", ".lock"))):
            raise KnowledgeTreeConfigError("github_backup.branch 不是合法分支名。")

    config = KnowledgeTreeConfig(
        version=version,
        workspace=workspace,
        vault=directories["vault"],
        vault_name=vault_name.strip(),
        knowledge_library=directories["knowledge_library"],
        source_notes=directories["source_notes"],
        raw_cache=directories["raw_cache"],
        prompt_box=prompt_box,
        obsidian_cli=obsidian_cli,
        skills_root=skills_root.resolve(),
        config_path=config_path,
        source_evidence=source_evidence,
        creation_root=zones["creation_root"],
        learning_root=zones["learning_root"],
        github_backup=backup,
    )
    _validate_boundaries(config)
    return config


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        config = load_config()
    except KnowledgeTreeConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
