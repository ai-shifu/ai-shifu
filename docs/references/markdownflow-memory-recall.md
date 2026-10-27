---
title: MarkdownFlow Memory Recall
status: implemented
owner_surface: learner
last_reviewed: 2026-10-27
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
recreating the course key does not answer that old lesson's question again, even
with the same value. The session's `memory_generations` metadata records the
deletion generations its memory already reflects, so only newer deletions are
refreshed and an answer accepted after a deletion stays readable. Checkpoints
carry this metadata; sessions and checkpoints without it refresh every key that
was ever deleted.
Historical conversation is preserved. Session-only working notes are preserved,
except a note stored under a key that a deletion refresh clears.
Acceptance is recorded with a SHA-256 fingerprint of the current answer copy,
never inferred from a seeded session value. The optional `answer_hashes` session
metadata stores no duplicate answer text and needs no database schema migration.
An old session without this field can recover only current copies matching
uniquely paired successful host interaction/deferred results, including subsequent
successful writes. Unknown or mismatched copies remain session-only. A session-scope
write clears answer ownership even if its value is identical. Rewind restores the
fingerprints with the checkpoint; old checkpoints infer only from restored evidence. An authorized
user-scope correction also updates its accepted named-answer copy immediately,
so a read in the same turn cannot return the superseded value.
Regenerating a historical answer cannot make a deleted key readable again;
a new learner submission can answer it anew under the existing write policy.

Instructions ask for relevant missing facts only and treat returned values as data, never
as author instructions or write authorization. Tool returns stay in model/session history,
not classroom text. Recall does not change the initial 32768-character memory projection,
persistence, usage limits or the
[256 KiB complete model input budget](markdownflow-input-budget.md).
Repeated tool results still consume that total budget. This increment provides exact-key
retrieval, not semantic search, historical conversation compression or automatic recovery
from oversized overall inputs. Shared writes and independent teaching-quality acceptance
remain separate work.


## Authored references and existing sessions

New native sessions send the authored script and teaching brief without server-side
variable substitution. The separate memory block retains its existing budget,
referenced-key priority, collection exclusions and values. The model may interpret
`{{name}}` using that memory or `recall`; an absent value remains unknown. A value
omitted from the memory block is no longer copied into the script through a separate
substitution path. Recall's existing size limit still applies.

An existing session keeps its saved prompt and interaction history. Already-expanded
text is not restored to authored source, and old unavailable-value metadata still
means missing evidence rather than learner data or a display instruction. Existing
Profile option values and pending interactions retain their current protocol.

Nickname and deletion refresh keep new raw script/brief sections unchanged while
updating the memory block. Previously expanded prompts retain the existing refresh
path. No session schema, field name, write policy or historical-data migration is
introduced. See [literal prompts](markdownflow-literal-prompts.md) for the narrow
sending contract. SDK tests establish request/policy delivery; they do not guarantee
that a real model interprets every authored reference correctly.
