---
title: Restore course answer edits
---

## Purpose / Big Picture

An answered last question should support the same edit action as earlier
questions. A question recovered from model narration should be editable in
published learning and full-course preview when its accepting turn can be
identified. See [Shared Interaction Rewind](../../product-specs/shared-interaction-rewind.md).

## Progress

- [x] 2026-11-09 11:41 CST: Reproduced both failures on origin/main in both learning modes.
- [x] 2026-11-09 11:46 CST: Route submissions by the saved answer and restore narrated replies from adjacent turn evidence.
- [x] 2026-11-09 11:51 CST: Verify saved answers, regenerated teaching and history reload in both course modes.

## Surprises & Discoveries

An answered control can remain the last actionable row after completion.
A narrated control has no native tool call, so its answer is a message turn.

## Decision Log

Keep native question order and existing reload anchors. Require adjacent saved
evidence for narrated answers. Reuse the preview rewind analytics contract.

## Outcomes & Retrospective

The last answer now uses the existing confirmation and reload request. A
narrated answer restores its own message turn, and its replacement appears on
the same control after history reload. The offline service tests cover current
and historical checkpoints, active session ownership and a later native
question. The frontend tests cover repeat suppression and retry after a failed
optimistic edit. Verified with 480 backend tests and 123 frontend tests.

## Context and Orientation

The course chat submits reload anchors; the service restores a saved checkpoint.
Published history uses turn block records, while preview uses scoped presentation
metadata and element rows.

## Plan of Work

Classify first, repeated and changed answers. Resolve narrated answers against
the next saved turn, then use the same evidence to project their defaults.

## Concrete Steps

Run the course chat Jest suite and the backend learning rewind/history tests.
Verify that the first answer remains normal and the replacement is visible after
loading history again.

## Validation and Acceptance

A changed final answer starts one confirmed rewind. A narrated edit removes old
teaching and restores its own message turn even with a later native question.
Missing or foreign evidence must not change existing progress.

## Idempotence and Recovery

Retirement and replacement use the existing transaction. Repeated unchanged
submissions are ignored. Unavailable checkpoints use the existing error.

## Interfaces and Dependencies

Existing reload anchors, checkpoints, history payloads and Umami events; no
database migration or request schema change.
