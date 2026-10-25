---
title: Replace MarkdownFlow Variables with Question Memory
status: in-progress
owner_surface: learner
last_reviewed: 2026-10-25
---

# Replace MarkdownFlow Variables with Question Memory

## Purpose / Big Picture

MarkdownFlow 2.0 authors ask questions and retain answers under the exact question
text. Remove variable authoring, substitution and runtime tool terminology.
The canonical contract is [Question Memory](../../references/markdownflow-question-memory.md).

## Progress

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
merge until the editor formal release is available. The app uses
0.3.2-dev.1 for reproducible branch validation; replace it with the formal editor
release after human review of PR #261. The main release-pin gate is retained.

## Context and Orientation

`src/api/markdownflow/engine/` owns the native runtime. Course and Profile hosts
use `flaskr.api.markdownflow`. Teacher preview lives in `src/web/`; shared UI
translations live in `src/i18n/`. Pinned external renderers retain legacy field
names, so adapters map those names to the question-memory contract.

## Plan of Work

Replace native interaction keys and model arguments with `question`. Keep
question parsing exact and limit collection to authored controls. Remove prompt
substitution and variable exports. Read old pending state without data loss.
Adapt hosts and preview UI, then update documentation and run focused tests.

## Concrete Steps

1. Change native interaction/session schemas and model instructions.
2. Replace script substitution with literal script/constraint assembly.
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
