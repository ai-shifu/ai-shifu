"""Verify provider raw snapshot schema behavior."""

from __future__ import annotations

from flaskr.service.order.models import PingxxOrder, StripeOrder


def test_provider_raw_models_define_billing_isolation_columns() -> None:
    pingxx_table = PingxxOrder.__table__
    stripe_table = StripeOrder.__table__

    assert "biz_domain" in pingxx_table.c
    assert "bill_order_bid" in pingxx_table.c
    assert "creator_bid" in pingxx_table.c

    assert "biz_domain" in stripe_table.c
    assert "bill_order_bid" in stripe_table.c
    assert "creator_bid" in stripe_table.c

    pingxx_indexes = {index.name for index in pingxx_table.indexes}
    stripe_indexes = {index.name for index in stripe_table.indexes}
    assert "ix_order_pingxx_orders_biz_domain_order_bid" in pingxx_indexes
    assert "ix_order_pingxx_orders_biz_domain_bill_order_bid" in pingxx_indexes
    assert "ix_order_stripe_orders_biz_domain_order_bid" in stripe_indexes
    assert "ix_order_stripe_orders_biz_domain_bill_order_bid" in stripe_indexes
