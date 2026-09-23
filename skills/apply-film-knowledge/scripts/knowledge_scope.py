"""Resolve call-local reading paths before opening note bodies."""
from __future__ import annotations
import json
from pathlib import Path

ROLE_DIRS = {"A": "A-制片与协作", "B": "B-故事与剧本", "C": "C-导演与视觉", "D": "D-声音与后期", "E": "E-发行与复盘"}
EXCLUDED = {".obsidian", ".git", ".trash", "__pycache__"}


def normalize_role(role):
    role = (role or "").upper()
    return "C" if role in {"C1", "C2"} else role


def zoned(config):
    if bool(config.get("creation_root")) != bool(config.get("learning_root")):
        raise ValueError("分区配置必须同时提供 creation_root 与 learning_root")
    return bool(config.get("creation_root"))


def dedupe_paths(paths):
    result = []
    for path in sorted(set(Path(p).resolve(strict=True) for p in paths), key=lambda p: (len(p.parts), str(p).casefold())):
        if not any(root.is_dir() and path.is_relative_to(root) for root in result):
            result.append(path)
    return result


def include_path(config, value):
    vault = Path(config["vault"]).resolve(strict=True)
    path = Path(value)
    path = (path if path.is_absolute() else vault / path).resolve(strict=True)
    roots = [Path(config[k]).resolve(strict=True) for k in
             (("creation_root", "learning_root") if zoned(config) else ("knowledge_library", "source_notes"))]
    if not any(path.is_relative_to(root) for root in roots) or set(path.relative_to(vault).parts) & EXCLUDED:
        raise ValueError("指定范围必须位于配置的创作区或学习区：" + str(value))
    if not path.is_dir() and (not path.is_file() or path.suffix.lower() != ".md"):
        raise ValueError("指定范围必须是 Markdown 文件或准确目录：" + str(value))
    return path


def make_scope(config, role="", include_paths=(), expanded=False):
    vault = Path(config["vault"]).resolve(strict=True)
    role = normalize_role(role)
    includes = dedupe_paths(include_path(config, p) for p in include_paths)
    if zoned(config):
        creation = Path(config["creation_root"]).resolve(strict=True)
        if not creation.is_relative_to(vault):
            raise ValueError("创作区越出 Vault")
        if role in ROLE_DIRS and not expanded:
            paths = [creation / ROLE_DIRS[role], creation / "岗位共用"]
            paths = [p for p in paths if p.is_dir()]
        else:
            paths = [creation]
        mode = "zones"
    else:
        paths = [Path(config[k]) for k in ("knowledge_library", "source_notes")]
        mode = "legacy"
    paths = dedupe_paths([*paths, *includes])
    return {"version": 1, "mode": mode, "role": role, "expanded": bool(expanded),
            "include_paths": [p.relative_to(vault).as_posix() for p in includes],
            "paths": [p.relative_to(vault).as_posix() for p in paths]}


def restore_scope(config, scope):
    if isinstance(scope, str):
        scope = json.loads(scope)
    if not isinstance(scope, dict) or scope.get("version") != 1 or type(scope.get("expanded")) is not bool:
        raise ValueError("续读 scope 无效，请使用检索返回的完整范围")
    if not isinstance(scope.get("include_paths"), list) or not all(isinstance(p, str) for p in scope["include_paths"]):
        raise ValueError("scope.include_paths 无效")
    expected = make_scope(config, scope.get("role", ""), scope["include_paths"], scope["expanded"])
    if scope != expected:
        raise ValueError("续读 scope 与当前配置或路径不一致，请重新检索")
    return expected


def scope_roots(config, scope):
    vault = Path(config["vault"]).resolve(strict=True)
    return [vault / p for p in restore_scope(config, scope)["paths"]]


def markdown_paths(roots):
    files = {}
    for root in dedupe_paths(roots):
        for path in ([root] if root.is_file() else sorted(root.rglob("*.md"))):
            if set(path.parts) & EXCLUDED:
                continue
            resolved = path.resolve(strict=True)
            if not (resolved == root or root.is_dir() and resolved.is_relative_to(root)):
                raise ValueError("笔记符号链接越出本次读取范围：" + str(path))
            files[resolved] = resolved
    return sorted(files.values(), key=lambda p: str(p).casefold())


def can_expand(scope):
    return scope["mode"] == "zones" and scope["role"] in ROLE_DIRS and not scope["expanded"]
