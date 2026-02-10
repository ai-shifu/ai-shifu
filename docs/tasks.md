# TTS Audio Segment Sync - Task List

## Phase 1: Backend - Database & Model

- [x] 1.1 Add `position` column to `LearnGeneratedAudio` model (`src/api/flaskr/service/tts/models.py`)
  - Add `position = Column(Integer, nullable=False, default=0, comment="...")`
  - Update `to_dict()` to include `position`

- [x] 1.2 Generate Alembic migration
  - Migration file: `migrations/versions/f1a2b3c4d5e6_add_position_to_learn_generated_audios.py`
  - down_revision: `6b956399315e`

## Phase 2: Backend - Text Splitting

- [x] 2.1 Add `split_text_by_visual_boundaries()` function (`src/api/flaskr/service/tts/__init__.py`)
  - Added `_VISUAL_BOUNDARY_PATTERN` combined regex for SVG/code/mermaid/math/script/style
  - Splits text with `re.split`, applies `preprocess_for_tts()` to each part, filters empty

- [x] 2.2 Add unit tests for `split_text_by_visual_boundaries()`
  - 10 test cases added to `tests/service/tts/test_tts_text_preprocess.py`
  - All 18 tests pass (8 existing + 10 new)

## Phase 3: Backend - DTO Changes

- [x] 3.1 Add `position` field to `AudioSegmentDTO` (`src/api/flaskr/service/learn/learn_dtos.py`)
  - Added `position: int = Field(default=0)`, updated `__init__` and `__json__`

- [x] 3.2 Add `position` field to `AudioCompleteDTO`
  - Added `position: int = Field(default=0)`, updated `__init__` and `__json__`

- [x] 3.3 Update `GeneratedBlockDTO` to support multiple audio URLs
  - Added `audio_urls: Optional[List[Dict[str, Any]]]` field
  - `__json__` outputs `audio_urls` list + backward-compat `audio_url` from first entry
  - All 288 tests pass

## Phase 4: Backend - Streaming TTS Changes

- [x] 4.1 Update `StreamingTTSProcessor` to detect visual element boundaries (`src/api/flaskr/service/tts/streaming_tts.py`)
  - Added `_current_position` counter and `_position_audio_bids` dict
  - Added `_check_visual_boundaries()` non-blocking loop using `VISUAL_BOUNDARY_PATTERN.search()`
  - Added `_submit_remaining_buffer()` helper
  - `process_chunk()` calls boundary check before TTS submission

- [x] 4.2 Update `StreamingTTSProcessor.finalize()` to handle last position
  - Groups `_all_audio_data` by position, concatenates/uploads/saves each separately
  - Each position gets its own `LearnGeneratedAudio` record and `AUDIO_COMPLETE` event
  - `finalize_preview()` also yields per-position events

- [x] 4.3 Update `StreamingTTSProcessor._yield_ready_segments()` to include `position` in `AudioSegmentDTO`
  - Segments tagged with `position` in TTSSegment dataclass
  - `_all_audio_data` stores 4-tuple `(index, audio_data, duration_ms, position)`
  - All 288 tests pass

## Phase 5: Backend - On-demand & History Changes

- [x] 5.1 Update `stream_generated_block_audio()` (`src/api/flaskr/service/learn/learn_funcs.py`)
  - Cache hit: queries all `LearnGeneratedAudio` records ordered by position, yields `AUDIO_COMPLETE` per position
  - Cache miss: uses `split_text_by_visual_boundaries()` to split text, synthesizes each position separately
  - Each position gets its own `audio_bid`, OSS upload, and DB record with `position=N`
  - Also updated `synthesize_generated_block_audio()` (non-streaming) for consistency

- [x] 5.2 Update `get_learn_record()` history query
  - Queries audio records ordered by `position`, builds `audio_urls_map` as `dict[block_bid, list[dict]]`
  - Passes `audio_urls` list to `GeneratedBlockDTO` (backward-compat `audio_url` handled by DTO)

- [x] 5.3 Update `stream_preview_tts_audio()` with position support
  - Uses `split_text_by_visual_boundaries()` to split preview text by visual boundaries
  - Yields per-position `AudioSegmentDTO` and `AudioCompleteDTO` events
  - All 288 tests pass

## Phase 6: Frontend - Type & Utility Changes

- [x] 6.1 Update SSE types (`src/cook-web/src/c-api/studyV2.ts`)
  - Added `position?: number` to `AudioSegmentData` and `AudioCompleteData`
  - Added `AudioUrlEntry` interface for history record per-position audio entries
  - Added `audio_urls?: AudioUrlEntry[]` to `StudyRecordItem`

- [x] 6.2 Update audio utilities (`src/cook-web/src/c-utils/audio-utils.ts`)
  - Added `BlockAudioPosition` interface (position, audioSegments, audioUrl, audioDurationMs, isAudioStreaming)
  - Added `audioPositions?: BlockAudioPosition[]` to `AudioItem`
  - `upsertAudioSegment()` routes by `segment.position` into `audioPositions[]`, mirrors position=0 to top-level for backward compat
  - `upsertAudioComplete()` routes by `complete.position` into `audioPositions[]`, mirrors position=0 to top-level
  - Added `buildAudioPositionsFromHistory()` to convert history `audio_urls[]` to `BlockAudioPosition[]`
  - TypeScript compiles cleanly

## Phase 7: Frontend - SSE & Listen Mode Changes

- [ ] 7.1 Update SSE event handling (`useChatLogicHook.tsx`)
  - Route `AUDIO_SEGMENT` events to correct position in `audioPositions[]`
  - Route `AUDIO_COMPLETE` events to correct position
  - Maintain backward compatibility with position=0 default

- [ ] 7.2 Update listen mode content data (`useListenMode.ts` - `useListenContentData`)
  - Parse block content to identify visual element boundaries
  - Expand `audioAndInteractionList` to include per-position audio entries
  - Map each position to corresponding content segment / slide page

- [ ] 7.3 Update listen mode audio sequence (`useListenMode.ts` - `useListenAudioSequence`)
  - Handle multi-position blocks in sequence playback
  - After position N audio ends, display visual element, then play position N+1
  - `handleAudioEnded()` advances within positions before advancing to next block

## Phase 8: Testing & Validation

- [ ] 8.1 Backend integration tests
  - Test streaming TTS with SVG content produces multiple positions
  - Test on-demand synthesis with visual boundaries
  - Test history query returns multiple audio URLs per block
  - Test backward compatibility (no visual elements -> single position=0)

- [ ] 8.2 Frontend manual testing
  - Test listen mode with blocks containing SVGs
  - Test audio-visual sync timing
  - Test history playback with multi-position audio
  - Test edge cases: no visual elements, visual at start/end, consecutive visuals

- [ ] 8.3 Backward compatibility verification
  - Existing audio records (position=0) play correctly
  - Old frontend (ignoring position) still works with new backend
  - New frontend handles both old (single) and new (multi) audio formats
