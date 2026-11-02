---
title: Shared Interaction Rewind
---

## Purpose / Big Picture

Learner and editor Debug must call shared rewind rules, rather than copy them.
Revising an earlier answer keeps its question and preceding teaching, restores
its accepting checkpoint, and teaches forward with the new answer. Storage stays
separate: durable learner records and expiring editor Debug sessions.

## Progress

- [x] 2026-11-01 CST: Inspect learner, draft preview, Debug, checkpoints and streaming guards.
- [x] 2026-11-01 CST: Create an isolated worktree from current main and copy local environment files.
- [x] 2026-11-01 CST: Share backend planning and frontend interaction-list transitions.
- [x] 2026-11-01 CST: Wire Debug answer edits, retries, cancellation and analytics.
- [x] 2026-11-01 CST: Run focused regressions and repository gates; review final diff.

## Surprises & Discoveries

Debug already shares the engine and session restore, but explicitly restarts on
answer edits and rejects reload anchors together with input. Interaction elements
have distinct IDs even when several questions share one generated block. Debug
must save the accepting checkpoint before model output to permit a running turn
to be superseded. Session and checkpoint metadata must be read from the same
cache snapshot to avoid racing an old stream's save.

## Decision Log

- Share checkpoint planning and interaction updates; keep storage and transport separate.
- Preserve all existing learner decisions and replay boundaries; new answer-edit behavior is Debug-only.
- Permit confirmed answer edits during streaming; reject late old-stream writes and UI events.
- Only Debug enables current-answer edits before first output, after durably saving its checkpoint.
- Order Debug admission by client generation so a late older HTTP request cannot supersede its replacement.
- Preserve main's edited-draft continuation for the current answer; other edited-draft starts use a fresh session. Missing checkpoints report an error.
- Keep existing content-regeneration analytics compatible; use a separate answer-edit family.
- Preserve the original dirty checkout. Submission and merge are authorized for this isolated branch.

## Outcomes & Retrospective

Implemented and reviewed on `codex/shared-interaction-rewind`. The original
dirty checkout remains untouched. The user verified the local Debug behavior
and authorized submission and merge into main.

- Backend agent, draft classroom and HTTP regressions: 1,794 passed.
- Final Debug/HTTP compatibility check (including element-only anchors): 123 passed.
- Frontend learner, Debug and shared-helper regressions: 228 passed.
- TypeScript, changed-file ESLint, Ruff, architecture boundaries and repository harness passed.
- Real FunctionModel runs verify single and same-turn multiple questions: the
  new answer reaches the model while discarded answers leave its context.
- The user verified the local Debug flow. Hosted deployment verification is outside this change.
- Review regression: error rows do not advance the current interaction; racing saves
  between preflight and request admission are retired by the post-claim replan.
- Review regression: Debug can change an active answer before first content;
  published learning and draft preview keep their existing pre-output run guard.
  Both use the shared decision; duplicate Debug submissions stay blocked.
- Review regression: late and duplicate Debug requests cannot replace a newer
  admitted request, including after its separate fence expires. Invalid
  generations fail DTO validation, and stale requests never start the engine.
- Integrated main's edited-draft continuation and shared SSE transport, retaining
  the Debug answer-edit guards and monotonic request admission.

## Context and Orientation

`agent/rewind.py` owns learner rollback; `agent/debug_session.py` stores Debug
checkpoints. Both execute through `agent/lesson_entry.py` and `agent/run_agent.py`.
The learner conversation hook and Debug hook previously duplicated list updates.
Canonical analytics contracts are in `docs/references/frontend-product-analytics.md`.

## Plan of Work

Extract one backend checkpoint planner consumed by learner, preview and Debug.
Extract one frontend interaction transition consumed by both hooks. Add exact
Debug interaction ownership and accept anchored new input without changing
content-regeneration requests. Keep prefix content, restore variables, and make
failed answer edits retry the same target with the new answer.

## Concrete Steps

1. Implement shared rules and focused tests for both storage callers.
2. Wire Debug request DTO, streaming session guard, UI and retry state.
3. Define answer-edit telemetry and regression coverage.
4. Run focused pytest/Jest, type checking, lint and repository boundary/harness checks.

## Validation and Acceptance

Identical scenarios must preserve prefix content, use the new answer and discard
future answers on both surfaces. Cover multiple questions per turn, repeated edits,
ordinary answers, unchanged content regeneration, script changes, expired sessions,
failed retries and replacement of a running stream. Tracking failures cannot change
teaching, and payloads exclude prompts, answers, variables and checkpoint identifiers.

## Idempotence and Recovery

No database migration or dependency update is required. Changes are isolated
on `codex/shared-interaction-rewind`. Debug cache entries expire after 30 minutes; old
sessions without exact interaction metadata fail safely for unsupported rewinds.

## Interfaces and Dependencies

Add optional Debug `reload_element_bid`; paired input means answer editing and an
anchor without input retains content regeneration. Keep the existing engine, SSE
terminal events, request identity guards, and learner storage contracts.
Add optional positive integer `request_generation` to Debug only. Updated clients
increase it for each request in a session; admission and session saves retain the
highest value. Legacy clients remain supported until a sequenced run is admitted.
