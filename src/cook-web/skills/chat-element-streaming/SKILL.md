---
name: chat-element-streaming
description: 当 ai-shifu 聊天流从 block 粒度向 element 粒度演进，或历史记录与 SSE 渲染一致性出现问题时使用本技能。统一 element_bid 渲染键、兼容旧字段并收敛 AskBlock 归并逻辑。
---

# Element 粒度聊天流

## 核心规则

- 使用 `element_bid` 作为聊天项稳定渲染 key。
- 在数据归一化入口保留 `generated_block_bid`、`parent_block_bid` 兼容字段。
- 历史 records 与实时 SSE 共用同一条转换路径，产出一致的 `contentList`。

## 工作流

1. 接收 SSE `type=element` 时按 `element_bid` 覆盖更新，不做重复拼接。
2. 对追问流 `element_type=answer`，让 `AskBlock` 按答案流增量更新。
3. 学习记录返回 `element_type=ask/answer` 时，归并到 `anchor_element_bid` 对应的 `AskBlock.ask_list`。
4. AskBlock 落位以接口返回顺序（`sequence`）为准，不强制锚定在 anchor 内容后。
5. 在统一归一化层回填旧字段，避免兼容逻辑散落到渲染层。
6. 调试预览链路若切换到 `type=element` + `type=done`，需按 `element_bid` 覆盖更新元素项，并将 `done` 作为唯一收尾信号。
7. SSE 包体字段需同时兼容 `type/event_type` 与 `content/data` 两套命名，避免后端灰度期间前端丢流。
8. 当调试流未返回 `done` 但出现多个 `element_bid` 时，以“新 element 到达”作为前一个 element 的结束信号，并立即补一个追问块（like-status/ask入口）。
9. 学习页、预览页、调试页处理 `type=done` 时，优先读取 `done.is_terminal` 判断它是“当前分段结束”还是“真正终态”；字段缺失时才回退到旧的前端推断。
10. `done` 收尾补追问块时，锚点应取“最近的可操作 element（content 或 interaction）”，否则最后一项为 interaction 时会漏补追问块。
11. 若后端出现 `done` 与后续 `element` 乱序，边界判定不能只依赖 streaming ref，需增加“从当前列表尾部推断上一个可操作 element”的兜底逻辑，避免中间 element 漏补追问块。
12. 若后端直接关闭预览 SSE，前端应把“最后一个可操作 element 不是 interaction”视为可续拉信号，自动发起下一次预览请求；但若最近一次 `done.is_terminal=true`，则必须停止续拉。
13. 预览链路收到 `type=done` 时，不要默认立即 `stopPreview`；仅当 `done.is_terminal=true` 才关闭当前预览流。关闭后若最后一个可操作块不是 `interaction`，应继续拉取下一段流。
14. 当需要在 `ai-shifu` 本地稳定复现 `run` SSE 卡住问题时，优先在 `getRunMessage` 层增加显式调试开关，回放由 `data.json` 截断得到的 stuck fixture，并保持 `message/readystatechange/close` 契约不变；不要把页面组件改成只兼容 mock 数据。
15. 学习页 `run` 流若在 3 秒内没有任何新事件，前端应在消费层主动判定为超时：关闭当前流与 loading 状态、向 `items/elementList` 追加 `type=error` 的错误项，并复用同一份国际化文案弹 destructive toast。
16. 听课模式 `Slide` 遇到超时错误时，只把它当作“关闭内部 loading overlay”的信号，不要把错误项渲染成单独一页；用户侧错误提示统一交给 toast。
17. 阅读模式同样不要把超时错误项渲染进正文列表；错误项可以保留在内部状态里供控制逻辑使用，但用户可见反馈只保留 toast。

## 备注

- 当同一答案分多次快照回传且 `element_bid` 相同，必须覆盖同一条消息。
- 字段重构从 `*BlockBid*` 到 `*ElementBid*` 后，消费方解构与依赖数组必须同步改名。
