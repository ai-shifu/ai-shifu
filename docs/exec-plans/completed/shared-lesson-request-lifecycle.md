---
title: Share lesson request lifecycle and session persistence
status: completed
owner_surface: learning-runtime
last_reviewed: 2026-10-26
---

# Share lesson request lifecycle and session persistence

## Purpose / Big Picture

Formal learning, whole-course preview and editor debug share the MarkdownFlow
engine but independently coordinate request termination and storage. A finished
debug session currently closes without the terminal event that formal learning
adds. Share request lifecycle rules and session-save dispatch while preserving
content, permission, billing and history isolation between the three hosts.

## Progress

- [x] 2026-10-26 CST: Inspect all three paths and confirm the finished-preview
  discrepancy on SIM; independently review backend and frontend duplication.
- [x] 2026-10-26 CST: Refresh main and create an independent branch after PR #3189
  was merged.
- [x] 2026-10-26 CST: Share backend stream termination and regression coverage.
- [x] 2026-10-26 CST: Select a session-save strategy once per turn and preserve
  every existing persistence boundary and isolation rule.
- [x] 2026-10-26 CST: Share frontend lesson SSE transport and lifecycle cleanup.
- [x] 2026-10-26 CST: Run affected suites, repository gates and independent review.
- [x] 2026-10-26 CST: Verify the changed paths on SIM and prepare a focused PR.

## Surprises & Discoveries

- MDF2 teaching is already shared through `agent_lesson_events`,
  `run_agent_lesson` and the application-independent engine. Preview elements
  already inherit the formal element adapter.
- Formal learning serializes SSE internally while editor preview yields typed
  DTOs. Shared lifecycle rules must respect both existing public interfaces.
- The native turn ending, HTTP request ending and lesson completion are distinct
  boundaries. An interaction can end an HTTP response while its lesson remains
  unfinished.
- SIM shares production storage and billing. Use isolated debug runs; never reset
  the historical learner sessions or change a shared course model for testing.
- Independent review reproduced a legacy preview whose context cache was updated
  after its terminal event. Hold that event until the existing cache update
  finishes; closing a terminal source must not lose the accepted preview turn.
- Real Chromium executes microtasks between native XHR load listeners. A
  microtask-only EOF fallback can settle before JSON business-error detection.
  Defer EOF to the next task, cancel its timer on settlement, and preserve the
  current-source guard before any business-error side effect.

## Decision Log

- Preserve endpoint methods, payloads, event names and `is_terminal` semantics.
  A non-terminal `done` marks a block boundary; a terminal event closes the HTTP
  stream and does not independently mark the lesson complete.
- Use shared stream lifecycle state at the existing event/transport boundaries.
  Normal empty streams must terminate, existing terminal events must not repeat,
  and disconnects must not yield additional events.
- Move repeated frontend SSE construction out of the editor hook into the shared
  request domain, reusing current authentication, trace and business-error paths.
  Keep page-specific history, rewind, element rendering and interaction behavior.
- Choose debug versus persisted session saving once per turn. Keep prepared
  content, terminal and interrupted-partial saves at their existing points;
  preserve reset/rewind generation checks and transaction ownership.
- Keep MDF1 compatibility and draft/published authorization and persistence
  differences. Legacy retirement and broad element-reducer rewrites are outside
  this task.

## Outcomes & Retrospective

Implementation and verification are complete. No main-branch merge or production
service deployment was performed. The previous finish repair remains
independently reviewable in merged PR #3189.

Verification passes 2,653 portable engine tests, 3,675 learning-host tests (93
skipped) and all 3,412 frontend tests across 278 suites, plus TypeScript and lint.
Independent review reproduced and closed both the legacy-preview cache and
native-XHR scheduling regressions. Real Chromium checks pass for HTTP 200/403
JSON business errors, ordinary EOF, retired requests and cancellation. The full
repository pre-commit gate and architecture boundary check pass.

