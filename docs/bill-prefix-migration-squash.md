# Bill Prefix Migration Squash

## Summary

This change rewrites the branch-only billing migration chain into one schema-only
revision and renames billing database/resource identifiers that should now use
the shorter `bill_` prefix.

The `/api/billing` route namespace stays unchanged. The contract change is
limited to business identifiers and persistence identifiers such as
`bill_order_bid`, `bill_products`, and `bill-product-*`.

## Decisions

- Keep `src/api/migrations/versions/b114d7f5e2c1_add_billing_core_phase.py` as
  the only branch-only bill migration revision.
- Delete later branch-only billing revisions and fold their final schema into
  `b114d7f5e2c1`.
- Remove catalog/config/rate seed writes from Alembic.
- Add an idempotent CLI command to seed bootstrap data manually after
  migrations.
- Rename business identifiers exposed through HTTP from `bill_order_bid` to
  `bill_order_bid`.
- Rename billing table names from `billing_*` to `bill_*`, while keeping
  semantic field names like `billing_provider`, `billing_interval`, and
  `billing_metric`.

## Impacted Surfaces

- Alembic revision chain and schema-contract tests.
- SQLAlchemy models and order raw snapshot bridge columns.
- Billing DTOs, serializers, read/write routes, tasks, webhooks, and CLI.
- Frontend billing types, pages, hooks, and tests.
- Billing product/config seed values and runtime config keys.

## Verification

- Backend focused pytest for billing, order webhook, and user trial bootstrap.
- Frontend billing tests plus `npm run type-check` and `npm run lint`.
- Manual check that the remaining bill migration no longer performs seed
  `bulk_insert` calls.
