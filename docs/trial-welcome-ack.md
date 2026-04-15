# Trial Welcome Ack Design

## Summary

Persist the welcome dialog acknowledgement for the auto-bootstrapped creator
trial so clearing browser storage does not cause the dialog to reopen.

The source of truth stays in billing:

- `trial_offer.status === "granted"` means the trial has actually been opened
- `trial_offer.welcome_dialog_acknowledged_at` means the welcome dialog has
  already been acknowledged

## Persistence Strategy

- Reuse existing billing metadata fields; do not add a migration.
- Write the acknowledgement timestamp to the first available trial grant record
  in this order:
  - `billing_subscriptions.metadata`
  - `billing_orders.metadata`
  - `credit_ledger_entries.metadata`
- Use one metadata key everywhere:
  - `welcome_trial_dialog_acknowledged_at`

The write is idempotent. If the timestamp already exists, the backend returns
the existing value without mutating state again.

## Read/Write Contract

- Extend `BillingTrialOfferDTO` with
  `welcome_dialog_acknowledged_at: str | None`
- Keep `GET /api/billing/overview` as the only read path for the frontend
- Add `POST /api/billing/trial-offer/welcome/ack`
  - empty body
  - returns `{ acknowledged, acknowledged_at }`
  - returns `acknowledged=false` when the user has no granted trial

## Frontend Flow

- `AdminLayout` keeps rendering `WelcomeTrialDialog` globally for `/admin`
- The dialog opens only when:
  - admin menu is ready
  - `trial_offer.status === "granted"`
  - `trial_offer.welcome_dialog_acknowledged_at == null`
- The dialog uses an in-memory fingerprint per mount to avoid reopening during
  the current page lifecycle
- On explicit dismiss, the dialog closes immediately and asynchronously sends
  the ack request; no toast is shown if the request fails
