# Creator Billing And Subscription Design

## 1. Overview

AI-Shifu currently monetizes at the **course order** level: a learner buys one course, pays once, and receives access to that course. The new billing model introduces a **creator-scoped billing domain** where a creator account purchases subscription plans and top-up packages, consumes credits as production workloads run, and receives paid entitlements such as branding, custom domains, queue priority, concurrency limits, and analytics depth.

This document defines the v1 implementation for:

- Creator-scoped subscription plans
- One-off top-up packages
- Credit wallets and ledger accounting
- Dual-channel auto-renewal
- Creator entitlements for branding, domains, priority, concurrency, analytics, and support tier

### 1.1 Fixed Product Decisions

The design assumes the following choices are already accepted:

| Topic | Decision |
|-------|----------|
| Billing owner | Creator account |
| Product scope | Subscription plans + one-off top-ups + gift credits |
| Renewal mode | Auto-renewal for both Stripe and domestic recurring payment channel |
| Entitlement scope | Credits + branding + domain + priority + concurrency + analytics + support tier |
| Legacy course orders | Preserved unchanged |

### 1.2 Goals

- Introduce a dedicated billing domain without breaking legacy learner course purchase flow.
- Meter creator production usage and convert it into billable credits.
- Support monthly and yearly plans, plus top-up packages and trial or gift credits.
- Support auto-renewal, renewal retries, cancellation scheduling, downgrade scheduling, and billing reconciliation.
- Make paid entitlements creator-scoped and available to runtime resolution.
- Provide creator-facing and admin-facing billing UIs.

### 1.3 Non-Goals

- Replacing the existing learner course purchase flow under `/order`
- Migrating legacy course orders into the new billing tables
- Delivering enterprise custom billing logic beyond storing custom-plan placeholders
- Implementing a full tenant model beyond creator-scoped ownership

## 2. Current State Analysis

### 2.1 Existing Course Order Flow

The current payment implementation is course-centric:

- Core models: [src/api/flaskr/service/order/models.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/order/models.py)
- Core routes: [src/api/flaskr/route/order.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/route/order.py)
- Core service flow: [src/api/flaskr/service/order/funs.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/order/funs.py)

Important characteristics:

- `order_orders` binds an order to `user_bid` and `shifu_bid`.
- Payment success unlocks a course, not a creator account capability.
- Stripe and Ping++ are wired as one-time payment providers.
- The order model does not contain subscription periods, billing anchors, wallet balances, or creator entitlements.

This flow must remain unchanged and isolated from the new billing implementation.

### 2.2 Existing Usage Metering

Usage is already recorded at the infrastructure level:

- Model: [src/api/flaskr/service/metering/models.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/metering/models.py)
- Recorder: [src/api/flaskr/service/metering/recorder.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/metering/recorder.py)
- Summary route: [src/api/flaskr/service/metering/routes.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/metering/routes.py)

Important characteristics:

- `bill_usage` is a raw fact table for LLM and TTS consumption.
- It stores `user_bid`, `shifu_bid`, provider, model, usage totals, scene, and billable flag.
- It does not store creator ownership, credit conversion, ledger entries, or wallet balance.
- It already distinguishes production vs non-billable scenes, which can be reused for settlement rules.

This table should remain the source of truth for raw billable usage. Creator credits must be computed in a new billing layer.

### 2.3 Existing Runtime Config

Current runtime branding and configuration are global:

- Runtime config route: [src/api/flaskr/route/config.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/route/config.py)
- Config storage: [src/api/flaskr/service/config/models.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/config/models.py)
- Config access: [src/api/flaskr/service/config/funcs.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/config/funcs.py)

Important characteristics:

- Branding values such as `logoWideUrl`, `logoSquareUrl`, `faviconUrl`, and `homeUrl` are returned globally.
- There is no creator-specific runtime resolution based on request host or creator ownership.
- `sys_configs` can store additive configuration, but cannot represent creator-specific resolved runtime state on its own.

This must evolve into creator-aware resolution so paid branding and domain entitlements become effective at request time.

### 2.4 Existing Payment Integrations

Available payment integrations:

- Stripe provider: [src/api/flaskr/service/order/payment_providers/stripe.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/order/payment_providers/stripe.py)
- Ping++ provider: [src/api/flaskr/service/order/payment_providers/pingxx.py](/Users/geyunfei/dev/yfge/ai_shifu_web_conf/src/api/flaskr/service/order/payment_providers/pingxx.py)

Important characteristics:

- Stripe currently supports checkout session, payment intent, webhook verification, and refunds for one-time payments.
- Ping++ currently supports one-time charge creation only.
- There is no subscription, invoice, mandate, recurring deduction, or renewal reconciliation flow.

V1 must add a normalized recurring billing layer above provider-specific implementations.

### 2.5 Existing Runtime Execution Controls

