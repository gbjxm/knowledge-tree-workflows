"""Bounded local evidence index for review and incremental follow-up."""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from retrieve_knowledge import parse_frontmatter, normalize, query_terms, GENERIC_TERMS, ROLE_CATEGORIES

from knowledge_scope import dedupe_paths, restore_scope, scope_roots, zoned

VERSION = 4
EXCLUDED = {".obsidian", ".git", ".trash", "__pycache__"}
NON_CONTENT = {"复习区", "任务", "自测问题", "创作练习", "已融合到知识库", "主题沉淀",
               "关键问题", "已沉淀", "待沉淀", "我的理解、疑问与联想", "可实践练习", "案例索引",
               "两轮收集与审核方法", "第一次审核发现的缺口", "第二轮补查结果", "第二轮全面性与专业性审核",
               "知识提炼清单", "待复习", "阅读中的个人记录", "内化检验记录"}
RISK_TERMS = ("边界", "反例", "分歧", "争议", "不能", "不适用", "误区", "例外")
URL_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
WIKI = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def digest(data):
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def utf8_streams():
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")


def inside(path, root):
    return path == root or root in path.parents


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=path.stem + "-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def section_blocks(text):
    """Full leaf sections with parent headings and exact line locations."""
    lines = text.splitlines()
    first = 0
    if lines and lines[0].strip() == "---":
        first = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    heading, parents, start, fence, result = "(正文)", [], first, None, []
    stack = []
    def add(end):
        left, right = start, end
        while left < right and not lines[left].strip():
            left += 1
        while right > left and not lines[right - 1].strip():
            right -= 1
        content = "\n".join(lines[left:right])
        if content and not any(p in NON_CONTENT for p in parents):
            result.append({"heading": heading, "parents": list(parents),
                           "line_start": left + 1, "line_end": right, "text": content})
    for i in range(first, len(lines)):
        marker = re.match(r"^\s*(" + chr(96) + r"{3,}|~{3,})", lines[i])
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not lines[i][marker.end():].strip():
                fence = None
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[i]) if fence is None else None
        if match:
            add(i)
            level, heading = len(match.group(1)), match.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
            parents = [name for _, name in stack]
            start = i + 1
    add(len(lines))
    return result


def link_targets(value):
    values = value if isinstance(value, list) else [value]
    return [m.group(1) for v in values for m in WIKI.finditer(str(v))]


def resolve_link(raw, origin, documents, vault, file_catalog=None):
    vault = Path(vault).resolve()
    raw = raw.split("#", 1)[0].strip().replace("\\", "/")
    if not raw:
        return None, "empty"
    raw = raw if raw.lower().endswith(".md") else raw + ".md"
    path = Path(raw)
    if path.is_absolute() or re.match(r"^[a-zA-Z]:", raw):
        return None, "outside"
    catalog = list(file_catalog if file_catalog is not None else documents)
    doc_names = {key.casefold(): key for key in documents}
    file_names = {key.casefold(): key for key in catalog}
    for candidate in (vault / path, Path(origin).parent / path):
        candidate = candidate.resolve()
        if inside(candidate, vault):
            key = candidate.relative_to(vault).as_posix()
            if key.casefold() in doc_names:
                return doc_names[key.casefold()], None
            if key.casefold() in file_names or candidate.is_file():
                return None, "exists_outside_index"
    if "/" in raw:
        return None, "missing"
    matches = [key for key in catalog if Path(key).name.casefold() == path.name.casefold()]
    if len(matches) == 1:
        key = matches[0]
        return (doc_names[key.casefold()], None) if key.casefold() in doc_names else (None, "exists_outside_index")
    return None, "ambiguous" if matches else "missing"


def table_cells(line):
    protected = re.sub(r"\[\[[^\]]+\]\]", lambda m: m.group(0).replace("|", "\u0000"), line)
    return [part.replace("\u0000", "|").strip() for part in
            re.split(r"(?<!\\)\|", protected.strip().strip("|"))]


