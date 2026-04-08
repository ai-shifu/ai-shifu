from __future__ import annotations

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.funcs import handle_billing_pingxx_webhook
from flaskr.service.billing.models import BillingOrder


@pytest.fixture
def billing_callback_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_pingxx_billing_order(
    billing_order_bid: str, charge_id: str
) -> BillingOrder:
    return BillingOrder(
        billing_order_bid=billing_order_bid,
        creator_bid="creator-1",
        order_type=BILLING_ORDER_TYPE_TOPUP,
        product_bid="billing-product-topup-small",
        subscription_bid="",
        currency="CNY",
        payable_amount=19900,
        paid_amount=0,
        payment_provider="pingxx",
        channel="alipay_qr",
        provider_reference_id=charge_id,
        status=BILLING_ORDER_STATUS_PENDING,
        failure_code="",
        failure_message="",
        metadata_json={},
    )


class TestBillingPingxxCallbacks:
    def test_pingxx_callback_marks_billing_order_paid(
        self, billing_callback_app
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_pingxx_billing_order("billing-pingxx-1", "ch_billing_pingxx_1")
            )
            dao.db.session.commit()

            body = {
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "id": "ch_billing_pingxx_1",
                        "order_no": "billing-pingxx-1",
                        "paid": True,
                        "time_paid": 1712577600,
                    }
                },
            }
            payload, status_code = handle_billing_pingxx_webhook(
                billing_callback_app, body
            )

            assert status_code == 200
            assert payload["matched"] is True
            assert payload["status"] == "paid"

            duplicate_payload, duplicate_status = handle_billing_pingxx_webhook(
                billing_callback_app, body
            )
            assert duplicate_status == 200
            assert duplicate_payload["matched"] is True

            order = BillingOrder.query.filter_by(
                billing_order_bid="billing-pingxx-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.paid_at is not None

    def test_pingxx_callback_reports_non_billing_payload(
        self, billing_callback_app
    ) -> None:
        body = {
            "type": "charge.succeeded",
            "data": {
                "object": {
                    "id": "ch_legacy_pingxx_1",
                    "order_no": "legacy-order-1",
                    "paid": True,
                }
            },
        }
        payload, status_code = handle_billing_pingxx_webhook(billing_callback_app, body)

        assert status_code == 202
        assert payload["matched"] is False
        assert payload["status"] == "not_billing"
