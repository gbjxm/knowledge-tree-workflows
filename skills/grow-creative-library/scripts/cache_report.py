from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

SKILLS_ROOT = Path(__file__).resolve().parents[2]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def no_links(path: Path) -> None:
    """Check before resolving; neither a selected root nor its parents may redirect."""
    for part in reversed((path, *path.parents)):
        try:
            if is_link(part):
                raise ValueError("目录链接或重解析点已跳过")
        except FileNotFoundError:
            continue


def walk_files(root: Path, warnings: list[dict[str, str]]) -> Iterator[tuple[Path, os.stat_result]]:
    try:
        no_links(root)
        if not root.exists():
            warnings.append({"path": str(root), "reason": "目录不存在"})
            return
        if not root.is_dir():
            warnings.append({"path": str(root), "reason": "不是目录"})
            return
        for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            try:
                if is_link(child):
                    warnings.append({"path": str(child), "reason": "目录链接或重解析点已跳过"})
                elif child.is_dir():
                    yield from walk_files(child, warnings)
                elif child.is_file():
                    yield child, child.stat()
                else:
                    warnings.append({"path": str(child), "reason": "非常规文件已跳过"})
            except OSError as exc:
                warnings.append({"path": str(child), "reason": type(exc).__name__})
    except (OSError, ValueError) as exc:
        warnings.append({"path": str(root), "reason": str(exc)})


def summary(count: int, size: int, extensions: dict[str, int]) -> dict[str, Any]:
    return {"file_count": count, "bytes": size, "human_size": format_size(size),
            "by_extension": dict(sorted(extensions.items(), key=lambda item: (-item[1], item[0])))}


def group_name(path: Path, root: Path) -> str:
    parts = path.relative_to(root).parts[:-1]
    return "/".join(parts[:2]) if parts else "."


def directory_kind(path: Path, configured_cache: Path) -> str:
    # Directory labels describe organization only, never retention/deletion eligibility.
    try:
        family = path.relative_to(configured_cache).parts[0]
    except (ValueError, IndexError):
        return "用途尚未核对"
    if family in {"bilibili", "books", "douyin"}:
        return "来源材料目录"
    if family in {"github-backup", "github-backup-implementation"}:
        return "备份与恢复产物"
    if family in {"knowledge-quality", "knowledge-retrieval", "release-tests", "release-staging",
                  "cache-maintenance"}:
        return "维护与试验产物（可能包含来源依据）"
    if family == "film-breakdown":
        return "拉片材料目录"
    return "用途尚未核对"


def source_path(config: Any, hint: Any) -> Path:
    if not isinstance(hint, str) or not hint.strip():
        raise ValueError("没有有效的原材料相对定位")
    parts = hint.replace("\\", "/").split("/")
    if any(p in {"", ".", ".."} or ":" in p for p in parts):
        raise ValueError("原材料定位不是安全的工作区相对路径")
    path = config.workspace.joinpath(*parts)
    if not path.is_relative_to(config.raw_cache):
        raise ValueError("原材料定位不在配置的 raw_cache 内，未读取")
    sensitive = {".env", "auth.json", "credentials.json", "secrets.json", "cookies.txt",
                 "id_rsa", "id_ed25519"}
    if any(p.casefold() in sensitive or p.casefold().startswith(".env.") for p in parts):
        raise ValueError("原材料定位指向敏感文件，未读取")
    if path.suffix.lower() in {".key", ".pem", ".pfx", ".p12", ".dpapi", ".clixml"}:
        raise ValueError("原材料定位指向敏感文件，未读取")
    no_links(path)
    return path


def source_references(config: Any, root: Path, warnings: list[dict[str, str]]) -> dict[str, Any]:
    found: dict[str, dict[str, Any]] = {}
    records = 0
    outside_scope = 0
    if config.source_evidence is not None:
        for record_path, _ in walk_files(config.source_evidence, warnings):
            if record_path.name != "record.json":
                continue
            records += 1
            try:
                data = json.loads(record_path.read_text(encoding="utf-8-sig"))
                if (not isinstance(data, dict) or data.get("schema") != "source-evidence-v1"
                        or not isinstance(data.get("source_id"), str) or not data["source_id"]
                        or not isinstance(data.get("source"), dict)):
                    raise ValueError("来源记录格式无效")
                source = data["source"]
                path = source_path(config, source.get("local_text_hint"))
                if not path.is_relative_to(root):
                    outside_scope += 1
                    continue
                key = os.path.normcase(str(path))
                item = found.setdefault(key, {
                    "path": str(path), "workspace_relative": path.relative_to(config.workspace).as_posix(),
                    "retention": "保留：现有长期来源记录引用；缺失或变化也不能自动解除保留",
                    "references": []})
                item["references"].append({
                    "source_id": data["source_id"],
                    "record": record_path.relative_to(config.workspace).as_posix(),
                    "expected_sha256": source.get("text_sha256")})
            except (OSError, ValueError, TypeError) as exc:
                warnings.append({"path": str(record_path), "reason": str(exc)})

    for item in found.values():
        path = Path(item["path"])
        item.update(exists=None, sha256=None, file_status="unreadable")
        try:
            no_links(path)
            if not path.exists():
                item.update(exists=False, file_status="missing")
            elif not path.is_file():
                item.update(exists=True, file_status="not_regular_file")
            else:
                before = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                after = path.stat()
                stable = (before.st_size, before.st_mtime_ns, before.st_ino) == (
                    after.st_size, after.st_mtime_ns, after.st_ino)
                item.update(exists=True, bytes=after.st_size,
                            sha256=digest.hexdigest() if stable else None,
                            file_status="present" if stable else "changed_during_read")
        except (OSError, ValueError) as exc:
            warnings.append({"path": str(path), "reason": str(exc)})
        for ref in item["references"]:
            expected = ref["expected_sha256"]
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                ref["hash_status"] = "invalid_expected_hash"
            elif item["file_status"] != "present":
                ref["hash_status"] = item["file_status"]
            else:
                ref["hash_status"] = "match" if expected == item["sha256"] else "mismatch"
    return {"records_seen": records, "outside_selected_scope": outside_scope,
            "files": sorted(found.values(), key=lambda item: item["path"].casefold())}


