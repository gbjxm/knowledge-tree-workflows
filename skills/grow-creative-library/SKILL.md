---
name: grow-creative-library
description: Build and continuously refine a Chinese Obsidian knowledge system by designing source architecture, organizing source notes and purpose-selected reusable topic knowledge, creating substantive cross-category topics before they are connected, and maintaining knowledge maps or lifecycle queues. Use for general web, book, PDF, audio, transcript, link, and local-file learning material, or for topic fusion after a source-specific Skill finishes. For Bilibili or Douyin sources, resolve intake purpose and note architecture here, then hand extraction to the respective source Skill. Hand formal relationships to weave-film-knowledge-connections and actual knowledge retrieval or project-practice writeback to apply-film-knowledge.
---

# Grow Creative Library

Build a working personal knowledge tree rather than a pile of source summaries. Preserve source traceability, organize reusable knowledge by creative problem, and keep personal reflection distinct from source claims. Hand explicitly requested learning, questioning and mastery diagnosis to `internalize-film-knowledge`; hand all typed topic relationships to `weave-film-knowledge-connections`; hand knowledge retrieval and explicit project-practice writeback to `apply-film-knowledge`; for session routing, lifecycle queues, North Star decisions, or weekly review, hand off to `operate-personal-knowledge-tree`.

## Location contract

- Discover `.codex/knowledge-tree.json` through the shared loader in `operate-personal-knowledge-tree\scripts\knowledge_tree_config.py`; never assume a drive letter or installation root.
- Use `vault`, `knowledge_library`, `source_notes`, and `raw_cache` from that configuration. North Star and tree status are inside `knowledge_library\00-待归档与知识地图`. Read [the shared zone contract](references/library-layout.md) for `creation_root`, `learning_root`, professional indexes, and source placement; learning sources do not automatically enter the creative zone.
- Only `KNOWLEDGE_TREE_CONFIG` may select another complete configuration; never add local path defaults or fall back to another vault.
- Explicit `--vault` and cache arguments override JSON defaults when supplied.
- Do not move, rewrite, or batch-migrate existing notes unless the user explicitly asks.

## Core workflow

1. Inspect the source URL or file metadata, visible table of contents, requested scope, and existing source notes. Distinguish `材料类型` from `笔记架构`; length alone never decides note shape.
2. Read `references/source-routing.md` and infer a recommended `材料类型`, `笔记架构`, `聚合单位`, target zone/role and professional category. Reuse an already explicit purpose or destination.
3. Apply the source-architecture gate before downloading full media, running ASR/OCR, drafting final notes, or writing anywhere in the vault. Only when note shape or destination is genuinely undecided, present one concise recommendation with options equivalent to `按推荐处理`, `改为单篇`, and `自定义`; existing explicit authorization and decisions need no repeated gate.
4. Treat an explicit user architecture as confirmation. If the same named source already records `架构状态: 已确认`, reuse its `笔记架构` and `聚合单位` without asking again unless the source topology changes or the user requests a different structure.
5. After confirmation, use the relevant installed source skill or tool and record the architecture on the source overview or single source note. Do not ask the same architecture question again in downstream skills.
6. Before source-note writing, read `references/accuracy-and-merging.md`. Establish the actual acquisition scope and a source-ordered content inventory; distinguish text, audio, visual evidence, and unresolved gaps.
7. When source content is unavailable or local evidence is insufficient, explain the gap in a working update and research reliable external material without waiting for a second confirmation. Keep supplements, links, date, reliability, disagreement, and uncertainty visibly separate.
8. Extract each source independently before synthesizing multiple sources. Default to full understanding of the acquired scope: preserve substantive claims, reasoning, distinct examples and conditions in the source note before selecting reusable topic knowledge.
9. Build a two-level content guide:
    - an overall outline;
    - a detailed semantic timeline, chapter/page guide, or heading/section guide.
