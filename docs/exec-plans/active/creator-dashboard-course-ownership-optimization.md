# Creator Dashboard Course Ownership Optimization

## Purpose / Big Picture

The creator dashboard now uses separate, SQL-optimized learners and ratings
list endpoints, but its course-scoped backend handlers still verify ownership
by loading the creator's full visible course map and then plucking one course
from it. This task tightens course-scoped endpoints to resolve ownership at
single-course granularity while preserving the existing creator-facing behavior
and error semantics.

## Progress

- [x] 2026-05-20 14:20 CST: Reviewed current ownership helper usage across the
  creator dashboard course-scoped handlers.
- [x] 2026-05-20 14:25 CST: Add a single-course ownership lookup helper and
  switch course-scoped handlers to use it.
- [x] 2026-05-20 14:30 CST: Sync optimization docs, generated harness docs, and
  rerun focused backend verification.

## Surprises & Discoveries

- The dashboard entry page still legitimately needs the full course map because
  it lists all visible courses; only the course-scoped endpoints benefit from
  this optimization.
- The current semantics intentionally treat shared-but-not-owned courses as
  "not found" for creator dashboard routes, so the new helper must keep that
  behavior.

## Decision Log

- Decision: keep `_load_dashboard_course_meta_map` for the entry page and add a
  new single-course helper for course-scoped routes.
  - Why: it avoids over-optimizing the one path that still needs the full set.
- Decision: preserve the existing `server.shifu.shifuNotFound` outcome when the
  target course is not creator-owned.
  - Why: tests and route semantics already rely on that behavior.

## Outcomes & Retrospective

- Course-scoped creator dashboard routes now resolve ownership without loading
  the creator's full visible course map first.
- The entry page still uses the full map by design, so the optimization stays
  targeted to the routes that benefit from it.

## Context and Orientation

- Main backend entry point:
  - `src/api/flaskr/service/dashboard/funcs.py`
- Tests/docs:
  - `src/api/tests/service/dashboard/test_dashboard_routes.py`
  - `docs/需求和优化.md`

## Plan of Work

1. Add a single-course creator ownership lookup helper.
2. Swap course detail, learners, follow-ups, follow-up detail, and ratings to
   the new helper.
3. Leave entry-page list building on the existing full-map helper.
4. Sync docs and rerun focused backend verification.

## Concrete Steps

1. Implement `_load_dashboard_course_meta(user_id, shifu_bid)`.
2. Replace map-based lookups in course-scoped handlers.
3. Update optimization docs to mark ownership tightening complete.
4. Regenerate harness docs and rerun dashboard pytest.

## Validation and Acceptance

- Course-scoped creator dashboard endpoints still return the same payloads and
  still reject non-owned courses with the same error semantics.
- Course ownership for course-scoped endpoints is resolved without loading the
  creator's full visible course map.
- Focused dashboard backend tests pass.

## Idempotence and Recovery

- The helper is internal and additive, so reverting a single route back to the
  map-based lookup would stay localized if a corner case appears.
- Entry-page behavior remains isolated from this optimization because it still
  uses the full course map helper.

## Interfaces and Dependencies

- Depends on `PublishedShifu` and the demo-course exclusion helper.
- Shares creator-visibility semantics with the rest of
  `src/api/flaskr/service/dashboard/funcs.py`.
