# Admin Pagination Component

Historical implementation proposal. The shared pagination component is now
present; PR #1542 merged on 2026-04-20 (`51534b5c5`). The scope and plan below
record the original migration, not pending work or today's complete API.
For current changes, use the [admin table workflow](../../src/web/skills/admin-table-visual-system/SKILL.md)
and [AdminPagination](../../src/web/src/components/admin/AdminPagination.tsx).

## Goal

Reduce repeated pagination UI code across admin list pages by extracting a shared
component for the existing page-number pagination pattern.

## Scope

- Add a shared `AdminPagination` component for the admin pages that already use
  the same first-page / ellipsis / trailing-page navigation pattern.
- Migrate the following pages to the shared component:
  - `src/web/src/app/admin/orders/page.tsx`
  - `src/web/src/app/admin/operations/page.tsx`
  - `src/web/src/app/admin/operations/users/page.tsx`
  - `src/web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Keep request logic, page state, and API contracts inside each page.

## Non-Goals

- Do not change the infinite-scroll behavior on `src/web/src/app/admin/page.tsx`.
- Do not refactor the dashboard pagination variant in the same step.

## Plan

1. Add a shared admin pagination component on top of the existing UI pagination primitives.
2. Replace the duplicated rendering helpers in the four matching admin pages.
3. Add focused tests for the shared pagination behavior.
