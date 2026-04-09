# New Creator Trial Credits

## Summary

This feature grants a one-time free credit trial to newly registered creators
when they first enter the creator billing workspace.

The implementation keeps trial state inside existing billing tables instead of
adding a dedicated trial table:

- credit grant is stored as a `free` wallet bucket
- the matching ledger entry uses `source_type=gift`
- idempotency is enforced by the existing
  `(creator_bid, idempotency_key)` unique constraint on
  `credit_ledger_entries`

## Registration Anchor

The feature does not modify `user_users`.

“Registration time” is defined as the earliest `created_at` among the
creator's verified auth credentials in `user_auth_credentials`.

This means:

- users without any verified credential are not eligible
- users who registered long ago and only became creators later are not
  eligible
- multi-provider users are evaluated by their earliest verified credential

## Trial Policy

Trial policy is controlled by the billing sys config
`BILLING_NEW_CREATOR_TRIAL_CONFIG`.

The normalized config fields are:

- `enabled`
- `program_code`
- `credit_amount`
- `valid_days`
- `eligible_registered_after`
- `grant_trigger`

Default seed values are:

- `enabled = 0`
- `program_code = "new_creator_v1"`
- `credit_amount = "100.0000000000"`
- `valid_days = 15`
- `eligible_registered_after = ""`
- `grant_trigger = "billing_overview"`

If `enabled = 1` but `eligible_registered_after` is empty or invalid, automatic
grant stays disabled and the backend logs a warning. This prevents accidental
backfill to older creators during rollout.

## Grant Flow

The only automatic trigger in v1 is `/api/billing/overview`.

On every overview request the backend:

1. loads the normalized trial config
2. resolves the creator's earliest verified credential timestamp
3. checks whether a trial ledger already exists for the configured
   `program_code`
4. grants the trial only when all eligibility checks pass
5. returns both the updated wallet snapshot and a `trial_offer` payload in the
   overview response

Grant details:

- bucket category: `free`
- source type: `gift`
- effective from: request time
- effective to: `effective_from + valid_days`
- idempotency key: `trial:{program_code}:{creator_bid}`

## API Shape

`/api/billing/overview` adds a `trial_offer` object:

- `enabled`
- `status`
- `credit_amount`
- `valid_days`
- `starts_on_first_grant`
- `granted_at`
- `expires_at`

`status` is one of:

- `disabled`
- `ineligible`
- `eligible`
- `granted`

The frontend uses this object instead of hardcoded free-trial assumptions.
