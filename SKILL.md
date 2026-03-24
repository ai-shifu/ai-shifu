# Frontend Skills

## Element-Level Chat Streaming

- When chat SSE switches from block-level payloads to element-level payloads, use `element_bid` as the stable render key for each chat item.
- Preserve the original `generated_block_bid` on a separate source field so refresh, TTS, and other backend actions can still target the server-side block.
- When history records and live SSE share the same element schema, keep one conversion path so both sources produce the same `contentList` structure.

## Module Augmentation Guardrails

- When a package subpath export appears to lose members in TypeScript, verify the published `node_modules` declaration file before changing the upstream package.
- Prefer module augmentation files with a top-level `import "package/subpath";` plus `export {};` so local declarations merge with upstream types instead of replacing the module shape.
- Only augment exported interfaces; if upstream props are not interface-based, avoid ambient overrides and use local wrapper types instead.

## Slide Audio Buffering State

- When a Slide step contains `is_speakable` content but no playable audio yet, treat it as a buffering step instead of auto-advancing it as silent content.
- Keep buffering visibility driven by step-level speakable intent plus player waiting events so the overlay hides on first playable audio and reappears only while waiting for the next streamed segment.
- When users switch markers manually during buffering, clear the current buffering state immediately and let the next step recompute its own playback status.
- When a Storybook demo only needs to surface Slide buffering UI clearly, prefer a streamed `is_speakable` step without audio payloads over a more complex fake audio simulator.
- When a Storybook demo needs to show buffering first and autoplay after audio arrives, add a story-only audio start delay on top of `StreamingSlidePreview` instead of changing production Slide contracts.

## Incremental Audio Segment Merge

- When backend `element.audio_segments` arrive as incremental updates instead of full snapshots, merge them with the existing item state before replacing `audio_segments` or `audioTracks`.
- When listen-mode data can carry audio in both `audio_segments` and `audioTracks`, always merge both sources before rendering so stale partial `audio_segments` never mask complete track-level segments.
- Deduplicate streamed audio segments with a stable key that includes `element_id`, `position`, and `segment_index` so repeated chunks do not overwrite or collapse adjacent segments incorrectly.
- When new streamed audio segments only extend the current step's playable media, do not reset Slide playback state from the beginning; only restart when the step structure, interaction target, or audio sequence membership actually changes.
- When a Slide playback regression is hard to reproduce from a final `elementList`, replay the raw ai-shifu `run` fixture in Storybook so each `data:` payload applies as a live SSE-style update.
- When wiring new Slide UI copy from ai-shifu into markdown-flow-ui props, add a dedicated `module.chat` translation key and pass the localized text from the renderer instead of hardcoding fallback strings.