The repository uses local thread pools and in-process queues for some workloads, but it does not contain a unified business task scheduler with creator-level priority classes or concurrency controls.

Implication:

- “Priority queue” and “concurrency boost” are not just billing flags.
- V1 must add a lightweight execution-control layer that can enforce creator-specific limits and priority classes for billable production work.

## 3. Product And Business Rules

### 3.1 Catalog

V1 product catalog includes:

| Product Type | Code | Billing Cadence | Purpose |
|-------------|------|-----------------|---------|
| Trial credit | `trial_15d` | One-time | New creator onboarding |
| Monthly light | `monthly_light` | Monthly recurring | Low-volume creator usage |
| Monthly pro | `monthly_pro` | Monthly recurring | Higher monthly usage |
| Yearly growth 5k | `yearly_growth_5000` | Yearly recurring | Annual commitment with 5,000 credits per year |
| Yearly growth 10k | `yearly_growth_10000` | Yearly recurring | Annual commitment with 10,000 credits per year |
| Yearly growth 22k | `yearly_growth_22000` | Yearly recurring | Annual commitment with 22,000 credits per year |
| Custom enterprise | `custom_enterprise` | Manual | Sales-managed |
| Top-up package | `topup_*` | One-time | Additional credits without changing base plan |
| Gift credits | `gift_*` | Manual | Promotions or operator grant |

### 3.2 Credit Sources

Credits can come from three source families:

| Source Family | Examples | Expiry Policy | Refresh Policy | Carry Over |
|--------------|----------|---------------|----------------|------------|
| Subscription allocation | Monthly plan, yearly plan periodic refresh | Expires at end of allocation window | Refreshed at cycle boundary | No |
| Top-up credits | Recharge package | No expiry while subscription stays active | None | Yes |
| Gift credits | Trial, campaign grant | Has explicit expiry timestamp | None | No automatic refresh |

### 3.3 Burn Priority

Credits are burned in the following deterministic order:

1. Subscription allocation credits with the earliest `expires_at`
2. Gift credits with the earliest `expires_at`
3. Top-up credits without expiry, oldest first by `created_at`

Rationale:

- Subscription allocations are intentionally periodic and non-carrying.
- Gift credits are promotional and should not outlive purchased credits.
- Top-up credits are durable reserve balance.

### 3.4 Billable Usage Rules

Usage-to-credit settlement only applies when all conditions below are true:

- `bill_usage.billable = 1`
- `bill_usage.usage_scene = production`
- The record is linked to a published course owned by a creator
- The record has not already been settled into the billing ledger

Non-production scenes remain recorded in `bill_usage` but do not consume credits in v1.

### 3.5 Credit Conversion Policy

Credit conversion is driven by a rate table, not hard-coded logic. Each rate is keyed by:

- `usage_type`
- `provider`
- `model`
- `usage_scene`
- `effective_from`

The settlement formula is:

`credits_consumed = ceil((usage_amount / unit_size) * credits_per_unit)`

Where:

- `usage_amount` is `total` for LLM and TTS by default
- `unit_size` and `credits_per_unit` come from `billing_usage_rates`
- Override fields in `extra` may be supported later for special pricing

### 3.6 Subscription Lifecycle

Normalized subscription states:

| State | Meaning |
|-------|---------|
| `draft` | Checkout initialized but not yet activated |
| `active` | Subscription valid and allowed to renew |
| `past_due` | Renewal attempted but payment failed; grace period active |
| `paused` | Renewals paused by system or admin |
| `cancel_scheduled` | Auto-renew disabled; current paid period continues |
| `canceled` | Subscription ended and will not renew |
| `expired` | Subscription ended without renewal |

### 3.7 Renewal And Grace Period

Renewal rules:

- Monthly plans renew every month on the billing anchor day.
- Yearly plans renew every 12 months on the billing anchor day.
- A renewal attempt is triggered automatically at the anchor timestamp.
- On failed renewal, the subscription enters `past_due`.
- Grace period duration is 7 days from the failed renewal attempt.
- During grace period:
  - Existing top-up balance remains usable.
  - No new subscription allocation is granted.
  - Auto-renew retry jobs keep running.
- If payment still fails after grace period, subscription becomes `expired`.
- Top-up credits become unusable when no active or past-due subscription exists.

### 3.8 Upgrade, Downgrade, Cancellation, And Refund Rules

Upgrade:

- Monthly-to-higher-monthly upgrade takes effect immediately.
- Yearly-to-higher-yearly upgrade takes effect immediately.
- Immediate upgrade creates a proration order for the remaining time in the current billing period.
- New plan entitlements activate immediately after payment success.
- For subscription allocations, the current allocation window is recomputed by difference:
  - `new_allocation_for_current_window = target_window_allocation - already_granted_current_window_allocation`
  - If negative, grant zero.

