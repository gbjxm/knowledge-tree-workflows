"""Problem-level retrieval regressions using isolated, disposable documents."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from knowledge_evidence import candidates, load_corpus, make_review
from retrieve_knowledge import load_topics, retrieve


def note(title, body, *, kind="主题笔记", problem=""):
    return (f"---\n类型: {kind}\n分类: 声音与后期\n解决问题: {problem}\n"
            f"材料类型: 专业资料汇编\n---\n# {title}\n\n{body}\n")


class LexicalRelevanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.sources = self.vault / "sources"
        self.cache = self.root / "cache"
        for folder in (self.library, self.sources, self.cache):
            folder.mkdir(parents=True)
        self.config = dict(vault=str(self.vault), knowledge_library=str(self.library),
                           source_notes=str(self.sources), raw_cache=str(self.cache))

    def tearDown(self):
        self.temp.cleanup()

    def write(self, title, body, *, source=False, problem=""):
        path = (self.sources if source else self.library) / (title + ".md")
        path.write_text(note(title, body, kind="材料总览" if source else "主题笔记", problem=problem),
                        encoding="utf-8")
        return path.relative_to(self.vault).as_posix()

    def test_natural_scene_details_do_not_hide_continuity_method(self):
        self.write("运动方向与动作接口", "## 核心命题\n空间轴线和动作接口要在切点比较。\n"
                   "## 知识单元\n### 连续动作对照\n对照连续动作与剪点，区分运动方向、空间轴线和动作接口。\n"
                   "## 适用边界\n没有真实素材不能认定应重拍。",
                   problem="运动方向、空间轴线和动作接口怎样在剪点检查")
        question = ("一个戴着围巾的小男孩从图书室推门离开，摄像机绕到架子后时，"
                    "画面里的运动方向反过来了，我要怎样区分空间轴线、动作接口和剪点的问题？")
        result = retrieve(load_topics(self.library), question)
        self.assertFalse(result["gap"])
        self.assertEqual(result["candidates"][0]["title"], "运动方向与动作接口")
        self.assertIn("连续动作", result["candidates"][0]["method_chunks"][0]["content"])

    def test_quick_context_cannot_manufacture_a_topic_match(self):
        self.write("对白底噪", "## 核心命题\n对白底噪应在剪口连续。\n## 知识单元\n"
                   "### 剪口\n用对白底噪与环境声音检查剪口。", problem="对白底噪怎样连续")
        result = retrieve(load_topics(self.library), "离子推进器燃料泵维修扭矩", role="D",
                          constraints="对白底噪 环境声音 剪口", expected_output="对白编辑")
        self.assertTrue(result["gap"])
        self.assertEqual(result["context"]["constraints"], "对白底噪 环境声音 剪口")

    def test_title_without_specific_body_is_not_source_evidence(self):
        self.write("肤色调色与镜头匹配", "## 适用边界\n保持意图；相邻两个环节需要协作。", source=True)
        corpus = load_corpus(self.config)
        self.assertEqual(candidates(corpus, "相邻两镜肤色变化大，是调色管线或镜头匹配问题吗"), [])

    def test_link_navigation_does_not_substitute_for_a_method(self):
        self.write("来源索引", "## 已沉淀的知识\n[[肤色调色与镜头匹配]]\n", source=True)
        corpus = load_corpus(self.config)
        review = make_review(corpus, "肤色调色与镜头匹配", ["肤色调色与镜头匹配"])
        self.assertEqual(review["facets"][0]["status"], "gap")
        self.assertFalse(review["evidence"])

    def test_sound_boundary_is_not_a_skin_tone_diagnosis(self):
        sound = self.write("声音设计", "## 适用边界\n声音意图交给相邻两个部门处理，变化需要记录。")
        color = self.write("镜头肤色匹配", "## 知识单元\n### 区分光源与管线\n"
                           "肤色匹配先核对调色管线，再比较灯光；只保留与光源意图一致的差异。\n"
                           "## 适用边界\n肤色差异不能凭单帧或数值认定错误。")
        corpus = load_corpus(self.config)
        review = make_review(corpus, "相邻两镜肤色变化大，先查灯光意图还是调色管线", [], role="D")
        paths = {doc["path"] for doc in review["documents"].values()}
        self.assertIn(str((self.vault / color).resolve()), paths)
        self.assertNotIn(str((self.vault / sound).resolve()), paths)
        primary = next(e for e in review["evidence"] if e["id"] in review["facets"][0]["evidence_ids"])
        self.assertEqual(primary["heading"], "区分光源与管线")
        self.assertTrue(review["facets"][0]["boundary_ids"])

    def test_each_consumed_method_keeps_its_own_boundary(self):
        for title, limit in (("输入解释", "先确认素材输入身份"), ("匹配锚点", "只比较同一剧情状态")):
            self.write(title, "## 知识单元\n### 肤色匹配\n肤色匹配要比较调色管线和参考锚点。\n"
                       f"## 适用边界\n{limit}。")
        corpus = load_corpus(self.config)
        review = make_review(corpus, "肤色匹配 调色管线 参考锚点", [])
        facet = review["facets"][0]
        by_id = {item["id"]: item for item in review["evidence"]}
        method_documents = {by_id[item_id]["document_id"] for item_id in facet["evidence_ids"]}
        boundary_documents = {by_id[item_id]["document_id"] for item_id in facet["boundary_ids"]}
        self.assertEqual(len(method_documents), 2)
        self.assertEqual(method_documents, boundary_documents)

    def test_known_generic_word_cannot_answer_unknown_engineering_problem(self):
        self.write("镜头节奏推进", "## 核心命题\n推进情绪。\n## 知识单元\n"
                   "### 动势\n推进与停顿用于镜头节奏。", problem="镜头如何推进")
        result = retrieve(load_topics(self.library), "离子推进器燃料泵密封泄漏怎样计算维修扭矩", role="C")
        self.assertTrue(result["gap"])

    def test_short_professional_terms_keep_their_complete_characters(self):
        for term in ("轴线", "焦距", "蒙太奇", "和声", "和弦"):
            with self.subTest(term=term):
                self.write(term, f"## 核心命题\n{term}需要按实际意图比较。\n## 知识单元\n"
                           f"### 对照\n比较{term}的两个候选，缺少素材时不认证效果。", problem=term)
                result = retrieve(load_topics(self.library), term)
                self.assertFalse(result["gap"])
                self.assertEqual(result["candidates"][0]["title"], term)

    def test_sound_bridge_is_not_a_file_identity_table(self):
        identity = self.write("对白版本身份", "## Line版本记录\n"
                              "| 声音来源 | 文件版本 | 空间 |\n|---|---|---|\n| | | |\n")
        bridge = self.write("声音桥", "## 知识单元\n### 叙事声源\n"
                            "让上一场声音延续到下一场，观众仍需在适当时刻理解声源。\n"
                            "声音桥可以连接情绪或跨越空间，不证明两场同时。\n"
                            "## 适用边界\n不擅定空间毗邻。")
        review = make_review(load_corpus(self.config), "检查声音衔接", [
            "如何让原场景声音延续并避免观众误读声音来源？"])
        primary = {e["id"]: e for e in review["evidence"]}
        paths = {review["documents"][primary[item]["document_id"]]["path"]
                 for item in review["facets"][0]["evidence_ids"] + review["facets"][0]["support_ids"]}
        self.assertIn(str((self.vault / bridge).resolve()), paths)
        self.assertNotIn(str((self.vault / identity).resolve()), paths)

    def test_real_sound_method_in_another_discipline_remains_readable(self):
        key = self.write("剧本场景方法", "## 知识单元\n### 声画衔接\n"
                         "声音延续可以构成声音转场；用听觉视点交代声源，放回场景审听。\n"
                         "## 适用边界\n声音桥不证明两个场景同时。")
        review = make_review(load_corpus(self.config), "检查声音转场", ["声音延续怎样交代声源？"])
        self.assertEqual(review["facets"][0]["status"], "needs_semantic_review")
        self.assertIn(str((self.vault / key).resolve()), {d["path"] for d in review["documents"].values()})

    def test_visual_source_is_not_bound_to_a_sound_transition(self):
        source = self.write("合成与Alpha", "## 运算方法\nAlpha与颜色运算顺序不能任意交换。\n"
                            "## Spotting\nVFX也可以用声音转移注意。", source=True)
        key = self.write("声音转场", "## 知识单元\n### 衔接审听\n"
                         "声音转场处理后须审听底噪与声源，先比较衔接，再判断安静是否丢失。\n"
                         "## 适用边界\n未听媒体不认证衔接。")
        # A previously recorded source link does not make its contents relevant.
        path = self.vault / key
        path.write_text(path.read_text(encoding="utf-8").replace("材料类型:",
                        f'来源材料: ["[[{source.removesuffix(".md")}]]"]\n材料类型:'), encoding="utf-8")
        review = make_review(load_corpus(self.config), "检查声音转场", ["声音转场的处理顺序和听审边界是什么？"])
        self.assertEqual(review["facets"][0]["support_ids"], [])
        self.assertTrue(review["facets"][0]["source_gap"])

    def test_definition_warning_does_not_replace_a_continuity_method(self):
        rows = ["| 专业术语 | 定义 | 典型用途 | 误区 |", "|---|---|---|---|"]
        rows += [f"| 方位{i} | 近景视线与画面方向 | 双人相对 | 空间容易出错 |" for i in range(12)]
        self.write("镜头术语", "## 专业术语表\n" + "\n".join(rows))
        self.write("视线与空间轴线", "## 知识单元\n### 匹配方法\n"
                   "保持视线与画面方向：先画双人相对站立的空间轴线，再逐镜对照近景的观看方向。\n"
                   "## 适用边界\n方向改变要让观众重新定位。")
        review = make_review(load_corpus(self.config), "检查空间连续性", [
            "双人相对站立的近景视线与画面方向如何保持空间清楚？"])
        by_id = {item["id"]: item for item in review["evidence"]}
        self.assertEqual(by_id[review["facets"][0]["evidence_ids"][0]]["heading"], "匹配方法")

    def test_polysemous_project_facts_do_not_choose_a_professional_object(self):
        decision = self.write("决策复盘", "## 知识单元\n### 解释与反证\n"
                              "复盘先列事实，再区分解释假设与反证；缺少实际结果不能确定归因。\n"
                              "## 适用边界\n一次结果不能证明方法有效。")
        self.write("曝光与色彩解释", "## 知识单元\n### 曝光匹配\n"
                   "曝光和白平衡要在同一色彩管线比较；实际结果需要记录事实。\n"
                   "## 适用边界\n缺少素材不能认证调色。")
        corpus = load_corpus(self.config)
        question = "复盘怎样区分事实、解释假设与反证？"
        plain = make_review(corpus, "检查决策依据", [question])
        for material in ("平台曝光和受众数据尚未取得。", "曝光、白平衡、色彩是材料中的词，不是本次复盘对象。"):
            with self.subTest(material=material):
                actual = make_review(corpus, "检查决策依据", [question], material=material)
                self.assertEqual(actual["facets"][0]["evidence_ids"], plain["facets"][0]["evidence_ids"])
                primary = {e["id"]: e for e in actual["evidence"]}
                docs = {actual["documents"][primary[item]["document_id"]]["path"]
                        for item in actual["facets"][0]["evidence_ids"]}
                self.assertEqual(docs, {str((self.vault / decision).resolve())})

    def test_explicit_empty_focus_survives_context_hints(self):
        self.write("对白底噪", "## 知识单元\n### 剪口连续\n对白底噪在剪口需要比较环境纹理。")
        corpus = load_corpus(self.config)
        question = "对白底噪怎样保持剪口连续？"
        plain = candidates(corpus, question, focus=())
        hinted = candidates(corpus, question, focus=(), context_hint="曝光 色彩 白平衡 VFX素材事实")
        self.assertEqual([r["block"]["id"] for r in plain], [r["block"]["id"] for r in hinted])


if __name__ == "__main__":
    unittest.main()
