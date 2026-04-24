---
name: shared-loading-dots
description: 当 cook-web 需要新增共享 loading 动画时，使用本技能统一公共组件目录、非破坏性导出方式，以及圆点序列动画的可配置实现。
---

# 共享圆点 Loading

## 核心规则

- 共享 loading 优先放在 `src/components/loading/`，并通过 `index.ts` 统一导出，避免调用方自行散落实现。
- 新增 loading 样式时，优先追加命名导出，不要直接替换默认 `Loading`，除非全站调用方已经确认要整体迁移。
- 圆点 loading 至少暴露 `count`、`size`、`gap`、`durationMs` 这类基础配置，保证同一动画能适配按钮内、局部块和页面级场景。
- 动画颜色优先复用 Tailwind 中已接入的主题变量，例如 `bg-primary`，不要在组件里直接写十六进制颜色。
- 动画实现优先复用 Tailwind 配置里的 `keyframes` 和 `animation`，只有 Tailwind 无法覆盖时再补局部样式文件。
- 如果业务目录里已经存在本地“空占位” loading 包装组件，例如聊天页的 `LoadingBar`，不要直接替换；优先保留原占位 loading，再把共享圆点 loading 接到内容已开始输出但流尚未结束的阶段。

## 工作流

1. 先检查 `src/components/loading/` 下是否已有默认 loading 和 barrel export，评估是否应该新增命名组件而不是改旧组件。
2. 若动画需要复用，优先把节奏、大小、间距做成 props，并通过共享工具方法兜底非法入参。
3. 如果动画依赖自定义关键帧，优先在 `tailwind.config.ts` 中注册，保证 JSX 中仍以 tailwind classname 为主。
4. 修改导出后，补最小渲染测试，至少覆盖默认圆点数量和一组自定义 props。
5. 若本次沉淀出可复用约束，同时更新 `src/cook-web/SKILL.md` 索引，避免后续重复约定。

## 验证要点

- 默认 `Loading` 不受影响，新增圆点 loading 能通过命名导出被调用。
- 圆点数量、尺寸、间距和动画时长在 props 变更后能稳定生效。
- 组件颜色跟随主题变量，不引入硬编码颜色。
- 至少完成一次针对该组件的测试或静态校验，避免公共导出破坏现有调用方。
