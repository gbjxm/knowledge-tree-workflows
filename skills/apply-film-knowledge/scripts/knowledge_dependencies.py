"""Read identity and declared provenance without opening learning note bodies.

This catalog is maintenance metadata, never a retrieval corpus or permission.
Only frontmatter is decoded; complete note bytes are streamed for fingerprints.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from retrieve_knowledge import parse_frontmatter

EXCLUDED = {".obsidian", ".git", ".trash", "__pycache__"}
RETIRED = {"撤回", "停用", "已失效", "已撤回"}
PROVENANCE_TYPES = {"主题笔记", "材料总览", "分集笔记", "来源笔记", "项目应用"}
FIELDS = {"类型", "状态", "来源材料", "派生自", "调用知识"}
HEADER_LIMIT = 65536
WIKI = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _inside(path, root):
    return path == root or root in path.parents


def _digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            h.update(chunk)
    return h.hexdigest()


def _identity(path):
    """Hash bytes and decode a bounded header; never decode the note body."""
    before = path.stat()
    with path.open("rb") as handle:
        first = handle.readline(HEADER_LIMIT + 1).removeprefix(b"\xef\xbb\xbf")
        rows = []
        if first.strip() == b"---":
            size = len(first)
            while True:
                row = handle.readline(HEADER_LIMIT + 1)
                size += len(row)
                if not row or size > HEADER_LIMIT:
                    raise ValueError("frontmatter_unclosed_or_too_large")
                if row.strip() == b"---":
                    break
                rows.append(row)
    meta = {}
    if rows:
        header = b"---\n" + b"".join(rows) + b"---\n"
        parsed, _ = parse_frontmatter(header.decode("utf-8"))
        meta = {key: value for key, value in parsed.items() if key in FIELDS}
    fingerprint = _digest_file(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("changed_during_identity_scan")
    return fingerprint, meta


def _links(value):
    values = value if isinstance(value, list) else [value]
    return [m.group(1) for item in values for m in WIKI.finditer(str(item))]


def _resolve(raw, origin, nodes, vault):
    raw = raw.split("#", 1)[0].strip().replace("\\", "/")
    if not raw:
        return None, "empty"
    if Path(raw).is_absolute() or re.match(r"^[a-zA-Z]:", raw):
        return None, "outside_configured_roots"
    raw = raw if raw.lower().endswith(".md") else raw + ".md"
    names = {key.casefold(): key for key, node in nodes.items() if node["kind"] != "source_identity"}
    for candidate in (vault / raw, origin.parent / raw):
        candidate = candidate.resolve()
        if not _inside(candidate, vault):
            continue
        key = candidate.relative_to(vault).as_posix()
        if key.casefold() in names:
            return names[key.casefold()], None
        if candidate.is_file():
            return None, "outside_configured_roots"
    if "/" in raw:
        return None, "missing"
    matches = [key for key in names.values() if Path(key).name.casefold() == Path(raw).name.casefold()]
    return (matches[0], None) if len(matches) == 1 else (None, "ambiguous" if matches else "missing")


def load_dependency_catalog(config):
    """No calls to load_corpus, candidates, section_blocks, or learning text."""
    vault = Path(config["vault"]).resolve(strict=True)
    roots = []
    for name in ("knowledge_library", "source_notes", "prompt_box"):
        if not config.get(name):
            continue
        root = Path(config[name]).resolve(strict=True)
        if not _inside(root, vault):
            raise ValueError("依赖身份范围越出活动 Vault")
        if not any(_inside(root, existing) for existing in roots):
            roots = [existing for existing in roots if not _inside(existing, root)] + [root]
    nodes, edges, errors, unresolved = {}, [], [], []
    for root in roots:
        for path in ([root] if root.is_file() else sorted(root.rglob("*.md"))):
            if set(path.relative_to(root).parts) & EXCLUDED:
                continue
            key = path.relative_to(vault).as_posix()
            if key in nodes:
                continue
            if not _inside(path.resolve(), root):
                errors.append({"path": key, "reason": "symlink_outside_configured_roots"})
                continue
            try:
                fingerprint, meta = _identity(path)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append({"path": key, "reason": str(exc)})
                continue
            note_type = str(meta.get("类型", "未标注"))
            kind = "topic" if note_type == "主题笔记" else "application" if note_type == "项目应用" else "source"
            nodes[key] = {"kind": kind, "note_type": note_type, "hash": fingerprint,
                          "status": str(meta.get("状态", "")), "metadata": meta}
    for key, node in list(nodes.items()):
        if node["note_type"] not in PROVENANCE_TYPES:
            continue  # Maps and ordinary navigation never declare provenance.
        fields = ("调用知识",) if node["kind"] == "application" else ("来源材料", "派生自")
        for field in fields:
            for raw in _links(node["metadata"].get(field, [])):
                target, reason = _resolve(raw, vault / key, nodes, vault)
                if target:
                    edges.append({"dependent": key, "dependency": target, "field": field,
                                  "certainty": "declared_frontmatter"})
                else:
                    unresolved.append({"path": key, "field": field, "target": raw, "reason": reason})
    evidence_root = config.get("source_evidence")
    if evidence_root:
        evidence_root = Path(evidence_root).resolve(strict=True)
        if _inside(evidence_root, vault):
            raise ValueError("来源身份记录不能位于 Vault 内")
        workspace = Path(config.get("workspace", vault.parent)).resolve()
        cache = Path(config["raw_cache"]).resolve(strict=True)
        for path in sorted(evidence_root.rglob("record.json")):
            if not _inside(path.resolve(), evidence_root):
                errors.append({"path": str(path), "reason": "evidence_symlink_outside_root"})
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8-sig"))
                if record.get("schema") != "source-evidence-v1" or not isinstance(record.get("source_id"), str):
                    raise ValueError("invalid_source_identity")
                source, note = record["source"], record["note"]
                if not isinstance(source, dict) or not isinstance(note, dict):
                    raise ValueError("invalid_source_or_note_identity")
                if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value)
                       for value in (source.get("text_sha256"), note.get("sha256"))):
                    raise ValueError("invalid_source_or_note_fingerprint")
                key = "evidence:" + record["source_id"]
                if key in nodes:
                    raise ValueError("duplicate_source_identity")
                versions = [("primary", source)]
                review = record.get("review", {})
                for i, item in enumerate(review.get("incremental_reviews", []) if isinstance(review, dict) else []):
                    if isinstance(item, dict) and isinstance(item.get("source"), dict):
                        versions.append(("incremental:" + str(i), item["source"]))
                inputs = []
                for role, version in versions:
                    hint = version.get("local_text_hint")
                    actual, availability = None, "not_located"
                    if hint:
                        raw_path = Path(hint)
                        raw_path = (raw_path if raw_path.is_absolute() else workspace / raw_path).resolve()
                        if not _inside(raw_path, cache):
                            availability = "outside_configured_raw_cache"
                            errors.append({"path": str(path), "reason": availability})
                        elif not raw_path.is_file():
                            availability = "missing"
                        else:
                            actual = _digest_file(raw_path)
                            availability = "matched" if actual == version.get("text_sha256") else "hash_mismatch"
                    inputs.append({"role": role, "expected_hash": version.get("text_sha256"),
                                   "actual_hash": actual, "availability": availability})
                nodes[key] = {"kind": "source_identity", "hash": _digest_file(path), "status": "",
                              "source_id": record["source_id"], "source_identity": {
                                  name: source.get(name) for name in ("kind", "bvid", "page", "cid", "locator")},
                              "inputs": inputs, "reviewed_note_hash": note.get("sha256"),
                              "note_path": note.get("path"), "metadata": {}}
                raw_note = note.get("path")
                target, reason = _resolve(str(raw_note or ""), vault / "identity.md", nodes, vault)
                if target:
                    nodes[key]["note_binding_status"] = "matched" if nodes[target]["hash"] == note.get("sha256") else "hash_mismatch"
                    edges.append({"dependent": target, "dependency": key, "field": "source_evidence.note",
                                  "certainty": "declared_source_identity"})
                else:
                    nodes[key]["note_binding_status"] = "note_missing_or_unresolved"
                    unresolved.append({"path": key, "field": "source_evidence.note", "target": raw_note, "reason": reason})
            except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
                errors.append({"path": str(path), "reason": str(exc)})
    # A declaration is identity metadata, not proof of correctness or read access.
    unique = {json.dumps(edge, ensure_ascii=False, sort_keys=True): edge for edge in edges}
    edges = [unique[key] for key in sorted(unique)]
    serial = {"nodes": nodes, "edges": edges}
    snapshot = hashlib.sha256(json.dumps(serial, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {"version": 1, "vault": str(vault), "snapshot": snapshot, **serial,
            "errors": errors, "unresolved": unresolved, "body_read_permission": False,
            "identity_scan": "hash_bytes_and_bounded_frontmatter_only"}


def calculate_dependency_impact(catalog, previous=None):
    """Propagate declared changes, preserving unresolved reviews across scans."""
    previous = previous or {}
    if previous and (previous.get("version") not in (1, 2) or not isinstance(previous.get("files"), dict)
                     or not isinstance(previous.get("dependencies"), dict)):
        raise ValueError("补查快照结构无效")
    if previous and previous.get("vault") != catalog["vault"]:
        raise ValueError("补查快照属于另一个 Vault")
    old_catalog = previous.get("dependency_catalog") or {}
    if old_catalog and (old_catalog.get("version") != 1 or old_catalog.get("vault") != catalog["vault"]
                        or not isinstance(old_catalog.get("nodes"), dict) or not isinstance(old_catalog.get("edges"), list)):
        raise ValueError("依赖身份检查点无效或属于另一 Vault")
    nodes = catalog["nodes"]
    old_nodes = old_catalog.get("nodes", {})
    if not old_catalog and previous.get("files"):
        old_nodes = {key: {"hash": value} for key, value in previous["files"].items()}
    # An explicitly saved empty catalog is still a baseline. An initial
    # inventory without a checkpoint does not classify every note as added.
    baseline = bool(old_catalog) or bool(old_nodes)
    added = sorted(set(nodes) - set(old_nodes)) if baseline else []
    removed = sorted(set(old_nodes) - set(nodes))
    modified = sorted(key for key in set(nodes) & set(old_nodes)
                      if nodes[key]["hash"] != old_nodes[key].get("hash")
                      or nodes[key].get("inputs") != old_nodes[key].get("inputs", nodes[key].get("inputs")))
    renamed, ambiguous = [], []
    for gone in removed:
        matches = [new for new in added if nodes[new]["hash"] == old_nodes[gone].get("hash")]
        if len(matches) == 1:
            competing = [old for old in removed if old_nodes[old].get("hash") == nodes[matches[0]]["hash"]]
            if len(competing) == 1:
                renamed.append({"from": gone, "to": matches[0], "status": "identity_candidate_not_rebound"})
            else:
                ambiguous.append({"from": gone, "candidates": matches, "reason": "multiple_old_identities"})
        elif matches:
            ambiguous.append({"from": gone, "candidates": matches, "reason": "multiple_new_identities"})
    revoked = sorted(key for key, node in nodes.items() if node.get("status") in RETIRED)
    unavailable = sorted(key for key, node in nodes.items() if node["kind"] == "source_identity"
                         and (any(item["availability"] != "matched" for item in node.get("inputs", []))
                              or node.get("note_binding_status") != "matched"))
    seeds = set(added + modified + removed + revoked + unavailable)
    # Historical edges are used only to trace lost dependencies, not persisted
    # as current declarations after a relation has been removed.
    reverse = defaultdict(set)
    for edge in [*old_catalog.get("edges", []), *catalog["edges"]]:
        reverse[edge["dependency"]].add(edge["dependent"])
    if not old_catalog:
        for dependent, dependencies in previous.get("dependencies", {}).items():
            for dependency in dependencies:
                reverse[dependency].add(dependent)
    current_reverse = defaultdict(set)
    for edge in catalog["edges"]:
        current_reverse[edge["dependency"]].add(edge["dependent"])
    edge_key = lambda edge: (edge["dependent"], edge["dependency"], edge.get("field"))
    old_edges = {edge_key(edge) for edge in old_catalog.get("edges", [])}
    legacy_pairs = {(dependent, dependency)
                    for dependent, dependencies in previous.get("dependencies", {}).items()
                    for dependency in dependencies} if not old_catalog else set()
    # Resolving a previously missing declaration can create an edge without
    # changing the dependent's bytes. A new declaration to an existing source
    # likewise needs review of that dependent, not every sibling using source.
    new_edges = [edge for edge in catalog["edges"] if baseline and edge_key(edge) not in old_edges
                 and (edge["dependent"], edge["dependency"]) not in legacy_pairs]
    impacts = {}
    def propagate(seed, initial_chain, graph, *, review_start=False, trigger_reason=None):
        start = initial_chain[-1]
        if review_start and start in nodes:
            impacts.setdefault((seed, start), {"trigger": seed, "target": start, "chain": initial_chain,
                "status": "pending_content_review", "kind": nodes[start]["kind"],
                "trigger_reason": trigger_reason})
        queue, visited = deque([(start, initial_chain)]), set(initial_chain)
        while queue:
            current, chain = queue.popleft()
            for target in sorted(graph[current]):
                if target in visited:
                    continue
                visited.add(target)
                next_chain = [*chain, target]
                if target in nodes:
                    impacts.setdefault((seed, target), {"trigger": seed, "target": target, "chain": next_chain,
                        "status": "pending_content_review", "kind": nodes[target]["kind"],
                        "trigger_reason": trigger_reason})
                queue.append((target, next_chain))
    for seed in sorted(seeds):
        propagate(seed, [seed], reverse, trigger_reason="dependency_added" if seed in added else "dependency_changed_or_unavailable")
    for edge in new_edges:
        propagate(edge["dependency"], [edge["dependency"], edge["dependent"]], current_reverse,
                  review_start=True, trigger_reason="declared_dependency_added")
    for item in previous.get("pending_dependency_reviews", []):
        if not isinstance(item, dict) or not isinstance(item.get("chain"), list):
            raise ValueError("依赖待复核记录无效")
        impacts.setdefault((item.get("trigger"), item.get("target")), item)
    records = sorted(impacts.values(), key=lambda item: (str(item.get("target")), str(item.get("trigger"))))
    topics = sorted({item["target"] for item in records if item.get("kind") == "topic"})
    applications = sorted({item["target"] for item in records if item.get("kind") == "application"})
    # Cycles are diagnostic only. Iterative reachability remains finite.
    cycle_nodes = set()
    for start in nodes:
        pending, seen = list(reverse[start]), set()
        while pending:
            target = pending.pop()
            if target == start:
                cycle_nodes.add(start)
                break
            if target not in seen:
                seen.add(target)
                pending.extend(reverse[target])
    return {"schema": "knowledge-dependency-impact-v1", "snapshot": catalog["snapshot"],
            "baseline_missing": not baseline, "changes": {"added": added, "modified": modified,
                "removed": removed, "renamed": renamed, "ambiguous_renames": ambiguous,
                "dependency_edges_added": new_edges},
            "revoked": revoked, "unavailable_source_inputs": unavailable,
            "affected_topics": topics, "affected_applications": applications,
            "affected_methods": [{"path": key, "method_scope": "whole_topic_pending", "source_binding": "unresolved"}
                                 for key in topics],
            "pending_reviews": records, "cycle_nodes": sorted(cycle_nodes),
            "identity_errors": catalog["errors"], "unresolved_declarations": catalog["unresolved"],
            "body_read_permission": False, "knowledge_modified": False, "applications_modified": False}
