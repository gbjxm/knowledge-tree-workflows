"""Black-box reference-domain checks with disposable v2 files, never holdout content."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from knowledge_review import read_request, review_scoped
from retrieve_knowledge import load_config, retrieve_scoped


UNKNOWN_TARGET = "参考知识：调色曝光。实际问题：发片后的差异怎样记录事实和解释假设？"
SOUND_TARGET = "参考知识：调色曝光。实际问题：声音转场突然变安静，怎样检查声源归属和听觉视点？"


def fixture_note(title, body, *, kind="主题笔记", category="声音与后期", problem="", sources=()):
    source_yaml = json.dumps([f"[[{path.removesuffix('.md')}]]" for path in sources], ensure_ascii=False)
    common = (f"---\n类型: {kind}\n分类: {category}\n状态: 持续积累\n材料类型: 隔离夹具\n"
              "信息来源: 自建测试正文\n完整程度: 当前夹具\n整理日期: 2026-10-03\n知识库版本: 2.1\n"
              f"适用阶段: [复盘与方法升级]\n解决问题: {problem}\n")
    if kind == "主题笔记":
        common += (f"主题域: {title}\n来源材料: {source_yaml}\n关联项目: []\n知识状态: 已提炼\n"
                   "成熟度: 种子\n上位主题: []\n相关主题: []\n最后复核: 2026-10-03\n证据状态: 单一来源\n")
        sections = ("## 核心命题\n" + problem + "\n## 学习材料\n隔离夹具，不是已核验外部知识。\n"
                    "## 内容导览\n按问题核对方法和条件。\n## 知识单元\n" + body +
                    "\n## 外部补充与分歧\n仅用于工具行为测试。\n## 项目应用与验证\n没有真实项目验证。\n")
    else:
        common += "沉淀状态: 未沉淀\n已沉淀主题: []\n待沉淀主题: []\n"
        sections = body
    return common + f"---\n# {title}\n\n" + sections


class ReferenceExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.library = self.vault / "知识库"
        self.creation = self.library / "创作区"
        self.learning = self.library / "学习区"
        self.cache = self.root / "cache"
        self.common = self.creation / "岗位共用"
        self.visual = self.creation / "C-导演与视觉"
        self.post = self.creation / "D-声音与后期"
        for folder in (self.common, self.visual, self.post, self.learning, self.cache,
                       self.vault / ".obsidian", self.root / "skills"):
            folder.mkdir(parents=True, exist_ok=True)
        (self.vault / "提示词.md").write_text("# 隔离夹具\n", encoding="utf-8")
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps({
            "version": 2, "workspace": ".", "vault": "vault", "vault_name": "vault",
            "knowledge_library": "vault/知识库", "source_notes": "vault/知识库/学习区",
            "creation_root": "vault/知识库/创作区", "learning_root": "vault/知识库/学习区",
            "raw_cache": "cache", "prompt_box": "vault/提示词.md", "obsidian_cli": None,
            "skills_root": "skills",
        }, ensure_ascii=False), encoding="utf-8")
        self.config = load_config(self.config_path)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, folder, title, body, **options):
        path = folder / (title + ".md")
        path.write_text(fixture_note(title, body, **options), encoding="utf-8")
        return path

    def color_only(self):
        body = ("### 曝光比较方法\n调色曝光需要记录事实和解释假设：先核对曝光与白平衡，再对照相邻肤色。"
                "发片后的差异记录可以保留成像状态，但曝光比较没有分发结果的因果方法。\n"
                "## 适用边界\n没有输入色彩身份不能判断曝光变化。")
        topic = self.write(self.post, "曝光与白平衡", body, problem="调色曝光如何记录事实和解释假设")
        source = self.write(self.post, "调色曝光来源", body, kind="来源笔记")
        return topic, source

    def generic_review(self, *, sources=()):
        body = ("### 记录事实与解释假设\n发片后的差异先记录事实，再列解释假设与反证；复盘时核对比较条件，"
                "避免把一次结果直接当作原因。记录观察与解释时，应区分实际差异、候选解释和验证动作。\n"
                "## 适用边界\n记录事实和解释假设不是原因认证；缺少相同条件不能认定改动有效。")
        return self.write(self.common, "决策复盘与反证", body,
                          category="创作实践与项目复盘", problem="发片后的差异怎样记录事实和解释假设", sources=sources)

    def sound_in_visual(self, *, long=False):
        text = ("声音转场突然变安静时，先检查声源归属与听觉视点，再在切点前后审听声音延续和空间归属。"
                "声音桥能够延续情绪，不能直接证明场景同时或空间毗邻。")
        if long:
            text += "\n" + ("复核声源归属与听觉视点，记录声音转场切点前后的可观察差异；尚未听媒体不认证效果。\n" * 180)
        body = "### 声源归属的检查顺序\n" + text + "\n## 适用边界\n声音转场必须审听；没有声音媒体只能给条件判断。"
        source = self.write(self.visual, "色彩场景手册的声音章节", body, kind="来源笔记", category="导演与视听语言")
        topic = self.write(self.visual, "视觉与色彩场景设计", body,
                           category="导演与视听语言", problem="声音转场怎样核对声源归属与听觉视点",
                           sources=[source.relative_to(self.vault).as_posix()])
        return topic, source

    def fictional_release_source(self):
        body = ("### 判断发布差异的顺序\n发片后的差异先核对传播量和受众到达记录，保留同一发布版本与采样范围。"
                "再比较事实与解释假设，检查原因依据是否来自可比较记录。平台曝光量只描述分发观察，"
                "不能直接证明传播差异的原因。\n## 适用边界\n受众变化的原因需要另外验证，夹具不代表真实平台规则。")
        source = self.write(self.common, "虚构发布观察资料", body, kind="来源笔记",
                            category="创作实践与项目复盘")
        topic = self.write(self.common, "发布差异与受众记录", body,
                           category="创作实践与项目复盘", problem="传播量与受众变化怎样核对事实和原因依据",
                           sources=[source.relative_to(self.vault).as_posix()])
        return topic, source

    def quick(self, query, **kwargs):
        return retrieve_scoped(self.config, query, role="D", no_cache=True, **kwargs)

    def review(self, query, questions=()):
        return review_scoped(self.config, query, questions, role="D", no_cache=True, budget=24000)[0]

    @staticmethod
    def review_paths(review, fields=("evidence_ids", "support_ids", "boundary_ids")):
        by_id = {item["id"]: item for item in review["evidence"]}
        return {Path(review["documents"][by_id[item_id]["document_id"]]["path"])
                for facet in review["facets"] for field in fields for item_id in facet[field]}

    def test_unknown_explicit_target_cannot_use_known_reference_as_primary(self):
        color, source = self.color_only()
        quick = self.quick(UNKNOWN_TARGET)
        self.assertEqual(UNKNOWN_TARGET, quick["query"])
        self.assertTrue(quick["method_gap"])
        self.assertFalse(any(card["method_chunks"] for card in quick["candidates"]))
        for item in quick.get("source_candidates", []):
            if Path(item["path"]) == source:
                self.assertIs(False, item["primary_eligible"])
                self.assertEqual("comparison_hint", item["use_role"])
        review = self.review(UNKNOWN_TARGET)
        self.assertEqual(UNKNOWN_TARGET, review["query"])
        self.assertEqual("gap", review["facets"][0]["status"])
        self.assertFalse(self.review_paths(review) & {color, source})
        # This is a bounded-call gap, never proof that the whole tree lacks knowledge.
        self.assertNotIn("全库", quick["gap_reason"] or "")
        self.assertNotIn("学习区", json.dumps(quick["scope"], ensure_ascii=False))

    def test_generic_observation_and_explanation_method_survives_reference_exclusion(self):
        self.color_only()
        generic = self.generic_review()
        quick = self.quick(UNKNOWN_TARGET)
        self.assertFalse(quick["method_gap"])
        self.assertIn(generic, {Path(card["path"]) for card in quick["candidates"] if card["method_chunks"]})
        review = self.review(UNKNOWN_TARGET)
        self.assertIn(generic, self.review_paths(review, ("evidence_ids",)))
        self.assertTrue(review["facets"][0]["boundary_ids"])
        self.assertEqual([], list(self.cache.rglob("*.json")))

    def test_reference_source_does_not_become_generic_method_support_or_boundary(self):
        color, source = self.color_only()
        generic = self.generic_review(sources=[source.relative_to(self.vault).as_posix()])
        review = self.review(UNKNOWN_TARGET)
        self.assertIn(generic, self.review_paths(review, ("evidence_ids",)))
        self.assertFalse(self.review_paths(review) & {color, source})
        self.assertEqual([], review["facets"][0]["support_ids"])
        self.assertTrue(review["facets"][0]["source_gap"])

    def test_actual_sound_method_in_visual_document_remains_primary_and_supported(self):
        self.color_only()
        topic, source = self.sound_in_visual()
        quick = self.quick(SOUND_TARGET)
        self.assertFalse(quick["method_gap"])
        self.assertIn(topic, {Path(card["path"]) for card in quick["candidates"] if card["method_chunks"]})
        review = self.review(SOUND_TARGET)
        used = self.review_paths(review, ("evidence_ids", "support_ids"))
        self.assertIn(topic, used)
        self.assertIn(source, used)
        self.assertTrue(review["facets"][0]["boundary_ids"])
        self.assertFalse(review["facets"][0]["source_gap"])

    def test_explicit_two_domain_comparison_retains_both_reading_domains(self):
        color, _ = self.color_only()
        release = self.write(self.common, "平台曝光量与受众记录",
            "### 分发数据检查\n平台曝光量属于分发数据，先核对平台曝光量，再记录事实和解释假设。"
            "平台曝光量与调色曝光不是同一观察量，比较时必须分别保留定义和测量对象。\n"
            "## 适用边界\n平台曝光量不能说明色彩曝光，比较两域不表示可以互相替代。",
            category="创作实践与项目复盘", problem="平台曝光量如何记录事实和解释假设")
        query = "参考知识：调色曝光。实际问题：比较调色曝光与平台曝光量的定义、观察对象和记录事实的边界。"
        quick = self.quick(query, limit=3)
        self.assertEqual({"color", "release"}, set(quick["query_roles"]["target_foci"]))
        review = self.review(query)
        all_paths = {Path(doc["path"]) for doc in review["documents"].values()}
        self.assertTrue({color, release} <= all_paths)

    def test_direct_creative_translation_is_not_a_reference_exclusion(self):
        target = self.write(self.visual, "情绪意图与色彩选择",
            "### 色彩表达的比较顺序\n用色彩表达角色的情绪变化，先明确情绪意图，再比较色彩明度与饱和度，"
            "让色彩表达落到当前场景的观看条件；光线方向与对比也须结合角色状态选择。\n"
            "## 适用边界\n色彩表达没有唯一正确答案，没有实际画面不认证情绪效果。",
            category="导演与视听语言", problem="如何用色彩表达角色的情绪变化")
        query = "如何用色彩表达角色的情绪变化？"
        quick = self.quick(query)
        self.assertFalse(quick["method_gap"])
        self.assertIn(target, {Path(card["path"]) for card in quick["candidates"] if card["method_chunks"]})
        self.assertIn(target, self.review_paths(self.review(query), ("evidence_ids",)))

    def test_exclusion_does_not_change_continuation_identity_or_learning_scope(self):
        topic, _ = self.sound_in_visual(long=True)
        learning = self.write(self.learning, "学习区的同名声源资料",
                              "### 声源归属的检查顺序\n未经点名的学习正文不参与本次调用。")
        quick = self.quick(SOUND_TARGET)
        card = next(card for card in quick["candidates"] if Path(card["path"]) == topic)
        token = next(item["continuation"] for item in card["method_chunks"] if item.get("continuation"))
        self.assertEqual(quick["snapshot"], token["snapshot"])
        self.assertEqual(quick["scope"], token["scope"])
        resumed = read_request(self.config, token, self.config_path)
        self.assertEqual(quick["snapshot"], resumed["snapshot"])
        self.assertEqual(quick["scope"], resumed["scope"])
        self.assertNotIn(str(learning), json.dumps(resumed, ensure_ascii=False))
        if token["mode"] == "section":
            tampered = copy.deepcopy(token)
            tampered["path"] = str(learning)
            with self.assertRaises(ValueError):
                read_request(self.config, tampered, self.config_path)

    def test_comparison_continuation_does_not_promote_primary_eligibility(self):
        self.color_only()
        review = self.review(UNKNOWN_TARGET)
        comparison = next(item for item in review["evidence"]
                          if item.get("use_role") == "comparison_hint" and item.get("continuation"))
        self.assertIs(False, comparison["primary_eligible"])
        resumed = read_request(self.config, comparison["continuation"], self.config_path)
        item = resumed["evidence"]
        self.assertEqual(comparison["id"], item["id"])
        self.assertEqual(review["scope"], resumed["scope"])
        self.assertEqual(review["snapshot"], resumed["snapshot"])
        # A raw full read lacks a fresh query judgment; it cannot grant eligibility.
        self.assertIsNot(True, item.get("primary_eligible"))

    def test_task_reference_exclusion_survives_applicability_subquestion(self):
        color, color_source = self.color_only()
        topic, source = self.fictional_release_source()
        subquestion = "本轮要判断发布后的传播差异，曝光与白平衡能否当作受众变化的原因依据？"
        review = self.review(UNKNOWN_TARGET, [subquestion])
        self.assertEqual(UNKNOWN_TARGET, review["query"])
        self.assertEqual(subquestion, review["facets"][0]["question"])
        used = self.review_paths(review)
        self.assertFalse(used & {color, color_source})
        self.assertTrue(used & {topic, source})

    def test_explicit_two_domain_subquestion_can_compare_reference_and_target(self):
        color, color_source = self.color_only()
        topic, source = self.fictional_release_source()
        subquestion = "请明确比较摄影曝光和平台曝光量的定义及各自原因解释方法。"
        review = self.review(UNKNOWN_TARGET, [subquestion])
        self.assertEqual(UNKNOWN_TARGET, review["query"])
        self.assertEqual(subquestion, review["facets"][0]["question"])
        paths = {Path(doc["path"]) for doc in review["documents"].values()}
        self.assertTrue(paths & {color, color_source})
        self.assertTrue(paths & {topic, source})

    def test_applicability_modal_variants_keep_open_verb_target_and_reference_separate(self):
        color, color_source = self.color_only()
        topic, source = self.fictional_release_source()
        cases = (
            ("调色曝光方法有没有资格用来识别发布后的传播差异？", "识别发布后的传播差异"),
            ("调色曝光方法合不合适用于甄别发布后的受众变化？", "甄别发布后的受众变化"),
            ("调色曝光方法究竟是否适合用来辨认发布后的传播差异？", "辨认发布后的传播差异"),
            ("调色曝光方法可不可以用来溯源发布后的受众变化？", "溯源发布后的受众变化"),
            ("调色曝光方法有必要用于量化发布后的传播差异吗？", "量化发布后的传播差异"),
        )
        for query, target_clause in cases:
            with self.subTest(query=query):
                review = self.review(query)
                self.assertEqual(query, review["query"])
                self.assertIn(target_clause, review["facets"][0]["query_roles"]["target_text"])
                used = self.review_paths(review)
                self.assertFalse(used & {color, color_source})
                self.assertTrue(used & {topic, source})

    def test_direct_and_applicable_sound_to_visual_translation_keep_real_method(self):
        bridge = self.write(self.common, "声音桥与视觉转场",
            "### 声音桥连接画面的顺序\n声音桥连接画面转场时，先选需要延续的声音，再跨切点安排起止位置，"
            "使視听信息过渡。声音桥可以服务视觉转场，但必须审听声源归属并核对观看意图。\n"
            "## 适用边界\n声音桥不能直接证明两个场景同时，没有连续声画只给条件判断。",
            problem="声音桥怎样连接画面转场并服务视觉转场")
        for query in ("用声音桥连接画面转场。", "声音桥是否可以服务视觉转场？"):
            with self.subTest(query=query):
                quick = self.quick(query)
                self.assertFalse(quick["method_gap"])
                self.assertIn(bridge, self.review_paths(self.review(query), ("evidence_ids",)))

    def same_domain_color_method(self):
        return self.write(self.post, "肤色变化的技术检查",
            "### 识别肤色变化的顺序\n识别肤色变化时，先记录同一角色在相同光源下的肤色变化，再检查输入色彩解释与曝光。"
            "只有一次输出，需要比较光源、妆发和技术处理的线索，避免把妆发变化当作管线失配。\n"
            "## 适用边界\n肤色变化不自动表示调色错误，缺少真实输入不能认证修正结果。",
            problem="调色曝光怎样识别肤色变化和保留光源条件")

    def test_same_domain_applicability_question_keeps_target_method(self):
        color = self.same_domain_color_method()
        query = "调色曝光方法有没有资格用来识别肤色变化？"
        self.assertFalse(self.quick(query)["method_gap"])
        self.assertIn(color, self.review_paths(self.review(query), ("evidence_ids",)))

    def test_concrete_facts_before_need_to_compare_clause_are_not_trimmed(self):
        self.same_domain_color_method()
        query = "同一角色在相同光源下肤色突然变化，只有一次输出，需要比较哪些线索？"
        quick = self.quick(query)
        self.assertEqual(query, quick["query"])
        self.assertEqual(query, quick["query_roles"]["target_text"])
        self.assertFalse(quick["method_gap"])

    def test_unclosed_reference_applicability_question_does_not_promote_domain(self):
        self.color_only()
        query = "调色曝光方法究竟能不能用来？"
        quick = self.quick(query)
        self.assertEqual(query, quick["query"])
        self.assertTrue(quick["method_gap"])
        self.assertFalse(any(card["method_chunks"] for card in quick["candidates"]))
        self.assertEqual("gap", self.review(query)["facets"][0]["status"])

    def test_reduplicated_modal_applicability_excludes_reference_primary(self):
        mix_body = ("### 混音检查顺序\n混音方法先核对声音接口，再比较声源归属、音频状态和监听条件。"
                    "混音记录在相同播放条件下观察变化。\n## 适用边界\n未听音频不能认证混音效果。")
        mix = self.write(self.post, "混音方法", mix_body, problem="混音方法怎样检查声音接口")
        mix_source = self.write(self.post, "虚构混音资料", mix_body, kind="来源笔记")
        costume_body = ("### 辨认服装状态变化的顺序\n辨认服装状态变化时，先按剧情时点列出服装的污损和修补，"
                        "再逐镜核对衣服状态变化。服装状态相同才能比较生成版本差异。\n"
                        "## 适用边界\n服装状态变化须结合剧情时点，不能只按单帧认定错误。")
        costume_source = self.write(self.common, "虚构服装状态资料", costume_body,
                                    kind="来源笔记", category="摄影美术与现场制作")
        costume = self.write(self.common, "服装状态变化", costume_body,
                             category="摄影美术与现场制作", problem="辨认服装状态变化",
                             sources=[costume_source.relative_to(self.vault).as_posix()])
        color, color_source = self.color_only()
        interface_body = ("### 处理声音接口的顺序\n处理声音接口时，先核对声源归属与开始结束状态，再连续审听"
                          "切点的声音变化；声音接口的中断要比较空间归属和监听条件。\n"
                          "## 适用边界\n没有声音媒体不能认证接口修正。")
        interface_source = self.write(self.common, "虚构声音接口资料", interface_body, kind="来源笔记")
        interface = self.write(self.common, "声音接口处理", interface_body, problem="处理声音接口",
                               sources=[interface_source.relative_to(self.vault).as_posix()])
        cases = (
            ("混音方法是不是能用于辨认服装状态变化？", {mix, mix_source}, {costume, costume_source}),
            ("摄影曝光可不可用于处理声音接口？", {color, color_source}, {interface, interface_source}),
        )
        for query, reference_paths, target_paths in cases:
            with self.subTest(query=query):
                review = self.review(query)
                self.assertEqual(query, review["query"])
                used = self.review_paths(review)
                self.assertFalse(used & reference_paths)
                self.assertTrue(used & target_paths)

    def test_plain_negative_fact_is_not_a_reduplicated_applicability_question(self):
        self.color_only()
        query = "摄影曝光不是声音接口，曝光和白平衡应如何检查？"
        quick = self.quick(query)
        self.assertEqual(query, quick["query"])
        self.assertEqual(query, quick["query_roles"]["target_text"])
        self.assertIsNone(quick["query_roles"]["comparison_status"])
        review = self.review(query)
        self.assertEqual(query, review["facets"][0]["query_roles"]["target_text"])
        self.assertIsNone(review["facets"][0]["query_roles"]["comparison_status"])


if __name__ == "__main__":
    unittest.main()
