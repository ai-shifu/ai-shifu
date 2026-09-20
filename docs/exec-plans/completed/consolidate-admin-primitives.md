# Consolidate shared admin primitives

## Purpose / Big Picture

Admin routes and billing panels currently maintain byte-identical copies of four
UI primitives. Keep one implementation so table, pagination, and clearable-input
maintenance reaches both groups of callers consistently.

## Progress

- [x] 2026-09-20 01:08 UTC: Audited both copies, their imports, and nearby tests.
- [x] 2026-09-20 01:08 UTC: Replaced route copies with explicit compatibility
  exports and moved existing behavioral tests beside the shared implementations.
- [x] 2026-09-20 01:12 UTC: Locked-dependency regression tests (13 tests),
  TypeScript, lint, and architecture checks passed. Completed repository gates
  before preparing the focused PR.

## Surprises & Discoveries

The shared implementations already exist under `src/web/src/components/admin`.
No new abstraction is needed. Existing route imports can remain compatible.
The checkout initially links to dependencies older than the lockfile; use an
isolated installation for final verification.

## Decision Log

- Keep shared implementations unchanged and retain client entry directives.
- Preserve explicit exports, props, styling, loading, empty, and pagination
  behavior. This refactor adds no user action or analytics contract.
- Limit this PR to the four duplicated primitives and their existing tests.

## Outcomes & Retrospective

Removed 342 lines of duplicate implementation. Existing behavioral and consumer
tests pass with the locked dependencies; TypeScript, lint, architecture, and
repository pre-commit checks pass. All legacy imports remain compatible.

## Context and Orientation

`src/web/src/app/admin/components` contains route compatibility entrypoints.
`src/web/src/components/admin` owns the canonical `AdminTableShell`,
`AdminPagination`, `AdminClearableInput`, and `adminTableStyles` implementations.

## Plan of Work

Replace the four duplicate bodies with explicit exports, relocate their two
existing test files, and exercise both route and shared billing consumers.

## Concrete Steps

Run the canonical table-shell and clearable-input tests, `OrdersTable` tests,
and `AdminBillingReportsPanel` tests. Run TypeScript, lint, architecture and
repository checks plus the all-file pre-commit gate before publishing.

## Validation and Acceptance

Table loading and empty states, sticky actions, pagination, input clearing and
billing reports preserve existing behavior. All callers type-check and no new
architecture boundary violations appear.

## Idempotence and Recovery

No data migration, dependency or configuration change. Reverting the PR restores
the duplicate bodies and test locations without affecting persisted data.

## Interfaces and Dependencies

Public import paths and component props remain unchanged. Dependencies flow from
route entrypoints to shared components; shared components do not import routes.
