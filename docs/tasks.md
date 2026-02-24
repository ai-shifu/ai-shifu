# Audio-Visual Sync Development Tasks

## Phase 1: Backend — Database & DTO Changes

- [x] 1.1 Add `position` field to `LearnGeneratedAudio` model (`src/api/flaskr/service/tts/models.py`)
- [x] 1.2 Generate Alembic migration for `position` column (`src/api/migrations/versions/a1b2c3d4e5f6_add_position_to_learn_generated_audios.py`)
- [x] 1.3 Add `position` field to `AudioSegmentDTO` (`src/api/flaskr/service/learn/learn_dtos.py`)
- [x] 1.4 Add `position` field to `AudioCompleteDTO` (`src/api/flaskr/service/learn/learn_dtos.py`)
- [x] 1.5 Add `VISUAL_MARKER` to `GeneratedType` enum (`src/api/flaskr/service/learn/learn_dtos.py`)
- [x] 1.6 Create `VisualMarkerDTO` class with fields: `position`, `visual_type`, `content` (`src/api/flaskr/service/learn/learn_dtos.py`)
- [x] 1.7 Update `RunMarkdownFlowDTO.content` union type to include `VisualMarkerDTO`
- [x] 1.8 Update `LearnGeneratedAudio.to_dict()` to include `position`

## Phase 2: Backend — Visual Boundary Detection

- [x] 2.1 Define all visual boundary regex patterns in `src/api/flaskr/service/tts/visual_patterns.py` (new file):
  - [x] 2.1.1 SVG: `<svg>...</svg>`
  - [x] 2.1.2 Mermaid: ` ```mermaid...``` `
  - [x] 2.1.3 Code blocks: ` ```lang...``` ` (fenced, not inline backtick)
  - [x] 2.1.4 Markdown image: `![alt](url)`
  - [x] 2.1.5 HTML `<img>` tag: `<img ... />` or `<img ...>`
  - [x] 2.1.6 Markdown table: `|...|` with `|---|` separator
  - [x] 2.1.7 iframe: `<iframe>...</iframe>` (Bilibili, YouTube, etc.)
  - [x] 2.1.8 Generic HTML block: `<div>`, `<section>`, `<article>`, `<figure>`, `<details>`, `<blockquote>`
  - [x] 2.1.9 Math block: `<math>...</math>` and `$$...$$`
- [x] 2.2 Implement `find_earliest_complete_visual(buffer)` utility — returns earliest complete visual match and its type
- [x] 2.3 Implement incomplete visual detection (extend existing `_strip_incomplete_blocks` patterns for iframe, table, `$$` math)

## Phase 3: Backend — VisualAwareTTSOrchestrator

- [x] 3.1 Create `VisualAwareTTSOrchestrator` class in `src/api/flaskr/service/tts/visual_aware_tts.py`:
  - [x] 3.1.1 `__init__`: same parameters as `StreamingTTSProcessor` + position tracking + raw buffer
  - [x] 3.1.2 `_create_processor()`: factory method for creating new `StreamingTTSProcessor` instance
  - [x] 3.1.3 `process_chunk()`: accumulate raw buffer, iteratively detect visual boundaries, split, yield events
  - [x] 3.1.4 `_split_at_visuals()`: feed text before visual to processor, finalize, emit marker, create new processor
  - [x] 3.1.5 Visual marker emission via `VISUAL_MARKER` event with type and content
  - [x] 3.1.6 `finalize()`: finalize remaining buffer, same interface as `StreamingTTSProcessor.finalize()`
  - [x] 3.1.7 `finalize_preview()`: preview mode finalize without OSS upload
- [x] 3.2 Modify `StreamingTTSProcessor.__init__` / `finalize()` to accept `position` parameter, pass to `AudioCompleteDTO` and DB record
- [x] 3.3 Modify `StreamingTTSProcessor._yield_ready_segments()` to include `position` in `AudioSegmentDTO`
- [x] 3.4 Handle edge case: empty text between consecutive visual elements (skip empty audio, emit visual markers only)
- [x] 3.5 Handle edge case: visual element at start/end of block

