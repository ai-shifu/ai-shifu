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

## 备注

- 当同一答案分多次快照回传且 `element_bid` 相同，必须覆盖同一条消息。
- 字段重构从 `*BlockBid*` 到 `*ElementBid*` 后，消费方解构与依赖数组必须同步改名。
