from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import date
from pathlib import Path


REQUIRED_PROPERTIES = (
    "类型",
    "分类",
    "状态",
    "材料类型",
    "信息来源",
    "完整程度",
    "整理日期",
)

TOPIC_PROPERTIES = ("主题域", "来源材料", "关联项目")
EPISODE_PROPERTIES = ("课程", "分集", "主题", "BV", "P")
V2_SOURCE_PROPERTIES = ("适用阶段", "沉淀状态", "已沉淀主题", "待沉淀主题")
V2_TOPIC_PROPERTIES = (
    "解决问题",
    "适用阶段",
    "知识状态",
    "成熟度",
    "上位主题",
    "相关主题",
    "最后复核",
)
V21_TOPIC_PROPERTIES = ("证据状态",)
PROJECT_PROPERTIES = (
    "项目",
    "项目阶段",
    "适用阶段",
    "当前问题",
    "调用知识",
    "验证状态",
    "复盘日期",
)
RAW_ARTIFACT_NAMES = {
    "metadata.json",
    "transcript.md",
    "subtitle.json",
    "audio.m4s",
}
DATAVIEW_EPISODE_FIELDS = ("P", "分集", "主题", "状态", "信息来源", "完整程度")
SOURCE_ARCHITECTURES = {"课程分层", "系列分层", "章节分层", "单篇材料", "主题直融"}
AGGREGATION_UNITS = {"课", "章", "集", "单篇", "主题"}
ARCHITECTURE_STATES = {"已确认"}
KNOWLEDGE_STATES = {"待提炼", "已提炼", "已验证", "已应用", "待修订"}
MATURITY_STATES = {"种子", "生长", "稳定"}
DEPOSIT_STATES = {"未沉淀", "部分沉淀", "已沉淀"}
UNDERSTANDING_STATES = {"待理解", "理解中", "已理解"}
QUESTION_STATES = {"待回答", "已回答", "不适用"}
EVIDENCE_STATES = {"单一来源", "多源互证", "实践验证", "存在争议"}
MASTERY_STATES = {"未检验", "能复述", "能辨析", "能迁移"}
CATEGORIES = (
    "故事与剧本",
    "导演与视听语言",
    "摄影美术与现场制作",
    "声音与后期",
    "创作实践与项目复盘",
    "行业观察与灵感素材",
)
PRESERVED_LEGACY_BODY_TYPES = {"项目资料", "工具资料", "个人思考"}
CONTROL_HEADINGS = {
    "知识树设置": ("核心设定", "知识树边界", "Codex工作方式", "确认机制"),
    "知识树状态": ("当前状态摘要", "六类覆盖", "待处理队列", "唯一下一步行动"),
    "知识收件箱": ("收件规则", "条目格式", "待处理条目"),
    "知识变更记录": ("记录规则", "变更记录"),
}


def parse_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return "", {}

    newline = "\r\n" if text.startswith("---\r\n") else "\n"
    closing = text.find(f"{newline}---", 4)
    if closing < 0:
        return "", {}

    raw = text[: closing + len(newline) + 3]
    props: dict[str, str] = {}
    for line in raw.splitlines()[1:]:
        if line == "---" or not line.strip() or line.startswith(" "):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        props[key.strip()] = value.strip()
    return raw, props


def property_values(raw: str, key: str) -> list[str]:
    lines = raw.splitlines()
    collected: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline.startswith("[") and inline.endswith("]"):
            body = inline[1:-1].strip()
            if body:
                collected.extend(item.strip().strip('"\'') for item in body.split(","))
        elif inline not in {"", "[]", "null", "~"}:
            collected.append(inline.strip('"\''))
        for following in lines[index + 1 :]:
            if following and not following.startswith((" ", "\t")):
                break
            item = re.match(r"^\s+-\s+(.+?)\s*$", following)
            if item:
                collected.append(item.group(1).strip().strip('"\''))
        break
    return [value for value in collected if value]


