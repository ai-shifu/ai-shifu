---
name: module-augmentation-guardrails
description: 当 TypeScript 对子路径导出出现类型丢失或声明冲突时使用本技能。通过规范的 module augmentation 写法避免覆盖上游导出。
---

# TypeScript 模块增强防护

## 核心规则

- 改类型前先核对 `node_modules` 中发布版声明文件。
- augmentation 文件必须包含顶层 `import "package/subpath";` 与 `export {};`。
- 仅增强已导出的 interface；非 interface 结构优先用本地 wrapper 类型。

## 工作流

1. 先确认是上游类型问题还是本地声明覆盖导致。
2. 在 augmentation 中显式引入依赖类型（如 `InteractionDefaultValueOptions`）。
3. 避免在 `.d.ts` 里重写整个模块结构。
4. 变更后执行定向类型检查，确认导出成员未丢失。
