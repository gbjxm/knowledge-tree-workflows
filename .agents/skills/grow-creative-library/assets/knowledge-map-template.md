---
类型: 知识地图
分类:
状态: 持续维护
材料类型: 知识库导航
信息来源: 知识库内部
完整程度: 持续积累
整理日期: YYYY-MM-DD
知识库版本: 2.1
主题域:
适用阶段: []
---

# 地图名称

> 这张专业索引帮助我按问题找到真实知识入口；同时显示物理归位。学习区链接是导航，不自动进入创作调用。

<!-- 六类专业地图存于 knowledge_library/00-待归档与知识地图/专业索引；路径由共享配置解析。 -->

## 当前学习重点

- 本分类当前最需要回答的核心问题：
- 它与 [[我的知识树北极星]] 的关系：
- 本轮只推进的一个动作：

## 按创作阶段调用

- 灵感与命题：
- 故事骨架：
- 剧本开发：
- 视觉设计：
- 资产与提示词：
- 生成与镜头：
- 剪辑与声音：
- 复盘与方法升级：

## 知识骨架

| 子域 | 要回答的核心问题 | 已有入口 | 覆盖状态 |
|---|---|---|---|
|  |  | 待补 | 空白 |

## 真实知识入口

```dataview
TABLE file.folder AS "物理归位", 解决问题 AS "解决问题", 适用阶段 AS "适用阶段", 知识状态 AS "知识状态", 成熟度 AS "成熟度"
WHERE 类型 = "主题笔记" AND 分类 = this.分类
SORT file.name ASC
```

## 跨域调用

```dataview
TABLE file.folder AS "物理归位", 分类 AS "主分类", 涉及分类 AS "涉及分类", 解决问题 AS "解决问题", 相关主题 AS "已确认连接"
WHERE 类型 = "主题笔记" AND 涉及分类 AND length(涉及分类) > 1 AND contains(涉及分类, this.分类)
SORT file.name ASC
```

## 待提炼材料

以下为已有沉淀状态的诊断视图；学习来源没有创作主题不代表入库失败，不据此自动转入创作区。

```dataview
TABLE 类型 AS "材料", 分类 AS "分类", 沉淀状态 AS "沉淀状态", file.mtime AS "最近更新"
WHERE contains(list("材料总览", "分集笔记"), 类型) AND (!沉淀状态 OR 沉淀状态 != "已沉淀")
SORT file.mtime DESC
```

## 待复习与练习

### 知识复习

```tasks
not done
tags include #复习
sort by path
```

### 创作练习

```tasks
not done
tags include #创作练习
sort by path
```

### 当前创作问题

```tasks
not done
tags include #创作问题
sort by path
```

## 最近的项目反馈

```dataview
TABLE 项目 AS "项目", 项目阶段 AS "阶段", 验证状态 AS "结果", 复盘日期 AS "复盘日期"
WHERE 类型 = "项目应用"
SORT 复盘日期 DESC
LIMIT 10
```
