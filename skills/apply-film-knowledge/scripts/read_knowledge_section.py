#!/usr/bin/env python3
"""Read a precisely located topic section with explicit completeness and continuation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from retrieve_knowledge import load_config, parse_frontmatter, resolve_config
from knowledge_evidence import load_corpus
from knowledge_scope import make_scope, restore_scope, scope_roots, zoned, normalize_role


def section_bounds(text: str, heading: str) -> tuple[int, int, int]:
    """Return level and exact content offsets; duplicate headings need read-id."""
    rows = text.splitlines(keepends=True)
    headings, offset, fence = [], 0, None
    for line in rows:
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line) if fence is None else None
        if match:
            headings.append((len(match.group(1)), match.group(2), offset, offset + len(line)))
        offset += len(line)
    matches = [entry for entry in headings if entry[1] == heading and entry[0] >= 2]
    if not matches:
        raise ValueError(f"未找到章节：{heading}")
    if len(matches) != 1:
        raise ValueError(f"章节名不唯一：{heading}；请用审查返回的 read-id 精确读取")
    level, _, header_start, start = matches[0]
    end = next((entry[2] for entry in headings if entry[2] > header_start and entry[0] <= level), len(text))
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return level, start, end


def extract_heading(body: str, heading: str) -> tuple[int, str]:
    level, start, end = section_bounds(body, heading)
    return level, body[start:end]


def read_section(config_path, topic_path, heading, max_chars=5000, offset=0,
                 snapshot=None, document_hash=None, *, scope=None, role="", include_paths=()):
    if max_chars < 1 or offset < 0:
        raise ValueError("max-chars 必须为正数，offset 不能为负数")
    if offset and (not snapshot or not document_hash):
        raise ValueError("续读必须携带 continuation 返回的 snapshot 和 document_hash")
    config_path = resolve_config(config_path)
    config = load_config(config_path)
    library = Path(config["knowledge_library"]).resolve(strict=True)
    path = Path(topic_path).resolve(strict=True)
    path.relative_to(library)
    if zoned(config) and snapshot and scope is None:
        raise ValueError("分区续读必须携带原 scope")
    selected = (restore_scope(config, scope) if scope is not None else
                make_scope(config, role, include_paths) if zoned(config) or include_paths else None)
    if scope is not None and (include_paths or role and normalize_role(role) != selected["role"]):
        raise ValueError("续读使用原scope，不可同时改变岗位或追加范围")
    if selected is not None and not any(path == root or root.is_dir() and path.is_relative_to(root)
                                        for root in scope_roots(config, selected)):
        raise ValueError("目标不在本次读取范围；请明确通过 --include-path 指定后重新检索")
    raw = path.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if document_hash and document_hash != actual_hash:
        raise ValueError("目标文章已变化，请重新检索；不能拼接不同版本的章节")
    text = raw.decode("utf-8-sig")
    meta, _ = parse_frontmatter(text)
    if meta.get("类型") != "主题笔记":
        raise ValueError("目标不是主题笔记")
    if str(meta.get("状态", "")) in {"撤回", "已撤回", "停用", "已失效"}:
        raise ValueError("目标主题已撤回或停用，请重新检索")
    corpus = load_corpus(config, write_index=False, scope=selected)
    if corpus["errors"]:
        raise ValueError("知识索引存在读取错误，请先核对错误来源")
    if snapshot and snapshot != corpus["snapshot"]:
        raise ValueError("知识快照已变化，请重新检索，不能沿用旧的续读位置")
    key = path.relative_to(Path(config["vault"])).as_posix()
    if corpus["files"].get(key) != actual_hash or path.read_bytes() != raw:
        raise ValueError("读取期间目标文章发生变化，请重试")
    level, start, end = section_bounds(text, heading)
    full = text[start:end]
    if offset > len(full):
        raise ValueError("offset 超过章节长度")
    stop = min(offset + max_chars, len(full))
    content = full[offset:stop]
    truncated = stop < len(full)
    first_line = text.count("\n", 0, start) + 1
    last_line = text.count("\n", 0, max(start, end - 1)) + 1
    result = {
        "path": str(path), "heading": heading, "level": level, "content": content,
        "evidence_status": meta.get("证据状态", "未标注"),
        "mastery_status": meta.get("掌握状态", "未检验"),
        "document_hash": actual_hash, "snapshot": corpus["snapshot"], "scope": selected,
        "line_start": first_line, "line_end": last_line,
        "returned_line_start": text.count("\n", 0, start + offset) + 1,
        "returned_line_end": text.count("\n", 0, max(start + offset, start + stop - 1)) + 1,
        "characters": len(full), "returned_characters": len(content), "offset": offset,
        "truncated": truncated, "read_required": truncated,
        "continuation": None,
    }
    if truncated:
        result["continuation"] = {
            "config": str(config_path), "path": str(path), "heading": heading,
            "offset": stop, "max_chars": max_chars,
            "snapshot": corpus["snapshot"], "document_hash": actual_hash, "scope": selected,
        }
    return result


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--path", required=True)
    parser.add_argument("--heading", required=True, help="精确且唯一的 H2–H6 标题")
    parser.add_argument("--max-chars", type=int, default=5000)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--snapshot")
    parser.add_argument("--document-hash")
    parser.add_argument("--role", default="")
    parser.add_argument("--include-path", action="append", default=[])
    parser.add_argument("--scope", help="原样携带检索或上次续读的 scope JSON")
    args = parser.parse_args()
    try:
        result = read_section(args.config, args.path, args.heading, args.max_chars,
                              args.offset, args.snapshot, args.document_hash,
                              scope=args.scope, role=args.role, include_paths=args.include_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
