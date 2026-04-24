# Operator User Points Grant

## Context

Operator user management already exposes creator credits summary on the user list
and the user detail page. The next step is to let operators issue credits for
internal use, rewards, and compensation without routing that action through the
commercial order flow.

This capability must stay consistent with the current user-facing credit model:

- the user surface still shows only `subscription credits` and `top-up credits`
- operator-issued credits are displayed as part of `subscription credits`
- top-up credits remain purchase-like credits with stricter consumption rules

## Confirmed Product Scope

### Entry

- location: `Admin -> Operations -> Users`
- add a sticky `action` column at the end of the list
- action menu reuses the same dropdown interaction as course transfer creator
- first action in v1: `grant credits`
- keep the existing credits balance cell clickable so operators can still jump to
  the user detail credits section for ledger review

### Grant Dialog

The dialog shows:

- user account summary (phone/email, nickname, user BID)
- current total credits
- current displayed credits expiry

The form contains:

- `type`: read-only, always `manual grant`
- `source`: `reward` or `compensation`
- `amount`: positive decimal credits
- `validity preset`:
  - `align_subscription`: same as the current active subscription expiry
  - `1d`: one day after grant time
  - `7d`: seven days after grant time
  - `1m`: one month after grant time
  - `3m`: three months after grant time
  - `1y`: one year after grant time
- `note`: optional free text

The dialog keeps a confirmation step before submit.

### Dialog interaction

- open from the row `More` dropdown
- show current credits summary in a lightweight top card so the operator can
  judge whether a grant is still needed
- the submit step shows a confirmation summary before the final request
- after success:
  - close the dialog
  - refresh the current user list page
  - keep table filters and pagination unchanged
  - make the updated credits balance visible immediately

## Product Rules

### Credit families shown to users

The user-facing grouping stays unchanged:

- `subscription credits`
- `top-up credits`

Manual grants do **not** create a third displayed family. They are grouped into
`subscription credits` for display.

### Consumption rules

- subscription purchase / renewal credits keep the current subscription-driven
  behavior
- top-up credits:
  - remain long-lived purchase credits
  - require an active subscription to be consumable
- manual grants:
  - do not require an active subscription
  - only depend on their own effective window
  - are still displayed inside the `subscription credits` family

### Balance and settlement behavior

- operator summary `available_credits` must reflect only credits that can be
  consumed right now
- settlement bucket loading must follow the same rule as admission, otherwise
  the list summary and the actual deduction path will diverge
- the wallet total can still include non-consumable buckets internally, but the
  operator surface must not overstate the user's usable balance
- manual grants should stay ahead of top-up display concerns and must not be
  blocked simply because the user has no active subscription

### Validity display rule

For the displayed `subscription credits` expiry:

- if the creator currently has an active subscription, show the subscription
  expiry first
- otherwise, if manual-grant subscription credits remain, show the earliest
  remaining manual-grant expiry
- do not expose a separate reward/compensation expiry card on the user surface

### Preset semantics

- `align_subscription` uses the current active subscription `current_period_end_at`
- `1d`, `7d`, `1m`, `3m`, `1y` are relative to grant time
- if no active subscription exists, `align_subscription` is invalid
- v1 does not support an absolute calendar date picker
- v1 does not support permanent validity

## API Proposal

Add a dedicated operator API instead of reusing the billing admin adjust route:

- `POST /shifu/admin/operations/users/{user_bid}/credits/grant`

Request payload:

```json
{
  "amount": "100",
  "grant_source": "reward",
  "validity_preset": "1m",
  "note": "campaign reward"
}
```

Response payload should at least include:

- granted amount / source / preset
- resolved `expires_at`
- refreshed summary for the target user
- created ledger identifier

Recommended error cases:

- invalid amount
- invalid source
- invalid preset
- `align_subscription` requested without an active subscription
- target user not found or is not eligible for the operator flow
- permission failure for non-operator callers

## Backend Plan

### Write path

Create a dedicated operator grant helper instead of exposing the generic billing
adjustment API.

The helper will:

