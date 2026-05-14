---
title: Operator Course Detail Page
status: implemented
owner_surface: shared
last_reviewed: 2026-05-13
canonical: true
---

## Operator Course Detail Page

### Goal

Add an operator-facing course detail page under `运营 -> 课程管理` so operators can open a course from the list and inspect its key metadata, operating metrics, and chapter structure in one place.

### Scope

- Keep the existing route entry at `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx`
- Add a dedicated operator detail API under the shifu admin surface
- Show three sections on the page:
  - basic course information
  - metrics summary
  - chapter tree list

### Data Contract

The backend detail payload should return:

- `basic_info`
  - `shifu_bid`
  - `course_name`
  - `course_status`
  - creator identity fields
  - created / updated timestamps
- `metrics`
  - `learner_count`
  - `order_count`
  - `order_amount`
  - `follow_up_count`
  - `rating_score`
- `chapters`
  - nested outline nodes for the latest course version
  - each node carries chapter/lesson kind, learning permission, visibility,
    content status, and last modifier identity
- chapter detail endpoint
  - returns chapter `content` on demand when the operator opens the detail modal
  - resolves system prompt with fallback order:
    lesson -> chapter -> course
  - returns prompt source metadata so the modal can label where the prompt came
    from

### Backend Notes

- Reuse the operator visibility rules from the existing course list
- Reuse the latest draft-vs-published resolution used by the operator list:
  - prefer the latest draft row when present
  - still expose whether the course is published
- Build chapter data from the resolved latest outline source so the detail page reflects the latest editable structure

### Frontend Notes

- Keep the page aligned with the existing admin detail card style used in dashboard pages
- Use i18n keys in `module.operationsCourse`
- Keep the bottom section optimized for inspection rather than rich editing
- Keep `src/cook-web/src/app/admin/operations/[shifu_bid]/page.tsx` as the route
  entry and orchestration layer, but split heavy bottom-tab UI into dedicated
  local components as the page grows

### Frontend Structure Follow-up

- Current preferred split order:
  1. credit usage tab
  2. users tab
  3. chapter tab table / detail helpers
- Split rules:
  - do not change existing backend contracts while only restructuring UI
  - keep route params, operator guard, tab switching, and data-fetch orchestration
    in `page.tsx`
  - move tab-local rendering, column sizing, and filter presentation into
    dedicated sibling components
- Goal:
  - reduce the size and review risk of `page.tsx`
  - allow later tab-level iteration without re-reading the whole detail page

### Credit Usage Aggregation Follow-up

- The current credit-usage list is settlement-accurate, but it is too granular
  for operator inspection because it shows one row per settled `usage_bid`.
- The operator-facing view should evolve without changing billing or settlement
  behavior.
- Implemented in this branch:
  - add a grouped credit-usage view for operators
  - keep grouping on the backend so pagination, totals, and ordering remain
    correct
  - use `progress_record_bid + usage_mode` as the primary grouping key so
    learning, listen, and follow-up rows stay separate
  - keep rows without `progress_record_bid` as standalone rows instead of
    forcing them into a group
- Grouped rows should summarize:
  - latest consumed time
  - learner account
  - nickname
  - chapter
  - lesson
  - usage mode summary
  - total consumed credits
  - model summary
- Future extension:
  - keep the grouped view as the default operator overview
  - later add grouped-to-raw drill-down so operators can inspect underlying
    usage rows without replacing grouped view as the primary mode

### Verification

- Add focused backend tests for the new operator detail response
- Add focused frontend tests for the detail page loading, rendering, and back navigation
- Run targeted type, lint, and pytest coverage for touched files
