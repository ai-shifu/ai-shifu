# Rebuild Course Visit Analytics Without Umami Data Reads

## Purpose / Big Picture

Replace the dormant operator course-visitor implementation introduced by
#1527 with a product-owned measurement path. The current implementation emits
a dynamic Umami event and asks the backend to read Umami statistics while
building the operator course detail response. That makes best-effort telemetry
part of a product API contract, even though the corresponding metric card has
already been removed from the UI.

The work is deliberately split into two pull requests. The first removes the
unused Umami-derived metric and every contract that exists only to support it.
The second is stacked on that cleanup and rebuilds the original product goal:
showing operators the number of distinct logged-in learners who opened a
course in the last 30 days, using first-party application data as the source of
truth.

## Progress

- [x] 2026-08-30 17:15 CST: Audited the current producer, backend reader,
      operator API field, hidden frontend contract, tests, configuration, and
      product specification.
- [x] 2026-08-30 17:15 CST: Created
      `sunner/remove-umami-data-dependency` from the latest `origin/main` for the
      independent cleanup pull request.
- [x] 2026-08-30 17:22 CST: Removed the obsolete #1527 implementation,
      regenerated env/i18n/knowledge artifacts, and passed focused backend,
      frontend, type, translation, harness, architecture, and tooling checks.
