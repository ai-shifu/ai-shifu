"""Repair historical paid Stripe snapshots without bypassing attempt validation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.user.consts import USER_STATE_PAID
from flaskr.service.user.models import UserInfo

if TYPE_CHECKING:
    from flask import Flask


def _historical_payment(
    snapshot_status: int,
) -> tuple[Order, StripeOrder, UserInfo, PaymentNotificationResult]:
    order = Order(
        order_bid=uuid4().hex,
        user_bid=uuid4().hex,
        shifu_bid=uuid4().hex,
        payment_channel="stripe",
        status=ORDER_STATUS_SUCCESS,
        paid_price=10,
    )
    snapshot = StripeOrder(
        stripe_order_bid=uuid4().hex,
        order_bid=order.order_bid,
        user_bid=order.user_bid,
        shifu_bid=order.shifu_bid,
        biz_domain="order",
        checkout_session_id="cs_" + uuid4().hex,
        payment_intent_id="pi_" + uuid4().hex,
        amount=1000,
        currency="usd",
        status=snapshot_status,
        checkout_session_object="{}",
        payment_intent_object="{}",
        metadata_json="{}",
    )
    user = UserInfo(user_bid=order.user_bid, state=USER_STATE_PAID)
    db.session.add_all([order, snapshot, user])
    db.session.commit()
    result = PaymentNotificationResult(
        order_bid=order.order_bid,
        status="manual_sync",
        provider_payload={
            "checkout_session": {
                "id": snapshot.checkout_session_id,
                "payment_intent": snapshot.payment_intent_id,
                "status": "open",
                "payment_status": "unpaid",
                "amount_total": 1000,
                "currency": "usd",
                "metadata": {"order_bid": order.order_bid},
            },
            "payment_intent": {
                "id": snapshot.payment_intent_id,
                "status": "succeeded",
                "amount": 1000,
                "currency": "usd",
                "metadata": {"order_bid": order.order_bid},
            },
        },
    )
    return order, snapshot, user, result


@pytest.mark.parametrize("snapshot_status", [0, 3])
@pytest.mark.parametrize(
    ("session_status", "payment_status"),
    [("open", "unpaid"), ("expired", "unpaid"), ("complete", "paid")],
)
def test_matching_paid_attempt_repairs_stale_snapshot_without_repeating_fulfillment(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_status: int,
    session_status: str,
    payment_status: str,
) -> None:
    notify = Mock()
    monkeypatch.setattr(funs, "send_order_feishu", notify)
    with app.app_context():
        order, snapshot, user, result = _historical_payment(snapshot_status)
        session = result.provider_payload["checkout_session"]
        session.update(status=session_status, payment_status=payment_status)
        provider = Mock(sync_reference=Mock(return_value=result))
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))

        for _ in range(2):
            details = funs.sync_stripe_checkout_session(
                app, order.order_bid, expected_user=user.user_bid
            )
            db.session.expire_all()
            assert details["status"] == 1
            assert order.status == ORDER_STATUS_SUCCESS
            assert snapshot.status == 1
            assert snapshot.checkout_session_id == session["id"]
            assert snapshot.payment_intent_id == session["payment_intent"]
            assert json.loads(snapshot.checkout_session_object) == session
            assert (
                json.loads(snapshot.payment_intent_object)
                == (result.provider_payload["payment_intent"])
            )
            assert user.state == USER_STATE_PAID
            notify.assert_not_called()
        assert provider.sync_reference.call_count == 2


@pytest.mark.parametrize(
    ("mismatch", "error_name"),
    [
        ("notification_order", "server.order.orderNotFound"),
        ("session_order", "server.order.orderNotFound"),
        ("intent_order", "server.order.orderNotFound"),
        ("session_id", "server.order.orderNotFound"),
        ("intent_id", "server.order.orderNotFound"),
        ("session_intent_id", "server.order.orderNotFound"),
        ("session_amount", "server.order.orderNotFound"),
        ("intent_amount", "server.order.orderNotFound"),
        ("session_currency", "server.order.orderNotFound"),
        ("intent_currency", "server.order.orderNotFound"),
        ("local_amount", "server.order.orderStatusError"),
        ("superseded_attempt", "server.order.orderNotFound"),
        ("other_user", "server.order.orderNotFound"),
        ("wrong_provider", "server.pay.payChannelNotSupport"),
        ("refunded_snapshot", "server.order.orderStatusError"),
        ("failed_snapshot", "server.order.orderStatusError"),
        ("refunded_order", "server.order.orderStatusError"),
    ],
)
def test_historical_recovery_preserves_identity_amount_currency_and_lifecycle_guards(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
    error_name: str,
) -> None:
    notify = Mock()
    monkeypatch.setattr(funs, "send_order_feishu", notify)
    with app.app_context():
        order, snapshot, user, result = _historical_payment(0)
        session = result.provider_payload["checkout_session"]
        intent = result.provider_payload["payment_intent"]
        expected_user = user.user_bid
        current_snapshot = snapshot
        if mismatch == "notification_order":
            result.order_bid = "foreign-order"
        elif mismatch == "session_order":
            session["metadata"]["order_bid"] = "foreign-order"
        elif mismatch == "intent_order":
            intent["metadata"]["order_bid"] = "foreign-order"
        elif mismatch == "session_id":
            session["id"] = "cs_foreign"
        elif mismatch == "intent_id":
            intent["id"] = "pi_foreign"
        elif mismatch == "session_intent_id":
            session["payment_intent"] = "pi_foreign"
        elif mismatch == "session_amount":
            session["amount_total"] = 900
        elif mismatch == "intent_amount":
            intent["amount"] = 900
        elif mismatch == "session_currency":
            session["currency"] = "eur"
        elif mismatch == "intent_currency":
            intent["currency"] = "eur"
        elif mismatch == "local_amount":
            order.paid_price = 11
        elif mismatch == "superseded_attempt":
            current_snapshot = StripeOrder(
                stripe_order_bid=uuid4().hex,
                order_bid=order.order_bid,
                biz_domain="order",
                checkout_session_id="cs_newer",
                payment_intent_id="pi_newer",
                amount=1000,
                currency="usd",
                status=0,
                checkout_session_object="{}",
                payment_intent_object="{}",
            )
            db.session.add(current_snapshot)
        elif mismatch == "other_user":
            expected_user = "foreign-user"
        elif mismatch == "wrong_provider":
            order.payment_channel = "pingxx"
        elif mismatch == "refunded_snapshot":
            snapshot.status = 2
        elif mismatch == "failed_snapshot":
            snapshot.status = 4
        elif mismatch == "refunded_order":
            order.status = ORDER_STATUS_REFUND
        db.session.commit()
        before = (order.status, snapshot.status, snapshot.payment_intent_id)
        provider = Mock(sync_reference=Mock(return_value=result))
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))

        with pytest.raises(AppError) as error:
            funs.sync_stripe_checkout_session(
                app, order.order_bid, expected_user=expected_user
            )

        assert error.value.code == ERROR_CODE[error_name]
        db.session.expire_all()
        assert (order.status, snapshot.status, snapshot.payment_intent_id) == before
        assert snapshot.checkout_session_object == "{}"
        assert snapshot.payment_intent_object == "{}"
        assert current_snapshot.checkout_session_object == "{}"
        assert current_snapshot.payment_intent_object == "{}"
        assert user.state == USER_STATE_PAID
        notify.assert_not_called()
        if mismatch in {"other_user", "wrong_provider"}:
            provider.sync_reference.assert_not_called()
        else:
            provider.sync_reference.assert_called_once_with(
                provider_reference=current_snapshot.checkout_session_id,
                reference_type="checkout_session",
                app=app,
            )
