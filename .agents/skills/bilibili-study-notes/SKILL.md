---
name: bilibili-study-notes
description: Extract and summarize Bilibili public courses or lectures into detailed, ordered, plugin-friendly Obsidian source notes. Use when the user provides a Bilibili URL, BV link, or multipart course; asks to read, transcribe, summarize, expand, organize, or update Bilibili notes; needs subtitle or audio-transcription fallback; or wants source artifacts kept out of the final vault. Hand authorized in-zone topic fusion to grow-creative-library, formal relationships to weave-film-knowledge-connections, knowledge use or project feedback to apply-film-knowledge, and maps or status to operate-personal-knowledge-tree.
---

# Bilibili Study Notes

## Overview

Turn one video or a multipart Bilibili source into detailed Chinese Obsidian notes for the active vault. Before extraction, use the source-architecture gate from `grow-creative-library`; then preserve source traceability, keep extraction artifacts out of final notes, and produce notes that work well with Obsidian Properties, Dataview or Bases, Tasks, Excalidraw, Advanced Tables, Linter, Omnisearch, and Chinese word splitting.

## Location Contract

- Read `vault`, `source_notes`, `knowledge_library`, and `raw_cache` from the discovered portable `.codex/knowledge-tree.json` through the shared loader in `operate-personal-knowledge-tree`.
- Follow the shared [zone contract](../grow-creative-library/references/library-layout.md). With zone configuration, courses go under `source_notes/课程`, personal interviews and independent learning topics under `source_notes/访谈与专题`; purpose-selected professional sources may go under a creative role. Learning summaries remain in learning unless specific knowledge is selected for creation.
- Extraction artifacts default to `raw_cache\bilibili`, which the shared loader requires to be inside the workspace and outside the vault.
- Only `KNOWLEDGE_TREE_CONFIG` may select another complete configuration. Explicit `--out` still overrides the JSON default, but the script resolves it first and fails closed if it equals or falls anywhere inside the active vault.

Use the cache for `metadata.json`, `transcript.md`, `subtitle.json`, `audio.m4s`, frames, and other raw artifacts. Final course folders must contain only Obsidian-facing Markdown notes unless the user explicitly asks to retain raw files there.

## Core Workflow