def has_heading(text: str, heading: str) -> bool:
    return re.search(rf"^##\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE) is not None


def has_subheading(text: str, heading: str) -> bool:
    return re.search(rf"^###\s+{re.escape(heading)}\s*$", text, flags=re.MULTILINE) is not None


def count_task_items(text: str) -> int:
    return len(re.findall(r"^-\s+\[\s\].*#(?:复习|创作练习)\b", text, flags=re.MULTILINE))


def is_v2(props: dict[str, str]) -> bool:
    value = props.get("知识库版本", "").strip().strip('"\'')
    return value in {"2", "2.0", "2.1"}


def is_v21(props: dict[str, str]) -> bool:
    value = props.get("知识库版本", "").strip().strip('"\'')
    return value == "2.1"


def require_properties(
    props: dict[str, str], required: tuple[str, ...], prefix: str, errors: list[str]
) -> None:
    for key in required:
        if key not in props:
            errors.append(f"{prefix} YAML 缺少 {key}:")


def check_raw_artifacts(path: Path, errors: list[str]) -> None:
    if not path.parent.exists():
        return
    present = sorted(name for name in RAW_ARTIFACT_NAMES if (path.parent / name).exists())
    if present:
        errors.append("最终笔记目录混入原始产物：" + "、".join(present))


def check_common(text: str, props: dict[str, str], errors: list[str]) -> None:
    h1 = re.findall(r"^#\s+.+$", text, flags=re.MULTILINE)
    h2 = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    preserve_legacy_body = props.get("类型", "").strip() in PRESERVED_LEGACY_BODY_TYPES

    if not preserve_legacy_body and len(h1) != 1:
        errors.append(f"需要且只能有一个 H1，当前为 {len(h1)}")

    duplicates = [name for name, count in Counter(h2).items() if count > 1]
    if not preserve_legacy_body and duplicates:
        errors.append("存在重复 H2：" + "、".join(duplicates))

    if not props:
        errors.append("缺少 YAML 属性")
        return

    for key in REQUIRED_PROPERTIES:
        if key not in props:
            errors.append(f"YAML 属性缺少 {key}:")

    check_optional_learning_states(props, errors)

    if re.search(r"^视频[:：]\s*https?://", text, flags=re.MULTILINE):
        errors.append("视频来源必须是 Markdown 链接，不能使用裸 URL")


def check_episode(text: str, props: dict[str, str], errors: list[str]) -> None:
    require_properties(props, EPISODE_PROPERTIES, "分集笔记", errors)

    if is_v2(props):
        check_v2_source(props, "分集笔记", errors)
    if is_v21(props):
        check_v21_source(text, props, "分集笔记", errors)

    if not props.get("P", "").strip():
        errors.append("分集笔记缺少有效 P 值")

    if not re.search(r"^视频[:：]\s*\[[^\]]+\]\(https?://[^)]+\)", text, flags=re.MULTILINE):
        errors.append("分集笔记缺少 Markdown 格式的视频来源")

    for heading in ("时间线笔记",):
        if not has_heading(text, heading):
            errors.append(f"分集笔记缺少 ## {heading}")

    if props.get("聚合单位", "").strip() == "课":
        if props.get("笔记架构", "").strip() != "课程分层":
            errors.append("课级笔记必须使用 笔记架构: 课程分层")
        if "包含P" not in props:
            errors.append("课级笔记 YAML 缺少 包含P:")
            return

        pages = parse_int_list(props.get("包含P", ""))
        if not pages:
            errors.append("课级笔记 包含P 必须至少包含一个页码")
            return
        if pages != sorted(pages):
            errors.append("课级笔记 包含P 必须按数字升序排列")
        if len(pages) != len(set(pages)):
            errors.append("课级笔记 包含P 不能包含重复页码")

        start_page = parse_first_int(props.get("P", ""))
        if start_page != pages[0]:
            errors.append("课级笔记 P 必须等于 包含P 的第一个页码")
        if not has_heading(text, "分集脉络"):
            errors.append("课级笔记缺少 ## 分集脉络")

        missing_links = [page for page in pages if not re.search(rf"[?&]p={page}(?:\D|$)", text)]
        if missing_links:
            errors.append("课级笔记缺少这些 P 的 Markdown 视频链接：" + "、".join(map(str, missing_links)))


def check_topic(text: str, raw: str, props: dict[str, str], errors: list[str]) -> None:
    require_properties(props, TOPIC_PROPERTIES, "主题笔记", errors)

    for heading in ("学习材料", "内容导览"):
        if not has_heading(text, heading):
            errors.append(f"主题笔记缺少 ## {heading}")

    if not is_v2(props):
        return

    require_properties(props, V2_TOPIC_PROPERTIES, "V2 主题笔记", errors)
    for heading in ("核心命题", "适用边界", "知识单元", "项目应用与验证"):
        if not has_heading(text, heading):
            errors.append(f"V2 主题笔记缺少 ## {heading}")

    knowledge_state = props.get("知识状态", "").strip()
    if knowledge_state and knowledge_state not in KNOWLEDGE_STATES:
        errors.append("知识状态必须是：" + "、".join(sorted(KNOWLEDGE_STATES)))

    maturity = props.get("成熟度", "").strip()
    if maturity and maturity not in MATURITY_STATES:
        errors.append("成熟度必须是：" + "、".join(sorted(MATURITY_STATES)))

    check_involved_categories(raw, props, errors)

    if is_v21(props):
        require_properties(props, V21_TOPIC_PROPERTIES, "V2.1 主题笔记", errors)
        evidence = props.get("证据状态", "").strip()
        if evidence and evidence not in EVIDENCE_STATES:
            errors.append("证据状态必须是：" + "、".join(sorted(EVIDENCE_STATES)))
        if not has_heading(text, "外部补充与分歧"):
            errors.append("V2.1 主题笔记缺少 ## 外部补充与分歧")

    check_mastery_extension(text, props, errors)


def check_mastery_extension(text: str, props: dict[str, str], errors: list[str]) -> None:
    has_mastery = "掌握状态" in props
    has_review_date = "最近检验" in props
    if not has_mastery and not has_review_date:
        return
    if has_mastery != has_review_date:
        errors.append("掌握扩展必须同时包含 掌握状态: 和 最近检验:")
        return

    mastery = props.get("掌握状态", "").strip()
    review_date = props.get("最近检验", "").strip()
    if mastery not in MASTERY_STATES:
        errors.append("掌握状态必须是：" + "、".join(sorted(MASTERY_STATES)))
    if review_date:
        try:
            date.fromisoformat(review_date)
        except ValueError:
            errors.append("最近检验必须使用有效的 YYYY-MM-DD 日期")
    if mastery != "未检验" and not review_date:
        errors.append("已检验主题必须填写 最近检验")
    if review_date or mastery != "未检验":
        if not has_subheading(text, "内化检验记录"):
            errors.append("已检验主题缺少 ### 内化检验记录")
        elif not section_has_record(text, "内化检验记录", level=3):
            errors.append("已检验主题的内化检验记录为空或只有占位内容")



def section_has_record(text: str, heading: str, level: int) -> bool:
    """Reject empty/template-only sections, without prescribing a record format.

    This is a structural guard only; whether a record reflects an actual answer
    must still be verified by the writer and reviewer.
    """
    match = re.search(
        rf"^{'#' * level}\s+{re.escape(heading)}\s*$\r?\n(.*?)(?=^#{{1,{level}}}\s+|\Z)",
        text, flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        return False
    body = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL)
    placeholders = {"", "无", "暂无", "待补充", "待填写", "待记录", "未记录", "待检验", "待回答", "待提出", "不适用", "TODO", "TBD", "...", "……", "—", "-"}
    for line in body.splitlines():
        clean = line.strip()
        if not clean or clean.startswith(("#", "```")):
            continue
        callout = re.match(r"^>\s*\[!question\][+-]?\s*(.*?)\s*$", clean)
        if callout:
            # Older source notes put the actual question in the callout title.
            # A label such as '当前关键问题' alone is still not question content.
            if heading == "关键问题" and re.search(r"[?？]", callout.group(1)):
                return True
            continue
        if re.match(r"^>\s*\[!", clean):
            continue
        clean = re.sub(r"^[>\s*\-]+", "", clean)
        clean = re.sub(r"^\[[ xX]\]\s*", "", clean)
        clean = re.sub(r"^(?:问题|核心回答|回答|诊断|下一步|日期|记录)[:：]\s*", "", clean).strip()
        if clean.strip("。.!！ ") not in placeholders and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean):
            return True
    return False


