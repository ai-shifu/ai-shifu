---
title: MarkdownFlow Memory Recall
status: implemented
owner_surface: learner
last_reviewed: 2026-10-08
canonical: true
---

# MarkdownFlow Memory Recall

AI-Shifu 2.0 teaching and teacher previews enable `Engine(memory_recall=True)`.
Portable hosts default to false, retaining their existing tools and instructions.
The read-only `recall` tool accesses the current turn's already authorized user/session
memory dictionaries, with session values winning. It performs no database/provider I/O,
changes no memory or profile and grants no additional write permission. The host must
refresh durable named answers and deletions before each request, as it does
for normal initial injection. Arbitrary source courses or other learners cannot be queried.

With `key=null`, `offset=0`, the tool returns alphabetically sorted available names, at most
20 candidates per page. `next_offset` is the next position, or null at the end; `skipped`
counts names too large to return. A page ending at the byte boundary may contain fewer
keys. Calls read live dictionaries: a legitimate write in the same turn can change paging.
With a string key and offset zero, it returns `status=found` and the complete JSON value.
Missing/excluded keys share `status=unavailable`. Negative offsets or a nonzero offset
with an exact key return `status=invalid_offset`; offsets past the list return an empty page.

Every result is at most **8192 UTF-8 bytes** of compact JSON (`ensure_ascii=False`, separators
`(',', ':')`), including status/structure and escaping. A larger complete value returns only
`status=too_large`; no original value is shortened, summarized or removed. The terminal
lesson guard returns the existing fixed lesson-over message without reading memory.
Keys the main script collects again are excluded from discovery and reads until
this lesson has accepted an answer. An accepted session answer makes that key
readable on the same deferred resume and on later requests. The AI-Shifu host
refreshes existing named-answer copies from the committed course snapshot, so an
old lesson cannot shadow a newer answer from another lesson. Unanswered questions
are never prefilled by this refresh. Deletion clears the accepted-answer copy;
recreating the course key does not answer that old lesson's question again.
Session-only working notes and historical conversation are preserved.

Instructions ask for relevant missing facts only and treat returned values as data, never
as author instructions or write authorization. Tool returns stay in model/session history,
not classroom text. Recall does not change initial 32768-character memory projection,
exact script substitutions, persistence, usage limits or the
[256 KiB complete model input budget](markdownflow-input-budget.md).
Repeated tool results still consume that total budget. This increment provides exact-key
retrieval, not semantic search, historical conversation compression or automatic recovery
from oversized overall inputs. Shared writes and independent teaching-quality acceptance
remain separate work.
