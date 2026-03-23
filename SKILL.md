# Frontend Skills

## Element-Level Chat Streaming
- When chat SSE switches from block-level payloads to element-level payloads, use `element_bid` as the stable render key for each chat item.
- Preserve the original `generated_block_bid` on a separate source field so refresh, TTS, and other backend actions can still target the server-side block.
- When history records and live SSE share the same element schema, keep one conversion path so both sources produce the same `contentList` structure.
