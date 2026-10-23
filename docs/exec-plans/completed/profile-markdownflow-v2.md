---
title: Profile questionnaire MarkdownFlow 2.0 runtime
status: completed
owner_surface: backend
last_reviewed: 2026-10-23
---

# Profile questionnaire MarkdownFlow 2.0 runtime

## Purpose / Big Picture

Run profile onboarding and operator previews with the existing MarkdownFlow 2.0
agent engine. Preserve published questionnaire documents, per-block progress,
answer imports, private final drafts, and the existing frontend SSE contract.

## Progress

- [x] 2026-10-23 CST: Traced learner and preview routes to the standalone 1.0
  runtime; fetched main and created `sunner/profile-markdownflow-v2`.
- [x] 2026-10-23 CST: Verified the existing runtime and onboarding contract tests
  before implementation (275 passing tests).
- [x] 2026-10-23 CST: Add the public engine reuse boundary and gateway adapter.
- [x] 2026-10-23 CST: Replace block execution and persist resumable tool state.
- [x] 2026-10-23 CST: Cover real agent interactions, resume, replay, imports,
  old cached sessions, error recovery, and hidden summaries.
- [x] 2026-10-23 CST: Bind learner and operator submissions to their deferred
  question ID and keep separate stable content/question/feedback identities.
- [x] 2026-10-23 CST: Passed 492 profile/config/route tests, 1,168 engine and
  shared-host tests, 170 frontend tests, and the complete pre-commit gate.
- [x] 2026-10-23 CST: Fixed mixed choice-plus-text input and guarded static
  question types, bindings and ordered stored values in separate review commits.
- [x] 2026-10-23 CST: Prepared a focused pull request with validation evidence
  and the cache-schema rollout/recovery contract.

## Surprises & Discoveries

- The 2.0 engine runs agent turns, while the profile frontend advances authored
  blocks. Keep document parsing as an authoring compatibility boundary and
  execute each block through the agent engine; do not call `MarkdownFlow.process`.
- Existing cached sessions have no typed tool history. Resume their current
  authored block without discarding a submitted answer.
- Whole-block variables are not sufficient evidence: unlabelled accepted
  answers need independent persistence, including while another question is
  pending and the learner imports external answers.
- Agent turns can emit both content and deferred controls. Separate element
  IDs prevent questions from replacing introductory text or earlier feedback.
- The existing test forbidding all learning-service dependencies must become
  a check that profile uses only the stable public agent API. Course execution,
  billing persistence and database lesson sessions remain outside this feature.

## Decision Log

- Reuse the vendored engine, shared gateway, synchronous bridge, interaction
  renderer and content formatter through `learn.agent.api`.
- Preserve current API/event names and request deduplication. Add optional
  `interaction_id` output / `expected_interaction_id` input to bind successive
  deferred questions to their original UI; bind exact replay to this token.
  This introduces no new user action or analytics payload change.
- Store only the current block's engine session in the existing owner-scoped
  Redis record. Keep the existing TTL, locks, frozen documents and replay data.
- Treat prior transcript and imported evidence as untrusted data, outside the
  authored script, so learner input cannot declare authored interactions.
- Retain nonbillable debug metering and shared provider routing/tracing.
- Keep static question bindings, input kinds and ordered stored choices identical
  to the frozen document while permitting localized display text. Preserve both
  selected choices and typed text in mixed controls.
- The first-release migration reads existing schema-1 sessions, which have no
  typed pending tools. Recovery from manually altered or future-incompatible
  schema-2 tool specs is outside this migration's accepted cache contract;
  a future host-validator change must define its typed-session migration.

## Outcomes & Retrospective

Profile onboarding and operator previews now execute through the shared 2.0
engine. Frozen authored blocks remain the UI progress boundary; deferred calls
and accepted evidence survive Redis, exact retry and assistant import. The
legacy parser remains only for authoring validation and source restoration.

Validation passed: 492 profile/config/route tests; 1,168 engine, bridge, gateway
and protocol tests; 170 frontend tests; the full repository pre-commit gate,
repository harness, architecture ratchet and unit-of-work ratchet. TypeScript
also passed across the complete frontend using the pinned markdown-flow-ui
0.2.35 from a temporary package mapping. The shared local node_modules has an
older 0.2.26 installation, so it was left untouched rather than changing a
shared environment or the dependency pin.

The implementation and offline acceptance are complete. Deployment and merge
remain outside this task; operators must follow the schema rollout contract
in the canonical profile onboarding specification.

## Context and Orientation

`src/api/flaskr/route/profile.py` and the operator preview routes use
`flaskr.service.profile_research.api`. The service owns Redis sessions,
per-block runs, cumulative SSE output and assistant-answer import. The engine
is vendored under `flaskr/service/learn/agent/engine`; its session serializer
preserves pending tool IDs, accepted answers, memory and model messages.

## Plan of Work

Expose an explicit public engine boundary. Add a profile-specific adapter that
runs one authored block, translates typed interactions to current controls,
and serializes the pending state. Replace the old execution call while leaving
admission, ownership, replay, final draft privacy and staged imports intact.
Update tests and canonical profile documentation together.

## Concrete Steps

1. Add `learn/agent/api.py`, a gateway-model factory, and the block adapter.
2. Extend the Redis session serializer with backward-compatible engine state.
3. Wire normal and final/imported runs through the same adapter.
4. Run deterministic `FunctionModel` regressions and existing route tests.
5. Run static checks, review the diff, commit and open a ready pull request.

## Validation and Acceptance

Real tool calls must pause, survive Redis round trips and accept answers.
Rejected answers must retain the question. Replaying an identical request must
not call the model. Tool/provider failures must leave the durable cursor
unchanged. No summary text may appear in learner-visible content events.
Imported answers must preserve manual evidence and use the same final engine
block. Learner and operator preview routes must continue to pass their existing
contract tests. Run all offline engine tests plus repository harness,
architecture and unit-of-work checks.

## Idempotence and Recovery

All edits are on a feature branch. The database schema is unchanged. Existing
cached payloads remain readable; engine state is added only after a successful
turn. Existing locks and exact-request replay remain authoritative. Deployment
must replace old workers together: old workers do not understand new pending
tool state. Reverting code requires expiring active profile sessions, whose
maximum lifetime remains thirty minutes.

## Interfaces and Dependencies

The profile public API keeps its existing fields and adds the optional
interaction identity described in the canonical product spec. The new public
`learn.agent.api` exposes reusable engine primitives without course orchestration.
Production model calls use `GatewayModel` and the existing nonbillable usage
context. No new package or frontend dependency is required.
