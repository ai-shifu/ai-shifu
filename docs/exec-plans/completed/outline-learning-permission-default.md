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
- [x] 2026-10-11: Unify backend creation defaults.
- [x] 2026-10-11: Remove frontend creation defaults and use response state.
- [x] 2026-10-11: Verify backend and frontend checks; review creation,
  explicit overrides, response state, analytics, and import/copy compatibility.
- [x] 2026-10-11: Complete repository gates and prepare the verified change for PR.
- [x] 2026-10-11: Keep the default server-only, remove course-detail metadata,
  and verify omitted permissions and explicit teacher choices.

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
- 2026-10-11: Keep the default solely in creation logic. The frontend leaves
  permission unspecified unless a teacher selects one; creation responses
  already provide the effective permission, so no extra metadata is needed.
- 2026-10-11: Preserve existing permissions and analytics contracts; no migration.

## Outcomes & Retrospective

Backend course-service tests pass (1,183 passed, 3 skipped). Frontend creation,
settings, and analytics tests pass (67 passed). Lint, architecture,
transaction-site, and independent contract review pass. Full type-check reports
only the two confirmed baseline errors; no unrelated source changes are included.
All repository pre-commit checks pass with the protected-file handling above.

## Context and Orientation

`shifu_outline_funcs.py` owns single, batch, and default-course outline creation.
`useShifu.tsx` submits creation requests and updates the tree.
`ChapterSetting.tsx` handles explicit lesson permission choices.

## Plan of Work

Centralize the backend default and remove browser defaults while preserving
explicit choices. Cover actual stored permissions,
creation responses, and frontend request/state behavior.

## Concrete Steps

Run focused backend creation/DTO tests and frontend store/dialog tests. Run
type-check, lint, architecture checks, repository harness, developer-tool
validation, and the complete pre-commit gate. Review the diff and create a ready
PR through the repository workflow.

## Validation and Acceptance

Omitted and null permissions produce `trial` in single and batch APIs. A new
course's first lesson is `trial`. Explicit permissions survive creation. The
dialog leaves new permissions unselected, default requests omit `type`, and
local state reflects response values. Existing best-effort analytics remain unchanged.

## Idempotence and Recovery

Tests use isolated fixtures. No data rewrite or migration is involved. Reverting
the patch restores the former creation defaults without rewriting existing rows.

## Interfaces and Dependencies

Outline creation `type` remains optional, and creation response fields retain
their shape. No extra metadata, package dependency, or external service changes
are needed.
