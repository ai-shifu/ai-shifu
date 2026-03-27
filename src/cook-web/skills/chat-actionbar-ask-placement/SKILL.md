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
- 移动端不能把 `LIKE_STATUS` 一刀切隐藏；至少要为 `interaction` 元素保留追问入口，保证与 PC 的追问能力一致。
- 移动端阅读模式下，`interaction` 的追问按钮样式应与正文 `custom-button-after-content` 的追问按钮保持一致；PC 端维持原有桌面样式。
- 当追问操作栏挂在 `interaction` 元素后方时，需要移除操作栏顶部额外间距（如 `padding-top`），避免与交互块之间出现空白断层。
- 当需求要求“按接口顺序直接展示内容与追问”时，不要额外引入 `readyElementBids`、`onTypeFinished` 等前端渲染门禁。
- 交互块触发 `onSend` 且需要截断后续内容时，必须保留该交互块关联的辅助行（`LIKE_STATUS` / `ASK`），避免进入思考中后追问入口消失。
- 后台调试/预览链路中收到 `interaction` 时，也要为该 `interaction` 本身补齐 `LIKE_STATUS`，否则追问按钮不会渲染。
- 重生成判定不能直接依赖“列表最后一项”；应忽略 `LIKE_STATUS`/`ASK` 等辅助行，按“最后可操作元素”判断，避免点击末尾交互块误弹重生成确认框。
- 预览链路里 `updateContentListWithUserOperate` 在截断列表时，也要保留当前 `interaction` 关联的 `LIKE_STATUS/ASK`（按 `parent_block_bid/parent_element_bid` 匹配），避免选择后追问入口消失。
- interaction 提交值组装时要去重并保序（如 `selectedValues + buttonText` 同值场景），避免变量被写成 `ENFJ,ENFJ` 这类重复值。

## 工作流

1. `toggleAskExpanded` 先执行同父级 `ASK` 去重，再切换展开态。
2. 移除按钮时同步移除对应数据注入，避免空白操作栏。
3. 移动端长按菜单在“无可展示动作”时不弹空菜单。
4. 对 `sys_lesson_feedback_score` 这类隐藏正文的 interaction，同步隐藏操作栏。
5. 为 `ContentRender/IframeSandbox` 增加渲染完成回调并向上透传到 `ChatUi`。
6. `onTypeFinished` 要覆盖普通 markdown 与 `sandbox/iframe` 两条渲染路径。

## 备注

- 阅读模式下桌面端追问操作栏继续挂在 `LIKE_STATUS`，避免正文未就绪时按钮先出现。
