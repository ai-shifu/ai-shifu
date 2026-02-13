# Listen Mode Segmented TTS (AV Sync) - Task List

## 2026-02-11 Listen Mode Display & Playback Alignment (New)

### 0. Requirement Baseline (Source of Truth)

- [x] Freeze baseline requirement in docs:
- [x] Rule A: each visual element (`table/svg/img/html/div/iframe/video/markdown table`) + the following narration text is one slide unit.
- [x] Rule B: slide switch happens only after the narration audio for that slide is finished.
- [x] Rule C: behavior must be identical for single-block and cross-block content.
- [x] Rule D: interaction popup opens on current slide and must not re-show title.
- [x] Add requirement examples (single block, cross block, no narration after visual, multi interactions).
- [x] Link requirement section from `docs/listen-mode-segmented-tts.md`.

### 1. Single Segmentation Contract (Backend as Authority)

- [x] Define one shared AV boundary contract (JSON schema):
- [x] `visual_boundaries[]` with `kind`, `position`, `block_bid`, `source_span`.
- [x] `speakable_segments[]` with `position`, `text`, `after_visual_kind`, `block_bid`.
- [x] Ensure image boundaries are included (`<img>` and markdown image).
- [x] Ensure sandbox boundaries are included (`div/section/article/main/template/...`) and never speak sandbox text.
- [x] Expose this contract in run/on-demand TTS payload (SSE metadata + records DTO where needed).
- [x] Add migration/compat handling so old clients still work when metadata is absent.

### 2. Frontend Timeline Refactor (Cross-Block Slide Unit)

- [x] Replace per-item page mapping with a global timeline builder across all content items.
- [ ] Build `SlideUnit` model:
- [ ] `slide_id`, `visual_ref`, `audio_ref(position)`, `source_block_bid`, `next_block_continuation`.
- [ ] Support cross-block pairing:
- [x] If a block ends with visual and next block begins with narration, bind that narration to previous visual slide.
- [x] Remove title placeholder slide for narration-only fallback in listen mode.
- [x] Keep reveal sections contiguous per logical slide unit, not strictly per `generated_block_bid`.
- [x] Keep backward path for non-listen mode unchanged.

### 3. Audio Position -> Slide Mapping Consistency

- [x] Stop local heuristic that skips image-only markdown as audio boundary.
- [x] Drive mapping from backend `position` contract (no independent front-end re-segmentation for mapping).
- [ ] Validate mapping for:
- [ ] SVG boundary
- [ ] HTML table boundary
- [ ] Markdown table boundary
- [ ] HTML image and markdown image boundary
- [ ] Sandbox HTML boundary
- [ ] iframe/video boundary with fixed markers
- [x] Add guard logs for mismatch (`position exists but no slide`, `slide exists but no position`).

### 4. Interaction Popup Behavior Fix

- [x] Change interaction anchor from `fallbackPage` heuristic to active timeline slide.
- [ ] Ensure popup always overlays current slide visual container.
- [x] Disable title rendering while interaction popup is visible.
- [x] Remove auto-advance after fixed timeout when interaction is pending.
- [ ] Add explicit continuation policy:
- [x] Continue only after submit/skip action, or
- [x] Continue by config flag `LISTEN_INTERACTION_AUTOCONTINUE_MS` (default off).
- [x] Handle multi-interaction on same page with queue/list instead of map overwrite.

### 5. Reveal Navigation and End-of-Audio Progression

- [x] Remove auto-carousel of trailing visuals without narration (`1200ms` loop).
- [ ] Enforce progression rule:
- [x] Same slide unit: stay until its narration completes.
- [x] Next slide unit: advance only after completion event.
- [ ] If slide has no narration:
- [x] define deterministic policy (`manual-next` by default, optional timed auto-next).
- [x] Update prev/next controls to navigate timeline units, not raw reveal pages.

### 6. Rendering & Title Layer Cleanup

- [ ] Refactor `ContentIframe` text segment rendering:
- [x] No section-title-only pseudo slide in listen mode content timeline.
- [x] Dedicated title slide only for explicit empty-state (no content at all).
- [x] Confirm interaction popup never reveals empty-state title behind overlay.
- [ ] Keep mobile and desktop behavior consistent.

### 7. Test Plan (Must Add)

- [x] Frontend unit tests for timeline builder:
- [x] Single block: visual -> text -> visual -> text.
- [x] Cross block: block A visual, block B text.
- [x] Cross block: block A text end, block B visual start.
- [x] Image-only visual boundaries.
- [x] Multiple interactions on one slide.
- [ ] Frontend integration tests (React + mocked SSE):
- [ ] Position/page sync with streaming append.
- [ ] Interaction popup blocks progression until resolved.
- [ ] No title re-show on interaction popup.
- [x] Backend tests:
- [x] Extend AV segmentation cases to assert emitted metadata contract.
- [x] Verify `position` continuity with mixed boundaries and fixed markers.
- [ ] E2E manual checklist:
- [ ] one-block multi-visual
- [ ] multi-block cross-pairing
- [ ] interaction on current slide
- [ ] replay from history records (`audios[]`)

