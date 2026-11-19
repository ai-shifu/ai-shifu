# Stream answer feedback and repair incomplete actions

## Purpose / Big Picture

Let learners read ordinary feedback as it is generated. A tool validation problem
should request only missing or rejected tool calls. The repair ignores any prose.

## Progress

- [x] 2026-11-19: Implement opt-in streaming and scoped native repair in the engine.
- [x] 2026-11-19: Enable the mode in course delivery and its live evaluator.
- [x] 2026-11-19: Complete regression and low-reasoning replay checks.

## Surprises & Discoveries

A response can contain a valid action with no prose, or a valid structured
correction alongside streamed prose. Both can run as soon as the action passes
validation. Rejected calls in a tool batch can be retried without repeating
successful calls.

## Decision Log

Keep the existing feedback formats and native deferral mechanism. Stream
ordinary prose immediately and use ordinary validators to authorize actions.
Check engine-rendered hints and learner controls before delivery. Treat initial
prose as final as it arrives, including when the model later chooses structured
checking. Preserve the displayed text in history if the action ultimately fails.

## Outcomes & Retrospective

All seven prior DeepSeek Flash and Gemini 4 Hydrogen cases and all three
GPT-6 Luna answer-feedback cases passed a single low-reasoning replay. Nine
previously failing steps used a single tool-only repair; the remaining step
passed on its first response. These replays preceded the review follow-up.
The deterministic suite verifies tool-only first replies, targeted repairs,
discarded repair prose, and persisted teaching and interaction controls.

## Context and Orientation

The MarkdownFlow engine is under `src/api/markdownflow/engine/`. The course
host in `src/api/flaskr/service/learn/agent/lesson_entry.py` and the evaluator
enable the mode for one text answer bound to authored material.

## Plan of Work

Use native validation to identify missing or rejected calls and request those
calls once. Accept valid actions with no prose and discard text in a repair.
If the first attempt has successful sibling calls, keep their results and
accept only the rejected calls on repair. Bind a rejected memory write to its
original call ID and require the replacement to keep the same normalized key
and storage scope. Reject a replacement if it would rerun a successful write.

## Concrete Steps

Use `CompleteFeedback` around the existing model request and tool execution.
Add deterministic streaming tests and repeat the earlier live model failures.

## Validation and Acceptance

Verify visible text before the first response has ended, one request on a
complete response, at most one repair, no repeated teaching, and safe recovery
when a tool is still invalid. Existing event and tool formats remain in use.

## Idempotence and Recovery

Keep repair data local to a turn. Keep already displayed text and the original
answer in history on failure. Never execute an invalid or interrupted action.

## Interfaces and Dependencies

Use the existing Pydantic AI model-request hooks and course startup settings.
The portable engine keeps buffering unless a host explicitly enables streaming
answer feedback.
