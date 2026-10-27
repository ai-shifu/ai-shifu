---
title: Share lesson request completion
status: completed
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
- [x] 2026-10-26 CST: Pass full repository gates and update PR #3191. Deploy
  SIM build 5504 (`sim-d92a225`); verify API 2/2 and Web 1/1 ready, with six
  deployed backend source hashes matching the narrowed PR.
- [x] 2026-10-26 CST: Complete the original affected lesson in an isolated editor
  debug session using `ark/deepseek-v4-1-flash-261017`. Observe one terminal,
  two actual calls and two usage/consumption entries totaling 9.62 credits.
  Two completed-session replays each emit one terminal and add zero calls or
  charges, with saved history unchanged and no response or retry after finish.
- [x] 2026-10-27 CST: Complete real-browser SIM acceptance for formal learning,
  course preview and editor debug. Reconcile every model usage against its unique
  consumption entry and verify completed replays add zero usage or charges.

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

The narrowed patch passes 67 focused tests and the full learning-host suite
(3,658 passed, 93 skipped), plus the full repository gate. SIM build 5504 now has
real-browser acceptance for formal learning, course preview and editor debug,
including native-session and read-only usage/ledger reconciliation.
The previous broad `sim-48acc14` is replaced in both API and Web. Existing learner
and author-preview sessions were preserved. Production services were not deployed.

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

The browser acceptance used the existing free internal test course
`4d011ad81eb348ce9f1c171a98d0d0cc`, lesson
`8303a2e1f64f4a5da47cf57619841337`, for both published learning and draft preview.
Both scopes were initially unused; two anonymous answers led to natural finish.
Editor debug used the original affected lesson in an isolated debug session.

| Path | Actual model | Model usages / consumption entries | Credits |
| --- | --- | --- | --- |
| Formal learning | `qwen/glm-5.3` | 3 / 3 | 24.66 |
| Course preview | `qwen/glm-5.3` | 4 / 4 | 18.90 |
| Editor debug | `ark/deepseek-v4-1-flash-261017` | 2 / 2 | 9.32 |

These are individual acceptance runs, not a cost benchmark. Each actual usage
has exactly one consumption entry. All three native sessions reached finish with
no subsequent model response or retry. Each observed completed request emitted
one terminal, the UI became idle, and formal learning offered the next lesson
with progress status 603. Completed HTTP replays preserved history and added zero
usage/charges; course preview replayed saved elements before its terminal. The
browser's automatic preview replay was also checked separately and cost zero.
Before/after hashes confirmed unchanged canonical, global and test-course profile
values. The original course's existing learner and author-preview sessions were
unchanged. No reset, migration, model-setting or runtime change was needed.

## Idempotence and Recovery

No schema or model-setting changes. SIM shares production storage and billing;
use fresh debug-session IDs and preserve existing learner and author previews.
Record the exact deployed image for any rollback.

## Interfaces and Dependencies

Keep all endpoint, event, frontend and storage interfaces unchanged. No new
dependency, transport layer or session-save abstraction is introduced.
