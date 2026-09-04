# Learner listen resume

## Purpose / Big Picture

Learners can leave and return to a listening lesson in the same browser without
losing their position. Restoring a position returns to the correct audio item
and never starts audio automatically. Listen mode deliberately has no
lesson-wide progress bar or cross-item seek control.

## Progress

- [x] 2026-09-04 10:00 CST: Confirmed that the learner slide renderer observes
  the native `audio` element used for listening; finalized sources can use that
  path, while streamed sources later required a UI-library extension.
- [x] 2026-09-04 10:15 CST: Added a local, versioned playback-position storage contract
  and unit tests.
- [x] 2026-09-04 10:20 CST: Connected metadata restore and lifecycle persistence to the
  native listen audio without autoplay.
- [x] 2026-09-04 10:25 CST: Rendered an accessible compact timeline in the existing
  learner controls and tracked accepted seeks.
- [x] 2026-09-04 10:30 CST: Focused tests, type check, lint, repository harness, and
  generated knowledge-index validation passed; commit gate remains.
- [x] 2026-09-04 13:00 CST: Replaced the per-audio timeline with a lesson-wide
  timeline, including progression restrictions and cross-slide navigation.
- [x] 2026-09-04 13:05 CST: Moved the lesson timeline below the player and sized
  it to the presentation viewport.
- [x] 2026-09-04 13:30 CST: Corrected active-lesson seek bounds to the generated
  audio end (rather than the previously reached position) and added regression
  coverage that the displayed position advances with playback.
- [x] 2026-09-04 13:50 CST: Added metadata-only duration collection for
  finalized audio whose server record lacks a duration, and corrected resume
  identity resolution to follow the native player's current source.
- [x] 2026-09-04 14:15 CST: Persisted the lesson's most recent resumable audio
  target so refresh returns to that slide before restoring its own timestamp.
- [x] 2026-09-04 14:35 CST: Corrected the restore and timeline target mapping
  from renderer-element indexes to the Slide library's marker-step indexes.
- [x] 2026-09-04 14:40 CST: Replaced active-audio URL reverse lookup with the
  Slide callback's confirmed current element, and covered restoring a later
  marker step after non-step content.
- [x] 2026-09-04 15:55 CST: Corrected the callback contract: Slide confirms
  the active marker step, while the playing audio can be a non-marker member
  of that step. Resume and the lesson timeline now resolve the exact source
  within the confirmed step boundary, with a mode-switch regression test.
- [x] 2026-09-04 16:20 CST: Corrected finalized audio identity during segment
  playback. The browser source may be a temporary segment URL, so persistence
  now uses the Slide player's current logical audio element and its finalized
  source; regression coverage simulates that temporary source.
- [x] 2026-09-04 16:45 CST: Removed the lesson-wide timeline, cross-item seek,
  duration preloading, related styling, copy, analytics, and tests after
  usability review. Storage-backed same-audio resume remains intact.
- [x] 2026-09-04 18:00 CST: Extended the UI library with a segment-aware
  absolute-playback callback and an idempotent resume request. The learner
  now stores streamed offsets with a stable stream identity and restores them
  through the library without autoplay.

## Surprises & Discoveries

- The existing listen sequence has in-memory continuation handling, but no
  durable same-browser position contract.
- `Slide` keeps its native audio element inside the library, but the learner
  renderer already observes that element for playback state.
- `Slide` navigates by marker-step index, while the learner renderer owns a
  broader element list. `onStepChange` confirms the rendered marker step, not
  necessarily the exact audio-owning element: the learner must match the
  native source only within that marker's bounded element range.
- The player deliberately prefers streamed audio segments even after a final
  URL becomes available. Its native `audio.src` can therefore be a temporary
  segment URL, while the player custom-action context still identifies the
  finalized logical audio element.

## Decision Log

- 2026-09-04: Persist only in browser storage. A backend record would require
  retention, cross-device conflict, and reset semantics outside this release.
- 2026-09-04: Store a position only for finite, finalized audio and key it by
  course, lesson, stable element/audio identity, and source version so a newly
  generated audio file cannot resume at an unrelated offset.
- 2026-09-04: Restore after metadata readiness and never call `play()` as part
  of restoration, preserving browser autoplay policies.
- 2026-09-04: Do not expose a lesson-wide progress or seek control. Fixed
  output and segmented audio make a lesson duration misleading; retaining only
  per-audio resume keeps the control surface accurate.
- 2026-09-04: A per-audio timestamp alone cannot resume a lesson after refresh,
  because the player initially renders its first slide. Store the latest
  resumable audio identity per course and lesson, request that slide first, and
  then apply its source-scoped timestamp.
- 2026-09-04: Use the UI callback as the authoritative active-step boundary,
  then use the player custom-action context as the authoritative current audio
  identity. This keeps identity stable for non-marker children and for native
  segment URLs that cannot be matched to a finalized MP3 URL.
- 2026-09-04: For a live stream, store the logical element identity and its
  absolute elapsed time, not the transient browser segment URL or its local
  duration. A matching finalized file may still consume that saved stream
  target when the lesson is revisited.

## Outcomes & Retrospective

Implemented same-browser playback resume for finalized and streamed audio.
Stream restoration delegates segment availability and precise seeking to the
MarkdownFlow UI player and remains paused after restoring.

## Context and Orientation

`src/web/src/app/c/[[...id]]/Components/ChatUi/useListenMode.ts` coordinates
the ordered audio/interaction sequence and holds `AudioPlayerHandle`. The
learner control surface is rendered by the listen-mode chat components. Audio
tracks originate in `useChatLogicHook.tsx`; finalized tracks expose a stable
URL and duration while streaming tracks may not have a finite duration.

## Plan of Work

1. Add a pure playback-position storage module with validation, expiry-at-end
   rules, and tests.
2. Extend the native-audio integration to report metadata, time updates, seek,
   pause, ended, unmount, and visibility changes.
3. Restore exactly once for a matching audio identity after metadata is ready.
4. Cover the behavior with focused storage, hook, and component tests.

## Concrete Steps

1. Inspect `AudioPlayerHandle` and the active listen controls for the narrowest
   extension point.
2. Define the storage key and serialized value, then implement validation and
   lifecycle helpers.
3. Wire persistence and restoration through `ListenModeSlideRenderer`.
4. Run focused tests, type checking, linting, and the relevant browser suite
   if the harness surface changes.

## Validation and Acceptance

- A paused, finite audio item resumes at the saved offset after refresh or
  returning to listen mode, but remains paused.
- Seek changes are immediately eligible for persistence; normal playback saves
  at a bounded cadence and flushes on pause, unmount, and page hiding.
- Positions near the beginning or completion are not restored; a natural end
  clears the stored record.
- A regenerated or otherwise changed audio source does not reuse an old
  position.
- A streamed audio item writes its logical absolute position without treating
  the temporary segment boundary as an end; restoration waits for that segment
  and does not autoplay.

## Idempotence and Recovery

Storage parsing treats malformed, stale, non-finite, or mismatched records as
absent and removes them. All storage access is browser-guarded and best-effort;
failure leaves normal playback unchanged. Clearing browser storage fully resets
the feature.

## Interfaces and Dependencies

- Browser `HTMLAudioElement` metadata,
  `timeupdate`, `pause`, `ended`, and visibility events.
- Browser `localStorage`; no new API endpoint, database table, or migration.
