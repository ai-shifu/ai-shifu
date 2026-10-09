# Continue teaching after a failed model stream

## Purpose / Big Picture

A provider failure after text has reached the learner must not erase that
teaching from the model's saved conversation. A later request should continue
from that partial response, retaining accepted answers and completed tool
results, without treating a repeat of the partial response as lesson completion.

## Progress

- [x] 2026-10-09T06:43:00Z: Reproduce missing partial teaching in four variants:
  first/resumed turns with original/projected request history.
- [x] 2026-10-09T06:54:00Z: Preserve interrupted run messages and usage, retain a
  durable interruption guard, and include it in rewind checkpoints. The engine
  and host/storage/rewind suites pass 651 cases before the additional legacy
  session compatibility case.
- [x] 2026-10-09T07:02:40Z: Broader related regression passes 5,513 tests (11 skips, four subtests).
  After adding last-turn retry and memory-request boundaries, all learning tests
  pass again: 2,837 tests, one skip and four subtests.
- [ ] Open a focused PR, deploy the exact feature tree to sim and reply to AI opinions.

## Surprises & Discoveries

The host already saves a failed turn's displayed text and session together.
The engine only copied model messages on `AgentRunResultEvent`, so the host's
saved session omitted teaching that was visible in the generated block.

Pydantic AI's stream handle exposes interrupted messages through public
`new_messages()` and `usage` accessors. Its normal history preparation closes
unexecuted partial tool calls with interrupted results rather than executing
those calls on a new prompt. Completed returns and accepted answers remain
paired. Retaining only new messages avoids replacing original persisted history
with a projected request copy.

The existing repeat guard assumes a successful previous turn. Applying its
completion inference to a failed partial response could end a lesson early;
a persisted `interrupted` flag prevents that until teaching advances, a new
interaction is asked, or the model explicitly finishes.

## Decision Log

- Preserve the actual interrupted model history after non-whitespace content
  has been emitted. Do not fabricate assistant responses or tool success.
- Keep the existing answer-retry path for failures before visible teaching.
  Do not save repetitions still held by the output guard as new teaching.
- Append new run messages only once; a later error while processing a completed
  result must not append that run again or double-count usage.
- A continuation of interrupted teaching may finish that turn at the lesson
  turn limit, as deferred-answer retries already can. New learner input does
  not receive this exception.
- Keep the interrupted turn's explicit memory-request evidence across continue
  retries; a new learner message replaces it. Deleted-value restoration still
  requires fresh current input under the existing policy.
- An explicit executed `finish` still ends the lesson, even if the model fails
  afterwards. A repeat alone cannot finish an interrupted lesson.
- Add the interruption flag to JSON sessions and rewind checkpoints with a
  false default for old records. No database migration is needed.
- Provider/engine exceptions are in scope. Browser disconnect persistence,
  provider retry policy, input limits and pedagogical quality are separate work.

## Outcomes & Retrospective

The original failure now has deterministic coverage. Broader regression and final learning tests pass. Exact-image sim acceptance
is pending.
This closes a concrete reliability gap, not the outstanding human teaching
quality or long-term cost acceptance.

## Context and Orientation

`engine/engine.py` streams model events and updates `Session`. `engine/session.py`
serializes conversation state. `agent/run_agent.py` persists failed engine turns
through `session_store.py`, alongside the generated teaching block.
`agent/rewind.py` saves and restores per-block checkpoints for regeneration.

## Plan of Work

Append the failed stream's new messages when it has emitted teaching, then let
the existing host transaction persist them with the displayed block. Distinguish
partial-stream repetition from evidence of lesson completion. Cover deferred
answers, completed and partial tools, explicit finish, projections, JSON/store
reloads, previews and rewind compatibility.

## Concrete Steps

1. Run the offline engine suite and host/storage/rewind regressions in conda
   `ai-shifu`, followed by related learning/profile/user/API/metering tests.
2. Stage this plan, regenerate repository knowledge indexes, and pass all-file
   pre-commit checks and the developer-tool check before each source commit.
3. Push a focused branch to GitHub, open a PR, then merge the feature tree into
   sim and allow the existing deployment webhook to build it.
4. Verify both sim API replicas against the committed runtime hashes and run
   normal HTTP teaching with new dedicated demo/internal learners. Run isolated
   deterministic fault probes against the installed engine without modifying
   service files, existing courses or learner records.
5. Inspect reviews, inline comments and issue comments; reply to each AI opinion.

## Validation and Acceptance

A failing first or resumed stream retains its partial teaching across reloads;
resumed answers appear exactly once. Unexecuted partial tools do not acquire
side effects; completed results are not executed twice. Repeated partial text
is hidden and leaves the lesson unfinished across repeated reloads. Advancing
teaching clears the guard. Explicit finish remains terminal. Old sessions and
checkpoints remain readable, and rewind restores the correct interruption flag.
Sim normal endpoints continue to teach and accept answers on the exact image.

## Idempotence and Recovery

Tests use offline providers and local SQLite. Sim HTTP acceptance uses only new
learners in internal/demo courses. There is no historical rewrite, migration,
production configuration change or automatic main merge. Older code ignores the
additive JSON field; rollback retains saved interrupted teaching evidence.

## Interfaces and Dependencies

Use the pinned Pydantic AI public stream-handle APIs. The additive boolean
`Session.interrupted` defaults to false and is serialized/restored with the
existing session/checkpoint contract. No dependency upgrade or new environment
variable is required.
