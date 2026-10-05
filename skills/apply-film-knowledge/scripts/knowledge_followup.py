"""Detect new/changed sources, stale dependencies and missing source-topic links.

Default read-only. --checkpoint saves file identities and actual dependencies
outside the Vault; it does NOT confirm relationships or mark issues resolved.
Exit code 0 means the report was produced; review status is reported separately.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from retrieve_knowledge import load_config, resolve_config
from knowledge_evidence import load_corpus, candidates, atomic_json, utf8_streams, inside
from knowledge_dependencies import load_dependency_catalog, calculate_dependency_impact
from knowledge_scope import make_scope, zoned

RETIRED = {"撤回", "停用", "已失效", "已撤回"}
PROVENANCE_TYPES = {"材料总览", "分集笔记", "来源笔记"}


def snapshot_state(corpus, previous=None, pending_topics=None, *, dependency_catalog=None,
                   pending_dependency_reviews=None):
    if corpus.get("scope") is not None and dependency_catalog is None:
        raise ValueError("全局补查检查点不能由局部读取范围生成")
    prior_dependencies = (previous or {}).get("dependencies", {})
    accumulated = dict(prior_dependencies)
    for key, doc in corpus["documents"].items():
        if doc["kind"] == "topic":
            accumulated[key] = sorted(set(accumulated.get(key, [])) | set(doc["source_targets"]))
    if dependency_catalog is not None:
        # The active v2 graph is exactly today's declarations. Old edges remain
        # only in pending impact chains, never accumulated as current knowledge.
        accumulated = {}
        for edge in dependency_catalog["edges"]:
            accumulated.setdefault(edge["dependent"], []).append(edge["dependency"])
        accumulated = {key: sorted(set(value)) for key, value in accumulated.items()}
    state = {"version": 2 if dependency_catalog is not None else 1,
            "vault": corpus["vault"], "snapshot": corpus["snapshot"],
            "files": corpus["files"],
            "dependencies": accumulated,
            "pending_topic_reviews": list(pending_topics if pending_topics is not None else (previous or {}).get("pending_topic_reviews", []))}
    if dependency_catalog is not None:
        state["dependency_catalog"] = dependency_catalog
        state["pending_dependency_reviews"] = list(pending_dependency_reviews or [])
        state["body_scope"] = corpus.get("scope")
        state["body_snapshot"] = corpus["snapshot"]
    return state


def followup(corpus, previous=None, limit=12, include_candidates=False, *, identity_catalog=None):
    if corpus.get("scope") is not None and identity_catalog is None:
        raise ValueError("全局增量补查需要完整盘点，不能把未读取内容当成删除")
    docs, files = corpus["documents"], corpus["files"]
    previous = previous or {}
    if previous and (previous.get("version") not in (1, 2) or not isinstance(previous.get("files"), dict)
                     or not isinstance(previous.get("dependencies"), dict)):
        raise ValueError("补查快照结构无效")
    if previous and previous.get("vault") != corpus["vault"]:
        raise ValueError("补查快照属于另一个 Vault")
    old = previous.get("files", {})
    added = sorted(set(files) - set(old)) if previous else []
    removed = sorted(set(old) - set(files))
    changed = sorted(k for k in set(old) & set(files) if files[k] != old[k])
    renamed = []
    for gone in removed:
        matches = [new for new in added if files[new] == old[gone]]
        if len(matches) == 1:
            renamed.append({"from": gone, "to": matches[0]})
    changed_set = set(changed + removed)
    revoked = [k for k, d in docs.items() if str(d["meta"].get("状态", "")) in RETIRED]
    dependencies = {**previous.get("dependencies", {})}
    for k, d in docs.items():
        if d["kind"] == "topic":
            dependencies[k] = sorted(set(dependencies.get(k, [])) | set(d["source_targets"]))
    affected = sorted(set(k for k, refs in dependencies.items() if set(refs) & (changed_set | set(revoked))) |
                      set(previous.get("pending_topic_reviews", [])))
    issues = list(corpus["errors"])
    pending = []
    for key, doc in docs.items():
        issues += [{"path": key, "kind": "outside_index" if item["reason"] == "exists_outside_index" else "broken_link", **item} for item in doc["broken_links"]]
        if doc["kind"] == "source":
            topic_refs = doc["topic_targets"]
            reverse = [k for k, d in docs.items() if d["kind"] == "topic" and key in d["source_targets"]]
            document_type = str(doc["meta"].get("类型", "未标注"))
            # A source map may intentionally summarize routes to topics. Keep
            # its one-way link visible without treating it as proven provenance
            # or silently deciding that a reverse link should be added.
            link_role = ("navigation" if document_type == "来源地图" else
                         "provenance" if document_type in PROVENANCE_TYPES else "unclassified")
            for target in sorted(set(topic_refs) ^ set(reverse)):
                issues.append({"path": key, "kind": "one_way_source_link", "topic": target,
                               "document_type": document_type, "link_role": link_role})
            if not topic_refs and not reverse and key not in revoked:
                independent = doc["meta"].get("关联检查") == "独立保留" and bool(doc["meta"].get("独立理由"))
                if not independent:
                    pending.append(key)
                    issues.append({"path": key, "kind": "source_not_integrated",
                                   "meaning": "待比较或合理独立，不能据此断言应建立关系"})
        elif not doc["source_targets"] and not doc["urls"]:
            issues.append({"path": key, "kind": "topic_provenance_unresolved"})
    exact = defaultdict(list)
    urls = defaultdict(list)
    titles = defaultdict(list)
    for k, d in docs.items():
        titles[d["title"]].append(k)
        if d["kind"] == "source":
            exact[d["body_hash"]].append(k)
            # A bundle's cited URLs do not make the whole bundle a duplicate.
            if len(d["urls"]) == 1:
                urls[d["urls"][0]].append(k)
    duplicate_groups = [v for v in exact.values() if len(v) > 1]
    same_origin = [v for v in urls.values() if len(v) > 1]
    duplicate_titles = [v for v in titles.values() if len(v) > 1]
    comparisons = []
    if include_candidates:
        topics = [k for k, d in docs.items() if d["kind"] == "topic"]
        priority = sorted(set(added + changed + pending) & set(docs),
                          key=lambda k: (k not in added + changed, k))
        eligible = [k for k in priority if docs[k]["kind"] == "source" and k not in revoked]
        for key in eligible[:limit]:
            d = docs[key]
            descriptive = [b["text"] for b in d["blocks"] if any(t in b["heading"] for t in ("核心观点", "核心命题", "方法", "材料简介"))]
            query = " ".join((d["title"], str(d["meta"].get("主题", "")), str(d["meta"].get("解决问题", "")), " ".join(descriptive)[:700]))
            rows = candidates(corpus, query, keys=topics, limit=12)
            seen, targets = set(), []
            for r in rows:
                if r["key"] in seen:
                    continue
                seen.add(r["key"])
                targets.append({"topic": r["key"], "heading": r["block"]["heading"],
                                "matched_terms": r["matched_terms"], "status": "unconfirmed_reading_candidate"})
                if len(targets) == 2:
                    break
            comparisons.append({"source": key, "candidates": targets,
                                "decision_needed": "比较正文后判定重复、补充、案例、边界变化、冲突或独立"})
        deferred = max(0, len(eligible) - limit)
    else:
        eligible = pending
        deferred = len(pending)
    issue_counts = Counter(item.get("kind", "index_error") for item in issues)
    one_way_roles = Counter(item.get("link_role", "unclassified") for item in issues
                            if item.get("kind") == "one_way_source_link")
    return {"schema": "knowledge-followup-v1", "snapshot": corpus["snapshot"],
            "baseline_missing": not bool(previous),
            "inventory": {"topics": sum(d["kind"] == "topic" for d in docs.values()),
                          "sources": sum(d["kind"] == "source" for d in docs.values())},
            "changes": {"added": added, "modified": changed, "removed": removed, "renamed": renamed},
            "affected_topics": affected, "revoked": revoked,
            "previous_review_packs_stale": bool(previous and previous.get("snapshot") != corpus["snapshot"]),
            "issues": issues, "exact_duplicates": duplicate_groups,
            "issue_summary": {"total": len(issues), "by_kind": dict(sorted(issue_counts.items())),
                              "one_way_by_role": dict(sorted(one_way_roles.items())),
                              "affected_topic_reviews": len(affected),
                              "affected_topics_in_issue_total": False},
            "same_origin_groups": same_origin, "duplicate_titles": duplicate_titles,
            "comparisons": comparisons, "deferred_comparisons": deferred,
            "comparison_scope": {"suggest": include_candidates, "limit": limit,
                                 "eligible": len(eligible), "shown": len(comparisons), "deferred": deferred,
                                 "deferred_meaning": "not_shown_in_this_invocation" if include_candidates else "sources_awaiting_comparison",
                                 "advances_review_progress": False},
            "semantic_links_written": 0, "status": "needs_review" if issues or comparisons or affected or duplicate_groups or duplicate_titles else "structural_check_pass"}


def run_followup(config, checkpoint=False, suggest=False, limit=12,
                 reviewed_topics=None, expected_snapshot=None, review_reason="",
                 identity_only=False, include_paths=()):
    # Identity inventory is independent of content review. It does not call the
    # unscoped body loader or grant retrieval access to learning notes.
    catalog = load_dependency_catalog(config)
    if identity_only and (suggest or reviewed_topics or include_paths):
        raise ValueError("身份盘点不生成正文候选或确认内容复核")
    scope = make_scope(config, include_paths=include_paths) if zoned(config) else None
    if include_paths and not zoned(config):
        scope = make_scope(config, include_paths=include_paths)
    corpus = None if identity_only else load_corpus(config, write_index=checkpoint, scope=scope)
    target = Path(config["raw_cache"]) / "knowledge-retrieval" / "followup-state-v1.json"
    if inside(target.resolve(), Path(config["vault"]).resolve()):
        raise ValueError("检查点不能写入 Vault")
    previous = None
    if target.is_file():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            raise ValueError("补查快照损坏；保持原文件并报告，不能冒充无变化")
    if previous and previous.get("vault") != catalog["vault"]:
        raise ValueError("补查快照属于另一个 Vault")
    impact = calculate_dependency_impact(catalog, previous)
    if identity_only:
        # Read-only inventory has its own identity snapshot; it does not replace
        # a full follow-up checkpoint with a narrower content observation.
        if checkpoint:
            raise ValueError("身份盘点不能推进完整内容检查点")
        return {"schema": "knowledge-dependency-inventory-v1", "snapshot": catalog["snapshot"],
                "dependency_impact": impact, "checkpoint_saved": False,
                "identity_inventory": {"notes": sum(n["kind"] != "source_identity" for n in catalog["nodes"].values()),
                                       "source_records": sum(n["kind"] == "source_identity" for n in catalog["nodes"].values())},
                "body_read_permission": False, "status": "needs_review" if impact["pending_reviews"] or catalog["errors"] or catalog["unresolved"] else "identity_inventory_complete"}
    # Body comparisons stay in today's explicit scope; the identity catalog,
    # rather than a narrower body corpus, decides global changes and deletion.
    body_previous = dict(previous) if previous else None
    if body_previous is not None:
        allowed = lambda key: scope is None or any(key == root or key.startswith(root + "/") for root in scope["paths"])
        body_previous["files"] = {key: value for key, value in previous["files"].items() if allowed(key)}
        body_previous["dependencies"] = {key: value for key, value in previous["dependencies"].items() if allowed(key)}
        body_previous["snapshot"] = previous.get("body_snapshot", previous.get("snapshot"))
    report = followup(corpus, body_previous, limit, suggest, identity_catalog=catalog)
    report["body_scope"] = scope
    report["identity_scope"] = {"paths": [config[name] for name in ("knowledge_library", "source_notes", "prompt_box") if config.get(name)],
                                "source_evidence": config.get("source_evidence"), "body_read_permission": False}
    report["comparison_scope"]["body_scope"] = scope
    report["duplicate_scope"] = "authorized_body_scope_only"
    report["body_inventory"] = report["inventory"]
    source_types = {"材料总览", "分集笔记", "来源笔记", "来源地图"}
    report["inventory"] = {
        "topics": sum(node["kind"] == "topic" for node in catalog["nodes"].values()),
        "sources": sum(node.get("note_type") in source_types for node in catalog["nodes"].values()),
        "applications": sum(node["kind"] == "application" for node in catalog["nodes"].values()),
        "source_records": sum(node["kind"] == "source_identity" for node in catalog["nodes"].values())}
    report["inventory_scope"] = "complete_configured_identity_catalog"
    report["body_changes"] = report["changes"]
    report["changes"] = {name: impact["changes"][name] for name in ("added", "modified", "removed", "renamed")}
    report["identity_snapshot"] = catalog["snapshot"]
    report["snapshot"] = hashlib.sha256((corpus["snapshot"] + "|" + catalog["snapshot"]).encode("utf-8")).hexdigest()
    report["dependency_impact"] = impact
    report["affected_topics"] = sorted(set(report["affected_topics"]) | set(impact["affected_topics"]))
    report["affected_applications"] = impact["affected_applications"]
    report["affected_methods"] = impact["affected_methods"]
    report["issue_summary"]["affected_topic_reviews"] = len(report["affected_topics"])
    if impact["pending_reviews"] or catalog["errors"] or catalog["unresolved"]:
        report["status"] = "needs_review"
    pending = list(report["affected_topics"])
    pending_dependencies = list(impact["pending_reviews"])
    if reviewed_topics:
        if not checkpoint or expected_snapshot != report["snapshot"] or not review_reason.strip():
            raise ValueError("确认内容复核需要 --checkpoint、当前 --expected-snapshot 和 --review-reason")
        if any(k not in corpus["documents"] or corpus["documents"][k]["kind"] != "topic" for k in reviewed_topics):
            raise ValueError("复核目标不是当前主题路径")
        pending = [k for k in pending if k not in reviewed_topics]
        pending_dependencies = [item for item in pending_dependencies if item["target"] not in reviewed_topics]
        report["content_review_acknowledged"] = {"topics": reviewed_topics, "reason": review_reason,
                                                 "basis": "caller_declared_content_review"}
    if checkpoint:
        if corpus["errors"] or catalog["errors"]:
            raise ValueError("索引含读取错误，检查点未推进")
        state = snapshot_state(corpus, previous, pending, dependency_catalog=catalog,
                               pending_dependency_reviews=pending_dependencies)
        state["snapshot"] = report["snapshot"]
        if reviewed_topics:
            state["last_content_review"] = report["content_review_acknowledged"]
        atomic_json(target, state)
    report["checkpoint_saved"] = checkpoint
    return report


def main():
    utf8_streams()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config")
    p.add_argument("--checkpoint", action="store_true", help="保存扫描基线和未完成依赖，不确认关联或清空问题")
    p.add_argument("--suggest", action="store_true", help="显示建议阅读主题，不记录候选已处理或自动翻页")
    p.add_argument("--full", action="store_true", help="显示全部 issues；不扩大 comparisons，候选数量由 --limit 控制")
    p.add_argument("--limit", type=int, default=12, help="--suggest 本次展示的来源数量，范围 1—50；不是处理进度")
    p.add_argument("--reviewed-topic", action="append", default=[])
    p.add_argument("--expected-snapshot")
    p.add_argument("--review-reason", default="")
    p.add_argument("--identity-only", action="store_true", help="只读依赖身份/声明图，不解码学习正文、不生成候选、不写检查点")
    p.add_argument("--include-path", action="append", default=[], help="本次明确选择的来源文件/目录参与正文比较；不沿链接扩张")
    a = p.parse_args()
    try:
        config = load_config(resolve_config(a.config))
        report = run_followup(config, a.checkpoint, a.suggest, max(1, min(a.limit, 50)),
                              a.reviewed_topic, a.expected_snapshot, a.review_reason, a.identity_only, a.include_path)
        if not a.full and "issues" in report:
            report["issue_count"] = len(report["issues"])
            report["issues"] = report["issues"][:20]
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
