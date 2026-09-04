# Learner listen resume and timeline

## Purpose / Big Picture

Learners can leave and return to a listening lesson in the same browser without
losing their position in the current audio item. The existing listen controls
gain a compact timeline for finalized, seekable audio. Restoring a position
never starts audio automatically.

## Progress

- [x] 2026-09-04 10:00 CST: Confirmed that the learner slide renderer owns
  the native `audio` element used for listening; no backend or UI-library
  change is needed.
- [x] 2026-09-04: Added a local, versioned playback-position storage contract
  and unit tests.
- [x] 2026-09-04: Connected metadata restore and lifecycle persistence to the
  native listen audio without autoplay.
- [x] 2026-09-04: Rendered an accessible compact timeline in the existing
  learner controls and tracked accepted seeks.
- [x] 2026-09-04: Focused tests, type check, lint, repository harness, and
  generated knowledge-index validation passed; commit gate remains.

## Surprises & Discoveries

- The existing listen sequence has in-memory continuation handling, but no
  durable same-browser position contract.
- `Slide` keeps its native audio element inside the library, but the learner
  renderer already observes that element for playback state. The resume and
  timeline behavior can use the same lifecycle listeners without extending the
  library API.

## Decision Log

- 2026-09-04: Persist only in browser storage. A backend record would require
  retention, cross-device conflict, and reset semantics outside this release.
- 2026-09-04: Store a position only for finite, finalized audio and key it by
  course, lesson, stable element/audio identity, and source version so a newly
  generated audio file cannot resume at an unrelated offset.
- 2026-09-04: Restore after metadata readiness and never call `play()` as part
  of restoration, preserving browser autoplay policies.
- 2026-09-04: Track accepted manual timeline seeks, not automatic restores or
  timeline renders. This produces an adoption signal without render noise.

## Outcomes & Retrospective

Implemented same-browser playback resume, a finite-audio timeline, and a
privacy-safe manual-seek adoption event. The feature deliberately excludes
streaming and unknown-duration sources.

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
4. Add a timeline control only where the active audio is finite and seekable;
   show a disabled progress state otherwise.
5. Cover the behavior with focused storage, hook, and component tests.

## Concrete Steps

1. Inspect `AudioPlayerHandle` and the active listen controls for the narrowest
   extension point.
2. Define the storage key and serialized value, then implement validation and
   lifecycle helpers.
3. Wire persistence and restoration through `ListenModeSlideRenderer`.
4. Render and style the timeline with keyboard-accessible seek behavior.
5. Run focused tests, type checking, linting, and the relevant browser suite
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
- Streaming/unknown-duration audio cannot be sought and does not write an
  invalid position.
- Desktop and mobile expose the same control semantics without obstructing the
  existing playback controls.

## Idempotence and Recovery

Storage parsing treats malformed, stale, non-finite, or mismatched records as
absent and removes them. All storage access is browser-guarded and best-effort;
failure leaves normal playback unchanged. Clearing browser storage fully resets
the feature.

## Interfaces and Dependencies

- Browser `HTMLAudioElement` metadata,
  `timeupdate`, `pause`, `ended`, and visibility events.
- Browser `localStorage`; no new runtime dependency, API endpoint, database
  table, migration, or markdown-flow-ui prop.

### learner_listen_timeline_seek

- Business question: Do learners use timeline seeking in listen mode enough to
  retain and improve the control?
- Metric definition: Count accepted seek actions, grouped by the fixed surface
  enum, over a reporting window. It is not a completion or retention metric.
- Event name: `learner_listen_timeline_seek`.
- Actor and surface: Learners on `learner_desktop` or `learner_mobile`.
  Anonymous trial learners are included; teacher/classroom mode and streaming
  or unknown-duration audio are excluded because no timeline is available.
- Trigger: A user commits a changed value through the timeline range control
  after the audio has a finite duration.
- Count unit and deduplication: One accepted value commit. Repeated deliberate
  seeks are meaningful and are not deduplicated; rendering, resume restore,
  and time updates never emit an event.
- Correlation: No course, lesson, audio URL, user text, or title is sent; the
  shared tracker provides its existing identity context.
- Consumers: Learner experience owner uses the event count by surface to judge
  timeline adoption after release.
- Compatibility: New additive event family.
- Verification: Component tests cover both surface values, no event for
  disabled/unchanged timeline states, exact payload, and tracking failure
  isolation.

| Field | Type | Allowed values | Cardinality | Privacy class | Why required |
| --- | --- | --- | --- | --- | --- |
| `surface` | string | `learner_desktop`, `learner_mobile` | 2 | non-personal | Compare control adoption by form factor. |