Downgrade:

- Downgrade is always scheduled, not immediate.
- Current plan remains active until current paid period ends.
- Next renewal uses the downgraded plan if not canceled before renewal.

Cancellation:

- Cancellation disables future auto-renewal only.
- Current paid period remains active.
- Creator keeps access to remaining subscription allocations and top-up credits until period end.
- Once the subscription becomes `canceled` or `expired`, top-up credits remain stored but unusable until a subscription is resumed or purchased again.

Refund:

- Full refund is supported only for operator action or provider-side failure cases approved by policy.
- Refunding a plan order creates a reversing ledger entry for any unused subscription allocation in the current window.
- Refunding top-up orders creates a reversing ledger entry for unused top-up credits.
- Consumed credits are never refunded as cash automatically.

## 4. Proposed Architecture

### 4.1 New Backend Module

Add a dedicated billing module:

`src/api/flaskr/service/billing/`

Recommended file layout:

| File | Responsibility |
|------|----------------|
| `models.py` | Billing tables |
| `consts.py` | State, source, and entitlement constants |
| `dtos.py` | API DTOs |
| `catalog.py` | Catalog loading and response assembly |
| `wallet.py` | Wallet and balance calculation |
| `ledger.py` | Ledger write and query helpers |
| `subscriptions.py` | Subscription lifecycle operations |
| `orders.py` | Billing order initialization and payment attempt creation |
| `entitlements.py` | Creator entitlement resolution |
| `runtime.py` | Creator-aware runtime config assembly |
| `settlement.py` | `bill_usage` to credit-ledger settlement |
| `renewal_jobs.py` | Renewal, retry, reconciliation jobs |
| `domain_binding.py` | Custom-domain binding and verification |
| `routes.py` | Public billing APIs |
| `admin_routes.py` | Admin billing APIs |
| `payment_providers/` | Recurring payment provider adapters |

### 4.2 Ownership Model

All billing records are owned by `creator_bid`. Resolver path:

1. Determine `shifu_bid` from workload context.
2. Resolve creator via existing shifu ownership helpers.
3. Use `creator_bid` as the wallet and entitlement key.

No billing state is stored on learner user accounts.

### 4.3 Separation From Legacy Orders

Legacy `/order` continues to operate independently for learner purchases. New billing tables never reuse `order_orders`, `order_pingxx_orders`, or `order_stripe_orders`.

Reasons:

- Different owner model: creator vs learner
- Different business object: subscription or top-up vs course purchase
- Different lifecycle: recurring vs one-time
- Different entitlement effects: global creator capabilities vs one-course access

## 5. Data Model

All new tables are additive. Column order should follow project conventions.

### 5.1 `billing_plans`

Stores subscription catalog entries.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `plan_bid` | VARCHAR(36) | Business id |
| `plan_code` | VARCHAR(64) | Stable code such as `monthly_light` |
| `name_i18n_key` | VARCHAR(128) | Display name key |
| `description_i18n_key` | VARCHAR(128) | Description key |
| `billing_interval` | VARCHAR(16) | `month`, `year`, `manual` |
| `billing_interval_count` | INT | Usually 1 or 12 |
| `currency` | VARCHAR(16) | Default `CNY` or `USD` |
| `price_amount` | BIGINT | Minor units |
| `credit_allocation` | INT | Credits granted per allocation window |
| `allocation_interval` | VARCHAR(16) | `month`, `year` |
| `auto_renew_enabled` | SMALLINT | Catalog-level support |
| `status` | SMALLINT | Active or inactive |
| `entitlement_payload` | JSON | Branding/domain/priority/concurrency/analytics/support |
| `sort_order` | INT | Display order |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.2 `billing_topup_products`

Stores one-off recharge packages.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `topup_bid` | VARCHAR(36) | Business id |
| `topup_code` | VARCHAR(64) | Stable code |
| `name_i18n_key` | VARCHAR(128) | Display key |
| `description_i18n_key` | VARCHAR(128) | Description key |
| `currency` | VARCHAR(16) | Currency |
| `price_amount` | BIGINT | Minor units |
| `credit_amount` | INT | Granted credits |
| `status` | SMALLINT | Active or inactive |
| `sort_order` | INT | Display order |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.3 `billing_subscriptions`

