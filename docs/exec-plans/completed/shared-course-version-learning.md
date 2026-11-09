# Share learning across course versions

## Purpose / Big Picture

A learner opening a draft course uses the same course and lesson history as
when opening its publication. The requested version determines the content
for new learning. An existing attempt keeps the version and pending question
it began with. Retaking resets that same attempt and uses the selected version.
Unpublished content still requires draft access.

## Progress

- [x] 2026-11-08 18:45 CST: Confirmed the shared attempt model and examined the
  existing publication revision, progress, and history contracts.
- [x] 2026-11-08 19:02 CST: Shared attempt identity and protected the retained source.
- [x] 2026-11-08 19:13 CST: Aligned history, reset, navigation, follow-up and audio.
- [x] 2026-11-08 19:19 CST: Verified the learning and web suites, including
  first publication, legacy data, permission revocation, and version changes.
- [x] 2026-11-09 13:49 CST: Removed standalone preview migration and replay.
  Verified direct start, retake with an old follow-up, and first publication.

## Surprises & Discoveries

- Publishing already preserves course and lesson business IDs and carries
  forward the script revision. Script revision does not cover course settings.
- Old standalone previews can store teaching outside the shared progress
  record, even when a follow-up has a progress row of its own.
- Existing progress cannot serve as evidence of course purchase. Text follow-up
  must check entitlement before reusing or creating progress.

## Decision Log

- Keep the stable account, course and lesson scope of formal learning. Use one
  active attempt for both classroom entry points and retain the content source
  when an attempt starts. Keep the existing independent editor Debug session.
- Start fresh when only an old standalone preview session exists. Use the
  shared history reader and retire the old session on retake.
- Retain draft authorization and explicit billing attribution. Recheck draft
  access before returning or using a retained draft source through either URL.
  A script revision match alone cannot prove settings are safe to publish.

## Outcomes & Retrospective

Both classroom entry points now use the same durable learning attempt and
persist new teaching under its retained source. A course can start from an
unpublished draft and keep its progress, transcript and pending question
after publication. Retaking chooses the selected version and retires old
standalone preview sessions. Opening a lesson with only an old preview starts
a fresh shared attempt.

The local learning suite passed 3,643 tests with 90 skips. A targeted run
also verified recovery after draft access is revoked and the reset quota is
exhausted. All 3,822 web tests passed. The API cutover requirement is recorded
in the classroom history reference.

## Context and Orientation

The learn host, `agent/lesson_entry.py`, `agent/run_agent.py`, and
`agent/session_store.py` run and retain the lesson. `elements/run_adapter.py`
and `learn_funcs.py` expose its history and outline. Text and live follow-up
use the learn service's existing anchors. The Cook Web course layout chooses
the version and renders the shared conversation.

## Plan of Work

Select and validate one physical version for new learning. Persist the source
alongside the active attempt and use it to authorize and resolve later actions.
Remove the ordinary-preview runtime and history reader. Use the selected
outline for navigation and the canonical progress record for writes, resets,
and completion.

## Concrete Steps

1. Implement shared attempt identity and retained content authorization.
2. Converge the teaching run, rewind, history, reset, and outline state.
3. Resolve text and live follow-up and audio from the same owned attempt.
4. Align version selection and learning actions in the classroom.
5. Run shared regression and compatibility checks.

## Validation and Acceptance

Exercise draft to published and published to draft for the same user and
lesson, including a course that has never been published. Publish it through
the real authoring service and verify that the original pending question is
answered under the same attempt and progress IDs. Verify continuing a pending interaction, shared completion and
retake, exact content revision, authorization after role revocation,
late writes after reset, and an unchanged revision after publication.
Verify that a lesson with only an old standalone preview opens a new attempt
and that retaking clears an old session and its related progress. Exercise old
formal records with missing provenance and a lesson absent from the selected
outline. Verify that a progress row does not grant course purchase.

## Idempotence and Recovery

Use the established progress lock and reset receipt to serialize mutations.
Keep original records and provenance through the change. An active attempt
must never be replaced during a read because the request used a different URL.
Drain old API workers before enabling the new build. Roll back only to a
version that still enforces draft provenance for the shared records.

## Interfaces and Dependencies

Reuse the existing learning routes and event envelope, progress rows,
record/reset APIs, and browser version selector. The memory manager reuse is
based on the independent memory change.