def check_optional_learning_states(props: dict[str, str], errors: list[str]) -> None:
    for key, allowed in (
        ("理解状态", UNDERSTANDING_STATES),
        ("关键问题状态", QUESTION_STATES),
    ):
        value = props.get(key, "").strip()
        # Preserve legacy empty fields; absence/empty never implies understanding.
        if value and value not in allowed:
            errors.append(key + "必须是：" + "、".join(sorted(allowed)))


def check_involved_categories(raw: str, props: dict[str, str], errors: list[str]) -> None:
    involved = property_values(raw, "涉及分类")
    if not involved:
        return
    if len(involved) != len(set(involved)):
        errors.append("涉及分类不能包含重复值")
    invalid = [category for category in involved if category not in CATEGORIES]
    if invalid:
        errors.append("涉及分类必须使用六类合法值：" + "、".join(invalid))
    category = props.get("分类", "").strip()
    if category not in involved:
        errors.append("涉及分类必须包含主题自己的分类")


def check_v2_source(props: dict[str, str], prefix: str, errors: list[str]) -> None:
    require_properties(props, V2_SOURCE_PROPERTIES, f"V2 {prefix}", errors)
    deposit_state = props.get("沉淀状态", "").strip()
    if deposit_state and deposit_state not in DEPOSIT_STATES:
        errors.append("沉淀状态必须是：" + "、".join(sorted(DEPOSIT_STATES)))


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in re.findall(r"\d+", value)]


