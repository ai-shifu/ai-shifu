# Audio-Visual Synchronization Design

## Background

In listen mode (audio-visual mode), LLM responses may contain both text and visual elements (SVG, HTML fragments, tables, images, videos, Mermaid diagrams, code blocks, etc.). Currently, the backend's `StreamingTTSProcessor` strips all visual elements from text before TTS synthesis, then concatenates all audio segments into a single audio file per block. This makes it impossible for the frontend to synchronize audio playback with visual element rendering.

**Current Flow:**
```
LLM Output: "Text A" + <svg>...</svg> + "Text B" + ![img](url) + "Text C"
    ↓
TTS Preprocessing: strips all non-speakable content → "Text A Text B Text C"
    ↓
Audio Segments: [seg0..segN] (split only by char count)
    ↓
Final: One concatenated audio per block
    ↓
Frontend: Plays one audio, renders all content at once (no sync)
```

**Target Flow:**
```
LLM Output: "Text A" + <svg>...</svg> + "Text B" + ![img](url) + "Text C"
    ↓
Visual-Aware Splitting: detect all visual boundaries
    ↓
Audio Position 0: TTS("Text A")        → AUDIO_COMPLETE(position=0)
Visual Marker:    <svg>...</svg>        → VISUAL_MARKER(visual_type="svg")
Audio Position 1: TTS("Text B")        → AUDIO_COMPLETE(position=1)
Visual Marker:    ![img](url)           → VISUAL_MARKER(visual_type="image")
Audio Position 2: TTS("Text C")        → AUDIO_COMPLETE(position=2)
    ↓
Frontend Event Queue:
  1. Play audio position 0
  2. Wait for audio 0 to finish → render SVG
  3. Play audio position 1
  4. Wait for audio 1 to finish → render image
  5. Play audio position 2
  6. On INTERACTION → wait for user input
```

## Supported Visual Content Types

All of the following content types are treated as **visual boundaries** that split audio:

| Type | Pattern | Example | `visual_type` value |
|------|---------|---------|---------------------|
| SVG | `<svg>...</svg>` | Inline vector graphics | `svg` |
| Mermaid diagram | ` ```mermaid...``` ` | Flow charts, sequence diagrams | `mermaid` |
| Code block | ` ```lang...``` ` | Syntax-highlighted code | `code` |
| Markdown image | `![alt](url)` | `![chart](https://...)` | `image` |
| HTML `<img>` tag | `<img ... />` or `<img ...>` | `<img src="...">` | `image` |
| Markdown table | `\|...\|` with `\|---\|` | Data tables | `table` |
| iframe / video embed | `<iframe>...</iframe>` | Bilibili, YouTube embeds | `iframe` |
| Generic HTML block | `<div>...</div>`, `<section>...</section>` | Rich HTML fragments | `html` |
| Math block | `<math>...</math>` or `$$...$$` | Mathematical formulas | `math` |

### Detection Priority

When multiple visual elements are adjacent or nested, the **first complete match** in buffer order takes priority. Detection is applied iteratively — after splitting at one boundary, the remaining buffer is re-scanned.

## Current Architecture Analysis

### Backend

#### Key Files
| File | Role |
|------|------|
| `src/api/flaskr/service/tts/models.py` | `LearnGeneratedAudio` DB model |
| `src/api/flaskr/service/tts/__init__.py` | `preprocess_for_tts()` - strips SVG/code/markdown |
| `src/api/flaskr/service/tts/streaming_tts.py` | `StreamingTTSProcessor` - real-time TTS during streaming |
| `src/api/flaskr/service/learn/context_v2.py` | Block processing, SSE event yielding |
| `src/api/flaskr/service/learn/learn_dtos.py` | `AudioSegmentDTO`, `AudioCompleteDTO`, `RunMarkdownFlowDTO` |

