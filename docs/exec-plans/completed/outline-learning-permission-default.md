---
title: Centralize the free outline default in the backend
status: completed
owner_surface: shared
last_reviewed: 2026-10-11
---

# Centralize the free outline default in the backend

## Purpose / Big Picture

Make new lessons consistently free after login, with the backend as the sole
owner of the default. The durable behavior and compatibility contract is
[Outline learning permission default](../../product-specs/outline-learning-permission-default.md).

## Progress

- [x] 2026-10-11: Inspect creation paths and synchronize the task branch with main.
- [x] 2026-10-11: Unify backend creation defaults and expose default metadata.
- [x] 2026-10-11: Remove frontend creation defaults and use response state.
- [x] 2026-10-11: Verify 1,184 backend and 109 frontend checks; review creation,
  explicit overrides, response state, analytics, and import/copy compatibility.
- [x] 2026-10-11: Complete repository gates and prepare the verified change for PR.

## Surprises & Discoveries

The lesson dialog and inline save use `trial`, but placeholders and default
course construction use `guest`. The backend also defaults omitted permissions
to `guest`. Creation responses already include the effective permission.

Full frontend type-check has two existing errors in the user-management test
file at lines 964 and 1026. Both reproduce on the unchanged base commit.

Write-based hygiene checks cannot open the sandbox-protected Codex environment
file even though it is unchanged. Its final newline and whitespace were verified
read-only; the all-files gate passed with that file excluded and automatic
staging disabled.

## Decision Log

- 2026-10-11: Use one backend constant for defaults, including initial outlines.
- 2026-10-11: Expose the default through existing course-detail metadata so the
  browser does not duplicate it; retain explicit teacher choices.
- 2026-10-11: Preserve existing permissions and analytics contracts; no migration.

## Outcomes & Retrospective

Backend course-service tests pass (1,184 passed, 3 skipped). Frontend creation,
settings, analytics, and editor tests pass (109 passed). Lint, architecture,
transaction-site, and independent contract review pass. Full type-check reports
only the two confirmed baseline errors; no unrelated source changes are included.
All repository pre-commit checks pass with the protected-file handling above.

## Context and Orientation

`shifu_outline_funcs.py` owns single, batch, and default-course outline creation.
`ShifuDetailDto` supplies authoring metadata. `useShifu.tsx` submits creation
requests and updates the tree. `ChapterSetting.tsx` handles lesson permissions.

## Plan of Work

Centralize the backend default, expose it in course detail, then remove browser
defaults while preserving explicit choices. Cover actual stored permissions,
creation responses, and frontend request/state behavior.

## Concrete Steps

Run focused backend creation/DTO tests and frontend store/dialog tests. Run
type-check, lint, architecture checks, repository harness, developer-tool
validation, and the complete pre-commit gate. Review the diff and create a ready
PR through the repository workflow.

## Validation and Acceptance

Omitted and null permissions produce `trial` in single and batch APIs. A new
course's first lesson is `trial`. Explicit permissions survive creation. The
dialog reflects backend metadata, default requests omit `type`, and local state
reflects response values. Existing best-effort analytics remain unchanged.

## Idempotence and Recovery

Tests use isolated fixtures. No data rewrite or migration is involved. Reverting
the patch restores the former creation defaults without rewriting existing rows.

## Interfaces and Dependencies

Course detail gains additive `default_learning_permission` metadata. Existing
outline creation `type` remains optional, and creation response fields retain
their shape. No package dependency or external service changes are needed.