1. Identify the BV ID, requested `p=` page numbers, visible title, page titles, course or series name, target vault, source folder, topic library, and cache folder. Respect every explicit page number.
2. Inventory existing notes before editing. Read any recorded `笔记架构`, `聚合单位`, and `架构状态`, plus filenames, YAML properties, index links, prior content, and whether the user wants Chinese-only output.
3. Before full extraction, invoke the `grow-creative-library` source-architecture gate. Recommend one of `课程分层`, `系列分层`, or `单篇材料`, identify the semantic aggregation unit, and include the purpose-selected zone/role plus professional category. Already explicit architecture and destination count as confirmation. Do not download full media, run ASR, draft final notes, or mutate the vault until confirmed. Reuse an established `架构状态: 已确认` without asking again.
4. After confirmation, run `scripts/bilibili_extract.py` for each requested page. Its default output is the configured `raw_cache\bilibili`; never write extraction artifacts to the final source folder.
5. Prefer usable Bilibili or supplied subtitles. An empty downloadable-subtitle list does not establish whether subtitles are embedded in the picture; an inaccessible API does not establish absence either. With `--transcribe`, unavailable or empty subtitle text falls back to public audio and local multilingual `base` ASR. ASR output remains an unverified transcription.
6. Before writing, use the shared [source-content contract](../grow-creative-library/references/accuracy-and-merging.md): inventory substantive points from the source, preserve reasoning and distinctive examples, then perform both directions of review. Check whether knowledge depends on pictures, edits, demonstrations, or sound; inspect the relevant original media when required and obtainable through the permitted extraction tools. For doubtful ASR words, embedded captions or diagrams, follow [按需核对原画面与转写](references/media-evidence.md). Keep raw evidence outside the Vault and explicitly report unseen/unheard or damaged portions. Transcripts and explanatory redraws do not prove that original visuals were inspected.
7. For a structured course, first map requested pages to real lessons or modules. Create `00 - 课程总览.md`, one grouped `分集笔记` per semantic lesson using `assets/lesson-note-template.md`, and a unified course knowledge summary using `assets/course-knowledge-summary-template.md` only when real cross-lesson knowledge exists. Multiple pages may belong to one lesson; one page is not automatically one note.
8. For an independent video, interview, conversation, roundtable, or podcast episode, create one source note using `assets/episode-note-template.md`. For a stable multi-episode interview or podcast series, create a series overview and one note per independent session.
9. A complete learning source note is a valid deliverable. After writing, hand any authorized in-zone synthesis to `grow-creative-library`; Bilibili does not own topic fusion. Do not automatically deposit course knowledge into creation; the user must select specific knowledge first. Do not automatically hand off to internalization or generate a course question. Learning is user-initiated; saving a learning result needs an explicit request. Hand maps and status to `operate-personal-knowledge-tree`. A skipped answer never blocks completion, and formal relationship proposals wait until `知识收尾` and are owned by `weave-film-knowledge-connections`.
10. Prepare candidate knowledge units as concepts, principles, methods, cases, boundaries, and open questions for that grow handoff. Grow owns problem-based search, authorized topic writes in the selected zone and reciprocal source links; Bilibili does not perform a second deposit pass.
11. Use wikilinks only for topic notes that exist and contain useful content. Keep unwritten candidates as plain text in `待沉淀主题` or `#待沉淀` tasks. Do not create a row of hollow topic links.
12. If an existing note is present, follow the semantic merge rules below. Never replace it wholesale or append a visibly separate old/new copy.
13. Validate requested-page assignment, page order, links, YAML properties, heading uniqueness, final-folder cleanliness, Tasks/Dataview compatibility, and source-to-topic traceability. Separately perform semantic content review and the read-only [coverage registration check](../grow-creative-library/references/source-coverage-check.md); a course's P assignment and a note's structural OK do not prove all examples and arguments were preserved.

## Script Usage

From the skill directory:

```powershell
python .\scripts\bilibili_extract.py "https://www.bilibili.com/video/BVxxxx?p=2" --transcribe --model base
```

Useful options:

- `--page N`: override the video page/episode when the URL lacks `p=`.
- `--out DIR`: explicitly override where extraction artifacts are written. Without it, use configured `raw_cache\bilibili`; a path inside the active vault is rejected before any network request or directory creation.
- `--transcribe`: enable local ASR fallback when subtitle text is empty or subtitle access fails.
- `--model MODEL`: defaults to multilingual `base`, suitable for Chinese. `base.en` is English-only and rejects an explicit non-English language. A larger model is an optional comparison when actual errors justify it; do not automatically download a new model or treat size as proof of accuracy.
- `--language LANG`: specify the known ASR language, for example `en` or `zh`; omit for detection. Specified language is labeled separately from detection, and a detected-language probability is not transcription accuracy.
- `--clip START,END`: one finite nonnegative time range with START < END, for example `0,180`. The output is marked partial. ASR processes that interval; subtitles retain overlapping whole cues with their original timestamps, so boundary cues can extend slightly beyond the interval. This option does not limit the audio download to that interval.

The script writes:

- `metadata.json`: source identity, metadata route, subtitle access state, extraction status, transcript source and full/partial processing scope. Processing scope is not a content-completeness verdict.
- `transcript.md`: subtitle text or ASR transcript with timestamps.
- `audio.m4s`: audio stream when subtitle fallback is needed.
- `subtitle.json`: raw subtitle payload when Bilibili subtitles exist.

Re-running the same page creates a new attempt directory when the original page directory already exists. Use the returned `out_dir`; do not assume a fixed path or combine an old transcript with a new attempt's audio or metadata. Failed attempts remain separate and do not replace earlier source packages.

