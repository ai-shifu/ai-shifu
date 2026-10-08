---
title: Follow-up Classroom Context
status: implemented
owner_surface: learner
last_reviewed: 2026-10-08
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
read raw agent sessions, tool calls, generation prompts or rewind configuration.
The anchor's full generated block is excluded because it can contain later text.
Later blocks and sidecars belonging to other anchors are excluded as well.

Prior classroom rows must be active and undeleted and match the anchor's learning
attempt, learner, course and lesson. Only content blocks become assistant messages
and interaction blocks become learner messages. Empty content is omitted. A
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