def split_table_sections(block):
    """Keep full tables readable, but rank exact rows rather than a whole dictionary.

    Context is separate, contiguous evidence. Never pretend joined header/row/note
    text occurred at one source line range.
    """
    lines = block["text"].splitlines()
    tables, i, fence = [], 0, None
    while i < len(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", lines[i])
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not lines[i][marker.end():].strip():
                fence = None
            i += 1
            continue
        if fence is None and i + 1 < len(lines) and lines[i].lstrip().startswith("|"):
            cells = table_cells(lines[i + 1])
            if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                end = i + 2
                while end < len(lines) and lines[end].lstrip().startswith("|"):
                    end += 1
                tables.append((i, end))
                i = end
                continue
        i += 1
    if not tables or not any(end - start - 2 > 8 or
                             len("\n".join(lines[start:end])) > 1800 or
                             sum(bool(URL_LINK.search(line)) for line in lines[start + 2:end]) > 1
                             for start, end in tables):
        return [block]

    parent = {**block, "routing_only": True}
    result, prose = [parent], []
    bounds = [0] + [x for table in tables for x in table] + [len(lines)]
    for left, right in zip(bounds[::2], bounds[1::2]):
        while left < right and not lines[left].strip():
            left += 1
        while right > left and not lines[right - 1].strip():
            right -= 1
        if left < right:
            part = {**block, "text": "\n".join(lines[left:right]),
                    "line_start": block["line_start"] + left,
                    "line_end": block["line_start"] + right - 1,
                    "heading": block["heading"] + " / 表格上下文",
                    "fragment_kind": "table_context", "_parent_start": block["line_start"]}
            prose.append(part)
            result.append(part)
    for start, end in tables:
        header = {**block, "text": "\n".join(lines[start:start + 2]),
                  "line_start": block["line_start"] + start,
                  "line_end": block["line_start"] + start + 1,
                  "heading": block["heading"] + " / 表头",
                  "fragment_kind": "table_header", "routing_only": True,
                  "_parent_start": block["line_start"]}
        result.append(header)
        # A final paragraph may qualify several tables in this same leaf.
        # Preserve every prose context locator; the reading budget may defer
        # its text, but must not silently drop a shared condition.
        context = [header] + prose
        context_keys = list(dict.fromkeys((p["line_start"], p["fragment_kind"]) for p in context))
        for row_number in range(start + 2, end):
            cells = table_cells(lines[row_number])
            label = " · ".join(cells[:2])
            linked = URL_LINK.search(lines[row_number])
            result.append({**block, "text": lines[row_number],
                           "line_start": block["line_start"] + row_number,
                           "line_end": block["line_start"] + row_number,
                           "heading": block["heading"] + " / " + (linked.group(1) if linked else label),
                           "fragment_kind": "table_row", "_parent_start": block["line_start"],
                           "_context_keys": context_keys})
    return result


def implementation_fingerprint():
    scripts = Path(__file__).resolve().parent
    paths = [scripts / name for name in ("knowledge_evidence.py", "retrieve_knowledge.py", "knowledge_scope.py")]
    return digest(json.dumps({p.name: digest(p.read_bytes()) for p in paths}, sort_keys=True))


def recorded_references(block):
    """Source-table support is a LOCAL record, never live verification."""
    refs = []
    for offset, line in enumerate(block["text"].splitlines()):
        links = list(URL_LINK.finditer(line))
        cells = []
        if line.lstrip().startswith("|"):
            protected = re.sub(r"\[\[[^\]]+\]\]", lambda m: m.group(0).replace("|", "\u0000"), line)
            cells = [s.replace("\u0000", "|").strip() for s in re.split(r"(?<!\\)\|", protected.strip().strip("|"))]
        for link in links:
            refs.append({"title": link.group(1), "url": link.group(2),
                         "recorded_support": cells[1] if len(cells) >= 2 else "",
                         "limits": cells[2] if len(cells) >= 3 else "",
                         "line": block["line_start"] + offset,
                         "verification": "local_record_only"})
    return refs


def load_corpus(config, write_index=False, *, scope=None):
    vault = Path(config["vault"]).resolve(strict=True)
    scope = restore_scope(config, scope) if scope is not None else None
    roots = (scope_roots(config, scope) if scope is not None else
             dedupe_paths(Path(config[name]) for name in ("knowledge_library", "source_notes")))
    if any(not inside(root, vault) for root in roots):
        raise ValueError("索引范围越出活动 Vault")
    cache_root = Path(config["raw_cache"]).resolve(strict=True)
    if inside(cache_root, vault):
        raise ValueError("派生缓存不能位于 Vault 内")
    raw_files, errors = {}, []
    for root in roots:
        for path in ([root] if root.is_file() else sorted(root.rglob("*.md"))):
            if set(path.relative_to(root).parts) & EXCLUDED:
                continue
            if not inside(path.resolve(strict=True), root):
                errors.append({"path": str(path), "reason": "symlink_outside_scope"})
                continue
            key = path.relative_to(vault).as_posix()
            if key not in raw_files:
                raw_files[key] = (path, path.read_bytes())
    files = {key: digest(data) for key, (_, data) in raw_files.items()}
    file_catalog = sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*.md")
                          if not set(path.relative_to(vault).parts) & EXCLUDED
                          and inside(path.resolve(strict=True), vault))
    fingerprint = digest(json.dumps({"files": files, "catalog": file_catalog,
                                     "parser": implementation_fingerprint(), "scope": scope}, sort_keys=True))
    cache = cache_root / "knowledge-retrieval" / (
        "evidence-index-v1.json" if scope is None else
        "evidence-scope-" + digest(json.dumps(scope, sort_keys=True))[:16] + ".json")
    # The current corpus is small. Reconstruct evidence from bytes already
    # read for hashing; never trust cached excerpts just because a header hash
    # matches. The persisted index is discovery metadata only.
    docs = {}
    for key, (path, data) in raw_files.items():
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            errors.append({"path": key, "reason": "invalid_utf8"})
            continue
        meta, body = parse_frontmatter(text)
        kind = "topic" if meta.get("类型") == "主题笔记" else "source"
        if kind == "source":
            source_types = {"材料总览", "分集笔记", "来源笔记", "来源地图"}
            if zoned(config):
                if meta.get("类型") not in source_types:
                    continue
            elif inside(path.resolve(), Path(config["knowledge_library"]).resolve()) and meta.get("类型") not in source_types - {"来源地图"}:
                continue
        h1 = re.search(r"(?m)^#\s+(.+)$", body)
        blocks = [part for block in section_blocks(text) for part in split_table_sections(block)]
        for b in blocks:
            identity = key + "|" + files[key] + "|" + str(b["line_start"])
            if b.get("fragment_kind"):
                identity += "|" + b["fragment_kind"]
            b["id"] = digest(identity)[:20]
            b["references"] = recorded_references(b)
        block_ids = {(b["line_start"], b.get("fragment_kind", "")): b["id"] for b in blocks}
        for b in blocks:
            if "_parent_start" in b:
                b["parent_id"] = block_ids[(b.pop("_parent_start"), "")]
            if "_context_keys" in b:
                b["context_ids"] = [block_ids[k] for k in b.pop("_context_keys")]
        docs[key] = {
            "path": key, "kind": kind, "title": h1.group(1).strip() if h1 else path.stem,
            "hash": files[key], "body_hash": digest(body.strip()), "meta": meta, "blocks": blocks,
            "source_type": str(meta.get("材料类型", "未标注")), "source_targets": [],
            "topic_targets": [], "broken_links": [], "scope_links": [], "urls": sorted({m.group(2) for m in URL_LINK.finditer(body)}),
        }
    catalog_documents = {key: {} for key in file_catalog}
    def link_issue(doc, origin, raw, error, field):
        target, _ = resolve_link(raw, origin, catalog_documents, vault, file_catalog)
        outside_scope = scope is not None and error == "exists_outside_index" and target not in raw_files
        doc["scope_links" if outside_scope else "broken_links"].append(
            {"target": raw, "reason": "outside_requested_scope" if outside_scope else error, "field": field})

    for key, doc in docs.items():
        source_links = link_targets(doc["meta"].get("来源材料", []))
        if doc["kind"] == "topic":
            for b in doc["blocks"]:
                if any("学习材料" in p or "来源" in p for p in b["parents"]):
                    source_links += link_targets(b["text"])
        for raw in dict.fromkeys(source_links):
            dest, error = resolve_link(raw, vault / key, docs, vault, file_catalog)
            if dest and dest != key:
                doc["source_targets"].append(dest)
            elif error:
                link_issue(doc, vault / key, raw, error, "来源材料")
        for raw in link_targets(doc["meta"].get("已沉淀主题", [])):
            dest, error = resolve_link(raw, vault / key, docs, vault, file_catalog)
            if dest and docs[dest]["kind"] == "topic":
                doc["topic_targets"].append(dest)
            else:
                link_issue(doc, vault / key, raw, error or "not_topic", "已沉淀主题")
        doc["source_targets"] = sorted(set(doc["source_targets"]))
        doc["topic_targets"] = sorted(set(doc["topic_targets"]))
    result = {"version": VERSION, "vault": str(vault), "snapshot": fingerprint,
              "files": files, "file_catalog": file_catalog, "documents": docs, "errors": errors, "scope": scope}
    if write_index and not errors:
        atomic_json(cache, {"version": VERSION, "vault": str(vault), "snapshot": fingerprint,
                            "scope": scope, "files": files, "documents": {k: {"title": d["title"], "kind": d["kind"]} for k, d in docs.items()}})
    return result


