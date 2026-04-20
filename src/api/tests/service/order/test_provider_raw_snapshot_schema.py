from __future__ import annotations

from pathlib import Path

from flaskr.service.order.models import PingxxOrder, StripeOrder

_API_ROOT = Path(__file__).resolve().parents[3]


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


def test_provider_raw_migration_adds_billing_isolation_columns() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert '"biz_domain"' in source
    assert '"bill_order_bid"' in source
    assert '"creator_bid"' in source
    assert "ix_order_pingxx_orders_biz_domain_order_bid" in source
    assert "ix_order_pingxx_orders_biz_domain_bill_order_bid" in source
    assert "ix_order_stripe_orders_biz_domain_order_bid" in source
    assert "ix_order_stripe_orders_biz_domain_bill_order_bid" in source