10. Apply the shared contract's source-to-note, note-to-source, and old-to-new review. Keep author claims, recognition uncertainty and supplements distinct. Run the read-only coverage check described in `references/source-coverage-check.md`; unresolved evidence limits the completion claim and downstream use.
11. For source-to-knowledge work or library-structure work, read `references/knowledge-system.md` and the `operate-personal-knowledge-tree` operating contract, then apply the deposit contract within the selected zone. Learning-only intake may finish with its source notes or learning-zone synthesis; it does not require creative-topic deposits.
12. Search existing topic notes by problem, aliases, and meaning within the authorized destination. Only explicitly selected learning knowledge may be fused into creative topics. Fuse reusable concepts, principles, methods, cases, boundaries, and open questions; do not reproduce the source outline.
13. Link both directions: the source records actual deposited topic notes, and each topic records the source note. Never create a wikilink merely to represent an idea that has not been written.
14. Use `assets/topic-note-template.md` for topic knowledge, `assets/source-overview-template.md` for long sources, and `assets/knowledge-map-template.md` for maps. Project-application records have one authority: hand them to `apply-film-knowledge` and its `assets/project-application-template.md`.
15. Include the destination zone/role and professional category in the initial recommendation when clear. If a destination remains genuinely ambiguous after extraction, ask once before archiving and offer one recommendation plus at most two alternatives. A category is a professional property, not a folder choice.
16. After architecture and category confirmation:
    - merge ordinary additions directly;
    - preview deletions, major restructuring, or conflict resolution before writing.
17. Complete source saving and any authorized in-zone topic fusion without automatically creating questions, exercises, learning fields, or an internalization handoff. Use `internalize-film-knowledge` only when the user asks to learn or be tested; learning writeback requires an explicit request to save that result.
18. Update the relevant role/learning navigation and professional index under `00-待归档与知识地图/专业索引`, plus `00-待归档与知识地图\知识库主页.md` when those navigation surfaces exist. Create maps only during explicit library-structure work.
19. If a project result is available, do not create an application record here. Hand it to `apply-film-knowledge`; that Skill requires explicit writeback authorization and observable results before any evidence-upgrade proposal. Otherwise leave project results unclaimed; do not create a personal exercise.
20. Do not add a formal same-category or cross-category `相关主题` merely because two topics seem related. At `知识收尾`, let `operate-personal-knowledge-tree` hand changed topics to `weave-film-knowledge-connections` for a preview-only pass.
21. Validate the note with `scripts/validate_note.py`; for system work also run `scripts/audit_knowledge_system.py`, then refresh the status surface through `operate-personal-knowledge-tree`.

## 入库后的增量补查

完成已授权的来源保存与主题融合后，读取 [新增材料补查](../apply-film-knowledge/references/incremental-followup.md)，运行 knowledge_followup.py --suggest --checkpoint。检查变化、未沉淀材料、单向来源入口、重复和受影响主题；阅读候选后再按本 Skill 原授权范围和分区处理普通融合。学习区完整保存或内部综合即可完成学习入库，不能因补查候选自动转入创作区；创作补查也不沿链接读取未点名的学习材料。未确认语义关系只预览，合理独立可保留；deferred 项不能报已完成。

## Source architecture gate

The initial question is a decision about note shape, not merely a request to name the media type. Use this compact form:

```text
我判断这是【材料类型】，建议采用【笔记架构】，按【聚合单位】整理；归入【创作岗位或学习子目录】，专业分类为【六类之一】。
请选择：按推荐处理 / 改为单篇 / 自定义。
```

- Ask once before the first final-vault write only if the source architecture or destination has not already been decided or authorized.
- Do not ask when the user has already specified the architecture in the current request.
- Do not ask for an established source whose overview records `架构状态: 已确认`; reuse that architecture.
- Ask again only when a new season, module, volume, or substantially different source set changes the existing topology.
- One source-architecture confirmation covers extraction, source-note creation, authorized in-zone synthesis, maps, and status refresh. It does not authorize taking unselected learning content into the creative zone. Downstream skills must not repeat it. It does not initiate personal learning or authorize saving a learning result.

## Library categories

Keep these six professional categories as `分类` and professional indexes, not physical storage folders. Physical placement follows `references/library-layout.md`; do not create a new professional category without asking the user.

1. `故事与剧本`
2. `导演与视听语言`
3. `摄影美术与现场制作`
4. `声音与后期`
5. `创作实践与项目复盘`
6. `行业观察与灵感素材`

Record unresolved fragments in the existing inbox. Intact mixed or uncertain learning syntheses belong in `学习区/综合整理` until the user selects specific knowledge for creative use.

## Knowledge system layers

- **Source layer**: preserve course, episode, book, article, and transcript-derived context in the purpose-selected zone; professional source notes may live under a creative role.
- **Knowledge layer**: organize reusable conclusions by creative problem inside topic notes; keep concepts, methods, cases, counterexamples, and limits together until repeated use justifies splitting.
- **Application layer**: record how a topic was used in a screenplay, shot, scene, prompt, edit, or production decision and whether it worked.
- **Navigation layer**: use the library home, category maps, Dataview views, and Tasks queues to surface what needs extraction, review, validation, or revision.

