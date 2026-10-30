---
title: Remove manual memory definition write APIs
status: completed
owner_surface: shared
last_reviewed: 2026-10-30
canonical: false
---

# Remove manual memory definition write APIs

## Purpose / Big Picture

Remove the three manual definition write endpoints, their dedicated services and
an unused Web API declaration. Keep automatic definition creation when saving
MarkdownFlow content, all shared definition and value logic, and active editor
visibility and learner memory operations. The current API contract lives in
[the variable scope reference](../../references/course-variable-scopes.md#memory-definition-api-type-compatibility).

## Progress

- [x] 2026-10-30 10:18 UTC: Verified remote main and created an isolated task branch
  from `71d6dd920f21f005a0c67b4b51630b6cf2dc55c2`, including merged PR #3251.
- [x] 2026-10-30 10:26 UTC: Removed only the named manual handlers, services and Web
  declaration. Confirmed retained function source is identical to the base.
- [x] 2026-10-30 10:28 UTC: Updated the current contract, removed ten unused error
  translations in every locale and regenerated translation types. Kept shared
  regressions on the internal creator and added route-removal coverage.
- [x] 2026-10-30 10:33 UTC: Passed 170 focused backend tests and 35 frontend
  tests, TypeScript checking, translation and architecture checks, the repository
  harness, developer-tool verification and all-file pre-commit checks.
- [x] 2026-10-30 10:35 UTC: Opened ready [PR #3253](https://github.com/ai-shifu/ai-shifu/pull/3253).
  Rebased onto new main `7718f31b9f826b04be61768f4fc7cb7fa12f2199`, including
  the independent #3252 copy update, and reran the 170 backend and 35 frontend
  tests plus TypeScript checking. No merge or deployment was performed.

## Surprises & Discoveries

- PR #3251 merged after the read-only audit. This task starts from that merged
  state and does not repeat the retired definition type-input cleanup.
- The Web saveProfile declaration generated a function but had no consumer.
  Learner profile editing has an unrelated local function with the same name.
- Course saving uses add_profile_item_quick_internal directly. Tests that used
  the removed manual wrappers for fixtures must retain shared coverage through
  that helper and an explicit caller-owned unit of work.
- The existing MDF tests mocked the internal creator. Real persistence and
  late-failure rollback need coverage to protect the retained production path.
- Three new route-map regressions failed before the handlers were removed;
  the retained profile and helper tests already passed at that point.
- Borrowed frontend dependencies initially contained markdown-flow-ui 0.3.3
  rather than the main lockfile's 0.3.6. A clean independent npm ci and Node
  22.23.4 resolved the resulting type errors; the lockfile did not change.

## Decision Log

- Remove the HTTP contracts immediately as explicitly requested after the audit;
  requests follow the existing JSON not-found response with code 404.
- Delete only add_profile_item_quick, save_profile_item and delete_profile_item
  and their route handlers. Preserve internal creation, normalization, DTOs,
  colors, models, legacy text-table compatibility, list, usage and visibility.
- Preserve learner profile editing, course-memory deletion, answer storage,
  runtime reads/writes, course copy and history restoration.
- Current official Skill source and the four v2.1.3 distribution packages do not
  call these manual endpoints. Skill content writes depend on automatic MDF
  definition creation, which remains available; no Skill release is needed.
- Update the current reference while preserving its old anchor. Keep the
  completed #3251 execution plan as historical scope rather than rewriting it.
- Do not change schema, stored data, runtime prompts, dependencies or analytics.
  This removes unused entrypoints and introduces no new Web interaction.

## Outcomes & Retrospective

The manual APIs and their dedicated services are removed in ready
[PR #3253](https://github.com/ai-shifu/ai-shifu/pull/3253). The 170 focused backend
tests, 35 frontend tests and TypeScript checking pass on current main plus this
change. Full-file pre-commit, developer-tool, translation, architecture and
repository-harness checks also pass. Independent review found no issue and
confirmed the retained functions are unchanged. Hosted PR checks are separate
from these local results. No merge, deployment or data migration is part of this
task.

## Context and Orientation

Profile routes are in src/api/flaskr/service/profile/routes.py. The dedicated
manual services and shared internal creator live in profile_manage.py. The
course MDF save service in shifu/shifu_mdflow_funcs.py extracts variables and
creates missing definitions in its own unit of work. The Web API catalog is
src/web/src/api/api.ts. Definitions and learner values are separate models.

## Plan of Work

Remove the three route handlers and dedicated services and the unused Web
catalog entry. Update the API contract and only newly unreachable translations.
Replace retained tests' fixture usage of deleted wrappers with the shared
internal creator. Add full-app route-map/404 regressions and real course-save
persistence/rollback regressions. Run the focused suites, required gates and an
independent diff review, then commit and open a ready PR against current main.

## Concrete Steps

1. Fetch remote main into a separate managed worktree and create the task branch.
   Copy existing local environment files without overwriting customized files.
2. Apply exact deletions and compare retained function source against main.
3. Generate translation types and repository knowledge indexes.
4. Run profile, MDF adapter, outline revision, UOW and annotation-policy tests.
   Run real automatic-definition creation and late-failure rollback coverage.
5. Run Web API, API generator and course store tests, TypeScript checking,
   translation parity/usage, architecture checks and repository harness checks.
6. Verify the developer toolchain and run all-file pre-commit checks.
7. Commit, push a task branch and open a ready independent PR. Never merge main.

## Validation and Acceptance

- All three POST paths are absent from the full Flask app route map and return
  the normal JSON code 404. The independent empty lookup route remains absent.
- Definition list responses retain fixed text fields and ignore old type filters.
  Usage, hiding, restoration, exact keys, system reuse and legacy SQL behavior
  continue to pass their existing regressions.
- Real MDF saves create missing definitions without the manual API, reuse keys
  without duplication and preserve existing learner values. A failure after
  the definition flush rolls back both definition and outline writes.
- Existing single-choice, multi-choice and free-text controls, learner profile
  editing and course-memory deletion remain on their existing contracts.
- The unused Web declaration and ten dedicated errors have no remaining live
  references. Shared translations and generated types remain aligned.
- Required developer tools and all-file pre-commit checks pass before commit.

## Idempotence and Recovery

No schema, value, definition or cache migration is needed. Existing rows stay in
place. Reverting the change restores the manual API contracts without a data
rewrite. Do not clean up historical values or legacy table support as part of
this retirement. Preserve the original working checkout and unrelated changes.

## Interfaces and Dependencies

The removed POST endpoints are /api/profiles/add-profile-item-quick,
/api/profiles/save-profile-item and /api/profiles/delete-profile-item. The
retained helper signature is add_profile_item_quick_internal(app, parent_id,
key, user_id). No new dependency or external service is introduced. PR #3250
removed an empty lookup and #3251 removed type inputs; both precede this task.
