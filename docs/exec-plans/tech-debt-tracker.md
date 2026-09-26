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
  separately decided. Billing business-order timeout/reuse has its own item
  below; the payment-attempt plan owns provider credentials within an order.
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

### Billing order timeout and reuse

Owner: billing backend and product. This is the active destination for the
completed [package-campaign plan's follow-up](completed/package-campaigns.md#follow-up-requirement-billing-order-timeout-and-reuse).
It concerns finding, expiring and reusing `BillingOrder` rows across fresh
subscription/top-up checkout requests. The active payment-attempt plan concerns
provider attempts within an existing business order and does not close this work.

- Credit existing implementation before proposing changes: `checkout.py` already
  finds/reuses pending subscription orders, compares product/order/campaign and
  provider-price identifiers, and expires stale orders. `consts.py` sets a
  30-minute deadline; top-up creation also sets `expires_at`, and sync can expire
  those rows. Thirteen selected subscription lifecycle/provider-boundary tests
  passed during this review. These implemented pieces are not outstanding debt.
- Remaining scope: `_prepare_topup_checkout` still creates a fresh business order
  for each fresh request. Define top-up reuse and reconcile preorder eligibility
  separately: the managed subscription-order query excludes preorder metadata.
  Confirm the original campaign-pricing production acceptance dependency before
  scheduling this follow-up; automated renewal remains outside scope unless
  product explicitly includes it.
- Decide the complete reuse key and price/campaign snapshot policy across
  providers. Map existing identity and price guards to that decision instead of
  assuming identifier equality proves unchanged payable amount or campaign
  terms. Specify replacement/expiry handling for draft subscription starts
  without changing an active subscription for upgrade/preorder attempts.
- Reconfirm late-payment handling against current provider reconciliation before
  implementation. The old proposal's strict timeout-terminal rule is a proposal,
  not a current contract or authorization to discard a provider-confirmed payment.
- Closure requires source/test evidence for subscription start, upgrade, preorder
  and top-up as scoped: same checkout inside the window, expiry and replacement,
  changed price/campaign snapshots, provider/channel credential refresh, duplicate
  requests and late webhook/sync outcomes. Run the selected provider smoke after
  the policy is approved. Existing partial timeout/reuse tests do not prove this
  full matrix; keep unmet cases here or transfer them to a dedicated active plan.

Source owners are `src/api/flaskr/service/billing/checkout.py` and `consts.py`.
Existing checks are `test_billing_write_routes_subscription_lifecycle.py` and
`test_checkout_provider_boundary.py` under `src/api/tests/service/billing/`.

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
