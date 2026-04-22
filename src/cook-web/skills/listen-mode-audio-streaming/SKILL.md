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
4. `run` 请求体 `listen` 必须跟随课程级 `tts_enabled` 对应的前台开关状态，也就是和 header 上学习模式 icon 的展示条件保持一致；不要再用当前 `learningMode` 反推请求参数。
5. `LIKE_STATUS` 仅表示流结束信号，TTS 还需校验 `is_speakable` 或已有可播音频。
6. 仅允许点击播放按钮时触发 `generated-blocks/:id/tts`，禁止 `onStepChange` 自动补拉。
7. `listen-mode` 映射 `elementList` 时显式透传 `isAudioStreaming`。
8. 统一分发层处理 `type/error` 或 `event_type/error`，立即弹出 destructive toast。
9. 音频播放 icon 的可见性需受 `is_speakable` 控制：当 `is_speakable === false` 时不展示播放按钮。
10. 处理 `audio_segment/audio_complete` 时禁止直接把 `Record<string, unknown>` 断言为目标类型，必须先做字段级归一化再写入 `upsertAudioSegment/upsertAudioComplete`。
11. 用 Storybook 或 `markdown-flow-ui` 回放 `data.json` 排查时，`elementList` 的组装路径必须和 `ai-shifu` 听课模式保持同构，禁止额外做 story 专用的音频归属重排补偿。
12. 听课模式组装 `elementList` 时，若内容本身是 `<iframe data-tag="video" ...></iframe>` 形式的视频 iframe，即使后端 `element_type` 仍是通用类型，也要优先把 slide element 的 `type` 推断为 `video`。
13. 听课模式消费 `record` 历史接口时，若 `payload.audio.subtitle_cues` 存在，必须在 `elementList` 中显式透传为 `subtitle_cues`，不要只保留 `content` 导致字幕时间轴元数据在渲染层丢失。
14. 听课模式 `run` 的 `audio_segment` 若已生成当前累计字幕 cue，必须同步透传到对应 element patch 的 `payload.audio.subtitle_cues`，不要等到 `audio_complete` 才返回字幕。
15. 课程设置里的 `tts_enabled` 虽然沿用后端字段名，但前端产品语义视为“听课模式开关”；改动作者端文案或 learner 端默认模式时，必须同时检查设置页文案、课程信息映射和 `/c/...` 布局层默认 `learningMode` 是否一致。
16. 从阅读模式切到听课模式前，如果 `record` 历史接口映射出来的首个 `text` 内容块没有 `audio_url/audioUrl`，必须拦截进入听课模式并提示用户先重修；判断范围只能看 `isHistory === true` 的历史内容，不能把后续 SSE 流里的新内容也算进去。
17. 听课模式把后端 `subtitle_cues[].text` 透传给 `markdown-flow-ui/slide` 前，要先过滤尾部终止标点：默认删除句号、逗号、冒号、分号等收尾符号，但保留问号、叹号、省略号，以及成对标点的后半个（如 `”`、`）`、`》`）。

## 备注

- 回放疑难问题时优先复用 Storybook 的原始 `run` fixture，按 SSE 顺序重放 `data:` 片段。
