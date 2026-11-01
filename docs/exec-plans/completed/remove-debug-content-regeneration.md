# Remove editor Debug content regeneration

## Purpose / Big Picture

Revise PR #3291 to remove editor Debug content regeneration. Its existing
checkpoint restores a whole generated turn rather than one rendered element,
so per-element regeneration controls do not offer the expected local edit.

## Progress

- [x] 2026-11-01 18:23 CST: Confirmed the requested replacement scope and all
  frontend consumers.
- [x] 2026-11-01 18:25 CST: Removed controls, retry state, request producer and
  regeneration-only analytics; preserved ordinary Debug and TTS.
- [x] 2026-11-01 18:26 CST: Updated contracts; 152 focused regression tests
  and frontend type checking passed.
- [x] 2026-11-01 18:29 CST: Verified repository checks and prepared the
  replacement scope and description for the existing ready PR.

## Surprises & Discoveries

- Earlier interaction-answer changes have a separate restart confirmation;
  removing it would change answer submission, outside this task.
- The backend checkpoint and reload contract remains for compatibility.

## Decision Log

- Remove frontend content regeneration and Retry; preserve normal start,
  stop, reset, interaction answers, engine analytics and existing TTS behavior.
- Revert the earlier PR's expanded TTS visibility and new request event.
- Retain retired regeneration event definitions for historical report queries.

## Outcomes & Retrospective

The frontend no longer exposes content regeneration or its retry workflow.
Focused tests cover retained copy/TTS controls, ordinary starts and resets,
interaction answers, language state and stale-stream isolation. The backend
compatibility contract and learner rewind remain intact.

All 152 related tests, frontend type checking and repository guardrails pass.
Lint retains existing fixture and editor warnings. PR #3291 is the delivery
boundary; no merge, deployment or live-browser acceptance is part of this task.

## Context and Orientation

`DebugPanel` owns the controls, `ShifuEdit` supplies callbacks and
`useDebugSession` owns transient run state. `DebugRunParams` and
`debug-request-params.ts` own frontend request preparation.

## Plan of Work

Remove the content regeneration and retry APIs together with their callers,
state and dedicated analytics. Replace regeneration-specific tests with
coverage of removed controls and retained normal Debug, copy and TTS flows.
Update the canonical Debug and analytics references.

## Concrete Steps

Inspect consumers, update the panel/editor/hook contract, remove unused
request helpers and analytics, regenerate repository knowledge indexes, run
focused Jest and TypeScript/lint checks, then the required repository gate.
Commit and push to the existing PR branch and rewrite its title and body.

## Validation and Acceptance

No Debug content regeneration or Retry control is rendered, and the public
hook cannot initiate an anchored reload. Ordinary initial runs, answers,
restarts, errors, variable updates, copying and TTS retain regression coverage.
The repository harness and architecture-boundary checks must pass.

## Idempotence and Recovery

Keep all work on `sunner/debug-element-actions`. Revert the task commit to
recover the previous UI; no migration or backend data cleanup is required.

## Interfaces and Dependencies

Remove regeneration-only panel props, hook returns and frontend reload
parameters together. Preserve the backend wire contract and shared learner
regeneration, translation and audio components.
