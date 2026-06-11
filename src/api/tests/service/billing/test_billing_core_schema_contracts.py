from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
    BillingSubscription,
)

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_core_models_define_catalog_subscription_order_tables() -> None:
    product_table = BillingProduct.__table__
    subscription_table = BillingSubscription.__table__
    order_table = BillingOrder.__table__
    campaign_table = BillingCampaign.__table__
    campaign_product_table = BillingCampaignProduct.__table__

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
    assert "campaign_bid" in order_table.c
    assert "expires_at" in order_table.c

    assert BillingCampaign.__tablename__ == "bill_campaigns"
    assert "campaign_bid" in campaign_table.c
    assert "benefit_type" in campaign_table.c

    assert BillingCampaignProduct.__tablename__ == "bill_campaign_products"
    assert "campaign_bid" in campaign_product_table.c
    assert "product_bid" in campaign_product_table.c
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

    expires_source = (
        _API_ROOT / "migrations/versions/c5d8e1f2a3b4_add_billing_order_expires_at.py"
    ).read_text(encoding="utf-8")
    assert '"expires_at"' in expires_source
    assert "ix_bill_orders_expires_at" in expires_source


def test_billing_campaign_migrations_define_campaign_tables_and_rule_columns() -> None:
    campaign_source = (
        _API_ROOT / "migrations/versions/1d8c4e7f9a2b_add_billing_campaign_tables.py"
    ).read_text(encoding="utf-8")
    product_rule_source = (
        _API_ROOT
        / "migrations/versions/4f2b7d8e9c1a_add_billing_campaign_product_rule_columns.py"
    ).read_text(encoding="utf-8")

    assert 'op.create_table(\n        "bill_campaigns",' in campaign_source
    assert 'op.create_table(\n        "bill_campaign_products",' in campaign_source
    assert "ix_bill_campaigns_enabled_start_end" in campaign_source
    assert "uq_bill_campaign_products_campaign_product" in campaign_source
    assert 'batch_op.f("ix_bill_orders_campaign_bid")' in campaign_source
    assert '"campaign_benefit_type"' in campaign_source
    assert '"campaign_discount_amount"' in campaign_source
    assert '"campaign_bonus_credit_amount"' in campaign_source

    assert '"discount_type"' in product_rule_source
    assert '"discount_amount"' in product_rule_source
    assert '"discount_percent"' in product_rule_source
    assert '"campaign_price_amount"' in product_rule_source
    assert '"bonus_credit_amount"' in product_rule_source
