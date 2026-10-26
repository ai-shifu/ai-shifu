---
title: Replace MarkdownFlow Variables with Question Memory
status: in-progress
owner_surface: learner
last_reviewed: 2026-10-26
---

# Replace MarkdownFlow Variables with Question Memory

## Purpose / Big Picture

MarkdownFlow 2.0 authors ask questions and retain answers under the exact question
text. Remove variable authoring and runtime tool terminology. Literal prompt
assembly and historical expanded-host matching belong to prerequisite PR #3188.
The canonical contract is [Question Memory](../../references/markdownflow-question-memory.md).

## Progress

- [x] 2026-10-26 CST: Preserve issued historical pending answer admission from unique old tool-call evidence without changing serialized history or new-call eligibility; 21 targeted engine/real-host checks pass, including durable write and later canonical refresh. Final related backend suite: 7,975 passed, 96 skipped; full pre-commit passes.

- [x] 2026-10-26 CST: Synchronize both #3188 review fixes through the shared matcher; final engine/learner/Profile pack passes 4,627 tests and full pre-commit passes. New controls remain literal after a historical pending answer.

- [x] 2026-10-26 CST: Save source snapshots and rebase onto current main without losing Profile tracing.
- [x] 2026-10-26 CST: Extract literal prompt behavior into PR #3188 and preserve shared compatibility fixes.
- [x] 2026-10-26 CST: Combined backend pack has 7,945 passing cases after migrating three new main tracing fixtures; 96 skips. All 2,643 engine/tracing checks and 368 frontend checks pass, with types, lint and full pre-commit.
- [ ] 2026-10-26 CST: Inspect current-head CI and effective reviews after the five-minute window.