Stores creator subscription contracts.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `subscription_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `plan_bid` | VARCHAR(36) | Current plan |
| `status` | VARCHAR(32) | Normalized state |
| `billing_provider` | VARCHAR(32) | `stripe`, `pingxx`, or alternate domestic adapter |
| `provider_subscription_id` | VARCHAR(255) | External recurring object id |
| `provider_customer_id` | VARCHAR(255) | External customer or payer id |
| `billing_anchor_at` | DATETIME | Renewal anchor |
| `current_period_start_at` | DATETIME | Current period start |
| `current_period_end_at` | DATETIME | Current period end |
| `grace_period_end_at` | DATETIME | Retry limit |
| `cancel_at_period_end` | SMALLINT | Scheduled cancellation flag |
| `next_plan_bid` | VARCHAR(36) | Scheduled downgrade or plan swap |
| `last_renewed_at` | DATETIME | Last success |
| `last_failed_at` | DATETIME | Last failure |
| `metadata` | JSON | Provider and lifecycle metadata |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.4 `billing_wallets`

Stores creator balance summary for fast reads.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `wallet_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `available_credits` | INT | Spendable credits |
| `reserved_credits` | INT | Optional for future task reservation |
| `lifetime_granted_credits` | BIGINT | Audit summary |
| `lifetime_consumed_credits` | BIGINT | Audit summary |
| `last_settled_usage_id` | BIGINT | Cursor for settlement job |
| `version` | BIGINT | Optimistic concurrency control |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.5 `billing_ledger_entries`

Immutable source of truth for credit movements.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `ledger_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `wallet_bid` | VARCHAR(36) | Wallet |
| `entry_type` | VARCHAR(32) | `grant`, `consume`, `refund`, `expire`, `adjustment`, `hold`, `release` |
| `source_type` | VARCHAR(32) | `subscription`, `topup`, `gift`, `usage`, `refund`, `manual` |
| `source_bid` | VARCHAR(36) | Link to source object |
| `amount` | INT | Signed credit delta |
| `balance_after` | INT | Running balance after write |
| `expires_at` | DATETIME | Source expiry |
| `consumable_from` | DATETIME | Usually immediate |
| `metadata` | JSON | Provider/model/usage details |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |

### 5.6 `billing_orders`

Stores checkout objects for plans and top-ups.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `billing_order_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `order_type` | VARCHAR(32) | `subscription_start`, `subscription_upgrade`, `subscription_renewal`, `topup`, `manual` |
| `product_bid` | VARCHAR(36) | Plan or top-up id |
| `subscription_bid` | VARCHAR(36) | Nullable for top-ups |
| `currency` | VARCHAR(16) | Currency |
| `payable_amount` | BIGINT | Minor units |
| `paid_amount` | BIGINT | Minor units |
| `payment_provider` | VARCHAR(32) | Provider |
| `status` | VARCHAR(32) | `init`, `pending`, `paid`, `failed`, `refunded`, `canceled`, `timeout` |
| `metadata` | JSON | Checkout details |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.7 `billing_payment_attempts`

Tracks every provider interaction.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `attempt_bid` | VARCHAR(36) | Business id |
| `billing_order_bid` | VARCHAR(36) | Parent order |
| `creator_bid` | VARCHAR(36) | Owner |
| `payment_provider` | VARCHAR(32) | Provider |
| `provider_reference_id` | VARCHAR(255) | Checkout, invoice, charge, mandate, or payment id |
| `provider_event_id` | VARCHAR(255) | Webhook event id |
| `attempt_type` | VARCHAR(32) | `checkout`, `renewal`, `retry`, `refund`, `reconcile` |
| `status` | VARCHAR(32) | `pending`, `succeeded`, `failed`, `canceled`, `refunded` |
| `request_payload` | JSON | Normalized request |
| `response_payload` | JSON | Normalized response |
| `error_code` | VARCHAR(128) | Provider error |
| `error_message` | TEXT | Error message |
| `processed_at` | DATETIME | Completion timestamp |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.8 `billing_entitlements`

