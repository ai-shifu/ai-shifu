# Admin Orders Page Slimming

## Purpose / Big Picture

Slim the admin orders route entry so `page.tsx` remains focused on routing,
authentication, tab URL state, and top-level dialogs while order-list filtering
and table rendering move into local route components. This first slice is
frontend-only and must preserve existing order list, redemption-code tab,
filter query, import activation, and create-redemption behavior.

## Progress

- [x] 2026-06-07 08:00 CST: Created `refactor/admin-orders-page-slimming` from
      latest `origin/main` without waiting for PR #1877 or PR #1879.
- [x] 2026-06-07 08:15 CST: Confirmed PR #1877 and PR #1879 are both clean and
      mergeable, and simulated both merge orders without conflicts.
- [x] 2026-06-07 08:35 CST: Extracted order-page shared types, constants, and
      query helpers into `ordersPageShared.ts`.
- [x] 2026-06-07 08:45 CST: Extracted the orders filter UI into
      `OrdersFilterPanel.tsx`.
- [x] 2026-06-07 08:50 CST: Extracted the orders table UI into
      `OrdersTable.tsx` while keeping data loading and column orchestration in the
      route entry.
- [x] 2026-06-07 09:00 CST: Ran focused orders page test, type-check, and
      targeted lint.

## Surprises & Discoveries

- The route file was 1,284 lines before this slice, with order filters and table
  rendering embedded directly in `page.tsx`.
- Existing `page.test.tsx` still emits React `act(...)` warnings from async
  state updates. The warnings were already documented as a known follow-up risk
  in the creator redemption-code notes and do not fail the focused test suite.
- The safest first slice is to move rendering blocks only. Data fetching,
  column auto-sizing, URL sync, and top-level dialogs remain in `page.tsx` to
  avoid changing behavior in the same PR.

## Decision Log

- Keep `page.tsx` responsible for auth redirect, tab URL sync, order fetching,
  course fetching, column auto-size state, and top-level create/import dialogs.
- Move only the order-list filter UI and table UI into sibling route-local
  components in this PR.
- Keep the redemption-code tab unchanged because it is already a dedicated
  component and has separate test coverage.
- Keep request transport through `@/api` and do not add new backend contracts.

## Outcomes & Retrospective

- `src/cook-web/src/app/admin/orders/page.tsx` is reduced from 1,284 lines to
  about 700 lines after the first split.
- The route entry still contains order data orchestration and can be split again
  later into `useOrdersList` if reviewers want a second, narrower PR.

## Context and Orientation

Relevant files:

- `src/cook-web/src/app/admin/orders/page.tsx`
- `src/cook-web/src/app/admin/orders/OrdersFilterPanel.tsx`
- `src/cook-web/src/app/admin/orders/OrdersTable.tsx`
- `src/cook-web/src/app/admin/orders/ordersPageShared.ts`
- `src/cook-web/src/app/admin/orders/page.test.tsx`
- `src/cook-web/src/app/admin/orders/CreatorRedemptionCodesTab.tsx`

## Plan of Work

1. Extract shared order-list constants and URL filter helpers.
2. Extract order filter rendering into a route-local component.
3. Extract order table rendering into a route-local component.
4. Keep data loading and top-level page behavior in the route entry.
5. Run focused frontend regression checks.

## Concrete Steps

- Add `ordersPageShared.ts` for local types, constants, and query helper
  functions.
- Add `OrdersFilterPanel.tsx` for the `AdminFilter` composition, course picker,
  status/channel selects, date range, and text filters.
- Add `OrdersTable.tsx` for `AdminTableShell`, table headers, resizable columns,
  cells, pagination, and view-detail action.
- Update `page.tsx` to wire those components without changing request payloads
  or URL sync behavior.

## Validation and Acceptance

- `cd src/cook-web && npm test -- --runTestsByPath src/app/admin/orders/page.test.tsx`
- `cd src/cook-web && npm run type-check`
- `cd src/cook-web && npm run lint -- --file src/app/admin/orders/page.tsx --file src/app/admin/orders/OrdersFilterPanel.tsx --file src/app/admin/orders/OrdersTable.tsx --file src/app/admin/orders/ordersPageShared.ts --file src/app/admin/orders/page.test.tsx`
- `python scripts/check_repo_harness.py` after generated docs refresh.
- `git diff --check`

Acceptance requires order-list filter search/reset, tab switching, create
redemption action, and initial shifu/status query behavior to keep passing in
`page.test.tsx`.

## Idempotence and Recovery

The split is local to the orders route. If a regression appears, compare the
new components against the previous inline `page.tsx` blocks and restore the
smallest moved rendering block. No database, backend, or migration recovery is
needed.

## Interfaces and Dependencies

- Frontend API client: existing `api.getAdminOrders` and
  `api.getAdminOrderShifus` calls remain in `page.tsx`.
- Shared admin UI: `AdminFilter`, `AdminTableShell`, resizable columns,
  date-range filter, and tooltip text components.
- No backend interface, i18n, or DTO changes are required.
