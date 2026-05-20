# Creator Dashboard Request Splitting

## Purpose / Big Picture

The creator dashboard course detail page currently couples course summary metrics
and the learner list into a single request. That means every learner search,
filter change, and pagination change refetches the summary payload even though
only the learner table changed. This task splits the request contract so the
course detail route returns summary/basic information only, while a new
course-scoped learners route serves the learner table.

The work spans backend DTOs/routes/tests, frontend request wiring/state
management, and follow-up documentation for later API optimization phases, so
it needs an ExecPlan to keep the contract and validation path explicit.

## Progress

- [x] 2026-05-20 12:45 CST: Reviewed the current dashboard detail, learners,
  ratings, and route parsing implementations plus the affected tests.
- [x] 2026-05-20 12:50 CST: Split the backend detail/learners contract and add
  strict pagination parsing.
- [x] 2026-05-20 12:55 CST: Update the frontend detail page to fetch summary and
  learners independently with request race protection.
- [x] 2026-05-20 13:00 CST: Record deferred optimization ideas in
  `docs/需求和优化.md` and run focused backend/frontend verification.
- [x] 2026-05-20 13:10 CST: Sync the shared demand/optimization doc with the
  final A-phase completion status and validation summary.

## Surprises & Discoveries

- The current learner list is still built in Python after loading the full
  learner set, so request splitting reduces redundant transfers now but does
  not yet solve the deeper query-scope cost.
- The follow-ups and ratings pages already contain request-id race protection,
  which gives a clear local pattern to reuse on the detail page.

## Decision Log

- Decision: add a dedicated `GET /api/dashboard/shifus/<shifu_bid>/learners`
  route instead of overloading the detail route.
  - Why: it matches the product spec and isolates the paginated/filterable
    table contract.
- Decision: change invalid `page_index` / `page_size` parsing from silent
  fallback to `raise_param_error(...)`.
  - Why: invalid query args should fail predictably instead of masking client
    bugs.
- Decision: defer DB-side learner/ratings pagination and filtering to a later
  phase documented in `docs/需求和优化.md`.
  - Why: the user asked to land the contract split first and keep deeper
    optimization as a later iteration.

## Outcomes & Retrospective

- The creator dashboard detail page now avoids refetching summary data on every
  learner-table interaction by splitting summary and learners into separate
  requests.
- Strict pagination parsing now makes bad dashboard query args fail fast,
  which keeps frontend/backend contract drift easier to detect.

## Context and Orientation

- Backend entry points:
  - `src/api/flaskr/service/dashboard/routes.py`
  - `src/api/flaskr/service/dashboard/funcs.py`
  - `src/api/flaskr/service/dashboard/dtos.py`
  - `src/api/tests/service/dashboard/test_dashboard_routes.py`
- Frontend entry points:
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/page.tsx`
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/page.test.tsx`
  - `src/cook-web/src/api/api.ts`
  - `src/cook-web/src/types/dashboard.ts`
- Follow-up references for request-id protection:
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/follow-ups/page.tsx`
  - `src/cook-web/src/app/admin/dashboard/[shifu_bid]/ratings/page.tsx`

## Plan of Work

1. Split the backend DTO and route contract so detail and learners can be
   fetched independently.
2. Preserve the current learner-table UI behavior while moving learner fetching
   to its own request/state path.
3. Harden pagination parsing at the route boundary and cover the behavior with
   targeted tests.
4. Record deferred Phase B API/query optimizations in the shared demand/upgrade
   document.

## Concrete Steps

1. Add request helpers in dashboard routes for timezone and pagination parsing.
2. Add `build_dashboard_course_learners(...)` and register the new learners
   route.
3. Remove `learners` from `DashboardCourseDetailDTO` and update backend tests.
4. Add `getDashboardCourseLearners` to the frontend API map and split detail
   page state/fetch effects.
5. Update dashboard detail Jest coverage for the two-request flow.
6. Append the deferred query optimization notes to `docs/需求和优化.md`.
7. Run focused pytest/Jest/type-check/harness regeneration validations.

## Validation and Acceptance

- `GET /api/dashboard/shifus/<shifu_bid>/detail` returns only basic info and
  metrics.
- `GET /api/dashboard/shifus/<shifu_bid>/learners` returns the paginated learner
  table with the current filters.
- Invalid `page_index` or `page_size` values on dashboard paginated routes
  return `Params Error page_index` or `Params Error page_size`.
- The creator dashboard detail page loads course summary data once and refetches
  only learners when learner filters or pagination change.
- Focused backend/frontend tests pass, and repository harness docs stay in sync.

## Idempotence and Recovery

- The new learners route is additive, so reverting the frontend split would not
  require backing out unrelated backend metrics work.
- If the learners route shape needs further tuning later, the detail page now
  isolates summary and table state so each side can evolve independently.

## Interfaces and Dependencies

- Uses existing dashboard ownership checks via `_load_dashboard_course_meta_map`.
- Reuses the existing learner DTOs and learner-row builder helper.
- Reuses `DashboardCourseLearnersCard` and the shared request utilities on the
  frontend.
- Documentation updates should remain aligned with the repository harness via
  the generator/checker scripts.
