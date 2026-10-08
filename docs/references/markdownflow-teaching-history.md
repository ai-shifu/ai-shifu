---
title: MarkdownFlow teaching history projection
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# MarkdownFlow teaching history projection

AI-Shifu 2.0 teaching and previews enable
`Engine(teaching_history_compaction=True)`. Portable engines default off and
have no `read_teaching` tool or related instructions unless explicitly enabled.

## Request projection and original evidence

Before a teaching run, after initial memory and recall-result projection, replace
older long assistant `TextPart` content with deterministic exact excerpts. Only
text larger than 4096 JSON-escaped UTF-8 bytes qualifies, and a replacement must
be smaller. The marker includes `status: teaching_excerpt`, an opaque reference,
the original character count, its first 256 and last 128 Unicode characters,
and a host-authored notice. It is incomplete historical evidence, not a semantic
summary, new instruction or learner request.

Keep the two most recent teaching turns complete. A user prompt or `interact`
return starts a teaching turn; without two later boundaries no older text is
projected. Keep all request parts, learner messages and answers, call arguments,
IDs, metadata, retries, ordering and message counts. Current-run tool loops are
never projected. Existing repeat and finish guards still inspect originals.

Keep original `Session.messages` and append only new run messages. Projection
never replaces the saved prefix, rendered classroom elements, checkpoint counts
or memory values. There is no persisted summary, new session field or process
cache. Database/session size is not reduced. Historical assistant text follows
the same evidence/retention contract as the original model history; a deleted
memory value is not thereby erased from past teaching. Historical teaching must
not be treated as a current authorized memory snapshot.

## Exact original reads

`read_teaching(reference, offset=0)` reads only original text that was projected
for this run in this lesson's session. No arbitrary history lookup, key discovery,
database access, cross-learner/course/lesson query or memory write is available.
References bind original message/part positions and SHA-256 content. Rewinding
recomputes the snapshot; a discarded or replaced future text cannot alias the
same position. Concurrent sessions on one Engine have separate dependency maps.

Successful results contain `status: found`, `reference`, `offset`, exact `text`
and `next_offset`. Offsets count Unicode characters. Follow `next_offset` until
null to reconstruct the complete text, including code, escaped JSON and Unicode.
The entire result is at most 8192 UTF-8 JSON bytes. Invalid offsets return
`invalid_offset`; unknown references return `unavailable`. Finished lessons
retain the existing terminal tool guard. Read only relevant missing details;
unavailable content must not be guessed or repeatedly requested.

Older uniquely paired successful read results may themselves be projected to
`teaching_read_compacted` with the original reference. Require the exact known
result shape and verify its text/offsets against the current original source.
Ambiguous, malformed, future, unsuccessful, small and recent results remain whole.
This prevents historical re-reads from recreating the original input growth.

## Budgets, recovery and remaining scope

The gateway continues checking complete messages and tool definitions before
**every** provider call against the existing 256 KiB application byte budget.
A current read can fit its per-result limit and still exceed the total request
budget; that call is refused before provider I/O. Long scripts, answers, recent
turns, many short teaching parts and current loops can still exceed the budget.
No provider token-limit guarantee or universal overflow recovery is added.

Failure/reload/retry and rewind derive the projection again from original saved
messages. Disabling host opt-in restores full request text without migrating data.
No summarization model call, schema, environment flag, dependency or frontend/SSE
change is added. Reads may add existing model tool-loop calls and cost, so full
teaching-quality, cache and cost observations remain separate acceptance work.
Semantic summaries, stored-data compaction and cross-course shared writing also
remain separate increments. Production enablement stays separately controlled.