def parse_first_int(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def check_source_architecture(props: dict[str, str], errors: list[str]) -> None:
    keys = ("笔记架构", "聚合单位", "架构状态")
    if not any(key in props for key in keys):
        return

    require_properties(props, keys, "来源架构", errors)
    architecture = props.get("笔记架构", "").strip()
    unit = props.get("聚合单位", "").strip()
    state = props.get("架构状态", "").strip()

    if architecture and architecture not in SOURCE_ARCHITECTURES:
        errors.append("笔记架构必须是：" + "、".join(sorted(SOURCE_ARCHITECTURES)))
    if unit and unit not in AGGREGATION_UNITS:
        errors.append("聚合单位必须是：" + "、".join(sorted(AGGREGATION_UNITS)))
    if state and state not in ARCHITECTURE_STATES:
        errors.append("架构状态必须是：" + "、".join(sorted(ARCHITECTURE_STATES)))


def check_v21_source(
    text: str, props: dict[str, str], prefix: str, errors: list[str]
) -> None:
    # Learning fields are optional; pending and answered states retain their source question.
    question_state = props.get("关键问题状态", "").strip()
    if question_state in {"待回答", "已回答"}:
        if not has_heading(text, "关键问题"):
            errors.append(f"V2.1 {prefix}缺少 ## 关键问题")
        elif not section_has_record(text, "关键问题", level=2):
            errors.append(f"V2.1 {prefix}{question_state}的关键问题为空或只有占位内容")


def check_overview(text: str, props: dict[str, str], errors: list[str]) -> None:
    if not has_heading(text, "材料简介"):
        errors.append("材料总览缺少 ## 材料简介")

    has_guide = any(
        has_heading(text, heading)
        for heading in ("分章节／分集导览", "分集矩阵", "分章节／分集矩阵", "按课与分集导览", "课程矩阵")
    )
    if not has_guide:
        errors.append("材料总览缺少分章节／分集导览或分集矩阵")

    if "```dataview" in text:
        missing = [field for field in DATAVIEW_EPISODE_FIELDS if field not in text]
        if missing:
            errors.append("Dataview 分集表缺少字段：" + "、".join(missing))

    if "```tasks" in text and "tags include #复习" not in text:
        errors.append("Tasks 查询应聚合 #复习 checkbox")

    if is_v2(props):
        check_v2_source(props, "材料总览", errors)
    if is_v21(props):
        check_v21_source(text, props, "材料总览", errors)


def check_map(text: str, props: dict[str, str], errors: list[str]) -> None:
    if not is_v2(props):
        errors.append("知识地图必须使用 知识库版本: 2 或 2.1")
    # Shared/role navigation needs knowledge entry points, not mandatory study queues.
    if has_heading(text, "知识骨架") and has_heading(text, "真实知识入口"):
        return
    if props.get("分类", "").strip() == "个人知识树":
        headings = ("当前学习焦点", "六类知识骨架", "最近生长的知识", "待理解材料", "待复习与练习")
    else:
        headings = ("按创作阶段调用", "真实知识入口", "待提炼材料", "待复习与练习")
        if is_v21(props):
            headings += ("知识骨架",)
    for heading in headings:
        if not has_heading(text, heading):
            errors.append(f"知识地图缺少 ## {heading}")


def check_project(text: str, props: dict[str, str], errors: list[str]) -> None:
    if not is_v2(props):
        errors.append("项目应用必须使用 知识库版本: 2 或 2.1")
    require_properties(props, PROJECT_PROPERTIES, "项目应用", errors)
    for heading in ("本轮目标", "调用的知识", "本轮决策与执行", "结果与证据", "回写知识库"):
        if not has_heading(text, heading):
            errors.append(f"项目应用缺少 ## {heading}")


def check_control(
    text: str, props: dict[str, str], note_type: str, errors: list[str]
) -> None:
    if not is_v21(props):
        errors.append(f"{note_type}必须使用 知识库版本: 2.1")
    for heading in CONTROL_HEADINGS[note_type]:
        if not has_heading(text, heading):
            errors.append(f"{note_type}缺少 ## {heading}")


def validate_text(text: str, path: Path | None = None) -> list[str]:
    """Apply the same structural checks to a candidate or a saved note."""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    errors: list[str] = []

    raw, props = parse_frontmatter(text)
    check_common(text, props, errors)
    check_source_architecture(props, errors)
    if path is not None:
        check_raw_artifacts(path, errors)

    note_type = props.get("类型", "").strip()
    if note_type == "分集笔记":
        check_episode(text, props, errors)
    elif note_type == "主题笔记":
        check_topic(text, raw, props, errors)
    elif note_type == "材料总览":
        check_overview(text, props, errors)
    elif note_type == "知识地图":
        check_map(text, props, errors)
    elif note_type == "项目应用":
        check_project(text, props, errors)
    elif note_type in CONTROL_HEADINGS:
        check_control(text, props, note_type, errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a creative-library Markdown note.")
    parser.add_argument("note", type=Path)
    args = parser.parse_args()

    path = args.note.resolve()
    text = path.read_text(encoding="utf-8-sig")
    errors = validate_text(text, path)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