When an original diagram or embedded caption is needed, use `scripts/bilibili_media_excerpt.py` for a bounded video-only excerpt and timestamped preview frames. It requires existing `ffmpeg`/`ffprobe`, creates a new directory inside configured `raw_cache`, and never substitutes a full-video download when a byte range fails. Read [media evidence](references/media-evidence.md) for usage and limits. Generated images must actually be viewed before recording visual findings.

After grouped course notes are written, validate cross-note page assignment:

```powershell
python .\scripts\validate_course_structure.py "<实际课程目录>" --expected-pages "5-19"
```

This check requires `00 - 课程总览.md`, verifies every课级笔记's `P` and `包含P`, detects duplicated or missing pages, and confirms that the overview links every lesson note.

For structured courses, process pages in numeric order and use zero-padded real lesson or module prefixes:

```text
{source_notes}/课程/
  课程名称/
    00 - 课程总览.md
    01 - 第一课 课名（P1-P3）.md
    02 - 第二课 课名（P4-P5）.md
    课程名称.md
    ...
```

The final filename count follows semantic lessons, not requested page count. Independent videos may remain one file per video.

## Plugin-Friendly YAML

Every final note must start with YAML properties.

Required for all final notes:

```yaml
类型:
分类:
状态:
材料类型:
信息来源:
完整程度:
整理日期:
```

Additional course and episode fields:

```yaml
笔记架构: 课程分层 / 系列分层 / 单篇材料
聚合单位: 课 / 集 / 单篇
架构状态: 已确认
课程:
分集:
包含P: []
主题:
BV:
P:
知识库版本: 2.1
适用阶段: []
沉淀状态: 未沉淀
已沉淀主题: []
待沉淀主题: []
```

Additional topic-note fields when depositing reusable knowledge:

```yaml
主题域:
来源材料:
关联项目:
证据状态: 单一来源
横向能力: []
```

Use Chinese property names exactly so Properties, Dataview, Bases, Omnisearch, and Linter can operate consistently.

## Final Note Forms

### 课程总览

Use as the navigation surface for a structured course. It must include:

- course/source intro and reliability boundary;
- a course matrix ordered by real lesson or module, with each lesson's `包含P`, problem, and note link;
- a one-sentence guide for every requested P under its owning lesson, so both “每课讲什么” and “每集讲什么” are visible without opening detailed notes;
- a Dataview table that lists starting `P`, `包含P`, `分集`, `主题`, `状态`, `信息来源`, and `完整程度`;
- learning queries only when explicitly requested, never as a default source-note requirement;
- a stable link to the unified course knowledge summary when that non-empty note exists;
- links to topic notes where reusable knowledge was deposited.

Do not duplicate detailed timelines or full examples in the course overview. Its job is navigation.

### 课级笔记

Use one grouped `分集笔记` for each real lesson or module. Keep `P` as the starting page for sorting and list every page in `包含P`. It must include:

- a Markdown video link for every included P, never a naked URL;
- source reliability and transcript/subtitle completeness;
- `## 本课速览`;
- `## 分集脉络`, with one concise line explaining each included P's role;
- `## 时间线笔记`;
- `## 核心观点`;
- `## 方法与案例`;
- any exercises actually taught by the speaker, attributed within the method content;
- `## 主题沉淀`;
- useful summaries when they add reading value;
- source locations for important examples and claims.
- no default learning fields, review assignments, or empty personal-learning sections; preserve any existing personal records.

Do not split a lesson merely because it spans several P values. Conversely, do not merge independent lessons only to reduce file count.

### 单篇或单集笔记

Use `assets/episode-note-template.md` for an independent video, interview, conversation, roundtable, podcast episode, or other self-contained page. It keeps `笔记架构: 单篇材料` and `聚合单位: 单篇`, with one timeline and the same source-fidelity contract; importance does not require a learning question.

### 统一知识总结

