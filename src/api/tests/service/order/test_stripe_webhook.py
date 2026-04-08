from __future__ import annotations

from datetime import datetime
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
    BILLING_PRODUCT_SEEDS,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.funs import handle_stripe_webhook
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult

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


class DummyStripeProvider:
    def __init__(self, notification: PaymentNotificationResult):
        self._notification = notification

    def verify_webhook(self, *, headers, raw_body, app):
        del headers, raw_body, app
        return self._notification


@pytest.fixture
def stripe_webhook_app():
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
    _load_route_module("order").register_order_handler(app, "/api/order")
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(_seed_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_products() -> list[BillingProduct]:
    items: list[BillingProduct] = []
    for seed in BILLING_PRODUCT_SEEDS:
        payload = dict(seed)
        payload["metadata_json"] = payload.pop("metadata", None)
        items.append(BillingProduct(**payload))
    return items


def _ensure_order(status, order_bid):
    order = Order.query.filter(Order.order_bid == order_bid).first()
    if not order:
        order = Order(order_bid=order_bid, shifu_bid="shifu-1", user_bid="user-1")
        dao.db.session.add(order)
        dao.db.session.commit()
    order.status = status
    order.payment_channel = "stripe"
    dao.db.session.commit()
    return order


def _ensure_billing_subscription(status, subscription_bid):
    subscription = BillingSubscription.query.filter(
        BillingSubscription.subscription_bid == subscription_bid
    ).first()
    if not subscription:
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid="creator-1",
            product_bid="billing-product-plan-monthly",
            status=status,
            billing_provider="stripe",
            provider_subscription_id="",
            provider_customer_id="",
            cancel_at_period_end=0,
            next_product_bid="",
            metadata_json={},
        )
        dao.db.session.add(subscription)
        dao.db.session.commit()
    subscription.status = status
    dao.db.session.commit()
    return subscription


def _ensure_billing_order(status, billing_order_bid, subscription_bid):
    order = BillingOrder.query.filter(
        BillingOrder.billing_order_bid == billing_order_bid
    ).first()
    if not order:
        order = BillingOrder(
            billing_order_bid=billing_order_bid,
            creator_bid="creator-1",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid="billing-product-plan-monthly",
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=9900,
            paid_amount=0,
            payment_provider="stripe",
            channel="card",
            provider_reference_id="cs_billing_test",
            status=status,
            failure_code="",
            failure_message="",
            metadata_json={},
        )
        dao.db.session.add(order)
        dao.db.session.commit()
    order.status = status
    order.payment_provider = "stripe"
    order.provider_reference_id = "cs_billing_test"
    dao.db.session.commit()
    return order


def test_handle_stripe_webhook_marks_order_paid(stripe_webhook_app, monkeypatch):
    with stripe_webhook_app.app_context():
        order = _ensure_order(ORDER_STATUS_TO_BE_PAID, "order-webhook-1")

        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="",
            latest_charge_id="",
            amount=100,
            currency="usd",
            status=0,
            receipt_url="",
            payment_method="",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        dao.db.session.add(stripe_order)
        dao.db.session.commit()

    notification = PaymentNotificationResult(
        order_bid="order-webhook-1",
        status="payment_intent.succeeded",
        provider_payload={
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test",
                    "metadata": {"order_bid": "order-webhook-1"},
                    "latest_charge": "ch_test",
                    "charges": {"data": [{"id": "ch_test", "receipt_url": "url"}]},
                    "payment_method": "pm_test",
                }
            },
        },
        charge_id="ch_test",
    )

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(notification),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu",
        lambda *args, **kwargs: None,
    )

    payload, status_code = handle_stripe_webhook(stripe_webhook_app, b"{}", "sig")

    assert status_code == 200
    assert payload["status"] == "paid"
    with stripe_webhook_app.app_context():
        refreshed_order = Order.query.filter(
            Order.order_bid == "order-webhook-1"
        ).first()
        refreshed_stripe_order = StripeOrder.query.filter(
            StripeOrder.order_bid == "order-webhook-1"
        ).first()
        assert refreshed_order.status == ORDER_STATUS_SUCCESS
        assert refreshed_stripe_order.latest_charge_id == "ch_test"
        assert refreshed_stripe_order.status == 1


