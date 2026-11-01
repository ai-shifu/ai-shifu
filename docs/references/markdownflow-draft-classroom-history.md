---
title: MarkdownFlow Draft Classroom History
status: implemented
owner_surface: learner
last_reviewed: 2026-11-03
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

## Editor Debug sessions

Editor Debug supports new runs, interaction answers and its existing TTS
controls. It does not offer content regeneration or a regeneration Retry action.
The preview DTO rejects content-only reload requests before usage admission or
model execution. An anchored request must include an exact `reload_element_bid`
and a nonempty answer; `reload_generated_block_bid` optionally identifies that
interaction's owning turn. Direct Debug runtime calls enforce the same boundary.
Learner and full-course draft classroom rewind remain separate supported flows.

Starting Debug again creates a fresh session. Answering the current interaction
continues the session. After confirmation, editing an earlier answer preserves
teaching before its accepting turn and replaces the affected suffix with output
based on the new answer. Exact interaction ownership distinguishes questions
sharing a turn. A failed or stopped answer edit retains an answer-only Retry
control, its original answer and the preserved prefix. Later answers and normal
continuations do not resend the edit anchors. A changed draft follows the
existing frontend confirmation/restart path; direct ordinary Debug continuation
can retain its engine conversation under an edited script.

Editor Debug uses a separate 30-minute cache, scoped to the authenticated teacher,
course, lesson and browser-generated Debug run ID. Its payload keeps the script
hash, serialized engine session, request generation and turn checkpoints with
question/interaction ownership needed for answer editing. Content-regeneration
retry mappings are no longer read or saved; the next normal save drops those
legacy fields. No database migration or published learner state change is needed.
An old session without usable answer checkpoints can continue normally, but
cannot selectively edit an earlier answer until restarted.

Answer edits restore the checkpoint's user-memory snapshot. Echoed frontend
variables cannot reintroduce discarded future answers. `debug_variables` SSE
messages replace the variable snapshot before replacement output and at its DONE
boundary. Old SSE and audio callbacks cannot update a replacement run.

Each Debug store binds its lock, request token and session state to one backend.
When Redis is configured, every operation uses strict Redis; an outage never
switches to process-local state. Without Redis, the explicitly process-local
development cache remains available. Temporary cache or lock failures retain
`server.learn.debugServiceUnavailable` (business code `4023`) and the request
language even after nested streaming contexts clear translation state.

Each request claims a fresh cache token, and a short write lock guards the token
check and session save together. Increasing client request generations fence
late admission as well as late writes; a superseded request cannot overwrite the
newer session. If a save succeeds before lock release fails, the saved engine
session remains committed; no rollback is claimed. The active answer-edit event
family and retired content-regeneration family retain their separate meanings in
the [frontend analytics reference](frontend-product-analytics.md).
