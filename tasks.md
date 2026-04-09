# Billing Refactor Tasks

## Phase 1: Capability Truth Source

- [x] Add a backend capability registry for billing surfaces.
- [x] Extend `GET /api/billing` bootstrap payload with capability metadata.
- [x] Add frontend billing bootstrap types, hook, and creator/admin capability status summary.
- [x] Create `docs/billing-refactor-plan.md` and move the active checklist to repository-root `tasks.md`.
- [x] Add or adjust UI and API tests that assert capability status rendering and bootstrap compatibility.
- [x] Update the billing design doc capability matrix so docs match code truth.

## Phase 2: Backend Module Split

- [x] Extract shared usage charge calculation into `src/api/flaskr/service/billing/charges.py`.
- [x] Repoint `daily_aggregates.py` and aggregate-related tests to the public charge builder.
- [x] Extract billing query and filter helpers into `src/api/flaskr/service/billing/queries.py`.
- [x] Extract billing serializers into `src/api/flaskr/service/billing/serializers.py`.
- [x] Extract billing read-model builders into `src/api/flaskr/service/billing/read_models.py`.
- [x] Extract new creator trial helpers into `src/api/flaskr/service/billing/trials.py`.
- [x] Extract checkout/refund/sync/reconcile flows into `src/api/flaskr/service/billing/checkout.py`.
- [x] Extract subscription lifecycle and renewal orchestration into `src/api/flaskr/service/billing/subscriptions.py`.
- [x] Extract Stripe/Pingxx webhook state handling into `src/api/flaskr/service/billing/webhooks.py`.
- [x] Rewire `routes.py`, `tasks.py`, `cli.py`, `renewal.py`, `callback.py`, and `order/funs.py` to new public modules only.
- [x] Shrink `src/api/flaskr/service/billing/funcs.py` to a thin compatibility layer under 1200 lines.

## Phase 3: Frontend, Tests, and Residual Cleanup

- [x] Split `src/cook-web/src/components/billing/BillingOverviewTab.tsx` into container and presentational components.
- [x] Remove `src/cook-web/src/components/billing/BillingPlaceholderSection.tsx` and its export.
- [x] Remove redundant billing frontend wrappers, re-exports, and unnecessary memoization.
- [x] Replace low-value source-text contract tests with route registration, metadata, and behavior assertions.
- [ ] Consolidate billing migrations into `core` and `extension` phases before merge.
- [x] Run targeted billing backend and frontend verification, then widen only if shared failures appear.
