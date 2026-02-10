# Tasks: Listen Mode TTS Segmentation By Sandbox Boundaries

Date: 2026-02-10

## Discovery (Done)

- [x] Audit backend TTS preprocessing and audio persistence logic (`src/api/flaskr/service/tts/__init__.py`, `src/api/flaskr/service/tts/streaming_tts.py`, `src/api/flaskr/service/learn/context_v2.py`, `src/api/flaskr/service/learn/learn_funcs.py`)
- [x] Audit frontend listen mode slide segmentation and audio playback (`src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts`, `src/cook-web/src/components/audio/AudioPlayer.tsx`)
- [x] Write design doc: `docs/tts-audio-segmentation-by-visual.md`

## Decisions / Clarifications (Done)

- [x] Visual boundaries include all `sandbox` elements
- [x] `position` is 0-based and applies to speakable parts (no visual-only placeholders)
- [x] History API returns a list via a new field (keep `audio_url` for compatibility unless explicitly removed)

## Backend (Planned)

- [x] Add DB migration: add `position` column + indexes on `learn_generated_audios`
- [x] Update SQLAlchemy model `LearnGeneratedAudio` to include `position` (default 0) and expose it in `to_dict()`
- [x] Add a helper to split raw block content into speakable sections by sandbox boundaries
- [x] Apply “sandbox + following speech is one unit” when computing part boundaries/positions
- [x] Update `stream_generated_block_audio()` to synthesize/persist/stream multiple audios per block (one per `position`)
- [x] (Phase 2) Update `StreamingTTSProcessor` (run-SSE listen-mode streaming) to become part-aware:
  - [x] Split streaming content by sandbox boundaries into multiple audio parts (`position`)
  - [x] Mark last segment of each part as `is_final=true` so the frontend can advance without waiting for OSS upload
  - [x] Persist/upload one audio per `(generated_block_bid, position)` during `finalize()`
- [x] Extend audio DTOs / SSE payloads to include `position` (and close signal):
  - [x] `AudioSegmentDTO.position`
  - [x] `AudioCompleteDTO.position`
  - [x] `AudioCompleteDTO.is_last` (frontend closes SSE on last part)
- [x] Update history record aggregation (`get_learn_record`) to support multiple audios per block:
  - [x] Add a new field `audio_list` returning an ordered list with `(position, audio_url, duration_ms, audio_bid, ...)`
  - [x] Keep `audio_url` as a legacy single-value field (set to `audio_list[0]`)
- [x] Add backend tests: split helper (`src/api/tests/service/tts/test_sandbox_split.py`)
- [ ] Add backend tests: on-demand multi-part TTS endpoint (mock synth/upload)

## Frontend (Planned)

- [x] Extend TS contracts in `src/cook-web/src/c-api/studyV2.ts`:
  - [x] `AudioSegmentData.position?: number`
  - [x] `AudioCompleteData.position?: number`
  - [x] `AudioCompleteData.is_last?: boolean`
  - [x] `StudyRecordItem.audio_list?: GeneratedAudioPartData[]`
- [x] Update audio state to store multiple parts per block keyed by `position` (`src/cook-web/src/c-utils/audio-utils.ts`)
- [x] Update SSE handlers to upsert audio by `(generated_block_bid, position)` (on-demand TTS SSE)
- [x] In listen mode, handle run-SSE `audio_segment/audio_complete` with `position` (sandbox-aligned streaming)
- [x] In listen mode, re-enable run-SSE streaming TTS request payload (`listen=true`) so audio can start during generation
- [x] Fix `requestAudioForBlock()` listen-mode short-circuit: do not treat legacy `audioUrl` as “segmented ready”
- [x] Update listen mode sequencing (`src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts`) to:
  - [x] Build an audio sequence aligned to sandbox units (sandbox + following speech)
  - [x] Only advance to next sandbox after current unit audio ends
  - [x] If no sandbox exists, keep “just continue playing audio”
  - [x] For sandbox-aligned playback, use `audioParts[position]` and do not fall back to legacy merged `audioUrl`
- [x] Update listen mode renderer to play the active audio part (`src/cook-web/src/app/c/[[...id]]/Components/ChatUi/ListenModeRenderer.tsx`)
- [ ] Manual QA in listen mode:
  - [ ] `text -> sandbox -> text` follows “sandbox + following speech” unit behavior
  - [ ] Multiple sandboxes advance only when each unit audio ends

## Ops / Quality (Planned)

- [x] Run `pytest` for backend changes (`cd src/api && pytest`)
- [ ] Run frontend build (`cd src/cook-web && npm run build`)
  Blocked in this sandbox: DNS/network to `fonts.googleapis.com` fails; local `node_modules` is incomplete (e.g. missing `reveal.js`).
- [x] Run `pre-commit run -a`
