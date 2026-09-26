---
name: listen-mode-audio-streaming
description: 当处理听课模式的流式音频、buffering、TTS 请求门禁与播放连续性问题时使用本技能。统一音频来源选择、分段合并策略和请求触发时机。
---

# 听课模式流式音频

## 核心规则

- `is_speakable` 且暂无可播音频时视为 buffering，不自动跳过。
- 音频来源单选：优先 `audioTracks`，不可播时才回退 `audio_url/audio_segments`。
- 分段去重 key 使用 `element_id + position + segment_index`，并允许后到分段提升 `isFinal`。

## 工作流

1. 合并增量 `audio_segments` 后再写回状态，不直接全量替换。
2. 仅新增当前步骤可播片段时不重置整段播放；结构变化才重启。
3. 用户手动切 marker 时立即清除当前 buffering 状态。
4. `run` 请求体 `listen` 必须跟随当前真实听课状态：只有 `learningMode === 'listen'` 且课程 `tts_enabled` 可用时才发送 `listen=true`；阅读模式即使课程支持听课也必须发送 `listen=false`。
5. `LIKE_STATUS` 仅表示流结束信号，TTS 还需校验 `is_speakable` 或已有可播音频。
6. `requestAudioForBlock` supports on-demand `generated-blocks/:id/tts` calls, including programmatic `listen=false` requests. This hook capability does not imply a reading-mode playback button: `NewChatComp` hides audio actions in both normal and preview reading mode. Its mode-level gate is `!isClassroomMode && (previewMode || isListenModeActive) && !isPreviewReadMode`; eligible content must also satisfy the speakability rules. Listen mode uses the existing automatic backfill queue described below; do not add an independent request from `onStepChange`.
7. `listen-mode` 映射 `elementList` 时显式透传 `isAudioStreaming`。
8. 统一分发层处理 `type/error` 或 `event_type/error`，立即弹出 destructive toast。
9. 音频播放 icon 的可见性需受 `is_speakable` 控制：当 `is_speakable === false` 时不展示播放按钮。
10. 处理 `audio_segment/audio_complete` 时禁止直接把 `Record<string, unknown>` 断言为目标类型，必须先做字段级归一化再写入 `upsertAudioSegment/upsertAudioComplete`。
11. 用 Storybook 或 `markdown-flow-ui` 回放 `data.json` 排查时，`elementList` 的组装路径必须和 `ai-shifu` 听课模式保持同构，禁止额外做 story 专用的音频归属重排补偿。
12. 听课模式组装 `elementList` 时，若内容本身是 `<iframe data-tag="video" ...></iframe>` 形式的视频 iframe，即使后端 `element_type` 仍是通用类型，也要优先把 slide element 的 `type` 推断为 `video`。
13. 听课模式消费 `record` 历史接口时，若 `payload.audio.subtitle_cues` 存在，必须在 `elementList` 中显式透传为 `subtitle_cues`，不要只保留 `content` 导致字幕时间轴元数据在渲染层丢失。
14. 听课模式 `run` 的 `audio_segment` 若已生成当前累计字幕 cue，必须同步透传到对应 element patch 的 `payload.audio.subtitle_cues`，不要等到 `audio_complete` 才返回字幕。
15. 课程设置里的 `tts_enabled` 虽然沿用后端字段名，但前端产品语义视为“听课模式开关”；改动作者端文案或 learner 端默认模式时，必须同时检查设置页文案、课程信息映射和 `/c/...` 布局层默认 `learningMode` 是否一致。
16. 阅读/听课模式切换只切换课时展示形态，不应硬断正在进行的 `/run` SSE；只有重修、离开课时、lesson reset 等真实生命周期结束场景才触发全局 stream stop。
17. 进入听课模式后持续扫描当前 lesson 已有正文中 `is_speakable !== false` 且有有效 `element_bid` 的内容块；历史回放内容天然可补，流式 `/run` 新内容必须等后端在原有事务 commit 之后发出 `audio_backfill_ready` 才能调用 `generated-blocks/:id/tts?listen=true`，禁止用尚未提交的 streaming element 直接补音频。补生成对同一 generated block 做 in-flight 去重；第一段音频可播后允许进入播放，整条 TTS SSE 继续补齐后续 position；没有可补正文或补音频失败时，不再提示重修或强制切回阅读，只保持当前模式并用 toast/缓冲态反馈。
18. 听课模式把后端 `subtitle_cues[].text` 透传给 `markdown-flow-ui/slide` 前，要先过滤尾部终止标点：默认删除句号、逗号、冒号、分号等收尾符号，但保留问号、叹号、省略号，以及成对标点的后半个（如 `”`、`）`、`》`）。
19. 听课模式组装 item 时，如果 final `element` 事件只把完整 `audio_url` 放在 element 顶层或 `payload.audio`，而当前 item 已经有 `audioTracks/audio_segments`，必须把完整 URL 回填到对应 position 的 `audioTracks`；不要让 Slide 映射层因为优先使用 `audioTracks` 而丢掉完整 mp3 URL。
20. 当需要在线上显式区分 buffering 卡住原因时，优先把 loading 文案拆成“未收到当前页音频 / 正在加载当前页音频 / 正在等待当前页后续音频片段”三类可配置文案，不要继续只透传单一字符串。
21. `AudioPlayer` 已经播放过流式 `audio_segment` 后，不要在同一播放会话中切到 `audio_complete.audio_url` 续播；完整 URL 只用于未来重播或零 segment 缓存回放，否则 mp3 拼接/seek 偏差会导致句首几个字重复。

## 备注

- 回放疑难问题时优先复用 Storybook 的原始 `run` fixture，按 SSE 顺序重放 `data:` 片段。

## Verification

The listen-mode queue in `NewChatComp` waits for persisted
`audio_backfill_ready` for newly streamed content, deduplicates in-flight blocks,
and stops applying results after the lesson scope ends. History and committed
new content have different eligibility. `listenModeUtils` determines candidates,
while `useChatLogicHook` records persisted readiness and supplies
`requestAudioForBlock`. Neither mode switching nor a slide change should create
a competing queue implementation. The lesson-change effect resets queue
bookkeeping and the lesson ref; it does not immediately close a silent old TTS
stream. `requestAudioForBlock` settles a stale stream when a guarded audio event
arrives, or through normal stream termination/error or the 120-second listen
backfill idle timeout. Do not describe this as eager lesson-switch cancellation.

Run `listenModeUtils.test.ts` for candidate selection and block deduplication,
and `src/lib/runWithConcurrency.test.ts` for bounded worker concurrency.
`NewChatComp.test.tsx` tests imported projection/loading helpers; it does not
render the component or verify its backfill effect orchestration. For changes
to that effect, add focused orchestration coverage for in-flight deduplication
and lesson-scope result guards instead of treating these helper suites as proof.
Run the adjacent
`useChatLogicHook.test.tsx` cases for programmatic on-demand audio requests,
forced `listen=true` backfill, persisted-ready gating, streaming failures, and
backfill idle timeout. The on-demand request test calls the hook directly and
does not establish a reading-mode UI action; changes to visible audio controls
need rendered component coverage. Also run `ListenModeSlideRenderer.test.tsx` when the mapping or
playback restore contract changes. Except for the shared concurrency suite, these files live in
`src/app/c/[[...id]]/Components/ChatUi/`.
