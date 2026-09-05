# Learner listen playback stability

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
- [ ] Run repository verification, commit, push, and open the replacement PRs.
- [ ] Publish an approved release of `markdown-flow-ui`, then update the
  application dependency pin before either branch merges into `main`.

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

## Context and Orientation

`src/web/src/app/c/[[...id]]/Components/ChatUi/ListenModeSlideRenderer.tsx`
maps learner content into `markdown-flow-ui`'s `Slide`. The application stores
one best-effort browser-local checkpoint per course and lesson in
`listenPlaybackCheckpoint.ts`. The library resolves `audioKey` to its audio
list, navigates to the owning step, seeks inside segmented or URL playback,
and resumes its normal audio lifecycle.

## Product Contract

1. There is no lesson-wide timeline and no arbitrary cross-item seek UI.
2. Checkpoints are emitted at pause, logical-item completion, low-frequency
   progress, and unmount. They never clear merely because one segment ends.
3. A checkpoint is keyed by the logical audio item and course/lesson scope.
4. Returning to listen mode or reloading restores the matching audio item and
   attempts normal playback. A browser may still reject unmuted autoplay after
   a full reload, in which case the restored position remains ready to play.
5. No player, subtitle, or interaction layout code is changed by this work.

### `learner_listen_resume_requested`

- Business question: What share of eligible listen sessions has a saved audio
  checkpoint to resume?
- Metric definition: Count resume-request events by course over a reporting
  window; compare with existing learner listen-session reporting as the
  denominator. This measures a resumable checkpoint, not autoplay success.
- Actor and surface: Learners on `learner_listen`; guests and members are
  included, preview mode is excluded.
- Trigger: After a valid checkpoint is read for the current course and lesson
  and before it is supplied to `Slide`.
- Count unit and deduplication: One event per course/lesson renderer scope;
  repeated renders and effects for that scope do not emit another event.
- Consumers: Learner playback adoption reporting owned by the learning team.
- Compatibility: New additive event; no backfill.
- Verification: Renderer tests cover the trigger and allowlisted payload;
  tracking uses `useTracking` and failures are ignored.

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `shifu_bid` | string | course machine ID | high | pseudonymous | course-level grouping |
| `surface` | string | `learner_listen` | 1 | non-personal | fixed product surface |

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
  state or analytics event is introduced.
- Release ordering: merge and publish the UI library first, then replace the
  application's temporary type augmentation with the released package types
  and exact release pin.
