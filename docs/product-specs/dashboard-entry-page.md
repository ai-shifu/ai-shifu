---
title: Dashboard Entry Page Contract
status: implemented
owner_surface: shared
last_reviewed: 2026-09-26
canonical: true
---

# Dashboard Entry Page Contract

## Entry And Navigation

`/admin/dashboard` shows course count, distinct learner count, successful order
count, successful order amount, and a paginated course table. The View Course
action opens `/admin/dashboard/{shifu_bid}`; the course name and row are not
navigation triggers. Follow-ups and ratings are sibling detail
pages below that course route. Build links through
[admin-dashboard-routes.ts](../../src/web/src/app/admin/dashboard/admin-dashboard-routes.ts).
The frontend detail path does not contain a `/shifu/` segment.

The [teacher dashboard specification](teacher-analytics-dashboard.md) owns the
course-detail behavior. This document owns only the entry page and its API.

## API Contract

`GET /api/dashboard/entry` returns the shared `code`, `message`, `data` envelope.
The data shape is defined by
[DashboardEntryDTO](../../src/api/flaskr/service/dashboard/dtos.py):

```json
{
  "summary": {
    "course_count": 0,
    "learner_count": 0,
    "order_count": 0,
    "order_amount": "0.00"
  },
  "page": 1,
  "page_size": 20,
  "page_count": 0,
  "total": 0,
  "items": []
}
```

Each item has `shifu_bid`, `shifu_name`, `learner_count`, `order_count`,
`order_amount`, and `last_active_at`. Amounts are strings with two decimal
places. Activity is UTC ISO-8601 with `Z`, or `null`; it is not an empty string.
`generation_count` is not part of this response.

Query parameters are optional `start_date` / `end_date` (`YYYY-MM-DD`),
`keyword`, `page_index` (default 1), and `page_size` (default 20, capped at 100).
Pagination syntax is validated at the route boundary. With neither date, all
time is selected. A missing end resolves to today's UTC date; a missing start
resolves to 13 days before the end. The inclusive range may span at most 366
days and becomes a half-open UTC interval. Response timestamps are never
localized by the request's timezone parameter.

## Scope And Metrics

- The course scope contains the current user's owned eligible courses;
  shared-only and built-in demo courses are excluded. Keyword filtering uses
  the shared course-loading path.
- Learners are the distinct union of users with non-reset, non-deleted progress
  and users imported through successful manual orders. Ordinary purchases
  alone do not make a user a learner. Summary learners are deduplicated across
  all selected courses, rather than summed from per-course counts.
- Orders include successful, non-deleted course orders, including nonzero
  manual orders. Amount sums `paid_price`; unsuccessful orders are excluded.
- Date filtering applies to progress/order creation timestamps for counts and
  progress update timestamps for last activity. With a date range, only courses
  with matching learner or order activity remain in the list and course count.
- Summary metrics cover the filtered course scope before pagination. Empty
  results have zero counts, `"0.00"` amount, zero pages, and an empty item list.

The implementation is
[build_dashboard_entry](../../src/api/flaskr/service/dashboard/funcs.py).
Preserve its scope, UTC boundaries, and summary-versus-page distinction when
optimizing queries. Use the query guidance in the teacher dashboard spec.

## UI And Verification

The entry page handles loading, empty, error, keyword, date, and pagination
states. It consumes the shared dashboard API and translations; all supported
locales come from [the shared locale list](../../src/i18n/locales.json).

Existing regression evidence:

- [Backend dashboard routes](../../src/api/tests/service/dashboard/test_dashboard_routes.py)
  cover ownership, shared/demo exclusions, manual-import learner inclusion,
  successful-order metrics, date filtering, pagination, and UTC serialization.
- [Entry page tests](../../src/web/src/app/admin/dashboard/page.test.tsx)
  cover the UI request and navigation behavior.
- [Query contract tests](../../src/api/tests/service/dashboard/test_dashboard_query_contracts.py)
  cover invalid date ranges and activity filtering, alongside follow-up source
  and identity constraints. Page-scoped hydration is an implementation pattern,
  not a regression guarantee asserted by this test file.

This contract records the implemented behavior; new metrics require an explicit
product change and matching producer/consumer tests.