### 8. Rollout & Safety

- [ ] Add feature flag `LISTEN_TIMELINE_V2` for staged rollout.
- [ ] Add telemetry:
- [ ] mapping mismatch counter
- [ ] interaction auto-advance counter
- [ ] user manual-next frequency
- [x] Run `pytest` for related backend suites.
- [ ] Run `npm run lint` + `npm run type-check` for cook-web.
- [ ] Run `pre-commit run -a` before commit.
- [ ] Prepare rollback notes: disable `LISTEN_TIMELINE_V2` to return old behavior.

### 9. Implementation Order

- [x] Step 1: Contract + backend metadata
- [x] Step 2: Frontend timeline builder + mapping switch
- [x] Step 3: Interaction behavior fix (no title re-show, no forced timeout)
- [x] Step 4: Navigation/progression polish
- [ ] Step 5: Tests + feature flag rollout

### 10. Acceptance Criteria

- [ ] For all supported visual kinds, each visual + following narration is one slide unit.
- [ ] Cross-block and single-block cases produce the same progression behavior.
- [ ] Slide advances only after corresponding narration audio ends.
- [ ] Interaction popup stays on current slide and title is never re-shown during popup.
- [ ] No frontend/backend `position` mapping mismatches in test fixtures.
- [ ] Existing non-listen mode behavior remains unchanged.

## Discovery / Design

- [x] Audit current backend TTS generation + persistence paths (run streaming + on-demand).
- [x] Audit current frontend Listen Mode segmentation + audio playback orchestration.
- [x] Write design doc: `docs/listen-mode-segmented-tts.md`.

## Backend

- [x] Add `position` column to `learn_generated_audios` (new Alembic migration).
- [x] Update `LearnGeneratedAudio` model to include `position` and (optionally) index metadata.
- [x] Implement backend AV segmentation helper `split_av_speakable_segments(raw: str) -> list[str]`.
- [x] Add unit tests for segmentation helper (SVG, img, markdown images, mermaid/code fences, sandbox HTML).
- [x] Fix: prevent stray SVG text fragments (e.g. `<text>...</text>`) from being synthesized.
- [x] Treat `<video>...</video>` and `<table>...</table>` as AV boundaries (do not speak; split positions).
- [x] Treat `<iframe>...</iframe>` (Admin video embeds, e.g. Bilibili) as AV boundaries; handle MarkdownFlow fixed markers (`=== ... ===`) without swallowing later visuals.
- [x] Treat Markdown tables as AV boundaries (do not speak; split positions).
- [x] Extend DTOs: add optional `position` to `AudioSegmentDTO` + `AudioCompleteDTO`.
- [x] Extend DTOs: extend `GeneratedBlockDTO` to return `audios[]` (position + url + duration + bid).
- [x] Update `/records` assembly: `get_learn_record()` returns `audios[]` per `generated_block_bid` (sorted by `position`).
- [x] Update `/records` assembly: keep `audio_url` behavior backward-compatible as needed.
- [x] Update on-demand TTS endpoint (manual/backfill only):
- [x] Keep query param `listen=true` to trigger segmented behavior.
- [x] When `listen=true`, synthesize and persist multiple audio rows with increasing `position`.
- [x] Ensure idempotency: if segmented audio already exists, return existing records instead of regenerating.
- [x] Add integration test for segmented on-demand TTS (DB rows + SSE payload includes `position`).
- [x] Update run SSE streaming TTS (Listen Mode):
- [x] Segment streaming TTS by AV boundaries and emit `position` in SSE audio payloads.
- [x] Persist one `LearnGeneratedAudio` row per `(generated_block_bid, position)`.
- [x] Guard against AV boundary markers split across stream chunks (do not speak sandbox/visual HTML).
- [x] Fix: treat sandbox blocks closed at EOF as complete in streaming segmentation (avoid dropping content).
- [x] Change: do not narrate any sandbox HTML blocks (remove textual-sandbox narration fallback).

## Frontend (Cook Web)

