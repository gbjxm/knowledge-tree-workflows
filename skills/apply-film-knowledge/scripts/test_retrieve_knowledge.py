from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from retrieve_knowledge import load_config, load_routes, load_topics, parse_formal_relations, retrieve


def topic_text(
    title: str,
    problem: str,
    stages: str,
    core: str,
    *,
    category: str = "故事与剧本",
    extra: str = "",
) -> str:
    return f"""---
类型: 主题笔记
分类: {category}
解决问题: {problem}
适用阶段: [{stages}]
证据状态: 单一来源
掌握状态: 未检验
---

# {title}

## 核心命题

{core}

## 适用边界

- 只在测试条件内使用。

## 知识单元

### 最小方法

先确认当前问题，再完成一个可观察的最小动作。

## 我的默认做法

- 先做最小检查。

## 相关知识

{extra}
"""


class RetrieveKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.library = self.vault / "library"
        self.sources = self.vault / "sources"
        self.cache = self.root / "cache"
        for directory in (self.library, self.sources, self.cache, self.vault / ".obsidian"):
            directory.mkdir(parents=True, exist_ok=True)
        self.prompt_box = self.vault / "prompt-box.md"
        self.executable = self.root / "Obsidian.com"
        self.prompt_box.write_text("# prompts\n", encoding="utf-8")
        self.executable.write_text("stub", encoding="utf-8")
        (self.library / "从灵感到完整故事.md").write_text(
            topic_text(
                "从灵感到完整故事",
                "如何把零散灵感发展成完整故事",
                "灵感与命题, 故事骨架",
                "用欲望、冲突和选择建立完整故事。",
            ),
            encoding="utf-8",
        )
        (self.library / "场面调度与镜头覆盖.md").write_text(
            topic_text(
                "场面调度与镜头覆盖",
                "怎样安排人物空间和最小镜头覆盖",
                "视觉设计, 生成与镜头",
                "人物行动先于摄影机，覆盖只保留可剪价值。",
                category="导演与视听语言",
            ),
            encoding="utf-8",
        )
        (self.library / "00-故事地图.md").write_text(
            """---
类型: 知识地图
分类: 导演与视听语言
---
# 导演地图

## 按创作问题调用

### 处理站着说话的对话场景

- **什么时候进入**：人物只是站着说话，镜头只是角度清单。
- **调用顺序**：先用 [[场面调度与镜头覆盖]] 建立人物空间和最小覆盖。
- **何时停止或返回**：人物和摄影机共同完成关系变化时停止。
""",
            encoding="utf-8",
        )
        self.config = self.root / "knowledge-tree.json"
        self.config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "workspace": str(self.root),
                    "vault": str(self.vault),
                    "vault_name": "vault",
                    "knowledge_library": str(self.library),
                    "source_notes": str(self.sources),
                    "raw_cache": str(self.cache),
                    "prompt_box": str(self.prompt_box),
                    "obsidian_cli": str(self.executable),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_loads_only_topics_from_configured_library(self) -> None:
        config = load_config(self.config)
        topics = load_topics(Path(config["knowledge_library"]))
        self.assertEqual(2, len(topics))
        self.assertNotIn("故事地图", {topic.title for topic in topics})

    def test_retrieval_is_stable_and_capped_at_three(self) -> None:
        topics = load_topics(self.library)
        first = retrieve(topics, "一个模糊灵感怎么发展成完整故事", "灵感与命题", 99)
        second = retrieve(topics, "一个模糊灵感怎么发展成完整故事", "灵感与命题", 99)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first["candidates"]), 3)
        self.assertEqual("从灵感到完整故事", first["candidates"][0]["title"])
        self.assertEqual("单一来源", first["candidates"][0]["evidence_status"])
        self.assertTrue(first["candidates"][0]["boundary"])

    def test_unsupported_problem_returns_gap(self) -> None:
        result = retrieve(load_topics(self.library), "设计电影宇宙区块链票务系统", "行业观察")
        self.assertTrue(result["gap"])
        self.assertEqual([], result["candidates"])

    def test_valid_stage_does_not_force_unrelated_problem(self) -> None:
        result = retrieve(load_topics(self.library), "角色骨骼权重炸了怎么修", "生成与镜头")
        self.assertTrue(result["gap"])

    def test_map_route_and_compact_professional_card(self) -> None:
        topics = load_topics(self.library)
        routes = load_routes(self.library)
        result = retrieve(topics, "两个人站着说话，镜头怎么拍才不死", "视觉设计", routes=routes)
        card = result["candidates"][0]
        self.assertEqual("场面调度与镜头覆盖", card["title"])
        for field in ("core", "boundary", "evidence_status"):
            self.assertTrue(card[field], field)
        # The fixture's generic instruction is not a body method for staging
        # a dialogue scene. Navigation must remain useful without inventing
        # a method or action merely to keep a card field nonempty.
        self.assertTrue(card["method_gap"])
        self.assertEqual([], card["method_chunks"])
        self.assertEqual("", card["minimal_action"])
        self.assertEqual("navigation_hint", card["route"]["kind"])

    def test_formal_relation_rows_are_exposed(self) -> None:
        body = """## 相关知识

### 同类知识连接

| 相关主题 | 分类 | 关系 | 连接理由 | 依据 |
|---|---|---|---|---|
| [[从梗概到可拍大纲]] | 故事与剧本 | 转译 | 把选择写成事件 | 现有笔记明示 |
"""
        relations = parse_formal_relations(body)
        self.assertEqual(1, len(relations))
        self.assertEqual("从梗概到可拍大纲", relations[0].target)
        self.assertEqual("转译", relations[0].relation)


if __name__ == "__main__":
    unittest.main()
