---
title: Shared Interaction Rewind
status: implemented
owner_surface: shared
last_reviewed: 2026-11-09
canonical: true
---

## Behavior

Published learning, full-course draft preview and editor Debug share the same
checkpoint planner in `flaskr/service/learn/agent/rewind.py`. The learner and
Debug interfaces share `src/web/src/lib/chat-interaction-rewind.ts` for locating
an interaction, replacing its displayed answer and truncating later items.

Changing a submitted answer, including the last question of a completed
lesson, keeps the question and preceding teaching. The new answer runs from
the checkpoint before the old one, replacing later teaching and session
answers. Ordinary learning ignores repeats of a settled answer. After a failed
edit, learners can retry the edit or submit the original answer again.

An ordinary classroom can edit a control rendered from narration when the
adjacent saved turn and active session prove which message answered it.
The new answer remains a message and the replacement appears on the original
control after reload. Missing or ambiguous evidence prevents the edit.

Editor Debug can confirm an answer change while output is streaming, including
before its first content arrives: it saves the accepting checkpoint before output.
Repeating the same answer during that wait does not start another request.
Published learning and full-course draft preview retain their existing guard for
resubmitting the current question before output, when their accepting checkpoint
is not yet durable. They still call the shared interaction and rewind rules,
with their existing selection, status-row handling and replay behavior preserved.
Cancelling confirmation changes nothing. Confirming replaces the active Debug
output, and late events or saves from the old request cannot overwrite its
replacement. A stopped or failed answer edit retries the same owned question
and the newly submitted answer.

## Storage and compatibility

Ordinary draft and published classrooms use the same durable lesson attempt
and its source version. Editor Debug uses an expiring cache scoped to teacher,
course, lesson and Debug session. Debug checkpoints stay in that cache.

Editor Debug accepts optional `reload_element_bid` with the existing
`reload_generated_block_bid` and `user_input` fields. Exact interaction plus
input selects answer editing. Existing content regeneration continues replaying
the original input of the selected content turn. Ordinary answers have no reload
anchor. The SSE envelope and terminal-event contract remain unchanged.

Debug requests include an increasing `request_generation` within their session.
Admission rejects older or duplicate generations before they can replace the
active request, including when HTTP requests arrive out of order. The saved
session retains the highest generation for its lifetime. Existing clients can
omit the field until their session admits a sequenced request; learner requests
and persistence do not use this Debug-only contract.

An answer to the current question can continue under an edited draft, retaining
the existing main behavior. Starting without an answer or targeting an earlier
question after a draft edit starts a fresh Debug session. Expired sessions, unknown controls,
missing checkpoints and old cache entries without exact interaction ownership
report the existing localized errors; they do not silently restart the lesson.
There is no database migration. Debug cache entries expire after 30 minutes.

## Replaying pending questions

A classroom lesson can redisplay a pending question while the learner answers
another question from the same turn. Durable turn records associate emitted
controls and accepted input with the engine's question identities. History
shows the original control and its answer, and attaches follow-ups from later
displays to that control in the page, event replay and model history. This
requires evidence that the same question was still pending in the same learner,
course, lesson and progress record. Distinct questions remain separate even
when their text matches. Records with insufficient evidence keep their controls.

## Verification and analytics

Regression tests cover both storage adapters, shared list transitions, repeated
and same-turn questions, new-answer propagation, future-state removal, running
stream replacement, retries and compatibility with content regeneration.
See [frontend product analytics](../references/frontend-product-analytics.md)
for the separate Debug answer-edit attempt/result contract.
