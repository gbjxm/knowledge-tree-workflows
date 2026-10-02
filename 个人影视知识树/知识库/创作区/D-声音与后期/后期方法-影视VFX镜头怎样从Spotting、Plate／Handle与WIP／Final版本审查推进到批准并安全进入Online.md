---
类型: 主题笔记
分类: 声音与后期
状态: 持续积累
材料类型: 主题沉淀
信息来源: 既有来源与综合主题的岗位转译
完整程度: 本轮选定专业范围；原始媒体与实际作品未重新验证
整理日期: 2026-10-02
知识库版本: 2.1
主题域: VFX镜头生命周期、版本审查、批准与Online交接
解决问题: 怎样在VFX被真实触发时，为每个镜头建立稳定Shot身份、清楚的Plate／Element／Handle与Turnover，审查WIP和Final版本，经过用户批准后插回当前CUT，并与DI／Grade／Online核对到PIC冻结
适用阶段: ["生成与镜头", "剪辑与声音"]
用途: 创作调用
主要岗位: ["D"]
协作岗位: ["C1", "C2"]
派生自: "[[知识库/学习区/综合整理/04-声音与后期/影视VFX镜头怎样从Spotting、Plate／Handle与WIP／Final版本审查推进到批准并安全进入Online]]"
来源材料:
  - "[[知识库/学习区/综合整理/04-声音与后期/影视VFX镜头怎样从Spotting、Plate／Handle与WIP／Final版本审查推进到批准并安全进入Online]]"
  - "[[知识库/创作区/D-声音与后期/声音与后期专业优化/04-色彩运算、调色判断与VFX往返]]"
关联项目: []
知识状态: 已提炼
成熟度: 生长
上位主题: []
相关主题: []
最后复核: 2026-10-02
证据状态: 多源互证
证据说明: 继承原稿具体专业观点的既有来源范围；本轮重组不构成独立新证据或实践验证
横向能力: ["AI影视"]
aliases: ["VFX回片与批准版本", "Plate Handle与Online核对"]
---

# 后期方法-影视VFX镜头怎样从Spotting、Plate／Handle与WIP／Final版本审查推进到批准并安全进入Online

> 本文是面向D岗位的专业方法正文。原稿的学习、个人理解与练习保留原位；此处以当前制作问题进入完整方法。旧稿中的阶段1—6、Stage、OPC及C部门标签用于解释专业功能与历史综合，不能替代当前V1的部门协作、工作集、采用或执行规则。

## 调用入口

- 当前问题：某VFX文件叫FINAL，帧数和分辨率都符合，是否能直接放入当前CUT？还要核对哪个版本、范围和批准事实？
- 何时进入：确有合成或生成式修复需求，需要准备Plate、审查WIP、处理返修或把Final插回当前剪辑时进入；没有需求不建空Tracker。
- 先带哪些事实：当前对象和精确版本、已知创作意图、已经观察到的结果与限制；缺少真实媒体时区分方案判断和执行结论。
- 何时结束：关键方法及其条件已能支持本次判断，剩余未知已定位；不因章节多而要求通读全部，也不只读标题或摘要便宣称方法覆盖。

## 快速认识

- 核心问题：为什么已经收到一个名为Final的漂亮文件，仍不能证明它属于当前CUT、使用了正确Plate、通过了运动上下文审查或可以冻结进PIC。
- 主要结论：VFX完成不是“交到一个文件”，而是Spotting—Shot ID—Scope—Plate／Element／Handle—Turnover—WIP／Final Version—上下文审片与Notes—修改或Repull／Reconform—用户批准唯一Final—插回当前CUT—DI／Grade／Online交叉核对—PIC冻结与最小归档的连续对象链。
- 调用价值：能把Shot与Version、代理与最终素材、单帧观感与上下文通过、技术修补与创作重生成分开，降低旧版本和错Plate进入成片的风险。
- 适用环节：锁画前VFX预判、Picture Lock后的VFX Turnover、AI生成式修复、WIP审片、锁画后改版、Final VFX插入、调色／Online往返和PIC冻结。

## 核心命题

### 一条连续生命周期

VFX镜头只有在以下链条能被追溯时才接近完成：

Spotting  
→ 分配稳定Shot ID  
→ 定义Scope和完成标准  
→ 绑定Plate、Element、Active Frame与Handle状态  
→ 形成Turnover并确认接收  
→ 接收WIP或标记为Final的具体Version  
→ 在当前CUT和正确观看条件下审片  
→ 把Notes绑定到具体Version和帧段  
→ 修改、Repull或Reconform  
→ 用户批准唯一Final Version  
→ 把该版本插入当前CUT  
→ 与DI／Grade／Online交叉核对  
→ PIC冻结并保存最小恢复证据。

任何一段缺失，都可能出现“文件存在但对象关系错误”：Shot没有稳定身份、Version指向旧CUT、Plate范围不足、WIP被当Final、Final未获批准、批准版未真正插入，或Online插入后颜色和时长已改变。

### 三个不能画等号

1. Shot不等于Version：Shot是一个持续存在的逻辑镜头对象；Version是这个Shot的一次提交或修改结果。
2. 单帧漂亮不等于上下文通过：静帧看不到跟踪漂移、闪烁、边缘呼吸、运动连续、入退切点和表演节拍。
3. 代理／预览不等于最终Plate或Final：代理和Offline Comp用于意图、时间与上下文沟通；只有交接定义明确时，它们才可能成为正式工作源或最终交付。

### 文件名不是批准证据

