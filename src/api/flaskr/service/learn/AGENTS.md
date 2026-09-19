# Backend Service: learn

This module owns learning-session orchestration, SSE streaming, ask-provider
adapters, listen-mode assembly, and runtime conversation state.

Entry files in this directory: `routes.py`, `learn_funcs.py`,
`runscript_v2.py`, `listen_element_run_stream.py`,
`ask_provider_adapters/registry.py`.

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
