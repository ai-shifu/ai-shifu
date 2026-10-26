"""Verify stale checkout protection and provider reconciliation selection rules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.billing import checkout
from flaskr.service.billing.models import BillingOrder
from flaskr.service.common.models import AppError


@pytest.mark.parametrize(
    "session",
    [
        {"status": "complete", "payment_status": "paid"},
        {"status": "open", "payment_status": "paid"},
        {"status": "processing"},
        {},
    ],
)
def test_paid_or_unknown_checkout_cannot_be_replaced(
    session: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(retrieve_checkout_session=Mock(return_value=session))
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with pytest.raises(AppError):
        checkout._reconcile_stored_stripe_checkout_before_replacement(
            Flask(__name__), bill_order_bid="bill-test", checkout_session_id="cs-test"
        )
    provider.expire_checkout_session.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["retrieve", "expire"])
def test_provider_failure_prevents_checkout_replacement(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(retrieve_checkout_session=Mock(return_value={"status": "open"}))
    failing = (
        provider.retrieve_checkout_session
        if failure_stage == "retrieve"
        else provider.expire_checkout_session
    )
    failing.side_effect = RuntimeError("provider unavailable")
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    with pytest.raises(AppError):
        checkout._reconcile_stored_stripe_checkout_before_replacement(
            Flask(__name__), bill_order_bid="bill-test", checkout_session_id="cs-test"
        )
    if failure_stage == "retrieve":
        provider.expire_checkout_session.assert_not_called()


@pytest.mark.parametrize("session_status", ["open", "expired"])
def test_unpaid_checkout_is_expired_once_before_replacement(
    session_status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = Flask(__name__)
    provider = Mock(
        retrieve_checkout_session=Mock(
            return_value=SimpleNamespace(
                to_dict=lambda: {"status": session_status, "payment_status": "unpaid"}
            )
        )
    )
    monkeypatch.setattr(checkout, "get_payment_provider", Mock(return_value=provider))
    checkout._reconcile_stored_stripe_checkout_before_replacement(
        app, bill_order_bid="bill-test", checkout_session_id="cs-test"
    )
    if session_status == "open":
        provider.expire_checkout_session.assert_called_once_with(
            session_id="cs-test", app=app
        )
    else:
        provider.expire_checkout_session.assert_not_called()


def test_missing_checkout_reference_needs_no_provider_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_provider = Mock()
    monkeypatch.setattr(checkout, "get_payment_provider", load_provider)
    checkout._reconcile_stored_stripe_checkout_before_replacement(
        Flask(__name__), bill_order_bid="bill-test", checkout_session_id=""
    )
    load_provider.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "channel", "open_id", "valid"),
    [
        ("alipay", "alipay_qr", None, True),
        ("alipay", "wx_pub", None, False),
        ("wechatpay", "wx_pub_qr", None, True),
        ("wechatpay", "wx_pub", " open-test ", True),
        ("wechatpay", "wx_pub", "", False),
        ("wechatpay", "wx_pub", None, False),
        ("wechatpay", "wx_wap", None, False),
        ("unknown", "alipay_qr", None, False),
    ],
)
def test_native_checkout_rejects_unsupported_channels_and_unbound_jsapi_accounts(
    provider: str,
    channel: str,
    open_id: str | None,
    valid: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(wechat_open_id=open_id) if open_id is not None else None
    load_user = Mock(return_value=user)
    monkeypatch.setattr(checkout, "load_user_aggregate", load_user)
    params = {
        "creator_bid": "creator-test",
        "product": SimpleNamespace(),
        "provider": provider,
        "channel": channel,
    }
    if valid:
        assert checkout._build_native_provider_options(**params) == (
            {"open_id": "open-test"} if channel == "wx_pub" else {}
        )
    else:
        with pytest.raises(AppError):
            checkout._build_native_provider_options(**params)
    if provider == "wechatpay" and channel == "wx_pub":
        load_user.assert_called_once_with("creator-test")
    else:
        load_user.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "lookup", "explicit_session"),
    [
        ("stripe", "order", "cs-explicit"),
        ("stripe", "reference", ""),
        ("alipay", "reference", "ignored-session"),
    ],
)
def test_reference_reconciliation_finds_owned_order_and_passes_stripe_session_only(
    provider: str,
    lookup: str,
    explicit_session: str,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    creator_bid = f"creator-{suffix}"
    order_bid = f"bill-{suffix}"
    reference = f"ref-{suffix}"
    with app.app_context():
        db.session.add(
            BillingOrder(
                bill_order_bid=order_bid,
                creator_bid=creator_bid,
                payment_provider=provider,
                provider_reference_id=reference,
            )
        )
        db.session.commit()
    sync = Mock(return_value=SimpleNamespace(status="paid"))
    monkeypatch.setattr(checkout, "sync_billing_order", sync)
    result = checkout.reconcile_billing_provider_reference(
        app,
        creator_bid=f" {creator_bid} ",
        payment_provider=provider,
        bill_order_bid=order_bid if lookup == "order" else "",
        provider_reference_id=reference,
        session_id=explicit_session,
    )
    expected_payload = (
        {"session_id": explicit_session or reference} if provider == "stripe" else {}
    )
    sync.assert_called_once_with(app, creator_bid, order_bid, expected_payload)
    assert result.to_task_payload() == {
        "status": "paid",
        "creator_bid": creator_bid,
        "bill_order_bid": order_bid,
        "provider_reference_id": reference,
        "payment_provider": provider,
    }
    assert result["bill_order_bid"] == order_bid


@pytest.mark.parametrize(
    "mismatch", ["creator", "provider", "deleted", "missing-reference", "missing-order"]
)
def test_reference_reconciliation_cannot_sync_unmatched_or_deleted_orders(
    mismatch: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = uuid4().hex
    creator_bid, order_bid, reference = (
        f"creator-{suffix}",
        f"bill-{suffix}",
        f"ref-{suffix}",
    )
    with app.app_context():
        db.session.add(
            BillingOrder(
                bill_order_bid=order_bid,
                creator_bid=creator_bid,
                payment_provider="stripe",
                provider_reference_id=reference,
                deleted=1 if mismatch == "deleted" else 0,
            )
        )
        db.session.commit()
    sync = Mock()
    monkeypatch.setattr(checkout, "sync_billing_order", sync)
    result = checkout.reconcile_billing_provider_reference(
        app,
        creator_bid="unrelated-owner" if mismatch == "creator" else creator_bid,
        payment_provider="alipay" if mismatch == "provider" else "stripe",
        provider_reference_id="" if mismatch == "missing-reference" else reference,
        bill_order_bid="not-a-real-order" if mismatch == "missing-order" else "",
    )
    assert result.status == "order_not_found"
    sync.assert_not_called()
