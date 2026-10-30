---
title: Remove unused memory definition type configuration
status: active
owner_surface: shared
last_reviewed: 2026-10-30
canonical: false
---

# Remove unused memory definition type configuration

## Purpose / Big Picture

Remove the ignored definition-list type filter and the save request's text-only
configuration requirement. Keep useful memory operations and the fixed legacy
response fields. The durable request and compatibility contract is in
[the scope reference](../../references/course-variable-scopes.md#memory-definition-api-type-compatibility).
This cleanup concerns memory definition metadata. It does not remove or change
MarkdownFlow single-choice, multi-choice or free-text interaction types.

## Progress

- [x] 2026-10-30 09:37 UTC: Audited definition route, helper, DTO, frontend producer,
  constants, translations and adjacent regression coverage against origin/main.
- [x] 2026-10-30 09:41 UTC: Applied the isolated implementation and regression patch on
  its own branch from current main; keep empty-route removal in its separate PR.
- [x] 2026-10-30 09:41 UTC: Regenerated translation types and repository indexes.
  Passed 186 backend tests, 33 frontend tests, type checking, translation
  parity/usage checks and the repository harness.
- [x] 2026-10-30 09:43 UTC: All-file pre-commit checks pass, including lint,
  formatting, architecture boundaries, translation usage and repository docs.
- [ ] 2026-10-30 09:37 UTC: Commit with the required body, push and open a ready PR
  without merging main.

## Surprises & Discoveries

- The list's `definition_type` argument was explicitly ignored. Its sole HTTP
  producer still sent `type: all` from the course authoring store.
- The definition model has no configurable type column. Response DTOs already
  report text; the optional legacy table path still needs its numeric text code.
- The old save endpoint ignores other retired settings already. Removing type
  reads also lets old extra `profile_type` fields be ignored without enabling
  an option-based definition or altering authored interaction controls.
- The main-branch syntax parser requires the existing percent-prefixed binding
  for these control fixtures. Regressions use that syntax without depending on
  separate interaction-binding work.

## Decision Log

- Remove type input handling and documentation, and simplify the private helper
  signature. Do not reject legacy extra HTTP fields.
- Preserve `profile_type: text`, `profile_type_str`, all other response fields,
  memory CRUD, scope, exact-key matching, visibility and answer persistence.
- Remove only unused non-text definition type constants and the old mapping.
  Keep text constants required by legacy SQL and response compatibility.
- Remove the now-unreachable type error translations in all eight locales and
  regenerate the frontend translation union after applying the patch.
- Do not change historical migrations, schema, MarkdownFlow interaction types,
  runtime prompts, component-library versions or product analytics.

## Outcomes & Retrospective

Implementation is integrated on the independent type-cleanup branch. All 186
focused backend tests and 33 frontend tests pass, along with type, translation
and documentation checks. All-file pre-commit checks also pass. Publication of
the ready PR remains. No deployment or main-branch merge is part of this task.

## Context and Orientation

The profile routes translate HTTP requests into profile_manage helpers. Definition
responses use ProfileItemDefinition; ordinary rows and the legacy profile_item
fallback both produce fixed text fields. The course authoring store's definition
refresh is the current web producer of the retired list filter. The scope reference
owns the permanent API compatibility contract linked above.

## Plan of Work

Remove the list query and helper parameter, the save request type validation and
related documentation, and the unused non-text definition constants. Stop sending
the ignored frontend filter. Keep all output fields and legacy text persistence.
Update request, response, storage and authored-control regressions together.

## Concrete Steps

1. Apply the patch only on the dedicated type-cleanup branch from current main.
2. Run `node scripts/generate_i18n_keys.js` and
   `python scripts/build_repo_knowledge_index.py` from the repository root.
3. In `src/api`, run `python -m pytest tests/service/profile/
   tests/test_mdflow_adapter.py tests/service/shifu/test_outline_content_revisions.py
   tests/service/shifu/test_shifu_uow_failure_paths.py -q` as one command.
4. In `src/web`, run the useShifu and API Jest suites, type checking and lint.
5. Check translation parity/usage, architecture boundaries and the repository
   harness. Verify developer tools, then run all-file pre-commit hooks.
6. Commit and create a ready PR. Keep the independent empty-route cleanup out of
   the patch and never merge either branch into main automatically.

## Validation and Acceptance

- List calls with no filter or legacy all/text/option filters return the same
  course-scoped definitions and retain their fixed text response and label.
- Save calls without a type or with old text/option fields pass only active
  arguments to the helper. Missing course/key validation remains effective.
- Real definition saves preserve existing learner values and the stored and
  parsed single-choice, multi-choice and free-text controls.
- Legacy quick-add keeps its fixed text DTOs and numeric text SQL value.
- The frontend omits the type query while preserving exact keys, scope
  classification, hidden-state projection and the existing cache behavior.
- Shared translations have matching keys and arguments after the two unused
  errors and generated union entries are removed.

## Idempotence and Recovery

No schema, data or cache migration is needed. Old HTTP clients can continue sending
extra type fields, which are ignored. Fixed response fields remain available to
existing consumers. Reverting restores the old input handling without rewriting
stored values. Do not remove adjacent manual CRUD or the legacy SQL fallback.

## Interfaces and Dependencies

The helper becomes `get_profile_item_definition_list(app, parent_id)`. The HTTP
list no longer advertises type filtering, and definition saves require no type
configuration. Response JSON and frontend response interfaces stay compatible.
There is no new dependency, library release or analytics event because no new
user-facing interaction path is introduced.
