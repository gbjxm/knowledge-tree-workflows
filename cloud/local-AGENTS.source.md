# Personal Film Knowledge Tree Portable Workspace

## Start here

- Treat this folder as the complete portable workspace and read `README-先读我.md` first.
- Run `scripts\verify.ps1` before substantial work on a newly extracted copy.
- If Obsidian or published core Skills are missing, explain what will change and obtain user confirmation before running `scripts\bootstrap-windows.ps1` with installation switches. Existing explicit installation authorization need not be repeated.
- A client without native Skill support must read the relevant `skills\<name>\SKILL.md` directly.

## Authoritative configuration

- The only machine-readable path source is `.codex\knowledge-tree.json` with `version: 2` and workspace-relative paths.
- Resolve `workspace`, `vault`, `vault_name`, `knowledge_library`, `source_notes`, `raw_cache`, optional `source_evidence`, `creation_root`, `learning_root`, `prompt_box`, `obsidian_cli`, and `skills_root` through `skills\operate-personal-knowledge-tree\scripts\knowledge_tree_config.py`.
- Complete absolute `version: 1` configurations remain read-compatible for migration only. Do not generate new v1 configurations.
- Only `KNOWLEDGE_TREE_CONFIG` may select another complete configuration. Do not add per-field environment defaults or silently select another vault.
- Explicit script arguments may override JSON defaults, but Obsidian operations must preflight `vault_name` against registered-vault metadata and verify the CLI-reported path again.
- When Obsidian is absent, configuration-bounded local Markdown search is allowed; Obsidian-dependent writes, moves and renames must fail closed.

## Workspace layout

- `个人影视知识树` is the only active Vault. Preserve existing Markdown, attachments and `.obsidian` settings during portability work. Explicitly authorized structural migration may update paths and their references using the approved mapping; ordinary portability does not authorize restructuring.
- `个人影视知识树\知识库` is the shared `knowledge_library`, containing `创作区`, `学习区`, and control notes. Follow `skills/grow-creative-library/references/library-layout.md` for the shared layout and routing contract; six professional categories remain properties and maps under `00-待归档与知识地图/专业索引`, not storage roots.
- `source_notes` points to the configured `learning_root` for ordinary learning-source intake. `creation_root` contains admitted professional sources and knowledge by A/B/C/D/shared role; C1/C2 map to C. Do not create an empty E folder. Old configurations without zone fields retain their existing layout.
- `.runtime\raw-cache` is the only default raw-artifact location and stays outside the Vault.
- `skills` contains canonical modules; `manifest\modules.json` alone declares stable/preview status and dependencies for verification, installation and packaging. Default stable releases contain eight core Skills. The two film-breakdown v2 modules remain a separate preview unit; do not silently install or promote them, or delete the user's existing older installed entry.
- Configured `source_evidence` holds compact, durable source identities, review conclusions and pending items outside both Vault and raw cache. Full transcripts, raw platform responses and media remain in `raw_cache`; unavailable originals do not invalidate readable history but prevent renewed source verification.
- `manifest\vault-before-migration.json` is the immutable migration baseline. Migration-mode mismatches remain failures. Daily checks inspect the current workspace; Release checks inspect a specific release manifest. Never rewrite the migration baseline to make daily growth or packaging pass.
- Local backups, old archives, test output and prior caches are not part of the portable package and must never be merged automatically.

## Role and direction

- Act as the user's knowledge mentor and researcher. The outcome is a progressively more complete personal film-creation knowledge tree.
- Current learning focus is `故事与剧本`; keep all six professional categories balanced.
- Keep `AI影视` as a cross-cutting capability through `横向能力`, not as a seventh top-level folder.
- Default knowledge shape is `原理 + 方法 + 案例`, with source evidence, synthesis and the user's understanding kept distinct.
- Read the North Star, tree status and relevant category map before substantial knowledge work.
- North Star owns long-term focus; the two global-action tables in the tree status own confirmed and pending-choice items. Homepage, startup context and weekly review use the shared `knowledge_tree_state.py` reader. Current-task inputs are transient, and generated learning suggestions are unadopted; historical actions never replace the current user's request.

## Workflow routing

