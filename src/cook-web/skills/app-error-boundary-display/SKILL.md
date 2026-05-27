---
name: app-error-boundary-display
description: 当 cook-web 需要调整 Next.js App Router 全局或路由级错误兜底页时使用本技能。错误页应直接展示错误名称、message、digest、cause、URL 和可用 stack，避免只提示用户查看控制台。
---

# 应用错误兜底展示

## 核心规则

- App Router 的兜底错误页需要同时覆盖 `src/app/error.tsx` 和 `src/app/global-error.tsx`；前者处理路由段错误，后者处理根布局或更外层错误。
- 错误展示 UI 优先收敛到共享组件，避免全局错误页和路由错误页各自维护不同字段和样式。
- 错误信息至少展示 `name`、`message`、`digest`、`cause`、当前 URL；有 `stack` 时可截断后直接展示，便于截图定位。
- 复制错误信息时需要额外带上当前链接、来源链接和简要浏览器环境；浏览器环境只保留浏览器名称与操作系统，不要复制用户信息、token 或密码等敏感凭证。
- `global-error.tsx` 需要自己返回 `<html>` 和 `<body>`，不要依赖根布局里的 Provider、i18n 或运行时配置已经初始化。
- 错误兜底组件不要静态 import `@/store` barrel，避免错误页加载时触发 unrelated store 的模块副作用。
- 兜底页样式优先使用 Tailwind class 和现有主题变量，不要引入硬编码色值；高度使用 `dvh`，不要使用 `vh` 或 `env(safe-area-inset-bottom)`。
- 这类兜底页允许提供最小静态文案，因为它可能在 i18n 初始化失败前渲染；不要把排障关键信息藏到只在控制台可见。

## 工作流

1. 先确认问题是 App Router 默认错误页，而不是业务组件内部已有错误态。
2. 新增或修改共享错误兜底组件，统一格式化错误字段、浏览器字段和复制文本。
3. 同步接入 `src/app/error.tsx` 与 `src/app/global-error.tsx`。
4. 若错误页需要访问浏览器对象，必须放在 client component 中，并用事件或 effect 读取，避免服务端渲染阶段访问 `window`、`document` 或触发 store 初始化副作用。
5. 修改后至少运行 `npm run type-check`，确认 App Router 特殊文件签名和 client component 类型通过。
