# Design: Segmented TTS Audio By Sandbox Boundaries In Listen Mode

Date: 2026-02-10

## Background

In listen/audiovisual mode, LLM output for a single generated content block may include both:

- Speakable markdown text
- Non-speakable “sandbox elements” (e.g. SVG and other content rendered as `sandbox` segments on the frontend)

Current behavior synthesizes TTS for the whole block as a continuous stream and then concatenates all TTS segments into a single MP3. Because sandbox elements are stripped during TTS preprocessing, there is no natural audio boundary where the frontend can pause/advance sandbox slides. This makes it difficult for the frontend to synchronize “audio rhythm” with sandbox/visual slides.

## Requirements

1. Keep the existing “long text splitting” behavior (provider-safe segmentation), but additionally split audio at **all sandbox boundaries** (not SVG-only).
2. The frontend controls pacing/synchronization (when to play/pause and when to advance slides).
3. Add `position` to `learn_generated_audios` to indicate which “audio part” this record is within a generated block.
4. Each sandbox element and the speech **after it** form one unit. Only after that unit’s speech finishes should the UI switch to the next sandbox element.
5. If a block contains no sandbox elements (audio-only), keep the existing “just play audio” behavior.

## Current Implementation (Code Audit)

### Backend

- TTS preprocessing strips SVG entirely:
  - `src/api/flaskr/service/tts/__init__.py` (`preprocess_for_tts`)
  - Uses `SVG_PATTERN = re.compile(r\"<svg[\\s\\S]*?</svg>\", ...)` and replaces SVG blocks with `\"\"` (removes them).

- Streaming TTS during lesson run (listen mode):
  - `src/api/flaskr/service/learn/context_v2.py`
    - `_should_stream_tts()` is true when `listen=true` and `preview_mode=false`.
    - Creates `StreamingTTSProcessor` and calls `tts_processor.process_chunk(chunk_content)` during `ProcessMode.STREAM`.
  - `src/api/flaskr/service/tts/streaming_tts.py`
    - `process_chunk()` appends raw chunk into `_buffer`.
    - `_try_submit_tts_task()` calls `preprocess_for_tts(self._buffer)` which removes SVG, then segments by sentence endings / `max_segment_chars`.
    - `finalize()` waits for pending segments, concatenates all yielded audio, uploads one MP3 to OSS, persists **one** `LearnGeneratedAudio` record, then yields `audio_complete`.

- On-demand TTS for a persisted generated block:
  - `POST /api/learn/shifu/<shifu_bid>/generated-blocks/<generated_block_bid>/tts`
  - `src/api/flaskr/service/learn/learn_funcs.py` (`stream_generated_block_audio`)
    - `split_text_for_tts()` -> `preprocess_for_tts()` -> no SVG boundary.
    - Concatenates into **one** audio, uploads to OSS, persists **one** `LearnGeneratedAudio`.

- History record retrieval:
  - `src/api/flaskr/service/learn/learn_funcs.py` (`get_learn_record`)
    - Loads `LearnGeneratedAudio` by `generated_block_bid` and maps to a single `audio_url` per block.

### Frontend

- Listen mode creates PPT-like slides from content segments:
  - `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts`
    - Uses `splitContentSegments(item.content, true)` from `markdown-flow-ui/renderer`.
    - Renders segments of type `markdown` and `sandbox` as Reveal slides.
    - Audio sequencing is **per content block**, not per segment.

- Audio playback:
  - `src/cook-web/src/components/audio/AudioPlayer.tsx`
    - Supports streaming base64 segments (`audio_segment`) and final OSS URL (`audio_complete`).
    - Assumes one audio track per content block.

## Problem Summary

Because sandbox elements are removed during TTS preprocessing, audio for “speech before sandbox” and “speech after sandbox” becomes continuous. The frontend can render sandbox as its own slide, but cannot reliably pause audio at the sandbox boundary (no persisted boundary-aligned audio artifacts exist).

## Proposed Design

### Scope / Phasing

To keep changes small and reuse existing logic, the rollout is split into phases:

1. **Phase 1 (Persisted, on-demand):** Generate **sandbox-boundary-aligned** audio parts via the existing on-demand endpoint (`/generated-blocks/:id/tts`), persist them with `position`, and let the frontend control pacing (history + fallback).
2. **Phase 2 (Streaming, run-SSE):** Make the run-SSE streaming TTS processor part-aware (`StreamingTTSProcessor`), so audio can start before the whole block finishes generating (real-time listen mode).

Phase 1 solves the persistence/history problem. Phase 2 enables true audiovisual synchronization while content is still streaming.

### Data Model

Add an integer field `position` to `learn_generated_audios`:

- Meaning: the audio part index within the same `generated_block_bid`.
- Index base: **0-based** (consistent with existing `segment_index` usage).
- Default: `0` for legacy single-audio-per-block records.
- Add an index (and optionally a composite index) to support fast lookup:
  - Recommended: `INDEX(generated_block_bid, position, status, deleted)`

### Audio Segmentation Strategy

Define “sandbox boundaries” as elements the frontend would render as `sandbox` segments, and that should create a hard audio boundary for TTS.

Implementation scope:

- Include all sandbox elements (frontend `segment.type === 'sandbox'`).
- Practically on backend, this means detecting these blocks in raw markdown and treating them as boundary markers.

Algorithm (full-block, non-streaming):

1. Split the raw generated markdown into **units** by sandbox boundaries.
2. Apply the unit rule:
   - Each sandbox element belongs to the **next** speakable section (speech after the sandbox).
   - If there is speakable text before the first sandbox, it becomes a standalone audio part.