Stores currently effective creator entitlements.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `entitlement_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `source_type` | VARCHAR(32) | `subscription`, `manual`, `custom_plan` |
| `source_bid` | VARCHAR(36) | Source object |
| `branding_enabled` | SMALLINT | Logo and favicon override |
| `custom_domain_enabled` | SMALLINT | Domain binding |
| `priority_class` | INT | Higher number is higher scheduling priority |
| `max_concurrency` | INT | Maximum concurrent billable jobs |
| `analytics_tier` | VARCHAR(32) | `basic`, `deep`, `enterprise` |
| `support_tier` | VARCHAR(32) | `standard`, `priority`, `dedicated` |
| `feature_payload` | JSON | Future feature flags |
| `effective_from` | DATETIME | Start |
| `effective_to` | DATETIME | End |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.9 `billing_domain_bindings`

Stores creator custom-domain mapping.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `domain_binding_bid` | VARCHAR(36) | Business id |
| `creator_bid` | VARCHAR(36) | Owner |
| `host` | VARCHAR(255) | Fully qualified host |
| `status` | VARCHAR(32) | `pending_verification`, `active`, `disabled`, `failed` |
| `verification_method` | VARCHAR(32) | `dns_txt`, `cname`, `manual` |
| `verification_token` | VARCHAR(255) | Proof token |
| `last_verified_at` | DATETIME | Verification time |
| `ssl_status` | VARCHAR(32) | `pending`, `active`, `failed` |
| `metadata` | JSON | Provider and DNS notes |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.10 `billing_usage_rates`

Stores credit pricing rules.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `rate_bid` | VARCHAR(36) | Business id |
| `usage_type` | SMALLINT | Mirrors metering type |
| `provider` | VARCHAR(64) | Provider name |
| `model` | VARCHAR(128) | Model name or wildcard |
| `usage_scene` | SMALLINT | Typically production |
| `unit_size` | INT | Token or char block |
| `credits_per_unit` | DECIMAL | Credit price per unit |
| `rounding_mode` | VARCHAR(16) | `ceil`, `floor`, `round` |
| `effective_from` | DATETIME | Start |
| `effective_to` | DATETIME | End |
| `status` | SMALLINT | Active or inactive |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

### 5.11 `billing_renewal_events`

Stores scheduled and processed renewal operations.

| Field | Type | Notes |
|-------|------|-------|
| `id` | BIGINT PK | Internal id |
| `renewal_event_bid` | VARCHAR(36) | Business id |
| `subscription_bid` | VARCHAR(36) | Subscription |
| `creator_bid` | VARCHAR(36) | Owner |
| `event_type` | VARCHAR(32) | `renewal`, `retry`, `expire`, `cancel_finalize`, `downgrade_apply`, `reconcile` |
| `scheduled_at` | DATETIME | Target time |
| `status` | VARCHAR(32) | `pending`, `processing`, `done`, `failed`, `canceled` |
| `attempt_count` | INT | Retry count |
| `last_error` | TEXT | Error details |
| `payload` | JSON | Event context |
| `processed_at` | DATETIME | Completion time |
| `deleted` | SMALLINT | Soft delete |
| `created_at` | DATETIME | Timestamp |
| `updated_at` | DATETIME | Timestamp |

## 6. Public API Design

All billing APIs are additive and do not modify the legacy `/order` endpoints.

### 6.1 `GET /billing/catalog`

Returns all active plans and top-up products visible to the current creator.

Response:

```json
{
  "plans": [
    {
      "plan_bid": "plan_monthly_light",
      "plan_code": "monthly_light",
      "display_name": "Monthly Light",
      "description": "For partial curriculum design and limited learner delivery",
      "billing_interval": "month",
      "billing_interval_count": 1,
      "currency": "CNY",
      "price_amount": 990,
      "credit_allocation": 5,
      "auto_renew_enabled": true,
      "entitlements": {
        "branding_enabled": false,
        "custom_domain_enabled": false,
        "priority_class": 1,
        "max_concurrency": 1,
        "analytics_tier": "basic",
        "support_tier": "standard"
      }
    }
  ],
  "topups": [
    {
      "topup_bid": "topup_1000",
      "topup_code": "topup_1000",
      "display_name": "1,000 Credit Pack",
      "description": "Adds durable credits to the creator wallet",
      "currency": "CNY",
      "price_amount": 100000,
      "credit_amount": 1000
    }
  ]
}
```

### 6.2 `GET /billing/overview`

Returns the creator’s current subscription, wallet, entitlement summary, and renewal state.

Response:

```json
{
  "creator_bid": "creator_123",
  "wallet": {
    "available_credits": 1280,
    "reserved_credits": 0,
    "lifetime_granted_credits": 5400,
    "lifetime_consumed_credits": 4120
  },
  "subscription": {
    "subscription_bid": "sub_123",
    "status": "active",
    "plan_bid": "plan_yearly_growth_5000",
    "plan_code": "yearly_growth_5000",
    "billing_provider": "stripe",
    "billing_anchor_at": "2026-04-01T00:00:00Z",
    "current_period_start_at": "2026-03-01T00:00:00Z",
    "current_period_end_at": "2026-04-01T00:00:00Z",
    "cancel_at_period_end": false,
    "next_plan_bid": ""
  },
  "entitlements": {
    "branding_enabled": true,
    "custom_domain_enabled": true,
    "priority_class": 3,
    "max_concurrency": 8,
    "analytics_tier": "deep",
    "support_tier": "priority"
  },
  "billing_alerts": [
    {
      "type": "low_balance",
      "message": "Wallet balance is below 20 percent of monthly baseline."
    }
  ]
}
```

### 6.3 `GET /billing/ledger`

Query params:

- `page`
- `page_size`
- `entry_type`
- `source_type`
- `start_time`
- `end_time`

Returns paginated ledger entries ordered by `created_at desc`.

### 6.4 `POST /billing/subscriptions/checkout`

Creates a billing order and payment initiation for:

- New subscription
- Immediate upgrade proration
- Resume from expired status

Request:

```json
{
  "plan_bid": "plan_monthly_pro",
  "payment_provider": "stripe",
  "channel": "stripe:subscription",
  "success_url": "https://cook.example.com/billing/result",
  "cancel_url": "https://cook.example.com/billing"
}
```

Response:

```json
{
  "billing_order_bid": "border_123",
  "subscription_bid": "sub_123",
  "payment_provider": "stripe",
  "checkout_mode": "subscription",
  "provider_reference_id": "cs_test_123",
  "checkout_url": "https://checkout.stripe.com/...",
  "status": "pending"
}
```

### 6.5 `POST /billing/subscriptions/cancel`

Request:

```json
{
  "subscription_bid": "sub_123"
}
```

Behavior:

- Sets `cancel_at_period_end = 1`
- Leaves current paid period active
- Preserves entitlements until current period end

### 6.6 `POST /billing/subscriptions/resume`

Request:

```json
{
  "subscription_bid": "sub_123"
}
```

Behavior:

- Clears scheduled cancellation when the provider supports reactivation
- If provider-side reactivation is not possible, creates a fresh recurring checkout

### 6.7 `POST /billing/topups/checkout`

Request:

```json
{
  "topup_bid": "topup_1000",
  "payment_provider": "pingxx",
  "channel": "pingxx:alipay_qr",
  "success_url": "https://cook.example.com/billing/result"
}
```

Behavior:

- Creates a one-time billing order
- On payment success, grants top-up credits into the wallet ledger

### 6.8 `POST /billing/webhooks/stripe`

Responsibilities:

- Verify signature
- Deduplicate by provider event id
- Handle subscription lifecycle events
- Handle invoice paid and invoice failed events
- Handle cancellation and refund events
- Update billing order, subscription, payment attempt, and ledger state atomically

Supported event families:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`
- `charge.refunded`

