---
title: Langfuse Trace Association
status: implemented
owner_surface: backend
last_reviewed: 2026-10-26
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

## SDK v4 Semantics
- Langfuse SDK v4 has no mutable trace record: a trace is the tree of its
  observations, so `src/api/flaskr/api/langfuse.py` keeps the legacy
  `trace.update()` / `trace.span()` call surface but maps it onto observations.
- The overall `input` and `output` of a request live on the root observation.
  Trace-level input/output APIs are deprecated and are not used.
- Correlating attributes (`user_id`, `session_id`, `tags`, `version`,
  `metadata`, environment) are replicated onto every observation through
  `propagate_attributes()`. Attributes bound late (for example the session id,
  known only after the progress record resolves) are additionally written to the
  still-open root observation.
- Observations are created with `start_observation(as_type=...)`; `start_span()`
  and `start_generation()` no longer exist.

## Verification
- Add focused tests for:
  - runtime trace finalization without empty-output overwrite
  - preview trace top-level `session_id` and root span finalization
  - ask nesting under a parent observation
  - publish summary trace output propagation

## MarkdownFlow 2.0 Request Contract

The two native engine hosts share `flaskr.api.markdownflow_tracing`. Each
accepted execution request owns one root observation; automatic native turns
and model requests remain children of that root. Related requests use the
native course session id or the existing Profile session id. Exact Profile
request replay does not execute or charge a model again and does not start an
additional execution trace.

### Names and correlation

Course names have the form `scene/course/chapter/lesson`. Scene names are
`learn`, `preview`, and `debug`. Titles come from the same draft or published
records used to resolve the lesson, with business ids as missing-title
fallbacks. Profile uses `profile` and `profile-preview`, since its questionnaire
does not belong to a course or lesson. Request ids, native turn indexes,
progress/block identifiers, content/configuration revisions, learning mode,
and operation type belong in metadata rather than observation names.

The tree uses stable names such as `context`, `turn`, and native tool names.
A turn is an `agent` observation, an LLM request is a `generation`, and an
engine tool execution is a `tool`. The existing shared gateway remains the
sole producer of model usage and cost observations. Explicit parent handles
keep producer-thread calls in the correct tree without relying on ambient
OpenTelemetry context.

### Inputs and public outputs

Root input is the current submitted learner text or structured answers. A
request without text uses an explicit start, continue, or regenerate action.
It is not the last model-message array entry, which may be a tool response.
The `context` child records the actual native session script and effective
author teaching brief. Restored sessions retain their script snapshot; debug
sessions use the submitted editor document. Prompt bodies are observation
input, not propagated trace metadata.

Root output contains the public prose and interaction controls in presentation
order. Hosts exclude heartbeats, audio, progress events, and private profile
transformations. Cumulative Profile content snapshots contribute only their
new suffix. Model generations retain their complete actual request messages,
results, usage, and error details. Private Profile summary and answer-extraction
operations are child spans in the same request, with their own real inputs and
outputs; they do not replace the public root output.

### Completion and failure isolation

Native tool calls are paired by their tool-call ids where possible. Deferred
interaction requests close the corresponding tool with the pending question.
Memory updates identify staged notes; unmatched `remember` calls are closed
with an unavailable-result status rather than an invented successful result.
Tools such as `finish` that omit a result stay open at the native turn boundary
and close only when the host reports its authoritative saved outcome. A failed
or discarded save must not leave an unresolved tool labeled as successful.
Any outstanding tool/turn is also closed when the request fails or disconnects.

The host marks a business outcome only after its authoritative save succeeds,
before publishing the terminal DTO. Root metadata separates `runtime_outcome`
from `transport_closed`, retaining `end_reason` for existing diagnostics. A
connection closed after a committed waiting/completed result remains successful;
a real mid-turn disconnect retains partial public output. A discarded save is
distinct from completion. Profile retains its buffered atomic publication and
retry semantics, including failures during private summary generation.

SDK create, update, child creation, and end operations are best-effort through
safe observation handles. Their failure cannot interrupt teaching, settlement,
session writes, or SSE publication. This contract uses Langfuse 4.14.4, changes
no database or persisted native-session schema, and applies only to new traces.
Independent ask, live voice, and capability probes retain their existing
semantics.

### Acceptance checks

Focused host regressions cover all five scenes, structured answers, no-text
actions, restored context, automatic continuation, tool completion, visible
interactions, failed/discarded saves, terminal-close classification, replay, and
SDK failure isolation. Real-SDK in-memory tests assert observation types,
parent-child ids, propagated session/user attributes, root IO, and idempotent
finalization. Remote acceptance additionally requires executing the deployed
test paths and reading back their observations in Langfuse; an in-memory export
or a successful submission alone is not remote acceptance.
