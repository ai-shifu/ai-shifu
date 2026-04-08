"""harden billing schema and seed rates

Revision ID: 9c1d2e3f4a5b
Revises: 8f1d2c3b4a5e
Create Date: 2026-04-08 01:10:00.000000

"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "9c1d2e3f4a5b"
down_revision = "8f1d2c3b4a5e"
branch_labels = None
depends_on = None


def _build_usage_rate_seeds() -> tuple[dict[str, object], ...]:
    seeds: list[dict[str, object]] = []
    effective_from = datetime(2026, 1, 1, 0, 0, 0)
    scene_specs = (
        ("debug", 1201),
        ("preview", 1202),
        ("production", 1203),
    )
    llm_metrics = (
        ("input", 7451),
        ("cache", 7452),
        ("output", 7453),
    )
    for scene_name, usage_scene in scene_specs:
        for metric_name, billing_metric in llm_metrics:
            seeds.append(
                {
                    "rate_bid": f"credit-rate-llm-{scene_name}-{metric_name}-default",
                    "usage_type": 1101,
                    "provider": "*",
                    "model": "*",
                    "usage_scene": usage_scene,
                    "billing_metric": billing_metric,
                    "unit_size": 1000,
                    "credits_per_unit": Decimal("0.0000000000"),
                    "rounding_mode": 7421,
                    "effective_from": effective_from,
                    "effective_to": None,
                    "status": 7151,
                    "deleted": 0,
                }
            )
        seeds.append(
            {
                "rate_bid": f"credit-rate-tts-{scene_name}-request-default",
                "usage_type": 1102,
                "provider": "*",
                "model": "*",
                "usage_scene": usage_scene,
                "billing_metric": 7454,
                "unit_size": 1,
                "credits_per_unit": Decimal("0.0000000000"),
                "rounding_mode": 7421,
                "effective_from": effective_from,
                "effective_to": None,
                "status": 7151,
                "deleted": 0,
            }
        )
    return tuple(seeds)


_USAGE_RATE_SEEDS = _build_usage_rate_seeds()


def upgrade():
    with op.batch_alter_table("billing_products", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_products_product_bid",
            ["product_bid"],
        )

    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_subscriptions_subscription_bid",
            ["subscription_bid"],
        )

    with op.batch_alter_table("billing_orders", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_orders_billing_order_bid",
            ["billing_order_bid"],
        )

    with op.batch_alter_table("credit_wallets", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_wallets_wallet_bid",
            ["wallet_bid"],
        )

    with op.batch_alter_table("credit_wallet_buckets", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_wallet_buckets_wallet_bucket_bid",
            ["wallet_bucket_bid"],
        )

    with op.batch_alter_table("credit_ledger_entries", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_ledger_entries_ledger_bid",
            ["ledger_bid"],
        )

    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_credit_usage_rates_rate_bid",
            ["rate_bid"],
        )
        batch_op.create_unique_constraint(
            "uq_credit_usage_rates_lookup",
            [
                "usage_type",
                "provider",
                "model",
                "usage_scene",
                "billing_metric",
                "effective_from",
            ],
        )

    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_billing_renewal_events_renewal_event_bid",
            ["renewal_event_bid"],
        )
        batch_op.create_unique_constraint(
            "uq_billing_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
        )

    rate_table = sa.table(
        "credit_usage_rates",
        sa.column("rate_bid", sa.String(length=36)),
        sa.column("usage_type", sa.SmallInteger()),
        sa.column("provider", sa.String(length=32)),
        sa.column("model", sa.String(length=100)),
        sa.column("usage_scene", sa.SmallInteger()),
        sa.column("billing_metric", sa.SmallInteger()),
        sa.column("unit_size", sa.Integer()),
        sa.column("credits_per_unit", sa.Numeric(precision=20, scale=10)),
        sa.column("rounding_mode", sa.SmallInteger()),
        sa.column("effective_from", sa.DateTime()),
        sa.column("effective_to", sa.DateTime()),
        sa.column("status", sa.SmallInteger()),
        sa.column("deleted", sa.SmallInteger()),
    )
    op.bulk_insert(rate_table, list(_USAGE_RATE_SEEDS))


def downgrade():
    rate_table = sa.table(
        "credit_usage_rates",
        sa.column("rate_bid", sa.String(length=36)),
    )
    op.execute(
        rate_table.delete().where(
            rate_table.c.rate_bid.in_([row["rate_bid"] for row in _USAGE_RATE_SEEDS])
        )
    )

    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_billing_renewal_events_subscription_event_scheduled",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_billing_renewal_events_renewal_event_bid",
            type_="unique",
        )

    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_usage_rates_lookup", type_="unique")
        batch_op.drop_constraint("uq_credit_usage_rates_rate_bid", type_="unique")

    with op.batch_alter_table("credit_ledger_entries", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_ledger_entries_ledger_bid", type_="unique")

    with op.batch_alter_table("credit_wallet_buckets", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_credit_wallet_buckets_wallet_bucket_bid",
            type_="unique",
        )

    with op.batch_alter_table("credit_wallets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_credit_wallets_wallet_bid", type_="unique")

    with op.batch_alter_table("billing_orders", schema=None) as batch_op:
        batch_op.drop_constraint("uq_billing_orders_billing_order_bid", type_="unique")

    with op.batch_alter_table("billing_subscriptions", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_billing_subscriptions_subscription_bid",
            type_="unique",
        )

    with op.batch_alter_table("billing_products", schema=None) as batch_op:
        batch_op.drop_constraint("uq_billing_products_product_bid", type_="unique")