### 6.9 `POST /billing/webhooks/pingxx`

Responsibilities:

- Verify provider signature
- Deduplicate by provider event id
- Handle recurring deduction success or failure
- Handle one-time top-up payment success
- Handle refund or closure events

Note:

- The exact upstream recurring capability depends on provider confirmation.
- Internally, the endpoint still writes the same normalized `billing_payment_attempts` and `billing_subscriptions` states as Stripe.

### 6.10 `GET /admin/billing/subscriptions`

Query params:

- `creator_bid`
- `status`
- `plan_code`
- `provider`
- `page`
- `page_size`

Returns admin subscription list with current state, current period, next plan, grace period, and renewal failures.

### 6.11 `GET /admin/billing/orders`

Query params:

- `creator_bid`
- `status`
- `order_type`
- `provider`
- `start_time`
- `end_time`
- `page`
- `page_size`

Returns billing order and payment-attempt summary for admin operations.

### 6.12 `POST /admin/billing/ledger/adjust`

Request:

```json
{
  "creator_bid": "creator_123",
  "amount": 500,
  "reason": "manual promotional grant",
  "source_type": "manual",
  "expires_at": "2026-06-30T23:59:59Z"
}
```

Behavior:

- Creates a signed ledger entry
- Updates wallet summary using optimistic locking
- Requires admin audit logging

### 6.13 `POST /admin/billing/domains/bind`

Request:

```json
{
  "creator_bid": "creator_123",
  "host": "learn.example.com",
  "verification_method": "dns_txt"
}
```

Behavior:

- Creates or updates a domain binding
- Generates verification token
- Returns DNS instructions and current status

## 7. DTO And Type Shapes

### 7.1 `BillingPlan`

```ts
type BillingPlan = {
  plan_bid: string;
  plan_code: string;
  display_name: string;
  description: string;
  billing_interval: 'month' | 'year' | 'manual';
  billing_interval_count: number;
  currency: string;
  price_amount: number;
  credit_allocation: number;
  auto_renew_enabled: boolean;
  entitlements: BillingEntitlements;
};
```

### 7.2 `BillingTopupProduct`

```ts
type BillingTopupProduct = {
  topup_bid: string;
  topup_code: string;
  display_name: string;
  description: string;
  currency: string;
  price_amount: number;
  credit_amount: number;
};
```

### 7.3 `CreatorBillingOverview`

```ts
type CreatorBillingOverview = {
  creator_bid: string;
  wallet: {
    available_credits: number;
    reserved_credits: number;
    lifetime_granted_credits: number;
    lifetime_consumed_credits: number;
  };
  subscription: BillingSubscription | null;
  entitlements: BillingEntitlements;
  branding: CreatorBrandingConfig | null;
  billing_alerts: Array<{
    type: string;
    message: string;
  }>;
};
```

### 7.4 `BillingSubscription`