WIP、FINAL、v12或approved写在文件名里，只能作为提交方的标签。用户是否在当前CUT中看过、批准了哪一个精确Version、接受了哪些限制，必须另有记录。批准动作也不替代技术QC、Online插入和PIC回归。

## 适用边界

- 本主题只在画面确实需要VFX、生成式修复或外部合成时触发；没有VFX的项目明确记不适用，不建立空Shot Tracker。
- 它管理镜头对象、版本、审片、批准和回片，不教授复杂合成、CG、Simulation、设施管理、供应商报价或成本追踪。
- Grade负责颜色与影调塑形，VFX负责需要改变或重建画面内容的时空像素工作，Online负责正确版本回原、插入、Conform和最终技术汇合，C负责需要重新决定人物、资产、空间、表演、镜头或故事事实的重生成；具体项目可能由同一人或同一软件完成，但逻辑责任仍需分开。
- AI Inpaint、Outpaint、清除、补帧、扩图、替脸式修复、超分或生成式补景都是新派生，不因看起来接近原片就继承父素材身份和批准。
- 本主题不规定统一Shot命名、Version位数、Plate编号、Handles帧数、文件格式、分辨率、位深、Alpha、色彩空间、审片平台或审批层级。
- Online、Grade、VFX与GFX不存在跨项目唯一先后顺序；按当前CUT、像素状态、Color Recipe、是否Baked及接收契约决定。
- 本主题不替代用户创作批准、表演与叙事判断、素材权利确认或最终母版全片QC。
- 当前知识由多源资料互证，但尚未用真实VFX镜头执行完整Turnover—WIP—Notes—Final—Online回归，不能写成实践验证。

## 学习材料

- 岗位转译的直接原稿：[[知识库/学习区/综合整理/04-声音与后期/影视VFX镜头怎样从Spotting、Plate／Handle与WIP／Final版本审查推进到批准并安全进入Online]]。本轮保留其中完整的专业知识单元、详细方法、案例、反例和条件，个人记录仍在原稿。
- 实际对照的创作区专业来源：[[知识库/创作区/D-声音与后期/声音与后期专业优化/04-色彩运算、调色判断与VFX往返]]。采用该汇编中与本问题相应的机制、来源定位和阅读限制。
- 下文课程、书籍和历史网页列表为继承的出处追溯；本文不声称本轮重新读取了其外部原文、听看了原声画或验证了当前软件／法律／平台规则。原稿中的访问日期与“本轮”均对应原记录的历史批次。


### 原综合稿的专业增补（2026-09-09）

[[知识库/创作区/D-声音与后期/声音与后期专业优化/04-色彩运算、调色判断与VFX往返|色彩运算、调色判断与VFX往返]]补充帧范围端点、源与输出映射、EXR窗口及透明边缘、返修差量和恢复验证。原文“v0.8升级输入”属于历史知识建设语境，本批不改项目或工作流。

### 《D后期知识建设｜07 D后期全链审计与v0.8升级输入》

简介：把阶段1—6、现有D主题、当前v0.75模板与D Skill放入同一传统后期链，经第一轮缺口审核、VFX／Online／现场录音等定向补查和第二轮压缩复审，确认VFX镜头生命周期是本轮唯一需要新增的专业主题。  
来源：[[知识库/学习区/综合整理/04-声音与后期/D后期知识建设/07-D后期全链审计与v0.8升级输入.md|阶段7专业资料汇编]]  
类型：同主题多来源专业流程审计  
信息来源：阶段1—6、当前工作流只读快照、ScreenSkills岗位资料、Netflix制作资料与两轮Codex综合审计  
完整程度：VFX生命周期和OPC边界基本完整；实际软件、媒体、项目成本与拦错结果待验证  
核验情况：Shot／Version、Plate／Handle、WIP审查、Notes、Repull、Final插入和DI／Online核对由多份一手资料互证；平台字段与大型制作组织均未外推为统一规则。  

### 汇编内的关键一手证据

