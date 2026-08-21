"""Verify billing write routes refund auth behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.service.billing import (
    billing_write_routes_test_helpers as write_route_helpers,
)
from tests.service.billing.billing_write_routes_test_helpers import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_TOPUP,
    BillingOrder,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
    StripeOrder,
    add_active_subscription,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def billing_write_client(monkeypatch) -> Iterator[dict[str, object]]:
    yield from write_route_helpers.billing_write_client(monkeypatch)


class TestBillingWriteRoutesRefundAuth:
    """Verify billing write routes refund auth behavior."""

    def test_refund_paid_stripe_order_marks_order_refunded(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-refund-stripe-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{bill_order_bid}/refund",
            json={"reason": "requested_by_creator"},
        ).get_json(force=True)

        assert refund["code"] == 0
        assert refund["data"]["status"] == "refunded"
        assert refund["data"]["refund_reference_id"] == "re_billing_test"
        assert (
            billing_write_client["refund_requests"][0]["metadata"]["payment_intent_id"]
            == "pi_billing_test"
        )

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            topup_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            ).all()
            refund_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="re_billing_test",
            ).one()
            refund_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_REFUND,
                source_bid="re_billing_test",
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_REFUNDED
            assert order.refunded_at is not None
            assert order.metadata_json["latest_event_type"] == "refund_payment"
            assert wallet.available_credits == 40
            assert len(topup_buckets) == 1
            assert refund_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert refund_bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert refund_bucket.available_credits == 40
            assert refund_bucket.metadata_json["bill_order_bid"] == bill_order_bid
            assert refund_ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND
            assert refund_ledger.amount == 20
            assert raw_order.status == 2
            assert "last_refund_id" in raw_order.metadata_json
            assert (
                StripeOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )

    def test_refund_pingxx_order_returns_unsupported(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        add_active_subscription(app, subscription_bid="sub-topup-refund-pingxx-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{bill_order_bid}/refund",
        ).get_json(force=True)

        assert refund["code"] == 0
        assert refund["data"]["status"] == "unsupported"
        assert billing_write_client["refund_requests"] == []

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            assert order.status == BILLING_ORDER_STATUS_PAID

    def test_write_routes_require_creator(self, billing_write_client) -> None:
        client = billing_write_client["client"]
        response = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
            },
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] != 0
