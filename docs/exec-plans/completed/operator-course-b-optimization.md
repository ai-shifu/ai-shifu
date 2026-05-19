# Operator Course B Optimization

## Purpose / Big Picture

Turn the operator course management performance work from the current "A plan"
incremental relief into the longer-term "B plan" backend optimization. The goal
is to keep the operator course list behavior and business definitions stable
while pushing course filtering, sorting, pagination, quick filters, and
overview-heavy scans closer to SQL so the page remains fast as course volume
grows.

This plan intentionally focuses on the backend request chain first. The current
frontend already delays overview loading after the list request, so the next
large gains come from reducing full-set Python merging and full-set activity
scans inside `list_operator_courses(...)` and `_build_operator_course_overview`.

## Progress

- [x] 2026-05-19 17:10 CST: Reviewed the requirement record in
  `docs/需求和优化.md` and confirmed B is still the correct follow-up after A.
- [x] 2026-05-19 17:20 CST: Audited the current `main` implementation of
  `list_operator_courses(...)` and `_build_operator_course_overview(...)`.
- [x] 2026-05-19 17:35 CST: Freeze the non-negotiable course list behavior
  baseline before changing query shape.
- [x] 2026-05-19 17:45 CST: Design the SQL-first candidate course query for the
  operator list path.
- [x] 2026-05-19 18:00 CST: Split the implementation into safe backend phases
  with explicit regression coverage gates.
- [x] 2026-05-19 17:55 CST: Added SQL-path regression coverage for merge
  precedence, demo-course visibility, and outline-activity ordering.
- [x] 2026-05-19 18:20 CST: Reworked operator course list to build SQL-first
  candidate rows, apply status/created/quick-filter preselection in SQL, and
  preserve `updated_at` semantics with candidate-scoped activity resolution.
- [x] 2026-05-19 18:25 CST: Reworked course overview to aggregate directly from
  SQL candidate rows and joined 30-day activity/order metrics.
- [x] 2026-05-19 18:30 CST: Verified
  `cd src/api && pytest -q tests/service/shifu/test_admin_courses.py` passes.
- [x] 2026-05-19 18:55 CST: Addressed PR feedback, removed the private SQLAlchemy engine gate, and prepared the plan for archive after regenerating harness docs.

## Surprises & Discoveries

- A plan improved the page by moving list field enrichment to page-sized rows,
  but the list path still loads both latest-draft and latest-published course
  sets, merges them in Python, computes activity for the merged set, applies
  multiple filters in Python, then sorts and paginates afterward.
- `_build_operator_course_overview(...)` still performs a full-set scan of
  merged visible courses and then issues 30-day activity / paid-order lookups
  across all visible `shifu_bid`s.
- The slowest remaining behavior is no longer "page field enrichment"; it is
  the persistence of full-set candidate computation and full-set post-processing
  before pagination.
- `updated_at` ordering remains tightly coupled to the activity fallback rule:
  `activity.updated_at or course.updated_at`. This is the most fragile contract
  to preserve during SQL-ization.
- A fully inlined SQL activity query with repeated candidate subqueries became
  too large for SQLite test parsing (`parser stack overflow`), even though the
  production direction is still valid for MySQL.
- The practical safe shape for this branch is therefore hybrid:
  - candidate selection / status / created-time / quick-filter preselection in
    SQL
  - activity resolution against the already-filtered candidate set in Python
  - overview aggregates fully SQL-backed

## Decision Log

- Decision: plan B as a staged backend refactor instead of a one-shot rewrite.
  - Why: the course list behavior is already heavily regression-tested, and the
    safest path is to move one cost center at a time while preserving DTOs.
- Decision: treat `updated_at` ordering as the primary invariant.
  - Why: prior debugging already showed this field is business-sensitive and
    easy to break when changing execution order.
- Decision: keep the frontend contract unchanged for B.
  - Why: A already moved overview timing on the page; B should now harvest
    backend gains without reopening page-level UI risk.
- Decision: separate list SQL-ization from overview caching.
  - Why: caching can hide inefficient query design; the list path should become
    structurally cheaper before cache is introduced.
- Decision: keep a legacy fallback path when the current Flask app is not bound
  to the active `SQLAlchemy` instance.
  - Why: several unit tests create bare `Flask(__name__)` apps with mocked
    loaders; preserving that path keeps low-friction behavior tests stable.
- Decision: stop short of fully SQL-joining outline activity in the list path
  for this branch.
  - Why: the candidate-scoped hybrid version preserves behavior while avoiding
    pathological SQL compilation in SQLite-based tests.

## Outcomes & Retrospective

