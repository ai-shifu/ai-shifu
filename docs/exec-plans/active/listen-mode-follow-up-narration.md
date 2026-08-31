# Listen-mode follow-up narration

## Purpose / Big Picture

Learners in listen mode can ask a follow-up without leaving the slide player. The
teacher's answer is synthesized sentence by sentence while its text is still
streaming and played through a
separate audio-and-subtitle layer that looks like lesson narration. The lesson
player remains paused at its original position for the whole follow-up session,
allows another question after each answer, and restores its prior play intent
only when the learner closes the follow-up panel. Course preview uses the same
experience without writing generated audio history.

## Progress

- [x] 2026-08-31 10:20 CST: Synced `origin/main` and created
      `sunner/listen-follow-up-narration` in the current worktree.
- [x] 2026-08-31 10:30 CST: Inspected the current ask store, run SSE, generated
      block TTS, Slide integration, mobile/fullscreen portals, analytics contract,
      and focused test suites.
- [x] 2026-08-31 12:05 CST: Added the follow-up answer lifecycle and formal versus
      preview narration transports.
- [x] 2026-08-31 12:50 CST: Added the isolated Slide narration layer and close,
      failure, and replay guards.
- [x] 2026-08-31 13:40 CST: Added localized failure copy, analytics contracts and
      producers, backend/frontend contract tests, and deterministic media-event
      integration coverage.
- [x] 2026-08-31 14:51 CST: Ran focused and repository-wide validation. Browser
      E2E remained environment-blocked because the Playwright Chromium binary
      and local authenticated runtime were unavailable; the attempted browser
      installation did not complete.
- [x] 2026-08-31 14:50 CST: Rebased the uncommitted implementation onto the new
      `origin/main` tip `4d3b602d6` after main advanced during validation.
- [x] 2026-08-31 16:20 CST: Diagnosed the live learner flow against the dev API.
      The answer TTS returned 14 audio segments, subtitle cues, and a final URL,
      but the isolated Slide was never explicitly asked to start its media.
      Added an explicit, speed-aware `play()` handoff plus a regression test.
- [x] 2026-08-31 16:56 CST: Reproduced the reported no-speech case with the
      one-character answer `2`. Verified that normal sentence answers mount an
      unmuted, full-volume narration layer and reach `playing`/`ended`, then
      removed the backend's two-character gate so Unicode letters and numbers
      of any non-zero length reach the existing TTS provider pipeline.
- [x] 2026-08-31 17:54 CST: Enabled the existing sentence-streaming TTS path for
      follow-up `/run` requests, returned follow-up audio as ephemeral SSE
      events, retained terminal generated-block/text TTS as a no-audio fallback,
      and changed narration completion to wait for every streamed segment rather
      than treating the first native `ended` event as the whole answer.

## Surprises & Discoveries

- The answer handler already had sentence-boundary streaming TTS support, but
  both the outer `/run` wrapper and `_should_stream_tts()` explicitly disabled
  it for asks, while the frontend hardcoded `listen=false`.
- `markdown-flow-ui@0.2.21` already accepts streaming audio segments, subtitle
  cues, hidden controls, and disabled keyboard shortcuts. It does not expose a
  dedicated playback-end callback, so the narration wrapper must listen to
  media events scoped to its own Slide.
- The existing ask store already carries generated-block and audio fields. The
  missing contract is the explicit narration status and capture of the answer
  block identity from the answer `ELEMENT` event.
- A real formal follow-up proved that text generation and TTS were both healthy:
  the browser requested generated-block TTS with `listen=false`, and the stream
  returned incremental audio and subtitles. The renderer test had only fired a
  synthetic `playing` event, so it did not catch that no consumer explicitly
  called `audio.play()` after mounting the isolated Slide.
- The remaining live no-speech reproduction was content-specific rather than a
  player failure: the answer `2` was rejected before provider synthesis by a
  legacy minimum-length check. `has_speakable_text` already treats Unicode
  letters and numbers as speakable, and the provider pipeline already preserves
  synthesis failures, so the length gate was both redundant and too strict for
  concise teacher answers.
- A native media `ended` event belongs to one streamed segment, not necessarily
  to the whole answer. `markdown-flow-ui` advances to the next segment itself;
  the wrapper must count completed segments and wait for the stream-final state
  before reporting answer completion.
- Generated-block identity is present at the SSE envelope level as well as on
  current answer elements. Capturing the envelope value makes the narration
  handoff resilient to element payload variations without changing `/run`.
