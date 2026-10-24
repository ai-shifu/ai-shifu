# Consolidate shared admin primitives

## Purpose / Big Picture

Admin routes and billing panels currently maintain byte-identical copies of four
UI primitives. Keep one implementation so table, pagination, and clearable-input
maintenance reaches both groups of callers consistently.

## Progress

- [x] 2026-09-20 01:08 UTC: Audited both copies, their imports, and nearby tests.
- [x] 2026-09-20 01:08 UTC: Consolidated the implementations and moved existing
  behavioral tests beside the shared components.
- [x] 2026-09-20 01:12 UTC: Locked-dependency regression tests (13 tests),
  TypeScript, lint, and architecture checks passed. Completed repository gates
  before preparing the focused PR.
- [x] 2026-09-20 01:33 UTC: Removed four forwarding modules and migrated 68
  imports across 36 source files. All 613 admin/billing tests, TypeScript, lint,
  architecture validation, and repository pre-commit checks passed.

## Surprises & Discoveries

The shared implementations already exist under `src/web/src/components/admin`.
No new abstraction is needed. This private frontend has no external consumers of
the route-local module paths; all callers can import shared components directly.
The checkout initially links to dependencies older than the lockfile; use an
isolated installation for final verification.

## Decision Log

- Keep shared implementations unchanged, including their client directives.
- Remove the four route forwarding files and migrate all imports together.
- Preserve component props, styling, loading, empty, and pagination
  behavior. This refactor adds no user action or analytics contract.
- Limit this PR to the four duplicated primitives, their callers, existing tests,
  and documentation of the canonical paths.

## Outcomes & Retrospective

The four route copies are deleted. Every caller imports the shared implementation
directly. The shared implementations remain unchanged. All 613 tests in 62
admin/billing suites pass, along with TypeScript, lint, architecture validation,
and the repository pre-commit gate; no references to the deleted modules remain.

## Context and Orientation

`src/web/src/components/admin` owns the canonical `AdminTableShell`,
`AdminPagination`, `AdminClearableInput`, and `adminTableStyles` implementations.
Admin routes and billing panels both import these modules directly.

## Plan of Work

Remove the four duplicate modules, update every caller and documented path,
relocate their two existing test files, and exercise route and billing consumers.

## Concrete Steps

Run the shared admin component, admin route, and billing component tests.
Run TypeScript, lint, architecture and repository checks plus the all-file
pre-commit gate before publishing.

## Validation and Acceptance

Table loading and empty states, sticky actions, pagination, input clearing and
billing reports preserve existing behavior. All callers type-check and no new
architecture boundary violations appear.

## Idempotence and Recovery

No data migration, dependency or configuration change. Reverting the PR restores
the duplicate bodies and test locations without affecting persisted data.

## Interfaces and Dependencies

Internal callers import `@/components/admin` modules directly; the four former
route-local paths are removed. Component props remain unchanged. Dependencies
flow from route entrypoints to shared components; shared components do not import
routes.
