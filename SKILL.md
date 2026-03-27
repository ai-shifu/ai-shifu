# Frontend Skills

## Element-Level Chat Streaming

- When chat SSE switches from block-level payloads to element-level payloads, use `element_bid` as the stable render key for each chat item.
- Preserve the original `generated_block_bid` on a separate source field so refresh, TTS, and other backend actions can still target the server-side block.
- When history records and live SSE share the same element schema, keep one conversion path so both sources produce the same `contentList` structure.
- 当追问流返回 `type=element` 且 `element_type=answer` 时，`AskBlock` 需要按答案流更新教师消息，而不是只监听 `type=content`，否则会出现追问问题已发送但回答气泡为空的问题。
- 当同一个追问答案在 SSE 中以相同 `element_bid` 多次回传（增量渲染快照）时，前端应按 `element_bid` 覆盖更新同一条回答消息，而不是持续拼接，避免同一答案被重复展示。
- 当学习记录接口返回 `element_type=ask/answer` 时，这两类元素应归并到对应 `anchor_element_bid` 的 `AskBlock.ask_list` 中展示，而不是作为独立内容块渲染在正文流里。
- 当 `ask/answer` 的 `anchor_element_bid` 指向较早内容，但事件实际出现在更后序位置时，`AskBlock` 的插入位置要按接口返回顺序（sequence）落位，不能固定锚在 `anchor` 内容后面。

## Module Augmentation Guardrails

- When a package subpath export appears to lose members in TypeScript, verify the published `node_modules` declaration file before changing the upstream package.
- Prefer module augmentation files with a top-level `import "package/subpath";` plus `export {};` so local declarations merge with upstream types instead of replacing the module shape.
- When augmenting `markdown-flow-ui/renderer`, explicitly import dependent upstream types like `InteractionDefaultValueOptions`; otherwise the local `.d.ts` can both hide the real exports and leave augmentation fields unresolved.
- Only augment exported interfaces; if upstream props are not interface-based, avoid ambient overrides and use local wrapper types instead.

## Slide Audio Buffering State

- When a Slide step contains `is_speakable` content but no playable audio yet, treat it as a buffering step instead of auto-advancing it as silent content.
- Keep buffering visibility driven by step-level speakable intent plus player waiting events so the overlay hides on first playable audio and reappears only while waiting for the next streamed segment.
- When users switch markers manually during buffering, clear the current buffering state immediately and let the next step recompute its own playback status.
- When a Storybook demo only needs to surface Slide buffering UI clearly, prefer a streamed `is_speakable` step without audio payloads over a more complex fake audio simulator.
- When a Storybook demo needs to show buffering first and autoplay after audio arrives, add a story-only audio start delay on top of `StreamingSlidePreview` instead of changing production Slide contracts.
- When an interaction step has already been answered, do not keep treating that marker as a playback blocker; close the overlay and let newly streamed follow-up audio start immediately on the same step.

## Incremental Audio Segment Merge

- When backend `element.audio_segments` arrive as incremental updates instead of full snapshots, merge them with the existing item state before replacing `audio_segments` or `audioTracks`.
- When listen-mode data can carry audio in both `audio_segments` and `audioTracks`, pick one canonical source for rendering (prefer `audioTracks`, fallback to legacy only when tracks are not playable).
- When backend moves interaction answers into `payload.user_input`, normalize that value at the record boundary back onto `element.user_input` so history and SSE rendering keep using the same field.
- Deduplicate streamed audio segments with a stable key that includes `element_id`, `position`, and `segment_index` so repeated chunks do not overwrite or collapse adjacent segments incorrectly.
- When new streamed audio segments only extend the current step's playable media, do not reset Slide playback state from the beginning; only restart when the step structure, interaction target, or audio sequence membership actually changes.
- When a Slide playback regression is hard to reproduce from a final `elementList`, replay the raw ai-shifu `run` fixture in Storybook so each `data:` payload applies as a live SSE-style update.
- When wiring new Slide UI copy from ai-shifu into markdown-flow-ui props, add a dedicated `module.chat` translation key and pass the localized text from the renderer instead of hardcoding fallback strings.
- 当听课模式依赖 `LIKE_STATUS` 作为内容块“流结束”的信号时，不要直接把它等同于“可发起 TTS”；还要再校验对应内容块是否 `is_speakable`，或是否已经带有可播放音频。
- 当后端 AV 分段会把纯视觉 block 识别为“无可朗读文本”时，前端的 `ttsReadyElementBids` 之类请求门禁必须和这条规则对齐，避免 slide 切换时对纯视觉内容重复打 `generated-blocks/:id/tts` 并触发 500。
- 当产品要求“仅点击播放按钮才发起 TTS”时，听课模式必须移除 `onStepChange`、序列切换等自动补拉请求逻辑，`generated-blocks/:id/tts` 只能由 `AudioPlayer` 的 `onRequestAudio` 点击行为触发。
- 当 run SSE 可能返回 `type/error` 或 `event_type/error` 事件时，前端要在统一消息分发层立即弹出 `destructive toast`，并优先使用事件 `content` 作为错误文案，避免错误被静默吞掉。
- 当学习页希望通过 URL 快速切换听课态时，`run` 接口请求体里的 `listen` 必须以页面查询参数 `listen` 为单一真值来源（如 `?listen=true` 强制传 `true`），不要再混用模式状态或组件内部推导值。
- 当听课模式的 slide 渲染同时拿到 legacy `audio_url/audio_segments` 和新结构 `audioTracks` 时，必须先选定单一音频来源（优先 `audioTracks`，仅在轨道无可播内容时回退 legacy），避免同一步骤出现重复播报。
- 当同一个音频分段 key（`element_id + position + segment_index`）会先到非 final 再到 final 时，去重不能直接丢弃后到分段；必须合并并提升 `isFinal`，否则播放器会误判“仍在流式”而卡在 buffering。
- 当 listen-mode 把内容项映射为 Slide `elementList` 时，除了 `audio_url/audio_segments`，还要显式透传 `isAudioStreaming`（例如 `is_audio_streaming`）；否则仅靠 segment 的 `is_final` 推断可能在 `audio_complete` 后仍显示 buffering。

