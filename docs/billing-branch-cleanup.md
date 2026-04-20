# Billing Branch Cleanup

## Summary

This cleanup is scoped to the committed diff between `upstream/main` and the
current branch. It excludes the current dirty worktree, local debugging
artifacts, and any untracked files.

The goal is to remove confirmed dead code, stale compatibility shims, and
duplicated billing test scaffolding without changing billing routes, DTOs,
database schema, plugin registration behavior, or the current billing UI
behavior.

## Cleanup Targets

- Remove the stale backend compatibility layer
  `src/api/flaskr/service/billing/funcs.py`.
- Remove the unused billing UI components
  `BillingMetricCard.tsx` and `BillingUsageDetailSheet.tsx`.
- Remove the unused `module.billing.ledger.detail.*` translation surface and
  regenerate frontend i18n key types.
- Consolidate repeated billing route loader setup in billing route tests into
  one shared helper under `src/api/tests/service/billing/route_loader.py`.

## Non-Goals

- No route, DTO, schema, migration, or feature-flag behavior changes.
- No cleanup for current worktree-only files such as local screenshots, logs,
  ad hoc docs, or untracked billing diagnostics helpers.

## Verification

- Focused backend pytest coverage for billing route and CLI surfaces.
- Focused frontend Jest coverage for billing admin surfaces.
- Frontend type-check and lint.
- Shared translation validation and targeted pre-commit checks on touched
  files.
