# New Creator Trial Product

## Summary

The creator free trial is now a first-class record in `billing_products`
instead of a runtime sys-config program.

Business policy stays the same:

- one-time only
- `100` credits
- valid for `15` days
- zero-price
- non-auto-renew

The trial remains publicly visible in billing overview, but it is rendered
through the existing free card instead of being mixed into the paid plan grid.

There is no separate "trial credits" runtime category. Trial grants are
exposed and consumed as normal `subscription` credits, alongside the only other
creator-consumable category: `topup`.

## Product Model

The database-backed catalog keeps a fixed plan product for the trial. Runtime
reads the product row from `billing_products`; it does not fall back to code
seeds anymore.

The canonical row is maintained by migrations:

- `product_bid = billing-product-plan-trial`
- `product_code = creator-plan-trial`
- `product_type = plan`
- `billing_mode = manual`
- `billing_interval = none`
- `price_amount = 0`
- `credit_amount = 100`
- `auto_renew_enabled = false`

`metadata` carries the trial-only behavior:

- `trial_valid_days = 15`
- `public_trial_offer = true`
- `starts_on_first_grant = true`
- `highlights = [...]`

## Eligibility And Idempotency

The system only auto-opens the trial when all guards pass:

1. the user is a creator in the current request
2. `PostAuthContext.creator_granted_now` is `true`
3. the creator currently has no subscription
4. no historical trial order or subscription exists for the fixed trial product
5. no legacy config-era trial ledger exists

Legacy compatibility is kept only for duplicate prevention. Old users who
already consumed the config-era trial are reported as `granted` and do not
receive the productized trial again.

## Bootstrap Flow

The automatic bootstrap happens in the billing post-auth hook, not in billing
overview.

When the guard passes, billing creates the trial inside one transaction:

- a zero-amount `BillingOrder` with `order_type=subscription_start`
- a matching `BillingSubscription`
- `payment_provider='manual'`
- `paid_at=now`
- `current_period_end_at = now + 15 days`

After that, the existing paid-order helpers are reused:

- `grant_paid_order_credits(...)`
- `activate_subscription_for_paid_order(...)`

This keeps the trial on the same wallet / ledger / subscription path as paid
products. New trial grants therefore create:

- a `subscription` wallet bucket
- a `grant` ledger sourced from the order/subscription flow
- an active subscription record

## Lifecycle

The trial subscription is a fixed-term manual subscription.

It enters the existing subscription lifecycle pipeline and schedules a normal
`EXPIRE` renewal event. After 15 days, the subscription transitions from
`active` to `expired` through the standard renewal executor rather than
remaining active forever.

## Overview API

`GET /billing/overview` exposes a product-backed `trial_offer`:

- `enabled`
- `status`
- `product_bid`
- `product_code`
- `display_name`
- `description`
- `currency`
- `price_amount`
- `credit_amount`
- `valid_days`
- `highlights`
- `starts_on_first_grant`
- `granted_at`
- `expires_at`

`status` remains one of:

- `disabled`
- `ineligible`
- `eligible`
- `granted`

The read model prefers product/order/subscription state. Legacy ledger-only
users still resolve to `granted`. If the trial product row is missing, the fix
is to apply the billing catalog migrations rather than editing runtime code.
