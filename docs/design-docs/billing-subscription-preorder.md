---
title: Billing Subscription Preorder
status: proposed
owner_surface: backend
last_reviewed: 2026-05-25
canonical: true
---

# Billing Subscription Preorder

## Background

AI-Shifu currently supports creator plan checkout, immediate plan activation,
manual/native one-time payment activation, renewal compensation, and
wallet-bucket-based credit accounting. The new package ordering requirement adds a
preorder lifecycle for non-auto-debit payment flows so creators can pay before
the current cycle ends and keep service continuity without provider-managed
recurring billing.

This design is based on the external requirement artifact named
`AI-Shifu 套餐订购与预购方案 (1).pdf`. The PDF is not committed to the
repository, so the assumptions needed for implementation are captured directly
in this document. This design extends the existing billing model documented in
`docs/billing-subscription-design.md`.

## Goals

- Support plan preorder for next-cycle renewal and downgrade.
- Keep immediate upgrade available when the target plan is higher tier.
- Allow at most one pending preorder per creator subscription.
- Preserve the zero-refund product rule for preorder and upgrade flows.
- Keep package credits auditable through `bill_orders`, `bill_subscriptions`,
  `credit_wallet_buckets`, and `credit_ledger_entries`.
- Keep self-managed cycle rules for Pingxx, native Alipay, native WeChat Pay,
  and manual grants: the local billing cycle decides the service window.

## Non-Goals

- Do not add provider-managed prepaid preorder for Stripe recurring
  subscriptions in the first implementation.
- Do not allow users to cancel preorder, switch preorder target, or request an
  automatic refund through this flow.
- Do not merge topup package behavior into subscription preorder. Topups remain
  independently purchased credit packages, but their credits still require an
  effective plan to be consumed.
- Do not re-open expired trial plans for self-service purchase.

## Product Model

Each plan needs a stable tier field in addition to price, cycle, and credit
amount.

| Field | Existing Source | Requirement |
| --- | --- | --- |
| Price | `BillingProduct.price_amount` | Used for payable amount and preorder credit offset. |
| Cycle | `billing_interval`, `billing_interval_count` | Each plan defines its own cycle; cycles do not inherit or concatenate. |
| Credits | `BillingProduct.credit_amount` | Granted per effective subscription cycle. |
| Tier | proposed `BillingProduct.metadata.plan_tier` or a dedicated column | Drives upgrade, renewal, and downgrade decisions. Do not infer tier from price. |

`sort_order` may stay a display ordering hint, but preorder business logic
should use a tier value. If a dedicated column is too disruptive for the first
iteration, use `metadata.plan_tier` and add a read helper so the decision point
is explicit and testable.

## Subscription States

The creator-facing plan relation has four states:

| State | Meaning | Allowed Actions |
| --- | --- | --- |
| Active, no preorder | Current subscription is inside its effective period and no next-cycle plan is prepaid. | Immediate upgrade, preorder renewal, preorder downgrade. |
| Active, with preorder | Current subscription is inside its effective period and one future paid plan exists. | Immediate upgrade only. The preorder payment offsets the upgrade order. |
| Expired | No effective active subscription remains. | New purchase only. |
| Trial | Trial plan is active or expired. | Active trial can upgrade or expire; it cannot be preordered. Expired trial cannot be purchased again through self-service. |

Only one pending preorder is allowed per subscription. The invariant is:

```text
creator_bid + active subscription -> at most one preorder order in pending_effective state
```

## User Actions

### New Purchase

- Applies when there is no active subscription.
- Creates `subscription_start`.
- Payment success immediately creates or activates `bill_subscriptions`,
  starts a new cycle, and grants subscription credits.
- Expired paid users are treated as new purchase users; no old credits carry
  forward.

### Immediate Upgrade

- Applies when the target plan tier is greater than the current plan tier.
- If there is no preorder, user pays the full target plan price.
- If there is an active preorder, user pays:

```text
payable_amount = target_plan.price_amount - preorder_order.paid_amount
```

- The absorbed preorder is no longer eligible for next-cycle activation.
- The payable amount must remain positive. If catalog pricing would make the
  preorder offset cover the full target price, checkout is rejected as a
  pricing configuration error instead of granting an upgrade without a provider
  charge.
- The new plan starts immediately.
- The new cycle length is calculated from the target plan itself.
- Available subscription credits become current remaining subscription credits
  plus the new plan full credits. This is not prorated monetary credit
  carry-over: unused credits stay as credits, and the old cycle is realigned to
  the new plan window rather than converted into a cash discount.

### Preorder Renewal

- Applies when the target plan tier equals the current plan tier.
- Payment happens now; plan switch happens at current cycle end.
- Current subscription and current subscription credits remain unchanged until
  cycle end.
