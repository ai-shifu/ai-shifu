---
name: chat-actionbar-ask-placement
description: 当调整聊天操作栏、追问入口和 AskBlock 锚点时使用本技能。确保内容与操作入口同步出现，避免双输入框、空菜单和错位展示。
---

# 操作栏与追问锚点

## 核心规则

- 同一 `parent_element_bid` 仅允许存在一个 `ASK` 项。
- `ASK` 优先插入 `LIKE_STATUS` 后方，缺失时回退到内容块后方。
- 追问操作栏显示时机必须和内容可见时机保持同步。
- 移动端自动归并的历史/SSE 追问默认保持折叠，仅在用户主动点击追问入口后展开。

## 工作流

1. `toggleAskExpanded` 先执行同父级 `ASK` 去重，再切换展开态。
2. 移除按钮时同步移除对应数据注入，避免空白操作栏。
3. 移动端长按菜单在“无可展示动作”时不弹空菜单。
4. 对 `sys_lesson_feedback_score` 这类隐藏正文的 interaction，同步隐藏操作栏。
5. 为 `ContentRender/IframeSandbox` 增加渲染完成回调并向上透传到 `ChatUi`。
6. `onTypeFinished` 要覆盖普通 markdown 与 `sandbox/iframe` 两条渲染路径。

## 备注

- 阅读模式下桌面端追问操作栏继续挂在 `LIKE_STATUS`，避免正文未就绪时按钮先出现。
