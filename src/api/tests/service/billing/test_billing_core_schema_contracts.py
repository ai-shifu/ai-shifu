from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
)

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_core_models_define_catalog_subscription_order_tables() -> None:
    product_table = BillingProduct.__table__
    subscription_table = BillingSubscription.__table__
    order_table = BillingOrder.__table__

    assert BillingProduct.__tablename__ == "bill_products"
    assert "product_bid" in product_table.c
    assert "product_code" in product_table.c
    assert "credit_amount" in product_table.c

    assert BillingSubscription.__tablename__ == "bill_subscriptions"
    assert "subscription_bid" in subscription_table.c
    assert "creator_bid" in subscription_table.c
    assert "provider_subscription_id" in subscription_table.c

    assert BillingOrder.__tablename__ == "bill_orders"
    assert "bill_order_bid" in order_table.c
    assert "creator_bid" in order_table.c
    assert "provider_reference_id" in order_table.c
    assert "subscription_bid" in order_table.c


def test_billing_core_migration_creates_catalog_subscription_order_tables() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert 'op.create_table(\n        "bill_products",' in source
    assert 'op.create_table(\n        "bill_subscriptions",' in source
    assert 'op.create_table(\n        "bill_orders",' in source
    assert "ix_bill_products_product_type_status" in source
    assert "ix_bill_subscriptions_creator_status" in source
    assert "ix_bill_orders_creator_status" in source
    assert "op.bulk_insert(" not in source
