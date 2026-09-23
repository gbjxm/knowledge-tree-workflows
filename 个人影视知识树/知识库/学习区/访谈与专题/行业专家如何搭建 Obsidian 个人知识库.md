---
类型: 材料总览
分类: 行业观察与灵感素材
状态: 持续收集
材料类型: 同主题网络资料
笔记架构: 单篇材料
聚合单位: 主题
架构状态: 已确认
信息来源: 本人原文、官方页面、公开仓库、公开访谈、研究论文
完整程度: 首轮资料池（已核对公开页面与链接，未逐篇全文精读）
整理日期: 2026-07-21
知识库版本: 2.1
主题: Obsidian 个人知识库与 AI 辅助知识管理
作者或讲者: 多位行业从业者与知识管理研究者
适用阶段: [复盘与方法升级]
来源材料: []
关联项目: []
复习状态: 待复习
沉淀状态: 未沉淀
已沉淀主题: []
待沉淀主题:
  - AI 代理进入个人知识库时的权限与治理边界
  - 从原始材料到可调用知识的分层结构
  - MOC、索引与语义链接如何配合
理解状态: 待理解
关键问题状态: 待回答
---

# 行业专家如何搭建 Obsidian 个人知识库

## 材料简介

这是一篇持续积累的案例资料笔记，收集 AI、软件工程和个人知识管理领域的公开实践，供以后升级个人影视知识树时参考。首轮重点检查三件事：人物身份是否可靠、资料是否由本人或权威渠道公开、对方是否真的展示了 Obsidian 或个人知识库方法。

资料收集日期：2026-07-21  
笔记架构：多来源资料汇总的单篇材料  
读取情况：公开页面和仓库链接已核对；本轮属于资料池，不等于已经逐篇完成全文精读  
可靠性说明：优先本人文章、官方身份页、公开仓库和本人访谈；第三方总结只作为辅助入口  

> [!important] 使用边界
> “行业权威”不等于“公开过 Obsidian”。Andrej Karpathy 的 LLM Wiki 是一个公开设计原型；Eugene Yan、Steph Ango、swyx、Kenneth Reitz、Nicole van der Hoeven 等人公开了更具体的 Obsidian 实践。Tiago Forte 和 Andy Matuschak 提供的是底层知识管理方法，不能写成他们公开了自己的 Obsidian Vault。

## 快速阅读路线

1. 先看 **Andrej Karpathy**：理解怎样让 LLM 把原始材料“编译”为可查询知识。
2. 再看 **Steph Ango**：理解长期维护中为什么仍要保留人的判断和自然生长。
3. 接着看 **Eugene Yan**：观察研究、文献笔记、写作和 RAG 怎样形成闭环。
4. 再看 **Kenneth Reitz**：学习怎样用 `CLAUDE.md` 给 AI 设权限和操作边界。
5. 最后看 **Nick Milo、Tiago Forte、Andy Matuschak**：补足导航、项目组织和常青笔记的方法基础。

## 分章节／分集导览

本页不是课程或连续媒体，因此不虚构章节、页码或时间码；以下按材料性质提供语义导览：

| 阅读范围 | 主要内容 | 适合回答的问题 |
|---|---|---|
| 第一组：Karpathy、Steph Ango、Eugene Yan | LLM 编译知识、人类理解、研究写作与 RAG | AI 应怎样进入知识库，同时保留来源和人的判断？ |
| 第二组：swyx、Kenneth Reitz、John Kim | 公开 Vault、代理契约、知识园丁 | 知识库怎样版本化、持续维护并控制代理权限？ |
| 第三组：Nick Milo、Nicole van der Hoeven、James Croft | MOC、插件自动化、机器可读结构 | 地图、属性、脚本和 Skills 应怎样分工？ |
| 第四组：Tiago Forte、Andy Matuschak、研究论文 | PARA、CODE、常青笔记与研究证据 | 哪些属于跨工具的方法，哪些结论仍需验证？ |

## 一、AI 与技术行业中的公开实践

### 1. Andrej Karpathy：LLM Wiki

**身份与材料性质**

Andrej Karpathy 曾任 OpenAI 研究科学家和 Tesla AI 负责人。这份资料不是一篇传统的“我的 Obsidian 使用教程”，而是他公开的个人知识库设计原型。

**核心做法**