3. For each speakable section:
   - Run existing `preprocess_for_tts(section)` to keep current cleaning rules.
   - If the result is empty or too short, skip creating audio for that section.
4. For each remaining section, synthesize via the existing long-text pipeline:
   - Keep current provider-safe splitting + concatenation inside each section.
   - Persist a `LearnGeneratedAudio` record with the corresponding `position`.

This keeps changes small and reuses the current, battle-tested TTS splitting and OSS upload logic.

### `position` Semantics (0-based)

`position` is the index of the speakable audio parts within the same `generated_block_bid` in playback order.

- If there is speakable text before the first sandbox: it is `position=0`.
- The first “sandbox + following speech” unit’s speech is then `position=1`.
- Otherwise (no leading speakable text): the first unit’s speech is `position=0`.

Frontend pacing:

- When sandbox exists: show sandbox `k`, play the corresponding audio part for that unit, and only after it ends advance to sandbox `k+1`.
- When no sandbox exists: play available audio parts sequentially (typically a single part).

### Backend API / SSE Contract Changes

To let the frontend control rhythm, it must know which audio it is receiving. Extend audio events with `position`:

- `audio_segment` payload:
  - Existing: `segment_index`, `audio_data`, `duration_ms`, `is_final`
  - Add: `position` (int)

- `audio_complete` payload:
  - Existing: `audio_url`, `audio_bid`, `duration_ms`
  - Add: `position` (int)
  - Add: `is_last` (bool) to indicate the last part in this SSE stream (frontend closes SSE only when `is_last=true`)

This is backward-compatible for clients that ignore unknown fields.

### History API Change (New Field Returning a List)

For persisted lesson records (`GET /api/learn/shifu/<shifu_bid>/records/<outline_bid>`), return multiple audios per generated block via a new field (keep `audio_url` for legacy consumers if needed).

Recommended shape (snake_case):

```json
{
  "generated_block_bid": "....",
  "content": "....",
  "block_type": "content",
  "audio_url": "https://.../legacy.mp3",
  "audio_list": [
    { "position": 0, "audio_url": "https://.../p0.mp3", "audio_bid": "....", "duration_ms": 1234 },
    { "position": 1, "audio_url": "https://.../p1.mp3", "audio_bid": "....", "duration_ms": 2345 }
  ]
}
```

### Backend Changes (High Level)

1. Migration + model update for `position`.
2. Add a backend helper to split content into speakable sections by sandbox boundaries.
3. Update on-demand endpoint `stream_generated_block_audio()` to synthesize/persist **multiple** audios per block (one per `position`), emitting SSE events with `position`.
4. (Phase 2) Update streaming listen-mode processor `StreamingTTSProcessor` to become “part-aware” using the same boundary logic:
   - Emit `audio_segment` events with `position`.
   - Mark the last segment of each part as `is_final=true` so the frontend can advance immediately without waiting for OSS upload.
   - Persist/upload one audio per `(generated_block_bid, position)` during `finalize()`.

### Frontend Changes (High Level)

Goal: the frontend controls pacing by aligning sandbox segments (visual units) with audio parts (`position`).

1. Extend TS types in `src/cook-web/src/c-api/studyV2.ts` to include optional `position`.
2. Extend audio state to support multiple parts per block, keyed by `position`:
   - e.g. `audioParts: Record<number, { audioUrl?, audioSegments?, isStreaming?, durationMs? }>`
3. Update SSE handlers to upsert audio segments/completions by `(generated_block_bid, position)`.
4. In listen mode, enable sandbox-aligned streaming TTS via run-SSE:
   - Send `listen=true` in the run request body to start part-aware streaming audio during generation.
   - Handle run-SSE `audio_segment/audio_complete` events and upsert by `(generated_block_bid, position)`.
   - Keep `/generated-blocks/:id/tts` as fallback and for history/backfill.
5. Update listen mode sequencing (`useListenMode.ts`) to enforce unit behavior:
   - Each sandbox and its following speech is one unit.
   - Do not advance to the next sandbox until the current unit’s audio finishes.
   - If the block has no sandbox, keep existing playback (just continue).

## Backward Compatibility / Rollout

To minimize risk:

- Restrict the “split-by-sandbox” behavior to listen mode first (where the problem exists).
- Keep `position=0` for legacy single-audio-per-block records.
- Extend history record APIs to return a list via a **new field** (while optionally keeping `audio_url` for legacy consumers).

## Testing & Verification

Backend:

- Unit tests for the split helper (multiple sandbox blocks, leading/trailing sandbox, nested/escaped HTML, incomplete sandbox during streaming).
- Integration test for listen-mode streaming TTS:
  - Given streaming chunks that include sandbox blocks, expect multiple `audio_complete` events with increasing `position`, and multiple DB rows.

Frontend:

- E2E/manual: a block with `text -> sandbox -> text` should:
  - Show sandbox, play the “following speech” audio part, then advance to next sandbox only when audio ends.

## Notes

- Boundary definition is “all sandbox elements”.
- `position` is 0-based.
- History API should return a list via a new field (do not remove existing fields unless required by frontend migration).

## Appendix: Key Files

Backend:

- `src/api/flaskr/service/tts/__init__.py`
- `src/api/flaskr/service/tts/streaming_tts.py`
- `src/api/flaskr/service/learn/context_v2.py`
- `src/api/flaskr/service/learn/learn_funcs.py`
- `src/api/flaskr/service/tts/models.py`

Frontend:

- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts`
- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/ListenModeRenderer.tsx`
- `src/cook-web/src/components/audio/AudioPlayer.tsx`
- `src/cook-web/src/c-utils/audio-utils.ts`
- `src/cook-web/src/c-api/studyV2.ts`