## 聊天操作栏裁剪

- 当学习页、预览、调试共用同一套聊天交互组件时，优先把按钮显隐收敛成统一的组件配置，比如 `showGenerateBtn`，再从入口层按场景透传，避免分散写死。
- 当某个操作按钮依赖 `LIKE_STATUS` 这类中间态项承载展示时，删除按钮展示的同时也要停掉对应的数据注入，否则页面里容易残留空白操作栏或无意义占位。
- 当移动端长按菜单依赖桌面端交互状态时，移除某类操作后要同步重算“是否还有可展示动作”，避免弹出空菜单。
- 当某类 `interaction`（例如 `sys_lesson_feedback_score`）需要隐藏内容主体时，操作栏渲染条件也必须同步排除该项，避免出现“内容已隐藏但追问按钮仍显示”的错位交互。
- 当阅读模式要求“内容与追问入口同步出现”时，桌面端追问操作栏应继续挂在 `LIKE_STATUS` 节点，不要提前挂在 `CONTENT/INTERACTION` 节点后面，避免内容 iframe 尚未完成渲染时按钮先行出现。
- 当聊天操作栏需要按 element 粒度稳定出现时，`SSE element` 与历史 `records/elements` 都应基于 `element_type` 统一插入 `LIKE_STATUS`，并且显式排除课后反馈交互（`sys_lesson_feedback_score`）以避免无效追问入口。
- 当桌面阅读模式仍存在“追问先于正文可见”的闪烁时，给 `ContentRender/IframeSandbox` 增加渲染完成回调并向上透传到 `ChatUi`，仅在父元素完成渲染后再展示对应 `LIKE_STATUS` 操作栏。
- 当 `ContentRender` 同时支持普通 markdown 与 `sandbox/iframe` 渲染时，`onTypeFinished` 的触发逻辑必须覆盖两条路径，不能只在非 sandbox 分支触发，否则 `readyElementBids` 不会落位并导致部分 element 丢失追问入口。

## 旧字段兼容回填

- 当聊天数据从 `generated_block_bid` 迁移到 `element_bid` 后，`ChatContentItem` 仍要保留 `generated_block_bid` 和 `parent_block_bid` 这类旧字段，避免预览、音频、历史回放中的遗留调用直接报警。
- 当新旧字段需要长期并存时，优先在统一的 list 更新入口做 normalize，把 `generated_block_bid` 回填为 `element_bid`，把 `parent_block_bid` 回填为 `parent_element_bid`，不要把兼容逻辑散落到每个渲染点。

## 音频排查日志清理

- 当需求要求移除“音频排查”日志时，优先按标记词（如 `listen-audio-debug`、`音频中断排查`）全局检索，统一删除日志函数、调用点和仅服务日志的辅助变量，避免只删 `console` 语句却残留无用代码。
- 清理日志后要同步修正 `useCallback/useEffect` 依赖数组与未使用变量，并对关键文件执行定向 ESLint 或类型检查，确保行为不变且可编译。

## 课后反馈弹窗时机

- 当课程反馈弹窗需要避免打断阅读时，自动弹出必须额外受“当前会话已滚动到底部”门禁控制，而不是只依赖 SSE 到达。
- 当听课模式存在音频播放或播放序列进行中时，课后反馈弹窗应先进入 pending 状态，待播放空闲后再延迟约 1.2 秒开放提示。
- 当用户主动关闭课后反馈弹窗后，应按 `outlineBid` 记录免打扰缓存，同一课节内不要再次自动弹窗。
- 当课后反馈交互已包含有效评分（1-5）时，视为已反馈状态，不再自动弹窗，只保留默认值回填能力。

## Docker 构建 npm 源兜底

- 当项目依赖包含预发布版本（如 `beta`）且构建环境默认使用镜像源时，Dockerfile 中要显式设置 `registry=https://registry.npmjs.org/`，避免镜像同步延迟导致 404。
- 建议在 `builder` 与 `runner` 阶段都提供 `ARG NPM_REGISTRY` 并执行 `npm config set registry ${NPM_REGISTRY}`，确保安装行为在多阶段构建中一致。
