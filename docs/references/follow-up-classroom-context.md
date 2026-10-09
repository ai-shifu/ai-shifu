---
title: Follow-up Classroom Context
status: implemented
owner_surface: learner
last_reviewed: 2026-10-09
canonical: true
---

# Follow-up Classroom Context

Text and Live follow-up questions remain separate conversations anchored to a
selected classroom element. LLM and external-provider prompts use the shared
`learn/follow_up_context.py` builder. Live keeps its independent voice instructions;
it does not inherit text Course Prompts. Explicit memory authorization remains
[the course-reference contract](course-memory-references.md).

For a persisted anchor, history consists of recent teaching and learner answers
before its generated block, the selected element's exact text, and recent
ASK/ANSWER sidecars belonging to that anchor. This includes the visible 2.0
conversation persisted through the existing generated-block bridge. It does not
read raw agent sessions, tool calls or generation prompts. For 2.0, the existing
versioned turn record supplies only its submitted `values` list through the rewind
codec; checkpoint memory, pending tools and other configuration never become model
messages. That input precedes its turn's teaching, including the selected anchor's
own turn. Older formats and malformed value lists yield no learner text.
The anchor's full generated block is excluded because it can contain later text.
Later blocks and sidecars belonging to other anchors are excluded as well.

Prior classroom rows must be active and undeleted and match the anchor's learning
attempt, learner, course and lesson. Only content blocks become assistant messages
and legacy interaction blocks become learner messages. 2.0 submitted values also
become learner messages in their original turn order. Empty content is omitted. A
resolved anchor from another learning attempt yields no history. If the anchor's
active generated block is absent, only the selected text and its own sidecar are
used; no latest-block fallback broadens that anchor's context.

The existing history limit is shared between prior classroom turns and sidecar
messages. Recent sidecar messages take priority, then remaining slots retain the
most recent preceding classroom rows. The selected nonempty anchor remains an
additional message, including when the limit is zero. Legacy embedded ASK history
still works; canonical sidecars take precedence. Calls without a resolved element
retain the existing generated-block fallback for legacy compatibility.

Context reads do not mutate classroom history, progress, memory or agent sessions.
Existing provider routing, SSE, billing and persistence paths remain in use.
Semantic recall, transcript compression and teaching-quality acceptance are
separate work; this bounded context does not promise the entire lesson transcript.

## Current course memory in 2.0

When the deployment selects 2.0, the existing memory facade also loads course notes
without variable definitions, alongside defined variables and registered system
fields. An explicit resolved snapshot, including an empty snapshot, prevents a
second read. Text dispatch opts into the same reader before handing off its snapshot;
Live loads its snapshot when building a new conversation with independent voice rules.

Both LLM and external-provider prompts receive a separate untrusted JSON data block,
even when an author supplied a follow-up prompt without the Course Prompt slot.
Its encoded UTF-8 payload is at most 16,384 bytes. Complete values are selected in
snapshot order; oversized values are omitted, never truncated or deleted. Omitted
keys remain unknown to that request. This bounds only the added memory block, not
the pre-existing course instructions or conversation budget. JSON string keys and
values escape angle brackets, ampersands and braces to preserve host boundaries.

Current facts must not replace historical quotations. This path reads memory only;
it cannot authorize new writes or restore deleted notes. Fresh requests observe
stored updates and deletions. An ongoing Live provider session retains its creation
snapshot. Legacy 1.0 behavior and cross-course custom-memory isolation are unchanged.

## Provider delivery boundary

The default LLM and Live builder consume this memory snapshot. Dify serializes the
shared provider messages into its outbound query, and Get Biji uses the contextual
LLM synthesis factory after retrieval. Existing Coze, Coze Workflow and Volc
adapters discard provider messages; their provider-only answers do not receive
course memory through this increment. Provider-specific context delivery remains
separate follow-up work, preserving the existing configured knowledge interfaces.
The builder supplying a message list is not proof that every adapter transmits it.
