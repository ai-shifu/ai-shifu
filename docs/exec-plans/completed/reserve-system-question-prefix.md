# Reserve System Question Names

## Purpose / Big Picture

Course questions must not declare names beginning with `sys_`, which is a
system-owned namespace. System references in teaching content remain valid.
The canonical naming contract lives in
[course variable scopes](../../references/course-variable-scopes.md).

## Progress

- [x] 2026-10-30 11:35 UTC: Inspected save, parse, history, import, publish and
      automatic definition creation, plus existing frontend error handling.
- [x] 2026-10-30 11:39 UTC: Added shared authoring validation before writes and
      excluded system references from automatic course definitions.
- [x] 2026-10-30 11:40 UTC: Added definition defense, eight localized errors,
      template compatibility and regression tests for each authoring entry point.
- [x] 2026-10-30 11:43 UTC: Updated the isolated branch to latest `origin/main`
      (`b618c8c4c`) and retained upstream question-and-answer translations.
- [x] 2026-10-30 11:44 UTC: Passed 1,375 related backend tests (three skipped),
      independent implementation review and all repository gates. The initial
      harness failure required staging the regenerated document indexes; its
      rerun passed.

## Surprises & Discoveries

- Variable extraction includes body references. Rejecting every extracted
  system key would prevent legitimate personalization references.
- Manual definition mutation routes are already removed; the internal definition
  helper remains the sole automatic creation path, with a legacy table fallback.
- The English built-in demo still declares system questions and needs course-local
  names so a newly created demo can pass the same authoring rules.
- Existing frontend request handling already displays localized business errors
  and preserves unsaved editor content after a rejected save.

## Decision Log

- Validate parsed interaction blocks using the existing MarkdownFlow name reader;
  do not introduce a second parser or change the application-independent engine.
- Match the literal, case-sensitive `sys_` prefix after the existing outer-space
  trimming. Keep system-owned definition creation available outside course scope.
- Reject old invalid drafts when resaved, restored, imported or published without
  migrating stored learner answers or changing existing published content.
- Keep the existing frontend publishing error analytics contract unchanged.

## Outcomes & Retrospective

All course-authoring paths now reject reserved question names before content
writes and moderation or publication side effects. System references remain
available without automatic course definitions. The English demo uses local
question names, and all eight locales expose error code `4022`.

Validation on the latest main base passed 1,375 tests with three existing skips
across shifu, profile and demo-import coverage. All pre-commit gates passed,
including the harness rerun after staging generated indexes. No engine,
frontend protocol, database migration or historical learner data was changed.

## Context and Orientation

`src/api/flaskr/service/shifu/` owns course draft and publication operations.
`profile/profile_manage.py` owns automatic definitions. Shared messages live in
`src/i18n/*/modules/backend/profile.json`, with codes in `src/api/error_codes.json`.

## Plan of Work

Share one parsed-question validator across save, parse, import and publish.
History restoration delegates to save. Reject system names in the course-scoped
definition helper while skipping valid body references during automatic creation.
Protect grammar boundaries, persistence and publication with regressions.

## Concrete Steps

1. Read layered instructions and create an isolated branch from current main.
2. Implement validation, translations, template compatibility and contract docs.
3. Run targeted pytest suites and static gates, inspect the final diff.

## Validation and Acceptance

Both supported question-binding syntaxes reject reserved names. Ordinary
questions, system references and literal examples continue to work. Rejections
leave draft/history/definition and current publication rows unchanged, without
starting moderation or summary side effects. Localization uses a stable error
code, and repository harness and lint gates pass.

## Idempotence and Recovery

No schema or data migration is involved. Reverting the change restores previous
authoring behavior. Existing learner answers and source-checkout changes are
preserved. Re-running validation is safe.

## Interfaces and Dependencies

Reuse `MarkdownFlowDocument.get_all_blocks()` and `read_interaction_variable()`.
Expose failures through the existing localized `AppError` envelope. Add no
dependency, frontend protocol or configuration setting.
