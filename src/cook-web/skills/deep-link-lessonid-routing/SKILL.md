---
name: deep-link-lessonid-routing
description: 当 cook-web 需要按 URL 深链定位课节并保持学习端与后台端行为一致时使用本技能。统一使用 lessonid 参数、复用目录点击拦截链路，并覆盖登录/付费/无效课节兜底。
---

# 深链课节定位（`lessonid`）

## 核心规则

- 学习端与后台端统一使用 `lessonid` 作为 URL 参数名。
- 课节解析必须走统一 URL 工具函数，避免页面手写解析逻辑。
- 定位优先级固定为：`lessonid` > store 当前状态 > 默认可学习课节。
- 用户显式切换课节后要同步回写 `lessonid`，并优先使用 `replace` 语义避免目录点击污染浏览历史。
- 后台编辑页仅在当前节点为 lesson 时回写 `lessonid`，避免把 chapter id 写入课节深链。

## 工作流

1. 在 `/c/:courseId`、`/shifu/:courseId` 初始化时优先读取 `lessonid`。
2. `lessonid` 变更时触发课节树重新定位，避免沿用旧缓存。
3. 命中课节后复用目录点击同一套权限拦截。
4. 目录点击、章节重置、课节兜底修正后都要把当前有效课节回写到 URL。
5. 需要登录时跳登录页并保留 `redirect`。
6. 付费未购时弹支付窗并带 `chapterId`、`lessonId`。
7. 无效 `lessonid` 兜底到默认可学习课节。

## 验收清单

- 已登录未购课节。
- 未登录课节。
- 有效 `lessonid`。
- 无效 `lessonid`。
- 学习端与后台端两条路由均通过。
