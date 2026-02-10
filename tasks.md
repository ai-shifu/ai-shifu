# Listen Mode Segmented TTS (AV Sync) - Task List

## Discovery / Design

- [x] Audit current backend TTS generation + persistence paths (run streaming + on-demand).
- [x] Audit current frontend Listen Mode segmentation + audio playback orchestration.
- [x] Write design doc: `docs/listen-mode-segmented-tts.md`.

## Backend

- [x] Add `position` column to `learn_generated_audios` (new Alembic migration).
- [x] Update `LearnGeneratedAudio` model to include `position` and (optionally) index metadata.
- [x] Implement backend AV segmentation helper `split_av_speakable_segments(raw: str) -> list[str]`.
- [x] Add unit tests for segmentation helper (SVG, img, markdown images, mermaid/code fences, sandbox HTML).
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
- [x] Fix: inject narration from textual sandbox HTML blocks (`<p>/<li>/<h*>`) to avoid missing audio after visuals.

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
- [x] Fix: align `position -> page` mapping with backend when narration comes from textual sandbox HTML blocks.
- [x] Fix: stabilize streaming SVG rendering to avoid blank flicker during generation.
- [x] Regression: ensure non-listen mode audio button still works (single audio_url path unchanged).

## QA / Ops

- [ ] Manual test scenario with one block containing multiple `<svg>` visuals and narration between them.
- [ ] Verify playback controls: play/pause/prev/next works across positions and blocks.
- [x] Run backend tests (`pytest`) and `pre-commit run -a` before any commit.
