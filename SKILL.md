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
