---
name: operate-personal-knowledge-tree
description: Coordinate and maintain the user's personal Chinese Obsidian film-creation knowledge tree. Use for named control workflows such as 开始学习, 开始整理知识树, 把这条知识放进知识树, 知识收尾, 今天先到这, 知识树周复盘, 修改我的北极星, 备份知识树; for branch routing, maps, lifecycle queues, status surfaces, Obsidian health checks, and confirmation boundaries. Do not use as the source-extraction, topic-fusion, knowledge-retrieval, mastery-test, or relationship-writing worker; hand those to their dedicated Skills.
---

# Operate Personal Knowledge Tree

## Purpose

Operate the knowledge system around the user rather than around a generic curriculum or a production project. Codex acts as knowledge mentor and researcher: preserve sources, help the user understand them, connect reusable knowledge, expose gaps and disagreements, and support learning when the user requests it.

## Location Contract

- The only machine-readable location source is the discovered `.codex/knowledge-tree.json` at the portable workspace root.
- Load it with `scripts/knowledge_tree_config.py`; never embed a vault, library, source, cache, prompt-box, or Obsidian CLI default in another file.
- Portable `version: 2` configurations use workspace-relative paths and include `skills_root`; complete absolute `version: 1` configurations remain read-compatible only.
- Only `KNOWLEDGE_TREE_CONFIG` may select another complete configuration. Missing, ambiguous, nonexistent, absolute v2, or boundary-breaking paths fail closed without a fallback target.
- Explicit command arguments remain valid and override JSON defaults, but Obsidian operations must first resolve `vault_name` from Obsidian's registered-vault metadata and compare it with the selected vault path before launching the CLI; the CLI result is then checked a second time.
- Control notes live under `knowledge_library\00-待归档与知识地图`; six professional maps live in its `专业索引` subfolder. Read [the shared zone contract](../grow-creative-library/references/library-layout.md) for creative roles, learning placement and old-config compatibility.

Read `我的知识树北极星.md`, `知识树状态.md`, and the relevant category map before substantial work. Read `references/operating-contract.md` for the V2.1 schema, lifecycle, branch scaffold, and ranking rules.

## 全局背景与当前任务

- 当前用户任务最高优先。不得把另一个任务的完成、等待或下一步覆盖本次目标，也不把本次对话目标自动写成全局待办。
- `知识树状态.md` 的 `## 已确认的全局待办` 与 `## 待选择的全局事项` 是行动状态的唯一事实源；两表均为 `标识 | 事项 | 依据`。没有已经采用的事项时保留空表并说明暂无，不能将历史建议自动移入已确认表。
- 用 `scripts/knowledge_tree_state.py` 的 `read_state` 共同读取全局表、北极星及只读当前任务参数。主页嵌入状态页章节；启动上下文与周复盘从同一函数读取背景，仅在明确请求学习建议时选题，不另维护“当前唯一行动”。解析失败明确报告，不能静默当成空队列。
- `--current-task`、`--source`、`--blocker`、`--learning` 只描述当前调用；不会写回全局状态。`learning_requested=False` 为默认，普通启动、入库、收尾和周复盘不调用选题器；只有用户明确请求学习建议才传 `--learning`，单独指定 `--source` 不等于学习请求。来源须明确选中，阻塞须与当前任务相关。系统建议始终标为未采用，普通提问或任务切换不更新全局事项。
- 来源证据、知识成熟度、用户掌握、项目效果分别统计。多源互证不算成熟度稳定；分类篇数少与语义孤岛不是自动补缺依据。

## Skill Boundaries

- Use `bilibili-study-notes` to extract Bilibili metadata, subtitles or ASR and write source notes.
- Use `douyin-study-notes` for `douyin.com` or `v.douyin.com` links, then return its completed source evidence to `grow-creative-library` for collection or authorized synthesis in the selected zone.
- Use `grow-creative-library` to organize source material and authorized topic knowledge within its destination. Learning intake does not automatically deposit into creative topics.
- Let `grow-creative-library` own the source-architecture gate for every new “summarize and put into Obsidian” request. This skill must not create source notes, topic deposits, maps, or status updates until that architecture is explicitly confirmed or reused from `架构状态: 已确认`.
- Use `internalize-film-knowledge` for user-requested explanation, discussion or understanding checks. Explain a stated confusion directly; test only when requested, and save understanding or mastery records only with explicit writeback authorization.
- Use `weave-film-knowledge-connections` to discover, preview, confirm, and audit all typed formal topic relationships.
- Use `apply-film-knowledge` to retrieve and read the knowledge needed for the current creative problem and to record explicitly authorized practice feedback; its current review contract determines the reading scope.
- Use this skill to choose the branch, track evidence and lifecycle queues, maintain navigation, conduct session closeout, and run weekly review.
- Never recurse between skills. Complete the worker skill, then apply authorized in-zone organization and state updates once.

