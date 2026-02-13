# Listen Mode A/V Sync Design (Run Queue + Positioned Audio)

## 1. Background

Current listen mode receives mixed SSE events from `/api/learn/shifu/<shifu_bid>/run/<outline_bid>`:

- text/content streaming (`type=content`)
- interaction blocks (`type=interaction`)
- TTS streaming (`type=audio_segment`, `type=audio_complete`)

At the moment, one generated block is eventually persisted as one `learn_generated_audios` record, and frontend rendering is mostly "arrive-and-render". This makes strict audio/visual synchronization difficult when the model output contains visual modules (SVG/HTML/mermaid) between text sections.

## 2. Requirement Summary

1. Keep long-text internal TTS chunking behavior, but split audio by visual boundaries (for example text before SVG and text after SVG should be separate audio units).
2. In run-event handling, frontend must process by queue:
   - audio: play in order
   - visual module: render only after previous audio finishes
   - interaction block: wait for user submit before continuing to next visual/audio unit
3. Add `position` field to `learn_generated_audios` to identify the Nth audio unit in a generated block.
4. Keep changes small and maximize reuse.

## 3. Current Implementation Audit

## 3.1 Backend

- SSE run endpoint: `src/api/flaskr/service/learn/routes.py`
- Run orchestration: `src/api/flaskr/service/learn/runscript_v2.py`
- Main streaming logic: `src/api/flaskr/service/learn/context_v2.py`
  - content and interaction events are emitted directly while streaming
  - `StreamingTTSProcessor` is created per generated block when `listen=true`
- Streaming TTS processor: `src/api/flaskr/service/tts/streaming_tts.py`
  - emits `audio_segment` during streaming
  - concatenates all segments into one final audio
  - writes one `LearnGeneratedAudio` row (no position field)
  - emits one `audio_complete` at finalize
- TTS preprocessing: `src/api/flaskr/service/tts/__init__.py`
  - removes SVG/code/mermaid for speech safety
  - does not preserve visual-boundary semantics for final persisted audio units
- Audio table model: `src/api/flaskr/service/tts/models.py`
  - `learn_generated_audios` has no `position`
- Record API: `src/api/flaskr/service/learn/learn_funcs.py`
  - `get_learn_record` maps one `audio_url` per `generated_block_bid`

## 3.2 Frontend

- Run SSE client and shared types: `src/cook-web/src/c-api/studyV2.ts`
- Main chat/run state machine: `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx`
  - applies `content`/`interaction` events immediately to UI state
  - stores streaming audio on block-level (`audioSegments`, `audioUrl`)
  - no run-level queue that gates visual rendering by audio completion
- Listen mode renderer and sequence controller:
  - `ListenModeRenderer.tsx`
  - `useListenMode.ts`
  - `AudioPlayerList.tsx`, `AudioPlayer.tsx`
  - these modules sequence playback among already-materialized items, but do not delay run-time visual event commit.

## 4. Gap Analysis

- DB cannot identify multiple audio units per generated block (`position` missing).
- Backend final persistence model is block-level single audio, not visual-boundary-aligned units.
- Frontend run handler is not queue-driven for "audio first, visual after audio, interaction blocks queue until submit".
- Record replay contract is block-level `audio_url`, not ordered audio-unit list.

## 5. Design Goals

- Preserve existing endpoint shape and major flow (`run` SSE + existing components).
- Add minimal compatible data extensions instead of replacing architecture.
- Reuse existing TTS preprocessing, audio playback, and listen-mode sequencing modules.
- Keep non-listen mode behavior unchanged.

## 6. Proposed Solution

## 6.1 Backend: Positioned Audio Units

### 6.1.1 Schema

Add `position` to `learn_generated_audios`:

- type: `Integer`
- nullable: `False`
- default: `0`
- meaning: zero-based audio unit order within one `generated_block_bid`
- index: add composite index on `(generated_block_bid, position)`

Files:

- model: `src/api/flaskr/service/tts/models.py`
- migration: `src/api/migrations/versions/<new_revision>_add_position_to_learn_generated_audios.py`

### 6.1.2 SSE payload extension

Extend audio DTOs with optional `position`:

- `AudioSegmentDTO.position`
- `AudioCompleteDTO.position`

Files:

- `src/api/flaskr/service/learn/learn_dtos.py`

### 6.1.3 Streaming TTS changes

Keep one processor per generated block, but persist and emit multiple audio-complete units:

- add `current_position` state
- detect visual boundaries in raw streamed content (SVG/code/mermaid/html-sandbox boundaries)
- when crossing a boundary:
  - flush current speech buffer as one audio unit (same position)
  - persist one `LearnGeneratedAudio(position=current_position)`
  - emit `audio_complete(position=current_position)`
  - increment `current_position`
- keep existing long-text segmentation inside one position (no extra position split for max-char chunking)

Primary file:

- `src/api/flaskr/service/tts/streaming_tts.py`

### 6.1.4 Record API compatibility

Return ordered audio units for one content block while preserving old field:

- add optional `audio_tracks` array on `GeneratedBlockDTO` (sorted by `position`)
- keep legacy `audio_url` fallback for compatibility

Primary file:

- `src/api/flaskr/service/learn/learn_funcs.py`

## 6.2 Frontend: Run Event Queue (Listen Mode)

Apply queue gating only when listen mode is active (`isListenMode=true`):

- enqueue `audio_segment`/`audio_complete` with `(generated_block_bid, position)`
- enqueue visual commit units (derived from content stream; commit only complete render segments)
- enqueue interaction blocks

Queue rules:

1. Audio events are consumed in order (block order, then `position`).
2. Visual units can commit only when no prior audio is pending/playing.
3. Interaction unit can commit only when no prior audio is pending/playing.
4. After interaction commit, queue pauses until user submits.

Implementation anchor:

- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx`

Reuse modules:

- `splitContentSegments` (already used in listen mode) for stable visual unit boundaries
- existing audio playback components (`AudioPlayerList`, `AudioPlayer`) for sequential playback callbacks

## 6.3 Out of Scope

- No endpoint replacement.
- No broad refactor of preview playground flow.
- No redesign of markdown renderer internals.

## 7. Rollout Plan

1. Add backend schema + DTO backward-compatible fields.
2. Backend emits positioned audio units while preserving existing run message types.
3. Frontend listen-mode queue gating behind a feature flag if needed.
4. Enable by default after verification.

## 8. Risks and Mitigations

- Risk: queue deadlock when audio fails.
  - Mitigation: add fail-fast fallback (mark audio failed, continue queue).
- Risk: audio order race due async synthesis completion.
  - Mitigation: strict order by `position`; hold future positions until previous position resolved.
- Risk: replay incompatibility with old `audio_url` consumers.
  - Mitigation: keep `audio_url` fallback and add `audio_tracks` as additive field.

## 9. Test Plan

## 9.1 Backend

- unit: visual-boundary split yields multiple positioned audio records
- unit: `position` persists and increments correctly
- unit: `audio_complete.position` emitted in order
- unit: `get_learn_record` returns `audio_tracks` ordered by `position`

## 9.2 Frontend

- unit/integration: queue blocks visual commit until prior audio ends
- unit/integration: interaction commit pauses queue until submit
- regression: non-listen mode still renders immediately

## 9.3 Manual

- content only
- content + SVG + content
- content + interaction + content
- regenerate/reload path in listen mode
