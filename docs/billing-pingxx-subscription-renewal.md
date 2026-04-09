# Billing Pingxx Subscription Renewal

Updated: 2026-04-09

## Summary

- Pingxx subscriptions are platform-managed recurring plans, not provider-managed subscriptions.
- Initial Pingxx subscription checkout creates a draft subscription plus a pending billing order and immediately creates a Pingxx charge for the first payment.
- Active Pingxx subscriptions schedule renewal preparation 7 days before the period end, but only create or reuse a pending local renewal order at that time.
- Users continue payment for pending Pingxx subscription orders from the billing orders UI, which creates or refreshes the current Pingxx charge.
- If a Pingxx renewal order is paid before the next cycle starts, credits are granted with a future `effective_from` and the subscription period is not advanced until the cycle boundary.
- If a Pingxx renewal order is paid after the cycle already ended, the renewal is shifted to start from the actual payment time.

## Backend Rules

### Checkout

- `POST /api/billing/subscriptions/checkout` accepts `payment_provider=pingxx`.
- Pingxx subscription checkouts keep `provider_subscription_id=""` and `provider_customer_id=""`.
- The checkout response remains `BillingCheckoutResultDTO`; Pingxx returns `payment_payload` with the charge credential.

### Renewal Scheduling

- Stripe keeps the existing single `renewal` event at `current_period_end_at`.
- Pingxx active auto-renew subscriptions schedule:
  - `renewal` at `max(current_period_start_at, current_period_end_at - 7 days)`
  - `expire` at `current_period_end_at`
- Pingxx renewal preparation creates at most one pending renewal order per target cycle and stores:
  - `checkout_type=subscription_renewal`
  - `provider_reference_type=charge`
  - `renewal_cycle_start_at`
  - `renewal_cycle_end_at`

### Pending Order Checkout

- `POST /api/billing/orders/{billing_order_bid}/checkout` is only valid for creator-owned pending Pingxx billing orders.
- Supported order types:
  - `subscription_start`
  - `subscription_renewal`
- The endpoint creates or refreshes the Pingxx charge and returns the existing checkout payload shape.

### Renewal Activation

- Renewal credit buckets always use the resolved cycle start/end saved in order metadata.
- Activation rules for Pingxx renewal orders:
  - Paid before `renewal_cycle_start_at`: grant future credits only; subscription period stays unchanged until the boundary.
  - Paid within the target renewal cycle: activate the original target cycle immediately.
  - Paid after `renewal_cycle_end_at`: shift to a new cycle starting at `paid_at`, save `applied_cycle_start_at` and `applied_cycle_end_at`, and activate that shifted cycle.
- `expire` first checks for a paid renewal order for the current target cycle. If present, it activates that renewal instead of expiring the subscription.

## Frontend Rules

- Plan cards reuse the existing automatic provider selection pattern:
  - prefer Stripe when available
  - fall back to Pingxx when Stripe is unavailable
- The UI does not add explicit provider choice buttons for plans.
- Billing orders expose a continue-payment action for pending Pingxx subscription orders and reuse the existing Pingxx QR opening flow.