Source notes can be the completed deliverable for learning intake; further synthesis depends on the requested purpose, not the fact that a source exists. See `references/knowledge-system.md` for the V2.1 schema, lifecycle, split rules, link contract, and maintenance rhythm.

Build the navigation layer around the user's North Star and knowledge completeness. Use creative-role and learning zones as the storage axis; retain professional categories as properties and indexes, then add `适用阶段`, `解决问题`, `关联项目`, evidence, and horizontal capabilities as retrieval axes. Projects remain application and validation branches rather than the homepage's primary organizing principle.

## Content-guide rules

Divide by changes in topic, claim, method, example, or argument; never cut mechanically only by duration.

- Under 10 minutes: usually 30 seconds to 2 minutes per detailed segment.
- 10–60 minutes: usually 2–5 minutes per detailed segment.
- Over 60 minutes: create coarse chapters, then 3–8 minute detailed segments.
- Articles and blogs: use headings and semantic transitions.
- Books: use chapters, sections, edition details, and page ranges; usually 3–10 pages per detailed segment.

For every detailed segment include:

- what it mainly covers;
- the substantive points needed to understand the segment; no fixed point-count cap;
- a replay or reread cue when useful;
- related `[[topic links]]` when they genuinely exist.

Write `整体脉络` as a medium-detail route map, not a thin table of contents. Each bullet should include the location or time range, the key teaching or argument move, and why that move matters for the user's learning. For a normal 20-60 minute lesson, use 4-7 bullets; each bullet should be one concise sentence or two short clauses. Keep full examples, case detail, and interpretation in the detailed guide or knowledge section.

## Short versus long material

- Use the routing matrix in `references/source-routing.md`; duration alone is only a complexity signal.
- Default structured courses to lesson-level grouping, not one giant note and not one note per media file.
- Default a single interview, conversation, podcast episode, article, paper, or independent video to one source note.
- Default same-topic fragments to one rolling source note; use `主题直融` only for a compact, explicit claim the user asks to place directly in the knowledge tree.
- Link source sections to the topic notes where knowledge was deposited, and do not duplicate the full source guide in every topic note.

## Output language and source display

- Write in Chinese by default.
- Preserve the original term once on first mention, for example `场面调度（mise-en-scène）`.
- For each source show only the title, a short introduction, clickable Markdown source link, source type, completeness, and reliability information.
- Render source links as Markdown links in the note body, never as naked URLs. Prefer labels such as `[打开原视频](https://...)`, `[课程页面](https://...)`, or `[P15 标题](https://...)` so a click in Obsidian opens the source page.
- Do not place full transcripts or raw source files in the final knowledge library.

## Plugin-Friendly Output

Write notes as structured Markdown that remains readable without plugins but works well with Obsidian Properties, Dataview or Bases, Tasks, Excalidraw, Advanced Tables, Linter, Omnisearch, and Chinese word splitting.

Required YAML properties for all final notes:

```yaml
类型:
分类:
状态:
材料类型:
信息来源:
完整程度:
整理日期:
```

For every newly created or substantially upgraded note, also include:

```yaml
知识库版本: 2.1
```

Legacy notes and V2 notes remain valid until their content is substantially edited; a path-only migration does not authorize batch schema upgrades.

For metadata-only organization that must preserve an old body exactly, use `项目资料`, `工具资料`, or `个人思考`. Add only the common classification properties and keep the original heading hierarchy and prose unchanged. These preserved legacy types are navigation sources, not V2 topic notes.

For topic notes also include:

```yaml
主题域:
解决问题:
适用阶段: []
来源材料:
关联项目:
知识状态: 已提炼
成熟度: 种子
上位主题: []
相关主题: []
最后复核: YYYY-MM-DD
证据状态: 单一来源
横向能力: []
```

For source overviews and episode notes also include relevant source fields plus:

```yaml
笔记架构: 课程分层 / 系列分层 / 章节分层 / 单篇材料 / 主题直融
聚合单位: 课 / 章 / 集 / 单篇 / 主题
架构状态: 已确认
适用阶段: []
沉淀状态: 未沉淀
已沉淀主题: []
待沉淀主题: []
```

Require these architecture fields on every newly created source note and every source overview or grouped note substantially updated after this workflow change. Leave legacy note schemas compatible; physical relocation alone does not require adding architecture fields.

