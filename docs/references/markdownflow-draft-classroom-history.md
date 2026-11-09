---
title: MarkdownFlow Draft Classroom History
status: implemented
owner_surface: learner
last_reviewed: 2026-11-08
canonical: true
---

# MarkdownFlow Draft Classroom History

The classroom's `preview=true` URL selects a draft version of a course. The
authenticated account, course, and lesson use the same progress record and
active engine session as the published classroom. Draft-only courses can
start learning before their first publication. Publishing retains business
IDs and the script revision, so the same progress and presentation appear in
the published classroom.

The selected version supplies the outline and the content for new attempts.
Continuing, regenerating, or changing an answer uses the source retained when
the attempt began, including its pending question and exact physical course
and outline rows when known. The host stores source metadata in
`LearnAgentSession.session_data`. It checks draft access whenever a request
uses retained unpublished material. Purchasing and usage admission are
separate from attempt ownership.

Both entry points use the same history, generated blocks, checkpoints, audio
and progress. Retake locks and retires that active attempt and leaves course
memory intact. The replacement uses the version selected by the new request.
Reset receipts deduplicate retries across versions. Existing staff exemptions
and lesson reset limits are checked against the same learning record. A
learner can explicitly retire an inaccessible draft attempt from the
published classroom after losing draft access, without using the reset
allowance.

Older independent preview rows can have an
`ai_shifu_preview_presentation` sidecar with exact adapter run IDs, question
ownership and checkpoints. A compatible draft-only attempt can be attached to
the shared record after verifying its script, revision and owned snapshots.
An existing formal attempt takes precedence. Unreadable or conflicting legacy
rows are kept without splicing their engine messages into the shared attempt.

## Rollout

Coordinate the API cutover so every worker understands retained draft
provenance before any worker starts shared draft attempts. Old workers can
use the shared progress key without enforcing draft permissions and may drop
provenance when saving a session. Drain old HTTP, SSE and live voice workers
before admitting requests to the new deployment. While any shared draft
attempt exists, roll back only to a version that checks retained draft
permissions before serving draft content or writing learning data to those
attempts, including streaming and follow-up, and preserves provenance on save.
Keep old records and usage receipts available for support.

## Editor Debug sessions

Editor Debug supports new runs, interaction answers and its existing TTS
controls. It does not offer content regeneration or a regeneration Retry action.
The frontend removes the content-regeneration entry points. The backend retains
the shared reload request and turn-rewind contracts without a content-only
rejection policy or dedicated regeneration retry compatibility. Exact answer
edits use `reload_element_bid`, a revised answer and an optional owning
`reload_generated_block_bid`. Generic rewinds continue to use the shared planner.
The ordinary classroom uses shared durable rewind for both content versions.

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
variables cannot reintroduce discarded future answers. Legacy `debug_variables`
snapshots restore the current panel around an answer edit. The committed
replacement turn also sends `user_variables` from its saved user scope so the
next browser request can replace its seed without copying lesson-only notes
or values from the discarded suffix. Automatic turns in a single request use
the memory saved by the preceding turn.

A successful Debug turn emits `debug_variables_committed` before its adapter
`done` event, including a nonterminal pause for a question. The content contains
`variables` for the current panel and `course_updates` for the browser's course
cache. The latter includes accepted named answers and user-scoped writes, with
the last eligible write for each key winning. A replacement turn updates the
cache through its own committed writes. Lesson-only notes and restored
checkpoints are not course writes. Failed or superseded turns do not publish a
new course update. Old SSE and audio callbacks cannot update a replacement run.

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