def test_stripe_webhook_route_marks_legacy_order_paid(stripe_webhook_app, monkeypatch):
    with stripe_webhook_app.app_context():
        order = _ensure_order(ORDER_STATUS_TO_BE_PAID, "order-webhook-route-1")

        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order-route",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_route_test",
            checkout_session_id="",
            latest_charge_id="",
            amount=100,
            currency="usd",
            status=0,
            receipt_url="",
            payment_method="",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        dao.db.session.add(stripe_order)
        dao.db.session.commit()

    notification = PaymentNotificationResult(
        order_bid="order-webhook-route-1",
        status="payment_intent.succeeded",
        provider_payload={
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_route_test",
                    "metadata": {"order_bid": "order-webhook-route-1"},
                    "latest_charge": "ch_route_test",
                    "charges": {
                        "data": [
                            {
                                "id": "ch_route_test",
                                "receipt_url": "https://stripe.test/receipt",
                            }
                        ]
                    },
                    "payment_method": "pm_route_test",
                }
            },
        },
        charge_id="ch_route_test",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(notification),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu",
        lambda *args, **kwargs: None,
    )

    with stripe_webhook_app.test_client() as client:
        response = client.post(
            "/api/order/stripe/webhook",
            data=b"{}",
            headers={"Stripe-Signature": "sig"},
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "paid"

    with stripe_webhook_app.app_context():
        refreshed_order = Order.query.filter(
            Order.order_bid == "order-webhook-route-1"
        ).one()
        refreshed_stripe_order = StripeOrder.query.filter(
            StripeOrder.order_bid == "order-webhook-route-1"
        ).one()
        assert refreshed_order.status == ORDER_STATUS_SUCCESS
        assert refreshed_stripe_order.latest_charge_id == "ch_route_test"
        assert refreshed_stripe_order.status == 1


def test_handle_stripe_webhook_routes_billing_orders_without_regression(
    stripe_webhook_app, monkeypatch
):
    with stripe_webhook_app.app_context():
        subscription = _ensure_billing_subscription(
            BILLING_SUBSCRIPTION_STATUS_DRAFT,
            "billing-subscription-1",
        )
        _ensure_billing_order(
            BILLING_ORDER_STATUS_PENDING,
            "billing-order-webhook-1",
            subscription.subscription_bid,
        )

    success_notification = PaymentNotificationResult(
        order_bid="billing-order-webhook-1",
        status="checkout.session.completed",
        provider_payload={
            "type": "checkout.session.completed",
            "created": 200,
            "data": {
                "object": {
                    "id": "cs_billing_test",
                    "subscription": "sub_provider_1",
                    "customer": "cus_provider_1",
                    "payment_status": "paid",
                    "metadata": {
                        "billing_order_bid": "billing-order-webhook-1",
                        "order_bid": "billing-order-webhook-1",
                    },
                }
            },
        },
        charge_id="",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(success_notification),
    )
    payload, status_code = handle_stripe_webhook(stripe_webhook_app, b"{}", "sig")

    assert status_code == 200
    assert payload["status"] == "paid"

    failed_notification = PaymentNotificationResult(
        order_bid="billing-order-webhook-1",
        status="payment_intent.payment_failed",
        provider_payload={
            "type": "payment_intent.payment_failed",
            "created": 100,
            "data": {
                "object": {
                    "id": "pi_billing_failed",
                    "metadata": {
                        "billing_order_bid": "billing-order-webhook-1",
                        "order_bid": "billing-order-webhook-1",
                    },
                    "last_payment_error": {
                        "code": "card_declined",
                        "message": "declined",
                    },
                }
            },
        },
        charge_id="",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(failed_notification),
    )
    payload, status_code = handle_stripe_webhook(stripe_webhook_app, b"{}", "sig")

    assert status_code == 200
    assert payload["billing_order_bid"] == "billing-order-webhook-1"

    with stripe_webhook_app.app_context():
        refreshed_order = BillingOrder.query.filter(
            BillingOrder.billing_order_bid == "billing-order-webhook-1"
        ).one()
        refreshed_subscription = BillingSubscription.query.filter(
            BillingSubscription.subscription_bid == "billing-subscription-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        buckets = CreditWalletBucket.query.filter_by(
            creator_bid="creator-1",
            source_bid="billing-order-webhook-1",
        ).all()
        ledgers = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-1",
            source_bid="billing-order-webhook-1",
        ).all()
        assert refreshed_order.status == BILLING_ORDER_STATUS_PAID
        assert refreshed_order.paid_at is not None
        assert refreshed_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert refreshed_subscription.provider_subscription_id == "sub_provider_1"
        assert refreshed_subscription.provider_customer_id == "cus_provider_1"
        assert wallet.available_credits == 300000
        assert len(buckets) == 1
        assert len(ledgers) == 1


