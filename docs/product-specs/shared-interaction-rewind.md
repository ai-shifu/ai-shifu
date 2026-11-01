---
title: Shared Interaction Rewind
status: implemented
owner_surface: shared
last_reviewed: 2026-11-01
canonical: true
---

## Behavior

Published learning, full-course draft preview and editor Debug share the same
checkpoint planner in `flaskr/service/learn/agent/rewind.py`. The learner and
Debug interfaces share `src/web/src/lib/chat-interaction-rewind.ts` for locating
an interaction, replacing its displayed answer and truncating later items.

Changing an earlier answer keeps that question and its preceding teaching,
restores the checkpoint before its old answer was received, and supplies the
new answer. Later teaching and session answers are discarded, and teaching
pauses normally at the next interaction. Multiple questions in one turn use
exact interaction ownership, rather than matching variable names or guessing
from the generated block alone.

A confirmation can be opened while output is streaming, including the wait
before its first content arrives. Repeating the same answer during that wait
does not start another request. Cancelling changes nothing. Confirming replaces the active output, and late events or saves from
the old Debug request cannot overwrite its replacement. A stopped or failed
answer edit retries the same owned question and the newly submitted answer.

## Storage and compatibility

The planner and engine are shared; storage ownership remains separate. Learner
progress is durable, full-course preview belongs to its draft generation, and
editor Debug uses an expiring cache scoped to teacher, course, lesson and Debug
session. Debug checkpoints never become learner progress or profile writes.

Editor Debug accepts optional `reload_element_bid` with the existing
`reload_generated_block_bid` and `user_input` fields. Exact interaction plus
input selects answer editing. Existing content regeneration continues replaying
the original input of the selected content turn. Ordinary answers have no reload
anchor. The SSE envelope and terminal-event contract remain unchanged.

Edited scripts start a fresh Debug session. Expired sessions, unknown controls,
missing checkpoints and old cache entries without exact interaction ownership
report the existing localized errors; they do not silently restart the lesson.
There is no database migration. Debug cache entries expire after 30 minutes.

## Verification and analytics

Regression tests cover both storage adapters, shared list transitions, repeated
and same-turn questions, new-answer propagation, future-state removal, running
stream replacement, retries and compatibility with content regeneration.
See [frontend product analytics](../references/frontend-product-analytics.md)
for the separate Debug answer-edit attempt/result contract.
