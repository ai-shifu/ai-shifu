---
title: MarkdownFlow Langfuse Tracing
status: active
owner_surface: backend
last_reviewed: 2026-10-26
canonical: false
---

# MarkdownFlow Langfuse Tracing

## Purpose / Big Picture

Make every MarkdownFlow 2.0 request identifiable and inspectable in Langfuse.
Course names include the scene, course, and lesson path. Root input describes
the current learner request, root output contains its public result, and the
tree shows context, turns, models, and tools. Profile uses the same machinery.

## Progress

- [x] 2026-10-26 CST: Inspected both engine hosts, gateway, SDK v4 facade, and tests; agreed on request-level traces and short scene names.
- [x] 2026-10-26 CST: Fetched origin/main and created sunner/markdownflow-tracing.
- [x] 2026-10-26 CST: Implemented safe observations, typed nodes, and the request coordinator.
- [x] 2026-10-26 CST: Integrated course learning, preview, and debugging with real-SDK regression coverage.
- [x] 2026-10-26 CST: Integrated Profile execution, preview, and private transformations; all 193 Profile tests pass.
- [ ] Run regression checks and inspect exported traces through Langfuse readback.
- [ ] Update the canonical design and deliver a ready pull request without merging.

## Surprises & Discoveries

- Course traces currently have fixed names and no root input/output.
- The root course generator labels every GeneratorExit as disconnected, even
  when it follows the last terminal event. Business completion must be recorded
  after persistence and before publishing that event.
- Restored course sessions retain the original script while refreshing the
  teaching brief. Context must come from the effective native session.
- Profile buffers native results before publication; tracing must preserve
  that atomicity and must not expose private profile summaries as root output.
- Tools such as finish and remember do not always emit ToolResult events.

## Decision Log

- One request per trace; model calls remain generations inside it.
- Scene names: learn, preview, debug, profile, profile-preview.
- Root input is the submitted answer or an explicit start/continue/regenerate
  action. Full script and effective teaching brief belong in a context node.
- Keep Langfuse 4.14.4 and all engine tracing in the application layer.
- Keep independent ask, live voice, and model probes outside this change.
- The user authorized synchronizing the change to dev and identified the
  development Langfuse project for remote acceptance. Keep the feature PR
  separate and preserve existing dev commits when integrating.
- The user requested minimal intrusion in business code. Keep course/Profile
  naming, metadata, output, and lifecycle policies in Langfuse-specific modules;
  use a current-turn observation proxy instead of mutating gateway instances.

## Outcomes & Retrospective

Implementation is complete. The course agent and affected routing suite passed
1,764 tests (three skipped); Profile passed all 193 tests. Shared SDK and gateway
regressions pass. Final checks and external acceptance remain pending.

## Context and Orientation

Course orchestration lives in flaskr/service/learn/agent. Profile owns its
native engine adapter under flaskr/service/profile_research. Both consume the
application binding flaskr/api/markdownflow.py and GatewayModel. The existing
Langfuse compatibility facade owns SDK v4 propagation and observation creation.
The canonical contract is docs/design-docs/langfuse-trace-association.md.

## Plan of Work

Add safe observation handles and a shared request coordinator, then integrate
both hosts without changing their persistence, streaming, metering, or replay
contracts. Add focused behavior tests and extend real-SDK in-memory assertions.

## Concrete Steps

Implement the shared coordinator and typed child observations. Wire effective
session context, request input, visible output, turn parents, tool events, and
persisted completion into each host. Run the targeted backend suites, repository
harness, architecture checks, and required pre-commit checks. Export deterministic
test requests to the configured Langfuse endpoint and read their observations
back before reporting external acceptance. Create and attach a non-draft PR.

## Validation and Acceptance

Verify all five scenes, structured answers and empty-input actions, automatic
continuation, session reuse, restored script snapshots, public interactions,
tools without paired results, partial output, failures, and terminal-close
classification. Tracing failures must not change business results. Profile
replay must not create additional model calls, and failed private transforms
must leave persisted state unchanged. External acceptance requires readback of
the generated root input/output and parent-child links, not just successful
export submission.

## Idempotence and Recovery

Observation finalization is idempotent. Failed trace operations fall back to
no-op handles. No database/session migration or historical backfill is required.
Existing runtime persistence and cancellation remain authoritative.

## Interfaces and Dependencies

The application coordinator provides root/current observations, context and
input binding, turn creation, native event observation, public output collection,
persisted completion, and idempotent finalization. A permanent parent proxy
follows the current turn without a new gateway setter. Host callbacks are
optional, and host-specific policy lives in local langfuse_tracing modules. The portable
markdownflow package gains no Langfuse dependency.
