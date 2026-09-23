"""Evidence-backed review input. Output is a reading pack, never final approval."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from retrieve_knowledge import load_config, resolve_config
from knowledge_evidence import load_corpus, make_review, full_evidence, validate_application, utf8_streams
from knowledge_followup import followup
from knowledge_scope import make_scope, restore_scope, can_expand, zoned, normalize_role


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
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument("--snapshot")
    parser.add_argument("--review-file")
    parser.add_argument("--application-file")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--include-path", action="append", default=[])
    parser.add_argument("--scope", help="续读或验证时原样携带返回的 scope JSON")
    args = parser.parse_args()
    try:
        config = load_config(resolve_config(args.config))
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
                result["followup"] = {"status": "not_checked", "reason": "本次分区读取不替代全局增量盘点，也不将未读取文件报告为删除"}
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
