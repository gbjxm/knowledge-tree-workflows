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
    "专业", "创作", "执行", "结果", "保持", "当前", "阶段", "问题", "设计", "检查", "方法",
    "意图", "变化", "状态", "时间", "内容", "方案", "关系", "推进", "相关", "同一",
    "一个", "两个", "一次", "通过", "形成", "使用", "判断", "原因", "以及", "还是",
    "突然", "改变", "可见", "成立", "同时", "转成", "获得", "相邻", "一致", "比较", "先查",
    "制作", "条件", "验证",
    "处理", "顺序", "过程", "增加", "前提", "清楚", "避免", "带来", "表达", "没有", "观众",
    "边界", "体验", "感觉",
}

# Sentence connectors are not professional concepts. Splitting them before
# character grams prevents a longer question from introducing many imaginary
# terms across clause boundaries. Matching still uses the original local text.
QUERY_CONNECTORS = re.compile(
    r"怎样|如何|为什么|是否|哪些|什么|应该|能不能|怎么办|到底|现在|当前|还是|或者|"
    r"以及|然后|之后|以后|之前|表现|建立|支持|检查|判断|[，。；！？：、\s]+"
)

# Professional objects, not destinations or fixed answers. A chapter can own
# an object even when its document belongs to another discipline. General
# workflow words such as '处理' and '版本' cannot establish that ownership.
PROFESSIONAL_OBJECTS = {
    "sound": (("声音", "声源", "音频", "音效", "底噪", "听审", "混音", "room tone", "foley"),
              ("声音", "声源", "音频", "音效", "底噪", "听觉", "听审", "审听", "混音", "声学", "对白", "配音", "room tone", "foley")),
    "music": (("音乐", "配乐", "旋律", "和声", "和弦", "音色"),
              ("音乐", "配乐", "旋律", "和声", "和弦", "音色", "composer")),
    "camera_space": (("轴线", "视线", "画面方向", "屏幕方向", "运动方向", "拍摄方向", "空间连续", "镜头衔接", "机位", "焦距", "蒙太奇"),
                     ("轴线", "视线", "方向", "摄影", "机位", "镜头", "覆盖", "调度", "布光", "焦距", "蒙太奇")),
    "color": (("肤色", "调色", "色彩", "色温", "白平衡", "曝光", "影调"),
              ("肤色", "调色", "色彩", "色温", "白平衡", "曝光", "影调", "光源", "look")),
    "assets": (("资产", "服装", "服化道", "道具", "材质", "美术", "生产设计"),
               ("资产", "服装", "服化道", "道具", "材质", "美术", "生产设计", "空间设计")),
    "text": (("字幕", "字体", "屏幕文字", "timed text", "sdh"),
             ("字幕", "字体", "文字", "文本", "timed text", "sdh")),
    "story": (("故事", "剧本", "人物弧光", "因果", "冲突", "阻力", "欲望"),
              ("故事", "剧本", "人物", "因果", "冲突", "阻力", "欲望", "大纲", "分场")),
    "performance": (("表演", "演员", "对白", "台词", "聆听", "语速"),
                    ("表演", "演员", "对白", "台词", "聆听", "人物", "配音")),
    "vfx": (("vfx", "视觉特效", "合成", "alpha", "抠像"),
            ("vfx", "视觉特效", "合成", "alpha", "抠像", "plate")),
    "release": (("播放量", "平台曝光", "完播", "留存", "平台传播", "传播原因", "传播效果", "传播策略",
                 "受众", "投放", "推荐量", "点击率", "触达"),
                ("播放量", "平台曝光", "完播", "留存", "平台传播", "传播原因", "传播效果", "传播策略",
                 "受众", "投放", "推荐量", "点击率", "触达", "发布条件")),
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
    document_hash: str = ""


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


def _heading_mask(body: str) -> str:
    """Keep offsets while masking fenced code from structural-heading regexes."""
    rows, fence = [], None
    for line in body.splitlines(keepends=True):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        inside = fence is not None
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
        rows.append(re.sub(r"[^\r\n]", "x", line) if inside or marker else line)
    return "".join(rows)


def _section(body: str, heading: str, level: int = 2) -> str:
    hashes = "#" * level
    pattern = rf"(?ms)^{re.escape(hashes)}\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,{level}}}\s|\Z)"
    match = re.search(pattern, _heading_mask(body))
    return body[match.start(1):match.end(1)].strip() if match else ""


def _subsections(block: str, parent: str) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    pattern = r"(?ms)^###\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s|\Z)"
    for match in re.finditer(pattern, _heading_mask(block)):
        content = block[match.start(2):match.end(2)].strip()
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
    headings = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", _heading_mask(body)))
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
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
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
                document_hash=hashlib.sha256(raw).hexdigest(),
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


def lexical_text(value: str) -> str:
    """Normalize without inventing terms across punctuation or field breaks."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[0-9a-z\u4e00-\u9fff]+", value))


def _raw_object_foci(value: str) -> tuple[str, ...]:
    text = lexical_text(value)
    # Distribution reach and image exposure share a word, not an object.
    # Only explicit metric phrases are masked; bare exposure stays ambiguous.
    color_text = lexical_text(re.sub(r"(?:平台|传播|推荐|投放|流量|受众)[^，。；！？]{0,4}?曝光(?:量|率|次数|数据)?", "", value))
    return tuple(name for name, (triggers, _) in PROFESSIONAL_OBJECTS.items()
                 if any(lexical_text(term) in (color_text if name == "color" else text) for term in triggers))


def query_roles(value: str) -> dict[str, Any]:
    """Bounded grammatical routing: target vs a proposed borrowed reference.

    This does not decide whether a comparison is valid. It keeps a questioned
    reference domain from supplying the target's evidence merely by being named.
    """
    labeled_target = re.search(r"(?:^|[。；\n])\s*(?:实际问题|当前问题|目标问题|本次目标|判断目标)\s*[:：]\s*(.+)$", value, re.S)
    intent_target = re.search(r"(?:我)?(?:实际要|实际想|实际需要|只想|只要|仅想|仅要|需要)\s*"
        r"((?:检查|判断|分析|解释|解决|确认|了解|比较|讨论).+)$", value, re.S)
    if intent_target and not labeled_target:
        prefix = value[:intent_target.start()]
        # A normal trailing request does not erase its preceding concrete
        # problem. Reduce an intent span only inside declared reference context.
        declared_reference = re.search(r"(?:参考知识|参考方法|参考材料|参考领域)\s*[:：]|"
            r"(?:借|拿|用)[^，。；：\n]{1,80}?(?:打个比方|作个比方|做个比方|类比|举个例子)", prefix)
        if not declared_reference:
            intent_target = None
    target_anchor = labeled_target or intent_target
    explicit_target = bool(target_anchor)
    reference_context = ""
    if target_anchor:
        prefix = value[:target_anchor.start()]
        labels = re.findall(r"(?:参考知识|参考方法|参考材料|参考领域)\s*[:：]\s*([^。；\n]+)", prefix)
        analogies = re.findall(r"(?:借|拿|用)([^，。；：\n]{1,80}?)(?:打个比方|作个比方|做个比方|类比|举个例子)", prefix)
        reference_context = "；".join([*labels, *analogies])
        value = target_anchor.group(1)
    def borrowed(target, reference):
        return {"mode": "borrowed_reference", "target_text": target, "comparison_text": reference,
                "target_foci": list(_raw_object_foci(target)), "comparison_foci": list(_raw_object_foci(reference)),
                "explicit_target": True, "comparison_status": "not_target_evidence"}
    # These are grammatical qualification relations, not a list of the
    # operations that different professions happen to perform. Everything
    # after the relation remains the target, including an unfamiliar verb.
    repeated_question = r"(?P<question_word>[\u4e00-\u9fff]{1,3})不(?P=question_word)"
    doubt = r"(?:是否|能否|可否|可不可以|有没有|有无|有必要|" + repeated_question + r")"
    linked = re.compile(r"(?P<reference>[^，。；！？：]{1,120}?)(?P<modal>" + doubt +
        r")[^，。；！？：]{0,24}?(?P<link>用来|用于|作为|当作)(?P<target>[^。；！？]*)")
    qualified = re.compile(r"(?P<reference>[^，。；！？：]{1,120}?)(?P<modal>"
        r"(?:能否|可否|可不可以)(?:(?:能够|可以|能)\s*)?|"
        r"(?P<ability_word>能够|可以|能|可)不(?P=ability_word)(?:(?:能够|可以|能)\s*)?|"
        r"(?:是否|(?P<compound_question>[\u4e00-\u9fff]{1,3})不(?P=compound_question))"
        r"\s*(?:能够|可以|能))(?P<target>[^。；！？]*)")
    for expression in (linked, qualified):
        for match in expression.finditer(value):
            reference = "；".join(part for part in (reference_context, match.group("reference").strip()) if part)
            target = match.group("target").strip()
            # A dangling connector gives no target object. Preserve it as an
            # unresolved applicability request, not a same-domain method hit.
            complete = bool(target and re.sub(r"^(?:用来|用于|作为|当作)\s*", "", target).strip())
            result = borrowed(target if complete else "", reference)
            result["target_context"] = value[:match.start()].strip()
            result["applicability_status"] = "target_supplied" if complete else "target_unresolved"
            if not complete:
                result["mode"] = "applicability_unresolved"
            return result
    # Subject-first capability questions are comparisons of applicability,
    # not an instruction to make the subject's domain the target evidence.
    capability = re.compile(r"(?P<reference>[^，。；！？：]{1,80}?)(?:能否|是否|可否|能不能)"
        r"(?:用来|用于|能够|可以)?(?P<purpose>解释|代表|解决|判断|诊断|证明|说明)(?P<target>[^。；！？]+)")
    for match in capability.finditer(value):
        reference = "；".join(part for part in (reference_context, match.group("reference").strip()) if part)
        target = (value[:match.start()] + " " + match.group("purpose") + match.group("target") + value[match.end():]).strip()
        if target and reference:
            return borrowed(target, reference)
    pattern = re.compile(r"(?:是否|能否|可否|能不能|可不可以|可以)?(?:能)?"
        r"(?:借用|借|套用|参考|借鉴|照搬|照着|按|用|拿)\s*(?P<reference>[^，。；！？]{1,80}?)"
        r"(?P<purpose>(?:来)?(?:判断|解释|分析|推断|诊断|修正|解决|评价|支持|说明|证明|作为|当作|用于|做))")
    for match in pattern.finditer(value):
        reference = "；".join(part for part in (reference_context, match.group("reference").strip()) if part)
        target = (value[:match.start()] + " " + match.group("purpose") + value[match.end():]).strip()
        target_foci, reference_foci = _raw_object_foci(target), _raw_object_foci(reference)
        if reference and target and (explicit_target or not target_foci or
                reference_foci and set(reference_foci) - set(target_foci)):
            return borrowed(target, reference)
    foci = _raw_object_foci(value)
    reference_foci = _raw_object_foci(reference_context)
    if reference_context and (not foci or reference_foci and set(reference_foci) - set(foci)):
        return borrowed(value, reference_context)
    return {"mode": "multiple_targets" if len(foci) > 1 else "direct", "target_text": value,
            "comparison_text": reference_context, "target_foci": list(foci), "comparison_foci": list(reference_foci),
            "explicit_target": explicit_target, "comparison_status": None}


def object_foci(value: str) -> tuple[str, ...]:
    return tuple(query_roles(value)["target_foci"])


def general_review_body(question: str, owner: str, body: str) -> bool:
    """Allow explicitly requested neutral reasoning, not incidental film facts."""
    requested = any(term in question for term in ("复盘", "解释假设", "反证", "事前依据", "一次结果", "单次结果", "区分事实"))
    if not requested or not any(term in owner for term in ("复盘", "决策", "反证", "过程质量", "观察/解释", "观察、解释", "观察与解释")):
        return False
    if any(focus != "release" for focus in _raw_object_foci(owner)):
        return False
    groups = (("事实", "数据", "结果", "观察"), ("解释", "原因", "影响", "归因", "反证"),
              ("复盘", "决策", "方法", "事前", "证据", "样本", "依据"))
    return sum(any(term in question for term in group) and any(term in body for term in group)
               for group in groups) >= 2


def owns_objects(foci: Iterable[str], title: str, heading: str = "", body: str = "") -> bool:
    if not foci:
        return True
    # The shared category label before ｜ is not a chapter's object identity.
    owner = lexical_text(title.split("｜")[-1] + " " + heading)
    text = lexical_text(body)
    for focus in foci:
        _, terms = PROFESSIONAL_OBJECTS[focus]
        if any(lexical_text(term) in owner for term in terms):
            return True
        # Permit real cross-discipline methods, not an incidental mention of
        # one object (e.g. '声音转移注意' inside a VFX tool decision).
        if sum(lexical_text(term) in text for term in terms) >= 2:
            return True
    return False


def short_lookup(query: str) -> bool:
    if re.fullmatch(r"[a-z0-9][a-z0-9+&/-]*", query.strip(), re.IGNORECASE):
        return True
    value = normalize(" ".join(QUERY_CONNECTORS.split(query)))
    for filler in sorted(STOP_TERMS | GENERIC_TERMS, key=len, reverse=True):
        value = value.replace(normalize(filler), "")
    return 2 <= len(value) <= 4


def independent_terms(terms: Iterable[str]) -> list[str]:
    values = set(terms)
    return sorted((term for term in values if not any(term != other and term in other for other in values)),
                  key=lambda term: (-len(term), term))


def specific_terms(terms: Iterable[str]) -> list[str]:
    # Remove contained grams before filtering general phrases. Otherwise
    # discarding '画面上' would expose '面上' as a spurious specific concept.
    return [term for term in independent_terms(terms) if term not in GENERIC_TERMS and
            re.sub(r"(?:[上下中内外后前]|[一二三四五六七八九十两\d]+(?:个|条|项|次|镜|场)?)$", "", term)
            not in GENERIC_TERMS]


def direct_match(terms: Iterable[str], available: Iterable[str] | None = None, *, lookup=False) -> bool:
    """Require a specific phrase or multiple concepts, not a role/generic word."""
    specific = specific_terms(terms)
    if len(specific) >= 2:
        return True
    # A precise short lookup (including an English object name) may have one
    # concept. A multi-concept problem must not be answered by one incidental
    # phrase occurring in a distant example.
    return ((lookup and bool(specific)) or
            (any(len(term) >= 4 for term in specific) and
             (available is None or len(specific_terms(available)) < 2)))


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
    normalized_query = " ".join(QUERY_CONNECTORS.split(unicodedata.normalize("NFKC", query).casefold()))
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
                if size >= 3 and len(normalized_run) > size and (
                    term[0] in "的和与及是了又让把在或并由才这那时" or
                    term[-1] in "的和与及是了又让把在或并由才这那时"
                ):
                    continue
                if term not in STOP_TERMS:
                    terms.add(term)
    terms.difference_update(normalize(item) for item in STOP_TERMS)
    return sorted((term for term in terms if len(term) >= 2), key=lambda item: (-len(item), item))


def _documents(topics: list[Topic], routes: list[Route]) -> list[str]:
    docs: list[str] = []
    for topic in topics:
        docs.append(lexical_text(" ".join((topic.title, *topic.aliases, topic.problem, topic.core, topic.summary, topic.default_practice))))
        docs.extend(lexical_text(f"{chunk.heading} {chunk.content}") for chunk in topic.chunks)
    docs.extend(lexical_text(route.searchable) for route in routes)
    return docs


def _idf(terms: Iterable[str], docs: list[str]) -> dict[str, float]:
    total = max(1, len(docs))
    values: dict[str, float] = {}
    for term in terms:
        df = sum(1 for doc in docs if term in doc)
        if not df:
            # Unseen scene details are reported in debug, not rewarded with
            # maximum rarity and allowed to drown out known method concepts.
            values[term] = 0.0
            continue
        base = math.log((total + 1) / (df + 1)) + 0.35
        length_factor = 1.0 + min(max(len(term) - 2, 0), 2) * 0.35
        if term in GENERIC_TERMS:
            base *= 0.25
        values[term] = base * length_factor
    return values


def _coverage(terms: list[str], text: str, weights: dict[str, float]) -> tuple[float, list[str]]:
    target = lexical_text(text)
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
    if not chunks:
        return ""
    source = chunks[0].content
    source = "\n".join(
        line.lstrip("> ") for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("> [!")
    )
    compact = _compact(source, 240)
    first = re.split(r"(?<=[。；])|\n", compact)[0].lstrip("- 0123456789.、")
    return first.strip() or f"先按《{topic.title}》完成当前问题的最小检查。"


def _selection_corpus(topic: Topic):
    """Adapt the legacy pure API to the review's same body selector.

    This temporary structure is for ranking only. It is not a read locator,
    snapshot, or a substitute for a scoped corpus bound to current file bytes.
    """
    from knowledge_evidence import section_blocks, split_table_sections
    text = "# " + topic.title + "\n" + "\n".join(
        "## " + chunk.section + "\n### " + chunk.heading + "\n" + chunk.content
        for chunk in topic.chunks)
    blocks = [part for block in section_blocks(text) for part in split_table_sections(block)]
    for index, block in enumerate(blocks):
        block["id"] = f"selection-{index}"
    block_ids = {(block["line_start"], block.get("fragment_kind", "")): block["id"] for block in blocks}
    for block in blocks:
        if "_parent_start" in block:
            block["parent_id"] = block_ids[(block.pop("_parent_start"), "")]
        if "_context_keys" in block:
            block["context_ids"] = [block_ids[key] for key in block.pop("_context_keys")]
    key = str(topic.path)
    return {"documents": {key: {"title": topic.title, "kind": "topic", "blocks": blocks,
                                "meta": {"分类": topic.category, "解决问题": topic.problem}}}}, key


def _method_rows(topic: Topic, query: str, role: str, corpus=None):
    """Select body reading candidates with review eligibility, not title overlap."""
    from knowledge_evidence import candidates as body_candidates
    if corpus is None:
        selected_corpus, key = _selection_corpus(topic)
    else:
        selected_corpus = corpus
        key = topic.path.relative_to(Path(corpus["vault"])).as_posix()
    rows = body_candidates(selected_corpus, query, keys=[key], limit=200, role=role)
    # Topic scoring still locates documents. Its summary or a matching source
    # list is not the method body; retain the note's existing method-body range.
    def in_method_body(row):
        block = row["block"]
        owners = [block["heading"], *block.get("parents", [])]
        return any(chunk.heading in owners or block["heading"].startswith(chunk.heading + " / ")
                   for chunk in topic.chunks)
    return [row for row in rows if row.get("primary_eligible", True) and in_method_body(row)][:2]


def _reading_info(original: str, shown: str, heading: str) -> dict[str, Any]:
    normalize_space = lambda value: re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n").strip())
    truncated = normalize_space(original) != normalize_space(shown)
    return {"heading": heading, "characters": len(original), "returned_characters": len(shown),
            "truncated": truncated, "read_required": truncated, "continuation": None}


def _bind_readings(result, corpus):
    """Bind displayed fragments to exact, versioned sections without changing ranking."""
    from read_knowledge_section import extract_heading
    for card in result["candidates"]:
        path = Path(card["path"])
        key = path.relative_to(Path(corpus["vault"])).as_posix()
        doc = corpus["documents"].get(key)
        if not doc or doc["kind"] != "topic":
            raise ValueError("快查文章身份已变化，请重新检索")
        if card.get("document_hash") and card["document_hash"] != doc["hash"]:
            raise ValueError("快查缓存与当前文章版本不一致，请重新检索")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != doc["hash"]:
            raise ValueError("快查期间文章发生变化，请重新检索")
        text = raw.decode("utf-8-sig")
        card.update(kind="topic", document_hash=doc["hash"])
        entries = [(item, card[name]) for name, item in card["reading"].items()]
        for item, shown in entries:
            try:
                _, full = extract_heading(text, item["heading"])
            except ValueError as exc:
                # Ambiguous or stale headings must not quietly select another section.
                item.update(read_required=True, continuation=None, reading_error=str(exc),
                            reading_hint="用 knowledge_review.py 获取该段准确证据 ID 后续读")
                continue
            item.update(_reading_info(full, shown, item["heading"]))
            if item["read_required"]:
                item["continuation"] = {"mode": "section", "path": str(path), "heading": item["heading"],
                    "offset": 0, "max_chars": 5000, "document_hash": doc["hash"],
                    "snapshot": corpus["snapshot"], "scope": corpus.get("scope")}
        by_id = {block["id"]: block for block in doc["blocks"]}
        context_ids = []
        for item in card["method_chunks"]:
            block = by_id.get(item.get("id"))
            if block is None:
                # Legacy cards select the same body candidates, but their
                # temporary ranking IDs never become evidence identities.
                try:
                    _, full = extract_heading(text, item["heading"])
                except ValueError as exc:
                    item.update(read_required=True, continuation=None, reading_error=str(exc),
                                reading_hint="用 knowledge_review.py 获取该段准确证据 ID 后续读")
                    entries.append((item, item["content"]))
                    continue
                item.update(_reading_info(full, item["content"], item["heading"]))
                if item["read_required"]:
                    item["continuation"] = {"mode": "section", "path": str(path), "heading": item["heading"],
                        "offset": 0, "max_chars": 5000, "document_hash": doc["hash"],
                        "snapshot": corpus["snapshot"], "scope": corpus.get("scope")}
            else:
                item.update(_reading_info(block["text"], item["content"], item["heading"]))
                try:
                    _, section = extract_heading(text, item["heading"])
                    use_section = section.strip().replace("\r\n", "\n") == block["text"].strip()
                except ValueError:
                    use_section = False
                if item["read_required"]:
                    item["continuation"] = ({"mode": "section", "path": str(path), "heading": item["heading"],
                        "offset": 0, "max_chars": 5000, "document_hash": doc["hash"],
                        "snapshot": corpus["snapshot"], "scope": corpus.get("scope")} if use_section else
                        {"mode": "evidence", "read_id": block["id"], "offset": 0, "max_chars": 5000,
                         "snapshot": corpus["snapshot"], "scope": corpus.get("scope")})
                context_ids.extend(block.get("context_ids", []))
            entries.append((item, item["content"]))
        from knowledge_evidence import full_evidence
        card["context_evidence"] = []
        for item_id in dict.fromkeys(context_ids):
            context = full_evidence(corpus, item_id)
            full = context["excerpt"]
            context.update(excerpt=_compact(full, 900), returned_characters=len(_compact(full, 900)))
            context["read_required"] = context["excerpt"] != full
            context["continuation"] = ({"mode": "evidence", "read_id": item_id, "offset": 0,
                "max_chars": 5000, "snapshot": corpus["snapshot"], "scope": corpus.get("scope")}
                if context["read_required"] else None)
            card["context_evidence"].append(context)
            entries.append((context, context["excerpt"]))
            context["truncated"] = context["read_required"]
        card["truncated"] = any(item["truncated"] for item, _ in entries)
        card["read_required"] = any(item["read_required"] for item, _ in entries)
    for item in result.get("source_candidates", []):
        item["truncated"] = item["read_required"]
        item["returned_characters"] = len(item["excerpt"])
        item["continuation"] = ({"mode": "evidence", "read_id": item["id"],
                                 "snapshot": corpus["snapshot"], "scope": corpus.get("scope")}
                                if item["read_required"] else None)
    result["snapshot"] = corpus["snapshot"]
    if corpus.get("scope") is not None:
        result["scope"] = corpus["scope"]


def _candidate_navigation(result, corpus, budget=1200):
    selected_paths = {card["path"] for card in result["candidates"] + result.get("source_candidates", [])}
    all_links = [{"path": key, **link} for key, doc in corpus["documents"].items() for link in doc.get("scope_links", [])]
    relevant = [link for link in all_links if str(Path(corpus["vault"]) / link["path"]) in selected_paths]
    returned = list(relevant)
    while returned and len(json.dumps(returned, ensure_ascii=False, separators=(",", ":"))) > budget:
        returned.pop()
    result["out_of_scope_links"] = returned
    result["out_of_scope_link_summary"] = {
        "selection": "evidence_documents_only", "total_in_scope": len(all_links), "relevant": len(relevant),
        "returned": len(returned), "omitted_unrelated": len(all_links)-len(relevant),
        "omitted_for_budget": len(relevant)-len(returned), "relevant_complete": len(returned)==len(relevant)}


def _topic_score(
    topic: Topic,
    terms: list[str],
    weights: dict[str, float],
    stage: str,
    role: str,
    route_scores: dict[str, tuple[float, Route]],
    *, foci: tuple[str, ...] = (), lookup=False,
    question: str = "",
) -> tuple[float, float, list[str], list[tuple[float, KnowledgeChunk]]]:
    title_cov, title_hits = _coverage(terms, " ".join([topic.title, *topic.aliases]), weights)
    problem_cov, problem_hits = _coverage(terms, topic.problem, weights)
    summary_cov, summary_hits = _coverage(terms, " ".join((topic.core, topic.summary, topic.default_practice)), weights)
    direct_hits = title_hits + problem_hits + summary_hits
    chunk_rows: list[tuple[float, KnowledgeChunk]] = []
    for chunk in topic.chunks:
        if not owns_objects(foci, topic.title, chunk.heading, chunk.content) and not (
                "release" in foci and general_review_body(question, topic.title + " " + chunk.heading, chunk.content)):
            continue
        heading_cov, _ = _coverage(terms, chunk.heading, weights)
        content_cov, content_hits = _coverage(terms, chunk.content, weights)
        direct_hits.extend(content_hits)
        chunk_rows.append((heading_cov * 0.65 + content_cov * 0.35, chunk))
    chunk_rows.sort(key=lambda item: (-item[0], item[1].heading))
    chunk_cov = chunk_rows[0][0] if chunk_rows else 0.0
    route_cov = route_scores.get(topic.title, (0.0, None))[0]
    semantic = title_cov * 38.0 + problem_cov * 34.0 + summary_cov * 16.0 + chunk_cov * 28.0 + route_cov * 44.0
    owner = topic.title + " " + topic.problem
    same_object = owns_objects(foci, topic.title) or bool(chunk_rows)
    if not same_object or not direct_match(direct_hits, [term for term in terms if weights.get(term)], lookup=lookup):
        # A map or the requested workflow stage may route a reading, but must
        # not manufacture a topic match with no specific local support.
        semantic = 0.0
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
    corpus=None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), MAX_RESULTS))
    routes = routes or []
    roles = query_roles(query)
    target_query = roles["target_text"]
    expanded_query, matched_alias_rules = _expand_query(target_query, _load_taxonomy())
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
        score, semantic, hits, chunk_rows = _topic_score(topic, terms, weights, stage, role, route_scores,
                                                       foci=tuple(roles["target_foci"]), lookup=short_lookup(target_query),
                                                       question=target_query)
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
        method_rows = _method_rows(topic, query, role, corpus)
        selected_chunks = [KnowledgeChunk(row["block"]["heading"], row["block"]["text"],
                                          (row["block"].get("parents") or [""])[-1]) for row in method_rows]
        route_row = route_scores.get(topic.title)
        route = route_row[1] if route_row and route_row[0] >= 0.08 else None
        card: dict[str, Any] = {
            "title": topic.title,
            "path": str(topic.path),
            "document_hash": topic.document_hash,
            "category": topic.category,
            "solves": topic.problem,
            "stages": topic.stages,
            "why_matched": hits[:5],
            "core": _compact(topic.summary or topic.core, 480),
            "method_chunks": [
                {"heading": chunk.heading, "section": chunk.section, "content": _compact(chunk.content, 650),
                 "section_role_hint": row["section_role_hint"], "selection_status": "needs_semantic_review",
                 **({"id": row["block"]["id"], "line_start": row["block"]["line_start"],
                     "line_end": row["block"]["line_end"], "fragment_kind": row["block"].get("fragment_kind", "section"),
                     "context_ids": row["block"].get("context_ids", []),
                     "parent_id": row["block"].get("parent_id")} if corpus is not None else {})}
                for chunk, row in zip(selected_chunks, method_rows)
            ],
            "method_gap": not selected_chunks,
            "method_gap_reason": "主题可定位，但本题尚未获得主要正文阅读候选；需按专业问题补查" if not selected_chunks else None,
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
        card["reading"] = {
            "core": _reading_info(topic.summary or topic.core, card["core"],
                                  "一分钟核心摘要" if topic.summary else "核心命题"),
            "boundary": _reading_info(topic.boundary, card["boundary"], "适用边界"),
            "default_practice": _reading_info(topic.default_practice, card["default_practice"], "我的默认做法"),
        }
        card["reading"] = {name: item for name, item in card["reading"].items() if item["characters"]}
        for item, chunk in zip(card["method_chunks"], selected_chunks):
            item.update(_reading_info(chunk.content, item["content"], chunk.heading))
        reading = list(card["reading"].values()) + card["method_chunks"]
        card["truncated"] = any(item["truncated"] for item in reading)
        card["read_required"] = any(item["read_required"] for item in reading)
        if debug:
            card.update({"score": round(score, 3), "semantic_score": round(semantic, 3)})
        candidates.append(card)

    gap = not any(card["method_chunks"] for card in candidates)
    top_margin = round(ranked[0][0] - ranked[1][0], 3) if len(ranked) >= 2 else None
    ambiguous = bool(len(ranked) >= 2 and ranked[1][0] >= ranked[0][0] * 0.88)
    result: dict[str, Any] = {
        "query": query,
        "query_roles": roles,
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
        "method_gap": not any(card["method_chunks"] for card in candidates),
        "method_gap_reason": ("本题尚未获得主要正文阅读候选；候选主题、相关原理或导航不能证明方法已充分"
                              if not any(card["method_chunks"] for card in candidates) else None),
        "gap_reason": "本题尚无可靠直接正文依据；保留主题仅供进一步阅读" if gap else None,
    }
    if debug:
        result["debug"] = {
            "terms": terms,
            "unmatched_query_terms": [term for term in terms if not weights.get(term)],
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
        rows.append(f"{path.relative_to(library).as_posix()}|{hashlib.sha256(path.read_bytes()).hexdigest()}")
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
        document_hash=payload.get("document_hash", ""),
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
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
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
            corpus = load_corpus(config, write_index=False)
            result = retrieve(topics, query, stage, limit, routes=routes, role=role, corpus=corpus, **context)
            result["index_cache"] = {"status": cache_status, "path": str(cache / INDEX_RELATIVE)}
            # Old configurations keep the same candidate set, with bound reading locators added.
            _bind_readings(result, corpus)
            return result
        corpus = load_corpus(config, write_index=not no_cache, scope=scope)
        files = [Path(corpus["vault"]) / key for key in corpus["files"]]
        topics, routes = load_topics(library, files=files), load_routes(library, files=files)
        result = retrieve(topics, query, stage, limit, routes=routes, role=role, corpus=corpus, **context)
        source_keys = [k for k, d in corpus["documents"].items() if d["kind"] == "source"]
        rows = evidence_candidates(corpus, query, keys=source_keys, limit=max(1, min(limit, MAX_RESULTS)), role=role)
        result["source_candidates"] = [evidence(corpus, row) for row in rows]
        result["method_gap"] = result["method_gap"] and not any(row.get("primary_eligible", True) for row in rows)
        if not result["method_gap"]:
            result["method_gap_reason"] = None
        result["source_count"] = len(source_keys)
        result["gap"] = result["method_gap"]
        result["gap_reason"] = "本次读取范围尚无可靠直接正文依据；保留主题仅供进一步阅读" if result["gap"] else None
        result.update(scope=scope, snapshot=corpus["snapshot"], index_errors=corpus["errors"])
        result["index_cache"] = {"status": "disabled" if no_cache else "scoped_discovery_only"}
        if result["gap"] and can_expand(scope):
            scope = make_scope(config, role, include_paths, expanded=True)
            continue
        _bind_readings(result, corpus)
        _candidate_navigation(result, corpus)
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