#### Current StreamingTTSProcessor Flow
1. `process_chunk(chunk)`: Accumulates text buffer, calls `preprocess_for_tts()` to strip visual elements, submits TTS tasks at sentence boundaries (~300 chars).
2. All segments are yielded as `AUDIO_SEGMENT` events (base64 encoded).
3. `finalize()`: Concatenates all segments into one file, uploads to OSS, saves one `LearnGeneratedAudio` record, yields `AUDIO_COMPLETE`.

#### Current preprocess_for_tts()
Already strips all visual content types:
- SVG (`<svg>...</svg>`)
- Mermaid (` ```mermaid...``` `)
- Code blocks (` ```...``` `, `` `...` ``)
- Images (`![alt](url)`)
- HTML tags (`<[^>]*>`)
- XML blocks (`<math>`, `<script>`, `<style>`)
- Data URIs (`data:...`)
- Handles incomplete blocks during streaming (partial SVG, unclosed fences)

### Frontend

#### Key Files
| File | Role |
|------|------|
| `src/cook-web/src/c-api/studyV2.ts` | SSE event types, `/run` endpoint |
| `src/cook-web/src/c-utils/audio-utils.ts` | Audio segment merge utilities |
| `src/cook-web/src/app/c/.../useChatLogicHook.tsx` | SSE message handler, content state |
| `src/cook-web/src/app/c/.../useListenMode.ts` | Listen mode: PPT slides + audio sequence |
| `src/cook-web/src/components/audio/AudioPlayer.tsx` | Streaming + URL audio playback |
| `src/cook-web/src/app/c/.../ContentIframe.tsx` | IframeSandbox for HTML/iframe rendering |

#### Current Listen Mode Flow
1. `useListenContentData`: Maps content items to slides and audio sequence list.
2. `useListenPpt`: Manages Reveal.js slide rendering and navigation.
3. `useListenAudioSequence`: Plays audio items in sequence, advances slides.
4. INTERACTION items cause a 2-second pause then advance.

## Design

### Principle: Minimal Changes, Maximum Reuse

The core strategy is to **split a single block's audio at visual element boundaries** into multiple positional audio records, and introduce a lightweight **VISUAL_MARKER** SSE event so the frontend can build an ordered event queue.

### 1. Database Changes

#### Add `position` field to `learn_generated_audios`

```python
# In LearnGeneratedAudio model
position = Column(
    SmallInteger,
    nullable=False,
    default=0,
    comment="Audio position index within the block (0-based)",
)
```

This field indicates the ordinal position of this audio segment within a block. A block with no visual elements has one audio with `position=0`. A block with one visual element in the middle has two audios: `position=0` (text before) and `position=1` (text after).

**Migration**: Add column with `ALTER TABLE learn_generated_audios ADD COLUMN position SMALLINT NOT NULL DEFAULT 0`.

### 2. Backend Changes

#### 2.1 New SSE Event Type: VISUAL_MARKER

Add to `GeneratedType` enum:
```python
VISUAL_MARKER = "visual_marker"
```

Add DTO:
```python
class VisualMarkerDTO(BaseModel):
    position: int          # Position in the block's event sequence
    visual_type: str       # "svg", "mermaid", "code", "image", "table", "iframe", "html", "math"
    content: str = ""      # Raw visual content (for frontend to render independently if needed)
```

This event tells the frontend: "A visual element should be displayed here, between audio position N-1 and audio position N."

#### 2.2 Visual Boundary Detection Patterns

All patterns for visual content that should split audio:

```python
# Paired tag patterns (opening + closing tag)
VISUAL_PAIRED_TAG_PATTERNS = [
    # SVG: <svg ...>...</svg>
    (re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE), "svg"),
    # iframe (Bilibili, YouTube, etc.): <iframe ...>...</iframe>
    (re.compile(r"<iframe[\s\S]*?</iframe>", re.IGNORECASE), "iframe"),
    # Math block: <math ...>...</math>
    (re.compile(r"<math[\s\S]*?</math>", re.IGNORECASE), "math"),
    # Generic HTML block: <div ...>...</div>, <section>, <article>, <figure>
    (re.compile(r"<(div|section|article|figure|details|blockquote)[^>]*>[\s\S]*?</\1>", re.IGNORECASE), "html"),
]

# Fenced block patterns (``` delimited)
VISUAL_FENCED_PATTERNS = [
    # Mermaid diagrams
    (re.compile(r"```mermaid[\s\S]*?```"), "mermaid"),
    # Code blocks (any language)
    (re.compile(r"```[a-zA-Z]*\n[\s\S]*?```"), "code"),
]

