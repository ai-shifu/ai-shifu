# Operator Course Copy

This ExecPlan is a living document and must stay aligned with `PLANS.md`.

## Purpose / Big Picture

Add an operator-only "Copy Course" action in the course list so operations can
create a new draft course from an existing course's latest draft, assign it to a
specified creator, and avoid manual re-entry of course structure and settings.
The copied course must preserve authoring content and core configuration while
not carrying over shared permissions or downstream operating data.

## Progress

- [x] 2026-05-15 10:45 CST: Audited the current operator course list, transfer
  creator flow, and shifu import/export/history helpers to confirm feasible
  reuse points.
- [x] 2026-05-15 10:55 CST: Locked the product rules from the requirement:
  source is the latest draft, copied course starts as draft, built-in demo
  courses cannot be copied, and shared permissions / learning data are not
  copied.
- [x] 2026-05-15 11:05 CST: Wrote the implementation checklist and sequencing
  below so execution can proceed with staged validation instead of a blind
  full-stack change.
- [x] 2026-05-15 11:20 CST: Implemented the backend course-copy service, route, and
  focused pytest coverage, including latest-draft cloning, outline remapping, and
  creator bootstrap reuse.
- [x] 2026-05-15 11:50 CST: Implemented the frontend row action, copy dialog, API
  wiring, zh/en/fr i18n, and focused Jest coverage.
- [x] 2026-05-15 12:20 CST: Ran focused backend/frontend validation, including
  the new copy tests, transfer regression tests, and frontend type-checking.

## Surprises & Discoveries

- Observation: the existing operator transfer-creator flow already solves the
  highest-risk target-user concerns, including identifier normalization,
  missing-user bootstrap, verified credential upsert, creator role grant, and
  post-auth creator bootstrap.
  Evidence: `src/api/flaskr/service/shifu/admin.py` and
  `src/api/tests/service/shifu/test_transfer_creator.py`.
- Observation: the existing import/export helpers already show the correct way
  to regenerate outline bids and remap parent/prerequisite relationships, but
  the raw import path is not a good product boundary for an operator action.
  Evidence: `src/api/flaskr/service/shifu/shifu_import_export_funcs.py`.
- Observation: `DraftShifu.clone()` already covers TTS and learner-language
  fields, so draft duplication can stay field-complete if the new copy service
  clones the latest draft instead of manually enumerating only legacy columns.
  Evidence: `src/api/flaskr/service/shifu/models.py`.
- Observation: saving a clean draft-history root before writing the rebuilt
  outline tree keeps the copied course history consistent without needing to
  reconstruct block-level history records.
  Evidence: `copy_operator_course(...)` now calls `save_shifu_history(...)`
  before `save_outline_tree_history(...)`.

## Decision Log

- Decision: implement a dedicated operator copy service instead of exposing the
  import/export flow directly.
  Rationale: the UI action is a business workflow, needs precise copy/exclude
  rules, and should not inherit file-import semantics.
  Date/Author: 2026-05-15 / Codex
- Decision: copy from the latest draft only, even if the course has published
  content.
  Rationale: the requirement explicitly prefers the latest draft so operations
  duplicate the editable current working state.
  Date/Author: 2026-05-15 / Codex
- Decision: reuse the transfer-creator target resolution path for identifier
  handling, missing-user creation, creator-role grant, and credential sync.
  Rationale: it already matches the `.com` / `.cn` style operator input rules
  and avoids two drifting implementations.
  Date/Author: 2026-05-15 / Codex
- Decision: do not copy shared course permissions or any learner/order/metering
  records.
  Rationale: the copied course should be a fresh authoring asset, not an
  operational clone with inherited live audience state.
  Date/Author: 2026-05-15 / Codex

## Outcomes & Retrospective

- Added `POST /api/shifu/admin/operations/courses/{shifu_bid}/copy` and a
  dedicated backend copy workflow that duplicates the latest draft, regenerates
  outline bids, remaps parent/prerequisite links, and writes draft history.
