---
title: MarkdownFlow recall history compaction
status: active
owner_surface: learner
last_reviewed: 2026-10-08
---

# MarkdownFlow recall history compaction

AI-Shifu 2.0 teaching and author previews enable
`Engine(memory_recall=True, recall_history_compaction=True)`. Portable engines
default to no compaction. Compaction requires recall to remain available.

## Request projection

Before a teaching run, the engine projects its initial memory section and then
compacts older successful `recall` results. Only uniquely paired call/result IDs
with recognized `found` or `keys` string results qualify, and only when the marker
is smaller as a JSON-escaped UTF-8 string. Original call arguments, IDs, ordering
and result metadata remain intact. Malformed, ambiguous, small, unsuccessful,
unknown and non-string results are retained.

The most recent request carrying a user prompt or `interact` result starts the
protected teaching turn. All history from that request onward is retained, as
are all current-run requests and tool loops. With no later turn boundary, old
results are retained. Complete teaching text, learner messages, interaction
answers, memory-write calls/results and retry feedback are never shortened.

A compacted result carries `status: history_compacted` and a host-authored notice
to call recall again if needed. It is neither an actual stored value nor a learner
request. Fresh reads use the current host-authorized snapshot, including deletion,
source-reference refresh and re-collected-answer exclusion. An old successful call
does not grant current access. Existing tool/request limits still apply.

## Evidence and budgets

The projection is never substituted for the stored history. Append only new run
messages to the original `Session.messages`; original tool values, classroom
elements, canonical memory and checkpoint message counts remain available for
serialization, retry and rewind. No summary cache or new session field is stored.
Historical classroom evidence remains subject to its existing retention contract.

The gateway still checks the complete projected messages and effective tools
against its 256 KiB compact UTF-8 JSON application budget before every provider
request. Compaction neither raises that budget nor changes provider token limits.
An oversized current answer, script, recent turn or teaching transcript can still
be refused with the existing save-before-error behavior.

This is the first deterministic history-compaction increment, covering recall
payload accumulation. Semantic summaries of teaching text, stored-data compaction,
cross-course shared writing and full quality/cost acceptance remain separate work.
No extra provider call, schema migration, environment or frontend change is added.