| 材料 | 本主题采用的证据 | 不直接移植的部分 |
|---|---|---|
| [ScreenSkills：VFX Editor](https://www.screenskills.com/skills-checklists/scripted-film-and-tv/editorial-department/vfx-editor-skills/) | VFX需要Shot／Version、Plate／Handle、Turnover、WIP审查、Notes、Repull、Final插入、DI核对和归档的连续生命周期 | 岗位编制、大型数据库、供应商与成本字段 |
| [Netflix：VFX Shot and Version Naming](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360057627473-VFX-Shot-and-Version-Naming-Recommendations) | Shot身份、单次Version和被批准进入Final Cut的版本必须区分 | 具体命名结构、字段和位数 |
| [Netflix：VFX Media Review Delivery](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360057627253-VFX-Media-Review-Delivery-Specifications) | WIP／FINAL、Version、Scope、Submission Note和上下文审片是不同交付事实 | 文件规格、审片平台和上传实现 |
| [Netflix：VFX Plate Naming](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360055781274-VFX-Plate-Naming-Best-Practices) | Plate与Repull后的新Plate需要稳定身份和版本谱系 | PL编号和命名样式 |
| [ScreenSkills：Online Editor](https://www.screenskills.com/skills-checklists/unscripted-tv/post-production-department/online-editor-skills/) | Online接收高质量原件、Final VFX、Grade和GFX并形成最终画面，同时传播变化 | Unscripted TV岗位范围和统一上线顺序 |

## 内容导览

### 整体脉络

- 触发与分流：先在CUT上下文中Spotting，判断问题应由Grade、VFX、Online还是返回C处理；未触发VFX时不建表。
- 对象建模：为需要VFX的逻辑镜头建立稳定Shot ID，并把Scope、Plate、Element、Active Frame、Handle和参考绑定到它。
- Turnover：交付的不只是文件，而是当前CUT基线、创作意图、范围、像素和色彩解释、参考及开放问题。
- 版本审片：每个WIP／Final标签都只是具体Version；在单镜与场景上下文中审看，把Notes绑定版本和帧段。
- 改版回路：普通修改产生新Version；Plate或范围错误需要Repull；CUT改变需要Reconform，必要时两者同时发生。
- 批准与插入：用户批准精确Final后，Online把它插入当前CUT，再与DI／Grade、离线参考和上下游组件交叉核对。
- 冻结与恢复：只有当前批准版真正进入PIC、问题关闭或被明确接受，才冻结并保存Final及直接依赖。

### VFX镜头状态流

~~~mermaid
flowchart TD
    A["当前CUT中发现VFX需求"] --> B{"问题路由"}
    B -->|Grade| C["技术平衡／匹配／Look"]
    B -->|Online| D["Relink／Conform／版本汇合"]
    B -->|返回C| E["重生成创作事实"]
    B -->|VFX| F["Spotting＋稳定Shot ID"]
    F --> G["Scope＋Plate／Element／Handle"]
    G --> H["Turnover＋接收确认"]
    H --> I["WIP或Final标签的具体Version"]
    I --> J["单镜＋当前CUT上下文审片"]
    J --> K{"用户是否批准精确Version"}
    K -->|修改| L["新Version"]
    K -->|Plate／范围变化| M["Repull"]
    K -->|CUT变化| N["Reconform"]
    L --> J
    M --> H
    N --> G
    K -->|批准Final| O["插入当前CUT"]
    O --> P["DI／Grade／Online交叉核对"]
    P -->|问题| J
    P -->|通过| Q["PIC冻结＋最小归档"]
~~~

## 知识单元

### 一、Spotting先识别创作问题，不先指定工具

VFX Spotting是把剪辑中的观察转成可追踪问题，而不是看到瑕疵就写“用AI修”。每个事件至少回答：

- 它位于哪个当前CUT、镜头或时间段；
- 观众会看到什么症状；
- 这影响叙事、表演、连续性、可信度还是纯技术完成；
- 最小可接受结果是什么；
- 剪辑、Grade、VFX、Online或返回C中谁最接近根因；
- 如果不处理，错误代价是什么。

先判断能否通过换镜、缩短、重构图或声音转移注意解决；如果必须改变画面内容或运动一致性，再触发VFX。软件能力不能反向定义创作问题。

### 二、Shot是持续身份，Version是一次状态

| 对象 | 回答的问题 | 典型变化 |
|---|---|---|
| Shot | 这是哪一个持续追踪的VFX镜头对象 | Scope、当前CUT绑定、状态、最终批准关系 |
| Plate | 这次工作的画面底板来自哪里、覆盖什么范围 | Repull、新父源、范围、色彩解释 |
| Version | 这个Shot的哪一次提交正在被审查 | WIP、修改、Final标签、批准或被替代 |
| Review／Note | 谁在什么上下文看了哪个Version，发现什么 | 新问题、关闭、接受限制 |
| Final Insert | 当前批准Version是否真正进入当前CUT／PIC | 插入、替换、回归、冻结 |

一个Shot可以有多个Version；一个Version不能脱离Shot、父Plate和CUT基线独立成为“最新正确文件”。Shot身份通常保持稳定，但若镜头的创作功能或范围被根本改变，是否建立新Shot由项目规则决定，不把某种命名习惯写成通则。

### 三、Scope必须同时写画面动作和完成边界

“擦掉路人”“修一下脸”“背景更完整”不足以指导或验收。轻量Scope应说明：

- 要改变、保留和绝不能改变什么；
- 生效的Active Frame范围与入退状态；
- 角色表演、视线、口型、动作节拍和镜头运动中哪些是锁定事实；
- 边缘、遮挡、反射、阴影、景深、运动模糊、颗粒和光色需要怎样延续；
- 交付是修补层、完整合成、带Alpha元素还是其他明确角色；
- 哪些已知限制可以接受，哪些失败必须返回。

完成标准应能在运动上下文中观察，而不只用“自然”“电影感”“无痕”这类不可判定词。

### 四、Plate、Element、Active Frame与Handle各有角色

- Plate：VFX工作的画面底板或核心父素材。它需能回到精确原件、CUT事件和色彩解释。
- Element：合成需要的附加画面、Clean Plate、Matte、参考、生成层、粒子或其他部件；每个元素同样需要来源和版本。
- Active Frame：当前CUT真正可见、必须完成的帧段。
- Handle：Active Frame之外保留的额外源帧，为切点微调、转场、稳定、变速或下游处理留余量。
- Offline Reference／Temp Comp：沟通构图、时长、意图和上下文的参考，不自动成为正式Plate或最终像素源。
- Proxy：为流畅工作或审看产生的派生表示；除非交接明确，它不替代高质量原件、最终Plate或Final。

Handle是否需要、需要多少，取决于剪辑稳定度、转场、变速、供应商和接收契约。本主题只要求记录“是否有足够余量以及谁确认”，不规定统一帧数。

### 五、Turnover交的是可重建语境

OPC版Turnover不需要设施级数据库，但至少包含：

1. Shot ID、当前CUT／版本和时间基线；
2. Scope、创作意图、必须保留项和完成标准；
3. Plate／Element父对象及Active Frame／Handle状态；
4. Offline Reference、关键参考帧或动作参考；
5. 缩放、裁切、稳定、变速、重构图、转场和临时效果事实；
6. 源色彩解释、Color Recipe、View参考及Alpha／合成角色；
7. 输出角色、当前开放问题、联系人或批准责任；
8. 实际接收确认，而不是只记录“已发送”。

Turnover后若发现父Plate、范围、像素解释或CUT错误，应停止继续堆Version，先Repull或修正基线。

### 六、WIP与Final是提交状态，不是质量结论

项目可以自定义状态，但必须区分以下逻辑：

- Turned Over：任务和材料已被接收；
- WIP：可用于方向、技术或阶段性审查，尚未完成；
- Final-labelled：提交方认为可作为Final审查的Version；
- Change Requested／On Hold／Omitted：需要修改、暂停或已不再需要；
- User-approved Final：用户在明确上下文中批准的精确Version；
- Inserted Current：批准版已进入当前CUT／PIC候选；
- Superseded：已被新Version、Repull或新CUT替代。

即使文件名写FINAL，它仍需通过上下文审片、用户批准、Online插入和回归。相反，一个仍写WIP的文件也不能因为“看起来够好”被静默当作Final。

### 七、上下文审片至少有三个尺度

1. 单镜循环：检查边缘、跟踪、Matte、噪声、颗粒、纹理、运动模糊、Alpha、反射和局部稳定性。
2. 前后镜头：检查动作、视线、空间、光色、景深、颗粒、速度和入退切点连续。
3. 场景或段落播放：检查观众注意力、表演节拍、叙事信息、修复是否抢眼，以及问题是否只在真实播放速度出现。

静帧看不出闪烁、漂移、抖动、帧间形变、运动节奏和切点暴露；低质量代理也可能隐藏边缘、色带、压缩和颗粒问题。必要时同时看高质量单镜与当前CUT上下文。

### 八、Notes必须绑定精确Version和观察证据

一条可执行Note应包含：

- Shot ID与被审查Version；
- 当前CUT和审片上下文；
- 帧号、时间段或清楚的动作定位；
- 观察到的症状，不把未经验证的根因写成事实；
- 创作意图或必须保留项；
- 期望变化和验收观察点；
- 优先级、责任、状态与用户决定。

“再自然一点”“边缘不对”“AI感重”无法形成稳定回路。可以写成：“角色抬手经过窗框的12帧内，右手边缘出现亮线并随运动跳动；保持手指轮廓和动作节拍，只修正边缘污染，在原速与前后镜头播放中复核。”

### 九、修改、Repull与Reconform不是同义词

- 修改：父Plate和CUT基线未变，在同一Shot上产生新Version。
- Repull：需要重新提取或交付Plate／Element，原因可能是父源错误、范围变化、Handle不足、色彩解释错误或更高质量源可用；新Plate必须保留与旧Plate的谱系。
- Reconform：CUT、时长、切点、变速、转场或画面结构变化后，把Shot及其Version重新对齐当前时间线。

Reconform可能发现Handle不足并触发Repull；Repull也可能让旧WIP全部失效。两者都不能只覆盖旧文件而不更新Shot状态、受影响Version和回归范围。

### 十、用户批准必须落到唯一Final Version

批准前至少确认：

- 审看的是哪个精确Version、实际文件和父Plate；
- 它已放入哪个当前CUT、用什么参考View和播放速度审看；
- Scope是否满足，必须保留的表演、空间和叙事事实是否未变；
- 已知限制、未解决问题和下游风险是否可接受；
- CUT、Plate或Version一旦变化，批准是否自动失效。

Agent、供应商、文件名或技术QC都不能代替用户的创作批准。用户批准也不能证明文件已经正确进入Online或最终编码。

### 十一、Final插入当前CUT后还要做交叉核对

Online插入批准版时核对：

- Shot ID、批准Version与实际文件一致；
- Active Frame、Handle、Cut点、变速、转场、缩放、裁切、稳定和重构图正确；
- Alpha、Premult、边缘、黑位、高光、色带、颗粒和压缩没有因往返改变；
- Color Recipe与当前Grade关系清楚，没有漏变换或双变换；
- Offline Reference与Online结果在相同观看条件下可解释地一致；
- Final插入没有使用旧Plate、旧WIP或另一个CUT的批准记录；
- 变化已经传播到Grade、GFX、字幕、声音或其他受影响组件。

只有Final VFX在当前CUT里通过运动上下文与技术回归，才能成为PIC候选的一部分。

### 十二、DI／Grade／Online的交叉点要写事实

| 接口 | 主要检查 | 不能替代 |
|---|---|---|
| VFX→Grade／DI | 返回像素、Color Recipe、参考View、动态范围、Alpha、颗粒和批准状态 | Colourist不能猜Plate编码或替用户批准内容 |
| Grade／DI→VFX | 用于审片的Look／View、是否Baked、返修如何避免重复变换 | Look参考不能冒充源像素解释 |
| VFX→Online | 批准Version、Active Frame／Handle、缩放／变速事实、Final文件和限制 | 文件名不能替版本绑定 |
| Online→VFX | 当前CUT、离线参考、插入差异、技术异常和Repull／Reconform需求 | Online不能静默改VFX内容后仍沿用原批准 |

DI、Grade和Online可以由同一人或同一软件完成，但仍要知道当前动作是在改变像素内容、观看解释、时间结构还是最终汇合。

### 十三、Grade、VFX、Online与返回C的路由

| 路由 | 适合的问题 | 应返回而不是硬修的情况 |
|---|---|---|
| Grade | 曝光、白平衡、对比、饱和、色相、镜头匹配、局部塑形与叙事Look | 需要重建物体、身体、背景运动或遮挡关系 |
| VFX | Paint／Cleanup、跟踪、抠像、合成、稳定、局部重建和时序像素修复 | 修复会改变人物身份、表演、镜头意图、资产设计或故事事实 |
| Online | 高质量回原、正确Version插入、Conform、缩放／变速／转场复核、最终技术汇合 | 需要重新创造内容或掩盖上游未批准改变 |
| 返回C | 人物、资产、空间、表演、动作、机位、光向或生成逻辑本身错误 | 只是版本、色彩、边缘或时间线技术问题 |

判断依据是根因和创作影响，不是哪个软件“也能做”。能在Grade里遮住一个缺陷，不等于Grade就是正确责任层；能用生成模型补一块画面，也不等于它没有改变上游创作事实。

### 十四、AI生成式修复必须成为新派生

生成式填补、清除、扩图、补帧、超分、风格重绘或局部重生成至少保留：

- 父素材／父Plate和Shot；
- 实际输入范围、Mask、参考输入及限制；
- 模型、版本、关键参数、提示和批次；工具未提供的字段明确记未知；
- 原始输出、人工修改、合成后的Version和父子关系；
- 改变了哪些画面事实，哪些必须保持；
- 当前状态：候选、WIP、Final-labelled、用户批准、插入或被替代；
- 来源、同意、权利或标识中与该派生直接相关的已知事实。

原件和原始输出不得被新修复覆盖。若生成式修复改变脸、视线、口型、手势、道具、服装、光向、空间结构或事件意义，应暂停VFX流程并返回C／用户确认，而不是把语义改变包装成Cleanup。

### 十五、PIC冻结前关闭的是对象关系，不只是画面瑕疵

VFX进入PIC冻结的最低条件：

1. 每个触发Shot都有稳定身份、当前Scope和明确状态；
2. 当前CUT绑定正确，锁画后变化已Reconform；
3. 当前Plate／Element和必要Handle可追溯；
4. 用户批准的唯一Final Version明确；
5. 该Version已真正插入当前CUT；
6. 在正确View下完成单镜、前后镜头和段落审查；
7. DI／Grade／Online接口核对完成；
8. 开放问题已关闭、暂停、删除或由用户明确接受；
9. PIC清单指向实际文件，而不是“Final文件夹”；
10. 最小恢复材料已经保存。

若后续CUT、Plate、Color Recipe、Grade或Final Version变化，相关批准和PIC检查必须按影响范围重新打开。

### 十六、最小归档保留Final及其直接依赖

OPC不需要复制大型设施数据库，但至少保留：

- Shot Tracker最终快照；
- 用户批准并实际插入的Final文件及Hash；
- 父Plate、直接Element和必要参考；
- Scope、关键Notes、批准与被替代Version关系；
- Color Recipe、当前CUT／PIC绑定和已知限制；
- 能重新识别、重连或再次输出所需的最小工程／说明。

只保存最终像素可能无法返修；保存所有缓存又会造成巨大负担。归档层级由恢复目标决定，本主题不规定统一保存年限、副本数或机构级迁移方案。

## 方法与案例

### 帧数相同，不代表用了同一段画面

先区分源帧号、提交序列帧号、时间线位置与审片播放器显示帧号。它们可能从不同数字起算；“第12帧有问题”若没说坐标，接收方可能修错位置。最小可靠记录是具体文件／Version、采用的帧号体系、帧率及可核对的动作定位。

[OpenTimelineIO 0.17时间范围文档](https://opentimelineio.readthedocs.io/en/v0.17.0/api/python/opentimelineio.opentime.html)明确区分含末帧与不含末端的表示。本库构造算例：无变速、一对一映射，Active源帧为1001—1050（两端都含），共50帧；前后各8帧Handle，对应提取993—1058，共66帧。同一范围用半开区间记为[993,1059)，不是[993,1058)。1001是本例约定，不是行业统一起点。

既要验数量，也要验首尾内容和映射。少一帧后复制尾帧补足数量，仍不是正确交付；错起点但总数相同，也可能在自动文件检查中漏过。

### Handle有三个“是否可用”

一是父源是否真实存在额外帧；二是Plate是否把它们交出；三是返回Version是否在这些帧也完成了约定效果。原片有Handle，不代表供应方已经修过Handle。延长CUT进入原来未完成的范围，不能继承仅Active区获批的结果。

变速时还要分清源余量与输出余量。以源帧位移／输出帧位移定义的恒定0.5速度为例，24个输出帧间隔只跨12个源帧间隔；但插值、运动估计或模糊可能额外需要邻近源帧，不能只按这个比值算交付范围。变速曲线、倒放、冻结段更应提供逐段映射或可重建设置。

[Foundry OFlow文档](https://learn.foundry.com/nuke/current/content/comp_environment/temporal_operations/oflow_retiming.html)说明可按速度或源帧映射产生中间图像。由此得到本库边界：产生了中间帧不证明保住正确遮挡、身体轮廓或表演；源映射、重建设置和实际原速观看必须分别核对。

### 空间窗口与时间Handle不是同一种余量

Overscan（画框外空间余量）服务稳定、畸变、模糊等空间操作；Handle是时间上的额外帧。增加其中之一不能补另一种缺失。

[OpenEXR技术说明](https://openexr.com/en/latest/TechnicalIntroduction.html)区分Display Window（预期画面窗口）与Data Window（实际保存像素的区域），二者可以不同，数据区域还可能有非零或负坐标原点。因此只核对“1920×1080”不够：同尺寸文件也可能因窗口、原点、像素宽高比、裁切或缩放出现错位。

接收测试先确认画框、数据边界与是否保留空间余量，再看元素在同一坐标系中的位置。RGB、Alpha、Matte或向量若经不同裁切／缩放，也会导致边缘不重合；不能只移动其中一层让一帧看似对齐。此处只补交接判断，不要求为无相应需求的镜头生成多通道EXR。

### 边缘发黑，先分清解释错误与内容损坏

预乘解释错会改变半透明边缘贡献；若图像已经带黑背景污染、抠像漏色或运动模糊缺失，正确Unpremult也未必能修复。先确认Straight／Premult、颜色通道和实际Alpha，再分别看RGB、Alpha及不同背景上的合成。

本库候选检查：用黑、白和中灰背景辅助暴露轮廓、漏光或污染，但它不是所有元素都必须“边缘不变”的标准。发光、透明玻璃和烟雾本就依赖背景。最终仍须放回真实Plate和正确View，完整观看遮挡、快速移动及出入画。

如果只是颜色解释或合成设置错误，先修解释；如果已在文件中烘焙错误或缺失细节，回到父源重新输出或修复；不通过压暗整张图把技术边缘隐藏成Look。

### 返修Note关闭的是哪一处，哪些地方仍需回归

新Version改善了指定问题，不等于其他区域都未改变。提交说明应列出本次差量、处理范围和未处理项；审查先核对旧Note，再比较必须保留的视线、口型、道具、阴影、背景结构和时序。

本库构造：为修眼周闪烁，模型同时把人物视线由躲闪改为直视。局部技术目标有所改善，但表演事实变化；应保留旧版、拒绝自动继承批准并交创作责任人判断。Mask是输入约束，不是输出边界证明；需要检查Mask外以及邻近帧是否发生变化。

像素差分适合定位变化候选，但有损编码、重颗粒或合法调色也会产生差异；它不能单独判定语义是否被改。相同文件哈希可证明文件未变，却不能证明Online取了正确帧段或正确View。

### 恢复目标要分层，不等于必须保存所有缓存

可以区分：能重新播放已批准Final；能在当前CUT正确重连；能重渲染或继续返修。第三层通常比前两层需要更多工程、元素、变换及依赖。所谓“最小归档”应覆盖约定目标，不是只留父Plate就保证可重做，也不是保存整个软件缓存目录。

本批只给恢复检查方法。没有实际移位重连、重新渲染和输出核对，不能把Manifest完整写成恢复成功；相关项目与媒体操作仍需单独授权。

### 轻量VFX Shot Tracker

VFX被触发后，用“一行Shot＋一个版本子列表”即可开始，不建立空设施表。

| 区域 | 最小字段 |
|---|---|
| Shot身份 | Shot ID、当前CUT／事件、时间范围、当前状态 |
| Scope | 症状、创作意图、必须保留、完成标准、责任路由 |
| 来源 | Plate／父Asset、Active Frame、Handle状态、Element、参考、Color Recipe |
| Version | Version ID、WIP／Final-labelled／Approved／Superseded、父Plate、提交说明、实际文件 |
| Review | 审片上下文、最新Note、帧段、负责人、下一动作、开放问题 |
| 批准与插入 | 用户批准Version、日期、已知限制、当前CUT插入、Grade／Online回归、PIC状态 |
| 恢复 | Final Hash、直接依赖、最小工程／说明、恢复位置 |

同一CUT、Asset、Decision／Issue和Deliverable／QC事实应引用共享权威位置，不在Shot Tracker里重复维护另一套作品版本。

### 只在事件发生时更新

| 事件 | 必须更新的内容 | 不需要做的事 |
|---|---|---|
| Spotting确认VFX | 新建Shot、Scope和当前CUT绑定 | 给无VFX镜头建空行 |
| Turnover或Repull | Plate／Element／Handle、参考、接收与父子关系 | 复制全部源素材字段 |
| 收到新Version | Version、文件、提交说明和审片状态 | 把“最新”自动设为权威 |
| 审片或新Note | 审查上下文、证据、动作和状态 | 每天重复填写无变化字段 |
| CUT变化 | Reconform、受影响范围、是否Repull、批准失效 | 静默沿用旧Final |
| 用户批准Final | 精确Version、条件、限制与批准证据 | 把批准等同于已插入 |
| Online插入／PIC冻结 | 实际插入、回归、Final Hash和恢复入口 | 建立设施级归档数据库 |

### 案例一：单帧漂亮，播放时边缘呼吸

AI Cleanup把演员身后的路人移除，停在任意一帧都很干净；原速播放时，演员肩部边缘随呼吸忽粗忽细。该Version只能通过静帧检查，不能通过上下文审片。Note应定位动作区间和边缘症状，要求保持肩部轮廓与动作节拍，在原速、循环及前后镜头中复核。

### 案例二：旧WIP进入当前CUT

某Shot的v05标注FINAL，但用户后来批准的是基于新Plate的v08。Online从“Final”文件夹拖入v05，画面本身没有明显瑕疵。若只做视觉QC可能漏掉；Shot—Version—批准—插入绑定能直接发现错误。修复不是再调颜色，而是换回批准v08并重新完成插入回归。

### 案例三：锁画后延长镜头需要Repull

CUT把镜头尾部延长，原Turnover没有足够Handle。把旧Final拉长会出现冻结或重复帧。正确动作是记录Change，Reconform当前Shot，判断旧Plate不足后Repull新的范围，再让受影响Version重新审片和批准；旧Final自动成为Superseded。

### 案例四：生成式修脸改变表演

修复模型消除了眼周抖动，却把角色原本迟疑的视线变成直视。技术瑕疵减少，但表演事实改变。该问题不能由VFX操作者自行宣布完成，应保留原始输出、将改变记录为新派生，返回C／用户决定是否重生成或接受新的表演。

### 反例：代理预览被当作最终Plate

Offline代理包含烘焙Look、压缩和临时缩放，供应方直接据此生成高分辨率修复。返回画面虽然尺寸足够，却继承了双重Look和代理伪影。问题根因是父素材身份错误；应回到正确高质量Plate和Color Recipe，做最小Roundtrip后再继续。

## 专业职责与工具边界

下表用于说明专业职责与创作取舍。已有采用方向和本次授权直接复用；普通专业步骤由岗位处理，新的重要创作取舍随完整候选统一审阅。每一行不构成独立审批门。

### Agent可以承担

- 从当前CUT和问题清单提出Spotting候选，但不自动创建采用Shot。
- 提取文件事实、帧率、时长、范围、Hash、父子关系和Version差异。
- 检查Shot、Plate、Version、CUT、批准和实际插入之间是否存在缺项或冲突。
- 对静帧差异、闪烁、边缘、黑帧、分辨率、Alpha、色彩标签和旧Version提供候选异常。
- 草拟Turnover、Submission Note、Review Note、Change／Reconform影响和Tracker更新。
- 在明确工具与授权下生成WIP候选，并保留真实输入、输出、模型和失败信息。
- 对批准Final和Online插入文件做字节、元数据与抽样差异核对。

### 必须由人确认

- 是否真的需要VFX，以及Scope、完成标准和创作优先级。
- 角色、表演、空间、资产、镜头和故事事实是否允许改变。
- WIP的方向是否成立，哪个Note必须修改，哪些限制可以接受。
- 哪个精确Version在当前CUT上下文中成为Approved Final。
- AI生成式修复的语义改变、身份、同意与残余风险。
- Grade、VFX、Online或返回C的最终路由。
- PIC是否可冻结，以及整片观看中该镜头是否真正不抢戏、不掉戏。

### Agent不得声称

- 只看单帧或代理就声称上下文审片通过。
- 文件名含Final就声称已获批准。
- 自动检查无报错就声称创作、表演或合成自然。
- 没有实际打开媒体就声称已审看、已插入或已回归。
- 生成模型完成输出就声称已替代原件、已采用或已进入PIC。
- 由技术修复推导出权利已清、可发布或真实项目已经验证。

## 小项目的适用范围

每支片只在VFX被触发时保留：

1. 当前CUT上的VFX Spotting清单和明确路由。
2. 每个逻辑镜头一个稳定Shot ID；Shot与Version分开。
3. Scope、必须保留项和可观察完成标准。
4. 父Plate／Element、Active Frame、Handle状态、参考和Color Recipe。
5. 一份实际被接收的轻量Turnover。
6. 每个WIP／Final-labelled Version的文件、父对象和提交说明。
7. 绑定精确Version、帧段和上下文的Review Notes。
8. CUT或Plate变化时的修改、Repull／Reconform与批准失效记录。
9. 用户批准的唯一Final Version及已知限制。
10. Approved Final实际插入当前CUT后的DI／Grade／Online回归。
11. PIC冻结时的Final Hash、直接依赖、Tracker快照和最小恢复入口。

停止条件：

- 当前CUT、Shot或父Plate身份不明确；
- 只有静帧、截图或代理，无法完成所需运动审片；
- Scope会改变人物、表演、资产、空间或故事事实，但没有用户确认；
- CUT已经变化却未Reconform，或Handle不足却未Repull；
- 只收到WIP／Final标签，没有精确Version批准；
- Color Recipe、Alpha角色或插入方式不明，无法解释返回结果；
- Approved Final尚未真正进入当前CUT；
- 没有真实文件、播放、回读或回归证据，却被要求写“通过”；
- 维护字段多到超过实际审片和返修收益时，停止扩表并回到事件触发最小项。

## 常见误区

- “有最终文件就完成了”：Final文件必须能回到Shot、Plate、Version、批准和当前CUT。
- “版本号最大就是当前版”：版本号只表示提交序列，不表示用户批准、当前CUT适配或已插入。
- “看一帧没问题就能过”：运动、边缘、节奏和连续性必须在上下文中判断。
- “代理只是小一点”：代理可能含压缩、裁切、缩放、烘焙Look和临时效果，不能默认当Plate。
- “VFX能修就不必回C”：改变表演、资产、空间或故事事实时，应回到创作责任层。
- “AI修复不是新素材”：任何生成式改变都形成新派生和新审查对象。
- “用户批准等于Online通过”：批准解决创作采用，插入与技术回归仍是后续门。
- “Online可以顺手改内容”：Online若改变已批准VFX像素，应建立新Version并重新审查。
- “Handles越多越专业”：余量服从真实需求；固定数字不能替代CUT稳定度和接收契约。
- “OPC也要复制大型VFX数据库”：OPC需要稳定对象和事件证据，不需要空字段、供应商成本系统或设施级状态搬运。

## 外部补充与分歧

- 外部来源：阶段7汇编内的ScreenSkills VFX Editor、ScreenSkills Online Editor及Netflix三份VFX制作资料。
- 检索日期：2026-08-10。
- 可靠性：ScreenSkills用于职业功能边界；Netflix用于平台制作环境中的Shot／Version、Review与Plate可追溯实践；两者均为一手／官方职业资料。
- 多源一致：VFX不能只追踪文件，要追踪Shot、Version、Plate、审片、Notes、Final插入和下游核对；当前CUT与批准状态是共同基线。
- 来源补充：ScreenSkills给出编辑、Turnover、Repull、DI与归档的连续职责；Netflix把命名、媒体审片和Plate身份拆得更细；阶段7把这些压缩为OPC事件触发Tracker。
- 不能外推：Netflix命名、Review文件规格和Plate编号不等于全球通则；ScreenSkills岗位划分不要求OPC建立同样人员编制。
- Codex综合：Grade／VFX／Online／C路由表、轻量Tracker和11项OPC第一圈是对多来源的当前压缩，不是行业标准。
- 不确定性：尚未验证一人维护Tracker的实际时间、Agent异常检查的误报、真实Plate Repull、锁画改版和最终恢复成本。

## 不能泛化的规则

- 不存在统一Shot名称、Version位数、文件夹结构或状态词。
- 不存在适用于所有镜头的Handles帧数、Plate格式、分辨率、位深、Alpha或色彩编码。
- WIP、Final、Approved、Omitted、On Hold和Superseded的术语由项目定义；本主题约束的是逻辑差异。
- Shot是否在范围根本变化后沿用ID，需按项目与接收方规则决定。
- Online、VFX、Grade、GFX和DI的人员、软件、顺序与交付轮次会随规模变化。
- 静帧、代理、低码率Review和高质量Final各能证明的内容不同，不给出统一审看设备或放大倍率。
- AI生成式修复需要身份和父子关系，但模型可提供的版本、Seed、凭证或标识字段并不一致。
- PIC冻结、Final Cut、Locked Cut与Master的术语因项目和地区不同，必须在当前项目中定义。
- 本主题的OPC Tracker和事件门不是已采用v0.8设计，也未经真实项目证明更高效。

## 相关知识

- 前置接口：素材接受与Picture Lock提供当前CUT、父素材、时间基线和锁画改版门。
- 色彩接口：源色彩身份与调色输出提供Plate像素解释、Color Recipe、参考View和Stage5专项QC。
- 创作接口：创作调色主题负责把生成缺陷分流到Grade、VFX、Online或返回C。
- 下游接口：成片完成主题负责接收Approved Final、完成Online汇合、PIC冻结、母版QC和恢复。
- 当前仅保留接口说明；本轮不建立正式主题关系，YAML相关主题保持为空。

## 方法摘要

### 一分钟核心摘要

VFX完成是一条对象生命周期，不是收到一个Final文件。先在当前CUT中Spotting并分流，再给逻辑镜头稳定Shot ID，定义Scope，绑定Plate、Element、Active Frame和Handle，完成Turnover。每个WIP或Final标签都只是具体Version，必须在单镜、前后镜头和段落上下文审看，Notes要绑定Version与帧段。普通修改产生新Version，父Plate或范围错误要Repull，CUT变化要Reconform。用户批准唯一Final后，Online把它插回当前CUT，并与DI／Grade核对到PIC冻结。代理不是最终Plate，单帧漂亮不是上下文通过，AI生成式修复是新派生且不能静默改变创作事实。

### 关键概念

- VFX Spotting与责任路由
- Shot ID与Version分离
- Scope与可观察完成标准
- Plate、Element、Active Frame与Handle
- Turnover与接收证据
- WIP、Final-labelled与Approved Final
- 上下文审片与版本化Notes
- 修改、Repull与Reconform
- AI生成式修复派生身份
- Final插入、DI／Grade／Online回归
- PIC冻结与最小恢复

## 岗位接口

D说明Grade、VFX与Online各自能修什么；人物、资产、动作、空间和镜头事实改变交C2统合，资产问题与C1核对。技术修复产生新派生，不自行继承原素材采用状态。

文中的版本确认、批准与冻结用于解释正式采用或交付所需的对象关系；方案咨询和候选返修不因此新增逐项用户审批。D可与相关专业直接交换受限意见，实际权限和保存方式沿用项目当前规范。传统多岗位方法转到AI制作时，只保留真实需求触发的功能，不复制设施编制、所有表格或固定参数。

## 项目应用与验证

当前状态：本轮完成既有专业内容的岗位转译，未在真实项目中执行或验证效果。正文中的案例分别沿用其原有身份：作者／机构案例、教学构造、条件算例或本体系综合；不登记为小陌的真实制作结果。

实际使用时，以当前对象、精确版本及必要的正常速度声画／文件检查，比较一种有理由的最小候选与原方案，记录方法前提是否满足、收益与代价、未观察项。文本判断、哈希、结构校验与检索命中各自只证明对应范围；没有真实媒体观察、实际回读或恢复操作时，不升级为创作通过、交付通过或实践验证。

以下保留原稿具有专业内容的验证方法，属于真实任务触发后可选的验证设计，不是本轮已执行事项，也不自动增加用户练习或项目任务。

### 最小验证协议

1. 选择一支有真实可播放CUT且确实需要VFX的短片，不为了测试虚构大量Shot。
2. 为一个镜头建立轻量Tracker和Turnover，保存正确Plate与一个代理参考。
3. 生成或接收至少两个Version，其中一个故意保留可观察问题。
4. 分别做静帧、单镜循环、前后镜头和段落审片，记录各自发现的问题。
5. 人工注入一次旧WIP或旧Final，检查Tracker、Agent和人工上下文审片谁能发现。
6. 改一个切点或时长，执行Reconform；Handle不足时执行Repull。
7. 用户批准精确Final，插入当前CUT并完成Grade／Online回归。
8. 从工作路径之外验证Final、父Plate、直接依赖和说明能否被识别、重连或重新输出。
9. 记录维护成本、拦错收益、误报与阻塞；收益不足时删减字段，不以“更专业”为理由保留。

在真实媒体、工具、完整审片和恢复证据出现前，本主题只能保持知识已提炼、多源互证、项目待验证。
