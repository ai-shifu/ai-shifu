# Frontend Skills

## Element-Level Chat Streaming

- When chat SSE switches from block-level payloads to element-level payloads, use `element_bid` as the stable render key for each chat item.
- Preserve the original `generated_block_bid` on a separate source field so refresh, TTS, and other backend actions can still target the server-side block.
- When history records and live SSE share the same element schema, keep one conversion path so both sources produce the same `contentList` structure.

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
- When listen-mode data can carry audio in both `audio_segments` and `audioTracks`, always merge both sources before rendering so stale partial `audio_segments` never mask complete track-level segments.
- When backend moves interaction answers into `payload.user_input`, normalize that value at the record boundary back onto `element.user_input` so history and SSE rendering keep using the same field.
- Deduplicate streamed audio segments with a stable key that includes `element_id`, `position`, and `segment_index` so repeated chunks do not overwrite or collapse adjacent segments incorrectly.
- When new streamed audio segments only extend the current step's playable media, do not reset Slide playback state from the beginning; only restart when the step structure, interaction target, or audio sequence membership actually changes.
- When a Slide playback regression is hard to reproduce from a final `elementList`, replay the raw ai-shifu `run` fixture in Storybook so each `data:` payload applies as a live SSE-style update.
- When wiring new Slide UI copy from ai-shifu into markdown-flow-ui props, add a dedicated `module.chat` translation key and pass the localized text from the renderer instead of hardcoding fallback strings.

## 聊天操作栏裁剪

- 当学习页、预览、调试共用同一套聊天交互组件时，优先把按钮显隐收敛成统一的组件配置，比如 `showGenerateBtn`，再从入口层按场景透传，避免分散写死。
- 当某个操作按钮依赖 `LIKE_STATUS` 这类中间态项承载展示时，删除按钮展示的同时也要停掉对应的数据注入，否则页面里容易残留空白操作栏或无意义占位。
- 当移动端长按菜单依赖桌面端交互状态时，移除某类操作后要同步重算“是否还有可展示动作”，避免弹出空菜单。
