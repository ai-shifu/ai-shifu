# Post-Auth Trial Bootstrap

## Summary

Creator trial bootstrap is a post-auth follow-up that runs only when the user
was promoted to creator during the current request.

This keeps login success independent from billing side effects while avoiding
the old behavior where existing creators could be re-evaluated on every login.
The runtime trial definition is read only from the product row in
`billing_products`.

## Request Contract

`PostAuthContext` now includes:

- `creator_granted_now: bool`

It means "this request is the one that just granted creator admin capability".

The creator-upgrade chain now returns that signal end-to-end:

- `init_first_course(...)`
- `ensure_admin_creator_and_demo_permissions(...)`
- `verify_phone_code(...)`
- `/user/ensure_admin_creator`
- phone login flow
- Google OAuth flow

The post-auth runner receives the final value through `PostAuthContext`.

## Billing Hook Policy

Billing registers a best-effort post-auth hook through the existing extension
mechanism.

The hook immediately returns unless `creator_granted_now` is `true`.

This is the key policy change:

- first-time creator grant in the current request: eligible for auto bootstrap
- existing creator logging in again: no auto bootstrap attempt
- non-creator login: no auto bootstrap attempt

Failures inside the billing hook are logged but must not block authentication
or creator promotion.

## Bootstrap Guard

Before creating the trial order, billing verifies:

1. the user is currently a creator
2. there is no current creator subscription
3. there is no historical trial product order or subscription
4. there is no legacy pre-product trial ledger

Only then does billing create the zero-amount manual order and subscription and
reuse the normal paid-order grant helpers.

## Read Model

`GET /billing/overview` is now read-only for trial state. It never grants
credits.

It reports:

- product-backed eligibility for the public trial offer
- current trial grant state from order/subscription records
- legacy grant state from the old ledger-only implementation

This separation keeps all trial mutations in post-auth bootstrap and leaves
overview as a pure query endpoint with no sys-config fallback.