- [x] 2026-08-30 17:25 CST: Published ready cleanup pull request
      [#2718](https://github.com/ai-shifu/ai-shifu/pull/2718) from
      `sunner/remove-umami-data-dependency` to `main`.
- [x] 2026-08-30 17:27 CST: Created
      `sunner/rebuild-course-visit-metric` from the final cleanup head and defined
      the first-party storage, write, query, eligibility, and initial-data
      contracts.
- [x] 2026-08-30 17:59 CST: Implemented the first-party course-visit table,
      authenticated fail-open write path, atomic latest-visit upsert, rolling
      business-table count, operator metric card, localized explanation, and
      focused regression coverage.
- [x] 2026-08-30 18:05 CST: Passed focused backend and frontend suites,
      TypeScript, translation, migration, repository-harness, architecture, and
      full pre-commit gates; published ready stacked pull request
      [#2719](https://github.com/ai-shifu/ai-shifu/pull/2719) with #2718's branch
      as its base until the cleanup merges.
- [x] 2026-08-30 18:24 CST: Addressed the duplicate
      [Devin](https://github.com/ai-shifu/ai-shifu/pull/2719#discussion_r3889064203)
      and
      [Codex](https://github.com/ai-shifu/ai-shifu/pull/2719#discussion_r3889066618)
      review findings with a privacy-minimized operator-card exposure event,
      while keeping course-visit data entirely first-party; passed 106 focused
      frontend tests, TypeScript, lint, formatting, repository-harness, and
      architecture checks.

## Surprises & Discoveries

- The repository has only one product-code path that reads statistics back
  from Umami: `visit_count_30d` on the operator course detail API.
- The operator course detail UI deliberately stopped rendering the visitor
  card in #1815, but the API still performs the Umami request and the frontend
  still carries an unused response field and translations.
- The existing event uses one event name per course
  (`course_visit_<shifu_bid>`). Once the only consumer is removed, keeping this
  producer would create an undocumented, unconsumed event family.
- Shared browser-side Umami transport is used by unrelated product analytics
  contracts and is not part of this removal.
- Temporary guest accounts have stable product IDs but are not equivalent to
  logged-in people and can be double-counted across guest-to-account identity
  changes, so they cannot safely extend the original #1527 population.
- Existing learning progress, orders, and Umami history cannot correctly
  backfill page openings. The rebuilt metric therefore begins with a partial
  30-day window at deployment instead of substituting a different behavior.

## Decision Log

- Decision: remove the old #1527 implementation completely in the first pull
  request, including the dynamic course event, backend Umami management client,
  management credentials, hidden API field, stale frontend types/i18n, tests,
  and obsolete Umami-based product specification.
  - Why: partial compatibility would retain dead code and preserve the invalid
    dependency the cleanup is intended to eliminate.
- Decision: retain the shared Umami script/site configuration, browser
  transport, identity setup, and unrelated product events.
  - Why: the issue is product code consuming telemetry as data, not the use of
    Umami for best-effort product analytics.
- Decision: rebuild #1527 only from the cleanup branch and use first-party
  business data for both writes and reads.
  - Why: the displayed metric must remain correct and available independently
    of analytics delivery, filtering, retention, credentials, or outages.
- Decision: preserve the original metric semantics unless implementation
  evidence requires a documented change: distinct logged-in, non-preview
  users who opened the learner course page during the trailing 30 UTC days.
  - Why: this is the original product decision behind #1527 and distinguishes
    access interest from learners who have progress records.
- Decision: keep the rebuild pull request stacked on the cleanup branch until
  the cleanup merges, then rebase or retarget it to `main`.
  - Why: this keeps the removal reviewable on its own and prevents the rebuild
    from reintroducing obsolete Umami contracts.
- Decision: persist one `learn_course_visitors` row per
  `(shifu_bid, user_bid)`, preserving first visit time and atomically advancing
  the latest visit time.
  - Why: a uniqueness constraint makes retries and concurrent writes safe,
    while the latest timestamp exactly supports a current rolling distinct
    count without retaining unnecessary per-visit history.
- Decision: use an authenticated empty-body
  `POST /api/learn/shifu/<shifu_bid>/visit` and keep the write independent from
  existing course-loading `GET` requests.
  - Why: identity must come from the validated token, and a failed metric write
    must never fail or mutate the user-visible course load.
- Decision: exclude temporary guests and include active registered, trial, or
  paid users on published non-preview learner routes.
  - Why: this restores the original #1527 logged-in-user definition without
    claiming that temporary browser-scoped identities are people.
- Decision: do not backfill earlier visits and explain the initial partial
  window in the metric tooltip.
  - Why: every available proxy would silently change the definition, while
    reading old Umami data would recreate the dependency being removed.
- Decision: add `operator_course_visitor_metric_shown` only for successful
  operator-card exposure, with `shifu_bid` as its sole feature-owned field.
  - Why: this satisfies the repository's user-facing capability analytics
    contract without sending the visitor count to Umami or making Umami a
    source, sink, compatibility write, or runtime dependency of the business
    metric.

## Outcomes & Retrospective

- Cleanup is isolated in #2718 with no database migration or replacement
  metric, so reviewers can verify the invalid dependency is fully gone before
  reviewing the first-party rebuild.
- The first-party rebuild now records only eligible published-course visits in
  `learn_course_visitors`, derives the 30-day operator count from that table,
  and keeps write failures independent from course loading. It contains no
  Umami read, sync, compatibility event, or historical backfill. It is
  published for review as stacked pull request #2719 after all local repository
  gates passed; hosted checks run on the pull request independently.

## Context and Orientation

Before the cleanup, the obsolete backend reader lived in
`src/api/flaskr/common/umami_client.py`. It was called by
`src/api/flaskr/service/shifu/admin_operations/courses_detail.py`, which
returned `visit_count_30d` through
`src/api/flaskr/service/shifu/admin_dtos_courses.py`. Compatibility exports in
`src/api/flaskr/service/shifu/admin.py` and
`src/api/flaskr/service/shifu/admin_operations/courses.py` kept the symbol
patchable in older tests.

The matching learner-side producer lived in
`src/cook-web/src/app/c/[[...id]]/courseVisitTracking.ts` and was invoked by the
course page. The operator frontend no longer rendered the metric, but its types,
empty response value, fixture fields, translation marker, generated i18n key,
and locale strings remained. The obsolete Umami-based specification occupied
`docs/product-specs/operator-course-visit-analytics.md`; the rebuild replaces
it at the same canonical path with the first-party contract.

The rebuild must locate an authenticated learner at the existing course-page
initialization boundary, record a first-party visit without changing or
blocking the page result, and query a product-owned table from the operator
detail service. New model timestamps and rolling-window boundaries use UTC.

## Plan of Work

1. Remove the complete Umami-derived course metric seam while leaving shared
   analytics infrastructure and unrelated event producers unchanged.
2. Regenerate repository documentation indexes and run focused backend,
   frontend, translation, harness, and boundary checks.
3. Publish the cleanup as a ready pull request from
   `sunner/remove-umami-data-dependency` to `main`.
4. Branch from the cleanup head and define the first-party visit contract:
   authenticated eligible population, preview exclusion, server-side
   deduplication, UTC rolling window, stable request/response schema, and
   failure independence.
5. Add the smallest product-owned storage and write path that preserves exact
   distinct-user semantics, then expose the rolling 30-day distinct count from
   the operator course detail API and render it in the intended metric-card
   position.
6. Add focused regression coverage for eligibility, deduplication, timing,
   rolling-window boundaries, API output, UI placement, and write failures.
7. Publish the rebuild as a ready stacked pull request whose base is the
   cleanup branch.

## Concrete Steps

1. Delete `flaskr.common.umami_client` and its tests, then remove its imports,
   compatibility exports, API call, DTO field, and backend-only Umami
   management settings.
2. Delete `courseVisitTracking.ts` and its tests, remove its course-page
   invocation, and remove the unused operator frontend response field,
   fixtures, translation marker, locale entries, and generated key.
3. Remove the obsolete product specification and its index entry, then run
   `python scripts/build_repo_knowledge_index.py`.
4. Run focused backend and frontend tests, type-check and translation checks,
   `python scripts/check_repo_harness.py`,
   `python scripts/check_architecture_boundaries.py`, and pre-commit checks.
5. Commit, push, and open the cleanup pull request.
6. Add `learn_course_visitors`, an authenticated empty-body course visit
   endpoint, atomic latest-visit upsert, and a trailing 30-day business-table
   count after inspecting adjacent course-entry and admin-query patterns.
7. Implement, test, commit, push, and open the stacked rebuild pull request.

## Validation and Acceptance

The cleanup is accepted when no backend production code imports an Umami
management client or reads Umami statistics, no `course_visit_<shifu_bid>`
producer or `visit_count_30d` contract remains, backend-only Umami credentials
are absent, shared Umami event transport still compiles, documentation indexes
are current, and focused checks pass.

The rebuild is accepted when a logged-in non-preview course entry records a
product-owned visit, ineligible entries do not, repeated writes respect the
documented server-side deduplication contract, tracking failure cannot change
the learner-visible operation, and the operator detail page displays an exact
distinct-user count for the trailing 30 UTC days without contacting Umami.

## Idempotence and Recovery

The cleanup consists of deletions and narrow contract edits and can be safely
reapplied after a rebase. Documentation generation and all validation commands
are repeatable.

The rebuild migration must be additive and use a uniqueness constraint that
makes visit recording retry-safe. If the stacked branch must be rebased after
the cleanup merges, rebase it onto updated `main`, resolve only overlapping
course-metric files, rerun the complete focused validation set, and retarget
the pull request without force-pushing unrelated history.

## Interfaces and Dependencies

- Cleanup retains `ANALYTICS_UMAMI_SCRIPT` and `ANALYTICS_UMAMI_SITE_ID` as the
  public frontend analytics configuration contract.
- Cleanup removes the private backend Umami management API contract and
  `AdminOperationCourseDetailMetricsDTO.visit_count_30d`.
- Rebuild adds `POST /api/learn/shifu/<shifu_bid>/visit` with an empty body and
  identity derived exclusively from the validated token.
- Rebuild adds `learn_course_visitors` with UTC `first_visited_at` and
  `last_visited_at`, a unique `(shifu_bid, user_bid)` constraint, and a
  `(shifu_bid, last_visited_at)` query index.
- Rebuild will restore `visit_count_30d` only as a business-backend response
  field backed by first-party data, along with the operator UI label and card.
- Existing course authorization, admin route structure, UTC helpers, and
  database session are reused instead of introducing a separate analytics
  service dependency.
