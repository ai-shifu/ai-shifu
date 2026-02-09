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
- [x] Extend DTOs: add optional `position` to `AudioSegmentDTO` + `AudioCompleteDTO`.
- [x] Extend DTOs: extend `GeneratedBlockDTO` to return `audios[]` (position + url + duration + bid).
- [x] Update `/records` assembly: `get_learn_record()` returns `audios[]` per `generated_block_bid` (sorted by `position`).
- [x] Update `/records` assembly: keep `audio_url` behavior backward-compatible as needed.
- [x] Update on-demand TTS endpoint:
- [x] Add query param `av_mode=true` (or new endpoint) to trigger segmented behavior.
- [x] When `av_mode=true`, synthesize and persist multiple audio rows with increasing `position`.
- [x] Ensure idempotency: if segmented audio already exists, return existing records instead of regenerating.
- [x] Add integration test for segmented on-demand TTS (DB rows + SSE payload includes `position`).

## Frontend (Cook Web)

- [x] Extend types: `StudyRecordItem` to accept `audios[]` in addition to legacy `audio_url`.
- [x] Extend types: `ChatContentItem` to store segmented audio metadata (e.g. `audios[]` and per-position streaming state).
- [x] Listen Mode: parse content boundaries consistently:
- [x] Use `splitContentSegments(content, true)` to compute text-segment ordering and map `position -> slide page`.
- [x] Listen Mode: update audio sequencing:
- [x] Iterate through `(generated_block_bid, position)` steps instead of one track per block.
- [x] Advance Reveal slides according to the mapped page for each audio segment.
- [ ] Update TTS request path in Listen Mode:
- [x] Request segmented audio with `av_mode=true`.
- [x] Group incoming SSE audio_segment/audio_complete by `position`.
- [x] Regression: ensure non-listen mode audio button still works (single audio_url path unchanged).

## QA / Ops

- [ ] Manual test scenario with one block containing multiple `<svg>` visuals and narration between them.
- [ ] Verify playback controls: play/pause/prev/next works across positions and blocks.
- [x] Run backend tests (`pytest`) and `pre-commit run -a` before any commit.