def candidates(corpus, question, keys=None, limit=6, role="", context_hint=""):
    """Lexical scores suggest reading; no score verifies a claim or relation."""
    # Split grammatical connectors before character tokenization; prevents
    # meaningless cross-word grams such as '身份和剧' outranking the subject.
    parts = [s.strip() for s in re.split(r'怎样|如何|为什么|是否|哪些|什么|表现|建立|支持|检查|[，。；！？：、\s]+|的|和|与|及', question) if s.strip()]
    terms = query_terms(" ".join(parts))
    # Small term equivalences, not memorized test questions. Keep the original
    # term as well so an article's more precise wording can still win.
    equivalent = {"外套": "服装", "衣服": "服装", "台词": "对白", "房间声": "room tone", "底噪": "room tone"}
    aliases = [v for k, v in equivalent.items() if k in question]
    terms = sorted(set(terms + query_terms(" ".join(aliases))))
    subject = [t for t in query_terms(parts[0] if parts else question)
               if t not in GENERIC_TERMS | {"状态", "时间", "内容", "方案", "关系"}]
    subject += query_terms(" ".join(v for k, v in equivalent.items() if parts and k in parts[0]))
    hint_terms = set(query_terms(context_hint))
    # Explicit professional objects constrain evidence selection. A skin-tone
    # or acting example cannot stand in for costume, nor a sound Cue for text.
    objects = (("服装", "外套", "衣服", "服化道"),
               ("字幕", "timed text", "sdh"),
               ("动机", "欲望", "目标", "意图", "动力"),
               ("对白", "台词", "dialogue", "人声"))
    required_objects = [group for group in objects if any(t in question.casefold() for t in group[:3])]
    docs, rows = corpus["documents"], []
    for key in (keys if keys is not None else docs):
        doc = docs[key]
        if str(doc["meta"].get("状态", "")) in {"撤回", "已撤回", "停用", "已失效"}:
            continue
        for b in doc["blocks"]:
            if b.get("routing_only"):
                continue
            context = normalize(doc["title"] + " " + " ".join(b["parents"]) + " " + b["text"])
            rows.append((key, b, context))
    if not rows or not terms:
        return []
    counts = Counter(t for t in terms for _, _, context in rows if t in context)
    weights = {t: math.log(1 + len(rows) / (1 + counts[t])) * (0.12 if t in GENERIC_TERMS else 1.0) for t in terms}
    total, ranked = sum(weights.values()) or 1, []
    for key, b, context in rows:
        hits = [t for t in terms if t in context]
        independent = [t for t in sorted(hits, key=len, reverse=True) if not any(t != x and t in x for x in hits)]
        meaningful = [t for t in independent if t not in GENERIC_TERMS]
        if not meaningful:
            continue
        score = sum(weights[t] for t in hits) / total / (1 + 0.08 * math.log(1 + len(b["text"]) / 500))
        if subject and not any(t in context for t in subject):
            score *= 0.35
        section_text = normalize(b["text"] + " " + b["heading"])
        title_text = normalize(docs[key]["title"])
        for group in required_objects:
            if not any(normalize(t) in section_text for t in group):
                score *= 0.20
            if any(normalize(t) in normalize(b["heading"]) for t in group):
                score *= 1.25
            if any(normalize(t) in title_text for t in group):
                score *= 1.20
        if score >= 0.025 and (len(meaningful) >= 2 or max(map(len, meaningful)) >= 4):
            if hint_terms:
                score *= 1.0 + 0.20 * sum(t in context for t in hint_terms) / len(hint_terms)
            if str(docs[key]["meta"].get("分类", "")) in ROLE_CATEGORIES.get(role, set()):
                score *= 1.12
            if any(t in b["heading"] for t in ("导览", "速览", "整体脉络", "总体结构")):
                score *= 0.65
            if "案例" not in question and (b["heading"].startswith("《") or "案例" in b["heading"]):
                score *= 0.65
            ranked.append({"key": key, "block": b, "score": score, "matched_terms": meaningful[:6]})
    ranked.sort(key=lambda r: (-r["score"], r["key"], r["block"]["line_start"]))
    return ranked[:limit]


