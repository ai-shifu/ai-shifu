"""Verify stripe refund behavior."""

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import db
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.funs import get_payment_details, refund_order_payment
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.stripe import StripeProvider


class DummyStripeRefundProvider:
    """Simulate Stripe refund provider behavior for tests."""

    def __init__(self, result: PaymentRefundResult) -> None:
        """Capture the result returned by refund requests."""
        self._result = result

    def refund_payment(self, *, request: object, app: object) -> object:  # pylint: disable=unused-argument
        _ = (request, app)
        return self._result


def test_stripe_refund_passes_the_stable_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _RefundResult:
        def to_dict(self) -> dict[str, str]:
            return {"id": "re_idempotent", "status": "succeeded"}

    class _Refund:
        @staticmethod
        def create(**kwargs: object) -> object:
            captured.update(kwargs)
            return _RefundResult()

    provider = StripeProvider()
    monkeypatch.setattr(
        provider,
        "_client_options",
        lambda _app: (type("Stripe", (), {"Refund": _Refund}), {}),
    )

    provider.refund_payment(
        request=PaymentRefundRequest(
            order_bid="order-idempotent-refund",
            amount=100,
            metadata={
                "payment_intent_id": "pi_idempotent",
                "idempotency_key": "order-refund:stable-key",
            },
        ),
        app=object(),
    )

    assert captured["idempotency_key"] == "order-refund:stable-key"
    assert "idempotency_key" not in captured["metadata"]


@pytest.fixture
def app() -> Iterator[Flask]:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _ensure_order(status: object, order_bid: object) -> object:
    order = Order.query.filter(Order.order_bid == order_bid).first()
    if not order:
        order = Order(order_bid=order_bid, shifu_bid="shifu-1", user_bid="user-1")
        db.session.add(order)
        db.session.commit()
    order.status = status
    order.payment_channel = "stripe"
    db.session.commit()
    return order


