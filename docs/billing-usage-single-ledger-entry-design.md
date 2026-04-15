# Billing Usage Single Ledger Entry Design

## Context

Current usage settlement writes one `credit_ledger_entries` consume row per
`metric x wallet_bucket` combination. This preserves bucket-level audit detail,
but one LLM invocation can appear as multiple ledger rows even though it is a
single user-facing usage event.

The target behavior is:

- keep `bill_usage` as the raw usage truth source
- keep `credit_wallet_buckets` as the actual balance buckets that are mutated
- write exactly one consume ledger row per settled usage
- move bucket-level deduction detail into ledger `metadata`

This keeps wallet math unchanged while collapsing the usage ledger surface into
one row per usage event.

## Goals

- One settled usage produces one `credit_ledger_entries` consume row.
- Preserve per-metric consumed credit detail for reports.
- Preserve per-bucket deduction audit detail in ledger metadata.
- Avoid schema migrations for this change.

## Non-Goals

- No change to `bill_usage` recording.
- No change to wallet bucket selection priority.
- No change to non-usage ledger flows such as grant, refund, expire, or manual
  adjustment.

## Contract Changes

### Ledger Write Contract

For `source_type=usage` and `entry_type=consume`:

- `amount` stores the total consumed credits for the whole usage event.
- `wallet_bucket_bid` is no longer the canonical source of truth for usage
  consume rows and may be empty when multiple buckets are involved.
- `balance_after` stores the final wallet balance after the whole usage event is
  settled.
- `expires_at` and `consumable_from` are omitted on aggregated usage consume
  rows because multiple buckets may contribute distinct effective windows.

### Ledger Metadata Contract

Usage consume ledger metadata must include:

- existing usage fields: `usage_bid`, `usage_scene`, `provider`, `model`
- `metric_breakdown[]`: one item per billed metric with total consumed credits
  for that metric across all buckets
- `bucket_breakdown[]`: one item per touched wallet bucket with the credits
  consumed from that bucket during the usage settlement

Recommended `bucket_breakdown[]` shape:

- `wallet_bucket_bid`
- `consumed_credits`
- `bucket_category`
- `source_type`
- `source_bid`
- `effective_from`
- `effective_to`
- `billing_metrics`

`billing_metrics` is the list of metric labels that consumed credits from the
bucket. It supports audit/debugging without recreating one ledger row per
metric-bucket pair.

## Reporting Impact

- Daily usage metric reporting should continue to derive consumed credits from
  `metric_breakdown[]`.
- Daily ledger summary `entry_count` for usage consume rows now reflects the
  number of settled usage events, not the number of bucket-split consume rows.

## Read Model Impact

- `GET /billing/ledger` and admin ledger views should return one usage consume
  row per usage event.
- Serialization should expose `bucket_breakdown[]` as part of usage ledger
  metadata so audit detail remains available to callers.

## Test Impact

Update tests that currently assume:

- one usage can create multiple consume ledger rows
- usage consume `wallet_bucket_bid` always points at the bucket shown in the row
- usage ledger daily `entry_count` equals the number of bucket-split consume
  rows

Add focused assertions for:

- one usage creates one consume ledger row
- metadata includes multiple metric items when applicable
- metadata includes all touched buckets in `bucket_breakdown[]`
- usage daily aggregates still compute consumed credits correctly from
  `metric_breakdown[]`

## Rollout Notes

- This is a contract change for usage consume ledger rows only.
- Existing historical rows remain valid; read/report code must tolerate both the
  old split-row format and the new aggregated-row format during the transition.