def evidence(corpus, row, max_chars=1800):
    key, b = row["key"], row["block"]
    doc = corpus["documents"][key]
    return {
        "id": b["id"], "title": doc["title"], "path": str(Path(corpus["vault"]) / key),
        "heading": b["heading"], "line_start": b["line_start"], "line_end": b["line_end"],
        "document_hash": doc["hash"], "kind": doc["kind"], "source_type": doc["source_type"],
        "excerpt": b["text"] if len(b["text"]) <= max_chars else "",
        "read_required": len(b["text"]) > max_chars, "characters": len(b["text"]),
        "source_status": doc["meta"].get("沉淀状态", "未标注"),
        "author_or_institution": doc["meta"].get("作者或讲者", doc["meta"].get("信息来源", "未标注")),
        "note_date": doc["meta"].get("整理日期", None),
        "published_date": doc["meta"].get("发布日期", None),
        "completeness": doc["meta"].get("完整程度", "未标注"),
        "evidence_status": doc["meta"].get("证据状态", "未标注"),
        "references": b["references"], "attribution": "local_note_excerpt",
        "matched_terms": row.get("matched_terms", []),
        "fragment_kind": b.get("fragment_kind", "section"),
        "parent_id": b.get("parent_id"), "context_ids": b.get("context_ids", []),
    }


