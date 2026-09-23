#!/usr/bin/env python3
"""Retrieve compact, professional film-knowledge call cards.

The v2 retriever keeps the Vault as the authority, uses maps only as routing
hints, ranks topic metadata before relevant note sections, and never lets a
workflow stage create a match by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


SKILLS_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = Path(__file__).resolve().parents[1]
OPERATE_SCRIPTS = SKILLS_ROOT / "operate-personal-knowledge-tree" / "scripts"
if str(OPERATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATE_SCRIPTS))

from knowledge_tree_config import load_config as load_shared_config
from knowledge_tree_config import resolve_config_path
from knowledge_scope import normalize_role, make_scope, scope_roots, can_expand, markdown_paths, zoned


DEFAULT_RESULTS = 1
MAX_RESULTS = 3
MIN_SCORE = 4.5
RELATIVE_SCORE_FLOOR = 0.62
INDEX_VERSION = 2
INDEX_RELATIVE = Path("knowledge-retrieval") / "index-v2.json"

RELATION_HEADINGS = ("同类知识连接", "跨域连接")
ROLE_CATEGORIES = {
    "B": {"故事与剧本"},
    "C": {"导演与视听语言", "摄影美术与现场制作", "创作实践与项目复盘"},
    "D": {"声音与后期", "创作实践与项目复盘"},
    "E": {"行业观察与灵感素材", "创作实践与项目复盘", "声音与后期"},
}

STOP_TERMS = {
    "一个", "一些", "这个", "那个", "现在", "当前", "怎么", "怎样", "如何", "为什么",
    "哪些", "什么", "问题", "检查", "可以", "需要", "应该", "进行", "设计", "电影", "影视",
    "系统", "内容", "方法", "时候", "之后", "里面", "我的", "让它", "这个人", "这段", "这些",
    "一下", "到底", "感觉", "最后", "版本", "怎么拍", "怎么办", "能不能",
}

GENERIC_TERMS = {
    "人物", "角色", "场景", "镜头", "画面", "故事", "生成", "声音", "素材", "工作流", "项目",
    "专业", "执行", "结果", "保持", "当前", "阶段", "问题", "设计", "检查", "方法",
}


@dataclass
class FormalRelation:
    target: str
    category: str
    relation: str
    reason: str
    basis: str
    section: str


@dataclass
class KnowledgeChunk:
    heading: str
    content: str
    section: str


@dataclass
class Topic:
    path: Path
    title: str
    category: str
    problem: str
    stages: list[str]
    evidence: str
    mastery: str
    core: str
    boundary: str
    default_practice: str = ""
    summary: str = ""
    aliases: list[str] = field(default_factory=list)
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    relations: list[FormalRelation] = field(default_factory=list)


@dataclass
class Route:
    map_path: Path
    category: str
    name: str
    stage: str
    enter: str
    order: str
    stop: str
    targets: list[str]

    @property
    def searchable(self) -> str:
        return " ".join((self.category, self.name, self.stage, self.enter, self.order, self.stop))


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _clean_scalar(value: str) -> str:
    return _strip_quotes(value.strip())


def _parse_inline_list(value: str) -> list[str]:
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [_clean_scalar(part) for part in inner.split(",") if _clean_scalar(part)]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, text
    data: dict[str, Any] = {}
    current_key: str | None = None
    for raw in match.group(1).splitlines():
        list_match = re.match(r"^\s+-\s+(.*)$", raw)
        if list_match and current_key:
            if not isinstance(data.get(current_key), list):
                data[current_key] = []
            data[current_key].append(_clean_scalar(list_match.group(1)))
            continue
        field_match = re.match(r"^([^:#][^:]*):\s*(.*)$", raw)
        if not field_match:
            current_key = None
            continue
        key, value = field_match.group(1).strip(), field_match.group(2).strip()
        current_key = key
        if value.startswith("[") and value.endswith("]"):
            data[key] = _parse_inline_list(value)
        elif value:
            data[key] = _clean_scalar(value)
        else:
            data[key] = []
    return data, text[match.end():]


def _section(body: str, heading: str, level: int = 2) -> str:
    hashes = "#" * level
    pattern = rf"(?ms)^{re.escape(hashes)}\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,{level}}}\s|\Z)"
    match = re.search(pattern, body)
    return match.group(1).strip() if match else ""


def _subsections(block: str, parent: str) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    pattern = r"(?ms)^###\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s|\Z)"
    for match in re.finditer(pattern, block):
        content = match.group(2).strip()
        if content:
            chunks.append(KnowledgeChunk(match.group(1).strip(), content, parent))
    if block.strip() and not chunks:
        chunks.append(KnowledgeChunk(parent, block.strip(), parent))
    return chunks


KNOWLEDGE_STOP_SECTIONS = {
    "来源差异与综合判断", "外部补充与分歧", "相关知识", "我的默认做法", "项目应用与验证",
    "对我的创作有什么启发", "我的理解、疑问与联想", "复习区", "学习材料", "内容导览",
}


def _knowledge_chunks(body: str) -> list[KnowledgeChunk]:
    """Split the method body into H2/H3 chunks without loading source/review tails."""
    headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body))
    active = False
    chunks: list[KnowledgeChunk] = []
    for index, match in enumerate(headings):
        heading = match.group(1).strip()
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        block = body[start:end].strip()
        if heading == "知识单元":
            active = True
        elif heading in KNOWLEDGE_STOP_SECTIONS:
            active = False
        elif heading == "方法与案例":
            active = True
        if not active:
            continue
        subchunks = _subsections(block, heading)
        if subchunks:
            chunks.extend(subchunks)
        elif block:
            chunks.append(KnowledgeChunk(heading, block, heading))
    return chunks


def _title_from_link(value: str) -> str:
    match = re.search(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", value)
    raw = match.group(1) if match else value
    return raw.replace("\\", "/").rstrip("/").split("/")[-1].removesuffix(".md").strip()


def _link_titles(value: str) -> list[str]:
    return [_title_from_link(item) for item in re.findall(r"\[\[[^\]]+\]\]", value)]


def parse_formal_relations(body: str) -> list[FormalRelation]:
    relations: list[FormalRelation] = []
    for heading in RELATION_HEADINGS:
        section = _section(body, heading, level=3)
        if not section:
            continue
        for line in section.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 5 or cells[0] == "相关主题" or set(cells[0]) <= {"-", ":"}:
                continue
            relations.append(
                FormalRelation(
                    target=_title_from_link(cells[0]),
                    category=cells[1],
                    relation=cells[2],
                    reason=cells[3],
                    basis=cells[4],
                    section=heading,
                )
            )
    return relations


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def load_topics(library: Path, *, files=None) -> list[Topic]:
    topics: list[Topic] = []
    for path in (files if files is not None else sorted(library.rglob("*.md"), key=lambda item: str(item).casefold())):
        text = path.read_text(encoding="utf-8-sig")
        meta, body = parse_frontmatter(text)
        if meta.get("类型") != "主题笔记":
            continue
        title_match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        title = title_match.group(1).strip() if title_match else path.stem
        chunks = _knowledge_chunks(body)
        topics.append(
            Topic(
                path=path,
                title=title,
                category=str(meta.get("分类", "未标注")),
                problem=str(meta.get("解决问题", "")),
                stages=_as_list(meta.get("适用阶段")),
                evidence=str(meta.get("证据状态", "未标注")) or "未标注",
                mastery=str(meta.get("掌握状态", "未检验")) or "未检验",
                core=_section(body, "核心命题"),
                boundary=_section(body, "适用边界"),
                default_practice=_section(body, "我的默认做法"),
                summary=_section(body, "一分钟核心摘要", level=3),
                aliases=_as_list(meta.get("aliases") or meta.get("检索别名")),
                chunks=chunks,
                relations=parse_formal_relations(body),
            )
        )
    return topics


def _field_from_bullet(block: str, label: str) -> str:
    pattern = rf"(?m)^-\s+\*\*{re.escape(label)}\*\*：\s*(.+)$"
    match = re.search(pattern, block)
    return match.group(1).strip() if match else ""


def load_routes(library: Path, *, files=None) -> list[Route]:
    routes: list[Route] = []
    for path in (files if files is not None else sorted(library.rglob("*.md"), key=lambda item: str(item).casefold())):
        text = path.read_text(encoding="utf-8-sig")
        meta, body = parse_frontmatter(text)
        if meta.get("类型") != "知识地图":
            continue
        category = str(meta.get("分类", path.parent.name))
        stage_block = _section(body, "按创作阶段调用")
        for line in stage_block.splitlines():
            match = re.match(r"^-\s+([^：:]+)[：:]\s*(.+)$", line.strip())
            if not match:
                continue
            stage, order = match.group(1).strip(), match.group(2).strip()
            targets = _link_titles(order)
            if targets:
                routes.append(Route(path, category, f"{category}｜{stage}", stage, "", order, "", targets))
        problem_block = _section(body, "按创作问题调用")
        for match in re.finditer(r"(?ms)^###\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s|\Z)", problem_block):
            name, block = match.group(1).strip(), match.group(2).strip()
            enter = _field_from_bullet(block, "什么时候进入")
            order = _field_from_bullet(block, "调用顺序")
            stop = _field_from_bullet(block, "何时停止或返回")
            targets = _link_titles(" ".join((enter, order, stop)))
            if targets:
                routes.append(Route(path, category, name, "", enter, order, stop, targets))
        cross_block = _section(body, "跨子域总入口")
        for line in cross_block.splitlines():
            if not line.strip().startswith("-"):
                continue
            targets = _link_titles(line)
            if targets:
                routes.append(Route(path, category, "跨子域入口", "", "", line.lstrip("- "), "", targets))
    return routes


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _load_taxonomy() -> list[dict[str, Any]]:
    path = SKILL_ROOT / "references" / "retrieval-taxonomy.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return list(payload.get("rules", []))


def _expand_query(query: str, taxonomy: list[dict[str, Any]]) -> tuple[str, list[str]]:
    normalized_query = normalize(query)
    additions: list[str] = []
    matched_rules: list[str] = []
    for rule in taxonomy:
        triggers = [normalize(str(item)) for item in rule.get("any", [])]
        required = [normalize(str(item)) for item in rule.get("all", [])]
        any_ok = not triggers or any(item and item in normalized_query for item in triggers)
        all_ok = all(item and item in normalized_query for item in required)
        if any_ok and all_ok:
            additions.extend(str(item) for item in rule.get("add", []))
            matched_rules.append(str(rule.get("id", "alias")))
    return " ".join([query, *additions]), matched_rules


def query_terms(query: str) -> list[str]:
    normalized_query = unicodedata.normalize("NFKC", query).casefold()
    terms: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9+&/-]{1,}", normalized_query):
        normalized_run = normalize(run)
        if not normalized_run:
            continue
        if re.fullmatch(r"[a-z0-9]+", normalized_run):
            terms.add(normalized_run)
            continue
        if len(normalized_run) <= 4:
            terms.add(normalized_run)
        for size in (4, 3, 2):
            if len(normalized_run) < size:
                continue
            for index in range(len(normalized_run) - size + 1):
                term = normalized_run[index:index + size]
                if term not in STOP_TERMS:
                    terms.add(term)
    terms.difference_update(normalize(item) for item in STOP_TERMS)
    return sorted((term for term in terms if len(term) >= 2), key=lambda item: (-len(item), item))


def _documents(topics: list[Topic], routes: list[Route]) -> list[str]:
    docs: list[str] = []
    for topic in topics:
        docs.append(normalize(" ".join((topic.title, topic.problem, topic.core, topic.summary, topic.default_practice))))
        docs.extend(normalize(f"{chunk.heading} {chunk.content}") for chunk in topic.chunks)
    docs.extend(normalize(route.searchable) for route in routes)
    return docs


def _idf(terms: Iterable[str], docs: list[str]) -> dict[str, float]:
    total = max(1, len(docs))
    values: dict[str, float] = {}
    for term in terms:
        df = sum(1 for doc in docs if term in doc)
        base = math.log((total + 1) / (df + 1)) + 0.35
        length_factor = 1.0 + min(max(len(term) - 2, 0), 2) * 0.35
        if term in GENERIC_TERMS:
            base *= 0.25
        values[term] = base * length_factor
    return values


def _coverage(terms: list[str], text: str, weights: dict[str, float]) -> tuple[float, list[str]]:
    target = normalize(text)
    if not target or not terms:
        return 0.0, []
    denominator = sum(weights.get(term, 1.0) for term in terms) or 1.0
    hits = [term for term in terms if term in target]
    numerator = sum(weights.get(term, 1.0) for term in hits)
    return numerator / denominator, hits


def _stage_match(topic: Topic, stage: str) -> bool:
    stage_norm = normalize(stage)
    return bool(stage_norm) and any(
        stage_norm in normalize(candidate) or normalize(candidate) in stage_norm for candidate in topic.stages
    )


def _compact(value: str, limit: int) -> str:
    value = re.sub(r"\n{3,}", "\n\n", value.strip())
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    for marker in ("。", "；", "\n"):
        cut = clipped.rfind(marker)
        if cut >= int(limit * 0.65):
            return clipped[:cut + 1].rstrip()
    return clipped.rstrip() + "…"


def _first_action(topic: Topic, chunks: list[KnowledgeChunk]) -> str:
    source = topic.default_practice or (chunks[0].content if chunks else topic.summary or topic.core)
    source = "\n".join(
        line.lstrip("> ") for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("> [!")
    )
    compact = _compact(source, 240)
    first = re.split(r"(?<=[。；])|\n", compact)[0].lstrip("- 0123456789.、")
    return first.strip() or f"先按《{topic.title}》完成当前问题的最小检查。"


def _topic_score(
    topic: Topic,
    terms: list[str],
    weights: dict[str, float],
    stage: str,
    role: str,
    route_scores: dict[str, tuple[float, Route]],
) -> tuple[float, float, list[str], list[tuple[float, KnowledgeChunk]]]:
    title_cov, title_hits = _coverage(terms, " ".join([topic.title, *topic.aliases]), weights)
    problem_cov, problem_hits = _coverage(terms, topic.problem, weights)
    summary_cov, summary_hits = _coverage(terms, " ".join((topic.core, topic.summary, topic.default_practice)), weights)
    chunk_rows: list[tuple[float, KnowledgeChunk]] = []
    for chunk in topic.chunks:
        heading_cov, _ = _coverage(terms, chunk.heading, weights)
        content_cov, _ = _coverage(terms, chunk.content, weights)
        chunk_rows.append((heading_cov * 0.65 + content_cov * 0.35, chunk))
    chunk_rows.sort(key=lambda item: (-item[0], item[1].heading))
    chunk_cov = chunk_rows[0][0] if chunk_rows else 0.0
    route_cov = route_scores.get(topic.title, (0.0, None))[0]
    semantic = title_cov * 38.0 + problem_cov * 34.0 + summary_cov * 16.0 + chunk_cov * 28.0 + route_cov * 44.0
    score = semantic
    if semantic >= 10.0 and _stage_match(topic, stage):
        score += 7.0
    if semantic >= 10.0 and role.upper() in ROLE_CATEGORIES and topic.category in ROLE_CATEGORIES[role.upper()]:
        score += 4.0
    hits = sorted(set(title_hits + problem_hits + summary_hits), key=lambda item: (-len(item), item))
    return score, semantic, hits[:8], chunk_rows


def retrieve(
    topics: list[Topic],
    query: str,
    stage: str = "",
    limit: int = DEFAULT_RESULTS,
    *,
    routes: list[Route] | None = None,
    role: str = "",
    task_type: str = "",
    object_name: str = "",
    constraints: str = "",
    expected_output: str = "",
    debug: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_RESULTS))
    routes = routes or []
    structured_query = " ".join(item for item in (query, task_type, object_name, constraints, expected_output) if item)
    expanded_query, matched_alias_rules = _expand_query(structured_query, _load_taxonomy())
    terms = query_terms(expanded_query)
    docs = _documents(topics, routes)
    weights = _idf(terms, docs)

    route_scores: dict[str, tuple[float, Route]] = {}
    for route in routes:
        route_cov, _ = _coverage(terms, route.searchable, weights)
        if stage and route.stage and normalize(stage) == normalize(route.stage):
            route_cov += 0.08
        for target in route.targets:
            current = route_scores.get(target)
            if current is None or route_cov > current[0]:
                route_scores[target] = (route_cov, route)

    all_ranked: list[tuple[float, float, Topic, list[str], list[tuple[float, KnowledgeChunk]]]] = []
    for topic in topics:
        score, semantic, hits, chunk_rows = _topic_score(topic, terms, weights, stage, role, route_scores)
        all_ranked.append((score, semantic, topic, hits, chunk_rows))
    all_ranked.sort(key=lambda item: (-item[0], item[2].title, str(item[2].path).casefold()))
    ranked = [row for row in all_ranked if row[1] >= MIN_SCORE]
    if ranked:
        top_score = ranked[0][0]
        ranked = [row for row in ranked if row[0] >= max(MIN_SCORE, top_score * RELATIVE_SCORE_FLOOR)]
    selected = ranked[:limit]
    alternatives = [row for row in ranked[limit:3]]

    candidates: list[dict[str, Any]] = []
    for score, semantic, topic, hits, chunk_rows in selected:
        selected_chunks = [chunk for chunk_score, chunk in chunk_rows if chunk_score > 0.03][:2]
        if not selected_chunks and topic.chunks:
            selected_chunks = topic.chunks[:1]
        route_row = route_scores.get(topic.title)
        route = route_row[1] if route_row and route_row[0] >= 0.08 else None
        card: dict[str, Any] = {
            "title": topic.title,
            "path": str(topic.path),
            "category": topic.category,
            "solves": topic.problem,
            "stages": topic.stages,
            "why_matched": hits[:5],
            "core": _compact(topic.summary or topic.core, 480),
            "method_chunks": [
                {"heading": chunk.heading, "section": chunk.section, "content": _compact(chunk.content, 650)}
                for chunk in selected_chunks
            ],
            "default_practice": _compact(topic.default_practice, 450),
            "minimal_action": _first_action(topic, selected_chunks),
            "boundary": _compact(topic.boundary, 600),
            "evidence_status": topic.evidence,
            "mastery_status": topic.mastery,
            "route": (
                {
                    "name": route.name,
                    "stage": route.stage or None,
                    "enter": _compact(route.enter, 320),
                    "order": _compact(route.order, 460),
                    "stop": _compact(route.stop, 320),
                    "source": str(route.map_path),
                    "kind": "navigation_hint",
                }
                if route else None
            ),
            "formal_relations": [
                {
                    "target": relation.target,
                    "category": relation.category,
                    "relation": relation.relation,
                    "reason": relation.reason,
                    "basis": relation.basis,
                    "section": relation.section,
                }
                for relation in topic.relations[:3]
            ],
        }
        if debug:
            card.update({"score": round(score, 3), "semantic_score": round(semantic, 3)})
        candidates.append(card)

    gap = not candidates
    top_margin = round(ranked[0][0] - ranked[1][0], 3) if len(ranked) >= 2 else None
    ambiguous = bool(len(ranked) >= 2 and ranked[1][0] >= ranked[0][0] * 0.88)
    result: dict[str, Any] = {
        "query": query,
        "context": {
            "role": role or None,
            "stage": stage or None,
            "task_type": task_type or None,
            "object": object_name or None,
            "constraints": constraints or None,
            "expected_output": expected_output or None,
        },
        "limit": limit,
        "topic_count": len(topics),
        "route_count": len(routes),
        "candidates": candidates,
        "alternatives": [{"title": row[2].title, "category": row[2].category} for row in alternatives],
        "ambiguous": ambiguous,
        "gap": gap,
        "gap_reason": "当前主题、知识单元与导航路由均不足以可靠回答该问题" if gap else None,
    }
    if debug:
        result["debug"] = {
            "terms": terms,
            "matched_alias_rules": matched_alias_rules,
            "top_margin": top_margin,
            "ranked": [
                {"title": row[2].title, "score": round(row[0], 3), "semantic": round(row[1], 3)}
                for row in ranked[:8]
            ],
            "below_threshold": [
                {"title": row[2].title, "score": round(row[0], 3), "semantic": round(row[1], 3)}
                for row in all_ranked[:5]
            ],
        }
    return result


def _index_signature(library: Path) -> str:
    rows: list[str] = []
    for path in sorted(library.rglob("*.md"), key=lambda item: str(item).casefold()):
        stat = path.stat()
        rows.append(f"{path.relative_to(library).as_posix()}|{stat.st_size}|{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _topic_to_json(topic: Topic) -> dict[str, Any]:
    payload = asdict(topic)
    payload["path"] = str(topic.path)
    return payload


def _topic_from_json(payload: dict[str, Any]) -> Topic:
    return Topic(
        path=Path(payload["path"]),
        title=payload["title"],
        category=payload["category"],
        problem=payload["problem"],
        stages=list(payload.get("stages", [])),
        evidence=payload.get("evidence", "未标注"),
        mastery=payload.get("mastery", "未检验"),
        core=payload.get("core", ""),
        boundary=payload.get("boundary", ""),
        default_practice=payload.get("default_practice", ""),
        summary=payload.get("summary", ""),
        aliases=list(payload.get("aliases", [])),
        chunks=[KnowledgeChunk(**item) for item in payload.get("chunks", [])],
        relations=[FormalRelation(**item) for item in payload.get("relations", [])],
    )


def _route_to_json(route: Route) -> dict[str, Any]:
    payload = asdict(route)
    payload["map_path"] = str(route.map_path)
    return payload


def _route_from_json(payload: dict[str, Any]) -> Route:
    return Route(map_path=Path(payload["map_path"]), **{k: v for k, v in payload.items() if k != "map_path"})


def load_or_build_index(library: Path, raw_cache: Path, *, no_cache: bool = False) -> tuple[list[Topic], list[Route], str]:
    signature = _index_signature(library)
    cache_path = raw_cache / INDEX_RELATIVE
    if not no_cache and cache_path.is_file():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8-sig"))
            if payload.get("version") == INDEX_VERSION and payload.get("signature") == signature:
                return (
                    [_topic_from_json(item) for item in payload.get("topics", [])],
                    [_route_from_json(item) for item in payload.get("routes", [])],
                    "hit",
                )
        except (OSError, ValueError, TypeError, KeyError):
            pass
    topics = load_topics(library)
    routes = load_routes(library)
    if not no_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": INDEX_VERSION,
            "signature": signature,
            "topics": [_topic_to_json(item) for item in topics],
            "routes": [_route_to_json(item) for item in routes],
        }
        temp = cache_path.with_suffix(cache_path.suffix + f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temp, cache_path)
    return topics, routes, "rebuilt" if not no_cache else "disabled"


def resolve_config(config_arg: str | None = None) -> Path:
    return resolve_config_path(config_arg)


def load_config(config_path: Path) -> dict[str, Any]:
    return load_shared_config(config_path).as_dict()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="具体创作问题")
    parser.add_argument("--role", default="", choices=("", "A", "B", "C", "C1", "C2", "D", "E"))
    parser.add_argument("--stage", default="", help="工作流阶段")
    parser.add_argument("--task-type", default="", help="任务类型")
    parser.add_argument("--object", dest="object_name", default="", help="精确对象，如 Sxx/Vxx/CUTxx")
    parser.add_argument("--constraints", default="", help="成本、工具、审美或权限限制")
    parser.add_argument("--expected-output", default="", help="期望交付物或判断")
    parser.add_argument("--limit", type=int, default=DEFAULT_RESULTS, help="默认 1，最大 3")
    parser.add_argument("--config", help="统一知识树配置；工作流桥必须显式传入")
    parser.add_argument("--no-cache", action="store_true", help="不读取或写入 Vault 外的派生索引")
    parser.add_argument("--debug", action="store_true", help="显示评分与命中信号")
    parser.add_argument("--include-path", action="append", default=[], help="本次明确点名的 Markdown 文件或目录，Vault相对或绝对路径")
    return parser


def retrieve_scoped(config, query, *, role="", include_paths=(), stage="", limit=DEFAULT_RESULTS,
                    no_cache=False, **context):
    from knowledge_evidence import load_corpus, candidates as evidence_candidates, evidence
    role = normalize_role(role)
    library, cache = Path(config["knowledge_library"]), Path(config["raw_cache"])
    scope = make_scope(config, role, include_paths)
    while True:
        if not zoned(config) and not include_paths:
            topics, routes, cache_status = load_or_build_index(library, cache, no_cache=no_cache)
            result = retrieve(topics, query, stage, limit, routes=routes, role=role, **context)
            result["index_cache"] = {"status": cache_status, "path": str(cache / INDEX_RELATIVE)}
            return result
        corpus = load_corpus(config, write_index=not no_cache, scope=scope)
        files = [Path(corpus["vault"]) / key for key in corpus["files"]]
        topics, routes = load_topics(library, files=files), load_routes(library, files=files)
        result = retrieve(topics, query, stage, limit, routes=routes, role=role, **context)
        source_keys = [k for k, d in corpus["documents"].items() if d["kind"] == "source"]
        rows = evidence_candidates(corpus, query, keys=source_keys, limit=max(1, min(limit, MAX_RESULTS)), role=role)
        result["source_candidates"] = [evidence(corpus, row) for row in rows]
        result["source_count"] = len(source_keys)
        result["gap"] = not result["candidates"] and not rows
        result["gap_reason"] = "本次读取范围没有有效主题或来源候选" if result["gap"] else None
        result.update(scope=scope, snapshot=corpus["snapshot"], index_errors=corpus["errors"],
                      out_of_scope_links=[{"path": k, **link} for k, d in corpus["documents"].items() for link in d.get("scope_links", [])])
        result["index_cache"] = {"status": "disabled" if no_cache else "scoped_discovery_only"}
        if result["gap"] and can_expand(scope):
            scope = make_scope(config, role, include_paths, expanded=True)
            continue
        return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        config_path = resolve_config(args.config)
        config = load_config(config_path)
        library = Path(config["knowledge_library"]).expanduser().resolve()
        raw_cache = Path(config["raw_cache"]).expanduser().resolve()
        if not library.is_dir():
            raise FileNotFoundError(f"知识库不存在: {library}")
        result = retrieve_scoped(config, args.query, role=args.role, include_paths=args.include_path,
                                 stage=args.stage, limit=args.limit, no_cache=args.no_cache,
                                 task_type=args.task_type, object_name=args.object_name,
                                 constraints=args.constraints, expected_output=args.expected_output, debug=args.debug)
        result["config"] = str(config_path)
        result["knowledge_library"] = str(library)
        print(json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.debug else None,
            separators=None if args.debug else (",", ":"),
        ))
        return 0
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
