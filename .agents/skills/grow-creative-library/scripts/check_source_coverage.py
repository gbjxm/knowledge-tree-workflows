#!/usr/bin/env python3
"""Read-only registration checks; never certify semantic completeness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


STATUSES = {"保留", "合并", "待补", "待核"}
PENDING = {"待补", "待核"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_range(value: Any, count: int) -> tuple[int, int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    start, end = value
    if type(start) is not int or type(end) is not int:
        return None
    if not 1 <= start <= end <= count:
        return None
    return start, end


def consecutive_ranges(numbers: set[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for number in sorted(numbers):
        if result and number == result[-1][1] + 1:
            result[-1][1] = number
        else:
            result.append([number, number])
    return result


def check_coverage(source_data: bytes, note_data: bytes, manifest: Any) -> dict[str, Any]:
    """Validate declared mappings, without inferring claims from either text."""
    report: dict[str, Any] = {
        "result": "invalid",
        "semantic_review": "required",
        "meaning": "仅检查登记、输入版本与定位；不能证明语义保全、事实准确或画面覆盖。",
        "source_sha256": sha256(source_data),
        "note_sha256": sha256(note_data),
        "errors": [],
        "pending_items": [],
        "unregistered_ranges": [],
    }
    errors = report["errors"]

    def error(code: str, message: str, item_id: str | None = None) -> None:
        entry = {"code": code, "message": message}
        if item_id is not None:
            entry["id"] = item_id
        errors.append(entry)

    try:
        source_lines = source_data.decode("utf-8-sig").splitlines()
        note_lines = note_data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        error("encoding", "源文本和笔记必须为 UTF-8；PDF 等二进制文件先提取带定位的文本。")
        return report
    if not isinstance(manifest, dict):
        error("manifest", "覆盖清单必须是 JSON 对象。")
        return report
    if type(manifest.get("version")) is not int or manifest["version"] != 1:
        error("version", "覆盖清单 version 必须为 1。")
    for field in ("source_sha256", "note_sha256"):
        expected = manifest.get(field)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            error("hash", f"{field} 必须填写输入文件原始字节的 SHA-256。")
        elif expected.lower() != report[field]:
            error("stale_input", f"{field} 已变化，覆盖清单不能用于当前输入。")

    scope = manifest.get("scope")
    declared: set[int] = set()
    if not isinstance(scope, list) or not scope:
        error("scope", "scope 必须声明至少一个源文本行号闭区间。")
    else:
        for value in scope:
            interval = line_range(value, len(source_lines))
            if interval is None:
                error("scope", f"无效 scope 行号范围：{value!r}。")
            else:
                declared.update(range(interval[0], interval[1] + 1))
        if declared and not any(source_lines[n - 1].strip() for n in declared):
            error("scope", "声明范围不能只有空白行。")

    def locator(value: Any, lines: list[str], label: str, item_id: str) -> set[int]:
        if not isinstance(value, dict):
            error("locator", f"{label} 必须包含 lines 行号闭区间。", item_id)
            return set()
        interval = line_range(value.get("lines"), len(lines))
        if interval is None:
            error("locator", f"{label}.lines 无效或超出文件范围。", item_id)
            return set()
        selected = "\n".join(lines[interval[0] - 1 : interval[1]])
        if not selected.strip():
            error("locator", f"{label} 定位不能只有空白行。", item_id)
        if "quote" in value:
            quote = value["quote"]
            if not isinstance(quote, str) or not quote.strip():
                error("quote", f"{label}.quote 如填写，必须是非空确切片段。", item_id)
            elif quote.replace("\r\n", "\n") not in selected:
                error("quote", f"{label}.quote 不在指定行段中。", item_id)
        return set(range(interval[0], interval[1] + 1))

    items = manifest.get("items")
    registered: set[int] = set()
    ids: set[str] = set()
    if not isinstance(items, list) or not items:
        error("items", "items 不能为空；空清单不能报告登记闭合。")
        items = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            error("item", f"第 {index} 项必须为对象。")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            item_id = f"#{index}"
            error("id", "每个内容项须有非空 id。", item_id)
        elif item_id in ids:
            error("id", "内容项 id 重复。", item_id)
        ids.add(item_id)
        if not isinstance(item.get("item"), str) or not item["item"].strip():
            error("item", "须说明该项保留的观点、案例、论证或限定条件。", item_id)
        status = item.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            error("status", "status 必须为 保留、合并、待补 或 待核。", item_id)
            status = None
        reason = item.get("reason")
        if status in {"合并", "待补", "待核"} and (
            not isinstance(reason, str) or not reason.strip()
        ):
            error("reason", "合并、待补或待核必须说明理由／缺口。", item_id)
        source_numbers = locator(item.get("source"), source_lines, "source", item_id)
        if not source_numbers.issubset(declared):
            error("scope", "source 定位超出已声明 scope。", item_id)
        registered.update(source_numbers & declared)
        if status in {"保留", "合并"} or item.get("note") is not None:
            locator(item.get("note"), note_lines, "note", item_id)
        if status in PENDING:
            report["pending_items"].append({"id": item_id, "status": status, "reason": reason})

    meaningful = {n for n in declared if source_lines[n - 1].strip()}
    report["unregistered_ranges"] = consecutive_ranges(meaningful - registered)
    report["registered_items"] = len(items)
    if not errors:
        report["result"] = (
            "open" if report["pending_items"] or report["unregistered_ranges"] else "closed"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="UTF-8 source/transcript/extracted text")
    parser.add_argument("--note", required=True, type=Path, help="UTF-8 note")
    parser.add_argument("--coverage", required=True, type=Path, help="Version 1 JSON registration manifest")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    try:
        report = check_coverage(
            args.source.read_bytes(), args.note.read_bytes(),
            json.loads(args.coverage.read_text(encoding="utf-8-sig")),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = {
            "result": "invalid", "semantic_review": "required",
            "errors": [{"code": "input", "message": str(exc)}],
            "pending_items": [], "unregistered_ranges": [],
        }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        label = {"closed": "登记闭合；仍待语义复核", "open": "登记未闭合；仍有待处理项", "invalid": "输入或登记无效"}
        print(label[report["result"]])
        for entry in report["errors"]:
            print(f"ERROR: {entry.get('id', '')} {entry['message']}")
        for entry in report["pending_items"]:
            print(f"PENDING: {entry['id']} {entry['status']} {entry['reason']}")
        for start, end in report["unregistered_ranges"]:
            print(f"UNREGISTERED: 源文本 L{start}-L{end}")
        print("本检查不能证明语义保全、事实准确或画面覆盖。")
    return {"closed": 0, "open": 1, "invalid": 2}[report["result"]]


if __name__ == "__main__":
    raise SystemExit(main())
