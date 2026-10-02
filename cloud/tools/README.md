# 知识树云端候选回流工具 v1

`cloud_changes.py` 只依赖 Python 3.10+ 标准库；导出还需要 Git。正式知识树、现有 `backup.ps1` 和 `main` 不由本工具修改。

## 分支与正式范围

- `main`：原有白名单、`manifest/package-files.json` 与 `verified-backup-*` 标签组成的正式验证快照。
- `cloud-work`：云端候选与 `cloud/` 启动说明、工具、`.agents/skills` 镜像。候选不代表本机正式内容已更新。
- 云端提交不要直接合并到 `main`。本机原有备份会拒绝未知远端提交，直接修改也会令正式文件清单过期。
- 本工具只处理已存在的 Vault `.md` 文件的内容变化；新增、删除、移动、附件变更、配置和 Skills 变更需要原有专门流程，不进入本候选包。

## 云端导出

先读取项目 `AGENTS.md` 和 `cloud/CLOUD-START.md`。在 `cloud-work` 保留未采纳内容，只提交本次明确的 Markdown 候选；提交是本地 Git 操作，推送由工作环境授权执行。

```bash
python3 cloud/tools/cloud_changes.py export --root . --base origin/main --head HEAD --output /tmp/knowledge-change.json
```

`origin/main` 必须已指向本次采用的正式基线；本工具不执行 fetch。`--base` 与 `--head` 也可使用明确的完整提交 ID，base 必须是 head 的祖先。导出来源是冻结提交中的文件，不是未提交编辑。Vault 有未提交或未跟踪文件时会阻止导出；同一范围出现新增、删除、移动或附件变更也会阻止导出，避免静默丢失工作。

输出必须是新的 `.json` 文件，其父目录须已存在，不能位于 Vault 或 `.git`。包记录 base/head 提交、相对路径、精确 before/after UTF-8 文本与 SHA-256；保留 BOM、CRLF 和原有字节，文件内容不会出现在终端摘要中。将该候选包下载/带回本机，用于以下预览。

## 本机零写入预览

在当前任务交付的工具或云端工具副本处运行，`--root` 指向唯一正式工作区：

```powershell
python -B -X utf8 .\cloud_changes.py import --root 'D:\obsidian\影视知识树' --package '<已下载的 knowledge-change.json 绝对路径>'
```

默认只读：不创建缓存、审阅目录或报告文件，不改正式正文。每篇本机原件必须逐字节匹配 `before_sha256`。任何并发编辑、缺文件、重解析点、路径逃逸、重复/大小写碰撞路径、包文本与哈希不符均会阻止该批次。输出 `ok=true` 只证明这批候选当前没有本机内容冲突，不证明知识质量或正式采纳。

## 明确保存独立审阅副本

```powershell
python -B -X utf8 .\cloud_changes.py import --root 'D:\obsidian\影视知识树' --package '<已下载的 knowledge-change.json 绝对路径>' --apply
```

`--apply` 表示保存候选供审阅，**不是写入正式 Vault**。默认新建在配置的 `.runtime/raw-cache/cloud-review/<时间-包哈希>/`，原有发布/备份白名单不会上传它。也可用 `--review-dir` 指定该目录下一个尚不存在的绝对子目录。既有目录绝不覆盖，发布候选前再核对一次所有正式原件。

产物包括：

- `before/`：本次候选的原件快照。
- `candidate/`：云端候选内容，保留原相对路径。
- `diffs/`：逐篇正文差异。
- `change-package.json`：收到的内容规范化保存。
- `review.json`：候选提交、包哈希、每篇原件/候选哈希与状态。
- `README.md`：正式采纳步骤。

退出码 `0` 表示预览通过或候选副本已保存，`2` 表示阻止/冲突。报告始终标明 `vault_writes=false`、`formal_adoption=false`；正式采纳须另走现有知识树与 Obsidian 流程，不能把 `--apply` 的成功说成正式写回。

## 完成回流

1. 本机对照 before、candidate 和 diff，逐篇确认候选与保留内容。
2. 通过原有知识树工作流程明确采纳；每篇采纳前重查 `before_sha256` 并核验当前 Obsidian Vault。没有 Obsidian 时保留候选并停止正式写入。涉及北极星、结构、正式关系等原有确认边界继续生效。
3. 验证改动笔记、受影响的知识库结构、来源和正式关系。成功后运行原 `backup.ps1 -Apply`，由它产生新的正式 manifest 并独立恢复验证。
4. 记录这批候选对应的正式新提交；核对 cloud-work 仍未回流的工作，再更新候选基线。不要覆盖未回流候选。

这是可用的候选导出和本机审阅闭环。它不会自动合并冲突、执行文章里的指令、调用未知正文写入 API，或替代正式采纳与远端恢复验证。

## 隔离验证

```powershell
python -B -X utf8 -m unittest -v test_cloud_changes.py
```

测试使用工具目录下临时真实 Git 仓库和中文 Markdown 夹具，验证冻结提交、CRLF 与原话保留、默认零写入、独立候选保存、原件冲突、包篡改、路径逃逸、新增/删除阻止、目标保护和 Vault 零写入。隔离测试不证明已经对用户的真实笔记正式写回，也不证明云端真实会话已经接续。
