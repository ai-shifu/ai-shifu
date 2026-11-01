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

## Editor Debug sessions

Editor Debug supports new Debug runs, interaction answers and its existing TTS
controls. It does not offer content regeneration or a regeneration Retry action.
The Debug request DTO and endpoint reject removed `reload_generated_block_bid`
and `reload_element_bid` fields with a parameter error before usage admission
or generation. Direct Debug runtime calls with reload identifiers are rejected
before planning or model execution. Learner and full-course draft classroom
rewind remain separate supported flows.

Starting Debug again creates a fresh session. Answering the current interaction
continues the session; resubmitting an earlier answer retains its confirmation
and whole-session restart behavior. An answer after a draft edit resumes the
conversation under the edited script.

Editor Debug uses a separate 30-minute cache, scoped to the authenticated teacher,
course, lesson and browser-generated Debug run ID. Its payload contains only
the script hash and serialized engine session. Debug does not capture or store
per-turn checkpoints, original-input sidecars or regeneration retry mappings.
An older cached payload can still load its engine session; its next save drops
the unused sidecar fields. No database migration or published learner state
change is needed.

Each Debug store binds its lock, request token and session state to one backend.
When Redis is configured, every operation uses strict Redis; an outage never
switches to process-local state. Without Redis, the explicitly process-local
development cache remains available. Temporary cache or lock failures retain
`server.learn.debugServiceUnavailable` (business code `4023`) and the request
language even after nested streaming contexts clear translation state.

Each request claims a fresh cache token, and a short write lock guards the token
check and session save together. A superseded request cannot overwrite the newer
session. If a save succeeds before lock release fails, the saved engine session
remains committed; no rollback is claimed. Existing frontend business-error
display and normal Debug restart remain available. The retired frontend event
family retains its historical definitions in the
[frontend analytics reference](frontend-product-analytics.md).