Only add `涉及分类` after a confirmed cross-category semantic relationship; it must contain the topic's own `分类` and every category represented in `### 跨域连接`. Same-category relationships never create this property.

Project-application schema and writeback belong only to `apply-film-knowledge`; do not duplicate or locally recreate its template.

Learning fields and sections are optional extensions, not requirements for knowledge storage. Do not generate self-tests, review tasks, an empty personal-understanding section, or first-person claims on the user’s behalf. Preserve existing personal content. Author-taught exercises belong to source knowledge and retain their attribution; they are not automatically user assignments. Keep useful summaries, navigation and source locations. Dataview is a helper view; static links and normal headings remain the durable source of truth.

Only place a wikilink in `已沉淀主题`, `来源材料`, `相关主题`, or正文 when its target note exists and contains useful content. Cross-category `相关主题` additionally requires a user-confirmed typed relationship and reciprocal writeback through `weave-film-knowledge-connections`. Keep unwritten candidates as plain text in `待沉淀主题` or as `#待沉淀` tasks.

## Cache rules

- Store video, audio, OCR, ASR transcripts, subtitles, frames, working coverage records, and temporary downloads under the configured `raw_cache`, outside the Vault. Adopted compact review records belong to configured `source_evidence` under [durable-source-evidence.md](references/durable-source-evidence.md); do not copy raw source media into that durable store.
- Never store cookies, credentials, or authentication exports in the cache.
- Never delete cache automatically. The recurring check reports size every 14 days and asks the user before cleanup.
- Use `scripts/cache_report.py` to calculate cache usage.

## Validation

Before completion verify:

- source notes state material acquisition, actual content-review scope, and unresolved evidence separately under their existing source information section;
- source-to-inventory-to-note and note-to-source semantic review has been performed for the claimed scope; distinctive examples, qualifiers, and prior unique content remain represented;
- the coverage record is bound to current source/note bytes and checked through `scripts/check_source_coverage.py`; structural `OK` and closed registrations are not semantic completeness or a coverage percentage;
- adopted durable review records pass `scripts/audit_source_evidence.py`; missing cached originals remain an explicit inability to reverify, not a reason to discard history or certify new content;

- Chinese YAML properties use `类型`, `分类`, and `状态`;
- YAML properties include `材料类型`, `信息来源`, `完整程度`, and `整理日期`;
- exactly one H1 exists;
- no duplicate H2 headings exist;
- every material has a title, short introduction, and clickable Markdown source link or explicit local-source path;
- long media has both overall and detailed guides;
- key claims have timestamps, page ranges, section anchors, or source labels where available;
- external supplements, source links, retrieval date, reliability, disagreement, and uncertainty are visibly labeled;
- personal interpretation is not presented as the author's claim;
- useful summaries and concepts are retained as knowledge content; no personal learning tasks or records are invented;
- V2.1 source notes record `沉淀状态`, actual deposited topics, and unwritten candidates separately; existing optional learning fields remain valid and are not changed by ordinary ingestion;
- newly created or substantially updated source notes record a valid `笔记架构`, `聚合单位`, and `架构状态: 已确认`;
- V2.1 topic notes contain a core proposition, applicability boundary, structured knowledge units, `证据状态`, and a project-validation area;
- new topics do not require mastery fields or a learning-record placeholder; explicit learning writeback validates any added state against the actual user response;
- confirmed formal topic links are reciprocal and contain type, reason, and basis in `### 同类知识连接` or `### 跨域连接` as appropriate;
- confirmed cross-category topic links additionally contain conditional, consistent `涉及分类`; same-category links do not create it;
- the home view starts from the user's North Star, current learning focus, branch coverage, pending understanding, and evidence gaps;
- actual source-to-topic links are bidirectional and do not point to empty placeholder notes; learning-only intake does not require a new creative topic;
- raw artifacts remain outside the final library.

## Done / Partial / Stop

- **Done**：已确认的来源架构被正确复用或写入；来源本身可追溯；实际发生的主题沉淀双向可追溯且有实质内容，学习入库不以进入创作区为完成条件；校验和系统审计通过；需要的内化、调用、关系或运行维护已单向交接。
- **Partial**：材料不完整、证据不足、只完成部分沉淀或下游交接尚未执行；明确列出完成范围与缺口，不报告全部完成。
- **Stop**：新来源架构未确认、目标分类或拆分方式需要用户选择、来源不可访问且不能可靠补证、目标会造成空主题/假链接，或验证失败。停止后续 Vault 写入。