Use one non-empty summary for reusable knowledge that crosses lessons. It keeps frameworks, methods, comparison tables, case indexes, workflows, exercises, and links to lesson notes. It must not repeat the lesson-by-lesson timeline or detailed speaker examples. Do not invent a course-level learning question; retain questions raised by the source as attributed knowledge.

Reuse a confirmed source architecture; ask only when the architecture decision is still genuinely missing. Complete source notes and authorized in-zone synthesis without assigning personal study tasks or automatically moving learning knowledge to creation. The user can later select any note for explanation or testing; neither a discussion nor an answer authorizes learning writeback.

In `## 主题沉淀`, separate `已沉淀` from `待沉淀`. When topic fusion is authorized, a normal episode should update at most 1-3 topic notes within the chosen destination. Prefer keeping related concepts, methods, cases, and boundaries inside one useful topic note until repeated sources or project use justify splitting.

### 主题笔记

Hand authorized source-note synthesis to `grow-creative-library`, which owns V2.1 topic fusion by problem or method rather than source order. Courses and personal-learning materials stay in the learning zone; only user-selected specific knowledge enters creative topics, with its original learning source retained. Grow links the episode or course as a source card and records evidence, lifecycle and maturity while keeping personal interpretation separate from source claims. Bilibili never writes project feedback; when the user explicitly requests a real-use record, hand it to `apply-film-knowledge`. Use `internalize-film-knowledge` only for a user-initiated learning request; saving demonstrated mastery additionally requires an explicit request to save the result. Leave all formal relationship discovery to `weave-film-knowledge-connections` at closeout and never write a connection before its preview is confirmed.

## Semantic Merge Rules

Treat existing user notes as content to preserve.

1. Parse the existing note and the expanded material by meaning, not only by exact heading text.
2. Merge content into one reading flow:
   - problem or purpose;
   - course outline;
   - timestamped notes;
   - core ideas and key concepts;
   - methods, examples, and case analysis;
   - author-taught training methods as source content, and previously adopted exercises when present;
   - topic deposits;
   - existing personal learning records, without inventing new reminders;
   - useful existing source-location cues, without assigning a rewatch task.
3. Move prior material into matching sections. For example, merge `可操作方法` and source-taught training into `方法与案例`, and place an earlier `时间线笔记` after `课程脉络`.
4. Preserve unique prior details, timestamps, questions, and personal notes. Deduplicate exact repetitions and obvious paraphrases, keeping the clearer or more complete wording.
5. Keep one title, one source line, one accuracy note, and one instance of each section heading.
6. Never leave labels such as `旧版`, `新版`, `原有笔记（保留）`, or a second complete note below a divider unless the user explicitly requests version archives.
7. Do not delete existing content merely because the new version is more detailed. If two statements conflict, keep the uncertainty visible and check the transcript or video.

## Obsidian Output Rules