def test_stripe_webhook_route_delegates_billing_orders(stripe_webhook_app, monkeypatch):
    with stripe_webhook_app.app_context():
        subscription = _ensure_billing_subscription(
            BILLING_SUBSCRIPTION_STATUS_DRAFT,
            "billing-subscription-route-1",
        )
        _ensure_billing_order(
            BILLING_ORDER_STATUS_PENDING,
            "billing-order-route-1",
            subscription.subscription_bid,
        )

    notification = PaymentNotificationResult(
        order_bid="billing-order-route-1",
        status="checkout.session.completed",
        provider_payload={
            "type": "checkout.session.completed",
            "created": 300,
            "data": {
                "object": {
                    "id": "cs_billing_test",
                    "subscription": "sub_provider_route_1",
                    "customer": "cus_provider_route_1",
                    "payment_status": "paid",
                    "metadata": {
                        "billing_order_bid": "billing-order-route-1",
                        "order_bid": "billing-order-route-1",
                    },
                }
            },
        },
        charge_id="",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(notification),
    )

    with stripe_webhook_app.test_client() as client:
        response = client.post(
            "/api/order/stripe/webhook",
            data=b"{}",
            headers={"Stripe-Signature": "sig"},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["billing_order_bid"] == "billing-order-route-1"
    assert payload["data"]["status"] == "paid"

    with stripe_webhook_app.app_context():
        refreshed_order = BillingOrder.query.filter(
            BillingOrder.billing_order_bid == "billing-order-route-1"
        ).one()
        refreshed_subscription = BillingSubscription.query.filter(
            BillingSubscription.subscription_bid == "billing-subscription-route-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
        ledgers = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-1",
            source_bid="billing-order-route-1",
        ).all()

        assert refreshed_order.status == BILLING_ORDER_STATUS_PAID
        assert refreshed_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        assert refreshed_subscription.provider_subscription_id == "sub_provider_route_1"
        assert wallet.available_credits == 300000
        assert len(ledgers) == 1


def test_handle_stripe_webhook_ignores_stale_subscription_updates(
    stripe_webhook_app, monkeypatch
):
    with stripe_webhook_app.app_context():
        subscription = _ensure_billing_subscription(
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            "billing-subscription-2",
        )
        subscription.provider_subscription_id = "sub_provider_2"
        subscription.provider_customer_id = "cus_provider_2"
        subscription.metadata_json = {
            "latest_event_time": datetime(2026, 4, 8, 12, 10, 0).isoformat()
        }
        dao.db.session.add(subscription)
        dao.db.session.commit()

        _ensure_billing_order(
            BILLING_ORDER_STATUS_PAID,
            "billing-order-webhook-2",
            subscription.subscription_bid,
        )

    notification = PaymentNotificationResult(
        order_bid="",
        status="customer.subscription.updated",
        provider_payload={
            "type": "customer.subscription.updated",
            "created": 100,
            "data": {
                "object": {
                    "id": "sub_provider_2",
                    "customer": "cus_provider_2",
                    "status": "past_due",
                    "cancel_at_period_end": False,
                    "metadata": {},
                }
            },
        },
        charge_id="",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda channel: DummyStripeProvider(notification),
    )

    payload, status_code = handle_stripe_webhook(stripe_webhook_app, b"{}", "sig")

    assert status_code == 200
    assert payload["subscription_bid"] == "billing-subscription-2"

    with stripe_webhook_app.app_context():
        refreshed_subscription = BillingSubscription.query.filter(
            BillingSubscription.subscription_bid == "billing-subscription-2"
        ).one()
        assert refreshed_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
