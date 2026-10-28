# Backend Service: learn

This module owns learning-session orchestration, SSE streaming, ask-provider
adapters, listen-mode assembly, and runtime conversation state.

Entry files in this directory: `routes.py`, `learn_funcs.py`,
`host/run.py`, `elements/run_stream.py`,
`ask/providers/registry.py`.

Element building, streaming, persistence and history readers live in
`elements/`, which must not import routes, the run host or follow-up modules
(`scripts/check_architecture_boundaries.py` enforces this). The old
`listen_element_*` module paths are one-release aliases of `elements/`.

The lesson host lives in `host/`: `run.py` takes the run lock or ask slot and
streams SSE, `lesson.py` picks the lesson turn or follow-up for a request,
`db_session.py` owns the streamed run's database session and `sse.py` shapes
terminal events. `host/` must not import `routes.py`; `runscript_v2` is a
one-release alias of `host/run.py`.

Follow-up questions live in `ask/`: `follow_up_run.py` resolves the lesson,
progress record and trace before `handler.py` answers through `providers/`;
`context.py` builds the conversation history and `memory_writer.py` stages
course-memory updates. The host calls in with an `AskContext`; `ask/` must not
import the host or `routes.py`. `ask/__init__.py` stays import-free so provider
constants can be imported without the follow-up runtime. The old
`handle_input_ask`, `follow_up_*`, `ask_provider_langfuse` and
`ask_provider_adapters` paths are one-release aliases.

## Do

- Preserve the SSE event flow and element-oriented runtime state used by
  study, preview, and listen-mode frontends.
- Keep ask-provider integration behind adapter and registry layers so
  provider-specific branches do not leak into routes.
- Treat listen-mode and preview helpers as part of the same runtime state
  machine, and update them together when payload contracts move.

## Avoid

- Do not introduce a second streaming protocol or event naming scheme without
  updating every consumer and compatibility path.
- Do not bypass adapter normalization when wiring new provider or workflow
  integrations into ask flows.
- Do not change runtime DTO enums or element semantics without coordinated
  frontend and test updates.

## Tests

`cd src/api && pytest tests/service/learn/ -q`
