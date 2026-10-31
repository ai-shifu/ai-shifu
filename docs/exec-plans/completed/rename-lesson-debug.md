# Clarify editor Debug code names

## Purpose / Big Picture

The lesson editor's transient Debug panel is named `lesson-preview`,
`LessonPreview` and `usePreviewChat`, which makes it easy to confuse with the
separate full-course classroom preview. Rename the editor-owned frontend code
to Debug names while preserving its behavior and external contracts.

## Progress

- [x] 2026-10-31 CST: Identified editor-only consumers, helper exports, shared
  variable types and current documentation references.
- [x] 2026-10-31 CST: Updated guidance and source-navigation references; recorded
  the contract boundary for the independent naming change.
- [x] 2026-10-31 CST: Rename the directory, component, hook and owned helpers,
  updating producers, consumers and existing tests together.
- [x] 2026-10-31 CST: Pass 223 tests across eight existing frontend suites,
  type-check, lint, repository harness, architecture checks and all 21 full
  pre-commit checks; prepare the independent branch for review.

## Surprises & Discoveries

Only `ShifuEdit` consumes the main component and hook. Variable-storage exports
also appear in the Shifu store and shared type declarations. Submission helpers
have callers in the shared regression tests. The backend's existing preview
endpoint serves editor Debug, while classroom preview uses the learner chat
flow; a source rename must preserve the endpoint.

## Decision Log

- Rename the directory to `lesson-debug`, the component to `LessonDebug`, the
  hook to `useDebugChat`, and their directly owned copy, submission, typewriter
  and variable symbols consistently.
- Keep API URLs, request fields, SSE values, storage keys, analytics event names
  and payloads, and translation namespaces unchanged. This is a source naming
  refactor with no new user interaction or analytics contract.
- Base this PR on current main and keep selected-step regeneration in its
  separate feature PR. Do not merge either PR or deploy as part of this task.
- Update active guidance and current source locations in older plans while
  retaining historical analytics identifiers and acceptance evidence.

## Outcomes & Retrospective

Implementation and verification are complete. The naming boundary is recorded
in the frontend skill router so later changes can distinguish editor Debug from
classroom preview without relying on conversation context. Existing behavior
tests pass after renaming their imports and symbols. Independent structural
comparison confirmed all non-import runtime literals are preserved. Repository
lint passes with its existing warnings; full pre-commit checks pass. No backend
code, selected-step regeneration, merge or deployment is included.

## Context and Orientation

The renamed implementation lives under `src/web/src/components/lesson-debug/`.
`src/web/src/components/shifu-edit/ShifuEdit.tsx` owns its editor entry point.
`src/web/src/store/useShifu.tsx` prepares Debug variables and parsing results;
`src/web/src/types/shifu.ts` and `chatUi.ts` consume the variable map type.
`src/web/SKILL.md` and the element-streaming skill route future Debug work.

## Plan of Work

Move the editor Debug directory, rename its component, hook and owned helper
files and symbols, then update all imports, mocks and shared type consumers.
Preserve runtime literals and protocols. Update documentation paths and run
the knowledge generator before repository harness validation.

## Concrete Steps

Run the existing Debug component, hook, variable, typewriter, submission and
editor integration tests. Run frontend type-check and lint, the development
tool doctor, architecture checks, repository harness and full pre-commit gate.
Commit the focused rename on its own branch and open a ready-for-review PR.

## Validation and Acceptance

All active editor Debug imports resolve from `lesson-debug`, and the component,
hook, helper exports and test mocks use their Debug names. Existing behavioral
tests pass without changing request URLs, event values, stored variables or
user-visible text. No old source-navigation path remains in active guidance.
The PR contains no selected-step regeneration behavior.

## Idempotence and Recovery

This change does not migrate stored data or require a runtime rollout sequence.
Reverting the naming commit restores the previous source layout. Update shared
imports and exports atomically so no consumer relies on temporary aliases.

## Interfaces and Dependencies

Rename internal TypeScript symbols and module paths together. Existing backend
preview endpoints, Debug run IDs, SSE framing, Umami events, localStorage keys
and i18n JSON remain compatible. No new package dependency is required.
