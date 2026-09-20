"""Keep unsuccessful Pingxx lock acquisition retryable at both callback URLs."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.route import callback
from flaskr.route.common import register_common_handler
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order, PingxxOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo

from tests.service.billing.test_billing_callbacks import billing_callback_app

__all__ = ["billing_callback_app"]


@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize(
    "lock_failure", ["missing", "busy", "factory_exception", "acquire_exception"]
)
def test_unavailable_payment_lock_returns_retry_response_without_marking_paid(
    billing_callback_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    scoped: bool,
    lock_failure: str,
) -> None:
    app = billing_callback_app
    register_common_handler(app)
    context = SimpleNamespace(
        creator_bid=uuid4().hex, integration_bid=uuid4().hex, provider="pingxx"
    )
    order = Order(
        order_bid=uuid4().hex,
        user_bid=uuid4().hex,
        creator_bid=context.creator_bid,
        payment_integration_bid=context.integration_bid,
        status=ORDER_STATUS_TO_BE_PAID,
        paid_price=10,
        payment_channel="pingxx",
    )
    snapshot = PingxxOrder(
        pingxx_order_bid=uuid4().hex,
        order_bid=order.order_bid,
        transaction_no=uuid4().hex,
        charge_id=uuid4().hex,
        amount=1000,
        status=0,
        extra="{}",
        charge_object="{}",
    )
    user = UserInfo(user_bid=order.user_bid, state=USER_STATE_REGISTERED)
    db.session.add_all([order, snapshot, user])
    db.session.commit()
    payload = {
        "type": "charge.succeeded",
        "data": {
            "object": {"order_no": snapshot.transaction_no, "id": snapshot.charge_id}
        },
    }
    provider = Mock(
        verify_webhook=Mock(
            return_value=PaymentNotificationResult(
                order_bid=snapshot.transaction_no,
                charge_id=snapshot.charge_id,
                status="charge.succeeded",
                provider_payload=payload,
            )
        )
    )
    monkeypatch.setattr(
        callback, "resolve_provider_credential_context", Mock(return_value=context)
    )
    monkeypatch.setattr(
        callback, "build_provider_config_overrides", Mock(return_value={})
    )
    monkeypatch.setattr(callback, "get_payment_provider", Mock(return_value=provider))
    lock = Mock(acquire=Mock(return_value=False))
    lock_factory = Mock(return_value=None if lock_failure == "missing" else lock)
    if lock_failure == "factory_exception":
        lock_factory.side_effect = ConnectionError("Redis unavailable")
    elif lock_failure == "acquire_exception":
        lock.acquire.side_effect = ConnectionError("Redis disconnected")
    monkeypatch.setattr(funs.cache_provider, "lock", lock_factory)
    notify = Mock()
    monkeypatch.setattr(funs, "send_order_feishu", notify)

    response = app.test_client().post(
        "/api/order/webhooks/pingxx/token"
        if scoped
        else "/api/callback/pingxx-callback",
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"code": "FAIL", "message": "processing error"}
    db.session.expire_all()
    assert order.status == ORDER_STATUS_TO_BE_PAID
    assert snapshot.status == 0
    assert snapshot.charge_object == "{}"
    assert user.state == USER_STATE_REGISTERED
    notify.assert_not_called()
    lock_factory.assert_called_once_with(
        "success_buy_record_from_pingxx" + snapshot.charge_id,
        timeout=10,
        blocking_timeout=10,
    )
    if lock_failure in {"busy", "acquire_exception"}:
        lock.acquire.assert_called_once_with(blocking=True)
    else:
        lock.acquire.assert_not_called()
    lock.release.assert_not_called()
