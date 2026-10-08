---
title: Compact older long teaching with exact source reads
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Compact older long teaching with exact source reads

## Purpose / Big Picture

Reduce repeated long teaching input while preserving complete original evidence.
This deterministic increment retains exact excerpts and provides bounded original
text reads; semantic summaries and persisted-data compaction remain separate work.
The durable contract is [Teaching history](../../references/markdownflow-teaching-history.md).

## Progress

- [x] 2026-10-08 04:37 UTC: Verify merged PR 3040 and inspect engine projection,
  original-message persistence, tool loops, retry, rewind and host activation.
- [x] 2026-10-08 04:39 UTC: Add request-only excerpts, position/content references,
  bounded exact original reads, old read-result projection and explicit host opt-in.
- [x] 2026-10-08 04:43 UTC: Real engine/gateway/SQLite and failure/rewind acceptance
  passed; full learning/profile suite: 2754 passed, 1 skipped, 4 subtests passed.
  Add 35 cases. Negative mutations of projection, original evidence, recent-turn
  protection, page bounds and host wiring fail 5 / 1 / 23 / 3 / 3 cases; restore bytes.
  Local isolated probe passes 117 checks and 22 runtime hashes, without provider
  calls/shared writes. Representative teaching projection: 57792 input bytes.
- [x] 2026-10-08 04:45 UTC: Developer-tool check and all repository gates passed.
- [ ] 2026-10-08 04:39 UTC: Publish one open PR, verify sim including real model,
  reply to every independent AI opinion and verify final CI. Main merge is manual.

## Surprises & Discoveries

Rewind restores the history by original message count. A persisted summary would
invalidate that evidence unless new snapshot semantics were introduced. Request-only
projection and content-bound references avoid a new cache and its invalidation.

## Decision Log

- 2026-10-08: Start with deterministic exact excerpts plus read access, avoiding an
  unverified semantic summary or extra summarization call. This is a long-teaching
  compression increment, not completion of semantic summary or memory milestones.
- 2026-10-08: Keep the two most recent teaching turns and every user/interaction
  answer whole. Only older response text larger than 4096 JSON-escaped UTF-8 bytes
  qualifies. Keep all calls, metadata, order, message counts and current tool loops.
- 2026-10-08: Read only eligible original text in this run's session snapshot.
  References bind position and SHA-256 content; pagination uses Unicode offsets and
  limits the full result to 8192 UTF-8 JSON bytes. No listing or arbitrary DB access.

## Outcomes & Retrospective

Implementation and local acceptance pass. Long teaching alone can exceed the input
budget without projection and fit afterward; exact-bound and one-byte-over checks
also cover the tool loop. SQLite host preserves originals and invalidates future
references on rewind. Final repository gates passed. Publication, sim and reviews remain pending.

## Context and Orientation

`engine/teaching_history.py` projects TextPart values and owns `read_teaching`.
Engine creates a per-run dependency snapshot, retains original history and enables
reads only with compaction. The host factory opts in for teaching/previews. Gateway
input budgets, host memory authorization, storage and rewind remain existing paths.

## Plan of Work

Add projection and reads, validate exact evidence and bounded requests, run full
learning/profile and gates, publish/synchronize sim, verify real provider behavior
and inspect/reply to all AI opinions before handoff.

## Concrete Steps

Run the teaching history unit/lifecycle tests, real gateway and durable host tests,
then all learning/profile tests. Run targeted negative mutations and restore bytes.
Stage new docs/prompts before regenerating indexes. Check developer tools and all
pre-commit gates, publish the PR, synchronize its tree to sim and verify replicas.

## Validation and Acceptance

Old long teaching alone can exceed the existing gateway budget; projection reduces
it without changing saved evidence. Exact original reads reconstruct Unicode/code
and stay within result and total-request budgets. Two recent turns, long answers,
current tool results, failure/reload/retry and pending questions remain complete.
Separate sessions and rewound/replaced future text cannot resolve each other's
references. Projection/read markers never become classroom elements or memory writes.
Portable defaults remain off; no schema, environment, dependency or frontend changes.

## Idempotence and Recovery

Derive each snapshot from current original messages. Do not retain a process-global
mapping or session cache. Rewind/retry recompute references. Disable host opt-in to
restore full model history without any stored-data migration.

## Interfaces and Dependencies

Add Engine(teaching_history_compaction=False), project_teaching_history(messages)
and read_teaching(reference, offset=0). Reuse existing tool limits, gateway, provider
and SSE paths. No new dependency or persistence field.
