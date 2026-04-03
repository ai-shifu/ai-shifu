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
- 当需求要求 PC 学习页或 `preview=true` 预览页的追问入口贴到内容区最右侧时，只调整 `c` 端真实学习链路的 `LIKE_STATUS` 外层对齐；编辑器调试页保持左对齐，避免不同场景布局串改。
- 编辑器调试预览若通过 `disableAskButton` 禁用追问，应该直接隐藏追问按钮本体；若该行已无其它动作，也一并不渲染，避免留下空白操作栏。
- 当需求要求“按接口顺序直接展示内容与追问”时，不要额外引入 `readyElementBids`、`onTypeFinished` 等前端渲染门禁。
- SSE 流里 `ELEMENT/CONTENT` 阶段只更新当前元素本体，不要提前插入 `LIKE_STATUS`；追问入口统一在 `TEXT_END` 后补齐，避免按钮先于流式正文出现。
- 若后端未必为每个 `element` 都补 `TEXT_END`，前端可在“下一个 `element` 开始”或“当前流关闭”时，把上一个活动 `element` 视为隐式完成并补齐追问入口。
- 交互块触发 `onSend` 且需要截断后续内容时，必须保留该交互块关联的辅助行（`LIKE_STATUS` / `ASK`），避免进入思考中后追问入口消失。
- 后台调试/预览链路中收到 `interaction` 时，也要为该 `interaction` 本身补齐 `LIKE_STATUS`，否则追问按钮不会渲染。
- 重生成判定不能直接依赖“列表最后一项”；应忽略 `LIKE_STATUS`/`ASK` 等辅助行，按“最后可操作元素”判断，避免点击末尾交互块误弹重生成确认框。
- 预览链路里 `updateContentListWithUserOperate` 在截断列表时，也要保留当前 `interaction` 关联的 `LIKE_STATUS/ASK`（按 `parent_block_bid/parent_element_bid` 匹配），避免选择后追问入口消失。
- interaction 提交值组装时要去重并保序（如 `selectedValues + buttonText` 同值场景），避免变量被写成 `ENFJ,ENFJ` 这类重复值。
- Slide 播放器里的追问入口若通过 `playerCustomActions` 注入，桌面端要和播放器 notes 浮层互斥，移动端则单独提供悬浮入口并复用 `AskBlock` 的弹层展示。
- 听课模式桌面端若 `markdown-flow-ui/slide` 已支持函数式 `playerCustomActions`，优先直接消费 `currentElement / isActive / toggleActive / setActive` 上下文，不要在 `ai-shifu` 里再额外维护一套追问按钮高亮、展开收起和暂停播放状态；只保留浮层渲染与 outside click 关闭这类业务层收口。
- 听课模式移动端若追问按钮仍需放在 player 外部，也应继续透传 `playerCustomActions`，在播放器内部只做上下文桥接、不渲染实际按钮；外部按钮只负责位置与样式，点击后调用同一套 active 状态，确保自动暂停、当前元素命中和关闭行为与桌面端一致。
- 听课模式里的 `AskBlock` 若在前端本地先拿到新追问/新回答，父层也要同步维护一份按锚点 `element_bid` 索引的 `ask_list` 覆盖表，并并回 `elementList`；不要只让 `AskBlock` 自己持有本地状态，否则调试时会看到对应 slide element 的 `ask_list` 仍是 `undefined`。
- 听课模式里的追问若需要在切回阅读模式后继续展示，不能只同步 `ListenModeSlideRenderer` 的本地 `ask_list` 覆盖；还要把同一份 ask history 写回 `useChatLogicHook` 的 `items`，按 `parent_element_bid` 更新或补建 `ASK` block，并保留用户已主动展开的状态。
- `AskBlock` 若内部维护了 `displayList` 一类本地展示态，就不能只在初次挂载时用 `askList` 初始化；当 `askList` 或锚点 `element_bid` 变化时，必须把新的追问列表同步回本地状态，否则控制台里已经有 `ask_list`，浮层里仍会显示空列表。
- 若移动端通过 `playerCustomActions` 挂一个“只桥接 context、不实际渲染按钮”的隐藏节点，`Slide` 仍可能把它计入 mobile control count，导致播放器底部按钮列数从 4 变成 5；此时要么从组件层避免占位，要么在业务侧局部把移动端 controls 的列数强制修正回预期值。
- 若听课模式 PC 端的追问浮层需要与移动端追问弹层保持一致，优先让 `listen-slide-ask-block` 在桌面端也走“标题栏 + 独立滚动消息区 + 底部固定输入区”的面板结构，并把 ask/answer 气泡样式收敛到该作用域，避免影响普通阅读模式的 `AskBlock`。
- 听课模式桌面端关闭追问浮层时，不能只依赖 `Slide` 侧的 `setActive(false)` 回推状态；若 player 已隐藏或上下文更新延迟，业务层也要同步把本地 `playerCustomActionState.isActive` 置为 `false`，避免只暂停音频但浮层不收起。
- 听课模式下若 `playerCustomActions` 命中的 `currentElement` 是 `interaction`，则追问入口在 PC 和移动端都应禁用，并在切入交互块时主动关闭已展开的追问浮层；交互块不允许追问。
- 若 `markdown-flow-ui` 在组件节点（如 `.slide-interaction-overlay`）内部重新声明了 CSS 变量，`ai-shifu` 侧仅在 `:root` 覆盖不会生效；需要在相同或更内层的业务作用域选择器上重新声明该变量。
- 追问面板若支持 SSE 流式回答，自动滚底不能只依赖消息条数变化；同一条 answer 在流式追加、Markdown 重排导致内容区高度变化时，也要通过 `ResizeObserver` 或等价机制持续滚到底部。
- 当 `LIKE_STATUS` 挂在 `interaction` 元素后方时，如需求要求去掉追问入口，优先通过 `disableAskButton` 关闭按钮，仅保留必要的重生成或音频动作，避免影响正文块后的追问能力。
- `listen-slide-ask-block` 这类听课模式专用追问容器需要局部覆写气泡视觉时，优先在容器作用域内覆盖 `.userMessage`，避免改到普通聊天页或移动端追问弹层。
- 当听课模式的 `elementList` 需要感知追问时，优先把 `ask_list` 直接挂到对应 `element` 上；锚点匹配优先取 `anchor_element_bid`，缺失时再回退到归一化后的 `parent_element_bid`。

## 工作流

1. `toggleAskExpanded` 先执行同父级 `ASK` 去重，再切换展开态。
2. 移除按钮时同步移除对应数据注入，避免空白操作栏。
3. 移动端长按菜单在“无可展示动作”时不弹空菜单。
4. 对 `sys_lesson_feedback_score` 这类隐藏正文的 interaction，同步隐藏操作栏。
5. 为 `ContentRender/IframeSandbox` 增加渲染完成回调并向上透传到 `ChatUi`。
6. `onTypeFinished` 要覆盖普通 markdown 与 `sandbox/iframe` 两条渲染路径。
7. 给 slide 场景接追问时，优先复用现有 `ask_list`/`parent_element_bid` 映射，不要再额外复制一套问答状态。

## 备注

- 阅读模式下桌面端追问操作栏继续挂在 `LIKE_STATUS`，避免正文未就绪时按钮先出现。