- 原始材料保持不可变，避免整理过程破坏证据。
- LLM 读取原始材料，把它们编译成结构化、可检索、可继续维护的 Wiki。
- 用 `CLAUDE.md` 或 `AGENTS.md` 一类说明文件定义知识库结构和代理行为。
- 工作流包含 `ingest`、`query`、`lint`、索引和更新日志，而不只是聊天问答。
- 将 Obsidian 比作 IDE，将 LLM 比作程序员，将 Wiki 比作代码库。

**资料**

- [本人原始设计稿：LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- 来源类型：本人公开 Gist
- 完整程度：设计说明可公开访问；未见其私人 Vault 全量内容
- 可靠性：高；可直接核对本人原文

**对个人知识树的候选启发**

- 原始材料、整理后的来源笔记和可调用主题知识应保持分层。
- AI 的产物需要经过结构校验和来源回溯，不能只凭“读起来合理”。
- 可以将知识树规则写成机器可读的操作契约，再让 AI 在契约内工作。

### 2. Steph Ango（kepano）：一个 Vault、少文件夹、重链接

**身份与材料性质**

Steph Ango 是 Obsidian CEO。他公开说明了自己长期使用 Obsidian 的具体习惯。

**核心做法**

- 尽量使用一个主 Vault，减少知识被不同库割裂。
- 文件夹很少；个人笔记可放根目录，引用资料和剪藏再单独收纳。
- 通过 Properties、Bases 和内部链接组织信息，而不是不断增加目录层级。
- 大量使用内部链接，也允许先建立尚未解析的链接，让结构逐渐浮现。
- 通过日记、模板和随机回顾持续重新接触旧笔记。
- 强调“不要把理解外包出去”：AI 可以辅助，但人仍要维护判断和意义。
- 坚持本地 Markdown 和“文件优先于应用”的长期所有权。

**资料**

- [本人原文：How I use Obsidian](https://stephango.com/vault)
- [Obsidian 官方团队页面](https://obsidian.md/about)
- 来源类型：本人文章、官方身份页
- 完整程度：工作流文章可公开访问；私人笔记内容未公开
- 可靠性：高

**对个人知识树的候选启发**

- 影视知识树可以保留稳定的六类主干，同时主要依靠属性、地图和语义链接增加检索维度。
- 不要因为有 AI 就取消个人复述、辨析和项目验证。

### 3. Eugene Yan：研究笔记、文章写作与 RAG

**身份与材料性质**

Eugene Yan 是 Anthropic 技术成员，长期公开机器学习系统、推荐系统和写作方法。他明确记录了自己使用 Obsidian 的过程。

**核心做法**

- 写作先在 Obsidian 中形成项目符号大纲，并在顶部写清“为什么写、为谁写、提供什么价值”。
- 一边阅读文献，一边按标题和论点补充要点，再将大纲转为文章。
- 从 Roam Research 迁移到本地 Obsidian，保留 Zettelkasten 思路。
- 用 Obsidian Git 管理版本，并保持图片等资产在本地。
- 在 Obsidian Copilot 原型中，用自己的笔记做 RAG 检索、反思和写作辅助。
- 切块时按“顶层观点或项目符号”划分，比机械按固定 token 切块更贴近笔记语义。

**资料**

- [本人原文：Writing FAQ](https://eugeneyan.com/writing/writing-faq/)
- [本人原文：Migrating from Roam to Obsidian](https://eugeneyan.com/writing/roam-to-obsidian/)
- [本人原文：Building an Obsidian Copilot](https://eugeneyan.com/writing/obsidian-copilot/)
- [本人原文：Mac Setup（包含 Vault、Git 与 Zotero）](https://eugeneyan.com/writing/mac-setup/)
- 来源类型：本人文章
- 完整程度：相关文章可公开访问；个人 Vault 未完整公开
- 可靠性：高

**对个人知识树的候选启发**

- 面向 RAG 的切块应优先尊重概念、论点、课次和场景，而不是只看字符数。
- 学习材料应该能自然流向文章、创作决策或项目产物，再把结果回写知识库。

### 4. Shawn “swyx” Wang：公开的 Obsidian Brain

**身份与材料性质**

swyx 是 Latent Space 主理人和 AI 工程领域的知名作者。他把自己的部分 Obsidian Vault 作为公开仓库和发布站点展示出来，因此可以直接观察真实文件结构。

**核心做法**

- 使用 PARA：Projects、Areas、Resources、Archive。
- 把公开笔记视为相对原始的思考材料，不等同于经过编辑的正式作品。
- 用 GitHub 保存和展示 Markdown，并通过 Obsidian Publish 提供阅读入口。
- 把知识库当作持续写作和公开学习的中间层。

**资料**

- [公开 GitHub 仓库：swyxio/brain](https://github.com/swyxio/brain)
- [公开 Obsidian Publish](https://publish.obsidian.md/swyx)
- [本人简介](https://swyx.io/about)
- 来源类型：本人公开仓库、本人发布站点
- 完整程度：公开部分可直接检查；不代表全部私人知识库
- 可靠性：高

**对个人知识树的候选启发**

- 来源笔记可以保留“粗糙但可追溯”的状态，主题笔记和正式作品承担不同职责。
- 公开仓库适合研究结构，但不应机械复制其文件夹，因为它服务的是公开写作而非影视创作。

### 5. Kenneth Reitz：用 CLAUDE.md 管理 AI 权限

**身份与材料性质**

Kenneth Reitz 是 Python Requests 的作者。他公开记录了 Obsidian Vault 与 Claude Code 结合的具体结构，并在数周后写了系统演化复盘。

**核心做法**

- Vault 使用 Markdown、统一 frontmatter、模板和 Git。
- 根目录 `CLAUDE.md` 相当于知识库的“API 合同”，说明结构、属性、允许动作和禁止事项。
- 明确规定 AI 不应未经请求创建文件、重组目录或过度工程化。
- 使用 Smart Connections、Excalibrain、Dataview、Templater、Obsidian Git 等插件辅助检索和维护。
- 保留人工回路：Claude 提出建议，用户验证、选择和处置。
- 五周后的复盘显示，他又放弃了一部分编号目录，改用更语义化的顶层文件夹，说明知识库结构会随规模和使用方式变化。

**资料**

- [本人原文：Obsidian Vaults & Claude Code](https://kennethreitz.org/essays/2026-03-06-obsidian_vaults_and_claude_code)
- [本人复盘：Infrastructure for One](https://kennethreitz.org/essays/2026-04-16-infrastructure_for_one)
- 来源类型：本人文章
- 完整程度：结构、插件和治理规则有较详细说明；私人笔记内容未公开
- 可靠性：高

**对个人知识树的候选启发**

- 未来若让 AI 批量整理知识树，应把“可自动做、必须预览、绝对禁止”的动作写清楚。
- 不把任何一次文件夹设计当成永久答案，要根据真实检索和维护成本演化。

### 6. John Kim：让 Gardener 代理每天照料笔记

**身份与材料性质**

John Kim 是 Delight.ai 联合创始人兼 CEO。他在公开访谈中介绍了长期使用 Obsidian/Logseq，以及名为 Gardener 的知识库代理。

**核心做法**

- 代理每天检查笔记，从中选择值得继续培育的内容。
- 自动研究笔记里提到的人物和公司，补充必要背景。
- 修正错字、语法和标题，整理聚类并建议交叉链接。
- 把笔记看成 seed、nurture、tending 的生长过程，而不是一次写完。
- 自动化重点是“照料和补充”，不代表代理应该不经确认地改写个人判断。

**资料**

- [本人访谈与逐字稿：How I AI](https://pod.wave.co/podcast/how-i-ai/quests-token-leaderboards-and-a-skills-marketplace-the-elite-ai-adoption-playbook-john-kim-sendbird)
- [第三方访谈摘要：ChatPRD](https://www.chatprd.ai/how-i-ai/john-kims-playbook-for-ai-transformation)
- 来源类型：本人公开访谈；第三方摘要为辅助
- 完整程度：访谈逐字稿可访问；Gardener 的完整代码仓库链接仍待进一步核验
- 可靠性：访谈高；第三方摘要中等

**对个人知识树的候选启发**

- 可以设计“知识园丁”式维护：发现缺口、提出链接、检查格式和提醒复习。
- 自动补写外部资料时必须标注来源，不能混入用户自己的理解。

## 二、Obsidian 与个人知识管理领域的权威实践

### 7. Nick Milo：用 MOC 建立人工策展的知识地图

**身份与材料性质**

Nick Milo 是 Linking Your Thinking 的创始人，也是 Obsidian 社区有影响力的知识管理方法作者。

**核心做法**

- Map of Content（MOC）是一种人工维护的链接地图。
- MOC 用来聚拢、发展和导航一组相关想法，而不是充当普通文件夹目录。
- 地图表达“我怎样理解这些知识”，因此策展本身就是思考。
- 允许知识从局部笔记中自然涌现，再在需要时形成更稳定的入口。

**资料**

- [本人方法文章：Maps of Content](https://blog.linkingyourthinking.com/maps/)
- [Linking Your Thinking 官方站点](https://www.linkingyourthinking.com/)
- 来源类型：本人方法文章、官方站点
- 完整程度：核心概念可访问；完整课程不属于本轮范围
- 可靠性：高

**对个人知识树的候选启发**

- 六类地图不应该只是自动列表，还应逐渐表达真正的调用顺序、判断边界和问题路径。
- 自动 Dataview 适合列出内容，人工地图适合表达意义，二者职责不同。

### 8. Nicole van der Hoeven：多 Vault、Git 与插件自动化

**身份与材料性质**

Nicole van der Hoeven 是开发者倡导者和长期 Obsidian 实践者，公开过工作场景中的 Vault 设计和自动化脚本。

**核心做法**

- 不同工作边界可使用不同 Vault，并把每个 Vault 作为 Git 仓库管理。
- 使用同步、备份和 Obsidian Publish 支撑跨设备与公开输出。
- 使用 Dataview、QuickAdd、Templater 等脚本减少重复维护。
- 强调系统目标比插件数量重要，插件只应服务真实工作流。

**资料**

- [本人原文：How I Use Obsidian at Work](https://nicolevanderhoeven.com/blog/20210518-how-i-use-obsidian-at-work/)
- [本人公开的 Obsidian 脚本 Gists](https://gist.github.com/nicolevanderhoeven)
- [本人简介](https://nicolevanderhoeven.com/about/)
- 来源类型：本人文章、本人公开脚本
- 完整程度：文章和脚本可公开访问；具体工作 Vault 未完整公开
- 可靠性：高

**对个人知识树的候选启发**

- 自动化应从重复而稳定的动作开始，例如模板、属性检查和索引刷新。
- 当前知识树已经有清晰边界，不宜仅为了模仿案例而拆成多个 Vault。

### 9. James Croft：把 PARA、YAML 和 AI Skills 组合起来

**身份与材料性质**

James Croft 是 AI 与开发工具实践者。他的资料价值主要在具体实现，不属于大型 AI 公司高管案例。

**核心做法**

- 使用 PARA 和 CODE 组织项目及知识流转。
- 通过 YAML、双向链接和稳定 Markdown 让知识库对机器可读。
- 为 AI 设计可复用 Skills，让代理按确定规则处理知识库任务。
- 把 AI 视为知识库的协作层，而不是替代本地文件和结构。

**资料**

- [本人文章：Why Your Second Brain Needs an AI Companion](https://www.jamescroft.co.uk/why-your-second-brain-needs-an-ai-companion/)
- 来源类型：本人系列文章入口
- 完整程度：公开文章可访问；本轮未逐篇精读整个系列
- 可靠性：中高；适合作为工程实现参考

## 三、并非 Obsidian 案例，但提供底层方法

### 10. Tiago Forte：PARA、CODE 与渐进式总结

**身份与材料性质**

Tiago Forte 是 Building a Second Brain 方法体系的主要作者。他的方法是工具无关的，不能据此认定他本人以 Obsidian 作为唯一或主要 Vault。

**核心做法**

- CODE：Capture、Organize、Distill、Express，把收藏转化为表达和成果。
- PARA：Projects、Areas、Resources、Archives，按行动相关性而非学科分类组织信息。
- Progressive Summarization：多次接触笔记时逐层提炼重点，不在首次收藏时过度加工。
- 工具选择应服务工作方式，不能让应用功能反过来主导系统。

**资料**

- [CODE：The 4 Levels of Personal Knowledge Management](https://fortelabs.com/blog/the-4-levels-of-personal-knowledge-management/)
- [PARA 与项目式组织](https://fortelabs.com/blog/the-box-twyla-tharp-on-project-based-organizing/)
- [Progressive Summarization](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)
- [How to Choose Your Second Brain App](https://fortelabs.com/blog/how-to-choose-your-second-brain-app/)
- 来源类型：本人方法文章
- 完整程度：核心公开文章可访问；完整课程和书籍不属于本轮范围
- 可靠性：高；属于方法论来源，不属于具体 Obsidian Vault 证据

### 11. Andy Matuschak：常青笔记是思考环境

**身份与材料性质**

Andy Matuschak 是 tools for thought 领域的重要研究与实践者。他的公开笔记系统不是 Obsidian Vault，但深刻影响了双向链接、原子概念和常青笔记方法。

**核心做法**

- 笔记围绕概念和可复用主张，而不是围绕来源章节机械拆分。
- 标题应像 API，清楚表达这条笔记能被怎样调用。
- 链接不仅用于跳转，也表达概念之间的关系和推理路径。
- 写笔记是形成理解的过程，因此不能完全外包给自动摘要。
- 知识应持续修订和连接，而不是一次归档后不再访问。

**资料**

- [公开笔记说明：About these notes](https://notes.andymatuschak.org/About_these_notes)
- [本人网站与 Evergreen Notes 入口](https://andymatuschak.org/)
- 来源类型：本人公开笔记、本人网站
- 完整程度：公开笔记可访问；不是 Obsidian 使用案例
- 可靠性：高；属于底层方法参考

## 四、研究证据

### 12. 行业研究者使用 Obsidian 的案例研究

**研究范围**

论文研究行业研究者怎样管理自己的“第二大脑”，并以 Obsidian 为案例环境。其价值在于补充个体经验文章：不同检索目标会反过来影响笔记的创建、组织和维护方式。

**资料**

- [论文：How People Manage Knowledge in their “Second Brains”—A Case Study with Industry Researchers Using Obsidian](https://arxiv.org/abs/2509.20187)
- 来源类型：公开研究论文
- 完整程度：摘要和论文页面可访问；本轮未完成逐段论文笔记
- 可靠性：研究型来源；具体结论仍需结合样本规模和研究限制精读

**对个人知识树的候选启发**

- 应先明确未来怎样检索和调用知识，再决定属性、索引、切块和链接方式。
- 影视创作知识树的检索目标不是“找到相似文字”，而是为具体创作阶段找出可用方法、边界和证据。

## 五、横向比较

> [!note] Codex 综合
> 下表是对公开材料的综合整理，不是任何单一作者的原话，也不代表已经被个人知识树正式采纳。

| 案例 | 原始材料处理 | 主要组织方式 | AI 的角色 | 人工控制点 | 主要输出 |
|---|---|---|---|---|---|
| Karpathy | 原料不可变 | LLM 编译 Wiki、索引、日志 | ingest、query、lint、维护 | 规则、来源校验 | 可查询知识库 |
| Steph Ango | 本地 Markdown、引用资料分区 | 少文件夹、属性、Bases、链接 | 可辅助，不替代理解 | 意义、链接、回顾 | 长期思考与写作 |
| Eugene Yan | 文献要点与资产本地化 | 大纲、标题、Zettelkasten | RAG、检索、写作辅助 | 论点、受众、文章判断 | 技术文章与研究输出 |
| swyx | 公开原始笔记 | PARA、GitHub、Publish | 非核心 | 原始笔记与正式作品边界 | 公开学习与写作 |
| Kenneth Reitz | Markdown、frontmatter、Git | 语义目录、模板、CLAUDE.md | 建议、整理、查询 | 禁止事项和最终确认 | 可协作的个人基础设施 |
| John Kim | 每日笔记持续生长 | 聚类、交叉链接、生命周期 | 每日照料与补充研究 | 判断是否采纳和改义 | 被持续维护的 Wiki |
| Nick Milo | 既有笔记逐渐汇聚 | MOC 人工策展地图 | 非核心 | 地图表达的意义 | 可导航的知识网络 |
| Nicole van der Hoeven | 多 Vault、Git | 项目边界、模板、插件 | 以自动化为主 | 系统目标和 Vault 边界 | 工作知识与公开输出 |

## 六、对知识树升级的候选参考

> [!warning] 尚未采纳
> 以下只是以后升级时的评估清单，不代表本轮已经改变知识树结构、属性或自动化权限。

### 可以优先考虑

1. **保留三层内容边界**：原始材料／来源笔记／可调用主题知识，不让 AI 整理破坏原始证据。
2. **建立代理操作契约**：写清 AI 可以自动检查什么、什么必须预览、什么未经授权绝对不能修改。
3. **把地图与自动列表分工**：Dataview 列出现有内容，人工地图表达调用顺序、问题路径和意义。
4. **按语义而非固定长度切块**：课程按课次，文章按论点，影视知识按创作问题和方法单元处理。
5. **让输出回流**：剧本、镜头、提示词、成片和复盘结果反向验证知识，而不是只增加收藏。
6. **设计知识园丁而非自动作者**：AI 优先发现缺口、检查格式、建议链接、提醒复习；对含义和重大结构只提出建议。
7. **保留结构演化能力**：先观察真实检索成本和失败模式，再调整目录、属性和自动化，不照搬任何人的 Vault。

### 需要谨慎

- 大规模自动重写笔记可能消除用户原本的语气、判断和不确定性。
- 自动建立双链容易制造数量很多但没有语义价值的连接。
- 只依赖向量检索可能找到文字相近的材料，却找不到真正适合当前创作阶段的方法。
- 插件、脚本和代理越多，维护成本与故障面也越大。
- 公开的 Vault 往往服务作者自己的写作和发布目标，不能直接替代影视创作知识树的分类与调用逻辑。

## 外部补充与分歧

- 本轮没有找到 Sam Altman、Dario Amodei、Demis Hassabis、Jensen Huang 等大型 AI 公司高管公开展示完整 Obsidian 工作流的可靠一手资料，因此未将他们列入案例。
- Eugene Yan 是 Anthropic 技术成员，不应表述为 Anthropic 高管。
- John Kim 是 AI 公司联合创始人兼 CEO，但公司规模和公开影响力与 OpenAI、Anthropic、Google DeepMind 不在同一层级。
- Karpathy 的 LLM Wiki 是公开设计方案，不能据此断言其私人知识库完全采用了该方案。
- James Croft 的价值主要在工程实现；进一步采用前应继续核验其完整系列和公开仓库。
- 工具、职位和网页内容可能变化；正式升级前应重新核验关键资料。

## 已融合到知识库

### 已沉淀

- 暂无。本页目前保留为可追溯的资料总览，不提前制造主题笔记。

### 待沉淀

- AI 代理进入个人知识库时的权限与治理边界：何种动作可自动执行，何种动作必须预览或禁止。
- 从原始材料到可调用知识的分层结构：怎样同时保留证据、理解和调用效率。
- MOC、索引与语义链接如何配合：自动列表和人工地图分别承担什么职责。

## 知识提炼清单

- 概念：LLM Wiki、文件优先、MOC、PARA、CODE、常青笔记、知识园丁、代理操作契约。
- 原则：原始材料不被覆盖；理解不完全外包；结构服务真实调用；自动化必须受权限约束。
- 方法：语义切块、来源分层、人工地图、属性检索、Git 版本控制、人工确认回路。
- 案例：Karpathy、Steph Ango、Eugene Yan、swyx、Kenneth Reitz、John Kim、Nick Milo、Nicole van der Hoeven。
- 反例或边界：公开 Vault 不等于适合个人目标；插件数量不等于系统成熟；向量相似不等于创作可用。
- 开放问题：怎样把这些方法转译成适合个人影视知识树、同时不增加过多维护负担的最小升级？

## 复习区

### 一分钟总结

这些案例没有给出唯一正确的 Obsidian 结构，但共同指向：使用本地 Markdown 保持所有权，区分原始材料、来源笔记和可调用知识，通过链接、属性、地图与索引支持检索；AI 适合编译、检查、检索和照料知识，但意义判断、结构变更和最终采纳仍需人工控制。

### 关键概念

- LLM Wiki：让模型按规则把原始材料编译成结构化知识。
- 代理操作契约：用明确文件约束 AI 的结构认知、权限和禁止事项。
- MOC：人工策展的内容地图，用来表达理解和导航路径。
- 知识园丁：持续发现缺口、补充资料、检查格式和建议链接的维护代理。
- 语义切块：按论点、方法、课次或创作问题划分内容，而不是机械按字符长度切分。

### 自测问题

1. Karpathy 的 LLM Wiki 与普通 RAG 聊天最大的结构差别是什么？
2. Steph Ango 为什么反对把“理解”本身外包给 AI？
3. Kenneth Reitz 的 `CLAUDE.md` 解决了什么治理问题？
4. MOC 与 Dataview 自动列表分别适合承担什么职责？
5. 哪三类操作适合交给知识园丁，哪三类操作必须保留人工确认？

- [ ] #复习 精读 Karpathy、Steph Ango、Eugene Yan、Kenneth Reitz 和 Nick Milo 的五组核心材料，并给每组补一条原文定位。
- [ ] #创作练习 选择当前知识树的一个真实维护动作，分别写出“可自动执行、必须预览、禁止自动执行”三档权限。

## 关键问题

> [!question] 本材料当前只保留一个最值得回答的问题
> 如果以后让 AI 更深入地维护个人影视知识树，哪些机械工作可以放心交给它，哪些涉及理解、结构和创作判断的工作必须始终由自己确认？
