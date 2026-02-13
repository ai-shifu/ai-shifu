# Listen Mode A/V Sync Tasks

- [x] Audit backend run/TTS flow and identify current block-level audio persistence constraints.
- [x] Audit frontend run/listen flow and identify missing run-level queue gating.
- [x] Write design document: `docs/listen-mode-av-sync-design.md`.

- [x] Add DB migration to append `position` to `learn_generated_audios` with index `(generated_block_bid, position)`.
- [x] Update `LearnGeneratedAudio` model to include `position`.
- [ ] Extend audio DTOs (`AudioSegmentDTO`, `AudioCompleteDTO`) with optional `position`.
- [ ] Refactor `StreamingTTSProcessor` to flush/persist multiple audio units by visual boundaries and emit positioned audio events.
- [ ] Update `get_learn_record`/DTOs to expose ordered audio tracks while keeping `audio_url` fallback compatibility.

- [ ] Add listen-mode run event queue in `useChatLogicHook` for audio-first gating.
- [ ] Queue visual commits to run only after prior audio completion.
- [ ] Queue interaction commits to pause progression until user submit.
- [ ] Integrate positioned audio playback ordering in listen mode using existing audio player modules.
- [ ] Keep non-listen mode behavior unchanged (no queue gating).

- [ ] Add backend tests for positioned audio persistence and ordered SSE emission.
- [ ] Add frontend tests for queue gating and interaction pause/resume behavior.
- [ ] Execute regression checks for run/reload/history/listen-mode paths.
- [ ] Run `pre-commit run` and fix all hook issues.