def full_evidence(corpus, item_id):
    for key, doc in corpus["documents"].items():
        if str(doc["meta"].get("状态", "")) in {"撤回", "已撤回", "停用", "已失效"}:
            continue
        for block in doc["blocks"]:
            if block["id"] == item_id:
                return evidence(corpus, {"key": key, "block": block}, max_chars=len(block["text"]))
    raise ValueError("证据不存在或已变化，请重新检索")


def evidence_for_topic(corpus, key, question, limit=2):
    doc = corpus["documents"][key]
    keys = [key] + [k for k in doc["source_targets"] if k in corpus["documents"]]
    ranked = candidates(corpus, question, keys=keys, limit=30)
    return [evidence(corpus, r) for r in ranked if r["key"] != key][:limit]


def concerns(corpus, key, question, max_chars=1000):
    doc = corpus["documents"][key]
    risks = [b for b in doc["blocks"] if any(t in " ".join(b["parents"]) for t in RISK_TERMS)]
    ranks = {r["block"]["id"]: r["score"] for r in candidates(corpus, question, keys=[key], limit=200)}
    risks.sort(key=lambda b: (-ranks.get(b["id"], 0), b["line_start"]))
    return [evidence(corpus, {"key": key, "block": b}, max_chars) for b in risks[:2]]


