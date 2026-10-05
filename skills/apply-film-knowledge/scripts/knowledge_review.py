"""Evidence-backed review input. Output is a reading pack, never final approval."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from retrieve_knowledge import load_config, resolve_config
from knowledge_evidence import load_corpus, make_review, full_evidence, validate_application, utf8_streams
from knowledge_followup import followup, run_followup
from knowledge_scope import make_scope, restore_scope, can_expand, zoned, normalize_role


def read_request(config, request, config_path):
    """Consume an emitted reading locator; it never selects a new config or scope."""
    if isinstance(request, str):
        request = json.loads(request)
    if not isinstance(request, dict):
        raise ValueError("read-request 必须是返回的 JSON 对象")
    mode = request.get("mode")
    common = {"mode", "snapshot", "scope", "offset", "max_chars", "config"}
    required = {"mode", "snapshot", "scope"}
    if mode == "evidence":
        required.add("read_id")
        allowed = common | {"read_id"}
    elif mode == "section":
        required.update({"path", "heading", "document_hash"})
        allowed = common | {"path", "heading", "document_hash"}
    else:
        raise ValueError("read-request mode 必须为 evidence 或 section")
    if set(request) - allowed or required - set(request):
        raise ValueError("read-request 字段缺失或含未知字段；请原样传入返回对象")
    for name in required - {"scope"}:
        if not isinstance(request[name], str) or not request[name]:
            raise ValueError(f"read-request {name} 必须是非空字符串")
    if request["scope"] is not None and not isinstance(request["scope"], dict):
        raise ValueError("read-request scope 必须是原范围对象")
    if request.get("config") is not None and Path(request["config"]).resolve() != Path(config_path).resolve():
        raise ValueError("read-request 不能切换配置；请使用当前配置重新检索")
    offset, max_chars = request.get("offset", 0), request.get("max_chars", 5000)
    if type(offset) is not int or type(max_chars) is not int or offset < 0 or max_chars < 1:
        raise ValueError("read-request offset 必须为非负整数，max_chars 必须为正整数")
    selected = restore_scope(config, request["scope"]) if request["scope"] is not None else None
    if zoned(config) and selected is None:
        raise ValueError("分区续读必须携带原 scope 和 snapshot")
    if mode == "section":
        from read_knowledge_section import read_section
        return read_section(config_path, request["path"], request["heading"], max_chars,
                            offset, request["snapshot"], request["document_hash"], scope=selected)
    corpus = load_corpus(config, write_index=False, scope=selected)
    if request["snapshot"] != corpus["snapshot"]:
        raise ValueError("知识快照或读取范围已变化，请重新检索")
    item = full_evidence(corpus, request["read_id"])
    full = item["excerpt"]
    if offset > len(full):
        raise ValueError("offset 超过证据长度")
    stop = min(offset + max_chars, len(full))
    item.update(excerpt=full[offset:stop], offset=offset, returned_characters=stop-offset,
                truncated=stop < len(full), read_required=stop < len(full), continuation=None,
                returned_line_start=item["line_start"] + full.count("\n", 0, offset),
                returned_line_end=item["line_start"] + full.count("\n", 0, max(offset, stop-1)))
    if item["truncated"]:
        item["continuation"] = {"mode": "evidence", "read_id": item["id"],
                                "snapshot": corpus["snapshot"], "scope": selected,
                                "offset": stop, "max_chars": max_chars}
    return {"snapshot": corpus["snapshot"], "scope": selected, "evidence": item}


def review_scoped(config, query, questions=(), *, role="", include_paths=(), scope=None,
                  no_cache=False, stage="", material="", budget=9000, **context):
    role = normalize_role(role)
    fixed_scope = scope is not None
    selected = (restore_scope(config, scope) if fixed_scope else
                make_scope(config, role, include_paths) if zoned(config) or include_paths else None)
    if selected is not None:
        role = selected["role"]
    while True:
        corpus = load_corpus(config, write_index=not no_cache, scope=selected)
        result = make_review(corpus, query, questions, role, stage, material, budget, **context)
        if (not fixed_scope and selected and can_expand(selected) and
                all(f["status"] == "gap" for f in result["facets"])):
            selected = make_scope(config, role, include_paths, expanded=True)
            continue
        return result, corpus


def main():
    utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--config")
    parser.add_argument("--query", default="")
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--role", default="")
    parser.add_argument("--stage", default="")
    parser.add_argument("--material", default="")
    parser.add_argument("--task-type", default="")
    parser.add_argument("--object", dest="object_name", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--expected-output", default="")
    parser.add_argument("--budget", type=int, default=9000)
    parser.add_argument("--read-id")
    parser.add_argument("--read-request", help="原样传入返回的 continuation JSON；主题与来源共用，无需重新查询")
    parser.add_argument("--snapshot")
    parser.add_argument("--review-file")
    parser.add_argument("--application-file")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--include-path", action="append", default=[])
    parser.add_argument("--scope", help="续读或验证时原样携带返回的 scope JSON")
    args = parser.parse_args()
    try:
        config_path = resolve_config(args.config)
        config = load_config(config_path)
        if args.read_request is not None:
            forbidden = {"--query", "--question", "--role", "--stage", "--material", "--task-type",
                         "--object", "--constraints", "--expected-output", "--budget", "--read-id",
                         "--snapshot", "--review-file", "--application-file", "--include-path", "--scope"}
            if any(token.split("=", 1)[0] in forbidden for token in sys.argv[1:]):
                raise ValueError("read-request 使用原身份，不可同时传入查询或范围参数")
            result = read_request(config, args.read_request, config_path)
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            return 0
        selected = restore_scope(config, args.scope) if args.scope else None
        if args.scope and (args.include_path or args.role and normalize_role(args.role) != selected["role"]):
            raise ValueError("续读使用原 scope，不能同时改变岗位或追加路径")
        if args.read_id:
            if zoned(config) and (selected is None or not args.snapshot):
                raise ValueError("分区续读必须携带原 scope 和 snapshot")
            corpus = load_corpus(config, write_index=not args.no_cache, scope=selected)
            if args.snapshot and args.snapshot != corpus["snapshot"]:
                raise ValueError("知识快照或读取范围已变化，请重新检索")
            result = {"snapshot": corpus["snapshot"], "scope": corpus.get("scope"),
                      "evidence": full_evidence(corpus, args.read_id)}
        elif args.application_file:
            if args.include_path:
                raise ValueError("验证回执使用原scope，追加范围需重新检索")
            if not args.review_file:
                raise ValueError("核对审查回执需要 --review-file")
            review = json.loads(Path(args.review_file).read_text(encoding="utf-8-sig"))
            application = json.loads(Path(args.application_file).read_text(encoding="utf-8-sig"))
            original_scope = review.get("scope")
            if zoned(config) and original_scope is None:
                raise ValueError("旧审查回执缺少分区范围，请重新检索")
            if selected is not None and selected != original_scope:
                raise ValueError("验证范围与原审查回执不一致")
            corpus = load_corpus(config, write_index=not args.no_cache, scope=original_scope)
            result = validate_application(corpus, review, application)
        else:
            result, corpus = review_scoped(config, args.query, args.question, role=args.role,
                include_paths=args.include_path, scope=selected, no_cache=args.no_cache,
                stage=args.stage, material=args.material, budget=max(2500, args.budget),
                task_type=args.task_type, object_name=args.object_name,
                constraints=args.constraints, expected_output=args.expected_output)
            if args.snapshot and args.snapshot != corpus["snapshot"]:
                raise ValueError("知识快照或读取范围已变化，请重新检查")
            if corpus.get("scope") is not None:
                try:
                    identity = run_followup(config, identity_only=True)
                    impact = identity.get("dependency_impact", {})
                    selected_paths = set(corpus["documents"])
                    affected = [path for path in impact.get("affected_topics", []) if path in selected_paths]
                    result["followup"] = {
                        "status": identity.get("status", "needs_review"),
                        "mode": "identity_only",
                        "identity_snapshot": impact.get("snapshot"),
                        "body_read_permission": False,
                        "affected_topics": affected,
                        "affected_applications": impact.get("affected_applications", []),
                        "global_affected_topic_count": len(impact.get("affected_topics", [])),
                        "identity_error_count": len(impact.get("identity_errors", [])),
                        "unavailable_source_input_count": len(impact.get("unavailable_source_inputs", [])),
                        "reason": "仅附来源身份变化；依赖链不扩大本次正文读取范围，也不自动改变项目判断",
                    }
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    result["followup"] = {
                        "status": "not_checked", "mode": "identity_only", "body_read_permission": False,
                        "error": "依赖身份盘点未完成: " + str(exc),
                    }
            else:
                checkpoint = Path(config["raw_cache"]) / "knowledge-retrieval" / "followup-state-v1.json"
                try:
                    previous = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else None
                    report = followup(corpus, previous)
                    result["followup"] = {k: report[k] for k in ("baseline_missing", "inventory", "changes", "affected_topics")}
                    result["followup"]["pending_issue_count"] = len(report["issues"])
                except (ValueError, OSError, TypeError):
                    result["followup"] = {"error": "补查快照损坏，尚未完成变更检查"}
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 1 if result.get("traceability_pass") is False else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
