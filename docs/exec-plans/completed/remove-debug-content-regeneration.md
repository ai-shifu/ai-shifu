# Remove editor Debug content regeneration

## Purpose / Big Picture

Revise PR #3291 to remove editor Debug content regeneration. Its existing
checkpoint restores a whole generated turn rather than one rendered element,
so per-element regeneration controls do not offer the expected local edit.
Remove the corresponding Debug backend implementation as well as the UI.

## Progress

- [x] 2026-11-01 18:23 CST: Confirmed the requested replacement scope and all
  frontend consumers.
- [x] 2026-11-01 18:25 CST: Removed controls, retry state, request producer and
  regeneration-only analytics; preserved ordinary Debug and TTS.
- [x] 2026-11-01 18:26 CST: Updated contracts; 152 focused regression tests
  and frontend type checking passed.
- [x] 2026-11-01 18:29 CST: Verified repository checks and prepared the
  replacement scope and description for the existing ready PR.
- [x] 2026-11-01 18:40 CST: Removed backend Debug reload planning, checkpoint
  sidecars and retry mappings; retired request fields are rejected.
- [x] 2026-11-01 18:40 CST: Verified 1,827 backend and 152 frontend tests,
  including interaction resubmission, draft-edit continuation and shared
  learner/classroom rewind. Prepared the expanded removal for PR #3291.

## Surprises & Discoveries

- Earlier interaction-answer changes have a separate restart confirmation;
  removing it would change answer submission, outside this task.
- The first delivery retained Debug backend reload compatibility; the user's
  follow-up expands removal to that implementation. Ordinary Debug session
  persistence and shared learner/classroom rewind remain necessary.

## Decision Log

- Remove frontend content regeneration and Retry; preserve normal start,
  stop, reset, interaction answers, engine analytics and existing TTS behavior.
- Revert the earlier PR's expanded TTS visibility and new request event.
- Retain retired regeneration event definitions for historical report queries.
- Remove Debug-only backend checkpoint/retry state and reject old reload
  requests before model execution instead of silently starting a normal run.
- Preserve strict Redis semantics, write ownership, draft-edit continuation
  and the normal serialized Debug session. Drop old sidecars on the next save.

## Outcomes & Retrospective

The frontend no longer exposes content regeneration or its retry workflow.
Focused tests cover retained copy/TTS controls, ordinary starts and resets,
interaction answers, language state and stale-stream isolation. Backend Debug
reload planning, checkpoint sidecars and retry mappings are removed as well.
Shared learner and classroom rewind and interaction resubmission stay supported.

All 1,827 related backend tests and 152 frontend tests pass, including earlier
answer replacement, multiple questions per turn, saved pending answers,
language, expired caches, write ownership and partial-stream recovery.
Frontend type checking and targeted Ruff pass.
Lint retains existing fixture and editor warnings. PR #3291 is the delivery
boundary; no merge, deployment or live-browser acceptance is part of this task.

## Context and Orientation

`DebugPanel` owns the controls, `ShifuEdit` supplies callbacks and
`useDebugSession` owns transient run state. `DebugRunParams` and
`debug-request-params.ts` own frontend request preparation.
`agent/debug_session.py` owns the transient cache; `agent/run_agent.py` and
`agent/lesson_entry.py` also serve learner/classroom execution and must retain
their non-Debug checkpoint contracts. The preview DTO and route own rejection
of removed Debug reload fields.

## Plan of Work

Remove the content regeneration and retry APIs together with their callers,
state and dedicated analytics. Replace regeneration-specific tests with
coverage of removed controls and retained normal Debug, copy and TTS flows.
Update the canonical Debug and analytics references.
Remove Debug backend reload handling and sidecar persistence without changing
ordinary session ownership or shared learner/classroom rewind.

## Concrete Steps

Inspect consumers, update the panel/editor/hook contract, remove unused
request helpers and analytics, regenerate repository knowledge indexes, run
focused Jest and TypeScript/lint checks, then the required repository gate.
Commit and push to the existing PR branch and rewrite its title and body.
Exercise Debug cache ownership, errors, draft edits, old-cache loading and
the retired HTTP request contract alongside learner/classroom regressions.

## Validation and Acceptance

No Debug content regeneration or Retry control is rendered, and the public
hook cannot initiate an anchored reload. Ordinary initial runs, answers,
restarts, errors, variable updates, copying and TTS retain regression coverage.
The repository harness and architecture-boundary checks must pass.
The backend must reject old Debug reload requests before admission or a model
call, persist no Debug checkpoints/retry mappings and retain shared rewind.
Interaction components must retain current and earlier-answer resubmission,
including confirmation, new answers reaching the model, and preserving output
before the accepting turn.

## Idempotence and Recovery

Keep all work on `sunner/debug-element-actions`. Revert the task commit to
recover the previous UI; no migration or backend data cleanup is required.

## Interfaces and Dependencies

Remove regeneration-only panel props, hook returns and frontend reload
parameters together. Remove the Debug-specific backend reload contract while
preserving shared learner/classroom regeneration, translations and audio.
