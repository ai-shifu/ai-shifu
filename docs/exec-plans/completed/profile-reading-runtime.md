---
title: Profile collection uses course reading rendering
status: completed
owner_surface: frontend
last_reviewed: 2026-11-07
---

# Profile collection uses course reading rendering

## Purpose / Big Picture

Use the same MarkdownFlow rendering, waiting feedback and answer editing as
course reading in learner Profile collection and its operator preview. Profile
continues to prepare a private draft and lets the learner review and save it.

## Progress

- [x] 2026-11-07 11:18 CST: Verify the existing in-memory course adapter emits
  text, HTML, interaction and finality events without a course database.
- [x] 2026-11-07 11:30 CST: Connect shared rendering and waiting feedback.
- [x] 2026-11-07 11:30 CST: Wire Profile-owned answer rewind and analytics.
- [x] 2026-11-07 11:30 CST: Verify frontend, backend and repository contracts.

## Surprises & Discoveries

The course adapter already has an in-memory implementation used by Debug.
Course runtime and storage are independent of this reuse point.

## Decision Log

Use existing rendering and rewind operations through public exports. Retain
Profile ownership of session revisions, Redis, exact replay and private drafts.
Reuse course waiting feedback for question generation. Use a distinct localized
status for the existing Profile summary phase.

## Outcomes & Retrospective

Profile and its operator preview use the shared reading renderer. The
questionnaire host reuses course element conversion and engine checkpoints.
The complete Web Jest suite and the focused Profile and course backend
suites passed locally.

## Context and Orientation

Profile run and Redis session live in `src/api/flaskr/service/profile_research`.
Course element conversion and rewind are already used in course Debug. Learner
and admin Profile use the same conversation component.

## Plan of Work

Replace Profile's custom conversion with the in-memory course adapter. Share
the course reading block, typewriter gate and loading UI. Retain Profile's
controls-only interaction presentation and current question identity. Restore
the saved answer checkpoint when the learner confirms an edit.

## Concrete Steps

1. Export existing course operations through the learning API.
2. Produce compatible snapshots with stable display IDs and element finality.
3. On accepted edit replace the obsolete suffix and invalidate its draft.
4. Track confirmed edit requests and terminal outcomes per the
   [analytics contract](../../product-specs/web-umami-contract-remediation.md).

## Validation and Acceptance

Verify rendering during a first request, follow-up generation, and private
summary. Exercise confirmation, accepted and rejected edits, exact replay,
replacement of old answers and drafts, and the operator preview path. Run
focused tests and architecture and repository harness checks.

## Idempotence and Recovery

A failed replacement preserves the last committed branch and draft. Retries
reuse the original revision, target and request ID. Existing sessions without
checkpoints remain answerable and expose edits for newly checkpointed answers.

## Interfaces and Dependencies

The Profile run endpoint accepts an optional rewind flag and publishes
rewindable native IDs, plus a rewind acknowledgement for accepted replacements.
Existing Profile content events retain their strings and gain element finality.
The learning runtime and database remain unchanged.
