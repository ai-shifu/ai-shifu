---
title: Billing Subscription Purchase SMS Design
status: implemented
owner_surface: backend
last_reviewed: 2026-11-09
canonical: true
---

# Billing Subscription Purchase SMS Design

Original design: 2026-04-20

## Goal

Send one asynchronous SMS notification after a creator billing subscription
order first becomes paid. The notification must reuse the existing Aliyun SMS
integration and include:

- `product`: subscription plan name
- `date`: subscription expiry time

Covered order types:

- `subscription_start`
- `subscription_upgrade`
- `subscription_renewal`

## Trigger Source of Truth

The shared paid-order side effects in `billing/paid_side_effects.py` stage the
notification when billing confirms payment. Webhook and sync flows dispatch
it after commit. Payment adapters and callback routes do not send SMS.

## Design

### SMS sending

- Extend `src/api/flaskr/api/sms/aliyun.py` with a reusable template SMS helper.
- Keep `send_sms_code_ali()` as a thin wrapper so auth verification behavior
  stays unchanged.
- Add `ALIBABA_CLOUD_SMS_SUBSCRIPTION_SUCCESS_TEMPLATE_CODE` for the billing
  notification template.

### Billing orchestration

- Add a billing helper to mark `bill_orders.metadata` with
  `notifications.subscription_purchase_sms`.
- The helper records a pending notification state inside the same DB
  transaction that marks the order paid.
- Celery enqueue happens only after commit succeeds.
- Duplicate webhooks and duplicate manual sync calls must not enqueue another
  SMS task once the notification has left the initial state.

### Worker behavior

- Add Celery task `billing.send_subscription_purchase_sms`.
- The worker claims a `pending` or `failed_provider` notification under a
  row lock and commits its `processing` state. The provider call runs outside
  the transaction. The worker then locks the order again to finalize the result.
- Resolve SMS payload from:
  - phone: `load_user_aggregate(order.creator_bid).mobile`
  - product: translated `BillingProduct.display_name_i18n_key`, falling back to
    `product_code`
  - date: `BillingSubscription.current_period_end_at`, with renewal metadata
    fallback when needed
- Format `date` as an absolute timestamp in the app timezone.
- Persist a terminal notification state back into `bill_orders.metadata`.

## Failure Model

- `sent`: provider request succeeded
- `skipped_no_mobile`: creator has no mobile number
- `failed_missing_date`: no expiry date could be resolved
- `failed_provider`: provider call failed; worker may retry

Only provider failures should retry automatically.

## Compensation

- Use `flask console billing requeue-subscription-purchase-sms` to re-enqueue
  an order in `pending` or `failed_provider` state.
- No new public HTTP endpoint is required.

## Tests

`src/api/tests/service/billing/test_billing_subscription_sms.py` covers the
checkout sync, webhook, task, and requeue paths.

- SMS contract tests for the generic helper and the verification-code wrapper
- Billing webhook tests for first-paid enqueue and duplicate suppression
- Billing sync tests for first-paid enqueue and duplicate suppression
- Billing task tests for success, skip, missing date, provider retry, and
  duplicate task safety
- Regression coverage for existing auth SMS behavior