```ts
type BillingSubscription = {
  subscription_bid: string;
  status: 'draft' | 'active' | 'past_due' | 'paused' | 'cancel_scheduled' | 'canceled' | 'expired';
  plan_bid: string;
  plan_code: string;
  billing_provider: string;
  provider_subscription_id: string;
  billing_anchor_at: string;
  current_period_start_at: string;
  current_period_end_at: string;
  grace_period_end_at: string;
  cancel_at_period_end: boolean;
  next_plan_bid: string;
  last_renewed_at: string;
  last_failed_at: string;
};
```

### 7.5 `BillingLedgerItem`

```ts
type BillingLedgerItem = {
  ledger_bid: string;
  entry_type: 'grant' | 'consume' | 'refund' | 'expire' | 'adjustment' | 'hold' | 'release';
  source_type: 'subscription' | 'topup' | 'gift' | 'usage' | 'refund' | 'manual';
  source_bid: string;
  amount: number;
  balance_after: number;
  expires_at: string;
  consumable_from: string;
  metadata: Record<string, any>;
  created_at: string;
};
```

### 7.6 `BillingEntitlements`

```ts
type BillingEntitlements = {
  branding_enabled: boolean;
  custom_domain_enabled: boolean;
  priority_class: number;
  max_concurrency: number;
  analytics_tier: 'basic' | 'deep' | 'enterprise';
  support_tier: 'standard' | 'priority' | 'dedicated';
  feature_payload?: Record<string, any>;
};
```

### 7.7 `CreatorBrandingConfig`

```ts
type CreatorBrandingConfig = {
  creator_bid: string;
  logo_wide_url: string;
  logo_square_url: string;
  favicon_url: string;
  home_url: string;
  active_domain_host: string;
};
```

## 8. Backend Design Details

### 8.1 Checkout Flow

Subscription checkout:

1. Load catalog item by `plan_bid`
2. Resolve creator wallet and existing subscription
3. Determine operation type:
   - new subscription
   - immediate upgrade
   - resume
4. Create `billing_orders`
5. Create `billing_payment_attempts`
6. Initiate provider recurring checkout
7. Return checkout payload

Top-up checkout:

1. Load top-up product
2. Confirm creator has an active or past-due subscription
3. Create `billing_orders`
4. Create `billing_payment_attempts`
5. Initiate one-time provider payment
6. On payment success, grant credits into wallet ledger

### 8.2 Settlement Flow

Settlement job runs periodically:

1. Load creators with active or past-due subscriptions
2. For each creator, resolve owned published `shifu_bid` list
3. Fetch unsettled `bill_usage` records for those shifus where `billable=1` and scene is production
4. Resolve `billing_usage_rates`
5. Convert usage into credit deltas
6. Write `billing_ledger_entries` with `entry_type=consume`
7. Update `billing_wallets.available_credits`
8. Persist settlement cursor or linkage metadata to prevent double settlement

Double-settlement prevention:

- Add settlement metadata into `bill_usage.extra`
- Or add a separate settlement mapping table in a later iteration if the existing JSON field proves insufficient

V1 decision:

- Use `bill_usage.extra.billing_ledger_bid` and `bill_usage.extra.settled_at` markers to avoid introducing an extra mapping table

### 8.3 Balance Gating

Before a production billable action starts:

1. Resolve creator by `shifu_bid`
2. Load current `billing_wallets`
3. Load current `billing_subscriptions`
4. Confirm subscription state is `active` or `past_due`
5. Confirm `available_credits > 0`
6. Confirm creator concurrency is below entitlement limit
7. Admit workload into execution control layer

If any check fails:

- Reject the workload before expensive provider calls
- Return billing-specific error codes and i18n messages

### 8.4 Recurring Payment Abstraction

Add new provider adapter interfaces under `service/billing/payment_providers`.

Required methods:

- `create_subscription_checkout()`
- `resume_subscription()`
- `cancel_subscription()`
- `sync_subscription_state()`
- `handle_webhook()`
- `refund_order()`

Stripe implementation:

- Uses Stripe customer, subscription, invoice, and webhook primitives
- Supports checkout for recurring plan start and immediate upgrade proration

Domestic recurring implementation:

- Uses provider recurring signing and deduction primitives if supported
- If Ping++ does not expose required recurring support, add a new domestic provider adapter without changing the normalized internal API

### 8.5 Renewal Jobs

Required recurring jobs:

- `grant_subscription_allocation_job`
- `subscription_renewal_trigger_job`
- `subscription_retry_job`
- `subscription_expire_job`
- `scheduled_downgrade_apply_job`
- `billing_reconciliation_job`
- `domain_verification_job`

Execution model:

- Store scheduled units in `billing_renewal_events`
- Drive execution with a background runner that scans due events
- Mark each event atomically through `pending -> processing -> done/failed`

### 8.6 Admin And Audit

Admin billing adjustments must:

- Record operator id
- Record reason
- Write immutable ledger entry
- Never mutate prior ledger rows

Provider event handling must:

- Deduplicate by provider event id
- Store full normalized request and response payloads
- Allow replay-safe processing

