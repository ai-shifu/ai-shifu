# Safe Frontend Dead Code Cleanup

## Purpose / Big Picture

Remove unreachable frontend code while preserving current product behavior
and making the complete cleanup reversible with one Git revert. The audit is
based on main commit `75a105e5d6cf7544733036825085d1e8673c3e29`.

## Progress

- [x] 2026-09-04 UTC: Verified HEAD matches remote main and created
  `sunner/safe-frontend-dead-code-cleanup`.
- [x] 2026-09-04 UTC: Audited tracked frontend modules with Knip 5.85.0,
  TypeScript module resolution, and repository-wide reference searches.
- [x] 2026-09-04 UTC: Passed the baseline production build and all 214 Jest
  suites / 1,966 tests using Node 22.16.0 and lockfile-installed dependencies.
- [x] 2026-09-04 UTC: Removed the five unreachable modules and their exclusive
  utility code, deleting 1,771 source lines without modifying surviving declarations.
- [x] 2026-09-04 UTC: Passed 42 notification page tests and all 214 frontend
  suites / 1,966 tests, type checking, lint, and production build.
- [x] 2026-09-04 UTC: Verified identical route manifests and 166 identical
  application JavaScript asset hashes; passed translation, architecture,
  repository harness, development-tool, and full pre-commit checks.
- [x] 2026-09-04 UTC: Verified the cleanup patch can be reverse-applied and
  recorded the single-commit rollback procedure below.

## Surprises & Discoveries

- Knip reports `e2e/auth.setup.ts` and `e2e/harness-auth.ts` as unused, but
  `playwright.config.ts` selects the setup through `testMatch` and the setup
  imports the auth helper. Both files must remain.
- The five source candidates have only three incoming module references,
  all from within the candidate set. An independent TypeScript resolver scan
  of string literals in tracked frontend JS/TS files found no outside imports,
  re-exports, dynamic imports, or test references to them.
- The baseline Jest run passes but already reports a worker teardown warning.
  The baseline build also has existing lint, workspace-root, and i18n warnings.
- Two post-change full-suite runs had intermittent UI timing failures.
  Inspecting Jest's effective configuration showed that appending
  `--maxWorkers=2` to `test:ci` retained a parsed limit of 50 workers because
  the script already supplies `--maxWorkers=50%`. Running
  `npm test -- --ci --silent --maxWorkers=2` verified an effective limit of two
  workers and passed all 1,966 tests. The isolated onboarding suite also passed
  all 56 tests. No test or application behavior was changed to obtain a pass.

## Decision Log

- Keep this PR limited to the retired credit-notification type editor and its
  template-sync hook. Preserve maintained `c-*` compatibility modules,
  App Router entrypoints, browser setup, dependencies, shared translations,
  API contracts, analytics, and active components.
- Delete utility declarations only when all callers belong to the deleted
  modules or to other deleted utility declarations. Keep legacy policy
  normalization and defaults: current rule migration still needs them.
- Keep existing behavioral tests intact. Validate the actual route through its
  current tests rather than adding tests that merely assert files are absent.
- Keep all code and audit records in one commit and PR so rollback restores
  the entire dependency group together. Do not deploy or merge as part of this
  cleanup task.

## Outcomes & Retrospective

Deleted five unreachable files plus five functions, two types, and four
constant arrays used exclusively by the retired editor. All 47 surviving
top-level declarations in `creditNotificationUtils.ts` remain byte-for-byte
identical at the TypeScript statement level. Existing tests and live components
are untouched.

Validation passed:

- Notification page: 42 tests; full frontend: 214 suites / 1,966 tests.
- TypeScript, ESLint, production build, shared translation validation and usage.
- Both `routes-manifest.json` and `server/app-paths-manifest.json` match the
  baseline exactly. All 166 application JavaScript assets have matching SHA-256
  hashes (excluding webpack bootstrap and generated build/SSG manifests).
- Knip now reports only the two verified Playwright setup false positives.
- Repository harness, architecture boundaries, development tools, and
  `lefthook run pre-commit --all-files` pass.
- `git apply --reverse --check` accepts the complete source cleanup patch.

Authenticated browser smoke tests were not run locally; no route, browser
harness, live component, or test selector changed. The production build and
existing behavioral suites provide the local regression evidence.

## Context and Orientation

All deleted source files are under
`src/web/src/app/admin/operations/credit-notifications/`:

| File | Evidence |
| --- | --- |
| `CreditNotificationTypeConfigTable.tsx` | No callers; imports the retired card. |
| `CreditNotificationTypeConfigCard.tsx` | Only the retired table imports it. |
| `CreditNotificationTemplateSyncPanel.tsx` | Only the retired card imports its exports. |
| `CreditNotificationTypeRuleFields.tsx` | Only the retired card imports it. |
| `useCreditNotificationTemplateSyncState.ts` | No callers. |

These modules contain component/function/type declarations and inert constants,
with no top-level registration side effects. The live `page.tsx` renders
`CreditNotificationConfigTab` and `CreditNotificationTemplateManagementTab`.
The configuration tab uses `CreditNotificationRuleManagementSection`.

The same directory's `creditNotificationUtils.ts` contains five helpers used
exclusively by the retired modules: `setEstimatedDaysThreshold`,
`removeEstimatedDaysThreshold`, `formatPlaceholderToken`,
`formatPlaceholderList`, and `buildPlaceholderGuideGroups`. The last helper
also owns two placeholder types and four placeholder arrays with no other
consumers. `parseThresholdInput`, threshold predicates, normalization, and
`DEFAULT_ESTIMATED_DAYS_THRESHOLD` still serve active code and must remain.

## Plan of Work

Delete the proven unreachable group and its exclusive helper declarations.
Run the notification page tests first, then the full frontend suite, type
checking, lint, production build, translation checks, and repository gates.
Compare build route manifests before and after cleanup. Record results before
creating the single cleanup commit and PR.

## Concrete Steps

From `src/web`, run Knip 5.85.0 with `--include files --reporter json`.
Inspect each candidate's callers and top-level code; verify dynamic imports
and convention-based entrypoints independently. After deletion, run:

1. `npm test -- --runInBand src/app/admin/operations/credit-notifications/page.test.tsx`
2. `npm test -- --ci --silent --maxWorkers=2`, `npm run type-check`,
   `npm run lint`, `npm run build`.
3. From the repo root, `python3 scripts/check_translations.py` and
   `python3 scripts/check_translation_usage.py --fail-on-unused`.
4. Regenerate repository knowledge, then run `python3 scripts/check_repo_harness.py`,
   `python3 scripts/check_architecture_boundaries.py`,
   `python3 scripts/check_dev_tools.py`, and
   `lefthook run pre-commit --all-files`.

## Validation and Acceptance

All existing tests must remain and pass, including notification rule creation,
editing, migration, saving, template management, error paths, and tracking
failure isolation. Type checking and production build must pass. Public route
manifests must match the baseline. Translation inventory must stay valid.
Knip must no longer report unused source files; its two verified browser setup
false positives remain intentionally untouched.

## Idempotence and Recovery

Ship one cleanup commit on the task branch, with no database or configuration
migration. To undo it, create a new rollback branch from the current target
branch, run `git revert <cleanup-commit>`, validate, and open a rollback PR.
If the cleanup PR was squash-merged, revert its squash commit instead. Do not
reset shared history or restore only part of the retired dependency group.

## Interfaces and Dependencies

No API, stored data, configuration, package, translation, or analytics contract
changes. Audit tooling is installed outside the repository; package manifests
and lockfiles remain unchanged.