- At cycle transition, unused subscription credits from the old cycle are
  expired, then the new cycle grants the target plan full credits.

### Preorder Downgrade

- Applies when the target plan tier is lower than the current plan tier.
- Payment happens now; plan switch happens at current cycle end.
- Current subscription and current credits remain unchanged until cycle end.
- At cycle transition, unused subscription credits from the old cycle are
  expired, then the new cycle grants the target plan full credits.

### Unsupported Actions

| Scenario | Handling |
| --- | --- |
| Current plan is already highest tier and user requests upgrade | Reject. |
| Current plan is already lowest tier and user requests downgrade | Reject. |
| User has an active preorder and requests another preorder | Reject. |
| User requests preorder cancel | Reject in self-service. |
| User requests preorder target change | Reject in self-service. |
| Active preorder user requests immediate upgrade | Allow, absorb preorder payment as offset. |
| Expired user requests upgrade or preorder | Treat as new purchase only. |

## Data Model Design

### Plan Tier

Add a plan-tier resolver:

```text
resolve_plan_tier(product) -> int
```

Initial storage options:

- Preferred: add `bill_products.plan_tier` as an indexed integer column.
- Low-migration option: store `metadata.plan_tier` and enforce presence for
  self-service plan products.

The resolver should reject preorder/upgrade decisions when either current or
target plan has no tier.

### Preorder Record

Use `bill_orders` as the preorder payment truth source. A preorder is a paid
subscription order with metadata that says it is not yet effective.

Proposed order metadata:

```json
{
  "checkout_type": "subscription_preorder",
  "preorder_state": "pending_effective",
  "preorder_target_product_bid": "target-product-bid",
  "preorder_effective_at": "2026-06-24T23:59:59",
  "preorder_source_subscription_bid": "subscription-bid",
  "absorbed_by_bill_order_bid": null,
  "absorbed_at": null
}
```

`preorder_effective_at` is an audit/display snapshot taken at checkout. The
cycle-end executor must use the latest subscription/event boundary as the
source of truth and realign `renewal_cycle_start_at`/`renewal_cycle_end_at`
before applying the preorder, so admin period extensions do not activate the
preorder too early.

Recommended state values:

| State | Meaning |
| --- | --- |
| `pending_effective` | Paid and waiting for current cycle end. |
| `effective_applied` | Cycle transition consumed this preorder and activated the target plan. |
| `absorbed_by_upgrade` | Immediate upgrade used this preorder payment as a price offset. |
| `voided_admin_only` | Reserved for exceptional admin correction, not self-service. |

### Subscription Pointer

Keep `bill_subscriptions.next_product_bid` as the user-visible next-cycle
target. Add metadata to identify the paid preorder order:

```json
{
  "preorder_order_bid": "bill-order-bid",
  "preorder_payment_provider": "alipay",
  "preorder_channel": "alipay_qr"
}
```

This avoids a new table in the first implementation while preserving a direct
link from subscription state to the paid preorder. If the preorder lifecycle
later needs multiple admin actions or audit events, promote it into a dedicated
`bill_subscription_preorders` table.

### Renewal Events

Use `bill_renewal_events` for the cycle transition:

- `downgrade_effective` can continue to represent next-product application.
- For same-tier renewal preorder, either reuse `renewal` with a linked paid
  preorder order or add a `preorder_effective` event type.

Preferred first implementation: reuse `renewal` for same-tier renewal and
`downgrade_effective` for lower-tier preorder, because current code already
syncs renewal events around `next_product_bid`.

## API Design

Keep the existing subscription checkout endpoint but make the action explicit.

```http
POST /api/billing/subscriptions/checkout
```

Request:

```json
{
  "product_bid": "target-product-bid",
  "payment_provider": "alipay",
  "channel": "alipay_qr",
  "action": "preorder"
}
```

Allowed `action` values:

- `upgrade_immediate`
- `preorder`

Rules:

- If no active subscription exists, create `subscription_start` and return
  `checkout_type=subscription` plus `effective_mode=immediate` so the frontend
  can show that the request became an immediate new purchase rather than a
  preorder.
- `upgrade_immediate` requires target tier greater than current tier.
- `preorder` requires no active preorder and target tier less than or equal to
  current tier.
- If an active preorder exists, `upgrade_immediate` is the only allowed
  self-service action.
- Stripe recurring subscriptions should reject `preorder` in v1 unless product
  chooses to expose a non-recurring one-time preorder path.

Response should include action details so the frontend can render confirmation
copy without re-implementing business logic:

```json
{
  "bill_order_bid": "order-bid",
  "order_type": "subscription_upgrade",
  "checkout_type": "subscription_preorder",
  "effective_mode": "cycle_end",
  "current_product_bid": "current-product-bid",
  "target_product_bid": "target-product-bid",
  "preorder_order_bid": "existing-preorder-order-bid",
  "prepaid_offset_amount": 990,
  "payable_amount": 19810
}
```