## 9. Entitlements And Runtime

### 9.1 Creator-Scoped Branding

Current runtime config returns global branding. V1 changes:

1. Resolve request host or active creator context
2. Load creator entitlements and domain binding
3. Return creator-scoped branding values if enabled
4. Fall back to global config otherwise

New runtime fields:

- `billingEntitlements`
- `brandingConfig`
- `domainBinding`
- `creatorBillingStatus`

### 9.2 Domain Resolution

Request resolution order:

1. If request host matches an active `billing_domain_bindings.host`, use that creator
2. Else if explicit creator context is already known from authenticated admin path, use that creator
3. Else return global defaults

### 9.3 Priority And Concurrency Enforcement

V1 minimum viable execution control:

- Introduce a creator-aware admission service
- Track in-flight billable jobs by `creator_bid`
- Reject or defer jobs exceeding `max_concurrency`
- Sort queued jobs by `priority_class`, then `created_at`

This can be implemented first in-process, but the code must isolate the interface so a later external queue can replace it.

### 9.4 Analytics Entitlements

Analytics depth controls:

- Whether creator can access basic usage summary only
- Whether creator can access detailed billing ledger and deep consumption breakdown
- Whether creator can access export or enterprise-only metrics later

### 9.5 Support Tier

Support tier is stored in billing entitlements but enforced operationally outside core request path. V1 only exposes and stores it.

## 10. Frontend Design

### 10.1 Creator Billing Center

Add a creator-facing billing area in Cook Web containing:

- Catalog page for plans and top-ups
- Current subscription card
- Wallet balance card
- Credit ledger table
- Billing orders and invoices table
- Cancel or resume subscription actions
- Domain binding form
- Branding asset management form

Recommended frontend paths:

- `/admin/billing`
- `/admin/billing/ledger`
- `/admin/billing/orders`
- `/admin/billing/domains`

### 10.2 Runtime Bootstrap Changes

Extend runtime initialization to load creator-scoped billing fields alongside existing config:

- Entitlements
- Branding override
- Domain binding state
- Active billing warnings

### 10.3 Admin Billing Operations

Add admin views for:

- Subscription list
- Billing order list
- Renewal failure queue
- Manual credit adjustments
- Domain verification status

## 11. Migration And Rollout

### 11.1 Database Rollout

Rollout sequence:

1. Add new billing tables
2. Seed catalog and usage rates
3. Add runtime config additions
4. Deploy billing APIs and admin tooling
5. Deploy creator-facing UI
6. Enable creator billing for selected creators
7. Enable production settlement

### 11.2 Seed And Config Support

Use `sys_configs` for:

- Feature flags
- Default catalog visibility
- Low-balance threshold
- Grace period length
- Global fallback branding values

Do not store creator-specific mutable billing state in `sys_configs`.

### 11.3 Backfill

No legacy course orders are migrated into the new billing domain.

Optional backfills:

- Seed wallets for invited pilot creators
- Seed gift or trial credits
- Seed catalog and pricing rules

### 11.4 Safety Guards

- Keep all new routes additive
- Do not change existing `/order` request or response shapes
- Put settlement job behind a feature flag initially
- Allow operator-only manual correction via admin ledger adjustment

## 12. Risks And Dependencies

### 12.1 Domestic Recurring Billing Capability

This is the largest external dependency. The current domestic provider path does not prove recurring support in code. Implementation must confirm provider capabilities before coding production flow.

Mitigation:

- Keep provider contract normalized
- Implement Stripe recurring first
- Gate domestic recurring rollout behind provider capability validation

### 12.2 Queue And Concurrency Infrastructure

Current repository does not have a dedicated business task queue. Entitlement enforcement therefore requires new admission and scheduling code.

Mitigation:

- Implement a minimal creator-aware execution control layer in v1
- Keep the interface abstract enough for later queue infrastructure replacement

### 12.3 Domain Binding And SSL Automation

Custom-domain binding requires DNS verification and likely SSL provisioning outside the current codebase.

Mitigation:

- V1 stores bindings and verification tokens
- Automated SSL activation can be phased after domain ownership validation if infrastructure is not yet available

### 12.4 Billing Consistency

Wallet drift can occur if webhook processing, settlement, or manual adjustments are not idempotent.

Mitigation:

- Immutable ledger
- Optimistic locking on wallet summary
- Provider event deduplication
- Reconciliation jobs

## 13. Implementation Summary

The recommended implementation path is:

1. Add billing schema and catalog
2. Add wallet and ledger core
3. Add recurring payment abstraction
4. Add creator-scoped entitlement resolution
5. Add settlement from `bill_usage`
6. Add creator and admin billing UIs
7. Add execution gating for credits, priority, and concurrency
8. Roll out behind feature flags while preserving legacy course order flow
