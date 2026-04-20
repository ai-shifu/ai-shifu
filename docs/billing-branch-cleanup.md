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

## Second Pass Cleanup

This second pass remains scoped to the committed diff between `upstream/main`
and the current branch. It still excludes the dirty worktree, untracked files,
local diagnostics helpers, screenshots, logs, spreadsheets, and ad hoc docs.

The goal for this pass is to tighten internal branch-only surfaces that remain
redundant after the first cleanup round:

- Shrink `src/api/flaskr/service/billing/__init__.py` back to a minimal package
  marker instead of a broad compatibility re-export surface.
- Remove duplicated billing test route-loader bootstrapping from
  `test_runtime_config_billing.py` and `test_billing_callbacks.py`.
- Remove frontend billing helpers that are no longer consumed by production
  code, together with their dead tests and dead translation pre-registration.
- Consolidate the repeated paged admin billing table boilerplate into a shared
  hook and shared pager component without changing the rendered billing
  surfaces or the request/response contracts.
