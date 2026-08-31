---
name: module-augmentation-guardrails
description: 当 TypeScript 对子路径导出出现类型丢失或声明冲突时使用本技能。通过规范的 module augmentation 写法避免覆盖上游导出。
---

# TypeScript 模块增强防护

## 核心规则

- 改类型前先核对 `node_modules` 中发布版声明文件。
- augmentation 文件必须包含顶层 `import "package/subpath";` 与 `export {};`。
- 仅增强已导出的 interface；非 interface 结构优先用本地 wrapper 类型。
- 为子路径组件补扩展 props 时，要 augment 到真实导出子路径（如 `markdown-flow-ui/slide`），不要误写到相邻模块导致类型表面可用、运行接入点却不生效。

## 工作流

1. 先确认是上游类型问题还是本地声明覆盖导致。
2. 在 augmentation 中显式引入依赖类型（如 `InteractionDefaultValueOptions`）。
3. 避免在 `.d.ts` 里重写整个模块结构。
4. 变更后执行定向类型检查，确认导出成员未丢失。
5. 若扩展字段依赖 React 类型（如 `ReactNode`），在声明文件顶层显式 `import type`，避免 TS 在模块增强中退化成 `any`。