def collect_report(cache: Path, config: Any, *, details: bool = False) -> dict[str, Any]:
    # Keep the explicit positional cache override, without resolving away a junction.
    root = Path(os.path.abspath(cache))
    warnings: list[dict[str, str]] = []
    extensions: dict[str, int] = defaultdict(int)
    groups: dict[str, dict[str, Any]] = {}
    count = total = 0
    for path, info in walk_files(root, warnings):
        count += 1
        total += info.st_size
        ext = path.suffix.lower() or "[无扩展名]"
        extensions[ext] += info.st_size
        if details:
            name = group_name(path, root)
            group = groups.setdefault(name, {
                "path": name, "kind": directory_kind(path, config.raw_cache),
                "file_count": 0, "bytes": 0, "by_extension": defaultdict(int),
                "referenced_file_count": 0})
            group["file_count"] += 1
            group["bytes"] += info.st_size
            group["by_extension"][ext] += info.st_size
    result = {"cache": str(root), **summary(count, total, extensions)}
    if details:
        refs = source_references(config, root, warnings)
        for item in refs["files"]:
            name = group_name(Path(item["path"]), root)
            if name in groups and item["file_status"] in {"present", "changed_during_read"}:
                groups[name]["referenced_file_count"] += 1
        for group in groups.values():
            group.update(summary(group["file_count"], group["bytes"], group["by_extension"]))
            group["unassessed_file_count"] = max(0, group["file_count"] - group["referenced_file_count"])
            group["unassessed_policy"] = "尚未核对用途，暂时保留；未登记不等于未使用"
        result["details"] = {
            "groups": sorted(groups.values(), key=lambda item: (-item["bytes"], item["path"])),
            "source_references": refs,
            "interpretation": "目录类别仅是存放线索；程序不判定可删除文件，哈希匹配不代表内容复核。",
            "backup_scope": "原材料未纳入知识树 GitHub 备份；其他副本未核实。",
            "content_reverified": False}
    if warnings:
        result["warnings"] = warnings
    return result


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description="Report cache usage and source references without changing files.")
    parser.add_argument("cache", nargs="?", type=Path, default=config.raw_cache)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--details", action="store_true", help="只读目录分组和现有长期来源引用，不判断可删除文件")
    args = parser.parse_args(argv)
    result = collect_report(args.cache, config, details=args.details)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"缓存目录：{result['cache']}")
    print(f"文件数量：{result['file_count']}")
    print(f"占用空间：{result['human_size']}")
    if result["by_extension"]:
        print("按类型：")
        for extension, size in result["by_extension"].items():
            print(f"- {extension}: {format_size(size)}")
    if args.details:
        print("\n按材料或任务目录（最多两级）：")
        for group in result["details"]["groups"]:
            print(f"- {group['path']} | {group['kind']} | {group['human_size']} | "
                  f"{group['file_count']} 文件 | 来源记录引用 {group['referenced_file_count']} 个 | "
                  f"尚未核对用途 {group['unassessed_file_count']} 个")
        print("\n已有来源引用（同一文件只列一次）：")
        for item in result["details"]["source_references"]["files"]:
            labels = {"match": "匹配", "mismatch": "不匹配", "missing": "缺失",
                      "changed_during_read": "读取期间变化", "invalid_expected_hash": "记录哈希无效",
                      "not_regular_file": "不是常规文件", "unreadable": "无法读取"}
            refs = "；".join(f"{ref['source_id']}：{labels[ref['hash_status']]}" for ref in item["references"])
            print(f"- {item['workspace_relative']} | {item['retention']} | {refs}")
        print("\n" + result["details"]["interpretation"])
        print(result["details"]["backup_scope"])
        print("未登记材料尚未核对用途，暂时保留。")
    for warning in result.get("warnings", []):
        print(f"注意：{warning['path']}：{warning['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
