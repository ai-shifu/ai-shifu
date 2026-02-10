# TTS Audio Segment Synchronization Design

## 1. Problem Statement

In listen/watch mode, the LLM generates both text and visual elements (SVG, code blocks, mermaid diagrams, etc.) within a single block. Currently, the TTS system:

1. Strips all SVG/visual content during text preprocessing (`preprocess_for_tts()`)
2. Synthesizes remaining text into multiple audio segments purely based on character count (~300 chars)
3. Concatenates all segments into **one final audio file** per block
4. The frontend receives one `audio_complete` event per block with a single OSS URL

This means the frontend has **no way to synchronize audio playback with visual content boundaries**. When the LLM outputs content like:

```
"Here is an explanation..."  <SVG chart>  "As shown in the chart above..."
```

The audio merges "Here is an explanation..." and "As shown in the chart above..." into one continuous audio, making it impossible for the frontend to pause between text and SVG, or synchronize slide transitions with the corresponding audio segment.

## 2. Design Goal

Split audio generation at **visual element boundaries** (SVG, code blocks, mermaid, etc.), so the frontend can:

1. Play audio for the text before a visual element
2. Display/animate the visual element
3. Play audio for the text after the visual element
4. Control timing and transitions between segments

## 3. Current Architecture Analysis

### 3.1 Backend Audio Flow (Streaming)

```
context_v2.py                      streaming_tts.py
     |                                    |
     |-- StreamingTTSProcessor()          |
     |     |                              |
     |     |-- process_chunk(text) -----> |-- _try_submit_tts_task()
     |     |                              |     |-- preprocess_for_tts(buffer)
     |     |                              |     |-- Split at sentence/300chars
     |     |                              |     |-- _submit_tts_task()
     |     |                              |
     |     |-- finalize() -------------> |-- Wait all futures
     |                                   |-- concat_audio_best_effort()
     |                                   |-- Upload single audio to OSS
     |                                   |-- Save single LearnGeneratedAudio
     |                                   |-- Yield AUDIO_COMPLETE (1 per block)
```

### 3.2 Backend Audio Flow (On-demand / History)

```
learn_funcs.py
     |
     |-- stream_generated_block_audio()
     |     |-- Check existing LearnGeneratedAudio (cache)
     |     |-- _yield_tts_segments(full_text)
     |     |     |-- split_text_for_tts() -> segments by char count
     |     |     |-- synthesize each segment
     |     |-- concat_audio_best_effort()
     |     |-- Upload single audio to OSS
     |     |-- Save single LearnGeneratedAudio
     |     |-- Yield AUDIO_COMPLETE (1 per block)
```

### 3.3 Frontend Audio Flow

```
SSE Events:
  audio_segment (N times, base64 data, for streaming playback)
  audio_complete (1 time, OSS URL, for final/cached playback)

AudioPlayer.tsx:
  - Streaming mode: plays base64 segments sequentially via Web Audio API
  - Complete mode: plays single OSS URL via <audio> element

useListenMode.ts:
  - Maps each block to ONE audio entry in audioAndInteractionList
  - Sequence: play block audio -> advance to next block
  - No concept of "sub-segments within a block"
```

### 3.4 Database Model

```
learn_generated_audios:
  - One record per block (generated_block_bid)
  - Stores concatenated audio of all text segments
  - No position/ordering field
```

## 4. Proposed Solution

### 4.1 Core Idea

Instead of concatenating all text segments into one audio per block, **split audio at visual element boundaries** and store each part as a separate `LearnGeneratedAudio` record with a `position` field.

A block with content like:

```
Text A  <SVG>  Text B  <SVG>  Text C
```

Would produce 3 audio records:
- `position=0`: Audio for "Text A"
- `position=1`: Audio for "Text B"
- `position=2`: Audio for "Text C"

### 4.2 Key Design Decisions

1. **Splitting granularity**: Only split at visual element boundaries (SVG, code blocks, mermaid). Within each text segment, the existing ~300 char batching for TTS synthesis is preserved (for streaming latency optimization) but the sub-segments are still concatenated into one audio per position.

