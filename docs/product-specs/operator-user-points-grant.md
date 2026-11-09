---
title: Operator User Points Grant
status: implemented
owner_surface: frontend
last_reviewed: 2026-11-09
canonical: true
---

# Operator User Points Grant

## Scope

An operator can issue credits from the row action in
`Admin -> Operations -> Users`. The grant dialog shows the target account,
current usable balance, and displayed expiry. The balance link still opens the
user detail credits section for ledger review.

The dialog separates ordinary reward and compensation credits, referral
reward credits, and package grants. A package grant follows the package
endpoint and its own lifecycle. The ordinary credit flow does not create a
commercial order.

## Ordinary Credit Grant

- Enter a positive decimal credit amount and choose reward or compensation.
- Enter a positive integer validity duration in days, months, or years. The
  amount of time starts blank and the unit defaults to days.
- An optional note records operator context in the ledger.
- Review the amount, source, and estimated expiry in the confirmation step.
  After a successful request, the dialog reports the server's expiry and the
  user list refreshes with its filters and pagination intact.

Ordinary credits take effect immediately. Days are 24-hour periods. Months
and years clip to the destination month end when needed. The server computes
expiry from its UTC clock. The dialog refreshes its estimate at confirmation
and formats the persisted expiry for display after success.

## API

`POST /shifu/admin/operations/users/{user_bid}/credits/grant` requires an
operator and an eligible target account. An ordinary grant request includes:

```json
{
  "request_id": "grant-request-1",
  "amount": "100",
  "grant_source": "reward",
  "validity_value": 1,
  "validity_unit": "month",
  "note": "Campaign reward"
}
```

The route rejects the former `validity_preset` field. The result includes the
resolved UTC `expires_at`, grant and ledger identifiers, and the refreshed
credit summary. Reusing a request ID returns the original persisted grant and
expiry without writing or notifying again. Legacy rows can return null
duration fields.

The referral-reward variant uses `grant_type=referral_reward` and
`grant_source=reward`. Omit both duration fields. It uses the referral grant
service's own one-calendar-month rule. Package grants use
`POST /shifu/admin/operations/users/{user_bid}/packages/grant`.

## Credit Accounting and Display

Ordinary grants create a credit bucket and corresponding ledger entry under
the subscription credit display family. They remain consumable within their
effective window without an active subscription. Top-up credits require an
active subscription to be consumable and can still appear in the top-up
breakdown.

The operator summary counts currently consumable credits in
`available_credits`. It displays the active subscription expiry when present,
or the earliest qualifying manual-grant expiry otherwise. The operator ledger
labels manual grants by source and displays any explicit note.

See [operator credit reads](operator-user-points-columns.md) and
[manual credit validity and analytics](../design-docs/billing-subscription-design.md#manual-operator-credit-validity)
for the related contracts.

## Verification

- `src/api/flaskr/service/shifu/admin_operations/user_credits.py` owns the
  operator write entry. `test_admin_users.py` covers API dispatch, summary
  refresh, and ledger classification.
- `src/api/tests/service/billing/test_manual_credit_validity.py` covers expiry,
  input rejection, persisted metadata, and retry behavior.
- `UserCreditGrantDialog.tsx` and its adjacent test cover input, confirmation,
  expiry estimates, and the submitted request.