# Inline/self-closing patterns
VISUAL_INLINE_PATTERNS = [
    # Markdown image: ![alt](url)
    (re.compile(r"!\[[^\]]*\]\([^)]+\)"), "image"),
    # HTML img tag: <img ... /> or <img ...>
    (re.compile(r"<img\s[^>]*?/?>", re.IGNORECASE), "image"),
    # Markdown table: detect header row + separator row
    (re.compile(r"(?:^|\n)\|[^\n]+\|\s*\n\|[\s:|-]+\|\s*\n(?:\|[^\n]+\|\s*\n?)*", re.MULTILINE), "table"),
    # LaTeX display math: $$...$$
    (re.compile(r"\$\$[\s\S]*?\$\$"), "math"),
]
```

#### 2.3 Visual-Aware Audio Splitting — VisualAwareTTSOrchestrator

**Implementation approach — wrap rather than rewrite**:

Rather than deeply modifying `StreamingTTSProcessor`, create a **`VisualAwareTTSOrchestrator`** that wraps it:

```python
class VisualAwareTTSOrchestrator:
    """
    Orchestrates multiple StreamingTTSProcessor instances,
    splitting at visual element boundaries.

    Detects SVG, images, tables, iframes, code blocks, mermaid diagrams,
    HTML blocks, math blocks, etc. in the streaming text buffer.
    When a complete visual element is found, the current audio is finalized,
    a VISUAL_MARKER event is emitted, and a new audio position begins.
    """
    def __init__(self, ...same params as StreamingTTSProcessor...):
        self._position = 0
        self._raw_buffer = ""
        self._current_processor = self._create_processor()
        # ...params stored for creating new processors...

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        self._raw_buffer += chunk

        # Iteratively find and split at visual boundaries
        while True:
            visual_match = self._find_earliest_complete_visual()
            if not visual_match:
                break

            match_obj, visual_type = visual_match
            text_before = self._raw_buffer[:match_obj.start()]
            visual_content = match_obj.group()
            text_after = self._raw_buffer[match_obj.end():]

            # Feed text_before to current processor and finalize
            if text_before.strip():
                # Feed remaining pre-visual text
                yield from self._feed_and_finalize_current(text_before)
            else:
                # No meaningful text before visual, just finalize empty
                yield from self._finalize_current_if_has_content()

            # Yield visual marker
            yield RunMarkdownFlowDTO(
                ...,
                type=GeneratedType.VISUAL_MARKER,
                content=VisualMarkerDTO(
                    position=self._position,
                    visual_type=visual_type,
                    content=visual_content,
                ),
            )
            self._position += 1

            # Start new processor for text after
            self._current_processor = self._create_processor()
            self._raw_buffer = text_after

        # No more visual boundaries in buffer — feed to current processor
        # (only feed the delta that hasn't been processed yet)
        yield from self._current_processor.process_chunk(chunk_delta)

    def finalize(self, ...) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._current_processor.finalize(position=self._position, ...)
```

**Key design decisions:**
- The orchestrator accumulates the **raw** (unprocessed) buffer to detect visual elements, because `preprocess_for_tts()` would strip them.
- Each `StreamingTTSProcessor` instance independently handles its own text segment's sentence-boundary splitting and TTS synthesis.
- The global `_tts_executor` thread pool is shared across all processor instances.

#### 2.4 Modified AudioCompleteDTO

Add `position` field:
```python
class AudioCompleteDTO(BaseModel):
    audio_url: str
    audio_bid: str
    duration_ms: int
    position: int = 0  # NEW: position within block
