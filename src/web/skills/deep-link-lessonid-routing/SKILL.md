---
name: deep-link-lessonid-routing
description: 当 Cook Web 需要按 URL 深链定位课节并保持学习端与后台端行为一致时使用本技能。统一使用 lessonid 参数、复用目录点击拦截链路，并覆盖登录/付费/无效课节兜底，以及 debug=1 初始化和鉴权恢复排查。
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

## Learner debug console workflow

For QA or operations troubleshooting of `/c/:courseId` initialization, add
`debug=1` to the existing URL query while preserving `lessonid`, mode and other
reproduction parameters. `src/app/c/[[...id]]/page.tsx` enables
`src/components/debug/DebugConsoleOverlay.tsx` only for the exact value `1`;
`src/lib/debugConsole.ts` uses the same query gate for diagnostic emission.
Removing the parameter disables the overlay and gated diagnostics.

Inspect the complete chain when changing troubleshooting behavior:

- `src/lib/request.ts` emits selected request diagnostics via
  `REQUEST_DEBUG_PATTERNS` and `shouldLogRequestDebug`, plus the auth-chain
  diagnostics for business codes `1001`, `1004` and `1005`. Follow recovery
  start/skip/finish, token-change cancellation and any login redirect rather
  than treating every auth response as a new logout.
- Learner `page.tsx` and hooks such as `hooks/useLessonTree.ts` emit page and
  initialization diagnostics through the shared debug helpers.
- The overlay captures console log/info/warn/error calls after mounting,
  retains the latest 200 entries and offers clear/collapse controls. It cannot
  recover console output emitted before it mounted. Do not claim it is a
  complete initialization trace or a persisted log service.

Keep the URL gate, request/auth diagnostics and page instrumentation aligned;
changing only the overlay or relying only on a remote console drops part of
this reproduction workflow. Preserve existing token masking in request
summaries. The overlay also captures ordinary console output, and formatting
truncates rather than sanitizes it; inspect/redact diagnostic material before
sharing it and do not add credentials to instrumentation.

`src/lib/request.test.ts` covers request tracing and pre-stream business-error
handling, not the debug query/overlay or the full auth-recovery sequence. When
changing the debugging flow, verify with and without `debug=1`, a selected
request, an auth-recovery path and lesson-tree initialization; check that the
console capture is restored on disable/unmount and that diagnostics do not
change the underlying request behavior.
