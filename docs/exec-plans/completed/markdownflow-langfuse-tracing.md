---
title: MarkdownFlow Langfuse Tracing
status: completed
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
- [x] 2026-10-26 CST: Ran regression checks and inspected exported traces through Langfuse readback.
- [x] 2026-10-26 CST: Updated the canonical design and opened ready PR #3185; no main merge.
- [x] 2026-10-26 CST: Centralized host policies in Langfuse modules and removed gateway parent mutation from business code.
- [x] 2026-10-26 CST: Deployed dev build 5492 and read back debug, course preview, and Profile-preview request records.
- [x] 2026-10-26 CST: Full local backend passed 15,037 tests; all five deployed scenes passed remote readback.
- [x] 2026-10-26 CST: All applicable GitHub checks passed at runtime head 564f54a07; reviewed scope/acceptance and archived the plan.

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
- Full CI found old fixtures patching SDK names removed from the course entry
  module. Fixtures now patch the shared tracing boundary instead of retaining
  dead aliases in business code.
- Closing after a committed outline update precedes the terminal DTO. Mark the
  saved outcome before those yields, but keep turn output open through delivery.

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

The implementation and minimal-intrusion refinement are complete. The full
local backend passed 15,037 tests with zero failures, 107 skips, and 50 passing
subtests. Skips require real Redis (92 cases), optional SaaS plugins (10), or
isolated MySQL configuration (5); GitHub CI provides the Redis harness. The
gateway/usage file separately passed all 265 tests, and 631 focused
shared/course/Profile cases passed. Additional real SDK cases cover post-save
closes at outline updates, next-lesson controls, and the terminal event. Seven
bounded-name/context cases pass. All-files pre-commit, repository harness, and
architecture boundary checks pass. All applicable GitHub checks passed at
runtime head `564f54a07`, including the full backend suite with real Redis
(15,129 passed, 15 skipped),
frontend tests, runtime harness, static checks, lint, CodeQL, GitGuardian, and
automated review. The archival commit only updates documentation and generated
indexes; it does not change the verified runtime.

Dev build 5492 deployed image `20261026-54d5df8` to API and Cook Web; both
containers were running with zero restarts on readback. The debugging request
[aa37898765db4e1c8c94e59be04db4f2](https://langfuse.ai-shifu.cn/project/clx156l3a00034h4evri3dbb4/traces/aa37898765db4e1c8c94e59be04db4f2)
has the resolved course/lesson name, start action input, visible lesson and
interaction output, a context node, an agent turn, teaching generations, and an
interaction tool. Its native session link and waiting outcome are present.
The course preview request
[5ead395f5fbb4abfaeb78a85aeb1437d](https://langfuse.ai-shifu.cn/project/clx156l3a00034h4evri3dbb4/traces/5ead395f5fbb4abfaeb78a85aeb1437d)
was independently read back with preview naming, root IO, generation/tool
parents, and native session correlation. The completed Profile preview request
[bfd591e4210b4d4ea477a2ba93b78988](https://langfuse.ai-shifu.cn/project/clx156l3a00034h4evri3dbb4/traces/bfd591e4210b4d4ea477a2ba93b78988)
contains public closing text on the root, a separate `profile.summary` child
with actual transformation messages/result, and its model generation. Its
session is `fb7bb88d5a5247058a271a15f605219d`; its outcome is finished.

Build 5493 subsequently deployed image `20261026-cd4ec0c` to both services,
again with zero restarts. The formal learning answer request
[478ac77042dc4e33be626422f1a9c176](https://langfuse.ai-shifu.cn/project/clx156l3a00034h4evri3dbb4/traces/478ac77042dc4e33be626422f1a9c176)
shows the submitted structured answer, the published chapter/lesson path,
public lesson output, context/agent/generation/tool hierarchy, and native
session `f4783a1924014c39b5c0d175ec355861`. The formal Profile start request
[f585754ec8914380b718045ec7e5fe08](https://langfuse.ai-shifu.cn/project/clx156l3a00034h4evri3dbb4/traces/f585754ec8914380b718045ec7e5fe08)
has the short `profile` name, action input, greeting/question output, waiting
outcome, and session `639a697e2e9d448ab1def8a236653630`. Its context, agent,
generation, and interaction tool were read back. Collection was cancelled
after acceptance and the previously saved personal introduction was retained.

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
