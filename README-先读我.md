# 小陌的影视知识树便携工作区

本工作区维护完整 Obsidian Vault、八个正式核心 Skills、两个拉片 v2 预览模块、统一配置和 Windows 工具。正式便携包默认包含八个核心 Skills、现有 Vault 内容与长期来源复核记录；预览运行代码另列，原始缓存、开发备份、账号和凭据不进入包。

此前体系优化的历史暂停状态、验证结果和接续步骤见[任务续接记录](docs/知识树体系优化-续接记录.md)。

## 在新电脑上使用

1. 将整个 `影视知识树` 文件夹解压到任意位置，中文路径和空格都受支持。
2. 用 Codex、WorkBuddy 或 Claude Code 打开这个文件夹；让 AI 先读取本文件、`AGENTS.md` 和 `CLAUDE.md`。
3. 先运行只读验证：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
   ```

4. 如果尚未安装 Obsidian，AI 必须先征得你的同意，再运行：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap-windows.ps1 -InstallObsidian -InstallSkills -OpenVault
   ```

5. Obsidian 启动后选择“将文件夹作为仓库打开”，目标是本目录中的 `个人影视知识树`。第一次启用社区插件时，按 Obsidian 提示确认信任。

如果不安装 Obsidian，AI 仍可以读取笔记、执行本地 Markdown 检索、调用知识、运行知识库审计。移动、重命名等依赖 Obsidian 链接更新的操作会被明确阻止。

## 知识库怎么组织

共同根为 `个人影视知识树/知识库`：创作区按 A-制片与协作、B-故事与剧本、C-导演与视觉、D-声音与后期、岗位共用归位，C1/C2合用C；学习区按课程、书籍、访谈与专题、综合整理、个人思考保存材料。六类专业名称保留为属性与 `00-待归档与知识地图/专业索引`，不再作为存储主轴。没有真实材料的岗位不建空目录。

课程和个人学习材料默认在学习区完成整理，不自动进入创作。用户选定具体知识后才转入相应创作岗位，并保留学习来源。默认创作调用先本岗与共用，再按需跨创作岗位；学习笔记仅在本次点名时通过 `--include-path` 加入，链接不扩张读取范围。完整归位和旧配置兼容规则见[分区契约](skills/grow-creative-library/references/library-layout.md)。

按原视频复核已有课程时，使用[课程来源复核流程](docs/课程来源复核流程.md)。已固定的信息取舍规则仍需结合每批实际声画证据验收；小样本文字测试不代表四门课全部通过。

已完成课程的完整转录、原音视频地址和新版正式笔记入口见[课程资料索引](docs/课程资料索引.md)。

## 正式核心 Skills 与预览模块

`manifest/modules.json` 是验证、安装和打包共用的模块清单。默认正式集合为以下八个核心 Skills：

- `operate-personal-knowledge-tree`：总调度、状态、地图、学习开始/收尾和周复盘。
- `grow-creative-library`：来源架构确认、知识融合、主题与地图维护。
- `bilibili-study-notes`：Bilibili 提取、字幕/ASR 与来源笔记。
- `douyin-study-notes`：抖音链接的后台静音提取、ASR 与来源笔记。
- `internalize-film-knowledge`：主动发起的讲解、讨论与理解检验；明确要求保存才写回个人理解或掌握记录。
- `weave-film-knowledge-connections`：正式知识关系预览、确认、双向写入和审计。
- `apply-film-knowledge`：按创作问题调用已有知识，明确授权后记录实践反馈。
- `curate-ai-prompt-treasure-box`：维护《小陌的AI百宝箱》。
- `generate-film-breakdown-report` 与 `operate-film-breakdown-library`：作为依赖闭合的拉片 v2 预览单元单独登记，本轮不自动安装或晋升；现有拉片笔记、报告和图片仍保留。本机已有旧拉片入口不因核心更新而删除。

不支持原生 Skills 的 AI，应把 `skills\每个-skill\SKILL.md` 当作工作说明直接读取，不要改写 Skill 语义。

## 检查技能同步

说“检查技能同步”或“检查安装一致性”，即可只读比较工作区正式技能与安装副本：

```powershell
.\scripts\verify.ps1 -Mode Installed
# 需要限定范围或指定安装位置时：
.\scripts\verify.ps1 -Mode Installed -TargetSkillsRoot '<安装目录>' -SkillNames 'grow-creative-library','bilibili-study-notes'
```

默认只比较模块清单中的八个正式技能，分别报告缺失、内容差异、额外文件和必要依赖入口缺失。目录、日志和缓存按现有安装规则筛选，忽略数量按被跳过的项计数。安装目录沿用已有安装工具的解析规则；其他技能和预览模块不参与比较。

返回码 `0` 为一致、`1` 为发现差异、`2` 为无法完成检查。额外文件或不同内容需要核对，不自动覆盖或删除，也不据此认定实际回答效果。仅在点名或技能维护收尾时运行；默认 Daily、发布与隔离恢复仍不依赖本机安装状态。

## 按需备份到 GitHub

