from __future__ import annotations

from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingOrder,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.webhooks import handle_billing_pingxx_webhook
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order, PingxxOrder
from tests.common.fixtures.billing_products import build_billing_products

_ROUTE_DIR = Path(__file__).resolve().parents[3] / "flaskr" / "route"


def _load_route_module(module_name: str):
    package_name = "flaskr.route"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(_ROUTE_DIR)]
        sys.modules[package_name] = package

    full_name = f"{package_name}.{module_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(
        full_name,
        _ROUTE_DIR / f"{module_name}.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


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
    _load_route_module("callback").register_callback_handler(app, "/api/callback")
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_billing_products())
        dao.db.session.commit()
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


def _create_billing_pingxx_raw_snapshot(
    billing_order_bid: str, charge_id: str
) -> PingxxOrder:
    return PingxxOrder(
        pingxx_order_bid=billing_order_bid,
        biz_domain="billing",
        billing_order_bid=billing_order_bid,
        creator_bid="creator-1",
        user_bid="",
        shifu_bid="",
        order_bid="",
        transaction_no=billing_order_bid,
        app_id="app_billing_test",
        channel="alipay_qr",
        amount=19900,
        currency="CNY",
        subject="Billing topup",
        body="Billing topup",
        client_ip="127.0.0.1",
        extra="{}",
        status=0,
        charge_id=charge_id,
        refund_id="",
        failure_code="",
        failure_msg="",
        charge_object="{}",
    )


def _create_legacy_pingxx_records(
    order_bid: str, charge_id: str
) -> tuple[Order, PingxxOrder]:
    order = Order(
        order_bid=order_bid,
        shifu_bid="legacy-shifu-1",
        user_bid="legacy-user-1",
        payable_price=Decimal("199.00"),
        paid_price=Decimal("199.00"),
        payment_channel="pingxx",
        status=ORDER_STATUS_TO_BE_PAID,
    )
    pingxx_order = PingxxOrder(
        pingxx_order_bid=f"pingxx-{order_bid}",
        user_bid=order.user_bid,
        shifu_bid=order.shifu_bid,
        order_bid=order.order_bid,
        transaction_no="txn-legacy-1",
        app_id="app_legacy_test",
        channel="alipay_qr",
        amount=19900,
        currency="CNY",
        subject="Legacy course",
        body="Legacy course",
        client_ip="127.0.0.1",
        extra="{}",
        status=0,
        charge_id=charge_id,
        refund_id="",
        failure_code="",
        failure_msg="",
        charge_object="{}",
    )
    return order, pingxx_order


class TestBillingPingxxCallbacks:
    def test_pingxx_callback_marks_billing_order_paid(
        self, billing_callback_app
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_pingxx_billing_order("billing-pingxx-1", "ch_billing_pingxx_1")
            )
            dao.db.session.add(
                _create_billing_pingxx_raw_snapshot(
                    "billing-pingxx-1",
                    "ch_billing_pingxx_1",
                )
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
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                billing_order_bid="billing-pingxx-1",
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-pingxx-1",
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-pingxx-1",
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.paid_at is not None
            assert raw_order.status == 1
            assert raw_order.charge_id == "ch_billing_pingxx_1"
            assert wallet.available_credits == 20
            assert bucket.available_credits == 20
            assert ledger.amount == 20

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

    def test_pingxx_callback_route_reuses_billing_and_legacy_paths(
        self, billing_callback_app, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "flaskr.service.order.funs.get_shifu_creator_bid",
            lambda *args, **kwargs: "creator-legacy-1",
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.set_user_state",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.send_order_feishu",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.query_buy_record",
            lambda *args, **kwargs: {},
        )

        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_pingxx_billing_order(
                    "billing-pingxx-route-1",
                    "ch_billing_pingxx_route_1",
                )
            )
            dao.db.session.add(
                _create_billing_pingxx_raw_snapshot(
                    "billing-pingxx-route-1",
                    "ch_billing_pingxx_route_1",
                )
            )
            legacy_order, legacy_pingxx_order = _create_legacy_pingxx_records(
                "legacy-pingxx-order-1",
                "ch_legacy_pingxx_route_1",
            )
            dao.db.session.add(legacy_order)
            dao.db.session.add(legacy_pingxx_order)
            dao.db.session.commit()

        with billing_callback_app.test_client() as client:
            billing_response = client.post(
                "/api/callback/pingxx-callback",
                json={
                    "type": "charge.succeeded",
                    "data": {
                        "object": {
                            "id": "ch_billing_pingxx_route_1",
                            "order_no": "billing-pingxx-route-1",
                            "paid": True,
                            "time_paid": 1712577600,
                        }
                    },
                },
            )
            legacy_response = client.post(
                "/api/callback/pingxx-callback",
                json={
                    "type": "charge.succeeded",
                    "data": {
                        "object": {
                            "id": "ch_legacy_pingxx_route_1",
                            "order_no": "legacy-pingxx-order-1",
                            "paid": True,
                            "time_paid": 1712577600,
                        }
                    },
                },
            )

        assert billing_response.status_code == 200
        assert billing_response.data.decode("utf-8") == "pingxx callback success"
        assert legacy_response.status_code == 200
        assert legacy_response.data.decode("utf-8") == "pingxx callback success"

        with billing_callback_app.app_context():
            billing_order = BillingOrder.query.filter_by(
                billing_order_bid="billing-pingxx-route-1"
            ).one()
            billing_raw = PingxxOrder.query.filter_by(
                biz_domain="billing",
                billing_order_bid="billing-pingxx-route-1",
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            legacy_order = Order.query.filter_by(
                order_bid="legacy-pingxx-order-1"
            ).one()
            legacy_pingxx_order = PingxxOrder.query.filter_by(
                charge_id="ch_legacy_pingxx_route_1"
            ).one()

            assert billing_order.status == BILLING_ORDER_STATUS_PAID
            assert billing_raw.status == 1
            assert wallet.available_credits == 20
            assert legacy_order.status == ORDER_STATUS_SUCCESS
            assert legacy_pingxx_order.status == 1
