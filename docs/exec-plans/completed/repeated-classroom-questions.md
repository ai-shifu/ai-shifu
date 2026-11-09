---
title: Repeated Classroom Questions
---

## Purpose / Big Picture

When a lesson asks two questions in one turn, answering the first can show the
second again. Reloading the lesson should show both questions once, preserve
each answer, and keep any follow-up started from the later display of the
second question.

## Progress

- [x] 2026-11-09 CST: Reproduced duplicate controls and missing follow-ups on the published classroom path.
- [x] 2026-11-09 CST: Recorded emitted identities and answer ownership and used them in both history readers.
- [x] 2026-11-09 CST: Verify the formal classroom, old-record compatibility and scoped follow-up history.

## Surprises & Discoveries

Main already reconstructs many legacy answer defaults from the next turn's
checkpoint. That checkpoint alone cannot prove that two visible controls are
the same question.

## Decision Log

Use the tool-call ID paired with its persisted control in emission order. An
alias is valid while the checkpoint still contains the pending question in the
same learner, course, lesson and progress scope. Missing or ambiguous identity
metadata breaks that chain. Preserve the legacy answer reconstruction.

## Outcomes & Retrospective

The focused published-classroom tests reproduce the issue on main, including
when two distinct questions have identical wording. They pass with the fix,
along with the history tests for alias ownership and older records.

## Context and Orientation

The formal classroom stores turns in generated blocks. The
`agent/run_agent.py` and `agent/rewind.py` modules write the checkpoint and
interaction evidence. The `agent/interaction_history.py` projection supplies
answers and alias information to `elements/history.py` and
`elements/queries.py` in the learning service.

## Plan of Work

Record emitted controls and accepted input in the same durable turn. Reuse
the history projection when reading sidecars for the page, event replay and
follow-up context. Make the cross-version branch depend on this change and
keep its legacy preview migration on that branch.

## Concrete Steps

From `src/api`, run the published-classroom regression and
`tests/service/learn/test_follow_up_classroom_history.py` with pytest. Widen
to `tests/service/learn/` and run the repository guards from the root.
On the dependent branch run the shared version and draft classroom tests.

## Validation and Acceptance

After answering A, verify that live output can redisplay B and that reload
contains the original A and B only. Answer B from the original control and
verify both answers. Load the earlier ask and reply on redisplayed B from
the original anchor in the page, events and model history. Exercise
identical text, missing identity evidence and sidecars outside the scope.

## Idempotence and Recovery

History projection is read-only. Existing turn records remain readable.
If a worker has no identity evidence for a control, history keeps that
control visible and does not redirect its sidecars.

## Interfaces and Dependencies

The existing version-one turn JSON gains optional `question_ids` and
`answered_question_id` fields. Existing HTTP and SSE types are unchanged.
