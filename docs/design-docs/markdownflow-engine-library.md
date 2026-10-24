---
title: MarkdownFlow engine library
status: implemented
owner_surface: backend
last_reviewed: 2026-10-23
canonical: true
---

# MarkdownFlow engine library

## Dependency boundary

`src/api/markdownflow/` owns native MarkdownFlow 2.0 execution, script parsing,
Session JSON, typed events, turn streaming, pagination and question rendering.
It imports neither Flask nor `flaskr` nor SQLAlchemy. The repository architecture
checker enforces that boundary; a subprocess test also executes a native turn
while application imports are forbidden.

`src/api/flaskr/api/markdownflow.py` is the shared application entry point. It
exports the library's native types and runner, binds question labels to shared
i18n, and supplies `GatewayModel`. The adapter in
`flaskr/api/llm/markdownflow_model.py` continues using the existing `chat_llm`
provider, metering, tracing and input-budget policy. There is one streaming
bridge implementation and one set of cancellation/capacity state.

Course orchestration under `flaskr/service/learn/agent/` owns progress, course
memory policy, authorization, course storage, rewind, TTS and course DTO
projection. The course runtime consumes the shared application binding.
Profile orchestration under `flaskr/service/profile_research/` remains on
MarkdownFlow 1.0 in this foundation change. Its migration to the library is a
separate product change; the library does not import either service.

## Calling the library

Application hosts import `Engine`, `Session`, `ScriptBundle`, native turn types,
`iter_turn`, `GatewayModel` and localized control helpers from
`flaskr.api.markdownflow`. They supply their own storage and business policy.
The asynchronous `Engine.run_turn()` API and synchronous `iter_turn()` adapter
operate on native Session state and typed events.

Independent Python callers import `markdownflow`, pass a native model to
`Engine`, and may use the library's portable session/memory store protocols.
`QuestionRenderer(QuestionLabels(...))` receives labels explicitly; it does
not resolve an application locale. Pure controls validation and rendering
share the same codec. Course DTO translation remains outside the library.

Prompts remain package resources and `markdownflow.load_prompt(name)` reads
their exact UTF-8 contents. The loader accepts a resource stem, such as
`teaching_summary`, and rejects paths or file extensions. The engine version
continues to come from `markdownflow/engine/__init__.py`; release tooling reads
that file without importing the application.

## Compatibility and delivery

PR #3163 extracts the existing course engine directly from `main`. PR #3161
then depends on that foundation to migrate Profile to MarkdownFlow 2.0. The
foundation does not require the Profile migration to run, and does not change
Profile routes, questionnaire execution, Redis schema or frontend behavior.
Profile-specific runtime changes and their regressions belong to PR #3161.

This is an in-repository library, shipped with the backend source. It is not a
new published dependency and does not change the pinned MarkdownFlow 1.0 Python
package or frontend package. Prompts, engine version and saved course Session
JSON are unchanged. Existing JSON contains no Python import paths and restores
with the moved classes, including partially answered deferred interactions.
No database or cache migration is required by this extraction.

The old course-local engine and shared helper modules are removed; course
consumers, release/evaluation tooling and tests move in the same change.
The package's public API is `markdownflow`, and application integrations use
the shared application entry point. Lower-level library imports remain
available for specialized course policies and internal tests.

## Verification

Run `cd src/api && python -m pytest tests/markdownflow/ -q` for portable engine,
formatter, bridge, gevent, renderer and package-boundary coverage. Also run
affected course and gateway tests, plus existing Profile 1.0 regressions to
confirm that the extraction preserves its behavior. Run
`python scripts/check_architecture_boundaries.py --run-fixture-tests` and the
normal boundary checker when changing this structure. The extraction
regressions cover independent execution, old Session JSON, shared course and
application types/runner/model, and default production runner selection.

Validation must use the foundation branch based on `main`. Results from a
combined Profile-migration branch do not establish this extraction's standalone
compatibility; the active foundation ExecPlan records the current verification.