## Operating Workflow

1. Load the North Star and current tree status.
2. When the turn introduces a new source, check for an explicit architecture or an existing source note with `架构状态: 已确认`. If neither exists, hand off to the `grow-creative-library` gate and stop all downstream writes until the user confirms once.
3. Identify the active professional branch and creative problem. Current focus is `故事与剧本`; all six categories remain professional properties and indexes. Determine creative-role or learning placement by the current purpose, not by the category name.
4. Search existing titles, aliases, core propositions, properties, and content before creating a note. Use `scripts/obsidian_cli.py`; when Obsidian is installed, local fallback is allowed only after target validation and never hides a mismatch. When Obsidian is absent, the wrapper permits only configuration-bounded local Markdown search and blocks all Obsidian-dependent writes.
5. Route clear reusable knowledge into an existing topic within the authorized zone when possible. Learning materials stay in learning unless specific knowledge is explicitly selected for creation. Route unclear fragments to `知识树收件箱.md` with source, candidate branch, uncertainty, and one question.
6. Finish source preservation and knowledge deposit without adding learning tasks, question queues or empty personal-understanding sections. Preserve source-taught exercises as knowledge and retain existing personal records. Hand off to `internalize-film-knowledge` only when the user asks to learn; learning stays in the conversation unless saving is explicitly requested.
7. Keep source claims, external research, Codex synthesis, and the user's understanding visibly separate. External research may proceed when local evidence is insufficient, but must show links, date, reliability, uncertainty, and disagreements.
8. Update only real links, lifecycle fields, the relevant map, and status surfaces. Do not create empty topic notes.
9. Validate changed notes and the knowledge-library scope before reporting completion.

## Named Workflows

### Back Up the Knowledge Tree

For `备份知识树`, load the unified config and run the workspace-level `scripts/backup.ps1 -Apply`. The configured private repository, branch and stable publication scope are already authorized; do not reconfirm them on each request. For a request to inspect only, use the default or `-Preview`.

- This is a system backup, so skip source architecture, learning selection, note editing and status writeback.
- The tool preserves a snapshot, pushes normally, restores from a fresh remote clone, and verifies before creating a `verified-backup-*` tag. Report the commit, tag and restore receipt; a push alone is not a completed backup.
- If source files change during snapshot, safety checks fail, or the remote has an unrecognized commit, stop this attempt and explain its recorded phase. Do not force-push, silently omit files, erase history or bypass validation.
- `-RestoreTest -Commit <full SHA>` restores only into a new cache directory and does not change the remote. Replacing the live workspace requires an explicit destination and authorization.
- Do not schedule backups or attach them to startup/closeout. Raw media and extraction caches are outside this backup. See the workspace `docs/故障恢复.md` for recovery and cold-start commands.

### Start Learning

For `开始学习` or `开始整理知识树`:

- distinguish learning from organizing: `开始整理知识树` does not request a lesson or review question;
- continue with the selected material or stated confusion; if the user asks what to learn next, use the shared reader with `--learning` to propose a supported target;
- report the relevant branch and current task without inventing a gap or assigning an exercise;
- load only the relevant map and notes, not the full vault;
- continue directly with the user's material.

### Add Knowledge

For `把这条知识放进知识树`:

- identify or reuse the already explicit learning/creative purpose and destination;
- search by problem and meaning within that destination;
- merge authorized ordinary additions directly; learning-only requests do not authorize moving knowledge to creation;
- use the inbox when the claim, source, or intended use is unclear;
- preview deletions, major restructuring, substantive conflict resolution, or North Star changes.

### Coordinate Internalization

For `我想理解 X`, `考考我`, `复习一下`, `我没听懂`, `我没理解`, or `继续理解`:

- route the turn to `internalize-film-knowledge`: explain or discuss a stated confusion; use at most one question only for an explicit check request;
- use its read-only selector only for an explicit learning-suggestion request without a named topic; do not treat a supplied source as that request;
- keep the exchange in conversation by default; save personal understanding, answers or mastery only after the user explicitly requests it;
- let `grow-creative-library` handle any evidence gap discovered during diagnosis;
- refresh status surfaces after a writeback, without asking a second question.

### Close the Session

For `今天先到这` or `知识收尾`:

- inspect only notes changed in this session;
- finish links and lifecycle fields;
- hand only changed topic notes to `weave-film-knowledge-connections`, which previews at most two high-confidence formal candidates and writes nothing where confirmation is required;
- record structural changes, not ordinary edits, in `知识树变更记录.md`;
- keep unresolved understanding questions as background; surface learning suggestions only when explicitly requested. Selecting a source for deposit or closeout is not a request to study it. Historical questions do not block closeout.

### Weekly Review

For `知识树周复盘`:

1. Run `scripts/weekly_review.py`.
2. Run the note validator and strict library audit.
3. Review unresolved links, orphans, dead ends, tasks, pending understanding, mastery counts, weak evidence, disagreements, formal same-category edges, formal cross-category edges, ordinary navigation hints, and semantic islands.
4. Update diagnostic snapshots only when requested in the authorized workflow; preserve the global action tables unless their exact changes have been adopted. Never save current-task parameters as a global action.
5. Keep learning inventories as diagnostics. Generate an unadopted learning suggestion only when explicitly requested, passing `--learning` to the shared state reader; ordinary weekly review does not select a question. A lack of supported candidates is valid; do not choose the branch with fewest notes.
6. Propose North Star changes separately and wait for confirmation.

## 新材料补查

来源入库和知识收尾后按 [新增材料补查](../apply-film-knowledge/references/incremental-followup.md) 执行，保存的检查点仅是 Vault 外运行状态。weekly_review.py 已加入只读补查摘要；有变化或未处理项时再取 --suggest 的详细阅读候选。创作区未沉淀专业来源也能供综合审查发现，但不会自动升级为主题。学习区来源不因补查或链接进入创作读取，须由用户本次点名并传 `--include-path`；学习整理可在自身授权范围内维护。未确认的正式关系继续交 weave 预览。

## Hook and confirmation boundary

Hooks are auxiliary reminders and after-the-fact checks. They are not a reliable write-before-approval gate and never substitute for explicit confirmation in the executing Skill.

Apply normal source creation, semantic merges, lifecycle updates, and map maintenance directly only after the source architecture is confirmed or reused. Require confirmation for an undecided new-source architecture or destination, changing an established source architecture, changing personal goals or preferences, the North Star, zone structure or professional classifications, deleting knowledge, resolving a substantive disagreement, performing a major reorganization, or writing, changing, or removing a cross-category topic relationship. Do not ask again when the current request already supplies the purpose, destination or architecture, or when `grow-creative-library` obtained that confirmation. Explicitly authorized migration follows its approved scope.

## Commands

```powershell
python .\scripts\obsidian_cli.py check
python .\scripts\obsidian_cli.py search "虚假胜利"
python .\scripts\weekly_review.py
python .\scripts\knowledge_tree_state.py --json
# 仅在用户明确请求学习建议时：
python .\scripts\knowledge_tree_state.py --learning --json
python .\scripts\weekly_review.py --current-task "本次用户明确的目标" --local-only --json
python .\scripts\knowledge_tree_runtime.py --context --current-task "本次用户明确的目标"
python ..\weave-film-knowledge-connections\scripts\audit_connections.py --strict
```

`--local-only` 仅读本地Markdown，不调用Obsidian或补查缓存；隔离候选和关闭的副本使用此模式或测试替身，不对它们调用真实Obsidian。

Validate the skill with the system skill creator's `quick_validate.py` under `PYTHONUTF8=1`.

## Done / Partial / Stop

- **Done**：目标控制流程完成，状态和地图只反映真实内容，相关 worker 已单向交接，严格健康检查通过。
- **Partial**：只完成路由、只读诊断或部分状态刷新；明确未完成的 worker、确认或验证，不报告全部完成。
- **Stop**：北极星/顶层结构/删除/正式跨域关系缺少确认，统一配置边界失败，worker 返回停止，或严格审计失败。Hook 不得绕过停止条件。