def test_refund_order_payment_updates_status(app: object, monkeypatch: object) -> None:
    order_bid = "order-refund-1"
    with app.app_context():
        order = _ensure_order(ORDER_STATUS_SUCCESS, order_bid)

        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="",
            latest_charge_id="ch_test",
            amount=100,
            currency="usd",
            status=1,
            receipt_url="",
            payment_method="",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        db.session.add(stripe_order)
        db.session.add(
            StripeOrder(
                order_bid=order.order_bid,
                stripe_order_bid="billing-stripe-order",
                biz_domain="billing",
                bill_order_bid="bill-order-refund-1",
                creator_bid="creator-1",
                user_bid="",
                shifu_bid="",
                payment_intent_id="pi_billing",
                checkout_session_id="cs_billing",
                latest_charge_id="ch_billing",
                amount=200,
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
        )
        db.session.commit()

        result = PaymentRefundResult(
            provider_reference="re_test",
            raw_response={"id": "re_test", "status": "succeeded"},
            status="succeeded",
        )

        provider = DummyStripeRefundProvider(result)
        monkeypatch.setattr(
            "flaskr.service.order.funs.get_payment_provider",
            lambda _channel: provider,
        )

        # refund_order_payment now joins the caller's session and commits its
        # unit of work there, which expires `order`; use the captured bid.
        payload = refund_order_payment(app, order_bid, reason="requested_by_customer")

    assert payload["status"] == "succeeded"
    with app.app_context():
        refreshed_order = Order.query.filter(Order.order_bid == order_bid).first()
        refreshed_stripe_order = (
            StripeOrder.query.filter(StripeOrder.order_bid == order_bid)
            .filter(StripeOrder.biz_domain == "order")
            .first()
        )
        billing_snapshot = StripeOrder.query.filter(
            StripeOrder.bill_order_bid == "bill-order-refund-1",
            StripeOrder.biz_domain == "billing",
        ).first()
        assert refreshed_order.status == ORDER_STATUS_REFUND
        assert refreshed_stripe_order.status == 2
        assert "last_refund_id" in refreshed_stripe_order.metadata_json
        assert billing_snapshot.status == 0


def test_refund_rolls_back_when_lifecycle_lock_is_lost_before_commit(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_calls = 0

    @contextmanager
    def _lost_lock(_order_bid: str) -> Iterator[None]:
        nonlocal lock_calls
        lock_calls += 1
        yield
        if lock_calls == 2:
            message = "payment lock lease lost"
            raise RuntimeError(message)

    order_bid = "order-refund-lost-lock"
    with app.app_context():
        order = _ensure_order(ORDER_STATUS_SUCCESS, order_bid)
        db.session.add(
            StripeOrder(
                order_bid=order.order_bid,
                stripe_order_bid="stripe-order-lost-lock",
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                payment_intent_id="pi_lost_lock",
                latest_charge_id="ch_lost_lock",
                amount=100,
                currency="usd",
                status=1,
                metadata_json="{}",
            )
        )
        db.session.commit()

    result = PaymentRefundResult(
        provider_reference="re_lost_lock",
        raw_response={"id": "re_lost_lock", "status": "succeeded"},
        status="succeeded",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _channel: DummyStripeRefundProvider(result),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.payment_lifecycle_lock",
        _lost_lock,
    )

    with pytest.raises(RuntimeError, match="payment lock lease lost"):
        refund_order_payment(app, order_bid)

    with app.app_context():
        order = Order.query.filter_by(order_bid=order_bid).one()
        stripe_order = StripeOrder.query.filter_by(order_bid=order_bid).one()
        assert order.status == ORDER_STATUS_SUCCESS
        assert stripe_order.status == 1
        operation = json.loads(stripe_order.metadata_json)["refund_operation"]
        assert operation["status"] == "pending"
        assert "last_refund_id" not in stripe_order.metadata_json

    monkeypatch.setattr(
        "flaskr.service.order.funs.payment_lifecycle_lock",
        lambda _order_bid: nullcontext(),
    )
    payload = refund_order_payment(app, order_bid)

    assert payload["refund_id"] == "re_lost_lock"
    with app.app_context():
        order = Order.query.filter_by(order_bid=order_bid).one()
        stripe_order = StripeOrder.query.filter_by(order_bid=order_bid).one()
        operation = json.loads(stripe_order.metadata_json)["refund_operation"]
        assert order.status == ORDER_STATUS_REFUND
        assert stripe_order.status == 2
        assert operation["status"] == "succeeded"
        assert operation["provider_reference"] == "re_lost_lock"


def test_get_payment_details_returns_minimal_stripe_payload(app: object) -> None:
    with app.app_context():
        order_bid = "order-details-1"
        order = _ensure_order(ORDER_STATUS_SUCCESS, order_bid)
        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="cs_test",
            latest_charge_id="ch_test",
            amount=100,
            currency="usd",
            status=1,
            receipt_url="",
            payment_method="pm_test",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        db.session.add(stripe_order)
        db.session.add(
            StripeOrder(
                order_bid=order.order_bid,
                stripe_order_bid="billing-stripe-order",
                biz_domain="billing",
                bill_order_bid="bill-order-details-1",
                creator_bid="creator-1",
                user_bid="",
                shifu_bid="",
                payment_intent_id="pi_billing",
                checkout_session_id="cs_billing",
                latest_charge_id="ch_billing",
                amount=200,
                currency="usd",
                status=0,
                receipt_url="",
                payment_method="",
                failure_code="",
                failure_message="",
                metadata_json='{"scope":"billing"}',
                payment_intent_object="{}",
                checkout_session_object="{}",
            )
        )
        db.session.commit()

    details = get_payment_details(app, order_bid, expected_user="user-1")
    assert details == {
        "payment_channel": "stripe",
        "course_id": "shifu-1",
        "order_bid": order_bid,
        "status": 1,
    }