- [x] 2026-10-25 09:56 UTC: Inspected engine, course/Profile hosts and authoring UI.
- [x] 2026-10-25 09:56 UTC: Confirmed standalone brace text remains literal.
- [x] 2026-10-25 09:56 UTC: Implemented typed questions, exact memory keys and legacy session readers.
- [x] 2026-10-25 09:56 UTC: Adapted course/Profile hosts and teacher preview; frontend type checks and 224 focused tests pass.
- [x] 2026-10-25 09:56 UTC: Updated canonical references; documentation harness and translation checks pass.
- [x] 2026-10-25 10:13 UTC: Native engine/stream acceptance passes 3,342 tests; host suites pass 1,213 tests before the final review correction. Profile contract regressions pass 199 tests, including rendered confirm values and complete stored-value suffixes.
- [x] 2026-10-25 10:13 UTC: Prepared [editor PR #261](https://github.com/ai-shifu/markdown-flow-ui/pull/261); its 3,448 tests, build and real-browser question-mode story pass. npm 0.3.2-dev.1 was read back and installed.
- [x] 2026-10-25 10:13 UTC: Integrated exact editor development pin and generated lockfile; application type checking, lint and 230 focused frontend tests pass.
- [x] 2026-10-25 10:16 UTC: Preserved legacy draft definition creation behind the unchanged runtime selector; routing/authoring/UOW checks pass 70 tests, including rollback.
- [x] 2026-10-25 10:17 UTC: Full repository pre-commit checks pass; application PR prepared on `sunner/markdownflow-question-memory`.
- [x] 2026-10-25 10:24 UTC: Application [PR #3181](https://github.com/ai-shifu/ai-shifu/pull/3181) is open; the release-pin gate correctly rejects the development package.
- [x] 2026-10-25 10:27 UTC: Expanded checks pass: 3,391 native/stream tests and 3,170 remaining learn/shifu service tests (96 existing skips). Corrected provisional reference deferral and question-only follow-up permission fixtures.
- [ ] Human editor dependency merge/formal release, followed by a release-only application pin before any main merge.

## Surprises & Discoveries

The pinned rendering libraries still name their transport field `variable`.
Existing pending sessions and browser protocols need narrow compatibility
adapters. Database profile fields also serve account data outside MarkdownFlow.
The editor dependency exposes variable controls without a disable prop and needs
an explicit question-mode flag. Its formal release workflow requires a human main
merge; feature branches use dev packages. The user explicitly excluded legacy
MarkdownFlow 1.0, so attempted changes to that SDK and its host paths are withdrawn.

## Decision Log

- 2026-10-26: Split prompt substitution removal into independent PR #3188 on main
  `8a055ce9a`. PR #3181 targets its branch, retaining question keys, naming migration,
  authoring/preview and all existing review fixes. Main's newer Profile tracing is preserved.
- 2026-10-26: The release-only main gate is unchanged. A stacked-base check may
  skip the main-only pin check; that is not evidence that the development pin is releasable.

- 2026-10-25: `?[%{{ question }} ...]` uses the trimmed question as its memory
  key; internal punctuation and spaces remain exact. `}}` closes the marker.
- 2026-10-25: The user explicitly confirmed that standalone `{{...}}` is literal
  text. New prompts never interpolate memory into authored script or constraints.
- 2026-10-25: Existing storage/wire names may be read at compatibility boundaries;
  new model tools and native session output expose questions only.
- 2026-10-25: No merge into main is authorized.
- 2026-10-25: The user explicitly excluded MarkdownFlow 1.0. Keep its SDK and
  runtime semantics unchanged; only native 2.0 and current authoring/preview are in scope.

## Outcomes & Retrospective

Native question-memory implementation and editor integration are complete.
The application PR is open with its reviewed implementation. Expanded service
and stream-reference checks pass, including the corrected provisional-reference
streaming boundary and follow-up question admission. Local repository checks
remain the commit gate; the development dependency intentionally blocks a main
merge until the editor formal release is available. The app uses a verified
editor development build for reproducible branch validation; replace it with the formal editor
release after human review of PR #261. The main release-pin gate is retained.

## Context and Orientation

`src/api/markdownflow/engine/` owns the native runtime. Course and Profile hosts
use `flaskr.api.markdownflow`. Teacher preview lives in `src/web/`; shared UI
translations live in `src/i18n/`. Pinned external renderers retain legacy field
names, so adapters map those names to the question-memory contract.

## Plan of Work

Replace native interaction keys and model arguments with `question`. Keep
question parsing exact and limit collection to authored controls. Consume the
literal-prompt prerequisite without duplicating its implementation. Read old pending state without data loss.
Adapt hosts and preview UI, then update documentation and run focused tests.

## Concrete Steps

1. Change native interaction/session schemas and model instructions.
2. Use PR #3188 as the base; keep its literal assembly and compatibility behavior.
3. Adapt host persistence, Profile matching and teacher preview contracts.
4. Run engine, host, frontend and repository harness checks.

## Validation and Acceptance

A punctuation-bearing question survives parsing, rendering, deferred answer and
store reload with the answer stored under the question itself. New model schemas
contain `question` and no `variable`. Standalone braces stay byte-for-byte intact
regardless of memory. Old pending sessions resume under the new schema. Preview
shows questions and answers instead of variable authoring. Offline engine tests,
affected host/frontend tests and repository harness checks pass.

## Idempotence and Recovery

No destructive data migration or deployed change is required. Old storage keys
are interpreted on load; existing learner memory is preserved. Work remains on
an independent feature branch and can be reviewed before any deployment.

## Interfaces and Dependencies

The native tool/spec uses `question`; legacy renderer/parser and SSE/DB adapters
remain explicit compatibility boundaries. The editor component gains a backwards-compatible question-mode flag in a separate
PR. The legacy Python component remains unchanged. Development package pins enable branch validation. Keep the existing main
release-only gate; replace dev pins with formal releases after human merges and
release publication. No main merge or production deployment is performed here.

The shared draft-save path retains legacy definition creation when the existing
deployment runtime selector chooses MarkdownFlow 1.0. Native 2.0 skips it. The
selector is shared through `flaskr.common.markdownflow` without changing its
environment-only semantics or existing course-routing entry point.

## Review Follow-up: 2026-10-25

- [x] 2026-10-25 10:44 UTC: Restored runtime-specific preview keys and editor mode
  in independent commit `2f1f0455b`; 32 backend and 88 frontend checks pass.
- [x] 2026-10-25 10:53 UTC: Rejected invalid active question markers in commit
  `54acab325`; 2,629 offline engine and 233 authoring/Profile tests pass.
- [x] 2026-10-25 10:55 UTC: Removed inapplicable native visibility actions in
  commit `52dd9728f`; 148 frontend checks, types and lint pass.
- [x] 2026-10-25 10:53 UTC: Editor PR #261 search-state correction is verified;
  all applicable CI is terminal/successful on `2f24ef3`, the valid review thread
  is resolved, and npm `0.3.2-dev.2` is read back against its exact source.
- [x] 2026-10-25 11:06 UTC: Historical inline/HTML/math and collected-key
  matching regressions pass in 146 relevant host tests; current native memory
  eligibility and the 1.0 SDK remain unchanged.
- [x] 2026-10-25 11:12 UTC: Corrected three CI test failures in `59563d8bc`.
  The shared local SDK was older than the pinned CI SDK; the exact CI SDK now
  passes 2,629 offline engine tests, 318 related host tests and all 74 tests in
  the two affected CI test files. No runtime or CI workflow change was needed.
- [x] 2026-10-25 11:13 UTC: Consumed reviewed npm `0.3.2-dev.2` through the
  existing feature-branch bump workflow (`0bdbf411a`); the generated lockfile's
  official package URL and integrity match the independently verified build.
- [x] 2026-10-25 11:24 UTC: A new live review caught saved-only legacy keys
  being unhidden by preview. Restored the original source-reference guard only
  at that compatibility boundary; the regression fails before the fix and all
  66 editor tests pass afterward, retaining the complete preview memory map.
- [ ] Synchronize final heads, terminal CI and live review threads. Keep the
  formal-release dependency comment open until a release pin exists.

The reviewer feedback about 1.0 preview values is handled only by restoring a
compatibility boundary introduced by this PR. No 1.0 SDK or execution behavior
is migrated. Native visibility actions are removed rather than introducing a
new storage or course-wide usage contract.

## Rebase Follow-up: 2026-10-25 UTC

- [x] Rebased the application branch onto `ee125ce17`, preserving main's
  PostCSS/Immutable security pins and installed editor export regressions.
- [x] Kept main's removed variable-list editor props absent. Native question
  insertion remains conditional on the existing 2.0 selector; legacy runtime
  and preview memory behavior remain unchanged. The 149 focused preview/editor
  tests pass after conflict resolution.
- [x] Consumed verified npm `0.3.4-dev.1` through the existing bump workflow
  (`d75e4eaf0`), retaining both the new editor baseline and native question hints.
  Official package integrity and ESM/CJS sources match the rebased editor.
- [x] Fresh official-registry installation passes 225 application tests,
  including the real ESM/CJS editor imports, plus TypeScript and lint. The
  rebased native engine passes all 2,629 offline tests with the CI-pinned SDK.
- [x] Updated both existing PR branches with explicit force-with-lease checks.
  The application contains main `ee125ce17`; editor PR #261 contains main
  `70fedef` and its final reviewed head is `be0d803`. Neither main was merged.

The old `0.3.2-dev.2` dependency-only commit is superseded by the newer editor
baseline and its rebased development build. It must not downgrade main's 0.3.3
API and package-loading fixes. Lockfile conflict resolution uses npm generation.