- Reused the operator target-creator bootstrap logic so copy and transfer stay
  aligned on identifier normalization, user creation, credential upsert, demo
  permission bootstrap, and creator-role grant behavior.
- Added the operator UI action, copy dialog, confirmation step, success toast,
  and zh/en/fr translations on the course list page.
- Added focused backend and frontend coverage to lock the new copy flow and the
  transfer regression surface touched by the shared helper extraction.

## Context and Orientation

The operator course list page already supports:

- course list filters and row actions;
- course detail navigation in a new tab;
- creator transfer via operator-only dialog and backend route.

The shifu backend already supports:

- loading the latest course draft;
- cloning draft course configuration via model helpers;
- rebuilding outline trees with fresh outline business ids;
- persisting draft history snapshots.

This feature should sit beside transfer-creator rather than changing creator
self-serve flows or generic import/export behavior.

## Plan of Work

1. Extract or add a shared backend helper for resolving the target creator from
   operator input so copy and transfer use the same rules.
2. Add an operator course-copy backend service that clones the latest draft,
   recreates outline versions with remapped ids, and saves history.
3. Add the operator route and frontend API binding.
4. Add the row action, dialog, confirmation, success handling, and i18n.
5. Add focused backend/frontend tests and run narrow validation before any
   broader checks.

## Concrete Steps

- Backend
  - Add a shared target-creator resolution helper in
    `src/api/flaskr/service/shifu/admin.py`.
  - Add helpers to load the source latest draft and latest active draft outline
    items, reject built-in demo courses, and build the copied outline/history
    tree.
  - Add `copy_operator_course(...)` that:
    - validates source course visibility;
    - resolves or creates the target creator;
    - grants creator role when needed;
    - creates a new `shifu_bid` and draft course titled `原课程名-副本`;
    - copies latest draft-level configuration and outline content;
    - saves draft and outline history;
    - returns the new course and target-creator summary.
  - Add `POST /api/shifu/admin/operations/courses/{shifu_bid}/copy` route.
- Frontend
  - Add `copyAdminOperationCourse` to `src/cook-web/src/api/api.ts`.
  - Extend `src/cook-web/src/app/admin/operations/page.tsx` with copy dialog
    state and confirmation flow, reusing the existing identifier validation
    rules.
  - Add the new menu item in the course row "more" menu.
  - Refresh the course list and toast after success.
  - Add `copyCourseDialog` and `actions.copyCourse` i18n keys in zh/en/fr.
- Tests
  - Add focused pytest coverage for success, demo rejection, missing-user
    creation, creator-role grant, copied draft/outline fields, and route access.
  - Add focused Jest coverage for opening the dialog, validation, submit,
    request payload, success toast, and error rendering.

## Validation and Acceptance

- `cd src/api && pytest tests/service/shifu/test_course_copy.py -q`
- `cd src/cook-web && npm run test -- src/app/admin/operations/page.test.tsx`
- `cd src/cook-web && npm run type-check`

Acceptance is met when operators can copy a non-demo course into a fresh draft
owned by the target creator, the copied course keeps draft content/config, and
no shared permissions or learner/order/metering data are inherited.

## Idempotence and Recovery

The operator action is intentionally non-idempotent because each successful copy
creates a fresh course. Recovery should come from rerunning the action to create
another copy, not mutating the previous result. If validation fails mid-request,
no partially copied course should remain committed.

## Interfaces and Dependencies

- Backend route: `POST /api/shifu/admin/operations/courses/{shifu_bid}/copy`
- Frontend caller: `src/cook-web/src/api/api.ts`
- Operator UI: `src/cook-web/src/app/admin/operations/page.tsx`
- i18n namespaces:
  `src/i18n/zh-CN/modules/operations-course.json`,
  `src/i18n/en-US/modules/operations-course.json`, and
  `src/i18n/fr-FR/modules/operations-course.json`
- Focused backend tests under `src/api/tests/service/shifu/`
- Focused frontend tests in
  `src/cook-web/src/app/admin/operations/page.test.tsx`