- [x] Extend types: `StudyRecordItem` to accept `audios[]` in addition to legacy `audio_url`.
- [x] Extend types: `ChatContentItem` to store segmented audio metadata (e.g. `audios[]` and per-position streaming state).
- [x] Listen Mode: parse content boundaries consistently:
- [x] Use `splitContentSegments(content, true)` to compute text-segment ordering and map `position -> slide page`.
- [x] Treat `<video>...</video>` and `<table>...</table>` as visual slides in Listen Mode.
- [x] Treat `<iframe>...</iframe>` (Admin “Insert Video”, e.g. Bilibili) as a visual slide in Listen Mode, including fixed-marker wrappers (`=== ... ===`).
- [x] Listen Mode: update audio sequencing:
- [x] Iterate through `(generated_block_bid, position)` steps instead of one track per block.
- [x] Advance Reveal slides according to the mapped page for each audio segment.
- [x] Update TTS request path in Listen Mode:
- [x] Stop auto-calling on-demand segmented TTS (`/generated-blocks/<bid>/tts?listen=true`); RUN SSE is source of truth.
- [x] Group incoming run SSE `audio_segment/audio_complete` by `position` (store in `audioTracksByPosition`).
- [x] Fix: map single-position audio to `pagesForAudio[0]` when available (sync to correct slide).
- [x] Fix: align `position -> page` mapping with backend (sandbox HTML is never narrated).
- [x] Fix: stabilize streaming SVG rendering to avoid blank flicker during generation.
- [x] Fix: ensure SVG slides never render blank (fallback to raw SVG until a stable parse is ready).
- [x] Fix: allow listen-mode autoplay to retry from final audio URL after streaming completes.
- [x] Fix: prevent Reveal auto-follow from fighting segmented audio playback (hold when audioTracksByPosition is active).
- [x] Regression: ensure non-listen mode audio button still works (single audio_url path unchanged).

## QA / Ops

- [ ] Manual test scenario with one block containing multiple `<svg>` visuals and narration between them.
- [ ] Verify playback controls: play/pause/prev/next works across positions and blocks.
- [x] Run backend tests (`pytest`) and `pre-commit run -a` before any commit.

## 2026-02-13 Listen Mode Event-Driven Orchestrator Refactor

### 0. Discovery and Design

- [x] Re-audit current listen-mode progression paths in:
- [x] `useListenMode.ts` (`playAudioSequenceFromIndex`, `handleAudioEnded`, `useListenPpt` auto-follow)
- [x] `useChatLogicHook.tsx` (`run`/`records` audio event ingestion)
- [x] `AudioPlayer.tsx` callback semantics (`onPlayStateChange`, `onEnded`, `onError`)
- [x] Write event-driven design doc: `docs/listen-mode-event-driven-orchestrator-design.md`.
- [x] Capture current gap summary for the reported cases:
- [x] audio not finished but slide switches ahead
- [x] image -> html switch happened but expected audio not played in order

### 1. Event Model and State Machine

- [x] Define `OrchestratorEvent` types and payload schema in frontend.
- [x] Define `UnitId` convention: `<generated_block_bid>:<position>`.
- [x] Define state model (`idle`, `waiting_audio`, `playing`, `interaction_blocked`, `paused`) and single event dispatcher.
- [ ] Add transition table tests for all core events.

### 2. Unified Queue for `/records` + `/run`

- [x] Implement records audio adapter: normalize history `audio_url/audios[]` into position-aware payload and per-position tracks.
- [x] Implement run audio adapter: normalize SSE `audio_segment/audio_complete` into one inbound event model.
- [x] Ensure idempotent merge by `UnitId` (late audio updates patch existing unit, no duplicate queue slot).
- [x] Remove direct sequence mutation from list-length side effects.

### 3. Visual Rendering Commands

- [x] Add orchestrator command channel for `SHOW_PAGE`.
- [ ] Ensure visuals can start rendering when visual stream starts (no full-block wait).
- [x] Keep Reveal sync/layout as rendering infrastructure only, not progression authority.
- [x] Remove/disable auto-follow progression logic that bypasses orchestrator.

### 4. Audio Playback Commands

- [x] Add orchestrator command channel for `PLAY_UNIT`.
- [x] Trigger next unit only from `PLAYER_ENDED`.
- [x] Ensure `PLAYER_ERROR` pauses current unit and never auto-advances.
- [x] Remove forced timeout auto-advance behavior from watchdog paths.

### 5. Interaction Gating

- [x] Gate progression with explicit interaction events (`INTERACTION_OPENED`/`INTERACTION_RESOLVED`).
- [x] Ensure interaction overlay binds to current active unit page.
- [x] Keep optional auto-continue flag behavior behind explicit configuration and orchestrator events.

### 6. Compatibility and Rollout

- [ ] Add feature flag `LISTEN_EVENT_ORCHESTRATOR_V1` for staged rollout.
- [ ] Keep legacy path as fallback for one release cycle.
- [ ] Add transition logs/metrics:
- [ ] unit mismatch counter
- [ ] audio stalled/error counter
- [ ] manual-next frequency
- [ ] Define rollback procedure (flag off -> legacy logic).

### 7. Verification

