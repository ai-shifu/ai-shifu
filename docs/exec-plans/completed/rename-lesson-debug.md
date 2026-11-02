# Name editor Debug code by responsibility

## Purpose / Big Picture

The lesson editor's transient Debug panel is named `lesson-preview`,
`LessonPreview` and `usePreviewChat`, which makes it easy to confuse with the
separate full-course classroom preview. Name its panel, session, runs, variables
and actions by their actual responsibilities while preserving behavior and
external contracts.

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
- [x] 2026-10-31 CST: Expand naming beyond the initial prefix replacement:
  distinguish panel/session/run, element/turn IDs, variable values/scopes and
  preparation/request/storage responsibilities; pass the same 223 tests.
- [x] 2026-10-31 CST: Complete the expanded scope's independent audit, 223
  tests, type-check, lint and all 21 repository-wide checks; prepare the
  update to PR #3264 without merging.
- [x] 2026-10-31 CST: Integrate the concurrent main action-row change from
  PR #3263 into the naming branch, preserving its inline regenerate/audio/copy
  layout and adapting only the Debug names and callback contracts.
- [x] 2026-10-31 CST: Correct file casing against the explicit engineering
  baseline: kebab-case for hooks and helpers, matching tests, component-matched
  CSS Modules and a kebab-case `.d.ts` module for shared declarations.

## Surprises & Discoveries

Only `ShifuEdit` consumes the main component and hook. Variable-storage exports
also appear in the Shifu store and shared type declarations. Submission helpers
have callers in the shared regression tests. The backend's existing preview
endpoint serves editor Debug, while classroom preview uses the learner chat
flow; a source rename must preserve the endpoint.
The audio and interaction paths used block-named arguments for actual element
IDs. The numeric stale-stream guard was also named like the opaque session ID.
Shared variable types imported a storage implementation, and `debugParse`
performed definition refresh and saved-value hydration as well as parsing.
Main advanced with PR #3263 while the naming update was in progress. Its panel
layout was preserved during conflict resolution rather than restoring the older
separate helper-row rendering.
Nearby source files use historical camelCase names, but the engineering baseline
explicitly requires kebab-case for ordinary frontend modules. Existing gates do
not enforce this filename rule, so passing them alone did not establish compliance.

## Decision Log

- Keep `lesson-debug` as the owning directory. Use `DebugPanel`,
  `DebugVariablesPanel` and `DebugContentCopyButton` for UI composition, and
  `useDebugSession` for session orchestration.
- Avoid repeating `Lesson` in those names: the directory supplies that context.
  Keep meaningful responsibility words such as `Panel`, `Session` and `Run`.
- Follow the canonical file-name rules in `docs/engineering-baseline.md` rather
  than copying legacy file casing. Keep code symbols such as `useDebugSession`
  in camelCase independently of the `use-debug-session.tsx` filename.
- Distinguish `startRun` / `stopRun` from `resetSession`; use action names for
  submissions, regeneration, variable updates and element audio. Adapt existing
  shared ChatUi props at the boundary rather than renaming unrelated consumers.
- Use camelCase for internal `DebugRunParams`, `elementBid` for rendered
  elements, `generatedBlockBid` for engine turns and `streamGeneration` for
  stale-callback guards. Preserve snake_case at the wire boundary.
- Move shared value, scope, preparation and run types to `src/types/debug-session.d.ts`.
  Use `prepareDebugSession`, `debug-request-params.ts` and `debug-variable-storage.ts`
  for the separate preparation, request-shaping and persistence responsibilities.
- Keep API URLs, request fields, SSE values, storage keys, analytics event names
  and payloads, and translation namespaces unchanged. This is a source naming
  refactor with no new user interaction or analytics contract.
- Base this PR on current main and keep selected-step regeneration in its
  separate feature PR. Do not merge either PR or deploy as part of this task.
- Update active guidance and current source locations in older plans while
  retaining historical analytics identifiers and acceptance evidence.

## Outcomes & Retrospective

The expanded implementation and verification are complete. All 223 existing
tests, frontend type-check and lint, and all 21 repository-wide checks pass.
Independent comparison confirms unchanged request payloads, stored JSON,
continuation preparation and local symbol bindings. The naming boundary is recorded
in the frontend skill router so later changes can distinguish editor Debug from
classroom preview without relying on conversation context. Existing behavior
tests pass after renaming their imports and symbols. Independent structural
comparison checks wire behavior and stored JSON. Diagnostic labels now identify
lesson Debug; protocol literals and user-visible strings stay stable. No backend
code, selected-step regeneration, merge or deployment is included.

## Context and Orientation

The renamed implementation lives under `src/web/src/components/lesson-debug/`.
`src/web/src/components/shifu-edit/ShifuEdit.tsx` owns its editor entry point.
`src/web/src/store/useShifu.tsx` prepares Debug variables and parsing results;
`src/web/src/types/debug-session.d.ts` owns value, scope, preparation and run types;
`shifu.ts` and `chatUi.ts` consume those types without importing storage code.
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