- Create `00 - 课程总览.md` with static lesson links ordered by real lesson or module, and list each requested P once under its owner.
- Add a Dataview table to the course overview when Dataview is available; keep static links so the note remains useful without plugins.
- Use zero-padded lesson prefixes so filesystem and Obsidian sorting remain stable.
- Write source video URLs in Markdown link form, never as naked URLs in the note body. Prefer `视频：[打开原视频](https://...)` for single-episode notes, or `[P15 标题](https://...)` when listing multiple sources.
- If the user requests Chinese-only notes, keep only Chinese Markdown notes. Do not create an English duplicate.
- Keep transcripts, audio, metadata, subtitles, frames, and temporary downloads in configured `raw_cache\bilibili`.
- Follow the shared [原材料保留与按需盘点](../grow-creative-library/references/durable-source-evidence.md#原材料保留与按需盘点) rules: retain acquired source inputs, used transcripts, corrections and review evidence; do not infer deletability from cache location or a live URL, download additional full videos just for archiving, or ask for repeated retention confirmation. Inventory is on request and does not delete files.
- Preserve unrelated user files and changes.
- Use relative Obsidian links from the course index.
- Set `沉淀状态` to `未沉淀`, `部分沉淀`, or `已沉淀`; update it only after the corresponding topic content and bidirectional links exist.

## Validation

Before reporting completion, verify:

- The source explanation separates actual material acquisition, content-review scope, and unverified parts; do not label an ASR-only or partially sampled visual review as whole-video verification.
- Distinctive cases retain their context, choices and explanatory result; hypotheses remain hypotheses and editor additions are labeled. Compare source→inventory→note, note→source, and the previous note→updated note using the shared content contract.
- Current source and note hashes match the coverage record; unregistered, pending or unresolved items are reported without claiming semantic completeness. Existing notes without this record stay compatible until actually revised; do not batch-migrate them.

- Every requested P is assigned to exactly one semantic lesson or independent note; no P is missing or duplicated.
- Run `scripts/validate_course_structure.py` for every structured course update, with the requested page set supplied through `--expected-pages`.
- Lesson files, `P`, `包含P`, overview links, and source links are in numeric order.
- The number of lesson notes matches semantic lessons, not requested page count.
- Every final note has YAML properties required for its type.
- Every grouped lesson note has `笔记架构: 课程分层`, `聚合单位: 课`, `架构状态: 已确认`, starting `P`, complete `包含P`, and a Markdown source link for each included page.
- Every independent note has the correct architecture fields, Markdown source link, and `p=` value when applicable.
- No final Markdown note contains `视频：https://` or another naked source URL.
- Existing unique content remains represented after an update.
- No note contains a separate appended old/new version.
- Each note has one H1 and no duplicate H2 headings.
- `分集笔记` contains `P` and `## 时间线笔记`; a grouped lesson also contains `包含P` and `## 分集脉络`.
- V2.1 source notes contain `沉淀状态`, `已沉淀主题`, and `待沉淀主题`; optional existing learning fields remain compatible and are not reset.
- New topic notes need no mastery fields or empty learning records; explicit learning writeback follows `internalize-film-knowledge` and preserves personal content.
- Every link in `已沉淀主题` resolves to a non-empty topic note that links back to this source.
- Candidate themes that have not been written are plain text, not hollow wikilinks.
- Chinese-only output contains no parallel English note.
- Final episode folders do not contain `metadata.json`, `transcript.md`, `subtitle.json`, `audio.m4s`, frames, or other raw artifacts.
- Markdown is valid UTF-8 and readable in Obsidian.

## Fallback Guidance

- If `x/player/v2` returns no usable subtitle text, use authorized ASR fallback and inspect relevant pictures when embedded captions or visual teaching matter. API failure is recorded as unavailable, not as zero subtitles.
- On metadata API HTTP 412 or code -412, the bundled script can read the same public page's `__INITIAL_STATE__.videoData`; it accepts only the requested BV, a unique page and a valid CID. If that public identity is unavailable, stop rather than guessing another page or bypassing login/access requirements.
- A short `--clip` run checks the selected interval only. Compare doubtful content with the actual source; a nonempty transcript or successful exit is insufficient.
- For Chinese or bilingual material, use multilingual `base`; specify `--language zh` only when that matches the actual speech. Preserve the original transcript and record corrections with their evidence and time locations.
- Keep outputs as personal derived study notes and avoid reproducing full transcripts in the response.

## Done / Partial / Stop

- **Done**：请求页全部完成提取与语义分组，最终来源笔记通过结构校验，原始产物只在 Vault 外缓存，已授权的来源到主题交接可追溯；学习来源不以进入创作区为完成条件。
- **Partial**：只取得部分页、字幕/ASR 质量有限、已授权的部分语义单元未沉淀或下游交接尚未完成；明确列出范围与缺口。
- **Stop**：来源架构尚未确认、`--out` 指向活动 Vault、目标页不存在、字幕和音频均不可用，或结构校验失败。停止后续写入，不把原始产物放进最终来源目录。
