---
title: Restore answer edits in the shared classroom
---

## Purpose / Big Picture

Learners can edit the last answer of a finished lesson and a question rendered
from model narration. Both actions work in published learning and ordinary
preview. See [Shared Interaction Rewind](../../product-specs/shared-interaction-rewind.md).

## Progress

- [x] 2026-11-10 CST: Reproduce the missing final-answer anchor and the rejected narrated answer on current main.
- [x] 2026-11-10 CST: Port the reviewed learner behavior and adapt the server fix to shared lesson attempts.
- [x] 2026-11-10 CST: Verify the replacement against the frontend and learning-service suites, including first publication.

## Surprises & Discoveries

Ordinary preview and published learning now share the active lesson attempt.
The previous fix's separate preview presentation modules have been removed.
The server already handles a final native answer once the client sends its
anchor.

## Decision Log

Use the common history projection and rewind planner. Keep the native
question IDs and attempt ownership checks. A narrated answer requires its
immediate successor's saved input and verification against the active session
before restoration.

## Outcomes & Retrospective

The shared path can edit a narrated answer in ordinary preview, published
learning, and after first publication. Regression tests cover the old and new
checkpoint formats and reject a different session before restoration.
The learning-service suite passed 3,723 tests with 90 skipped, and the
frontend suites passed 133 tests. Frontend type checking and lint passed.

## Context and Orientation

The web course chat detects an edit and sends the original element and block
IDs. The learning service selects a checkpoint, restores the engine, and
atomically retires the superseded suffix when the new turn is saved.

## Plan of Work

Preserve the reviewed ordered-answer and failed-edit behavior. Recognize the
narrated control's original message and project its answer on history reload.

## Concrete Steps

Run the course chat, rewind helper, and preview analytics Jest suites. Run the
backend learning-service tests with SQLite and the offline engine fixtures.

## Validation and Acceptance

Verify normal first answers, native final edits, failed-edit recovery, and
narrated edits that regenerate teaching before a later native question. The
replacement is visible on reload, including across first publication.

## Idempotence and Recovery

Settled repeats do not submit a second turn. An interrupted edit can be retried.
Inconsistent historical evidence follows the existing unavailable-rewind path.

## Interfaces and Dependencies

Reuse existing reload anchors, turn records, history payloads and preview
rewind analytics. The checkpoint records an optional session ID. Existing
records can be verified against the active session without a database migration.
