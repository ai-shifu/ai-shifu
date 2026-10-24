---
title: MarkdownFlow Memory Recall
status: implemented
owner_surface: learner
last_reviewed: 2026-10-13
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
Session-only working notes and historical conversation are preserved.
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
not classroom text. Recall does not change initial 32768-character memory projection,
exact script substitutions, persistence, usage limits or the
[256 KiB complete model input budget](markdownflow-input-budget.md).
Repeated tool results still consume that total budget. This increment provides exact-key
retrieval, not semantic search, historical conversation compression or automatic recovery
from oversized overall inputs. Shared writes and independent teaching-quality acceptance
remain separate work.


## Unavailable authored values

For script/brief reads outside fenced code, an absent, null or empty-string
learner value is represented in the initial host prompt by
`<unavailable_learner_value name="..." />`, with an escaped name. It is metadata,
not a learner fact or display text. The syntax guidance also covers unresolved
read templates in older host prompts: use the author's missing-evidence wording,
or omit that personal claim, including inside generated visuals. Do not invent
values, expose internal names or add an unauthored interaction to obtain them.

Existing complete values, including zero and false, keep exact substitution even
when omitted from the bounded memory block. Names collected in this lesson still
wait for its actual answer; earlier stored answers cannot prefill them. Missing notation in authored verbatim syntax examples and fenced
code/templates/CSS/JavaScript remains literal source content; known personalization
in verbatim text retains its existing substitution behavior. This does not rewrite
generated code or classroom output after generation.

Nickname and deletion refresh match each known host section independently in
both historical and current formats, then use the current rendering. Unrecognized
history, later learner requests, tool returns and already displayed teaching stay
unchanged. No memory placeholder is persisted as a profile value; course scope,
recall/write permissions and all input/request/retry limits remain unchanged.
Native SDK tests establish input/policy delivery only; actual-model and sim checks
must separately verify learner-visible behavior.