def make_review(corpus, query, questions, role="", stage="", material="", budget=9000,
                *, task_type="", object_name="", constraints="", expected_output=""):
    if not query.strip():
        raise ValueError("问题不能为空")
    explicit = bool(questions)
    questions = list(dict.fromkeys(q.strip() for q in questions if q.strip()))
    if len(questions) > 8:
        raise ValueError("请将本次审查限定为最多 8 个明确检查项")
    facets, records = [], {}
    for i, question in enumerate(questions or [query], 1):
        rows = candidates(corpus, question, limit=12, role=role, context_hint=query + " " + material)
        top = rows[:1]
        if len(rows) > 1 and rows[1]["score"] >= rows[0]["score"] * 0.70:
            top.append(rows[1])
        items, support, risks = [], [], []
        for row in top:
            item = evidence(corpus, row)
            items.append(item["id"])
            records[item["id"]] = item
            key = row["key"]
            for ref in (evidence_for_topic(corpus, key, question, limit=1) if not support else []):
                support.append(ref["id"])
                records[ref["id"]] = ref
            for ref in (concerns(corpus, key, question)[:1] if not risks else []):
                risks.append(ref["id"])
                records[ref["id"]] = ref
        # The strongest lexical row is not a confidence threshold. Keep the
        # existing small alternative window, even when it scores much lower.
        related = rows[len(top):len(top) + 2]
        alternatives = []
        for row in related:
            e = evidence(corpus, row)
            e["excerpt"], e["read_required"] = "", True
            alternatives.append(e["id"])
            records.setdefault(e["id"], e)
        context_ids = []
        for item_id in items + support + risks + alternatives:
            for context_id in records[item_id].get("context_ids", []):
                context_ids.append(context_id)
                if context_id not in records:
                    records[context_id] = full_evidence(corpus, context_id)
        facets.append({"id": f"Q{i}", "question": question, "evidence_ids": items,
                       "support_ids": sorted(set(support)), "boundary_ids": sorted(set(risks)),
                       "alternative_ids": alternatives, "context_ids": sorted(set(context_ids)),
                       "status": "needs_semantic_review" if items else "gap",
                       "source_gap": not support and not any(corpus["documents"][r["key"]]["kind"] == "source" for r in top)})
    # Navigation is a scope reminder, not evidence. Only attach links belonging
    # to documents selected for this response (including support/context and
    # alternatives); never spend a reading budget on every indexed document.
    selected_paths = {str(Path(e["path"]).relative_to(corpus["vault"]).as_posix())
                      for e in records.values()}
    all_scope_links = [{"path": k, **link} for k, d in corpus["documents"].items()
                       for link in d.get("scope_links", [])]
    relevant_scope_links = [link for link in all_scope_links if link["path"] in selected_paths]
    link_summary = {
        "selection": "evidence_documents_only", "total_in_scope": len(all_scope_links),
        "relevant": len(relevant_scope_links), "returned": len(relevant_scope_links),
        "omitted_unrelated": len(all_scope_links) - len(relevant_scope_links),
        "omitted_for_budget": 0, "relevant_complete": True,
    }
    review = {
        "schema": "knowledge-review-v1", "query": query, "role": role, "stage": stage,
        "context": {"task_type": task_type or None, "object": object_name or None,
                    "constraints": constraints or None, "expected_output": expected_output or None},
        "project_material": material, "snapshot": corpus["snapshot"], "scope": corpus.get("scope"),
        "out_of_scope_links": relevant_scope_links, "out_of_scope_link_summary": link_summary,
        "checklist_explicit": explicit, "coverage_status": "awaiting_application_review",
        "checklist_scope": "caller_defined_not_automatically_exhaustive",
        "facets": facets, "evidence": list(records.values()), "index_errors": corpus["errors"],
        "limits": ["命中仅表示可供审查，需逐项对照项目事实确认支持、限制、冲突或不适用。",
                   "来源类型据本地记录；外部 URL 未在本次打开，不代表已核验原文。",
                   "空缺检查项必须保留；字段完整或附有链接不等于结论正确。"],
    }
    # Factor out repeated document metadata. Alternative entries need only a
    # locator until the caller chooses to read them.
    document_fields = ("title", "path", "document_hash", "kind", "source_type", "source_status",
                       "completeness", "evidence_status", "author_or_institution", "note_date", "published_date")
    review["documents"] = {}
    for e in review["evidence"]:
        document_id = digest(e["path"])[:12]
        review["documents"].setdefault(document_id, {k: e[k] for k in document_fields})
        for k in document_fields:
            del e[k]
        e["document_id"] = document_id
    primary_ids = {e for f in facets for e in f["evidence_ids"] + f["support_ids"] + f["boundary_ids"] + f.get("context_ids", [])}
    review["budget_exceeded"] = False
    review["requires_more_reading"] = False

    def continuation(item):
        return {"mode": "evidence", "read_id": item["id"],
                "snapshot": corpus["snapshot"], "scope": corpus.get("scope")}

    def update_reading_status():
        for item in review["evidence"]:
            if item["read_required"]:
                item["continuation"] = continuation(item)
        review["requires_more_reading"] = any(e["read_required"] for e in review["evidence"]
                                              if e["id"] in primary_ids)

    def serialized_size():
        return len(json.dumps(review, ensure_ascii=False, separators=(",", ":")))

    update_reading_status()
    # Remove navigation before deferring any evidence body. Counts make this
    # omission explicit; an absent link never means that it is authorized or
    # that no cross-scope relationship exists.
    while relevant_scope_links and serialized_size() > budget:
        relevant_scope_links.pop()
        link_summary["returned"] = len(relevant_scope_links)
        link_summary["omitted_for_budget"] += 1
        link_summary["relevant_complete"] = False
    while serialized_size() > budget:
        items = [e for e in review["evidence"] if e["excerpt"]]
        if not items:
            break
        largest = max(items, key=lambda e: len(e["excerpt"]))
        deferred = {**largest, "excerpt": "", "read_required": True,
                    "continuation": continuation(largest)}
        # A short body can be smaller than a usable read request. Deferring it
        # would enlarge the response and force a pointless extra tool call.
        if (len(json.dumps(deferred, ensure_ascii=False, separators=(",", ":"))) >=
                len(json.dumps(largest, ensure_ascii=False, separators=(",", ":")))):
            break
        largest["excerpt"], largest["read_required"] = "", True
        update_reading_status()
    # Required locators, table-context IDs and same-scope continuation tokens
    # survive even when the requested budget is smaller than that metadata.
    review["budget_exceeded"] = serialized_size() > budget
    return review


