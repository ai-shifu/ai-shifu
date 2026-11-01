---
title: MarkdownFlow Draft Classroom History
status: implemented
owner_surface: learner
last_reviewed: 2026-11-01
canonical: true
---

# MarkdownFlow Draft Classroom History

Full-course draft previews (`preview=true` in the classroom) use their own
engine session and presentation history. They do not create published learner
progress or content blocks. Editor Debug retains its independent transient
session/snapshot store.

The host reserves a preview generation before teaching starts. Its existing
`LearnAgentSession.session_data` JSON contains a versioned
`ai_shifu_preview_presentation` sidecar with exact adapter run IDs, rendered
question ownership and accepted answer display values. The engine ignores this
host metadata; the product session store preserves it when replacing engine
state. No database or engine schema migration is required.

Preview history reads only active-generation `LearnGeneratedElement` rows
matching the authenticated user, course, lesson and registered run IDs. It uses
the shared final-element and audio normalization, preserving request order and
stream order within each request. It never reconstructs teaching from raw model
messages or falls back to published progress. Accepted answers populate the
original question; repeated requests for the same pending question do not append
duplicate controls.

Ownership records each emitted question in order within its turn block, so
several deferred questions sharing a block retain separate controls and answers.
Follow-up ASK/ANSWER runs remain independent; history includes only exchanges
whose exact anchor belongs to the active generation, using the existing anchor
attachment and ordering contract. Restart excludes their old anchors too.

The draft-update comparison uses the generation's fixed creation time. Saving
another turn does not imply that a running session adopted an edited script.
Scriptless lessons are checked before reserving agent state and retain 1.0
fallback history, catalog status and restart behavior.

An empty continuation of a pending or completed draft replays the committed
presentation without another model request. This also covers a browser refresh
that read history before the prior stream committed its final elements. Other
continuations retain the existing engine behavior.

The catalog and stream report the draft generation's activity/completion so the
existing restart action is available even when the teacher has no published
learning progress. DELETE records accepts explicit `preview_mode=true`, requires
preview permission, and retires only the draft generation. Late writes into that
generation are refused before staging memory or session changes. Published
restart retains the legacy behavior for existing callers, including retirement
of their preview session; it is not a reciprocal isolation change.

Existing drafts without this presentation sidecar restart once on their next
run. Unscoped historical elements cannot safely be assigned after the fact.
Unreadable engine state also restarts its presentation together. No published
learning records are reset by this compatibility path.

This repairs restoration and restart behavior. It does not guarantee that a
model always follows an author's teaching order. Existing reset analytics keeps
excluding preview traffic; no learner reset event is emitted for a draft reset.
Each new preview turn also records the existing versioned host checkpoint and
original inputs in presentation metadata. Editing an accepted answer restores
the checkpoint of its accepting turn; regenerating teaching restores that
teaching turn and replays its original inputs. Exact interaction element IDs
distinguish several questions in one block. The first unanswered pending
question remains a normal submission.

Planning accepts only anchors owned by the current authenticated user, course,
lesson and active draft generation. Superseded element rows, question ownership
and displayed answers retire with the guarded session save in one transaction.
Earlier teaching, controls and accepted display values remain. Engine checkpoint
answers cover only unconsumed deferred input, so display retirement follows the
retired host accepting turns instead. Follow-ups anchored to retired teaching
are excluded on reload. A failed save rolls retirement back. Reset invalidates
late writes, and stale plans cannot retire a later committed turn. The fixed
generation timestamp remains unchanged.

Old history without the required checkpoint reports rewind unavailable and
retains its existing history; restart is the recovery. Editor Debug remains
independent. This feature does not roll back prior billing or change existing
profile/memory admission rules. Preview rewind analytics uses its own start and
terminal-result family, as defined in the frontend analytics reference.
1.0 runtime behavior, engine fallback and code remain available.

## Editor Debug sessions and legacy regeneration compatibility

The current editor Debug panel supports new Debug runs, interaction answers and
the existing TTS controls. It no longer offers per-element content regeneration
or a regeneration Retry action. Its frontend hook does not accept or send
reload anchors. Starting Debug again creates a fresh session; answering the
current interaction continues the session, and resubmitting an earlier answer
retains its confirmation and whole-session restart behavior. Full-course draft
classroom rewind remains a separate supported flow.

Each Debug store binds its lock, request token and session/checkpoint state to
one backend. When Redis is configured, all of those operations use strict Redis;
an outage never switches reads or writes to process-local state. Without Redis,
Debug retains an explicitly process-local development cache. These choices do
not change the shared cache provider's fallback behavior for other consumers.

Temporary cache or lock failures use `server.learn.debugServiceUnavailable`
(business code `4023`) rather than an expired-session or classroom-reset error.
The preview SSE error preserves that code and the request-language message,
including after nested streaming contexts clear translation state. The frontend
stops the failed request and retains its existing business-error display. If a
save succeeded before lock release failed, its checkpoint and compatibility
retry mapping remain committed; no rollback is claimed.

Editor Debug uses its separate 30-minute cache, scoped to the authenticated
teacher, course, lesson and browser-generated Debug run ID. Its cached sidecar
records each turn's checkpoint and original inputs alongside the engine session;
it does not reuse classroom presentation ownership or published learner state.

The backend preview endpoint retains `reload_generated_block_bid`, turn
checkpoints and retry mappings for compatibility with older clients. This
compatibility path requires the same `debug_session_id` and unchanged script.
Several rendered elements can share one engine turn, so a legacy reload
restores the selected generated block's checkpoint and original input, then
replaces that entire turn and its successors through the normal teaching flow.
Checkpoints for the replaced suffix retire when replacement state is saved.
Earlier checkpoints remain available to compatible clients.

The cache keeps one mapping from a requested logical target to its first
replacement block. Only that mapping, while its replacement remains active in
the same Debug session and script, can resolve a retired target for a legacy
retry. Ordinary subsequent turns preserve it; another regeneration replaces
it. Other retired suffix anchors remain unavailable. The current frontend has
no retry target or Retry producer.

The restored Debug memory includes the checkpoint's user-memory snapshot. The
request's echoed current variables cannot reintroduce discarded future answers.
`debug_variables` SSE messages carry a JSON-encoded variable map before replacement
output and before its DONE boundary, replacing the frontend variable snapshot.
For a legacy reload, the anchor belongs only to that request; later answers and
continuations do not resend it. Old SSE and audio callbacks cannot update a
replacement run.
Each Debug request claims a fresh cache token; a short write lock guards the
token check and session save together. A stopped request that finishes after
its replacement cannot overwrite the new session or restore retired anchors.

For compatible clients, an unknown, expired or incompatible checkpoint reports
the existing rewind or Debug-session error instead of silently restarting.
Historical cached sessions without turn checkpoints can continue normally but
require an explicit restart before a legacy reload can use checkpoints.
Whole-lesson restart creates a new Debug run, and checkpoints from a different
draft are never reused for a reload. Legacy regeneration does not refund prior
model calls or modify published learning progress. The retired frontend event
family retains its historical definitions in the
[frontend analytics reference](frontend-product-analytics.md).
