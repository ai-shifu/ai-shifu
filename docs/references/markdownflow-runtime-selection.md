---
title: MarkdownFlow Runtime Selection
status: implemented
owner_surface: learner
last_reviewed: 2026-10-27
canonical: true
---

# MarkdownFlow Runtime Selection

Every identified course is taught by MarkdownFlow 2.0. The 1.0 lesson runtime
(`RunScriptContextV2`, its `learn/run/` collaborators and the block-oriented
editor preview) has been removed. `FLOW_ENGINE_V2_ENABLED` is no longer read; it
stays registered only until deployments stop setting it. The retired
`FLOW_ENGINE_V2_SHIFU_BIDS` variable is ignored. A blank course identifier is not
a course and is refused.

## Request routing

`runscript_v2._lesson_events` sends each request one of two ways:

- A follow-up question (`input_type == "ask"`) is answered by `learn.ask`
  beside the lesson, under its own semaphore. It never enters a lesson turn.
- Everything else, including reading, listening, classroom delivery and
  regeneration of earlier content, is a 2.0 lesson turn
  (`agent.lesson_entry.agent_lesson_events`).

A lesson with no script (its outline content is blank) is completed as it
stands, the way 1.0 finished a lesson with no blocks:
`agent.lesson_entry.complete_empty_lesson` checks access, marks the lesson
complete, advances the outline and offers the next lesson's button. A preview
changes no progress. Going back within a lesson with no script is refused with
`server.learn.agentRewindUnavailable`. A missing lesson is reported as
`server.shifu.lessonNotFoundInCourse`.

The editor preview always streams the 2.0 debug preview. Every current editor
bundle sends `debug_session_id`; a request without a valid one comes from a
bundle old enough to expect the retired 1.0 block preview and is refused as a
parameter error.

## History

Learning records written by 1.0 remain readable through the element history
readers (`legacy_record_builder`, `listen_element_legacy`); only the runtime was
removed. Pre-checkpoint history, including 1.0 blocks, cannot be regenerated or
have an earlier answer changed through 2.0; the localized error directs the
learner to Reset the lesson first.

## Verification

`tests/service/learn/test_lesson_routing.py` drives the actual
`runscript_v2._lesson_events` and `run_script` callers: lesson turns reach the
agent whatever the retired flag says, Ask reaches `learn.ask` with its request,
anchors, delivery flags, cancellation event and element adapter unchanged, and
a lesson with no script is completed. `tests/service/learn/agent/test_complete_empty_lesson.py`
covers completion, the paid-lesson refusal, previews and missing lessons against
a real database.