def validate_application(corpus, review, application):
    """Trace validation only. Never claims semantic/aesthetic approval."""
    errors = []
    if review.get("snapshot") != corpus["snapshot"]:
        errors.append("knowledge_snapshot_changed")
    known = {b["id"]: (k, b) for k, d in corpus["documents"].items() for b in d["blocks"]}
    evidence_by_id = {e["id"]: e for e in review.get("evidence", [])}
    for item_id, e in evidence_by_id.items():
        meta = review.get("documents", {}).get(e.get("document_id"), e)
        if item_id not in known or corpus["documents"][known[item_id][0]]["hash"] != meta.get("document_hash"):
            errors.append("stale_evidence:" + item_id)
        elif (e.get("excerpt") and e["excerpt"] != known[item_id][1]["text"]):
            errors.append("altered_evidence:" + item_id)
    answers = application.get("checks", [])
    ids = [a.get("facet_id") for a in answers]
    expected = [f["id"] for f in review.get("facets", [])]
    if sorted(ids) != sorted(expected):
        errors.append("missing_or_duplicate_facets")
    for answer in answers:
        facet = next((f for f in review["facets"] if f["id"] == answer.get("facet_id")), None)
        if facet is None:
            errors.append("unknown_facet")
            continue
        status = answer.get("status")
        if status not in {"applied", "limited", "conflict", "gap", "not_applicable"}:
            errors.append("invalid_status")
        if not answer.get("project_observation") or not answer.get("judgment") or not answer.get("reason"):
            errors.append("missing_project_application")
        used = answer.get("evidence_ids", [])
        allowed = set(facet["evidence_ids"] + facet["support_ids"] + facet["boundary_ids"] + facet.get("alternative_ids", []) + facet.get("context_ids", []))
        if status in {"applied", "limited", "conflict"} and not used:
            errors.append("missing_evidence")
        if any(e not in allowed or e not in known for e in used):
            errors.append("untraceable_evidence")
        read_ids = set(application.get("read_evidence_ids", []))
        required = set(used)
        for item_id in used:
            required.update(evidence_by_id.get(item_id, {}).get("context_ids", []))
        if any(evidence_by_id.get(e, {}).get("read_required") and e not in read_ids for e in required):
            errors.append("unread_full_evidence")
    return {"traceability_pass": not errors, "errors": sorted(set(errors)),
            "semantic_quality": "not_machine_verified", "reading_proof": "caller_declared_only",
            "all_facets_answered": sorted(ids) == sorted(expected)}