- The repository Playwright command depends on both an installed Chromium
  binary and a running authenticated learner stack. This environment had
  neither: the command stopped before the feature scenario could run, and the
  follow-up browser installation attempt stalled without producing a usable
  binary. Deterministic media behavior is therefore covered at the renderer
  integration boundary, while full browser coverage remains an environment
  follow-up.

## Decision Log

- Decision: send `listen=true` only for narrated follow-up `/run` requests and
  feed answer content into the existing sentence-streaming processor. The
  adapter emits its audio segment/complete messages ephemerally, so follow-up
  audio does not join lesson marker, progress, or page-turn history.
- Decision: keep the existing formal generated-block and preview text TTS calls
  as a terminal fallback only when `/run` emitted no audio. Preview streaming
  uses preview metering and disables generated-audio persistence.
- Decision: render the latest active answer in a second, single-element Slide
  with hidden controls rather than inserting it into the lesson Slide's
  `elementList`. Streaming segment playback remains authoritative for the
  session; a final URL can complete metadata but must not restart played audio.
- Decision: explicitly start the isolated Slide's media once its audio element
  has a source, while keeping native `playing`, `ended`, and `error` events as
  the state authority. A rejected play promise follows the same text-preserving
  failure path as a media error.
- Decision: the ask panel's custom-action active state continues to own the
  lesson pause/resume contract. Narration completion never deactivates it.
- Decision: analytics count accepted formal learner listen-mode attempts and
  exactly one terminal result; preview, read, classroom, empty input, guarded
  duplicate actions, and unmount cleanup are excluded.

## Outcomes & Retrospective

The listen-mode follow-up now starts sentence synthesis during `/run` answer
generation, narrates only the latest answer in an isolated
single-element Slide, and keeps the lesson paused until explicit panel close.
Speech completion reopens the input for another question; cancellation or
failure preserves completed text, stops active streams and media, and never
advances lesson markers or progress. Formal and preview learning both receive
ephemeral streamed answer audio; generated-block/text TTS remains available as
a no-audio fallback, and preview never persists generated-audio history.

Live diagnosis additionally verified the formal endpoint against an actual
teacher answer block: it returned playable audio segments with subtitle cues
and a final audio URL. The isolated player now explicitly begins
that first source instead of relying on an implicit library autoplay side
effect. Two further live follow-ups reached `playing` and `ended` with
`muted=false` and `volume=1`. The content-specific failure for a one-character
numeric answer is covered by allowing any cleaned text containing a Unicode
letter or number through generated-block and preview TTS.

The exact analytics contract is implemented with allowlisted identifiers and
surface/outcome enums, one result per accepted attempt, formal-listen-only
eligibility, and fail-open delivery. All locales and generated i18n key types
include the speech-failure message. No route, DTO, database field, migration,
runtime package, or MarkdownFlow version changed.

Validation completed successfully for the focused backend contract suites (42
tests), focused frontend suites (71 tests), adjacent chat regressions (78
tests), TypeScript, ESLint, Ruff, repository harness, development-tool checks,
translation checks, architecture boundaries, and the full lefthook pre-commit
gate. An authenticated in-app browser run additionally proved two normal
follow-up answers reached unmuted, full-volume `playing` and `ended` events.
`npm run test:e2e` could not start its scenarios because this machine did not
have the required Playwright Chromium binary or local authenticated runtime;
the browser installation attempt did not complete. This is an environment-only
verification gap, not a passing E2E result. The one-character backend change is
covered locally by generated-block, preview, and processor tests; the connected
dev API still runs the pre-change backend until this branch is deployed.

## Context and Orientation

`AskBlock.tsx` owns follow-up `/run` streaming and writes messages into the
lesson-and-anchor scoped Zustand store defined by `askState.ts` and
`useAskStateStore.ts`. `ListenModeSlideRenderer.tsx` owns the lesson Slide,
custom-action pause behavior, desktop/mobile follow-up overlays, fullscreen
portals, and playback speed. `studyV2.ts` owns SSE transports. Shared audio
normalization and stable segment upserts live in `c-utils/audio-utils.ts`.
Canonical analytics rules live in
`docs/references/frontend-product-analytics.md`, while current Cook Web event
contracts are recorded in `docs/product-specs/web-umami-contract-remediation.md`.

The backend already exposes generated-block TTS and preview text TTS. This work
does not add a route, DTO, model field, database column, or migration. It locks
the existing answer-block contract with tests and removes the legacy
two-character admission gate so concise letter or numeric answers can reach the
same provider pipeline.

## Plan of Work

