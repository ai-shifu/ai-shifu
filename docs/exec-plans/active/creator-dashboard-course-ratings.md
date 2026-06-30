# Creator Dashboard Course Ratings

## Purpose / Big Picture

Add a creator-facing course rating third-level page under the dashboard course
detail flow. The course detail page already exposes core metrics, a learner
list, and a follow-up page. This task extends the same information architecture
with a sibling ratings page so creators can review course feedback in a
course-scoped, breadcrumb-driven flow and jump into ratings from the detail
metric card.

The work spans backend dashboard DTOs/routes/queries, frontend route wiring,
shared dashboard types/API bindings, i18n, and focused regression tests, so it
needs an ExecPlan to keep the contract and validation path legible.

## Progress

- [x] 2026-05-19 11:25 CST: Reviewed the current creator dashboard detail and
  follow-up implementation plus the operator ratings reference page/backend.
- [x] 2026-05-19 11:35 CST: Defined the creator-facing rating contract and
  wired the backend DTOs, detail metric, and list route.
- [x] 2026-05-19 11:55 CST: Built the dashboard ratings page, breadcrumb flow,
  and detail-page rating entry point using shared components.
- [x] 2026-05-19 12:20 CST: Added focused backend/frontend tests, regenerated
  i18n keys, and ran narrow validation (`pytest`, dashboard Jest tests, and
  frontend type-check).

## Surprises & Discoveries

- The branch already contains a substantial creator dashboard detail revamp,
  including learner drill-down and a sibling follow-up page, so the ratings
  page should mirror that route structure instead of inventing a new pattern.
- The operator rating flow already solves most raw query and UI problems; the
  creator variant should reuse the shape selectively while trimming
  operator-only filters and columns.

## Decision Log

- Decision: keep the creator ratings page simpler than the operator page by
  omitting operator-only filters such as mode sorting toggles unless the
  creator view clearly benefits from them.
  - Why: the user asked for a creator-oriented field set, not a one-to-one
    clone of the operator console.
- Decision: expose rating average on the creator detail metrics payload and
  make the metric card clickable to the ratings page.
  - Why: this matches the follow-up and order drill-down pattern already
    established on the dashboard detail page.

## Outcomes & Retrospective

- The creator dashboard now exposes ratings as a first-class sibling page to
  follow-ups, with matching breadcrumb behavior and creator-focused fields.
- Reusing the operator reference made it straightforward to add the query path
  while still trimming creator-unneeded fields such as mode and sort controls.

## Context and Orientation

- Backend entry points:
  - `src/api/flaskr/service/dashboard/dtos.py`
  - `src/api/flaskr/service/dashboard/funcs.py`
  - `src/api/flaskr/service/dashboard/routes.py`
  - `src/api/tests/service/dashboard/test_dashboard_routes.py`
- Frontend entry points:
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/page.tsx`
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/follow-ups/page.tsx`
  - `src/cook-web/src/app/admin/dashboard/admin-dashboard-routes.ts`
  - `src/cook-web/src/api/api.ts`
  - `src/cook-web/src/types/dashboard.ts`
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/page.test.tsx`
- Operator reference:
  - `src/api/flaskr/service/shifu/admin.py`
  - `src/cook-web/src/app/admin/operations/[shifu_bid]/ratings/page.tsx`
  - `src/cook-web/src/app/admin/operations/operation-course-types.ts`

## Plan of Work

1. Reuse the existing dashboard ownership checks and course outline context map
   to add a creator-scoped ratings query path.
2. Extend the course detail metrics payload with average score so the dashboard
   detail page can show and link the rating metric consistently.
3. Add a ratings page under `/admin/dashboard/[shifu_bid]/ratings` using shared
   filters, summary cards, table shell, pagination, and breadcrumb components.
4. Update i18n/tests and validate the backend and frontend contract end to end.

## Concrete Steps

1. Add creator dashboard rating DTOs and the new detail metric field.
2. Implement a course ratings query helper in `dashboard/funcs.py`.
3. Register `GET /api/dashboard/shifus/<shifu_bid>/ratings`.
4. Add frontend API/type/route helpers for creator ratings.
5. Build the ratings page and hook up the detail metric card navigation.
6. Update tests, regenerate i18n keys, and run focused checks.

## Validation and Acceptance

- Backend detail response includes a creator-facing `rating_score` metric.
- `GET /api/dashboard/shifus/<shifu_bid>/ratings` returns creator-scoped rating
  summary and paginated rating rows.
- The dashboard course detail page shows a non-placeholder rating value when
  ratings exist and opens the ratings page on click.
- The ratings page renders clickable breadcrumbs back to dashboard and course
  detail, supports the intended filters, and shows creator-relevant columns.
- Focused backend/frontend tests pass, plus i18n keys regenerate cleanly.

## Idempotence and Recovery

- Route and DTO changes are additive; rerunning validations should be safe.
- If the rating route shape needs revision, keep the detail metric and ratings
  page loosely coupled through shared types so either side can be adjusted
  without reverting unrelated dashboard work.

## Interfaces and Dependencies

- Uses existing dashboard auth ownership checks from
  `_load_dashboard_course_meta_map`.
- Depends on `LearnLessonFeedback` for score/comment/mode/rated time data.
- Reuses operator helper patterns from `flaskr.service.shifu.admin` for
  average-score formatting and outline context assembly.
- Reuses shared frontend components:
  `AdminDateRangeFilter`, `AdminPagination`, `AdminTableShell`,
  `AdminTooltipText`, `Breadcrumb`, and card components.
