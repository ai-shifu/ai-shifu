# Listen Mode Slide-ID Unification Design (No DB Table)

Updated: 2026-02-13

## 1. Background

Current Listen Mode complexity is concentrated in frontend timeline reconstruction:

- Re-splitting content into visual segments.
- Mapping `audio position -> reveal page`.
- Recovering from async stream ordering and list shifts.

This creates duplicated parsing logic across backend and frontend and increases mismatch risk.

## 2. Target

Implement **1+2+3**:

1. Add `/run` SSE event type: `new_slide`.
2. Add `slide_id` to audio events (`audio_segment`, `audio_complete`).
3. Return same slide structure in `/records`.

Constraints:

- `slide_id` is generated dynamically (UUID), in memory only.
- No `learn_generated_slides` table for this phase.
- Keep backward compatibility with existing clients.

## 3. Non-Goals (Phase 1)

- No new DB model or migration for slides.
- No cross-session stable `slide_id`.
- No changes to non-listen mode behavior.
- No removal of legacy response fields in this phase.

## 4. Core Idea

Backend becomes the single authority for listen slide units.

- Backend emits **visual slide units** via `new_slide`.
- Backend binds each audio track to a `slide_id`.
- Frontend consumes ready-made slide timeline instead of rebuilding visual mapping heuristics.

Result:

- Frontend sequence engine operates on stable IDs (`slide_id`) instead of inferred page mapping.
- `/run` and `/records` share the same timeline contract.

## 5. Data Contract

### 5.1 New SSE Type: `new_slide`

Add `GeneratedType.NEW_SLIDE = "new_slide"`.

`new_slide.content` schema (`NewSlideDTO`):

```json
{
  "slide_id": "uuid",
  "generated_block_bid": "block_bid",
  "slide_index": 3,
  "audio_position": 1,
  "visual_kind": "svg|img|md_img|iframe|video|html_table|md_table|sandbox|placeholder",
  "segment_type": "markdown|sandbox|placeholder",
  "segment_content": "<svg>...</svg>",
  "source_span": [120, 348],
  "is_placeholder": false
}
```

Rules:

- `slide_id` unique within one run stream.
- `slide_index` monotonic in stream order.
- `audio_position` means: audio track position that should play on this slide.
- `placeholder` slide is allowed for pre-visual narration/text-only cases.

### 5.2 Audio Event Extension

Extend `AudioSegmentDTO` and `AudioCompleteDTO` with optional:

- `slide_id: str | null`

Existing fields remain unchanged (`position`, `audio_url`, `audio_bid`, `duration_ms`, `av_contract`).

Ordering guarantee:

- First event touching a slide must be `new_slide`.
- Audio events for that slide come after `new_slide`.

### 5.3 `/records` Extension

Extend `LearnRecordDTO`:

```json
{
  "records": [...],
  "interaction": "",
  "slides": [
    {
      "slide_id": "uuid",
      "generated_block_bid": "block_bid",
      "slide_index": 0,
      "audio_position": 0,
      "visual_kind": "svg",
      "segment_type": "markdown",
      "segment_content": "<svg>...</svg>",
      "source_span": [0, 100],
      "is_placeholder": false
    }
  ]
}
```

Notes:

- `slide_id` in `/records` is generated per response (new UUID each request).
- `/records` `slide_id` is not expected to equal historical `/run` `slide_id`.

## 6. Backend Design

### 6.1 Shared Slide Builder

Create shared helper (no persistence), for both `/run` and `/records`:

- Input:
  - raw content
  - AV contract (`visual_boundaries`, `speakable_segments`)
  - generated_block_bid
- Output:
  - ordered `slides[]`
  - mapping `audio_position -> slide_id`

Implementation principle:

- For each speakable segment position:
  - find preceding visual boundary.
  - map to that visual slide.
  - if no visual exists, create `placeholder` slide.

For visual slide payload:

- `segment_content` from `source_span` slicing raw content.
- `segment_type` chosen for frontend renderer (`markdown` or `sandbox`).

### 6.2 `/run` Path Changes

Where:

- `RunScriptContextV2` + `AVStreamingTTSProcessor` integration path.

Changes:

1. Initialize a run-local `slide_registry`.
2. When a new `(block_bid, position)` mapping appears:
   - allocate UUID `slide_id`.
   - emit `new_slide`.
3. Enrich outbound `audio_segment`/`audio_complete` with mapped `slide_id`.
4. Keep existing fields for compatibility.

Required invariant:

- `new_slide` must be emitted before first audio event using that `slide_id`.

### 6.3 `/records` Path Changes

Where:

- `learn_funcs.py::get_learn_record`.

Changes:

1. For each content record, build slide units with the same helper.
2. Accumulate into top-level `slides[]` with global `slide_index`.
3. Keep existing `records` unchanged.

## 7. Frontend Design

### 7.1 Ingestion (`useChatLogicHook`)

Add handler for `type === "new_slide"`:

- Upsert slide into listen timeline state by `slide_id`.
- Preserve order by `slide_index`.

Audio ingestion changes:

- Prefer `slide_id` binding when present.
- Keep fallback to `(generated_block_bid, position)` for compatibility.

### 7.2 Renderer (`ListenModeRenderer`)

Shift source of truth from content re-segmentation to backend slides:

- Render Reveal sections directly from `slides[]`.
- Keep old path behind fallback flag until migration complete.

### 7.3 Sequence (`useListenAudioSequence`)

Use queue keyed by `slide_id`:

- current unit identity: `content:${slide_id}` (instead of inferred page mapping).
- page switch by slide index resolved from `slide_id`.

Interaction logic remains:

- interaction still blocks progression explicitly.

## 8. Compatibility Strategy

### 8.1 Backward

- Old clients:
  - ignore unknown `new_slide` events safely.
  - continue using existing `position` and content parsing path.
- New clients:
  - prefer `slide_id` path.
  - fallback to legacy mapping if `slide_id` missing.

### 8.2 Forward

Phase 1 no DB:

- `slide_id` scope is one response/run.
- state reset on refresh/reload is expected behavior.

Future (optional):

- If stable replay identity is required later, introduce persisted `learn_generated_slides`.

## 9. Risks and Mitigations

Risk 1: Stream order race (`audio_*` before `new_slide`)

- Mitigation:
  - backend enforce ordering.
  - frontend temporary buffer for unmatched audio events.

Risk 2: Contract mismatch in old records without full AV metadata

- Mitigation:
  - fallback builder policy:
    - if no boundary/contract, emit placeholder slide for position 0.

Risk 3: Dual-path complexity during migration

- Mitigation:
  - feature flag `LISTEN_SLIDE_ID_V1`.
  - keep old path read-only fallback.

## 10. Rollout Plan

1. Backend contract support (`new_slide`, `slide_id`, `/records.slides`), flag off by default.
2. Frontend ingest + render + sequence support under flag.
3. Enable in internal env, run regression matrix.
4. Enable for production gradually.
5. Remove old mapping path after one stable release window.

## 11. Acceptance Criteria

- `/run` emits `new_slide` and subsequent audio events reference `slide_id`.
- `/records` returns `slides[]` in same contract family.
- Frontend listen mode can render and play entirely from `slide_id` timeline.
- No regression to non-listen mode.
- No DB migration required for this phase.

## 12. Open Questions

1. Should `segment_content` be sanitized server-side or rendered with current client sanitization path?
2. Should `new_slide` also include chapter/outline metadata for analytics correlation?
3. Should `/records` include precomputed `units[]` (content + interaction queue) to simplify frontend even further?