Extend each answer message with
`audioPlaybackStatus = pending | playing | completed | failed | cancelled`.
Capture both the rendered answer element ID and committed generated-block ID.
Lock the ask input after an accepted submission and release it only on speech
completion or failure. Expose narrowly scoped callbacks from `AskBlock` so the
listen renderer can start narration after committed text without changing read
mode.

Add a preview TTS transport beside generated-block TTS and feed both through
the existing audio segment, complete payload, subtitle cue, and stable upsert
helpers. Update only the anchor-scoped ask message that owns the active answer.
Cancel run and TTS sources explicitly when the panel closes.

For follow-up answers, bypass provider-native whole-element timestamp requests
and submit each completed sentence to the existing segment synthesizer. Drain
ready segments during LLM idle intervals so the first sentence can reach the
client before the answer stream ends. Keep the request-scoped MiniMax and
Volcengine behavior unchanged for normal lesson narration.

Build a follow-up narration overlay in `ListenModeSlideRenderer` from the latest
pending/playing answer. Render a single-element Slide outside the main lesson
element list, with hidden controls and keyboard shortcuts disabled. Scope
`playing`, `ended`, and `error` media events to that wrapper, apply the lesson
playback speed, and portal with the existing desktop/mobile fullscreen rules.
While it is active, hide the paused lesson subtitle layer. Completion changes
only the answer status and leaves the panel/custom action active.

Add typed, fail-open analytics helpers and producer tests for
`learner_listen_follow_up_attempt` and `learner_listen_follow_up_result`.
Document the metric, population, deduplication, exact allowlisted payload, and
privacy exclusions. Add the new failure toast to every locale and regenerate
the i18n key type through the repository's existing generator/check path.

## Concrete Steps

1. Update `askState.ts`, `AskBlock.tsx`, `studyV2.ts`, and focused tests for
   answer identity, busy state, formal/preview narration handoff, and
   cancellation.
2. Update `ListenModeSlideRenderer.tsx` and `ListenModeRenderer.scss` for the
   isolated narration Slide, media-event state transitions, pause retention,
   speed synchronization, and portals.
   Reuse the lesson audio loading dots above the slide while a follow-up answer
   is pending, including fullscreen portals, and remove them only when media
   actually enters the playing state.
3. Add a feature-owned analytics helper, wire it through the shared
   `useTracking` path, and document/test the event family.
4. Add localized failure copy and backend TTS contract coverage.
5. Add or extend deterministic Jest and Playwright coverage for two sequential
   questions, close/resume, preview, and speech failure where the current test
   harness can model the complete workflow.

## Validation and Acceptance

Acceptance is observable when a playing lesson pauses on opening follow-up,
the committed answer speaks with progressively updated subtitles, the input
reopens after media `ended`, a second question can be asked without resuming the
lesson, and closing the panel resumes once from the original time. A lesson
that was manually paused stays paused. Closing during text or speech cancels
the relevant sources; completed text remains when only speech is cancelled.
Speech failure keeps text, displays the localized failure message, reopens the
input, and leaves the lesson and panel paused. Preview behaves the same without
using generated-block persistence. Historical completed, failed, and cancelled
answers never auto-play on remount or reopen.

Run, in order: focused backend pytest; focused `studyV2`, `AskBlock`, renderer,
and analytics Jest suites; `npm run type-check`; `npm run lint`; focused and
then full `npm run test:e2e`; `python scripts/check_repo_harness.py`;
`python scripts/check_dev_tools.py`; and
`lefthook run pre-commit --all-files`. Record any environment-only limitation
instead of claiming an unrun check.

## Idempotence and Recovery

All store transitions identify one lesson, anchor, and answer block, and are
safe to ignore after that answer reaches a terminal narration status. Segment
upserts use the existing stable identity and final-promotion rules. Closing an
already closed SSE source, pausing already paused narration media, or attempting
to report a second terminal analytics result is a no-op. Unmount cleanup never
emits a cancellation result. If a test or edit fails, rerun the focused suite;
no migration or irreversible external state is involved.

## Interfaces and Dependencies

The implementation stays on `markdown-flow-ui@0.2.21`. It depends on the
existing `/run`, generated-block TTS, and preview text TTS SSE event shapes;
shared `normalizeAudioSegmentPayload`, `normalizeAudioCompletePayload`,
`upsertAudioSegment`, and `upsertAudioComplete` behavior; the scoped ask Zustand
store; Slide custom-action pause semantics; and the shared `useTracking`
transport. No new runtime package, route, schema, or provider is introduced.
