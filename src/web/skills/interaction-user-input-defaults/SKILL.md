---
name: interaction-user-input-defaults
description: Use when synchronizing interactive Markdown state between ai-shifu and markdown-flow-ui. Persist raw user_input, pass userInput to ContentRender or MarkdownFlow, and let markdown-flow-ui derive button, input, and selected-option defaults instead of parsing them again in business code.
---

# 交互输入默认值（`user_input`）

## 核心规则

在应用层模型中以原始 `user_input` 保存交互状态，并向下传递给 markdown-flow-ui。
不要在业务代码中重复实现 `user_input -> defaultButtonText/defaultInputText/defaultSelectedValues` 的解析逻辑。
“是否重新生成”的判定必须基于最后一个真实业务 element（如 content/interaction），不能直接使用列表尾项；需要排除 `LIKE_STATUS`、`ASK`、`loading` 等辅助项。

## 工作流

1. 当交互状态来自 `OnSendContentParams` 时，只做一次转换，得到稳定的 `user_input` 字符串。
2. 将该 `user_input` 保存到聊天项或预览项。
3. 通过带 `userInput` 的 `ContentRender` 或 `MarkdownFlow` 渲染交互内容。
4. 将仅业务相关的解析独立处理，例如课程反馈的评分/评语提取。
5. 如果相同交互序列化逻辑在多个文件出现，把它抽到共享工具函数。

## 备注

- 优先提供共享序列化器，统一处理 `selectedValues`、`inputText`、`buttonText`。
- 让 markdown-flow-ui 负责按钮默认值、自由文本默认值、多选默认值的还原。
- 对课程反馈这类结构化负载，持久化的 `user_input` 要可序列化，以便 UI 默认值稳定恢复。
