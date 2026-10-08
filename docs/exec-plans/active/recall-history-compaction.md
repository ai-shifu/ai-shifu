---
title: Compact completed memory recall history
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# Compact completed memory recall history

## Purpose / Big Picture

Prevent repeated old memory reads from consuming the model input budget while
preserving original classroom and session evidence. This first history-compaction
increment replaces only older successful recall results in the request projection.
It does not summarize teaching, truncate learner answers, or shrink persisted data.
The durable contract is [Recall history compaction](../../references/markdownflow-history-compaction.md).

## Progress

- [x] 2026-10-08 03:23 UTC: Verify merged PR 3039, inspect input budgeting,
  request projection, persistence, retry, deletion refresh and rewind contracts.
- [x] 2026-10-08 03:27 UTC: Add explicit host opt-in, conservative completed-result
  projection, and instructions for re-reading the current authorized snapshot.
- [x] 2026-10-08 03:30 UTC: Complete learning/profile regression: 2719 passed,
  1 skipped, 4 subtests passed, including every vendored engine test. Add 38 cases.
  Disable projection, overwrite original history, remove recent-turn protection,
  or disable the host opt-in: 5 / 5 / 15 / 3 targeted cases fail; restore exact bytes.
- [x] 2026-10-08 03:30 UTC: Local isolated probe passes 91 checks with no provider
  calls or shared-database writes; 50 old 6000-byte recall values fit within
  36593 projected input bytes, while all teaching text and original history remain.
- [x] 2026-10-08 03:31 UTC: Developer-tool check and all final repository gates passed.
- [ ] 2026-10-08 03:30 UTC: Publish a focused non-draft PR, synchronize sim
  and verify the deployed version.
- [ ] 2026-10-08 03:27 UTC: Audit all review surfaces, reply to each independent
  opinion and verify final technical CI. Main merge remains manual.

## Surprises & Discoveries

The host restores rewind history by original message count. Persisting a compacted
history would invalidate those checkpoints and lose evidence. The memory projection
already demonstrates the required approach: preserve originals and append only the
new run's messages. Tool loops require complete fresh recall results, so compaction
must happen once before a new teaching run, not on every gateway request.

## Decision Log

- 2026-10-08: First compact only older completed `recall` results. Retain call
  arguments, teaching, answers, memory writes, retries and the latest teaching turn.
  Semantic teaching summaries and storage compaction are separate follow-ups.
- 2026-10-08: Require an available recall tool; use the host's refreshed authorized
  snapshot for re-reads. Compaction does not grant access or write permission.
- 2026-10-08: No extra summarization provider call, persisted summary, environment
  flag, schema migration, dependency upgrade or frontend contract change.

## Outcomes & Retrospective

Implementation and local acceptance pass. New cases cover Unicode/escaping, malformed
results and ambiguous IDs, latest-turn/fresh-tool retention, full answers and failed
resumes, actual gateway budget recovery, SQLite storage, deletion/update and rewind.
Publication and deployed validation are pending.
This focused increment does not complete the entire memory milestone or recover from
large scripts, answers, current tool loops or long teaching text.

## Context and Orientation

`engine/history_context.py` copies selected `ToolReturnPart` values in request history.
`Engine.run_turn` combines it with the initial memory projection and appends only new
messages to `Session.messages`. `lesson_entry` opts in for learner and preview turns.
`GatewayModel` retains the complete messages/tools byte-budget check after projection.
Host session storage, rewind counts and classroom event production remain unchanged.

## Plan of Work

Implement conservative paired-result selection and an explicit marker, cover request
and stored evidence separately, verify fresh reads after changes/deletions, then run
all learning/profile tests and repository gates. Publish and verify sim before handoff.

## Concrete Steps

Run `tests/service/learn/agent/engine/test_history_context.py`,
`tests/service/learn/agent/test_history_compaction.py` and the factory contract tests.
Then run the complete learning/profile suite including all vendored engine tests.
Regenerate/stage documentation indexes, run developer-tool and all pre-commit gates,
commit/push, create/attach the PR, synchronize its exact tree to sim and validate pods.
Fetch reviews, inline comments and issue comments and reply to independent findings.

## Validation and Acceptance

Show that historical recall growth alone can exceed 256 KiB without compaction and
fit after projection, while the exact projected budget and one-byte-over refusal still
work. Preserve complete original values, learner input, pending interactions, retries,
latest-turn and fresh tool results, IDs/order, serialized history and rewind prefixes.
Current deletion/update authorization must govern fresh reads, with no projection
marker in classroom text or persisted tool returns. Default portable engines stay off.

## Idempotence and Recovery

Projection is deterministic and leaves input objects intact. A failed request retains
the same evidence and pending results for retry. Rewind recomputes from the restored
prefix without a summary cache to invalidate. Reverting the host opt-in restores the
previous request history without any stored-data migration.

## Interfaces and Dependencies

Add `Engine(..., recall_history_compaction=False)` and
`compact_recall_history(messages)`. Require `memory_recall=True` when enabled.
Keep pydantic-ai, the gateway/provider, existing schemas, DTOs and environment flags.
