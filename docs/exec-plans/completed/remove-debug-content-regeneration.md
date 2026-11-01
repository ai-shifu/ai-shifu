# Remove editor Debug content regeneration

## Purpose / Big Picture

Revise PR #3291 to remove editor Debug content regeneration. Its existing
checkpoint restores a whole generated turn rather than one rendered element,
so per-element regeneration controls do not offer the expected local edit.
Remove the corresponding content-only Debug backend implementation as well as
the UI. Preserve exact answer editing introduced on main by PR #3285.

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

- [x] 2026-11-03 09:04 UTC: Resolved the rebase against main while retaining
  exact answer edits, answer-only Retry, variable snapshots and generation
  fencing. Frontend checks pass: 175 tests and TypeScript.
- [x] 2026-11-03 09:12 UTC: Verified 1,859 backend regressions, 175 frontend
  tests, TypeScript and repository gates. Preserved all three PR commits and
  prepared the resolved branch for the existing PR. The unchanged literal-marker
  scanner stress module was excluded from the backend run.

## Surprises & Discoveries

- The November 3 rebase found that main now supports exact earlier-answer
  editing with prefix preservation. It reuses checkpoints and reload fields
  originally removed here, so those shared structures must remain for answers.
- The first delivery retained Debug backend reload compatibility; the user's
  follow-up expands removal to that implementation. Ordinary Debug session
  persistence and shared learner/classroom rewind remain necessary.

## Decision Log

- Remove frontend content regeneration and its Retry; preserve normal start,
  stop, reset, exact interaction answer edits and their Retry, engine analytics
  and existing TTS behavior.
- Revert the earlier PR's expanded TTS visibility and new request event.
- Retain retired regeneration event definitions for historical report queries.
- Reject content-only reload requests before usage admission or model execution.
  Retain turn checkpoints and interaction ownership for exact answer edits.
- Preserve strict Redis semantics, request-generation fencing, write ownership,
  draft-edit continuation and the serialized Debug session. Drop only legacy
  content-regeneration retry mappings on the next save.

## Outcomes & Retrospective

The frontend no longer exposes content regeneration or its retry workflow.
Focused tests cover retained copy/TTS controls, ordinary starts and resets,
interaction answers, language state and stale-stream isolation. Content-only
reload planning and retry mappings are removed. Checkpoints, exact question
ownership and answer-edit variable snapshots remain. Shared learner/classroom
rewind and exact Debug answer editing stay supported.

The original November 1 verification passed 1,827 related backend tests and
152 frontend tests, including earlier
answer replacement, multiple questions per turn, saved pending answers,
language, expired caches, write ownership and partial-stream recovery.
That verification also passed frontend type checking and targeted Ruff.
The November 3 rebase passed 1,859 backend tests, 175 frontend tests,
TypeScript, Ruff, repository harness, architecture checks and all other
repository-wide hook checks. The backend run covers learning-agent, HTTP route,
draft classroom history/rewind and lesson routing; only the unchanged
`test_literal_question_markers.py` scanner stress module is excluded.
Lint retains existing fixture and editor warnings. PR #3291 is the delivery
boundary; no merge, deployment or live-browser acceptance is part of this task.

## Context and Orientation

`DebugPanel` owns the controls, `ShifuEdit` supplies callbacks and
`useDebugSession` owns transient run state. `DebugRunParams` and
`debug-request-params.ts` own frontend request preparation.
`agent/debug_session.py` owns the transient cache; `agent/run_agent.py` and
`agent/lesson_entry.py` also serve learner/classroom execution and must retain
their non-Debug checkpoint contracts. The preview DTO and route own rejection
of content-only Debug reload combinations.

## Plan of Work

Remove the content regeneration and retry APIs together with their callers,
state and dedicated analytics. Replace regeneration-specific tests with
coverage of removed controls and retained normal Debug, copy and TTS flows.
Update the canonical Debug and analytics references.
Remove content-only Debug reload handling and retry mappings while retaining
answer-edit checkpoints, session ownership and shared learner/classroom rewind.

## Concrete Steps

Inspect consumers, update the panel/editor/hook contract, remove unused
request helpers and analytics, regenerate repository knowledge indexes, run
focused Jest and TypeScript/lint checks, then the required repository gate.
Commit and push to the existing PR branch and rewrite its title and body.
Exercise Debug cache ownership, errors, draft edits, old-cache loading and
the retired HTTP request contract alongside learner/classroom regressions.

## Validation and Acceptance

No Debug content regeneration or its Retry control is rendered, and the public
hook accepts anchored reloads only for exact interaction answer edits. Ordinary initial runs, answers,
restarts, errors, variable updates, copying and TTS retain regression coverage.
The repository harness and architecture-boundary checks must pass.
The backend must reject content-only Debug reload requests before admission or
a model call, retain answer checkpoints and drop content-only retry mappings.
Interaction components must retain current and earlier-answer resubmission,
including confirmation, new answers reaching the model, and preserving output
before the accepting turn.

## Idempotence and Recovery

Keep all work on `sunner/debug-element-actions`. Revert the task commit to
recover the previous UI; no migration or backend data cleanup is required.

## Interfaces and Dependencies

Remove regeneration-only panel props, hook returns and event producers together.
Retain exact answer-edit reload parameters and answer-only Retry callbacks.
Reject content-only Debug reloads while preserving shared learner/classroom
regeneration, translations and audio.
