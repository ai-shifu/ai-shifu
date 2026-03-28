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
4. `run` 请求体 `listen` 以 URL 查询参数为单一真值来源。
5. `LIKE_STATUS` 仅表示流结束信号，TTS 还需校验 `is_speakable` 或已有可播音频。
6. 仅允许点击播放按钮时触发 `generated-blocks/:id/tts`，禁止 `onStepChange` 自动补拉。
7. `listen-mode` 映射 `elementList` 时显式透传 `isAudioStreaming`。
8. 统一分发层处理 `type/error` 或 `event_type/error`，立即弹出 destructive toast。
9. 音频播放 icon 的可见性需受 `is_speakable` 控制：当 `is_speakable === false` 时不展示播放按钮。

## 备注

- 回放疑难问题时优先复用 Storybook 的原始 `run` fixture，按 SSE 顺序重放 `data:` 片段。