- validate operator user + target user
- validate amount / source / preset
- resolve expiry from the selected preset
- create a new credit bucket under the subscription display family
- create a matching ledger row
- attach metadata:
  - `grant_type = manual_grant`
  - `grant_source = reward | compensation`
  - `validity_preset`
  - `operator_user_bid`
  - `note`
  - `grant_channel = operator_user_management`

Implementation note:

- prefer a dedicated operator grant helper over overloading
  `adjust_credit_wallet_balance(...)` with operator-only semantics
- reuse existing wallet / ledger persistence primitives where possible so the
  write path stays consistent with current billing storage rules

### Read path updates

The existing operator user credit summary stays with these fields:

- `available_credits`
- `subscription_credits`
- `topup_credits`
- `credits_expire_at`

But the aggregation rules change:

- `subscription_credits` includes normal subscription credits plus manual grants
- `topup_credits` includes top-up credits only
- `available_credits` counts only currently consumable credits
- top-up credits are excluded from `available_credits` when no active
  subscription exists
- manual grants remain included in `available_credits` when they are still
  within their own validity window, even without an active subscription
- `credits_expire_at` follows the display rule instead of a naive earliest
  bucket-expiry rule

### Ledger display mapping

Operator credits detail keeps a precise business mapping:

- display entry type: `manual_grant`
- display source type: `reward` / `compensation`
- note column still shows explicit manual note only
- source document number is not shown in the operator detail list

## Frontend Plan

### User list

- add the sticky action column
- open a dedicated `UserCreditGrantDialog`
- refresh the user list after a successful grant
- keep the credits balance column link behavior for detail drill-down
- reuse the current table action visual style so the new entry feels native to
  the operations module

### Dialog fields

- summary card:
  - account identifier
  - nickname
  - user BID
  - available credits
  - current displayed credits expiry
- form area:
  - type
  - source
  - amount
  - validity preset
  - note
- confirmation area:
  - source
  - amount
  - resolved expiry text
  - note preview when present

### Validation

- source is required
- amount must be positive
- validity preset is required
- `align_subscription` is disabled or rejected when no active subscription exists
- note stays optional and is reserved for manual operator context, not for
  system-generated consumption remarks

### Types / i18n

Add request/response types and the following translation groups:

- list action copy
- grant dialog labels / preset labels / validation messages
- credits ledger labels for `manual_grant`, `reward`, `compensation`

## Verification Plan

### Backend

- grant success with `reward + 1d`
- grant success with `compensation + 1m`
- `align_subscription` success with active subscription
- `align_subscription` failure without active subscription
- manual grant counts into `subscription_credits`
- manual grant remains consumable without active subscription
- top-up credits stay non-consumable without active subscription
- expiry summary follows the product display rule

### Frontend

- action column renders on the user list
- dialog opens from the row action menu
- validation blocks invalid submit
- disabled `align_subscription` behavior is correct
- successful submit closes dialog and refreshes list data

## Delivery Checklist

### Backend

- add grant request / response DTOs in the shifu admin contract
- expose `POST /shifu/admin/operations/users/{user_bid}/credits/grant`
- implement manual-grant bucket creation and ledger creation
- align summary aggregation with the new consumable-balance rule
- align admission and settlement bucket selection with the same rule
- extend ledger display mapping for manual grant reward / compensation

### Frontend

- extend operations user list row actions
- add `UserCreditGrantDialog`
- add API route mapping and request types
- add i18n copy for dialog, validation, and ledger labels
- keep the existing credits-detail drill-down usable

### Acceptance

- operators can issue `reward` credits with `1d`
- operators can issue `compensation` credits with `1m`
- `align_subscription` uses the current subscription expiry and rejects users
  without an active subscription
- users without an active subscription can still consume valid manual grants
- users without an active subscription cannot consume top-up credits
- the user-facing surface still shows only `subscription credits` and
  `top-up credits`

## Open Guardrails

- do not add a third visible user-side credit family
- do not route manual grants through commercial orders
- keep `docs/需求和优化.md` local-only and out of git
