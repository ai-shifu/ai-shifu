# Billing Delivery Tasks

## Discovery

- [x] Audit existing course order and payment flow.
- [x] Audit existing metering and runtime config flow.
- [x] Confirm billing owner, product scope, renewal mode, entitlement scope, and doc location.

## Product Rules

- [ ] Freeze package, top-up, trial, and gift-credit business rules.
- [ ] Define credit burn priority, expiry, refresh, carry-over, and refund rules.
- [ ] Define upgrade, downgrade, cancellation, resume, and grace-period behavior in product-facing language.
- [ ] Define low-balance thresholds, expiration warnings, and billing-specific error messages.

## Data Model And Migrations

- [ ] Design creator-scoped billing schema and migration set.
- [ ] Add billing catalog seed data for plans and top-up products.
- [ ] Add billing usage rate seed data for LLM and TTS settlement.
- [ ] Add feature flags and billing defaults in `sys_configs`.

## Backend Billing Module

- [ ] Add `flaskr/service/billing/` module skeleton and route registration.
- [ ] Implement billing catalog and overview APIs.
- [ ] Implement creator wallet and ledger services.
- [ ] Implement immutable ledger writes with optimistic wallet updates.
- [ ] Implement billing order creation for subscription and top-up purchases.
- [ ] Implement subscription lifecycle services for start, upgrade, cancel, resume, expire, and downgrade scheduling.

## Metering And Settlement

- [ ] Implement usage-to-credit settlement from `bill_usage`.
- [ ] Implement settlement deduplication markers and replay-safe processing.
- [ ] Implement low-balance and inactive-subscription gating for billable production actions.
- [ ] Implement creator balance warnings and wallet summary refresh.

## Payments And Renewals

- [ ] Implement Stripe recurring subscription flow, invoices, and webhooks.
- [ ] Confirm domestic recurring payment provider capability and integrate recurring billing.
- [ ] Implement top-up purchase flow and top-up credit source handling.
- [ ] Implement webhook idempotency and reconciliation jobs.
- [ ] Implement renewal retry, grace-period, cancellation, and downgrade scheduling.
- [ ] Implement refund handling for billing orders and unused credit reversals.

## Entitlements And Runtime

- [ ] Implement creator-scoped branding entitlement resolution.
- [ ] Implement runtime config extension for creator billing status, entitlements, and branding.
- [ ] Implement custom-domain binding, verification, and host resolution.
- [ ] Implement priority class and concurrency entitlement enforcement.
- [ ] Implement analytics tier and support tier exposure for creator and admin views.

## Frontend Creator Experience

- [ ] Implement creator Billing Center frontend.
- [ ] Implement catalog purchase flows for plans and top-ups.
- [ ] Implement wallet and ledger views.
- [ ] Implement subscription management actions for cancel and resume.
- [ ] Implement branding and domain setup forms.

## Admin Operations

- [ ] Implement admin billing operations pages and tooling.
- [ ] Implement admin subscription list and billing order list.
- [ ] Implement manual ledger adjustment workflow with audit metadata.
- [ ] Implement renewal failure queue and reconciliation visibility.
- [ ] Implement domain review and verification status tooling.

## Localization And Copy

- [ ] Add i18n keys for all new billing UI and server messages.
- [ ] Add billing-specific legal or policy copy where required by checkout flows.

## Testing

- [ ] Add tests for payments, renewals, settlement, entitlements, and regression of legacy `/order`.
- [ ] Add unit tests for wallet math, ledger ordering, and source burn priority.
- [ ] Add webhook replay and duplicate-event tests.
- [ ] Add runtime resolution tests for creator branding and custom domain behavior.
- [ ] Add frontend tests for billing overview, purchase flow, and admin operations pages.

## Operations And Rollout

- [ ] Add rollout, migration, and backfill runbook.
- [ ] Add monitoring and alerting for renewal failures, wallet drift, and settlement lag.
- [ ] Define pilot rollout steps and feature-flag strategy.
- [ ] Document rollback strategy for billing APIs, settlement jobs, and runtime entitlement resolution.
