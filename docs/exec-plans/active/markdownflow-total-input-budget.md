---
title: MarkdownFlow total input budget
status: active
owner_surface: learner
last_reviewed: 2026-10-07
---

# MarkdownFlow total input budget

## Purpose / Big Picture

Bound every MarkdownFlow 2.0 gateway request, including instructions, rendered
script substitutions, memory, history, tool results and offered tool schemas.
PR #3029 bounded only the memory JSON section. Preserve complete learning
records and stop oversized requests before provider I/O or billing.
The durable contract is [MarkdownFlow Input Budget](../../references/markdownflow-input-budget.md).

## Progress

- [x] 2026-10-07 CST: Confirm PR #3031 merged and inspect the final gateway boundary.
- [x] 2026-10-07 CST: Implement a shared gateway input limit and localized failure.
- [x] 2026-10-07 CST: Verify exact boundaries, tools, Unicode, retries and persistence;
  176 focused tests and one actual SQLite persistence test passed. Disabling the
  gateway guard makes 16 regression cases fail.
- [ ] 2026-10-07 CST: Pass learning/profile suites and repository gates; open a PR.
- [ ] 2026-10-07 CST: Deploy to sim, verify runtime hashes and fresh-learner regression.
- [ ] 2026-10-07 CST: Reply to every AI opinion and complete external checks.

## Surprises & Discoveries

The gateway sees the final current instructions and offered tool schemas on every
model call, including tool-loop retries. Checking only the engine's initial
prompt would miss these inputs. The admission judge uses the same gateway.

## Decision Log

- 2026-10-07: Cap the compact UTF-8 JSON envelope containing mapped messages and
  effective tools at 262144 bytes (256 KiB). This is an application input budget,
  not a provider token limit or a complete HTTP wire-size guarantee.
- 2026-10-07: Reject oversized requests without shortening author instructions,
  learner answers, tool chains or persisted history. Retrieval and compression
  remain separate follow-ups. Do not reset the lesson automatically.
- 2026-10-07: Apply the same guard to streaming, non-streaming, teacher preview
  and memory-admission gateway calls. Judge failures continue to refuse writes.

## Outcomes & Retrospective

Implementation, 2479 learning/profile tests (one skipped, four subtests) and
all repository gates passed. The actual SQLite host preserves the complete
oversized named answer and deferred result through failure, reload and retry.
Disabling the gateway guard causes 16 focused regression failures. PR review,
external CI and sim acceptance are pending.

## Context and Orientation

`gateway_model.py` maps final pydantic-ai messages and tools before `chat_llm`.
The engine converts failures into `ErrorEvent`; `run_agent.py` persists failed
turn state and `lesson_entry.py` translates failures into the existing SSE error
path. Shared backend translations live in `src/i18n/*/modules/backend/learn.json`.

## Plan of Work

Count the effective gateway envelope before calling `chat_llm`; raise a typed
budget failure with numeric metadata only. Carry a stable failure code through
the engine and saved turn outcome to a localized host error. Add offline actual
engine/gateway and host tests, preserving deferred answers and complete snapshots.

## Concrete Steps

Use conda `ai-shifu` for Python. Run focused gateway, engine and host tests,
then full engine and learning/profile coverage. Regenerate the knowledge index,
run dev-tool checks and all repository pre-commit gates before committing.
Open a focused English PR and integrate its source into `origin/sim` after local
checks; do not merge the PR automatically.

## Validation and Acceptance

Exact-budget requests are sent unchanged; one-byte-over requests make zero
`chat_llm` calls. Unicode, JSON escaping, tool schema growth, tool-call arguments,
results, current instructions and history all count. Every tool-loop call is
checked. Oversized answered interactions retain full named answers and deferred
results across save/reload and can retry without losing evidence. The host shows
a localized capacity error after persistence. Ordinary reading, audio backfill
and listening complete on sim using a fresh learner in the fixed internal course.

## Idempotence and Recovery

No migration, new dependency, deployment setting or stored-data transformation
is required. Reverting this feature restores previous gateway request behavior.
Budget failures preserve records; retrying unchanged oversize input remains
blocked until the input is reduced or a later compression feature is available.

## Interfaces and Dependencies

Reuse `GatewayModel`, `ErrorEvent`, `TurnOutcome`, `raise_error` and existing
translations. The new optional error code is internal; legacy DTO/SSE success
semantics remain unchanged. Production stays on the default-off 2.0 flag.
