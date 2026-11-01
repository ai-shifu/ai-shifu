"""Protect billing core schema compatibility."""

from __future__ import annotations

from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
    BillingProductProviderPrice,
    BillingSubscription,
)


def test_billing_core_models_define_catalog_subscription_order_tables() -> None:
    product_table = BillingProduct.__table__
    subscription_table = BillingSubscription.__table__
    order_table = BillingOrder.__table__
    campaign_table = BillingCampaign.__table__
    campaign_product_table = BillingCampaignProduct.__table__
    provider_price_table = BillingProductProviderPrice.__table__

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
    assert BillingProductProviderPrice.__tablename__ == "bill_product_provider_prices"
    assert "provider_price_bid" in provider_price_table.c
    assert "provider_product_id" in provider_price_table.c
    assert "provider_price_id" in provider_price_table.c
    assert "provider_price_live_scope" in provider_price_table.c
    assert "active_scope" in provider_price_table.c
    assert "creator_bid" in order_table.c
    assert "provider_reference_id" in order_table.c
    assert "subscription_bid" in order_table.c
