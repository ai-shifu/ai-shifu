# Learner listen playback stability

> Lifecycle review, 2026-09-26: Completed original scope. Checkpoint stability has recorded multi-stream and mode-round-trip acceptance. Timeline delivery is tracked separately; durable behavior and analytics moved to a product specification. Merge evidence: [#2775](https://github.com/ai-shifu/ai-shifu/pull/2775) (`c0ff2eb08`)

## Purpose / Big Picture

Restore learner listen mode from the correct logical audio item and offset after
a reload or a reading/listening mode round trip. A lesson can contain multiple
generated audio streams separated by fixed content; the saved position must
refer to the stream that was actually playing, never the first stream.

## Progress

- [x] Created clean branches from `origin/main` for `ai-shifu` and
      `markdown-flow-ui`, excluding the earlier experimental timeline, seek, and
      layout work.
- [x] Added a UI-library checkpoint/restore contract based on stable logical
      audio keys rather than temporary audio URLs or custom-action references.
- [x] Added application-local persistence scoped by course and lesson, using
      the versioned `course_listen_playback_checkpoint:v1` schema.
- [x] Prevented either default-audio initialization path from selecting the
      first audio item while a restore request is pending.
- [x] Locally verified the supplied multi-stream lesson, including refresh and
      mode round trips, with the learner test environment.
- [x] Published `markdown-flow-ui` 0.2.25, updated the application release pin,
      and merged the library and application changes.
- [x] Reproduced and fixed a production mode-round-trip race where historical
      text returned before its audio backfill and the application discarded the
      still-valid checkpoint.
- [x] Limited restore waiting to audio items whose backfill remains eligible;
      terminal failures and ineligible items now release the player and clear
      the unusable checkpoint.
- [x] Published the production mode-round-trip fix through PR #2775 and synced
      it into the generated-slide timeline branch before further development.
- [x] 2026-09-26: Separated timeline delivery into `docs/exec-plans/completed/generated-slide-timeline.md`; verified merged #2778 and its successful CI.

## Decision Log

- Decision: Persist `{ audioKey, timeMs }`, not a temporary URL, current slide
  index, or a lesson-wide timeline position.
  - Why: A stable audio key survives streaming segment changes and fixed output
    between generated streams.
- Decision: Restore the selected logical item through `Slide`, then let normal
  player playback resume it.
  - Why: The UI library owns its segment and URL playback state; application
    code must not guess which media element represents an audio item.
- Decision: Gate the application player until checkpoint lookup for its current
  course/lesson scope finishes.
  - Why: It prevents normal startup from playing the first item before a saved
    later-item restore request reaches the library.
- Decision: Keep this change limited to playback identity and lifecycle.
  - Why: Timeline UI, arbitrary seek, subtitle positioning, interaction-card
    positioning, and playback-source ordering were unrelated experimental
    changes and remain excluded.
- Decision: Treat a restored element without playable audio as pending audio
  backfill, not as a stale checkpoint.
  - Why: Returning from reading mode can restore persisted text before its
    narration is reattached. The element identity remains valid during that
    interval, and allowing normal startup would both erase the checkpoint and
    play the first sentence.
- Decision: Ignore a near-zero checkpoint for the same logical audio key when
  a valid later position is already stored.
  - Why: Player teardown resets its media time before the unmount checkpoint is
    delivered. A same-key zero is lifecycle noise, while a different-key zero
    still means regenerated playback replaced the previously stored audio.
- Decision: Derive restore waiting from the application backfill lifecycle,
  including its terminal failure set, instead of from element presence alone.
  - Why: Persisted text can legitimately wait for narration, but failed or
    ineligible narration must not leave the player permanently disabled.

## Context and Orientation

`src/web/src/app/c/[[...id]]/Components/ChatUi/ListenModeSlideRenderer.tsx`
maps learner content into `markdown-flow-ui`'s `Slide`. The application stores
one best-effort browser-local checkpoint per course and lesson in
`listenPlaybackCheckpoint.ts`. The library resolves `audioKey` to its audio
list, navigates to the owning step, seeks inside segmented or URL playback,
and resumes its normal audio lifecycle.

## Product Contract

The current playback and analytics contract lives in
`docs/product-specs/learner-listen-playback.md`.

## Validation and Acceptance

- A checkpoint in a second generated stream resumes that stream, including
  when fixed images or interactions appear between streams.
- Returning from reading mode does not briefly start the first audio item or
  overwrite the later stream checkpoint.
- Refreshing restores the matching logical item and position; browser autoplay
  policy is the only allowed reason it may remain paused.
- Unit coverage verifies storage semantics and application startup gating.
- Before merge, the UI library and application pass their focused checks and
  the application pins an approved release package, never a dev build.

## Interfaces and Dependencies

- UI public contract: `SlideProps.onPlaybackCheckpoint` and
  `SlideProps.playbackRestoreRequest` in `markdown-flow-ui`.
- Application persistence: browser `localStorage`, best-effort only; no server
  state is introduced.
- Release ordering: merge and publish the UI library first, then replace the
  application's temporary type augmentation with the released package types
  and exact release pin.

## Follow-up Optimization: Visual Page Finder

Deferred proposal tracked in `docs/exec-plans/tech-debt-tracker.md`; it does not block checkpoint or timeline acceptance.


## Surprises & Discoveries

History can return text before narration; treating missing audio as an invalid checkpoint caused a return to the first stream.

## Outcomes & Retrospective

Checkpoint restoration shipped and the plan records multi-stream/local mode-round-trip acceptance. PR #2775 closes the production backfill race; timeline acceptance is recorded separately.

## Plan of Work

Persist logical audio identity and offset, gate initial player selection, and release restore waiting only when backfill becomes terminal or ineligible.

## Concrete Steps

Use `listenPlaybackCheckpoint.test.ts` and adjacent renderer tests to verify stable logical keys, near-zero teardown noise and backfill waiting. Replay a second-stream checkpoint across a mode round trip.

## Idempotence and Recovery

Storage is best-effort and scoped to course/lesson. Ignore malformed or unusable checkpoints; preserve a valid later offset when teardown emits a near-zero offset for the same key.