## Payment and Activation Flow

### Preorder Payment Success

When a preorder order becomes paid:

1. Do not grant credits to `available_credits`.
2. Create or update a subscription bucket only as reserved credits if the
   current implementation requires a wallet placeholder.
3. Set `bill_subscriptions.next_product_bid`.
4. Store `preorder_order_bid` in subscription metadata.
5. Upsert a renewal/downgrade-effective event at
   `current_period_end_at`.
6. Keep the current subscription period unchanged.

If using reserved credits, the grant ledger must use:

```json
{
  "bucket_credit_state": "reserved",
  "reserved_until": "cycle-end"
}
```

### Cycle-End Application

At cycle end:

1. Find the paid preorder order from subscription metadata or latest matching
   paid order.
2. Expire old-cycle remaining subscription credits.
3. Move reserved credits to available credits, or grant the target product
   credits if no reserved bucket was created.
4. Set `product_bid = next_product_bid`.
5. Clear `next_product_bid`.
6. Mark preorder metadata as `effective_applied`.
7. Set the new cycle window from the target plan.
8. Sync the next renewal or expire event.
9. Realign active topup bucket expiration to the new cycle end.

### Immediate Upgrade With Existing Preorder

When payment succeeds:

1. Load the active preorder order.
2. Set upgrade order amount to
   `target price - preorder paid amount`; reject checkout if that value is not
   positive.
3. Mark the preorder order metadata as `absorbed_by_upgrade`.
4. Void any reserved credit grant created by the preorder so it cannot be
   released at the original cycle boundary.
5. Clear subscription preorder metadata and `next_product_bid`.
6. Activate the target plan immediately.
7. Merge current remaining subscription credits with new plan full credits.
8. Start the new cycle from upgrade time using the target plan cycle.

This flow must be idempotent. Repeated sync/webhook processing must not absorb
the same preorder more than once.

## Credit Rules

| Scenario | Credit Handling |
| --- | --- |
| Immediate upgrade | Available subscription credits = old remaining + target full credits. |
| Preorder renewal | Old remaining credits expire at cycle end; target full credits become available in the new cycle. |
| Preorder downgrade | Old remaining credits expire at cycle end; target full credits become available in the new cycle. |
| Natural expiry without preorder | Remaining subscription credits expire. |
| Topup credits | Not changed by preorder; still require an effective subscription to be consumable. |

Current code already has helpers close to this model:

- immediate paid orders activate subscriptions in
  `src/api/flaskr/service/billing/subscriptions.py`
- renewal reservation and release are represented with `reserved_credits`
- old-cycle subscription credits can be expired during transition

The implementation should extend those helpers rather than introducing a
parallel wallet mutation path.

## Frontend and Admin Requirements

Creator UI should render the server-computed action state:

- active plan
- remaining cycle end
- pending preorder target, paid amount, and effective date
- allowed next actions
- upgrade offset amount when an active preorder exists

Admin billing pages should expose:

- active subscription product
- `next_product_bid`
- linked preorder order
- preorder state
- absorbed/applied timestamps

Self-service cancel or target-switch buttons should not be exposed in v1.

## Migration Strategy

1. Add plan tier source and backfill active plan products.
2. Add preorder metadata helpers and tests without changing public behavior.
3. Extend checkout route with explicit action validation.
4. Implement paid preorder reservation and next-cycle event sync.
5. Implement cycle-end preorder activation.
6. Implement immediate upgrade with preorder offset.
7. Update frontend billing overview and checkout confirmation.
8. Add admin read-model exposure.

## Validation

Focused backend tests should cover:

- no active subscription -> new purchase
- active A -> immediate upgrade to B/C
- active A -> preorder renewal A
- active B/C -> preorder downgrade
- active preorder -> reject another preorder
- active preorder -> immediate upgrade with prepaid offset
- expired subscription -> new purchase only
- trial active -> upgrade allowed, preorder rejected
- trial expired -> self-service purchase rejected for trial
- idempotent webhook/sync for preorder paid, absorbed, and applied states

Recommended checks:

```bash
cd src/api && pytest tests/service/billing/test_billing_write_routes.py tests/service/billing/test_billing_renewal_execution.py -q
python scripts/check_repo_harness.py
```

## Open Decisions

- Whether plan tier should be a first-class `bill_products.plan_tier` column or
  a required `metadata.plan_tier` field for v1.
- Whether same-tier preorder renewal should reuse `subscription_renewal` or get
  a new explicit order type such as `subscription_preorder`.
- Whether preorder credits should always be represented as `reserved_credits` at
  payment time, or granted only at cycle-end application.
- Whether Stripe should hide preorder entirely or offer a non-recurring preorder
  mode for manually managed subscriptions.
