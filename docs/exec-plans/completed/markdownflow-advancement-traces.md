---
title: MarkdownFlow Advancement Traces
status: completed
owner_surface: backend
last_reviewed: 2026-10-27
canonical: false
---

# MarkdownFlow Advancement Traces

## Purpose / Big Picture

Map a complete interactive document execution to a Langfuse Session, and each
admitted start, answer, continue, regenerate, or standalone Profile operation to
its own Trace. Retain the verified fault isolation and observation hierarchy
from PR #3196. The canonical contract is
`docs/design-docs/langfuse-trace-association.md`.

## Progress

- [x] 2026-10-27 CST: Verified the open PR, fetched remote main and feature branch, and inspected admission, replay, automatic turns, and legacy progress boundaries.
- [x] 2026-10-27 CST: Chose advancement-owned trace IDs independent of HTTP request IDs; preserved existing execution session IDs.
- [x] 2026-10-27 CST: Implemented modern/legacy advancement identity and retained fault isolation; related suites passed 4,221 tests with 93 skips.
- [x] 2026-10-27 CST: Updated the canonical design, marked the earlier identity plan superseded, and passed tool availability, architecture, repository harness, and all-files pre-commit gates.

## Surprises & Discoveries

A single course response may run multiple engine turns before waiting for the
learner. Separate admitted operations can also share one HTTP request ID.
Returning to request-derived trace IDs would merge those operations. Legacy
streams can switch document progress sessions within one response and need a
new trace when that happens. Profile rejects exact replays before tracing.

## Decision Log

- Allocate a fresh trace ID once when an advancement coordinator is admitted,
  before producer-thread execution. Request IDs remain correlation metadata.
- Reuse that trace through automatic engine turns, model calls, and nested
  helpers until waiting, completion, or failure. Standalone helpers own a trace.
- Keep native course/Profile session IDs as the Langfuse Session identity;
  restarting a document creates a new Session.
- Preserve deferred session binding, authoritative progress selection, early
  failure observations, no-op SDK fallbacks, stable usage correlation, idempotent
  finalization, and original exception/database cleanup behavior.
- This plan covers implementation and local acceptance. Publication and live
  CI/review convergence are tracked on the existing PR #3196. No main merge or
  deployment is authorized by this plan.

## Outcomes & Retrospective

The final related learning, Profile, Langfuse, payload, and LLM suites passed
4,221 tests with 93 skips for external Redis or optional integration paths.
An independent review verified operation boundaries and ID capture. It found
and verified a correction for child-SDK failure: nested no-op observations must
retain the owning advancement ID, just like root-creation fallbacks. Focused
coverage proves all four child-creation APIs retain model usage correlation.

The earlier session-trace plan records a superseded identity decision; its
fault-isolation work remains. All local delivery gates passed, and independent
review found no remaining actionable defect. Local implementation acceptance is
complete. The existing PR remains the publication and live CI/review record.

This work does not deploy services or rewrite historical traces. Existing local
Langfuse credentials are empty, so remote telemetry readback remains a separate
acceptance step; real-SDK in-memory export is not a deployed-path verification.

## Context and Orientation

`flaskr/api/langfuse.py` owns ID allocation and the SDK facade.
`flaskr/api/langfuse_markdownflow.py` owns advancement lifetime for Course and
Profile. Their service-local tracing modules retain naming/output policies.
Legacy course/preview lifetime is in `service/learn/context_v2.py`.

## Plan of Work

Replace session-derived trace identity with advancement allocation, then update
all identity assertions. Prove separate operations in one execution retain one
Session but distinct Traces, even with the same HTTP ID. Keep automatic turns
and nested transformations in the same Trace and preserve the failure suites.

## Concrete Steps

Use the existing checkout and dependency overlays with manifest-pinned
markdown-flow 0.4.2 and LiteLLM 1.106.2. Run focused real-SDK/legacy suites,
broaden to related learning/Profile/LLM tests, and run tool availability,
repository harness, architecture, and all-files pre-commit gates. Update the
existing PR title/description after publishing the verified implementation.

## Validation and Acceptance

Two real advances of one document have the same `session.id` and different
trace IDs. Multiple automatic turns and generations inside one advance share
one trace. Same HTTP IDs cannot merge distinct advances. A document reset and
legacy cross-document transition remain isolated. Exact replay creates no
execution observations or charges. SDK failure cannot stop valid teaching or
change original business errors/database cleanup. No-op generations retain
their owning advancement's trace ID.

## Idempotence and Recovery

Allocate IDs without remote calls or persistence migrations. Finalization
remains idempotent. Existing traces are not rewritten; old and new observations
continue to expose their native execution Session. Rollback changes only future
trace grouping, while verified fault-isolation fixes remain independent.

## Interfaces and Dependencies

`create_advancement_trace_id()` replaces the session trace-ID helper. Coordinator
instances retain the allocated ID through deferred binding and all child
operations. No DTO, engine, session-storage schema, dependency, or public HTTP
contract changes are required. Langfuse remains 4.14.4.
