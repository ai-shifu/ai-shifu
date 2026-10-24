---
title: Keep concurrent gevent lesson streams responsive
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Keep concurrent gevent lesson streams responsive

## Purpose / Big Picture

Fix the existing intermittent hang in the synchronous bridge for MarkdownFlow
2.0 async turns. A learner's stream must finish when its producer finishes, even
with many simultaneous requests under the production gevent worker.

## Progress

- [x] 2026-10-08 09:10 UTC: Resume after the owner's manual merge of #3046;
  publishing acceptance continues separately from this runtime change.
- [x] 2026-10-08: Plain macOS bridge checks pass (16 tests). Reproduce the
  unmodified 24-turn script in the downloaded Linux ARM64 production image:
  fresh interpreter attempt 12 hangs after detection; all producer threads idle.
- [x] 2026-10-08 09:17 UTC: Capture a request suspended in the patched queue's
  semaphore condition lock with four unread events and an idle producer. Restore
  the original native queue and the native admission-counter lock. A queue-only
  correction still fails repeated high-contention probes.
- [x] 2026-10-08: Add high-contention ordered streaming, backpressure/resume,
  quiet-turn cancellation/capacity refusal, error cleanup and counter-contention
  checks. Plain/gevent bridge tests pass; full learning/profile regression:
  2,734 passed, 1 skipped, 4 subtests. Linux fresh-interpreter probes pass 20/20
  before and 20/20 after the cancellation/error extensions. Restoring the patched
  queue fails the new streaming regression; source files remain unchanged by
  mutation probes, which mount separate disposable copies.
- [x] 2026-10-08 09:19 UTC: Independently restoring the cooperative admission
  lock also fails the streaming regression (batch 0, turn 3); the patched-queue
  mutation fails batch 2, turn 8. Developer-tool checks, Ruff and every repository
  pre-commit gate pass.
- [ ] 2026-10-08: Run bridge and learning regressions, Linux concurrency checks,
  repository gates, publish one PR and validate sim before manual main merge.

## Surprises & Discoveries

The pinned gevent 24.10.3 monkey patch replaces queue.SimpleQueue with Python's
semaphore-based queue._PySimpleQueue. The bridge documentation assumed the native
C queue. A failed original run has four unread events after its producer finishes;
the request is suspended acquiring the queue semaphore's condition lock. Native
producer threads must not share these cooperative synchronization primitives.
The admission counter also crosses that boundary; changing only the queue leaves
an intermittent failure in the stronger probe. Keep its very short, I/O-free
counter critical section on the original native lock as well. The pool-creation
lock remains cooperative because only request greenlets use it.

## Decision Log

- 2026-10-08: Fix the reproduced bridge failure before adding semantic-history
  summaries. Keep this PR independent of the image-publication implementation.
- 2026-10-08: Preserve cancellation, bounded buffering, immediate capacity
  refusal, heartbeats, event order and request/producer loop isolation.
- 2026-10-08: Use monkey.get_original for the two cross-native synchronization
  primitives. Do not unpatch the process, move asyncio onto request greenlets,
  upgrade gevent, or change the worker mode to hide the bug.

## Outcomes & Retrospective

The original Linux failure and patched-queue negative regression are reproduced.
The correction passes native Linux stress and local bridge/learning regressions.
Repository gates, review and deployed acceptance remain in progress. A passing
retry alone does not close an intermittent failure.

## Context and Orientation

Runtime: src/api/flaskr/service/learn/agent/bridge.py. Plain-thread tests live in
test_bridge.py; test_bridge_gevent.py launches gevent_scripts/bridge_under_gevent.py
in a fresh interpreter to avoid patching the entire pytest process.

## Plan of Work

Inspect failed greenlet/queue state, prove the defect with a regression, retain
the safe native-thread boundary and verify both worker modes. Use isolated
generators, not model providers or shared learner storage, for concurrency probes.

## Concrete Steps

Use conda ai-shifu for backend tests and the downloaded repository-built Linux
image for native Linux probes. Run focused bridge tests before widening to
learning/profile and repository gates. Stage documentation before regenerating
knowledge indexes. Publish to GitHub origin and synchronize to sim only after
local checks pass; reply to every independent AI review opinion.

## Validation and Acceptance

Concurrent turns return exactly their own ordered events and release admission
slots. A disconnected client cancels its producer without freezing the hub;
buffer limits and heartbeat timing remain intact. Regressions fail with the
correction removed. Final sim replicas must contain the tested module and pass
the same isolated probe. Production remains on engine 1.0 until a separate user
decision; main merge remains manual.

## Idempotence and Recovery

Repeated isolated probes create no learner records or provider calls. Test
containers are disposable. Revert only this change if needed; preserve existing
course-memory isolation and image-publication changes.

## Interfaces and Dependencies

Keep iter_turn and TurnStream interfaces and SSE events unchanged. No schema,
dependency upgrade or configuration change is planned.
