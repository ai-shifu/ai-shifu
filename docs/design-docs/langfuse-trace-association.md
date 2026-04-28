---
title: Langfuse Trace Association
status: implemented
owner_surface: backend
last_reviewed: 2026-04-17
canonical: true
---

# Langfuse Trace Association

## Background
- The backend used two different Langfuse patterns.
- `learn` runtime and preview created `generation` objects directly on the trace.
- `learn` ask, guardrail, and some `shifu` flows created a span first and then nested `generation` and `event` objects under that span.
- `learn` runtime also initialized trace `output` with an empty string and later called `trace.update(**trace_args)`, which could overwrite real output written earlier in the request.

## Goal
- Make Langfuse trees structurally consistent so related observations appear under the same trace in the UI.
- Stop empty `input` and `output` values from overwriting real trace data.
- Keep HTTP contracts unchanged.

## Decisions
- Introduce a shared helper in `src/api/flaskr/api/langfuse.py` that creates `trace + root span`.
- Treat the trace as trace-level metadata only.
- Treat the root span as the parent observation for runtime `generation` and `event` records.
- Keep ask-specific child spans, but always nest them under the runtime root span.
- Only send `input` and `output` to Langfuse when a real value exists.

## Scope
- `src/api/flaskr/service/learn/context_v2.py`
- `src/api/flaskr/service/learn/handle_input_ask.py`
- `src/api/flaskr/service/shifu/route.py`
- `src/api/flaskr/service/shifu/shifu_publish_funcs.py`
- Focused backend tests for the affected paths

## Implementation Notes
- `RUNLLMProvider` now receives both the trace and a `parent_observation`.
- `chat_llm` and `invoke_llm` continue to work with span-like observations, but callers no longer pass a trace directly for runtime work.
- `learn` runtime accumulates emitted teacher content and uses it when finalizing the root span and trace.
- `learn` ask finalization updates the ask span, the parent observation, and the trace, including the guardrail early-return path.
- `shifu` ask preview and publish summary use the shared helper and finalize trace output explicitly.

## Verification
- Add focused tests for:
  - runtime trace finalization without empty-output overwrite
  - preview trace top-level `session_id` and root span finalization
  - ask nesting under a parent observation
  - publish summary trace output propagation
