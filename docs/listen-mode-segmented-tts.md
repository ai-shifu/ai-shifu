# Listen Mode: Segmented TTS Between Visual Elements

## Background

In **Listen Mode** (audiovisual / 视听模式), the LLM can return a mixture of:

- speakable text
- visual elements treated as boundaries (e.g. `<svg>...</svg>`, `<img ...>`, mermaid/code fences, HTML sandbox blocks)

Sandbox HTML blocks are visual boundaries and must **never** be narrated in Listen Mode.

Today, the backend synthesizes speech in *provider-safe chunks* (sentence/length-based) and then **concatenates the whole block into a single audio file**. This prevents the frontend from synchronizing narration with multiple visual segments inside the same generated block.

## Requirement Baseline (2026-02-11)

Reference section: [`Requirement Baseline (2026-02-11)`](#requirement-baseline-2026-02-11)

### Core Rules

- Rule A: each visual element (`table/svg/img/html/div/iframe/video/markdown table`) plus its following narration text forms one slide unit.
- Rule B: slide switching happens only after the narration audio for that slide finishes.
- Rule C: behavior must remain identical for single-block and cross-block content.
- Rule D: interaction popup always opens on the current slide and must not re-show title content.

### Examples

- Single block: `<svg>...</svg> text A <svg>...</svg> text B` maps to two slide units.
- Cross block: block A ends with `<svg>...</svg>`, block B starts with narration text, that narration belongs to block A visual slide.
- No narration after visual: visual slide stays until manual next (default policy).
- Multi interactions on one page: interactions are queued in order and are not overwritten.

## Goals

- Generate **multiple audio files per generated block**, each representing **one speakable segment between visual elements**.
- Keep the existing “split long text into safe segments + concatenate” logic **within each speakable segment**.
- Let the **frontend control pacing** (when to advance visuals and when to play each audio segment).
- Make changes as small as possible and **reuse existing TTS pipeline**.
- **No extra on-demand TTS calls during `run`**: Listen Mode uses **RUN SSE** streaming TTS as the source of truth.

## Non-goals

- Perfect semantic alignment between text and visuals (we only align by structural boundaries).
- Redesign of `markdown-flow` content format.
- Changing how visuals are rendered (we use existing segmentation on the frontend).

## Current Implementation (What We Observed)

### Backend (audio generated as a single file per block)

1. **Streaming TTS during `run` (Listen Mode)**:
   - `src/api/flaskr/service/learn/context_v2.py` initializes `StreamingTTSProcessor` when `listen=true`.
   - `src/api/flaskr/service/tts/streaming_tts.py`:
     - `process_chunk()` preprocesses the full buffer via `preprocess_for_tts()` (which removes SVG/HTML/images).
     - `finalize()` concatenates all synthesized segments into one MP3 and writes **one** `LearnGeneratedAudio` row.

2. **On-demand TTS for a generated block**:
   - API: `POST /api/learn/shifu/<shifu_bid>/generated-blocks/<generated_block_bid>/tts`
   - `src/api/flaskr/service/learn/learn_funcs.py::stream_generated_block_audio()`:
     - splits by max length (`split_text_for_tts`)
     - concatenates into one MP3
     - writes **one** `LearnGeneratedAudio` row.

3. **Record fetch**:
   - `src/api/flaskr/service/learn/learn_funcs.py::get_learn_record()` currently maps
     `generated_block_bid -> audio_url` (single string), which cannot represent multiple audio segments.

### Frontend (visuals segmented, audio not)

- Listen Mode uses `splitContentSegments(content, true)` from `markdown-flow-ui` to split content into:
  - `text` (plain text between boundaries)
  - `markdown` / `sandbox` (visual / sandbox blocks)
- Code reference (source embedded in build artifacts):
  - `src/cook-web/node_modules/markdown-flow-ui/dist/components/ContentRender/utils/split-content.cjs.js.map`
- The Listen Mode PPT renderer currently only builds slides from `markdown`/`sandbox` segments:
  - `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts::useListenContentData()`
  - Audio is still treated as **one** track per `generated_block_bid`.

## Proposed Changes

### Query Constraint: No DB Joins (No 联查)

We **must not** use database join queries for parent/child data reads (e.g. SQLAlchemy `join()`, `outerjoin()`, `joinedload()`).

Required pattern for parent-child reads:

1. Query the **parent** table first (e.g. generated blocks).
2. Collect `parent_bid` (or equivalent business IDs) into a list.
3. Query the **child** table with `child.parent_bid IN (...)` (and other filters), then **compose** the response in Python/TypeScript.

Concrete example for this feature (already consistent with current code in `get_learn_record()`):

- Parent: `LearnGeneratedBlock` (ordered list for a progress record)
- Child: `LearnGeneratedAudio` filtered by `generated_block_bid IN (parent_bids)` and `deleted/status`
- Compose: `audios_by_block_bid[generated_block_bid] = sorted(list, key=position)`

### Listen Mode Source Of Truth: RUN SSE Only

Listen Mode must **not** auto-trigger additional TTS synthesis via:

- `POST /api/learn/shifu/<shifu_bid>/generated-blocks/<bid>/tts?listen=true`

Instead, Listen Mode relies on **RUN SSE** streaming audio events:

- `audio_segment` and `audio_complete`

When AV segmentation is enabled (Listen Mode), the backend run SSE stream must emit
multiple audio tracks per block, identified by `position`.

### 1) Database: add `position` to `learn_generated_audios`

Add a new integer field:

- `position INT NOT NULL DEFAULT 0`
- meaning: **0-based index** of the audio segment **within the same `generated_block_bid`**

Notes:

- Existing rows will automatically be treated as `position=0` (via default/backfill).
- Existing `segment_count` keeps its current meaning: number of internal provider-safe segments (sentence/length-based) used to build this *one* audio file.

Files:

- Model: `src/api/flaskr/service/tts/models.py::LearnGeneratedAudio`
- Migration: new Alembic migration under `src/api/migrations/versions/` (do not edit applied migrations).

### 2) Backend: split “speakable segments” by the same boundaries as the frontend

We will implement a backend helper to produce **ordered speakable segments** from a block’s `generated_content`.

Source-of-truth for boundary rules (frontend):

- `splitContentSegments(raw, keepText=true)` in `markdown-flow-ui` splits on:
  - `<svg...></svg>` (outside fenced code)
  - `<img ...>` (inline HTML)
  - Markdown images `!\[...\](...)`
  - Markdown tables (pipe table blocks, treat as visual)
  - mermaid fences and other fenced code blocks
  - “sandbox HTML blocks” beginning with tags like `script/style/iframe/div/section/...` (outside fences)

Cook Web Listen Mode additionally treats these HTML blocks as visual boundaries
for slide rendering (post-processing the `splitContentSegments` output):

- `<video ...></video>`
- `<table ...></table>`
- `<iframe ...></iframe>` (Admin “Insert Video”, e.g. Bilibili embeds)

Notes:

- MarkdownFlow fixed markers like `=== <iframe ...></iframe> ===` can confuse
  `splitContentSegments` (it may swallow following visuals into one sandbox).
  Listen Mode applies a small post-processing split so each visual stays on its
  own slide and narration remains in `text` segments.

Backend helper (new):

- `split_av_speakable_segments(raw: str) -> list[str]`
  - returns only the **text segments between visual boundaries**, in order
  - each entry is later passed through `preprocess_for_tts()` before synthesis (so we keep TTS-cleaning behavior consistent)

Why this approach:

- Keeps segmentation aligned with the frontend’s visual segmentation.
- Avoids large changes to existing `preprocess_for_tts` / `split_text_for_tts` / `concat_audio_best_effort` pipeline.

### 3) Backend: segmented TTS synthesis + persistence

When segmented AV TTS is enabled for a block:

1. Split raw content into `speakable_segments[]`.
2. For each speakable segment `i`:
   - run existing long-text pipeline (split by length/sentence + concat)
   - upload resulting MP3 to OSS
- persist a `LearnGeneratedAudio` row with:
     - `generated_block_bid = ...`
     - `audio_bid = new uuid`
      - `position = i`
      - `duration_ms`, `segment_count`, etc.

### 4) API + DTO changes

#### 4.1 Persisted records (`/records`)

Extend `GeneratedBlockDTO` to include a list:

- `audios: [{ position, audio_url, audio_bid, duration_ms }]`

Keep `audio_url` for backward compatibility if needed, but Listen Mode should prefer `audios`.

Files:

- DTO: `src/api/flaskr/service/learn/learn_dtos.py::GeneratedBlockDTO`
- Data assembly: `src/api/flaskr/service/learn/learn_funcs.py::get_learn_record()`

#### 4.2 On-demand TTS (`/generated-blocks/<bid>/tts`)

Keep a query param (or a new endpoint) to avoid breaking existing behavior:

- `?listen=true` (recommended)

Behavior:

- `listen=false` (default): existing single-audio behavior remains.
- `listen=true`: stream or return multiple audio segments, each with `position`.

Important:

- This endpoint is **manual/backfill only** and must not be auto-called by Listen Mode during `run`.

SSE payload additions:

- Add `position` to `AudioSegmentDTO` and `AudioCompleteDTO` (optional, default `0`).

Files:

- Endpoint: `src/api/flaskr/service/learn/routes.py`
- Logic: `src/api/flaskr/service/learn/learn_funcs.py::stream_generated_block_audio()`
- DTOs: `src/api/flaskr/service/learn/learn_dtos.py::AudioSegmentDTO`, `AudioCompleteDTO`

### 5) Frontend: playback orchestration (frontend-controlled rhythm)

Listen Mode should treat audio as **multiple tracks per generated block**:

- Parse content using `splitContentSegments(content, true)` to obtain an ordered list of segments (`text`/`markdown`/`sandbox`).
- Compute `position -> page` by simulating the backend segmentation behavior:
- One audio `position` corresponds to one “narration window” between visual boundaries.
- Map that narration window to the closest preceding visual slide page.
- If narration appears before the first visual, map it to a placeholder slide (so the first position has a stable page).

Data model changes (frontend):

- Extend `StudyRecordItem` and `ChatContentItem` to store `audios[]` instead of only `audioUrl`.
- Update Listen Mode sequencing (`useListenAudioSequence`) to iterate through `(generated_block_bid, position)` pairs.

Backward compatibility:

- If a block has `audios.length <= 1`, keep existing behavior (one track).

## Rollout / Risk Control

- Keep normal chat mode using the existing single-audio behavior unless explicitly updated later.
- Listen Mode relies on RUN SSE and does **not** auto-call the on-demand TTS endpoint.

## Testing Plan

Backend:

- Unit tests for `split_av_speakable_segments` using fixtures with:
  - multiple `<svg>` blocks
  - markdown images
  - fenced code blocks (ensure we do not split inside fences)
  - HTML sandbox blocks
- Integration test for `/generated-blocks/<bid>/tts?listen=true`:
  - verify DB writes multiple rows with increasing `position`
  - verify SSE payload includes `position`

Frontend:

- Manual test: one block containing multiple SVGs and text segments.
  - confirm slide advances + narration segments align
  - confirm pause/next/prev works
- Regression: non-listen mode audio playback still works for blocks with single audio.