目标仓库为 [gbjxm/knowledge-tree-workflows](https://github.com/gbjxm/knowledge-tree-workflows)，分支为 `main`。已授权支持公开和私有仓库，执行前仍核对仓库身份、实际可见性、未归档与未禁用状态及写入权限；预览和回执记录当时的可见性，工具不更改仓库可见性或账号权限。以后对 AI 说“备份知识树”，即执行已配置范围的备份；不定时运行，也不在收尾时自动推送。

```powershell
# 只读预览（不带参数也一样）
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Preview
# 备份、普通推送、从远端独立恢复验证
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Apply
# 指定远端版本，只恢复到新的隔离目录
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -RestoreTest -Commit '<完整40位提交号>'
```

正式文件按模块白名单保存为可浏览文件及 Git 历史，包括完整 Vault、附件、设置、八个正式技能、脚本、配置、文档和长期来源记录。原始音视频、转写/OCR 缓存、预览技能代码、凭据和开发备份留在本机，不在此批远端备份中。

只有从远端恢复并通过文件哈希、目录、Release、Daily、知识库结构、正式关系和来源绑定检查后，才创建 `verified-backup-*` 标签。无内容变化不重复提交；上传成功而恢复失败会明确报未完成。工作目录、恢复目录和回执均在配置的 `raw_cache/github-backup`；正式工作区不初始化 Git。

需要 Git、已登录对应账号的 GitHub CLI，以及现有 Python 依赖。配置只保存仓库和分支，不保存令牌。整盘损坏后的操作、恢复范围和失败处理见[故障恢复](docs/故障恢复.md)。

## 打包与再次迁移

发布前先预览本次明确的文件集合，再由同一集合生成清单和 ZIP：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1 -Preview
powershell -ExecutionPolicy Bypass -File .\scripts\package.ps1
```

默认 `verify.ps1` 为只读 Daily 检查，笔记数量只报告；`-Mode Migration` 继续严格比较不可变的原迁移快照；`-Mode Release -Root <解压目录> -Manifest <发布清单>` 核对这次发布的文件、哈希和依赖。`-SkipAudits` 不能跳过发布安全和完整性检查。

打包使用正式模块白名单，排除整个运行缓存、Secrets（包括加密凭据）、开发备份和临时文件；只保留必要的空缓存目录脚手架。暂存区扫描与 ZIP 使用同一集合，解压后再次验证，不覆盖已有包。不要绕过发布工具直接压缩整个开发工作区。

打包暂存与解压自检使用配置的 `raw_cache/release-staging`，不依赖系统 TEMP。本机这些中间产物及默认发布包都放在 D 盘；预览不会创建暂存目录。

长期来源复核记录位于配置的 `source_evidence`（本工作区为 `evidence/sources`）。记录可以随包迁移，完整转写和媒体仍留原缓存；缺原文时只能回看历史结论，不能声称已经重新核验原文。旧缓存与旧证据不会自动删除。

## 原材料与缓存

缓存目录还保存实际整理依据，不能统一视为可删除的临时文件。已取得的原书、音视频、用于整理的转写、人工校正稿和复核依据默认保留；用途不明的先保留。只在确认原件、重建方法及没有独立价值后，才提出清理候选，实际清理另定范围。

说“盘点原材料”或“查看缓存”可按需只读查看；也可在工作区运行：

```powershell
python -B -X utf8 .\skills\grow-creative-library\scripts\cache_report.py --details
# 需要机器可读报告时增加 --json；原有不带 --details 的统计用法仍可用。
```

详细盘点提供目录用量和已有来源记录的文件定位、存在性及哈希状态，不把未登记材料当成未使用，不新增逐文件登记或自动清理任务。原材料仍未纳入 GitHub 备份。完整规则见[共享保留约定](skills/grow-creative-library/references/durable-source-evidence.md#原材料保留与按需盘点)。

## 当前任务与学习方向

北极星保存长期重点；状态页中的“已确认的全局待办”和“待选择的全局事项”是全局事实源，主页嵌入同一内容。当前任务只来自本次对话；普通启动、入库、收尾和周复盘不自动选学习题。明确请求学习建议时才传本次调用的 `--learning`，建议另列且默认未采用；单独选中来源不等于请求学习，历史下一步不再作为当前指令。笔记默认保存知识，学习字段和个人学习栏目可选；讲解讨论默认留在对话，明确要求保存才写回。

## 安全边界

- 唯一机器路径配置是 `.codex\knowledge-tree.json`；便携版使用相对路径，长期证据目录也通过共享加载器解析。模块发布范围由 `manifest/modules.json` 管理。
- `个人影视知识树` 内部结构、附件和设置受保护，不能仅因便携搬机而重构、改名或批量升级；明确授权的知识库结构迁移按批准映射执行。原迁移基线保持不可变；日常合法增补不再要求与旧迁移快照相同，发布则核对本次明确的文件集合。
- 缓存只能进入 `.runtime\raw-cache`，不能进入 Vault。
- 安装软件、安装 Skills、删除知识、改变北极星、改变分区或六类专业分类或写入跨类关系，都必须遵守 `AGENTS.md` 的确认边界。
- 普通网页聊天通常不能执行本机脚本；迁移和维护应使用具有文件访问能力的桌面/命令行 AI。

迁移历史和旧路径含义见 `docs\迁移与路径映射.md`，恢复办法见 `docs\故障恢复.md`。