SIM integration `48acc14de3a79f6ba011e7c039382e3c19abf9fb` preserves SIM history
and has the same runtime source tree as implementation commit `66cad4b27`.
[Drone build 5503](https://ci.pillowai.cn/ai-shifu/ai-shifu/5503) produced
`sim-48acc14`. API deployment record 3370 and Web record 3371 completed; actual
readback showed API 2/2 and Web 1/1 available with zero restarts. The deployed
request helper SHA-256 is
`75d4d4f2ab36e8c63fce85777d92f290b1dcdd58aa299b2752ff83603ebb2542`,
and the course runner is
`fc32bd6479742571f6fdbc5a26101bc73bd64f1888a889d44e9dbeefb925dcc3`,
both matching the tested source.

Real-model acceptance reused the original 1,108-character lesson script from the
earlier finish investigation, SHA-256
`94f82238770f1f7861f01c952e9116536e54a68cc27ac1a6ba4a24ed926eae83`.
The isolated run `lifecycle-419221a9e3774297bf223139c7a4f5b7` used
`ark/deepseek-v4-1-flash-261017` and finished with one paired finish call/return,
no pending question and no model responses or retries after accepted finish.
Its two actual model requests match usage rows 812525 and 812526 and two distinct
consumption ledger entries totaling 9.55 credits: 42,876 input tokens, 37,760
cached input and 4,859 output tokens. This is an acceptance run, not a controlled
cost comparison with a prior model response.

The initial HTTP trace was `851ff9a05a0b44ecb77ccf3063492165`. Two subsequent
requests using the same completed debug session had traces
`324ef55e62e2474f8ab6cf5614a03a9e` and
`ff8d9c35396d4ffba9e35281905141c9`. Each now emits exactly
`preview_engine` followed by one terminal `done`; both probes exit successfully.
Both add zero usage rows or credits, and the Session history and usage remain
identical. Thus the previously observed missing terminal is fixed on the
deployed runtime without reopening the engine.

Existing author course-preview state was left intact. Formal/course-preview
boundaries are covered by the common request fixtures and full learning suite;
no new live persisted author-preview turn or learner progress was created for
this acceptance. No database migration or shared course-model change was made.

## Context and Orientation

`flaskr/service/learn/routes.py` exposes formal/whole-course preview and editor
preview endpoints. `runscript_v2.py` owns formal streaming; editor debug enters
through `agent/debug_session.py`. Both consume `agent/lesson_entry.py` and
`agent/run_agent.py`. Shared frontend infrastructure belongs under
`src/web/src/lib/`; consumers are `api/studyV2.ts`, the course chat hook and
`components/lesson-preview/usePreviewChat.tsx`.

The durable engine and host boundaries are in the
[engine library design](../../design-docs/markdownflow-engine-library.md).
The request and persistence contract is in the
[shared lifecycle design](../../design-docs/lesson-request-lifecycle.md).

## Plan of Work

First establish a shared request-end contract with failing regressions for the
known empty-preview case. Independently centralize frontend SSE transport and
session-save dispatch. Integrate without broad UI or engine changes, validate
the host and consumer boundaries, then exercise the reviewed runtime on SIM.

## Concrete Steps

Use the repository-pinned SDK environment for backend host and MarkdownFlow
tests. Run focused Jest suites, TypeScript checking and frontend lint for shared
transport changes. Regenerate repository knowledge indexes, run architectural
checks and the full pre-commit gate. Verify immutable SIM images and actual
session history/usage after a real lesson and a completed-session replay.

## Validation and Acceptance

- Formal, course-preview and debug streams end exactly once on normal EOF,
  including empty finished sessions; block boundaries do not close early.
- Errors retain their existing visible payloads and terminal behavior;
  disconnect/cancellation performs cleanup without sending completion.
- Frontend cleanup runs once for terminal, EOF, error and cancellation. Events
  from retired sources cannot modify the next request's state.
- Existing auth, language, trace, billing-error and request payload contracts
  remain intact; existing analytics triggers and schemas remain accurate.
- Debug storage remains temporary and isolated. Persisted saves retain all
  generation, reset, rewind, memory and partial-output safeguards.
- The finish repair still stops model requests; completed-session replay adds
  no model usage or credits.

## Idempotence and Recovery

No database or saved-session schema changes are needed. Existing stores and
preview namespaces are reused. Roll back only the SIM images to the recorded
pre-task tags if needed. Keep current deployment and model identifiers in the
verification record rather than embedding credentials or learner content.

The verified pre-task SIM branch tip is
`277e7ad9b9f19beaa17ee9287b4ed9186659f42c`; both API and Web currently run
`sim-277e7ad`. That immutable tag is the rollback point for this verification.

## Interfaces and Dependencies

Keep `RunElementSSEMessageDTO`, `RunMarkdownFlowDTO`, public hook return fields and
existing API signatures compatible. Shared transport may expose internal
once-only settlement callbacks; all producers and consumers change together.
No new dependency or model-provider API is required.
