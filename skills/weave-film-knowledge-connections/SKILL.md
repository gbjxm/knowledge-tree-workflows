---
name: weave-film-knowledge-connections
description: Discover, preview, confirm, write, and audit typed semantic relationships between existing film-creation topic notes in the user's Obsidian knowledge tree, including same-category and cross-category connections. Use when the user says “把这些知识串起来”, “检查知识孤岛”, “它们是什么关系”, “从剧本到镜头解释”, “确认连接”, or during 知识收尾 for changed topics. Do not use for navigation-only links, source extraction, evidence research, topic creation or fusion, mastery testing, or project-result writeback.
---

# Weave Film Knowledge Connections

Build a usable semantic network without turning link count into a goal. Connect only existing, substantive topic notes when the relationship changes a concrete creative decision.

## Goal and success

- Distinguish navigation hints, formal semantic relationships, and source/project evidence links.
- Preview every first-batch, cross-category, conflict, deletion, or relationship-change write.
- Write formal relationships in both notes with type, reason, basis, and reciprocal metadata.
- Finish only after note validation and the strict relationship audit pass.

## Location and references

Load all default paths from the discovered portable `.codex/knowledge-tree.json` through the shared `operate-personal-knowledge-tree` loader. Only `KNOWLEDGE_TREE_CONFIG` may select another complete configuration; explicit CLI paths remain bounded overrides.

Read `references/connection-contract.md` before previewing, writing, changing, or deleting a formal relationship. Follow [the shared zone contract](../grow-creative-library/references/library-layout.md): `分类` defines same/cross-category relationships independently of role folders. A relationship or source link never admits learning content into default creative retrieval.

## Boundaries

- Let `grow-creative-library` create or fuse topics. This Skill never creates a topic, including a cross-domain topic.
- Let `apply-film-knowledge` retrieve topics for a creative problem and record explicit project feedback.
- Let `internalize-film-knowledge` diagnose demonstrated mastery; do not create links during its question.
- Let `operate-personal-knowledge-tree` run routing, closeout, status, and weekly review.
- Route missing evidence or substantive knowledge revision to `grow-creative-library`.
- Never upgrade evidence from a link or from `Codex综合`.

## Workflow

1. Read the North Star, tree status, and every named or session-changed topic in full.
2. Search titles, `解决问题`, core propositions, stages, projects, body explanations, and existing typed relationships within the authorized zone or explicitly named notes. Creative closeout does not automatically expand through links into learning content.
3. Classify each observed link:
   - navigation: map, total index, compatibility entry, or scanning aid;
   - semantic: changes a creative decision and meets the contract;
   - evidence/application: route to the source or project contract.
4. Reject keyword-only, empty, map-only, quota-driven, or consequence-free candidates.
5. Select a directional relation and basis. Judge the reverse direction separately.
6. For explicit requests, preview at most two highest-value connections unless the user requested the initial whole-tree batch. During `知识收尾`, inspect only changed topics and preview at most two.
7. Show a stable preview number, both directions, affected files, and `未写入`; then stop.
8. Apply only the current preview or numbered items explicitly confirmed. A changed type or reason requires a revised preview.
9. Preflight both files, record their hashes, write both directions, validate each note, then run the strict relationship audit.
10. If any step fails, restore both files to their preflight hashes and stop before processing another relationship.

## Preview format

```markdown
### 知识连接预览（未写入）

| 编号 | 范围 | 起点 | 终点 | 关系 | 连接理由 | 依据 |
|---:|---|---|---|---|---|---|
| 1 | 同类 | [[起点主题]] | [[终点主题]] | 转译 | 忽略关系会导致的具体判断错误 | 现有笔记明示 |

反向写回：[[终点主题]] → [[起点主题]]，关系为“前置”。
影响文件：两篇主题笔记。
```

Accept `确认连接`, `只确认第 1 条`, `第 1 条改成制约`, or `不连接`. Silence and unrelated replies are not confirmation. Never persist unconfirmed candidates.

## 补查候选入口

新增材料检查可提供 unconfirmed_reading_candidate，说明见 [新增材料补查](../apply-film-knowledge/references/incremental-followup.md)。它只是阅读线索，不扩张分区或当前授权范围。先按本 Skill 读取范围内的相关主题并判断实质关系，不能把命中词当连接理由；来源→主题的沉淀归 grow，正式主题→主题关系仍遵守预览、确认和双向写回。

## Writeback

- Add reciprocal wikilinks to `相关主题` without deleting navigation hints.
- Put same-category rows under `### 同类知识连接`.
- Put cross-category rows under `### 跨域连接` and recompute optional `涉及分类`.
- Preserve existing prose, navigation bullets, source links, project evidence, mastery, maturity, and personal understanding.
- Update only `最后复核`; do not change `整理日期` merely because a relationship was added.
- Use path-qualified wikilinks when duplicate titles or cross-folder ambiguity is possible.
- Never duplicate rows.

Run:

```powershell
python ..\grow-creative-library\scripts\validate_note.py "<changed-note>"
python .\scripts\audit_connections.py --strict
```

## Completion contract

- **Done**: both directions written, metadata consistent, note validation and strict audit pass.
- **Partial**: a write or validation failed; restore the affected pair, report the failure, and do not continue.
- **Stop**: no confirmation where required, no substantive target, insufficient basis, unresolved knowledge conflict, or strict audit failure. Do not report complete.

## Weekly review

Report formal same-category edges, formal cross-category edges, navigation hints, and semantic islands separately. An island is not automatically a defect. Recommend weaving only when the current creative problem has a high-confidence candidate and no higher-priority error, disagreement, understanding, or mastery task is pending.
