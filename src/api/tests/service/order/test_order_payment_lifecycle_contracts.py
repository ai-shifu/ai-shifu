"""Verify payment resumption, callbacks, refunds, and transaction boundaries."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import (
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import (
    AlipayOrder,
    Order,
    PingxxOrder,
    StripeOrder,
    WechatPayOrder,
)
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
)

if TYPE_CHECKING:
    from flask import Flask


def _order(provider: str = "stripe", **changes: object) -> Order:
    order = Order(
        **(
            {
                "order_bid": uuid4().hex,
                "user_bid": uuid4().hex,
                "shifu_bid": uuid4().hex,
                "payment_channel": provider,
                "status": ORDER_STATUS_TO_BE_PAID,
                "paid_price": Decimal("10.00"),
            }
            | changes
        )
    )
    db.session.add(order)
    db.session.commit()
    return order


def _snapshot(
    order: Order, **changes: object
) -> StripeOrder | AlipayOrder | WechatPayOrder:
    provider = order.payment_channel
    common = {
        "order_bid": order.order_bid,
        "biz_domain": "order",
        "amount": 1000,
        "status": 0,
        "metadata_json": "{}",
    }
    if provider == "stripe":
        snapshot = StripeOrder(
            **(
                common
                | {
                    "stripe_order_bid": uuid4().hex,
                    "checkout_session_id": "cs-test",
                    "payment_intent_id": "pi-test",
                    "latest_charge_id": "ch-test",
                    "checkout_session_object": "{}",
                    "payment_intent_object": "{}",
                }
                | changes
            )
        )
    else:
        model = AlipayOrder if provider == "alipay" else WechatPayOrder
        snapshot = model(
            **(
                common
                | {
                    f"{provider}_order_bid": uuid4().hex,
                    "provider_attempt_id": uuid4().hex,
                    "transaction_id": uuid4().hex,
                    "channel": "alipay_qr" if provider == "alipay" else "wx_pub_qr",
                }
                | changes
            )
        )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


@pytest.fixture
def payment_side_effects(monkeypatch: pytest.MonkeyPatch) -> Mock:
    notify = Mock()
    monkeypatch.setattr(funs, "send_order_feishu", notify)
    monkeypatch.setattr(funs, "set_user_state", Mock())
    monkeypatch.setattr(funs, "get_shifu_creator_bid", Mock(return_value=""))
    return notify


@pytest.mark.parametrize("missing_lock", [True, False])
def test_pingxx_callback_without_lock_preserves_pending_payment(
    missing_lock: bool,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    payment_side_effects: Mock,
) -> None:
    lock = Mock(acquire=Mock(return_value=False))
    monkeypatch.setattr(
        funs.cache_provider,
        "lock",
        Mock(return_value=None if missing_lock else lock),
    )
    with app.app_context():
        order = _order("pingxx")
        snapshot = PingxxOrder(
            pingxx_order_bid=uuid4().hex,
            order_bid=order.order_bid,
            charge_id=uuid4().hex,
            amount=1000,
            status=0,
            extra="{}",
            charge_object="{}",
        )
        db.session.add(snapshot)
        db.session.commit()

        with pytest.raises(AppError) as caught:
            funs.success_buy_record_from_pingxx(app, snapshot.charge_id, {"paid": True})
        assert caught.value.code == 3003

        db.session.expire_all()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == 0
        assert snapshot.charge_object == "{}"
        payment_side_effects.assert_not_called()
        funs.set_user_state.assert_not_called()
        lock.release.assert_not_called()


@pytest.mark.parametrize("provider_name", ["alipay", "wechatpay"])
@pytest.mark.parametrize(
    "gate",
    [
        "transaction-id",
        "missing-id",
        "missing-order",
        "missing-lock",
        "busy-lock",
        "wrong-amount",
        "success",
    ],
)
def test_native_webhook_requires_usable_identifiers_lock_and_matching_amount(
    provider_name: str,
    gate: str,
    app: Flask,
    payment_side_effects: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = Mock(acquire=Mock(return_value=gate != "busy-lock"))
    monkeypatch.setattr(
        funs.cache_provider,
        "lock",
        Mock(return_value=None if gate == "missing-lock" else lock),
    )
    with app.app_context():
        order = _order(provider_name)
        snapshot = _snapshot(order, metadata_json="[]")
        if gate == "missing-order":
            order.deleted = 1
            db.session.commit()
        payload = (
            {
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "11.00" if gate == "wrong-amount" else "10.00",
            }
            if provider_name == "alipay"
            else {
                "trade_state": "SUCCESS",
                "amount": {"total": 1100 if gate == "wrong-amount" else 1000},
            }
        )
        notification = PaymentNotificationResult(
            ""
            if gate in {"transaction-id", "missing-id"}
            else snapshot.provider_attempt_id,
            "success",
            payload,
            None if gate == "missing-id" else snapshot.transaction_id,
        )
        if gate == "wrong-amount":
            with pytest.raises(RuntimeError, match="amount mismatch"):
                funs.success_buy_record_from_native(app, provider_name, notification)
            result = False
        elif gate in {"missing-lock", "busy-lock"}:
            with pytest.raises(AppError) as caught:
                funs.success_buy_record_from_native(app, provider_name, notification)
            assert caught.value.code == 3003
            result = False
        else:
            result = funs.success_buy_record_from_native(
                app, provider_name, notification
            )
        assert result is (gate in {"success", "transaction-id"})
        db.session.expire_all()
        assert order.status == (
            ORDER_STATUS_SUCCESS if result else ORDER_STATUS_TO_BE_PAID
        )
        assert snapshot.status == int(result)
        assert payment_side_effects.call_count == int(result)
        if result:
            assert json.loads(snapshot.raw_notification) == payload
            assert json.loads(snapshot.metadata_json)["latest_source"] == "webhook"
            assert (
                funs.success_buy_record_from_native(app, provider_name, notification)
                is True
            )
            assert payment_side_effects.call_count == 1
        if gate not in {"missing-id", "missing-lock", "busy-lock"}:
            assert lock.release.called
