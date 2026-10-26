---
name: hook-contract-refactor-safety
description: Use when refactoring hook return fields or parameter contracts. Update caller destructuring and argument objects together to prevent TypeScript property errors.
---

# Hook 契约重构安全

## 核心规则

- 公共 hook 字段改名后，消费方必须同批次同步改名。
- hook 删除参数后，调用对象中的旧字段必须同步移除。

## 工作流

1. 先在 hook 导出类型上完成改名或删参。
2. 全局检索调用点并同步更新解构、索引、依赖数组。
3. 清理对象字面量中的未知属性。
4. 运行定向 `tsc` 或相关测试，确保契约收敛。
