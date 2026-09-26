# Tech Debt Tracker

## Purpose

Keep current, actionable debt separate from dated inventories and delivered work.
Each item below identifies its dependency and next evidence needed.

## Current Debt

- Backend maintainers: investigate external provider HTTP calls held inside
  database transactions and legacy `Model.query` usage. Use the completed
  overhaul journal for entry points; size each change from a fresh census and
  cover transaction/failure behavior before changing it.
- Backend/API owners: verify candidate routes with no known consumer against
  production access evidence before proposing removals. The July inventory's
  count is historical and is not deletion authorization.
- Learning backend: assess retirement of the retained `RunScriptContextV2`
  facade. `src/api/flaskr/service/learn/runscript_v2.py` still imports and
  constructs it. The completed [decomposition](completed/learn-run-decomposition.md)
  delivered incremental extractions rather than the master plan's proposed
  replacement path; it did not delete this facade. Agree the replacement
  boundary before scheduling a dedicated retirement PR, and require golden SSE,
  resume and disconnect coverage plus removal of runtime callers for completion.
- Learning backend: extend deterministic golden fixtures for mid-stream errors
  and resume behavior; choose cases from current `/run` contracts.
- Frontend/product: shared-course editor permission affordances and French
  onboarding copy polish were deferred from the retired home-entry work. First
  confirm current editor behavior and intended scope; no implementation is queued.
- Learning frontend: optional visual page finder with desktop hover previews
  and a cross-device page panel. Before implementation, define thumbnails/typed
  cards, streaming refresh, caching, mobile discovery and rendering-cost limits.
- Growth/Skills: full generation/import attribution beyond the delivered course
  entry events needs its own producer/consumer contract. Cross-repository Skill
  acquisition acceptance remains in the active attribution plan.
- Billing/product: decide preorder-renewal campaign eligibility, price locking,
  stacking and provider behavior. Automatic renewal remains out of scope until
  separately decided; order reuse is owned by the active payment-attempt plan.
- Authentication: broader password IP-policy changes depend on the delivered
  trusted-client-IP boundary and a separately specified policy/test matrix.
- Architecture owners: shrink the committed boundary baseline as individual
  boundary violations are fixed; a fresh scan, not old counts, determines work.

### Course pricing follow-ups

Transferred from the completed [market-price plan](completed/course-price-market-rules-and-free-unlock.md):

- Frontend configuration: recover after an initial runtime-config fetch failure.
  `src/web/src/lib/initializeEnvData.ts` currently marks configuration loaded even
  on failure; `envStore.ts` retains the 0.50 minimum fallback. Define a bounded
  retry/recovery path and verify that a transient failure can recover China's
  CNY 0.01 authoring option without a page refresh, while preserving the global
  minimum and server-owned policy. This gap is not fixed by archiving the plan.
- Course-settings analytics: retain the initiating identity across the async save
  in `src/web/src/components/shifu-setting/ShifuSetting.tsx`. Verify the success
  event cannot be attributed to an account that replaced the initiating account;
  keep save success independent of telemetry and preserve the existing payload.
  The session-modal guard is a separate producer fix and does not close this item.
- Pricing integration coverage: reassess the recorded payment-hook and authoring-
  form boundary probes against current tests. Promote still-missing cases into
  stable integration coverage for provider bypass, server-confirmed free unlock
  and market-aware authoring. Close this item with actual test paths/results,
  not only independent helper assertions.

## Completed Debt and Evidence

The July inventory is preserved at `docs/history/backend-inventory-2026-07.md`.
Its 213 direct commits, serializer/pagination/env-read counts and stale endpoint
catalog observations are not current debt. Backend overhaul #2132/#2133 delivered
the refactors and the completed `uow-commit-site-migration.md` eliminated the
remaining outside-DAO commits. The current committed UoW baseline is empty;
`python scripts/check_uow_commit_sites.py` enforces that result.

## External Acceptance

Use the dated [plan review](../history/knowledge-review-2026-09-26.md) for the
complete per-plan disposition and open device, provider, SMTP and deployment
acceptance. Those tasks remain active and are not replaced by this debt list.