- [ ] Frontend unit tests for reducer and adapters.
- [x] Frontend unit tests for adapter helpers (`listen-orchestrator-adapters.test.ts`).
- [x] Frontend regression test for list index shift continuity (`listen-mode-audio-sequence.test.tsx`).
- [x] Frontend regression test for `image -> html -> delayed audio` wait/resume sequencing.
- [x] Frontend regression test for interaction gating (no auto-advance until explicit resolve).
- [ ] Frontend integration tests for:
- [ ] interaction -> image -> html -> delayed audio
- [ ] multi-position audio sequence ordering
- [ ] audio error (no auto-advance)
- [ ] Run `npm run lint` and `npm run type-check` in `src/cook-web`.
- [x] Run targeted listen-mode test suites.
- [ ] Run `pre-commit run -a` before commit.

## 2026-02-13 Listen Mode Slide-ID + `new_slide` Contract (No DB Table)

### 0. Design and Alignment

- [x] Write design doc: `docs/listen-mode-slide-id-newslide-design.md`.
- [ ] Team review for event contract fields (`new_slide`, `slide_id` on audio events, `/records.slides`).
- [ ] Decide feature flag name and default (`LISTEN_SLIDE_ID_V1` suggested).

### 1. Backend Contract Types

- [x] Add `GeneratedType.NEW_SLIDE = "new_slide"` in learn DTO enum.
- [x] Add `NewSlideDTO` schema in `learn_dtos.py`.
- [x] Extend `AudioSegmentDTO` with optional `slide_id`.
- [x] Extend `AudioCompleteDTO` with optional `slide_id`.
- [x] Extend `LearnRecordDTO` with optional `slides: list[NewSlideDTO]`.
- [ ] Keep all existing fields backward-compatible (no removal in this phase).

### 2. Shared Slide Builder (In-Memory)

- [x] Implement shared helper to build listen slides from:
- [x] raw generated content
- [x] AV contract (`visual_boundaries`, `speakable_segments`)
- [x] generated block bid
- [x] Generate `slide_id` with UUID dynamically (response/run scoped only).
- [x] Build mapping `audio_position -> slide_id`.
- [x] Support placeholder slide for pre-visual narration / text-only content.
- [x] Reuse this helper in both `/run` and `/records` paths.

### 3. `/run` SSE Path

- [x] Add run-local slide registry for current stream.
- [x] Emit `new_slide` before first audio event for each slide.
- [x] Enrich `audio_segment` with `slide_id`.
- [x] Enrich `audio_complete` with `slide_id`.
- [x] Add ordering guard to prevent audio before corresponding `new_slide`.
- [ ] Preserve legacy behavior when flag is off.

### 4. `/records` Path

- [x] In `get_learn_record`, generate `slides[]` with same shape as `new_slide`.
- [x] Ensure global `slide_index` ordering is deterministic in one response.
- [x] Keep `records[]` existing semantics unchanged.
- [x] Return `slides[]` only when listen-mode feature is enabled (or always if agreed).

### 5. Frontend Ingestion (`useChatLogicHook`)

- [x] Handle SSE `type === "new_slide"` and upsert by `slide_id`.
- [x] Extend local listen timeline state to store ordered slides.
- [x] Update audio event ingestion:
- [x] Prefer `slide_id` binding when provided.
- [x] Fallback to `(generated_block_bid, position)` when missing.
- [x] On refresh (`/records`), hydrate listen slides from `slides[]`.

### 6. Frontend Renderer and Sequencer

- [x] `ListenModeRenderer` render slides from backend-provided `slides[]` (flag path).
- [x] Reduce/remove frontend visual re-segmentation dependency in flag path.
- [x] `useListenAudioSequence` use `slide_id` as primary content unit identity.
- [x] Keep interaction gating behavior unchanged.
- [x] Keep legacy path available as fallback when no `slide_id`.

### 7. Testing

- [x] Backend unit tests for `NewSlideDTO` serialization and compatibility.
- [x] Backend integration test: `/run` emits `new_slide` before `audio_*` for each slide.
- [x] Backend integration test: `/records` returns `slides[]` and valid `slide_id` references.
- [x] Frontend unit test: `new_slide` ingestion + dedup/update by `slide_id`.
- [x] Frontend unit test: audio binding by `slide_id` with legacy fallback.
- [x] Frontend integration test: no frontend segmentation needed in flag path.

### 8. Rollout and Cleanup

- [ ] Add metrics:
- [ ] count missing `slide_id` audio events
- [ ] count unmatched audio->slide bindings
- [ ] count fallback-to-legacy mapping usage
- [ ] Enable flag in internal env and run manual matrix.
- [x] Run `pytest` related suites in `src/api`.
- [ ] Run `npm run lint` + `npm run type-check` in `src/cook-web`.
- [x] Run `pre-commit run -a`.
- [ ] After stabilization, plan legacy listen-mapping code removal.
