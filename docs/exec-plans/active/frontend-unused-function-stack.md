# Frontend Unused Function Cleanup Stack

## Purpose / Big Picture

Remove 13 verified unused functions and hooks left in active frontend files.
Build narrow, independently reversible PRs on top of PR #2762, whose head is
`89d053d0d9e4c622aa3ea2e45a82e16fd68ea446`. Preserve current behavior and keep
each PR's diff relative to the preceding stack branch.

## Progress

- [x] 2026-09-05 06:44 CST: Verified the clean worktree and #2762 head; checked
  all 13 declarations with Knip or noUnused diagnostics, repository searches,
  and TypeScript Language Service references, including unit tests.
- [x] 2026-09-05 06:47 CST: Removed the four unused billing hooks/formatters
  and exclusive imports/cache key; 13 related suites / 227 tests and type
  checking pass, with all retained declarations structurally unchanged.
- [x] 2026-09-05 06:53 CST: Removed five unused upload/password-strength
  helpers; 11 related suites / 115 tests and type checking pass, with all
  retained declarations structurally unchanged.
- [x] 2026-09-05 06:56 CST: Removed three unused authoring helpers and the
  obsolete commented loader call; 102 related suites / 1173 tests and type
  checking pass, with retained declarations structurally unchanged.
- [ ] Remove and validate the unused learner URL helper.
- [ ] Verify the entire stack, production routes, and complete rollback patch.

## Surprises & Discoveries

- File reachability alone missed unused declarations in maintained files.
- Knip's 231 export candidates include functions used inside their own module;
  an unused export does not establish an unused implementation.
- ESLint removed an unnecessary file-level no-unused-vars directive from
  tree utilities during the required checks; this changes no runtime code.
- The current TypeScript project has other noUnused diagnostics. They remain
  audit data, not a reason to change public arguments, Hook state, or unrelated
  behavior in this stack.

## Decision Log

- Scope is exactly the 13 verified functions, their exclusive imports/constants,
  the obsolete commented call to the deleted authoring loader, and the
  unnecessary tree-utilities lint directive removed by the required hook.
- Keep active implementations, API wrappers, public types, state shape, shared
  translations, dependencies, and compatibility module boundaries intact.
- Use four PRs with one cleanup commit per layer. No merge or deployment is
  part of this task. Existing tests remain intact; do not add file-absence tests.
- Preserve surviving TypeScript declarations and compare them structurally;
  run relevant existing tests and type checks for each layer, plus repository
  hooks before committing. Run the full suite and production build at the tip.

## Outcomes & Retrospective

Layer 1 removes four unused declarations and their exclusive imports/cache
key, totaling 43 source lines. Its 13 related suites / 227 tests and type
checking pass. Layer 2 removes five unused upload/password-strength helpers
and their adjacent documentation, totaling 164 source lines; its 11 related
suites / 115 tests and type checking pass. Layer 3 removes three unused
authoring helpers and an obsolete commented call, totaling 22 source lines;
its 102 related suites / 1173 tests and type checking pass. Layer 4 and
cumulative verification are pending.

## Context and Orientation

All source paths below are relative to `src/web/`.

| Layer | Branch | Files and removed declarations |
| --- | --- | --- |
| Base | `sunner/safe-frontend-dead-code-cleanup` | Existing PR #2762; no additional changes. |
| 1 | `sunner/cleanup-unused-billing-helpers` | `src/hooks/useBillingData.ts`: `useBillingBootstrap`, `useBillingCustomization`; `src/app/admin/operations/credit-notifications/creditNotificationUtils.ts`: `formatValue`, `formatTemplateParams`. |
| 2 | `sunner/cleanup-unused-browser-helpers` | `src/lib/file.ts`: `uploadMultipleFiles`, `uploadFileWithCustomName`; `src/lib/validators.ts`: `checkPasswordStrength`, `getPasswordStrengthText`, `getPasswordStrengthColor`. |
| 3 | `sunner/cleanup-unused-authoring-helpers` | `src/store/useShifu.tsx`: `loadProfileItemDefinations`; `src/components/dnd-kit-sortable-tree/utilities.ts`: `getDragDepth`, `findParentWithDepth`. |
| 4 | `sunner/cleanup-unused-learner-helper` | `src/c-api/studyV2.ts`: `getListenFlagFromPageUrl`. |

Each PR targets the preceding branch. The 13 declaration bodies account for
202 lines before adjacent comments, whitespace, and exclusive imports are
removed. The old `loadProfileItemDefinations` call exists only as a comment.
Other files' same-named `formatValue` declarations still have consumers.

## Plan of Work

For each layer, create its branch from the prior layer, remove only its named
declarations, validate the retained behavior, commit, push, and open a ready PR
against the prior branch. Record results in this plan as each layer finishes.
After the fourth layer, validate the cumulative stack and move this plan to
`docs/exec-plans/completed/`.

## Concrete Steps

Use Node 22.16.0 and the existing lockfile-installed dependencies. From
`src/web`, use `npm test -- --ci --silent --maxWorkers=2 --findRelatedTests`
with the layer's source paths and run `npm run type-check`. Do not append
another maxWorkers option to `test:ci`, which already specifies one.

Before each commit, run `python3 scripts/check_dev_tools.py`, regenerate the
knowledge index if this plan changes, and run
`lefthook run pre-commit --all-files`. At the stack tip, run
`npm test -- --ci --silent --maxWorkers=2`, `npm run build`, and compare the
route manifests with the baseline. Check each PR's actual base/head and commits.

## Validation and Acceptance

- The 13 functions have no remaining source references, except historical
  documentation; retained implementations and contracts remain intact.
- Each layer's related tests, type checking, and pre-commit gates pass.
- The complete frontend test suite and production build pass at the tip.
- Public route manifests match the baseline and generated knowledge is current.
- Every PR contains one incremental cleanup commit and targets its predecessor.
- Each layer's patch and the full stack accept reverse-application checks.

## Idempotence and Recovery

Merge bottom to top. After a predecessor merges, retarget the next PR to main;
if the predecessor was squash-merged or rewritten, transplant only that layer's
commit onto the updated main with `git rebase --onto`, then update downstream
branches bottom to top using `--force-with-lease` after checking their remote
heads. Verify each incremental diff again before merging.

To undo a merged layer, create a rollback branch and revert that layer's merge
or squash commit, then open a rollback PR. To undo the entire stack, revert
layers top to bottom. These changes require no database rollback or deployment
configuration restoration. Avoid resetting shared history or copying whole
source files over later changes.

## Interfaces and Dependencies

No package, API, analytics, localization, stored-data, or active Hook contract
changes. `useBillingOverview`, `useBillingWalletBuckets`, `uploadFile`, email
and phone validation, current profile loading, tree projection, and explicit
learner request parameters continue through their current implementations.
