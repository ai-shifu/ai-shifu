# Operator User Detail Page Slimming

## Purpose / Big Picture

Slim the operator user detail route entry so `page.tsx` remains a route-level
composition boundary instead of owning detail loading, credit ledger loading,
filter state, and view-model derivations. The refactor is frontend-only and
must preserve existing API contracts, i18n keys, table columns, route targets,
hash behavior, and operator-visible behavior.

## Progress

- [x] 2026-06-06 00:00 CST: Confirmed the current branch and adjacent user
  detail components before editing.
- [x] 2026-06-06 00:00 CST: Extracted user detail request, route parameter
  decoding, error, and retry state into `useUserDetailData.ts`.
- [x] 2026-06-06 00:00 CST: Extracted user credit ledger request, filter,
  pagination, reset, and retry state into `useUserCreditLedgerData.ts`.
- [x] 2026-06-06 00:00 CST: Extracted user detail display derivations into
  `useUserDetailViewModel.tsx` and shared constants into
  `userDetailConstants.ts`.
- [x] 2026-06-06 00:00 CST: Verified focused tests, type-check, lint, harness
  validation, and whitespace checks.

## Surprises & Discoveries

- The local `page.tsx` already contained a duplicated `setCreditFilters`
  declaration and a stray `</span>` in the credit expiry label; moving the
  surrounding logic into smaller modules removed those syntax issues without
  changing the rendered contract.
- The page already had good behavioral coverage in `page.test.tsx`, including
  credit filter request payloads, hash activation, user switching, course
  links, timestamp formatting, and usage detail loading.
- The credit expiry tooltip label is display-derived but still needs JSX, so it
  currently lives in the view-model hook rather than a pure `.ts` formatter.

## Decision Log

- Keep `page.tsx` responsible for operator guard, route params, hash/tab sync,
  route navigation, usage-detail request binding, and section composition.
- Keep request transport through `@/api`; do not introduce a new request
  abstraction or duplicate backend contract types.
- Preserve the existing credit query shape exactly: `all` values become empty
  strings, grant source only applies to grant filters, course/usage filters only
  apply to consume filters, and time filters only apply when type is not all.
- Keep the split local to the route directory because the hooks are specific to
  the operator user detail page and are not yet shared by other pages.

## Outcomes & Retrospective

- `src/cook-web/src/app/admin/operations/users/[user_bid]/page.tsx` now acts as
  a slimmer route entry and delegates data loading and display derivation to
  local hooks.
- The route remains behaviorally covered by the existing page test suite, and
  no backend, i18n, or visual contract changes were introduced intentionally.
- Future work can split the JSX-based credit expiry label into a tiny component
  if reviewers prefer keeping hooks free of JSX.

## Context and Orientation

Relevant files:

- `src/cook-web/src/app/admin/operations/users/[user_bid]/page.tsx`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/useUserDetailData.ts`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/useUserCreditLedgerData.ts`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/useUserDetailViewModel.tsx`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/userDetailConstants.ts`
- `src/cook-web/src/app/admin/operations/users/[user_bid]/page.test.tsx`
- `src/cook-web/src/app/admin/operations/operation-user-types.ts`

## Plan of Work

1. Move route-independent constants and empty response/detail factories out of
   `page.tsx`.
2. Move user detail loading state and route parameter decoding into a dedicated
   hook.
3. Move credit ledger loading state, filters, pagination, retry, and reset
   behavior into a dedicated hook.
4. Move display-only derivations for info cards, credit overview cards, and
   course labels into a view-model hook.
5. Keep route-level behavior in `page.tsx` and run focused regression checks.

## Concrete Steps

- Add `userDetailConstants.ts` for `EMPTY_VALUE`, tab hashes, empty detail,
  empty credit response, and shared local types.
- Add `useUserDetailData.ts` for user detail fetch and retry.
- Add `useUserCreditLedgerData.ts` for credit ledger fetch, filters, pagination,
  retry, and user-change reset.
- Add `useUserDetailViewModel.tsx` for display derivations and learning/course
  formatting helpers.
- Rewrite `page.tsx` imports and composition so it wires the new hooks into the
  existing summary and tab components.

## Validation and Acceptance

- `cd src/cook-web && npm test -- --runTestsByPath 'src/app/admin/operations/users/[user_bid]/page.test.tsx'`
- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint -- --file 'src/app/admin/operations/users/[user_bid]/page.tsx' --file 'src/app/admin/operations/users/[user_bid]/useUserDetailData.ts' --file 'src/app/admin/operations/users/[user_bid]/useUserCreditLedgerData.ts' --file 'src/app/admin/operations/users/[user_bid]/useUserDetailViewModel.tsx' --file 'src/app/admin/operations/users/[user_bid]/userDetailConstants.ts'`
- `python scripts/check_repo_harness.py`
- `git diff --check`

Acceptance requires all commands to pass and the focused page tests to keep
covering detail loading, credit request payloads, tab hash behavior, user
switching, course links, and usage detail loading.

## Idempotence and Recovery

The change is a local extraction. If a regression appears, compare the moved
logic against the previous `page.tsx` implementation and restore behavior in the
smallest extracted hook rather than reverting unrelated files. Since no backend
contracts or generated artifacts are changed, recovery does not require database
or migration steps.

## Interfaces and Dependencies

- Frontend API client: `@/api` methods `getAdminOperationUserDetail`,
  `getAdminOperationUserCredits`, and `getAdminOperationUserCreditUsageDetail`.
- Store dependencies: `useEnvStore` for login method and currency display data.
- UI dependencies: existing admin summary/tabs components and shared tooltip
  components.
- No backend interface, request DTO, or i18n file changes are required.
