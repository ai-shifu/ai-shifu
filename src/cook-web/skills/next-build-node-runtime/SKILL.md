---
name: next-build-node-runtime
description: 当 cook-web 执行 npm run build 出现 SyntaxError Unexpected token '?' 或 next/dist/compiled 报错时使用本技能，优先排查 Node 运行时版本不一致问题。
---

# Next Build Node 运行时排障

## 触发条件

- `npm run build` 在 `next/dist/compiled` 内部文件报语法错误。
- 报错包含 `SyntaxError: Unexpected token '?'`、`Unexpected token '.'` 等现代语法不兼容信息。
- 构建日志中 Warning 很多，但实际中断点不明确。

## 工作流

1. 在当前目录分别检查运行时版本与路径：`node -v`、`npm -v`、`which node`、`which npm`。
2. 对照 `package.json` 的 `engines.node`，确认是否匹配。
3. 如果 shell 初始化脚本切到了旧 Node，先切到项目要求版本再重新执行 `npm run build`。
4. 构建失败时只抓第一个 `Error` 作为阻断点，不把 `Warning` 当作失败原因。
5. 若阻断点是 ESLint `Error`，做最小改动修复；保留调试日志，不删除 `console.log`。