```

#### 2.5 Modified AudioSegmentDTO

Add `position` field:
```python
class AudioSegmentDTO(BaseModel):
    segment_index: int
    audio_data: str
    duration_ms: int
    is_final: bool
    position: int = 0  # NEW: which audio position this segment belongs to
```

#### 2.6 context_v2.py Changes

In the block processing loop (`run_inner`), replace:
```python
tts_processor = StreamingTTSProcessor(...)
```
with:
```python
tts_processor = VisualAwareTTSOrchestrator(...)
```

The orchestrator exposes the same `process_chunk()` / `finalize()` interface, so the change in `context_v2.py` is minimal.

### 3. Frontend Changes

#### 3.1 New SSE Event Type

In `studyV2.ts`:
```typescript
SSE_OUTPUT_TYPE = {
  // ...existing...
  VISUAL_MARKER: 'visual_marker',
}
```

#### 3.2 Event Queue Architecture for Listen Mode

The core idea: instead of directly playing audio and rendering content, build an **ordered event queue** and process events sequentially.

```typescript
type EventQueueItem =
  | { type: 'audio'; blockBid: string; position: number; /* audio data */ }
  | { type: 'visual'; blockBid: string; position: number; visualType: string; content: string; }
  | { type: 'interaction'; blockBid: string; /* interaction data */ };
```

**Processing rules:**
1. **Audio event**: Play the audio. When playback finishes, advance to next event.
2. **Visual event**: Wait for previous audio to finish, then render the visual element, then advance to next event immediately (visual rendering is instant).
3. **Interaction event**: Wait for all previous audio to finish, render the interaction UI, wait for user submission before advancing.

**Implementation location**: Extend `useListenAudioSequence` in `useListenMode.ts`.

Currently, `useListenAudioSequence` already sequences audio items. The change is to:
1. Add `VISUAL_MARKER` and `INTERACTION` items to the sequence list.
2. Modify `playAudioSequenceFromIndex` to handle visual markers (show content, advance immediately).
3. Modify interaction handling to truly wait for user input.

#### 3.3 AudioPlayer Changes

Minimal changes needed. The `AudioPlayer` component already handles per-block audio. With the new `position` field, each "positional audio" within a block becomes a separate audio item in the sequence list.

#### 3.4 Audio-Utils Changes

Update `AudioItem` interface:
```typescript
export interface AudioItem {
  generated_block_bid: string;
  position?: number;        // NEW
  audioSegments?: AudioSegment[];
  audioUrl?: string;
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
}
```

Update `AudioSegment`:
```typescript
export interface AudioSegment {
  segmentIndex: number;
  audioData: string;
  durationMs: number;
  isFinal: boolean;
  position?: number;         // NEW
}
```

#### 3.5 Content Rendering in Listen Mode

Currently, `useListenContentData` maps each content item to a slide. For visual-aware sync:
- Content items remain as slides (text + visual elements rendered together in markdown).
- The event queue controls **when** each slide becomes visible.
- A slide containing visual elements is held hidden until the preceding audio finishes.

This leverages the existing `shouldHoldForStreamingAudio` pattern in `useListenPpt`, extending it to hold slides until the audio queue reaches the visual marker.

### 4. Backward Compatibility

- **`position` defaults to 0**: Existing audio records work unchanged.
- **`VISUAL_MARKER` is a new event**: Old frontends ignore unknown SSE types.
- **`AudioCompleteDTO.position` defaults to 0**: Old behavior preserved.
- **Non-listen mode**: `VisualAwareTTSOrchestrator` is only used when `_should_stream_tts()` returns True, which only happens in listen mode.

### 5. Data Flow Diagram — Multiple Visual Types

```
Block LLM Output (streaming):
  "Here is the data:"
  + | Name | Score |    (markdown table)
    |------|-------|
    | Alice| 95    |
  + "And a visualization:"
  + <svg>...</svg>
  + "Watch the tutorial:"
  + <iframe src="bilibili...">...</iframe>
  + "In summary..."
           │
           ▼
  VisualAwareTTSOrchestrator
           │
           ├─ TTS("Here is the data:")
           │    └─ AUDIO_COMPLETE(position=0)
           │
           ├─ VISUAL_MARKER(position=1, visual_type="table", content="|Name|Score|...")
           │
           ├─ TTS("And a visualization:")
           │    └─ AUDIO_COMPLETE(position=1)
           │
           ├─ VISUAL_MARKER(position=2, visual_type="svg", content="<svg>...</svg>")
           │
           ├─ TTS("Watch the tutorial:")
           │    └─ AUDIO_COMPLETE(position=2)
           │
           ├─ VISUAL_MARKER(position=3, visual_type="iframe", content="<iframe>...</iframe>")
           │
           └─ TTS("In summary...")
                └─ AUDIO_COMPLETE(position=3)
           │
           ▼
  Frontend Event Queue:
    [0] Audio(pos=0)       → Play "Here is the data:"
    [1] Visual(table)      → Wait for [0], show table
    [2] Audio(pos=1)       → Play "And a visualization:"
    [3] Visual(svg)        → Wait for [2], show SVG
    [4] Audio(pos=2)       → Play "Watch the tutorial:"
    [5] Visual(iframe)     → Wait for [4], show Bilibili video
    [6] Audio(pos=3)       → Play "In summary..."
