# Stream answer feedback and repair incomplete actions

## Purpose / Big Picture

Let learners read ordinary feedback as it is generated. A tool validation problem
should request only the missing portion and should not cause repeated teaching.

## Progress

- [x] 2026-11-19: Implement opt-in streaming and scoped native repair in the engine.
- [x] 2026-11-19: Enable the mode in course delivery and its live evaluator.
- [x] 2026-11-19: Complete regression and low-reasoning replay checks.

## Surprises & Discoveries

The engine can receive an invalid action without receiving prose. The single
repair must cover both defects; separate tool and output retries are too broad
for this path.

## Decision Log

Keep the existing feedback formats and native deferral mechanism. Stream
ordinary prose immediately and use ordinary validators to authorize actions.
Display engine-rendered checking directions only after their existing checks.
The text already displayed is retained even if the action ultimately fails.

## Outcomes & Retrospective

All seven prior DeepSeek Flash and Gemini 4 Hydrogen cases and all three
GPT-6 Luna answer-feedback cases passed a single low-reasoning replay. Nine
previously failing steps used a single tool-only repair; the remaining step
passed on its first response. The deterministic suite verifies split replies
in both orders, rejected repair recovery, and persisted interaction controls.
The course host contracts and historical evaluator replay pass.

## Context and Orientation

The MarkdownFlow engine is under `src/api/markdownflow/engine/`. The course
host in `src/api/flaskr/service/learn/agent/lesson_entry.py` and the evaluator
enable the mode for one text answer bound to authored material.

## Plan of Work

Track whether teaching reached the learner. When a native retry is required,
request only the missing teaching or action. A complete action held for missing
teaching goes through the normal tool path after the next response supplies it.

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
