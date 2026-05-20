# Creator Dashboard Learners SQL Optimization

## Purpose / Big Picture

The creator dashboard course detail page already split summary and learners into
separate requests. The next bottleneck is inside the learners endpoint itself:
it still loads the full learner set, then filters, sorts, and paginates in
Python. This task pushes the creator learner list closer to SQL while keeping
the current response contract and creator-facing behavior stable.

## Progress

- [x] 2026-05-20 13:35 CST: Reviewed the current creator learner helper,
  related aggregation helpers, and the existing tests that lock current
  behavior.
- [x] 2026-05-20 13:45 CST: Reworked the learner endpoint to build filtered,
  ordered, paginated learner rows from SQL subqueries and only hydrate contacts
  for the current page.
- [x] 2026-05-20 13:50 CST: Sync the shared optimization doc and generated
  harness docs, then run focused verification.

## Surprises & Discoveries

- The current learner contract depends on a mix of progress, manual-order, auth,
  and credential data, so full SQL replacement still needs a small page-scoped
  contact hydration step.
- Joined-at semantics are subtle because the displayed value is the earliest of
  successful order time, auth grant time, and first learning time.

## Decision Log

- Decision: keep page-row contact formatting on the existing helper and only
  SQL-optimize filtering/sorting/pagination.
  - Why: it preserves current phone/email fallback semantics while shrinking the
    expensive part of the request path.
- Decision: preserve the current learning-status rules instead of redefining
  them for SQL convenience.
  - Why: frontend expectations and existing tests already rely on the creator
    definitions of `not_started`, `learning`, and `completed`.

## Outcomes & Retrospective

- The creator learners endpoint now keeps the old DTO but avoids building the
  full learner result set in Python before pagination.
- The remaining non-SQL work is intentionally narrow: only the current page's
  contact display fields are hydrated through the existing helper so creator UI
  semantics stay unchanged.

## Context and Orientation

- Main backend entry point:
  - `src/api/flaskr/service/dashboard/funcs.py`
- Route/tests/doc surfaces:
  - `src/api/flaskr/service/dashboard/routes.py`
  - `src/api/tests/service/dashboard/test_dashboard_routes.py`
  - `docs/需求和优化.md`

## Plan of Work

1. Replace Python-side learner filtering and ordering with SQL subqueries.
2. Preserve the current DTO shape and current creator-side filter semantics.
3. Update optimization docs to reflect that B-phase learner SQL work is done.
4. Run focused backend verification and refresh generated harness docs.

## Concrete Steps

1. Build learner-source, last-learning, joined-at, learned-lesson, and
   follow-up-count subqueries.
2. Apply keyword, learning-status, and date filters in SQL.
3. Count, clamp page index, and fetch only the paged learner rows from SQL.
4. Hydrate page-row contact fields, update docs, and rerun focused checks.

## Validation and Acceptance

- Learner search, learning-status filter, recent-learning date filter, sorting,
  and pagination all behave the same as before.
- The endpoint no longer materializes the full learner DTO list before
  pagination.
- Focused dashboard backend tests pass.

## Idempotence and Recovery

- The optimized query path keeps the old response DTO, so frontend callers do
  not need follow-up changes.
- If a query edge case appears later, the old helper decomposition still makes
  it possible to swap a single aggregation subquery without undoing the request
  split work.

## Interfaces and Dependencies

- Depends on `LearnProgressRecord`, `Order`, `AiCourseAuth`,
  `LearnGeneratedBlock`, `AuthCredential`, and `UserInfo`.
- Shares route/query semantics with the creator dashboard detail page and the
  optimization notes in `docs/需求和优化.md`.
