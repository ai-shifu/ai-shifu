"""Verify legacy Stripe synchronization persists evidence and authorizes access."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order, StripeOrder

if TYPE_CHECKING:
    from flask import Flask


def _seed_stripe_order() -> tuple[Order, StripeOrder]:
    order = Order(
        order_bid=uuid4().hex,
        user_bid=uuid4().hex,
        shifu_bid=uuid4().hex,
        payment_channel="stripe",
        status=ORDER_STATUS_TO_BE_PAID,
    )
    snapshot = StripeOrder(
        stripe_order_bid=uuid4().hex,
        order_bid=order.order_bid,
        biz_domain="order",
        checkout_session_id="cs-stored",
        checkout_session_object="{}",
        payment_intent_object="{}",
        metadata_json="{}",
    )
    db.session.add_all([order, snapshot])
    db.session.commit()
    return order, snapshot


@pytest.fixture
def sync_side_effects(monkeypatch: pytest.MonkeyPatch) -> Mock:
    notify = Mock()
    monkeypatch.setattr(funs, "send_order_feishu", notify)
    monkeypatch.setattr(funs, "set_user_state", Mock())
    monkeypatch.setattr(
        funs, "get_shifu_creator_bid", Mock(return_value="creator-test")
    )
    return notify


@pytest.mark.parametrize(
    ("session_status", "payment_status", "intent_status", "paid", "snapshot_status"),
    [
        ("complete", "unpaid", "processing", False, 0),
        ("open", "paid", "succeeded", True, 1),
        ("open", "unpaid", "succeeded", True, 1),
        ("expired", "unpaid", "canceled", False, 3),
        ("open", "unpaid", "processing", False, 0),
    ],
)
def test_sync_updates_provider_snapshot_and_pays_order_only_for_success(
    session_status: str,
    payment_status: str,
    intent_status: str,
    paid: bool,
    snapshot_status: int,
    app: Flask,
    sync_side_effects: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = {
        "id": "cs-stored",
        "status": session_status,
        "payment_status": payment_status,
    }
    intent = {
        "id": "pi-resolved",
        "status": intent_status,
        "latest_charge": "ch-resolved",
        "charges": {"data": [{"receipt_url": "https://receipts.example.test/receipt"}]},
    }
    provider = Mock(
        sync_reference=Mock(
            return_value=SimpleNamespace(
                provider_payload={"checkout_session": session, "payment_intent": intent}
            )
        )
    )
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, snapshot = _seed_stripe_order()
        session["metadata"] = {"order_bid": order.order_bid}
        intent["metadata"] = {"order_bid": order.order_bid}
        provider.sync_reference.return_value.order_bid = order.order_bid
        result = funs.sync_stripe_checkout_session(
            app, order.order_bid, expected_user=order.user_bid
        )
        db.session.expire_all()
        assert order.status == (
            ORDER_STATUS_SUCCESS if paid else ORDER_STATUS_TO_BE_PAID
        )
        assert snapshot.status == snapshot_status
        assert snapshot.checkout_session_id == "cs-stored"
        assert json.loads(snapshot.checkout_session_object) == session
        assert snapshot.payment_intent_id == "pi-resolved"
        assert snapshot.latest_charge_id == "ch-resolved"
        assert snapshot.receipt_url == "https://receipts.example.test/receipt"
        assert json.loads(snapshot.payment_intent_object) == intent
        assert result == {
            "payment_channel": "stripe",
            "course_id": order.shifu_bid,
            "order_bid": order.order_bid,
            "status": snapshot_status,
        }
        provider.sync_reference.assert_called_once_with(
            provider_reference="cs-stored", reference_type="checkout_session", app=app
        )
        assert sync_side_effects.call_count == int(paid)
        if paid:
            funs.sync_stripe_checkout_session(
                app, order.order_bid, expected_user=order.user_bid
            )
            assert sync_side_effects.call_count == 1


@pytest.mark.parametrize(
    "session_id", ["{CHECKOUT_SESSION_ID}", " {session_id} ", "cs-stored", None]
)
def test_sync_resolves_callback_placeholders_against_stored_session(
    session_id: str | None, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(
        sync_reference=Mock(return_value=SimpleNamespace(provider_payload={}))
    )
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order, snapshot = _seed_stripe_order()
        snapshot.payment_intent_id = "pi-preserved"
        snapshot.latest_charge_id = "ch-preserved"
        db.session.commit()
        provider.sync_reference.return_value.order_bid = order.order_bid
        provider.sync_reference.return_value.provider_payload = {
            "checkout_session": {
                "id": "cs-stored",
                "metadata": {"order_bid": order.order_bid},
            },
            "payment_intent": {
                "id": "pi-preserved",
                "metadata": {"order_bid": order.order_bid},
            },
        }
        funs.sync_stripe_checkout_session(
            app, order.order_bid, session_id=session_id, expected_user=order.user_bid
        )
        expected = "cs-stored"
        assert (
            provider.sync_reference.call_args.kwargs["provider_reference"] == expected
        )
        db.session.expire_all()
        assert snapshot.payment_intent_id == "pi-preserved"
        assert snapshot.latest_charge_id == "ch-preserved"
        assert order.status == ORDER_STATUS_TO_BE_PAID


@pytest.mark.parametrize(
    "unavailable",
    ["order", "owner", "provider", "snapshot", "session", "billing-domain"],
)
def test_sync_rejects_missing_foreign_or_cross_domain_evidence(
    unavailable: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider_factory = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", provider_factory)
    with app.app_context():
        order, snapshot = _seed_stripe_order()
        expected_user = order.user_bid
        if unavailable == "order":
            order.deleted = 1
        elif unavailable == "owner":
            expected_user = "unrelated-user"
        elif unavailable == "provider":
            order.payment_channel = "alipay"
        elif unavailable == "snapshot":
            snapshot.deleted = 1
        elif unavailable == "session":
            snapshot.checkout_session_id = ""
        elif unavailable == "billing-domain":
            snapshot.biz_domain = "billing"
        db.session.commit()
        with pytest.raises(AppError):
            funs.sync_stripe_checkout_session(
                app, order.order_bid, expected_user=expected_user
            )
    provider_factory.assert_not_called()


def test_late_sync_failure_rolls_back_order_snapshot_and_notification(
    app: Flask, sync_side_effects: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(
        sync_reference=Mock(
            return_value=SimpleNamespace(
                provider_payload={
                    "checkout_session": {"id": "cs-paid", "payment_status": "paid"}
                }
            )
        )
    )
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    monkeypatch.setattr(
        funs,
        "get_payment_details",
        Mock(side_effect=RuntimeError("response build failed")),
    )
    with app.app_context():
        order, snapshot = _seed_stripe_order()
        provider.sync_reference.return_value.order_bid = order.order_bid
        provider.sync_reference.return_value.provider_payload["checkout_session"] = {
            "id": "cs-stored",
            "payment_status": "paid",
            "metadata": {"order_bid": order.order_bid},
        }
        with pytest.raises(RuntimeError, match="response build failed"):
            funs.sync_stripe_checkout_session(
                app, order.order_bid, expected_user=order.user_bid
            )
        db.session.expire_all()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == 0
        assert snapshot.checkout_session_id == "cs-stored"
        assert snapshot.checkout_session_object == "{}"
    sync_side_effects.assert_not_called()


def test_sync_rejects_explicit_session_not_bound_to_order_before_provider_call(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", provider)
    with app.app_context():
        order, _snapshot = _seed_stripe_order()
        with pytest.raises(AppError) as caught:
            funs.sync_stripe_checkout_session(
                app,
                order.order_bid,
                session_id="cs-another",
                expected_user=order.user_bid,
            )
        assert caught.value.code == 3001
        assert order.status == ORDER_STATUS_TO_BE_PAID
    provider.assert_not_called()
