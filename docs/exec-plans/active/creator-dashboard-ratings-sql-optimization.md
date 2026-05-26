# Creator Dashboard Ratings SQL Optimization

## Purpose / Big Picture

The creator dashboard ratings page already exists, but its backend still loads
all course ratings into Python before applying learner keyword filters, chapter
filters, score/comment filters, date filters, sorting, and pagination. This
work pushes the expensive list shaping into SQL while keeping the current
creator-facing response contract, summary semantics, and frontend behavior
unchanged.

## Progress

- [x] 2026-05-20 13:55 CST: Reviewed the current creator ratings query,
  current summary semantics, and the dashboard route tests that pin behavior.
- [x] 2026-05-20 14:05 CST: Reworked the ratings endpoint to apply filters,
  ordering, counting, and pagination in SQL while hydrating only current-page
  user/contact/context data.
- [x] 2026-05-20 14:10 CST: Sync the shared optimization doc and generated
  harness docs, then rerun focused verification.

## Surprises & Discoveries

- The ratings page summary is intentionally full-course summary data rather than
  "current filter result" data, so the SQL refactor must keep two distinct
  query paths.
- Chapter keyword filtering depends on outline context resolution; the simplest
  stable path is to precompute matching outline ids from the existing context
  map, then apply the actual rating-row filter in SQL.

## Decision Log

- Decision: keep the existing full-summary semantics while SQL-optimizing only
  the list query path.
  - Why: current tests and creator UI expectations already rely on that split.
- Decision: reuse the creator learner keyword SQL helper for ratings user
  keyword filtering.
  - Why: the matching rules stay consistent across learners, follow-ups, and
    ratings.

## Outcomes & Retrospective

- The creator ratings endpoint now keeps the old response shape and full-summary
  semantics while avoiding full in-memory list filtering for the paged list.
- The remaining non-SQL work is deliberately page-scoped hydration for display
  fields, which keeps current creator UI semantics stable.

## Context and Orientation

- Main backend entry point:
  - `src/api/flaskr/service/dashboard/funcs.py`
- Tests/docs:
  - `src/api/tests/service/dashboard/test_dashboard_routes.py`
  - `docs/需求和优化.md`

## Plan of Work

1. Replace Python-side ratings filtering and pagination with SQL.
2. Preserve the existing creator-facing DTO and summary behavior.
3. Update shared optimization docs to mark ratings SQL work complete.
4. Regenerate harness docs and rerun focused dashboard backend verification.

## Concrete Steps

1. Build the base ratings query with a reusable `rated_at` expression.
2. Apply keyword, chapter, score, comment, and date filters in SQL.
3. Count/filter/order/page in SQL and hydrate only current-page display data.
4. Sync docs and rerun focused checks.

## Validation and Acceptance

- Ratings keyword, chapter keyword, score, comment, and date filters behave the
  same as before.
- The ratings endpoint no longer materializes the full rating row list before
  pagination.
- The summary payload still reflects full-course ratings rather than filtered
  list results.
- Focused dashboard backend tests pass.

## Idempotence and Recovery

- The response DTO is unchanged, so frontend callers do not need contract
  updates.
- If a specific filter needs follow-up tuning later, the base query and summary
  query are now separated cleanly.

## Interfaces and Dependencies

- Depends on `LearnLessonFeedback`, `UserInfo`, `AuthCredential`, and the
  dashboard outline-context helpers.
- Shares filter semantics with the creator learners/follow-ups request paths and
  the optimization tracking in `docs/需求和优化.md`.