## Phase 4: Backend — Integration

- [x] 4.1 Update `context_v2.py`: replace `StreamingTTSProcessor` with `VisualAwareTTSOrchestrator` in block processing loop (single-line change)
- [x] 4.2 Update audio reload logic to query by `generated_block_bid` + order by `position`, return list of audio records
- [x] 4.3 Update `PreviewSSEMessageType` to include `VISUAL_MARKER` for preview mode support

## Phase 5: Frontend — SSE & Data Layer

- [x] 5.1 Add `VISUAL_MARKER` to `SSE_OUTPUT_TYPE` in `src/cook-web/src/c-api/studyV2.ts`
- [x] 5.2 Add `VisualMarkerData` type definition (`position`, `visual_type`, `content`)
- [x] 5.3 Update `AudioSegment` interface to include optional `position` field in `src/cook-web/src/c-utils/audio-utils.ts`
- [x] 5.4 Update `AudioItem` interface to include optional `position` field
- [x] 5.5 Update `upsertAudioSegment` / `upsertAudioComplete` to handle `position` field (match by `blockBid` + `position`)
- [x] 5.6 Handle `VISUAL_MARKER` SSE event in `useChatLogicHook.tsx` message handler — store visual markers in content list

## Phase 6: Frontend — Listen Mode Event Queue

- [x] 6.1 Define `SubQueueItem` type (audio / visual) and `buildSubQueue()` helper in `useListenMode.ts`
- [x] 6.2 Add sub-queue tracking refs (`subQueueRef`, `subQueueIndexRef`) to `useListenAudioSequence`
- [x] 6.3 Update `useListenContentData` to detect `audioRecords` in `hasAudio` check
- [x] 6.4 Update `useListenAudioSequence` event processing:
  - [x] 6.4.1 Audio event: play audio via `playUrl()`, advance on completion
  - [x] 6.4.2 Visual marker event: skip visual markers in sub-queue (content already on slide)
  - [x] 6.4.3 Interaction event: unchanged (wait for user submission)
- [x] 6.5 Sub-queue exhaustion: clear sub-queue and advance to next main sequence item

## Phase 7: Frontend — Audio Player Adaptation

- [x] 7.1 Add `playUrl` method to `AudioPlayerHandle` interface (`AudioPlayer.tsx`)
- [x] 7.2 Implement `playUrl` in `AudioPlayerList.tsx` imperative handle via `startUrlPlayback`

## Phase 8: Testing & Verification

- [x] 8.1 Backend unit tests: visual boundary pattern detection (all 9 types)
- [x] 8.2 Backend unit tests: `find_earliest_complete_visual()` — multiple patterns, priority, incomplete elements
- [x] 8.3 Backend unit tests: `VisualAwareTTSOrchestrator` — single visual, multiple visuals, adjacent visuals, no visuals
- [x] 8.4 Integration test: block with SVG generates multiple positional audio records
- [x] 8.5 Integration test: block with table + image generates correct positions and markers
- [x] 8.6 Integration test: block with Bilibili iframe generates correct visual marker
- [x] 8.7 Integration test: block without visual elements — single audio (backward compatible)
- [ ] 8.8 Frontend manual test: listen mode with SVG — audio plays, then SVG appears, then next audio
- [ ] 8.9 Frontend manual test: listen mode with table — audio stops, table shown, next audio plays
- [ ] 8.10 Frontend manual test: listen mode with image — image appears after preceding audio
- [ ] 8.11 Frontend manual test: listen mode with Bilibili iframe — video embed shown after audio
- [ ] 8.12 Frontend manual test: listen mode with multiple mixed visuals — correct ordering
- [ ] 8.13 Frontend manual test: listen mode with interaction block — waits for user input
- [ ] 8.14 Frontend manual test: non-listen mode — no regression
- [ ] 8.15 Test audio reload (history) for blocks with positional audio