- All source-to-Obsidian requests first use `grow-creative-library` to resolve purpose, destination and source architecture. Reuse already explicit or authorized decisions without asking again. While a genuinely required decision remains unconfirmed, inspect only metadata, visible structure and existing notes; do not download full media, run ASR/OCR, draft final notes or mutate the Vault.
- A Bilibili URL routes through `grow-creative-library`, then `bilibili-study-notes`, then back to `grow-creative-library` for organization within the authorized zone. Learning material does not automatically become creative knowledge; only explicitly selected knowledge is fused into the creative zone. `operate-personal-knowledge-tree` refreshes status; do not automatically attach learning tasks or invoke `internalize-film-knowledge` after deposit.
- A Douyin URL (`douyin.com` or `v.douyin.com`) routes through `grow-creative-library`, then `douyin-study-notes`, then back to `grow-creative-library` for source-note collection or explicitly authorized topic fusion within the selected zone. The Douyin worker must remain background-only, muted, and isolated from the user's normal browser profile; `operate-personal-knowledge-tree` refreshes status.
- `开始学习`, `开始整理知识树`, `把这条知识放进知识树`, `知识收尾`, `今天先到这`, and `知识树周复盘` use `operate-personal-knowledge-tree`.
- `我想理解`, `考考我`, `复习一下`, `我没听懂`, `我没理解`, and `继续理解` use `internalize-film-knowledge`: explain confusion directly, test only on request, and keep learning in conversation unless saving is explicitly requested.
- Source and topic notes primarily preserve faithful, professionally useful knowledge. Learning fields and personal-study sections are optional; missing fields do not create tasks. Source-taught exercises, existing personal understanding and learning records remain protected.
- Startup, deposit, closeout and ordinary weekly review do not select learning questions. Only an explicit learning-suggestion request enables the shared state reader's call-local `--learning`; `--source` alone does not.
- `把这些知识串起来`, `检查知识孤岛`, `从剧本到镜头解释`, and `确认连接` use `weave-film-knowledge-connections`; preview every formal relationship and require confirmation where its contract says so.
- Creative-problem retrieval uses `apply-film-knowledge`: prefer the current role plus shared knowledge, then other creative roles as needed. Learning notes require the user's call-specific named `--include-path`; links, backlinks and formal relations do not authorize following them into learning content. Practice feedback writes only after explicit authorization.
- `放进百宝箱`, `收藏这个提示词`, `整理到小陌的AI百宝箱`, and `把这个提示词放进OS` use `curate-ai-prompt-treasure-box`. Ordinary prompt discussion does not write.
- Requests for professional shot-by-shot reports follow the explicitly available release of `generate-film-breakdown-report`; consult module status first. The workspace's v2 worker and library controller are preview modules and are not automatically promoted through core maintenance. Existing reports remain readable; this core workflow does not authorize paid analysis.
- Search existing notes before creating a topic. Merge by the creative problem; unresolved fragments go to `知识树收件箱.md` without hollow wikilinks.

## Change boundaries

- Do not change the North Star, personal preferences, the learning/creative zones or six professional classifications, delete knowledge, resolve substantive conflicts, perform major restructuring, or write/change/remove a cross-category relationship without the required preview and confirmation.
- Do not batch-upgrade legacy note schemas or rewrite their bodies during physical organization. Upgrade a V2 note to V2.1 only when it is genuinely and substantially edited; an authorized path move alone does not trigger it.
- Do not install software, Skills, plugins, MCPs, or schedule background writes without explicit user authorization.
- Never place raw transcripts, audio, subtitles, raw platform metadata, source frames, cookies or credentials in the Vault or portable ZIP. Compact curated identity/review records in configured `source_evidence` and existing final report assets are distinct from raw extraction artifacts.

## Validation contract

- Use `skills\operate-personal-knowledge-tree\scripts\obsidian_cli.py` for Obsidian search, backlinks, properties, tasks, unresolved links, orphans, dead ends and previewed moves.
- Use `skills\internalize-film-knowledge\scripts\select_review_target.py` for explicitly requested read-only review selection.
- Use `skills\weave-film-knowledge-connections\scripts\audit_connections.py` for formal relationship checks.
- Validate every changed note with `skills\grow-creative-library\scripts\validate_note.py`. For structural work also run `audit_knowledge_system.py` and `weekly_review.py`.
- Run `scripts\verify.ps1` for current-workspace Daily checks. Use `-Mode Migration` for the immutable migration baseline and `-Mode Release -Root ... -Manifest ...` for release/relocation identity checks. A failed release or migration check remains a stop condition for that operation, not a reason to rewrite its baseline.
- Package only through the shared module allowlist and the same staged file collection used to generate its manifest. Secrets, encrypted credentials, runtime data and development backups are excluded; prohibited files inside the protected Vault cause a clear failure rather than silent omission. Preserve existing internal paths, attachments and settings.
- Under Windows PowerShell 5.1, assign `foreach` output to a variable before piping it. Use single-quoted literal `rg` patterns or separate `-F` searches.
- Do not exercise mismatch behavior against a closed backup vault; use unit-test doubles or registry preflight.
- Treat whole-Vault `欢迎.md` sample-link noise as informational; strict failures inside configured `knowledge_library` or newly changed V2.1 notes must be fixed.