- This branch completes the planned B-optimization scope for the operator
  course page backend:
  - latest draft/published course candidate selection now happens in SQL
  - status / created-time / draft-published quick-filter preselection is no
    longer tied to Python full-set merge logic
  - overview counts now come from SQL aggregates instead of full merged course
    scans
- The list path still computes final `updated_at` ordering from activity in
  Python, but it now does so on the already SQL-filtered candidate set instead
  of after the old all-visible merge chain.
- Success here is still "same business result, lower cost profile"; this branch
  intentionally prioritizes that over a more aggressive but brittle full-SQL
  activity rewrite.

## Context and Orientation

Relevant files and surfaces:

- Requirement record:
  - `docs/需求和优化.md`
- Current frontend page:
  - `src/cook-web/src/app/admin/operations/page.tsx`
- Current backend course list and overview:
  - `src/api/flaskr/service/shifu/admin.py`
- Current operator course tests:
  - `src/api/tests/service/shifu/test_admin_courses.py`

Current `main` behavior summary:

1. `src/cook-web/src/app/admin/operations/page.tsx` loads the course list first
   and then asynchronously loads overview, which is the A-plan frontend change.
2. `list_operator_courses(...)` in
   `src/api/flaskr/service/shifu/admin.py` still:
   - resolves creator matches
   - loads latest draft seeds
   - loads latest published seeds
   - merges them in Python
   - computes activity for the merged candidate set
   - applies course status / updated time / quick-filter logic in Python
   - sorts in Python
   - paginates after the above work
3. `_build_operator_course_overview(...)` still loads latest draft and latest
   published rows for all visible courses, merges them, then computes multiple
   counts from the full merged set.

Known behavior that must not change:

- draft vs. published merge precedence
- `course_status` definitions
- `updated_at` sorting semantics
- quick filter result sets:
  - draft
  - published
  - created last 7 days
  - learning active last 30 days
  - paid order last 30 days
- creator keyword matching
- DTO shape returned to the frontend

## Plan of Work

1. Freeze the existing business invariants in tests and implementation notes.
2. Design a SQL-first course candidate query that selects the effective course
   row per `shifu_bid` before Python receives the result set.
3. Move status filtering, quick filters, and primary sorting to SQL or SQL
   subqueries where safe.
4. Reduce activity resolution to page-sized or SQL-joined work instead of
   merged full-set scans.
5. Revisit overview with either lighter aggregate queries or short-lived cache
   after the list query shape stabilizes.

## Concrete Steps

1. Add a behavior baseline section to `test_admin_courses.py` if any current
   merge/order/filter rule is not yet explicitly covered.
2. Introduce a backend helper that can build the effective course candidate set
   in SQL terms instead of only via Python `_merge_courses(...)`.
3. Move list-level filters in this order:
   - `course_status`
   - `created_at` range
   - `creator_keyword` matched bids
   - quick filters that already have natural SQL subqueries
4. Add an `updated_at`-aware SQL or subquery strategy that keeps the current
   activity fallback semantics.
5. Paginate at the database layer before page-field enrichment.
6. Keep page enrichment limited to the final page rows:
   - prompt flag
   - creator / modifier display data
   - page-row activity metadata
7. After list stabilization, design overview optimization separately:
   - short cache, or
   - lighter aggregate query path, or
   - both, if needed and still behavior-safe

## Validation and Acceptance

- List result order for no-filter page 1 remains unchanged.
- `course_status`, created time, updated time, and creator search results remain
  unchanged.
- Quick filters remain unchanged:
  - draft
  - published
  - created last 7 days
  - learning active last 30 days
  - paid order last 30 days
- Returned DTO fields remain unchanged for the frontend page.
- Focused backend tests in `src/api/tests/service/shifu/test_admin_courses.py`
  pass.
- Frontend page tests for operator course management remain green if any page
  timing assumptions need adjustment.

## Idempotence and Recovery

- Each phase should land independently so the branch can stop after list
  SQL-ization even if overview caching is deferred again.
- If `updated_at` ordering becomes unstable, revert to the prior helper or gate
  the SQL branch behind the old behavior until the discrepancy is resolved.
- If a quick filter changes result membership, pause and add a focused failing
  regression test before attempting another optimization.

## Interfaces and Dependencies

- Backend service surface:
  - `list_operator_courses(...)`
  - `_build_operator_course_overview(...)`
  - `_load_course_activity_map(...)`
  - `_load_recent_learning_active_course_bids(...)`
  - `_load_recent_paid_order_course_bids(...)`
- Frontend consumer:
  - `src/cook-web/src/app/admin/operations/page.tsx`
- Test surface:
  - `src/api/tests/service/shifu/test_admin_courses.py`
- Requirement source:
  - `docs/需求和优化.md`
