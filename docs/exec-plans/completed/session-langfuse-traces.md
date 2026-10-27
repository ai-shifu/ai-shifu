---
title: Session Langfuse Traces
status: completed
owner_surface: backend
last_reviewed: 2026-10-27
canonical: false
---

# Session Langfuse Traces

The session-to-trace identity decision below is superseded by the
[advancement tracing contract](../../design-docs/langfuse-trace-association.md#session-and-advancement-identity).
The verified fault-isolation and regression work remains in effect.

## Purpose / Big Picture

Use one Langfuse trace per learning or Profile session, while preserving each
request's input, public output, outcome, model calls, and tool hierarchy.

## Progress

- [x] 2026-10-27 CST: Read the current tracing contract and Langfuse SDK docs; fetched origin/main and created sunner/session-langfuse-traces.
- [x] 2026-10-27 CST: Identified course session loading as the earliest stable trace binding point.
- [x] 2026-10-27 CST: Implemented deterministic session identity in shared, course, Profile, and legacy tracing.
- [x] 2026-10-27 CST: Verified cross-request grouping, reset isolation, request metadata, parent links, and failure isolation; 3,929 tests passed, 93 skipped.
- [x] 2026-10-27 CST: Updated the canonical contract; tool availability, full pre-commit, repository harness, and architecture checks passed.
- [x] 2026-10-27 CST: Opened and attached ready PR #3196; verified it is open, mergeable, and unmerged. Reviewed scope and local acceptance before archival.

## Surprises & Discoveries

Course roots and turns currently start before the native session exists. Their
OTel trace ids cannot be changed afterward. First-turn progress/block metadata
arrives before new session creation and must survive delayed observation
creation. Profile already knows its session id before tracing starts. Legacy
course runtime also resolves its progress session before any model operation.

## Decision Log

- Replace request-based trace ids with deterministic, namespaced session ids
  scoped by user. Keep request ids in observation metadata.
- Each request owns a distinct root observation inside the shared trace; each
  request ends its observations normally. Never hold spans open between HTTP
  requests or cache telemetry objects across workers.
- Delay course trace and round creation until the existing session callback.
  Requests that fail before resolving a session retain a request-based error
  trace. Keep the current Langfuse 4.14.4 pin; no SDK upgrade is needed.
- Preserve replay, business persistence, metering, streaming, and engine
  contracts. No session migration or historical trace backfill.

## Outcomes & Retrospective

The learning, Profile, shared Langfuse, and payload regression suites passed
3,929 tests with 93 skips. Skips require external Redis or optional integration
dependencies. Tests use real Langfuse 4.14.4 in-memory exports. An independent
review found no actionable defects. The repository harness and architecture
ratchet passed with zero new boundary violations.

Implementation is available in ready
[PR #3196](https://github.com/ai-shifu/ai-shifu/pull/3196), with main unmerged.
GitHub CI was in progress at publication; frontend tests and GitGuardian had
passed. This plan's scope is the verified implementation and reviewable PR.

The existing shared virtual environment has markdown-flow 0.3.4 instead of the
required 0.4.2. Tests used an isolated `/tmp` overlay of the exact pinned package;
no shared environment or dependency manifest changed. The required Ruff 0.16.5
also uses an isolated tools overlay.

Deployment and remote Langfuse readback remain outside this change. Both the
worktree and source checkout have empty Langfuse credentials; no live export
was attempted. Local SDK export is not remote acceptance.

## Context and Orientation

The shared SDK facade is `src/api/flaskr/api/langfuse.py`; MarkdownFlow trace
lifecycle is in `langfuse_markdownflow.py`. Course and Profile presentation
policies stay in their service-local `langfuse_tracing.py` modules. Legacy
learning tracing is in `service/learn/context_v2.py`. The durable contract is
`docs/design-docs/langfuse-trace-association.md`.

## Plan of Work

Add deterministic session trace identity, defer course initialization until its
session callback, preserve early execution metadata, and update legacy runtime
creation. Exercise independent requests and sessions through real SDK exports.

## Concrete Steps

Run focused shared/course/Profile/legacy pytest checks, then the surrounding
service and Langfuse suites. Run repository harness, architecture checks, tool
availability, and the required pre-commit gate. Inspect the final diff and
publish the focused branch as a ready PR without merging main.

## Validation and Acceptance

Different request ids for one session must export the same trace id with unique
request observation ids. Different users and reset sessions must stay isolated.
Each model/tool remains under its request's agent observation. Request IO,
outcomes, and early progress identifiers must remain accurate. A failed SDK
operation must not affect business behavior. Remote telemetry acceptance, if
available, requires readback rather than successful submission alone.

## Idempotence and Recovery

Session identity is derived without storage or process-local caching. Repeated
finalization stays idempotent. SDK failure uses existing no-op observations.
Reverting the change restores request-based trace ids for later requests.

## Interfaces and Dependencies

`get_session_trace_id(session_id, user_id=...)` derives the shared trace id.
MarkdownFlow tracing can defer creation until session binding; host callback
signatures and the portable engine are unchanged. Langfuse stays at 4.14.4.
