# Dashboard Entry Page (v2) Technical Design

## Goal

Add a top-level entry page for the admin dashboard that shows:

1. Total course count
2. Total learner count
3. Total order count
4. Total generation count
5. Course list

When a course is clicked, user enters the existing course-level dashboard detail page.

## Scope

In scope:

- Admin route split: dashboard entry vs course detail
- Entry KPIs and course list
- Click-through navigation to existing detail view
- Backend aggregation API for entry metrics
- i18n keys and basic loading/error states

Out of scope:

- Redesign of course-level detail charts/tables
- New BI dimensions beyond requested metrics
- Historical data backfill or ETL jobs

## User Flow

1. User opens `/admin/dashboard`
2. Page shows four KPI cards and a course list
3. User clicks one course row/card
4. Browser navigates to `/admin/dashboard/shifu/{shifu_bid}`
5. Existing detail dashboard is displayed for that course

## Routing Plan

### New routes

- `GET /admin/dashboard`
  - New entry page
- `GET /admin/dashboard/shifu/[shifu_bid]`
  - Existing detail page content (moved from current `/admin/dashboard`)

### Backward compatibility

- Keep sidebar link pointing to `/admin/dashboard`
- Optional: if old deep links exist, support redirect from legacy query mode to `/admin/dashboard/shifu/{shifu_bid}`

## Backend Plan

## New endpoint

- `GET /api/dashboard/entry`

Query params:

- `start_date` (optional, `YYYY-MM-DD`)
- `end_date` (optional, `YYYY-MM-DD`)
- `keyword` (optional, search by course name/bid)
- `page_index` (default `1`)
- `page_size` (default `20`, max `100`)

Response shape:

```json
{
  "summary": {
    "course_count": 0,
    "learner_count": 0,
    "order_count": 0,
    "generation_count": 0
  },
  "page": 1,
  "page_size": 20,
  "page_count": 1,
  "total": 0,
  "items": [
    {
      "shifu_bid": "",
      "shifu_name": "",
      "learner_count": 0,
      "order_count": 0,
      "generation_count": 0,
      "last_active_at": ""
    }
  ]
}
```

## Metric definitions

- `course_count`: visible non-archived courses for current creator/collaborator
- `learner_count`: distinct `user_bid` in `learn_progress_records` for selected courses
- `order_count`: total non-deleted orders in `order_orders` for selected courses
- `generation_count`: total follow-up ask records in `learn_generated_blocks` (`type = MDASK`)

Note: if product expects a different meaning for “generation”, adjust before implementation.

## Permission model

- Reuse current creator/admin access checks from dashboard/order flows
- Data must be restricted to courses visible to current user

## Query strategy

- Reuse `get_user_created_shifu_bids(...)` as base course scope
- Aggregate using grouped queries and Python merge maps
- Avoid N+1 queries by batching with `IN (...)` and chunking when needed
- Date range applies to time-based metrics (orders/generation/active)

## Frontend Plan

## Page structure

- `src/cook-web/src/app/admin/dashboard/page.tsx`
  - New entry page UI
  - KPI cards: courses/learners/orders/generation
  - Course list (table or cards)
  - Date range filter (reuse existing `DateRangeFilter` pattern)
  - Click course => `router.push('/admin/dashboard/shifu/${shifuBid}')`

- `src/cook-web/src/app/admin/dashboard/shifu/[shifu_bid]/page.tsx`
  - Move current course-level dashboard implementation here
  - Keep existing learner detail sheet and charts unchanged

## API integration

Add in `src/cook-web/src/api/api.ts`:

- `getDashboardEntry: 'GET /dashboard/entry'`

Add new TS types in `src/cook-web/src/types/dashboard.ts`:

- `DashboardEntrySummary`
- `DashboardEntryCourseItem`
- `DashboardEntryResponse`

## i18n

Add keys in:

- `src/i18n/en-US/modules/dashboard.json`
- `src/i18n/zh-CN/modules/dashboard.json`

Suggested key groups:

- `module.dashboard.entry.kpi.courses`
- `module.dashboard.entry.kpi.learners`
- `module.dashboard.entry.kpi.orders`
- `module.dashboard.entry.kpi.generations`
- `module.dashboard.entry.table.course`
- `module.dashboard.entry.table.learners`
- `module.dashboard.entry.table.orders`
- `module.dashboard.entry.table.generations`
- `module.dashboard.entry.table.lastActive`
- `module.dashboard.entry.table.empty`

Then run:

- `python scripts/check_translations.py`
- `python scripts/check_translation_usage.py --fail-on-unused`
- `cd src/cook-web && npm run i18n:keys`

## Test Plan

Backend:

- Unit/integration tests for `/api/dashboard/entry`
- Verify permission scope
- Verify date-range filtering
- Verify pagination and keyword filtering
- Verify metric calculations on mixed sample data

Frontend:

- Entry page renders loading/error/empty/data states
- Click course navigates to detail route
- Detail route still loads existing per-course data
- i18n keys resolve in both `en-US` and `zh-CN`

## Risks and Mitigations

1. Metric ambiguity (`generation_count`, `order_count` status scope)
   - Mitigation: lock definitions before coding, keep DTO extensible.
2. Large dataset aggregation latency
   - Mitigation: indexed filters, grouped queries, optional pagination-first loading.
3. Route migration regressions
   - Mitigation: keep existing detail logic intact and move with minimal refactor.

## Acceptance Criteria

1. `/admin/dashboard` shows requested 4 KPI totals and course list.
2. Clicking a course enters the existing detail dashboard behavior.
3. Existing dashboard detail metrics/charts/learner drill-down still work.
4. New strings are fully i18n-compliant.
5. Relevant tests and pre-commit checks pass.
