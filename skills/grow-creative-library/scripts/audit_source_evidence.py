"""Read-only audit of durable review records; never certify semantic completeness."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "operate-personal-knowledge-tree" / "scripts"))
from knowledge_tree_config import load_config
from check_source_coverage import check_coverage, line_range


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_file(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("文件定位须为非空相对路径")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or path.drive or ".." in path.parts or ":" in value:
        raise ValueError("文件定位不能使用绝对路径或父目录穿越")
    result = (base / path).resolve()
    if not result.is_relative_to(base.resolve()):
        raise ValueError("文件定位解析后越界")
    return result


def audit(config: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "source-evidence-audit-v1", "configured": config.source_evidence is not None,
        "content_reverified": False, "records": [], "errors": [],
        "meaning": "只核对长期记录、笔记身份和可用的原文本定位；不代替语义复核或用户掌握检验。",
    }
    evidence_root = config.source_evidence
    if evidence_root is None:
        report["status"] = "not_configured_legacy_compatible"
        return report
    seen: set[str] = set()
    note_owners: dict[str, Path] = {}
    raw_names = {"metadata.json", "transcript.md", "subtitle.json", "cookies.txt"}
    for path in evidence_root.rglob("*"):
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(evidence_root.resolve()):
            report["errors"].append({"record": path.name, "error": "证据文件越界"})
        elif path.suffix.lower() not in {".json", ".md"} or path.name.casefold() in raw_names:
            report["errors"].append({"record": str(path.relative_to(evidence_root)), "error": "长期证据区不接受原始媒体、转写或平台元数据"})
    for path in sorted(evidence_root.rglob("record.json")):
        row: dict[str, Any] = {"record": str(path.relative_to(evidence_root)), "raw_source": "not_checked"}
        try:
            if not path.resolve().is_relative_to(evidence_root.resolve()):
                raise ValueError("记录路径越界")
            record = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(record, dict) or record.get("schema") != "source-evidence-v1":
                raise ValueError("不支持的长期记录格式")
            sid = record.get("source_id")
            if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", sid):
                raise ValueError("source_id无效")
            if sid in seen:
                raise ValueError("source_id重复")
            seen.add(sid)
            row["source_id"] = sid
            source, note, coverage, review = (record.get(k) for k in ("source", "note", "coverage", "review"))
            if not all(isinstance(obj, dict) for obj in (source, note, coverage, review)):
                raise ValueError("缺少source/note/coverage/review对象")
            for field in ("title", "locator"):
                if not isinstance(source.get(field), str) or not source[field].strip():
                    raise ValueError(f"来源缺少{field}")
            for obj, field in ((source, "text_sha256"), (note, "sha256")):
                if not isinstance(obj.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", obj[field]):
                    raise ValueError(f"无效{field}")
            if type(coverage.get("version")) is not int or coverage["version"] != 1 or coverage.get("source_sha256") != source["text_sha256"] or coverage.get("note_sha256") != note["sha256"]:
                raise ValueError("覆盖清单与来源/笔记身份不一致")
            if not isinstance(coverage.get("items"), list) or not coverage["items"]:
                raise ValueError("内容清单为空")
            scope = coverage.get("scope")
            if not isinstance(scope, list) or not scope or any(
                not isinstance(v, list) or len(v) != 2 or type(v[0]) is not int or type(v[1]) is not int
                or not 1 <= v[0] <= v[1] for v in scope
            ):
                raise ValueError("历史来源范围无效")
            declared = {n for a, b in scope for n in range(a, b + 1)}
            if not isinstance(review.get("scope"), str) or not review["scope"].strip() or not review.get("date"):
                raise ValueError("缺少历史复核范围或日期")
            note_path = relative_file(config.vault, note.get("path"))
            note_bytes = note_path.read_bytes()
            if sha(note_bytes) != note["sha256"]:
                raise ValueError("笔记字节已变化；历史记录仍保留，但当前绑定需复核")
            if "reviewed_prefix_bytes" in note:
                count = note["reviewed_prefix_bytes"]
                if type(count) is not int or not 0 < count <= len(note_bytes) or sha(note_bytes[:count]) != note.get("reviewed_note_sha256"):
                    raise ValueError("移存时保留的已复核正文前缀已变化；不能只刷新当前笔记哈希")
            note_lines = note_bytes.decode("utf-8-sig").splitlines()
            marker = f"<!-- source-evidence: {sid} -->"
            if marker not in note_bytes.decode("utf-8-sig"):
                raise ValueError("笔记缺少对应长期记录回链标识")
            note_owners[sid] = note_path
            ids: set[str] = set()
            pending: list[str] = []
            for item in coverage["items"]:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip() or item["id"] in ids:
                    raise ValueError("内容项无效或ID重复")
                ids.add(item["id"])
                if not isinstance(item.get("item"), str) or not item["item"].strip():
                    raise ValueError("内容项说明为空")
                src_locator = item.get("source")
                interval = line_range(src_locator.get("lines"), max(declared)) if isinstance(src_locator, dict) else None
                if interval is None or not set(range(interval[0], interval[1] + 1)).issubset(declared):
                    raise ValueError("历史来源定位不在声明范围中")
                status = item.get("status")
                if status not in {"保留", "合并", "待补", "待核"}:
                    raise ValueError("内容项状态无效")
                if status != "保留" and not item.get("reason"):
                    raise ValueError("合并或未完成项缺少理由")
                if status in {"待补", "待核"}:
                    pending.append(item["id"])
                locator = item.get("note")
                if status in {"保留", "合并"} or locator is not None:
                    if not isinstance(locator, dict) or line_range(locator.get("lines"), len(note_lines)) is None:
                        raise ValueError("笔记内容定位无效")
            row.update({"note": note["path"], "note_binding": "matches", "registered_items": len(ids),
                        "pending_items": pending, "review_scope": review["scope"], "review_date": review["date"]})
            hint = source.get("local_text_hint")
            if hint:
                raw_path = relative_file(config.workspace, hint)
                if not raw_path.is_relative_to(config.raw_cache.resolve()):
                    raise ValueError("原文本提示必须指向配置的raw_cache，不允许读取其他位置")
                if not raw_path.is_file():
                    row["raw_source"] = "missing_history_readable_reverification_unavailable"
                else:
                    raw_bytes = raw_path.read_bytes()
                    if sha(raw_bytes) != source["text_sha256"]:
                        row["raw_source"] = "changed_no_automatic_rebind"
                    else:
                        registration = check_coverage(raw_bytes, note_bytes, coverage)
                        if registration["errors"]:
                            raise ValueError("当前原文下的登记无效：" + "; ".join(e["message"] for e in registration["errors"]))
                        row["raw_source"] = "matches_recorded_text"
                        row["registration"] = registration["result"]
                        row["unregistered_ranges"] = registration["unregistered_ranges"]
            else:
                row["raw_source"] = "no_local_text_history_only"
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            row["error"] = str(exc)
            report["errors"].append({"record": row["record"], "error": str(exc)})
        report["records"].append(row)
    for path in config.vault.rglob("*.md"):
        if ".obsidian" in path.parts or ".trash" in path.parts:
            continue
        if not path.resolve().is_relative_to(config.vault.resolve()):
            report["errors"].append({"note": path.name, "error": "笔记回链检查路径越界"})
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            report["errors"].append({"note": str(path.relative_to(config.vault)), "error": str(exc)})
            continue
        for sid in re.findall(r"<!--\s*source-evidence:\s*([^\s>]+)\s*-->", text):
            if note_owners.get(sid) != path.resolve():
                report["errors"].append({"note": str(path.relative_to(config.vault)), "error": f"长期记录{sid}缺失、无效或属于其他笔记"})
    report["status"] = "invalid" if report["errors"] else "record_bindings_valid"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit(load_config(args.config))
    except (OSError, ValueError, RuntimeError) as exc:
        report = {"status": "invalid", "content_reverified": False, "errors": [{"error": str(exc)}]}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["status"])
        for row in report.get("records", []):
            print(f"{row.get('source_id', row['record'])}: {row.get('raw_source')}；待核 {len(row.get('pending_items', []))}")
        for error in report["errors"]:
            print("ERROR: " + error["error"])
        print("历史复核记录不等于本次重新核验了原文或媒体。")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