2. **What constitutes a "visual element boundary"**: SVG blocks (`<svg>...</svg>`), fenced code blocks (` ``` `), mermaid diagrams. These are the same elements already stripped by `preprocess_for_tts()`.

3. **Backward compatibility**: Blocks with no visual elements produce a single audio record with `position=0`, maintaining the same behavior as today.

4. **`position` field**: Integer starting from 0, representing the order of audio segments within a block. The frontend uses this to synchronize with content rendering.

### 4.3 Database Changes

#### 4.3.1 Add `position` column to `learn_generated_audios`

```python
position = Column(
    Integer,
    nullable=False,
    default=0,
    comment="Audio position within the block (0-indexed, split at visual element boundaries)",
)
```

Default value `0` ensures backward compatibility with existing records.

### 4.4 Backend Changes

#### 4.4.1 New Text Splitting Function

Add `split_text_by_visual_boundaries(text) -> list[str]` in `flaskr/service/tts/__init__.py`:

- Input: Raw markdown text from the LLM
- Output: List of text segments split at visual element boundaries
- Each segment has visual elements stripped (same as current `preprocess_for_tts`)
- Empty segments (e.g., between two consecutive SVGs) are filtered out

Example:
```python
text = "Hello world.\n<svg>...</svg>\nAs shown above.\n```python\ncode\n```\nFinally."
result = split_text_by_visual_boundaries(text)
# result = ["Hello world.", "As shown above.", "Finally."]
```

#### 4.4.2 StreamingTTSProcessor Changes (`streaming_tts.py`)

The streaming processor handles real-time content during LLM generation. Changes needed:

1. **Detect visual element boundaries in streaming buffer**: When an SVG or code block completes in the buffer, finalize the current audio segment (concatenate accumulated sub-segments, upload, save with current position) and start a new position.

2. **Multiple `AUDIO_COMPLETE` events**: Instead of one final `AUDIO_COMPLETE`, yield one per position. Each carries its own `audio_bid`, `audio_url`, `duration_ms`, and the new `position` field.

3. **Multiple `LearnGeneratedAudio` records**: In `finalize()`, save one record per position.

Key implementation approach:
- Track `_current_position` counter (starts at 0)
- When a complete visual element is detected in the buffer, call an internal `_finalize_position()` method that:
  - Waits for pending TTS futures for current position
  - Concatenates audio sub-segments for current position
  - Uploads to OSS
  - Saves `LearnGeneratedAudio` with current position
  - Yields `AUDIO_COMPLETE` with position info
  - Increments `_current_position`
  - Resets sub-segment tracking for next position
- The final `finalize()` method handles the last position

#### 4.4.3 On-demand Synthesis Changes (`learn_funcs.py`)

`stream_generated_block_audio()` handles synthesis for existing blocks (history/replay):

1. **Query change**: Instead of fetching one audio record, query all audio records for the block, ordered by `position`.
2. **Cache hit**: If audio records exist for all positions, yield `AUDIO_COMPLETE` for each position (with position field).
3. **Cache miss**: Use `split_text_by_visual_boundaries()` to determine segments, synthesize each, save with position.

#### 4.4.4 History Query Changes (`learn_funcs.py`)

`get_study_record()` currently builds `audio_url_map` with one URL per block:

```python
audio_url_map = {a.generated_block_bid: a.oss_url for a in audio_records}
```

Change to return a list of audio URLs per block:

```python
audio_urls_map = defaultdict(list)
for a in audio_records:
    audio_urls_map[a.generated_block_bid].append({
        "audio_url": a.oss_url,
        "audio_bid": a.audio_bid,
        "duration_ms": a.duration_ms,
        "position": a.position,
    })
# Sort by position
for bid in audio_urls_map:
    audio_urls_map[bid].sort(key=lambda x: x["position"])
```

#### 4.4.5 DTO Changes

**AudioSegmentDTO** - Add `position` field:

```python
position: int = Field(default=0, description="Audio position within block (visual element boundary)")
```

**AudioCompleteDTO** - Add `position` field:

```python
position: int = Field(default=0, description="Audio position within block (visual element boundary)")
```

**GeneratedBlockDTO** - Change `audio_url` from single string to list:

```python
audio_urls: Optional[list[dict]] = Field(
    default=None,
    description="TTS audio URLs for this block, ordered by position"
)
```

### 4.5 Frontend Changes

#### 4.5.1 Data Structure Changes (`audio-utils.ts`)

Update `AudioItem` to support multiple audio positions:

```typescript
export interface BlockAudioPosition {
  position: number;
  audioUrl?: string;
  audioBid?: string;
  durationMs?: number;
  audioSegments?: AudioSegment[];
  isAudioStreaming?: boolean;
}

// AudioItem gains:
export interface AudioItem {
  generated_block_bid: string;
  audioPositions?: BlockAudioPosition[];   // NEW: multiple audio per block
  // Keep existing fields for backward compatibility during migration
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}
```

#### 4.5.2 SSE Event Handling (`useChatLogicHook.tsx`)

Update `AUDIO_SEGMENT` and `AUDIO_COMPLETE` handlers to route events to the correct position:

- `AudioSegmentDTO` now includes `position`
- `upsertAudioSegment()` routes segments to `audioPositions[position]`
- `upsertAudioComplete()` marks specific position as complete

#### 4.5.3 Listen Mode Sequencing (`useListenMode.ts`)

This is the key frontend change. Currently `audioAndInteractionList` maps one audio entry per block. With positions, expand to:

```
Block A (position 0 audio) -> Block A SVG display -> Block A (position 1 audio) -> ...
```

The `useListenContentData` hook needs to:
1. Parse block content using `splitContentSegments()` to identify visual segments
2. Map audio positions to content segments
3. Build an expanded `audioAndInteractionList` where each position is a separate entry

#### 4.5.4 AudioPlayer Changes (`AudioPlayer.tsx`)

Minimal changes needed. The AudioPlayer already handles:
- Streaming segments (base64 data)
- Complete audio (OSS URL)
- `onEnded` callback

The listen mode sequencer (`useListenAudioSequence`) will handle advancing between positions. AudioPlayer plays one position at a time.

### 4.6 SSE Protocol Changes

#### Current Protocol:
```
audio_segment: {segment_index: 0, audio_data: "...", duration_ms: 1234, is_final: false}
audio_segment: {segment_index: 1, audio_data: "...", duration_ms: 1234, is_final: false}
audio_complete: {audio_url: "...", audio_bid: "...", duration_ms: 5678}
```

#### New Protocol:
```
audio_segment: {segment_index: 0, audio_data: "...", duration_ms: 1234, is_final: false, position: 0}
audio_segment: {segment_index: 1, audio_data: "...", duration_ms: 1234, is_final: false, position: 0}
audio_complete: {audio_url: "...", audio_bid: "abc", duration_ms: 5678, position: 0}
audio_segment: {segment_index: 0, audio_data: "...", duration_ms: 1234, is_final: false, position: 1}
audio_complete: {audio_url: "...", audio_bid: "def", duration_ms: 3456, position: 1}
```

Key: `position` defaults to `0` for backward compatibility.

## 5. Migration Strategy

1. **Database**: Add `position` column with `default=0`. All existing records automatically have `position=0`, maintaining backward compatibility.
2. **Backend**: Deploy new backend first. Old frontends ignore the `position` field (defaults to 0, treated as single audio per block).
3. **Frontend**: Deploy after backend. New frontend handles both single-position and multi-position blocks.

## 6. Impact Analysis

### Modified Files

**Backend:**
| File | Change |
|------|--------|
| `src/api/flaskr/service/tts/models.py` | Add `position` column |
| `src/api/flaskr/service/tts/__init__.py` | Add `split_text_by_visual_boundaries()` |
| `src/api/flaskr/service/tts/streaming_tts.py` | Support multi-position finalization |
| `src/api/flaskr/service/learn/learn_dtos.py` | Add `position` to AudioSegmentDTO/AudioCompleteDTO, update GeneratedBlockDTO |
| `src/api/flaskr/service/learn/learn_funcs.py` | Update history query, on-demand synthesis, streaming |
| `src/api/migrations/versions/` | New migration file |

**Frontend:**
| File | Change |
|------|--------|
| `src/cook-web/src/c-utils/audio-utils.ts` | Add `BlockAudioPosition`, update merge/upsert functions |
| `src/cook-web/src/c-api/studyV2.ts` | Update `AudioSegmentData`/`AudioCompleteData` types |
| `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx` | Route SSE events by position |
| `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts` | Expand sequence to include per-position entries |

### Unchanged Files
- `AudioPlayer.tsx` - No changes needed (plays one audio at a time)
- `useExclusiveAudio.ts` - No changes needed
- TTS provider integrations (`flaskr/api/tts/`) - No changes needed
- `audio_utils.py` (concat/duration) - No changes needed

## 7. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Streaming boundary detection may be imprecise | Reuse existing `_strip_incomplete_xml_block()` logic; only finalize position when a complete visual element is detected |
| More audio records per block increases DB load | Minimal impact: typical blocks have 0-2 visual elements, so 1-3 records vs 1 |
| More OSS uploads per block | Minimal impact: same total audio data, just split into smaller files |
| Frontend backward compatibility | `position` defaults to 0; old audio records work as-is |
| Edge case: visual element at start/end of block | Empty text segments are filtered out; position count adjusts accordingly |
