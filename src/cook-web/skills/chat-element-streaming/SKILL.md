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
14. 当需要在 `ai-shifu` 本地稳定复现 `run` SSE 问题时，优先在 `getRunMessage` 层增加显式调试开关；`mock_run_sse_fixture=stuck` 回放由 `data.json` 截断得到的卡住 fixture，`mock_run_sse_fixture=test` 回放 `mock-fixtures/test/data.json` 的完整测试流，并保持 `message/readystatechange/close` 契约不变；不要把页面组件改成只兼容 mock 数据。
15. 学习页 `run` 流若在 3 秒内没有任何新事件，前端应在消费层主动判定为超时：关闭当前流与 loading 状态、向 `items/elementList` 追加 `type=error` 的错误项，并复用同一份国际化文案弹 destructive toast。
16. 听课模式 `Slide` 遇到超时错误时，只把它当作“关闭内部 loading overlay”的信号，不要把错误项渲染成单独一页；用户侧错误提示统一交给 toast。
17. 阅读模式同样不要把超时错误项渲染进正文列表；错误项可以保留在内部状态里供控制逻辑使用，但用户可见反馈只保留 toast。
18. 阅读模式的流式点状 loading 应作为列表尾部状态渲染在最后一个 element 后面，不要绑定到当前流式 element 内部，否则 `html` 视觉 marker 更新时容易把 loading 插到两个 element 的视觉边界之间；但当 `loading` 思考占位仍在列表中时，不要同时显示点状 loading。
19. 阅读模式若要给 `markdown-flow-ui` 的 `ContentRender` 打开打字机效果，应只对“非历史记录、且 `element_type === text`”的实时正文块开启；`html`、`interaction` 和历史正文继续即时渲染，优先在 `ContentBlock` 这类渲染包装层集中判断，不要把条件散落到列表组装逻辑里。
20. 当阅读模式在消费层已经明确知道某个 `element` 被 `done` 或“下一个 element 到达”收尾时，要同步把本地 `ChatContentItem.is_final` 置为 `true`；不要让列表状态长期停留在早先 SSE 快照里的 `false`。
21. 阅读模式如果要阻止“前一个 text 还在打字机播放、后一个 element 已经出现”，优先在 `NewChatComp` 上层维护 `readModeItems` 的可见列表缓存和按 `element_bid` 存储的打字机完成态；只有前一个 text 同时满足“`is_final=true` 且当前 content 的打字机回调已完成”时，才放行下一个 element。
22. 移动端阅读模式若会在 `element` 收尾时给正文 `content` 追加追问按钮或把块改成 `isHistory=true`，不要让这个“收尾态 content”继续复用同一条 typewriter gate 缓存；否则缓存会因 `content` 变化被重置成未完成，而 `ContentRender` 又因为不再启用打字机而不会补发 `onTypeFinished`，最终把后续 element 永久卡住。
23. `isHistory` 只表示“来自学习记录/历史回放的数据”，不要把它当作运行时 UI 控制位复用；`run` SSE 覆盖已有历史项时，也不要从 `previousItem` 继承 `isHistory`，否则实时流会被误判成历史数据。
24. 阅读模式打字机和 `elementList` 可见性 gate 不要直接依赖 `isHistory`；应使用独立的 typewriter 候选标记，仅让“真正参与实时打字机的 text element”进入缓存与阻塞链路，避免历史首块被 SSE 覆盖后误拦住后续 element。
25. 一旦前端已经根据 `done` 或“下一个 element 到达”把某个元素标记为 `is_final=true`，后续同 `element_bid` 的 SSE `element` 快照不能再用旧的 `is_final=false/undefined` 覆盖回去；本地 finalize 语义优先级应高于早先快照字段。
26. 移动端 `custom-button-after-content` 只允许作为“打字结束后的静态尾部 UI”出现；打字机阶段传给渲染器的 content 必须先剥掉这段 markup，避免把追问按钮当正文逐字输出。
27. 非 `text` 的富内容块（如 `html`、`svg`、sandbox 相关内容）若需要尾部追问按钮，不要依赖内容字符串内部的 `custom-button-after-content` 首屏渲染；应把按钮从 content 中剥离后在外层独立渲染，避免正文未稳定时按钮先于正文或以异常结构闪现。
28. 只要 `StudyRecordItem` 这类共享记录类型被 SSE、历史记录和渲染层共同消费，就必须把 `is_final` 等流式收尾字段声明在共享接口里；不要仅在局部 UI 类型上兜底，否则 `next build` 很容易在跨层调用处报类型缺失。
29. 阅读模式不能只用 `cache.isFinished` 决定同一个 `element_bid` 是否继续打字；若当前归一化 content 已经比缓存快照更长，即使旧 cache 标记过完成，也必须继续给 `ContentRender` 打开 typewriter，否则后续增量首帧会直接整段落地。
30. 阅读模式判断“同一个 text element 是否需要再次进入打字机”时，不能把任意 content 差异都视为增量；只有“当前归一化 content 以缓存快照为前缀且长度更长”的真正追加场景才允许续打，避免收尾阶段的等价改写触发整段重打。
31. 同一个 `text element` 在 `is_final !== true` 的等待阶段，即使当前 chunk 已经打完，也不要先把 `enableTypewriter` 关掉；否则后续增量到达时会经历 `false -> true` 切换，`ContentRender` 会把已显示文本清空并从头重打。
32. 若流式链路在 `text_end/done` 后会自动续拉下一段，不能只依赖内存里的 `currentContentRef` 作为正文基线；下一轮 `content` 到达时应优先回填同一 `element_bid` 已渲染正文，并同时兼容“纯 delta”与“累计快照”两种 payload 语义，否则续流会把前一段正文覆盖掉并触发整段重打。
33. `AskBlock` 里的追问 answer 要把 `ContentRender.enableTypewriter` 当成“整条 answer 的会话状态”来保活，而不是把每个 `done/break` 都当成终态。非终态 `done(text_end)` 不能立刻 `finalize + close`，终态收尾时也不要顺手把 `shouldUseTypewriter` 改成 `false`，否则同一条 answer 后续再到 chunk 时就会从某一句开始整段直出。
34. `AskBlock` 本地 store 里若已经追加出比父层 `ask_list` 更长的追问历史，后续 `hydrateAskList` 不能再用更短的旧列表覆盖它；展开/收起、列表重排或重新渲染时都要优先保留较新的本地追问记录，否则收起后再展开会丢失刚刚流出来的追问问答。
35. 阅读模式若在 `text_end/done` 与下一段同 `element_bid` 文本续流之间存在等待期，尾部可见的那个 text element 不能先把 `enableTypewriter` 关掉；至少在本轮输出仍未结束时要保活这次打字机会话，避免后续追加文本到达时触发 `false -> true` 切换并把已显示正文清空重打。
36. 富内容块把 `custom-button-after-content` 从正文字符串里剥离后，如果改成在宿主层单独渲染追问按钮，按钮的横向布局与 `img/span` 对齐样式也要一起在宿主层显式声明；不要只依赖原先 custom element 场景下的 descendant selector，否则按钮容易在外层 DOM 变化后出现图标与文案错位或换行。
37. 阅读模式尾部 text 的打字机保活不能只依赖 `isOutputInProgress`；还要记录“当前这轮输出已经实际流到过哪个 element”。新一轮交互 `onSend` 刚启动、首个 element 尚未到达时，必须先清空上一轮的 keep-alive bid，避免旧正文被误判为当前流的一部分而再次整段打字。
38. 阅读模式打字机 keep-alive 的锚点不要回退到“上一轮残留的 text element”，但也不要被后续 `interaction/html` 抢走；它应绑定到“当前输出会话里最近一次参与打字机的 text element”。新一轮输出开始前先清空锚点，后续只有新的 text element 才能切换锚点，这样既能避免旧会话串场，也能避免 interaction 到达后把前一个 text 关掉再重开，触发整段重打。
39. 阅读模式判断某个 text 是否还能继续保活打字机时，不能只看“它是不是最后一个 text”；还要看“它是不是最后一个可见 item”。一旦尾部已经挂上 `like-status / interaction / ask` 之类的非 text 交互块，前一个 text 就不再是尾项，必须立即停止 keep-alive，避免交互块出现后前文再次整段打字。
40. 听课模式里已经明确被 `text_end/done` 或“下一个 element 到达”收尾的实时 element，应该立刻在数据层打上“切回阅读模式按历史态展示”的独立标记；阅读模式组装 `readModeItems` 时再把它映射成 `isHistory=true` 和 `shouldUseTypewriter=false`，不要等用户切模式时再临时回填，也不要直接污染实时流本身的 `isHistory` 语义。
41. 学习模式切换期间如果旧的 SSE stream 还在继续消费，凡是 `finalize/build item` 这类依赖当前模式的逻辑，都不能直接读取创建 stream 时 closure 里的 `isListenMode`；应改读实时 ref，否则“听课模式发起、阅读模式收尾”的交互链路会把新正文误标成 history-like，触发 typewriter 中途关闭后再重开，造成闪烁或整段重打。
42. 追问 `AskBlock` 的 streaming answer 若在打字途中被收起/关闭，不能把这条 answer 的 `shouldUseTypewriter` 立即改成 `false`，也不要卸载承载它的 `ContentRender` 面板节点；应让流式会话在隐藏状态下继续保活，否则再次打开时同一条 answer 会因重挂载从错误进度重新打字，表现为速度异常、跳字或像被“叠速”一样。
43. 上一条只适用于“流仍未结束”的窗口期；如果追问 answer 在面板隐藏期间已经收到终态 `done/text_end(is_terminal=true)` 并完成收尾，就应立即把该 answer 的 `shouldUseTypewriter` 置为 `false`。这样再次打开时直接展示静态最终文本，不要再重放一次打字机。

## 备注

- 当同一答案分多次快照回传且 `element_bid` 相同，必须覆盖同一条消息。
- 字段重构从 `*BlockBid*` 到 `*ElementBid*` 后，消费方解构与依赖数组必须同步改名。