```

### 6. Edge Cases

| Scenario | Handling |
|----------|----------|
| Block has no visual elements | Single audio with position=0, same as current behavior |
| Multiple visual elements in one block | Multiple audio positions, multiple visual markers |
| Visual element at start of block | position=0 audio is empty/skipped, visual marker emitted directly |
| Visual element at end of block | Last audio position has text before visual, visual marker last |
| Text too short between visuals (<2 chars) | Skip empty audio, emit consecutive visual markers |
| Adjacent visuals (SVG immediately followed by table) | Two consecutive visual markers, no audio between |
| Incomplete visual during streaming | Wait for complete element before splitting (existing incomplete-block detection logic) |
| Non-listen mode | No TTS processor created, no visual markers, unchanged behavior |
| Reload existing block audio | Query by `generated_block_bid` + order by `position`, return ordered list |
| Inline code (`` `code` ``) | NOT treated as visual boundary — too small, stays in text |
| Markdown bold/italic/links | NOT visual boundaries — text kept in TTS |
| Small standalone image in paragraph | Treated as boundary, splits audio around it |
| Table inside HTML `<div>` | Outer `<div>` takes priority as boundary |

### 7. Pattern Detection — Incomplete Element Handling During Streaming

The existing `_strip_incomplete_blocks()` function in `tts/__init__.py` already handles:
- Incomplete fenced code blocks (odd number of ` ``` `)
- Incomplete SVG tags (`<svg` without `</svg>`)
- Incomplete generic HTML tags (`<div` without `>`)

The `VisualAwareTTSOrchestrator` reuses this logic: **only complete visual elements trigger a split**. Partial elements remain in the buffer until more chunks arrive and complete them.

Additional incomplete element patterns to handle:
- Incomplete markdown table (header row without separator row yet)
- Incomplete iframe (`<iframe` without `</iframe>`)
- Incomplete `$$` math block (single `$$` without closing `$$`)

### 8. Performance Considerations

- Each positional audio is independently synthesized and uploaded to OSS, which means more OSS writes per block. However, each audio file is smaller, so total storage is similar.
- The visual boundary detection runs on the accumulated raw buffer, not on every chunk, minimizing regex overhead.
- Thread pool reuse: each `StreamingTTSProcessor` instance uses the same global `_tts_executor` thread pool.
- Pattern matching is ordered by likelihood (SVG/code first, then tables/images) to short-circuit early.
