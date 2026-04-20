# Admin Pagination Component

## Goal

Reduce repeated pagination UI code across admin list pages by extracting a shared
component for the existing page-number pagination pattern.

## Scope

- Add a shared `AdminPagination` component for the admin pages that already use
  the same first-page / ellipsis / trailing-page navigation pattern.
- Migrate the following pages to the shared component:
  - `src/cook-web/src/app/admin/orders/page.tsx`
  - `src/cook-web/src/app/admin/operations/page.tsx`
  - `src/cook-web/src/app/admin/operations/users/page.tsx`
  - `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Keep request logic, page state, and API contracts inside each page.

## Non-Goals

- Do not change the infinite-scroll behavior on `src/cook-web/src/app/admin/page.tsx`.
- Do not refactor the dashboard pagination variant in the same step.

## Plan

1. Add a shared admin pagination component on top of the existing UI pagination primitives.
2. Replace the duplicated rendering helpers in the four matching admin pages.
3. Add focused tests for the shared pagination behavior.
