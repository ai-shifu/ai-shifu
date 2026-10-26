---
title: Share lesson request completion
status: active
owner_surface: backend
last_reviewed: 2026-10-26
---

# Share lesson request completion

## Purpose / Big Picture

Share only HTTP request completion between formal learning and preview. An
already-finished editor preview must emit one terminal event, as formal learning
does. Keep the existing frontend, model execution and session-saving code.

## Progress

- [x] 2026-10-26 CST: Narrow PR #3191 at the user's request; restore all frontend
  and session-save changes to the PR base, `beeccf3fb`.
- [x] 2026-10-26 CST: Replace the broad stream wrapper with a small completion
  policy, retaining the original polling, serialization and error handling.
- [x] 2026-10-26 CST: Pass 67 focused request-completion, cleanup and legacy
  preview-history tests; full learning-host suite: 3,658 passed, 93 skipped.
- [ ] 2026-10-26 CST: Run repository gates, align SIM and update the existing PR.

## Surprises & Discoveries

Legacy preview saves its context after the adapter finishes. Its terminal event
must wait until that save completes, or closing the source loses the new turn.
This ordering fix is required by request completion, not a storage refactor.

## Decision Log

- Share only terminal observation, cancellation and the need to add one final
  event. Retain formal polling, heartbeat, status updates and error mapping.
- Preserve `done(false)` as a block boundary. Only `done(true)` ends the request;
  neither signal independently marks the lesson complete.
- Keep the existing draft/published permissions, save paths and frontend protocol.
  Frontend SSE and session-save refactoring are deferred outside this PR.
- Record a terminal only after serialization succeeds. Disconnects do not create
  successful completion, and terminal events do not create learning elements.

## Outcomes & Retrospective

The narrower patch is being verified. The previous `sim-48acc14` acceptance
included withdrawn frontend and storage changes; it does not validate this scope.

## Context and Orientation

The completion policy is in `flaskr/service/learn/request_stream.py`. Its callers
are `routes.py` and `runscript_v2.py`; editor debug delegates completion to its
request boundary. See the [host contract](../../design-docs/markdownflow-engine-library.md#course-request-completion).

## Plan of Work

Restore unrelated changes, retain only the completion policy and necessary legacy
ordering adjustment, then test both real request boundaries and update PR #3191.

## Concrete Steps

Run targeted and full learning-host tests in the pinned SDK environment. Regenerate
knowledge indexes and run the dev-tool doctor and full pre-commit gate. Verify
the narrowed SIM runtime through an isolated debug session and completed replay.

## Validation and Acceptance

Normal and empty EOF emit one terminal; existing terminals do not repeat. Block
boundaries and audio readiness remain ordered. Errors retain their payloads,
disconnects stop output, and legacy preview history is saved before terminal
delivery. Completed-session replay adds no model calls or credits.

## Idempotence and Recovery

No schema or model-setting changes. SIM shares production storage and billing;
use fresh debug-session IDs and preserve existing learner and author previews.
Record the exact deployed image for any rollback.

## Interfaces and Dependencies

Keep all endpoint, event, frontend and storage interfaces unchanged. No new
dependency, transport layer or session-save abstraction is introduced.
