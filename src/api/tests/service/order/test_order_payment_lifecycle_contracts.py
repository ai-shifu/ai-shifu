"""Verify payment resumption, callbacks, refunds, and transaction boundaries."""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order import funs
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
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
    PaymentRefundResult,
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
        funs.redis_cache,
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


@pytest.mark.parametrize(
    ("status", "snapshot_status"),
    [("succeeded", 2), ("pending", 1), ("requires_action", 1), ("failed", 4), ("", 4)],
)
@pytest.mark.parametrize("explicit_amount", [None, 400])
def test_refund_persists_provider_evidence_and_preserves_payment_state_until_success(
    status: str,
    snapshot_status: int,
    explicit_amount: int | None,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = PaymentRefundResult(
        "re-test", {"id": "re-test", "status": status}, status
    )
    provider = Mock(refund_payment=Mock(return_value=response))
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(
            order, metadata_json="invalid-json", failure_code="previous"
        )
        result = funs.refund_order_payment(
            app, order.order_bid, amount=explicit_amount, reason="requested_by_customer"
        )
        request = provider.refund_payment.call_args.kwargs["request"]
        assert request.amount == (1000 if explicit_amount is None else explicit_amount)
        assert request.reason == "requested_by_customer"
        assert request.metadata == {
            "order_bid": order.order_bid,
            "payment_intent_id": "pi-test",
            "charge_id": "ch-test",
            "idempotency_key": f"order-refund:{order.order_bid}:{snapshot.stripe_order_bid}:{request.amount}",
        }
        db.session.expire_all()
        assert result["refund_id"] == "re-test"
        assert snapshot.status == snapshot_status
        assert snapshot.failure_code == (status if status == "failed" else "previous")
        assert json.loads(snapshot.metadata_json) == {
            "last_refund_id": "re-test",
            "refund_operation": {
                "idempotency_key": request.metadata["idempotency_key"],
                "status": status,
                "amount": request.amount,
                "provider_reference": "re-test",
            },
        }
        assert json.loads(snapshot.payment_intent_object) == response.raw_response
        assert order.status == (
            ORDER_STATUS_REFUND if status == "succeeded" else ORDER_STATUS_SUCCESS
        )


@pytest.mark.parametrize(
    "missing", ["order", "snapshot", "billing-domain", "unsupported-provider"]
)
def test_refund_rejects_missing_or_wrong_domain_evidence(
    missing: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order = _order("alipay" if missing == "unsupported-provider" else "stripe")
        if missing == "billing-domain":
            _snapshot(order, biz_domain="billing")
        with pytest.raises(AppError):
            funs.refund_order_payment(
                app, "absent" if missing == "order" else order.order_bid
            )
        provider.refund_payment.assert_not_called()


def test_refund_provider_error_preserves_paid_state_and_durable_pending_operation(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(refund_payment=Mock(side_effect=RuntimeError("refund unavailable")))
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order = _order(status=ORDER_STATUS_SUCCESS)
        snapshot = _snapshot(order, status=1)
        with pytest.raises(RuntimeError, match="refund unavailable"):
            funs.refund_order_payment(app, order.order_bid)
        db.session.expire_all()
        assert order.status == ORDER_STATUS_SUCCESS
        assert snapshot.status == 1
        assert json.loads(snapshot.metadata_json) == {
            "refund_operation": {
                "idempotency_key": f"order-refund:{order.order_bid}:{snapshot.stripe_order_bid}:{snapshot.amount}",
                "status": "pending",
                "amount": snapshot.amount,
            }
        }


@pytest.mark.parametrize(
    ("event_type", "expected", "snapshot_status"),
    [
        ("payment_intent.payment_failed", "failed", 4),
        ("charge.refunded", "refunded", 2),
        ("refund.created", "refunded", 2),
        ("payment_intent.canceled", "cancelled", 3),
        ("payment_intent.processing", "acknowledged", 0),
    ],
)
def test_stripe_non_success_callbacks_persist_error_and_payment_evidence(
    event_type: str,
    expected: str,
    snapshot_status: int,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.app_context():
        order = _order()
        snapshot = _snapshot(order)
        snapshot.payment_intent_id = "pi_latest"
        snapshot.latest_charge_id = "ch-latest"
        db.session.commit()
        payload = {
            "id": "ch-latest" if event_type == "charge.refunded" else "pi_latest",
            "payment_intent": "pi_latest",
            "payment_method": "pm-test",
            "metadata": {
                "order_bid": order.order_bid,
                "stripe_order_bid": snapshot.stripe_order_bid,
            },
            "charges": {"data": [{"receipt_url": "https://example.test/receipt"}]},
            "last_payment_error": {"code": "card_declined", "message": "Card declined"},
        }
        provider = Mock(
            verify_webhook=Mock(
                return_value=PaymentNotificationResult(
                    order.order_bid,
                    event_type,
                    {"data": {"object": payload}},
                    "ch-latest",
                )
            )
        )
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        result, status = funs.handle_stripe_webhook(app, b"verified-body", "signature")
        assert result["status"] == expected
        assert status == (202 if expected == "acknowledged" else 200)
        db.session.expire_all()
        assert snapshot.status == snapshot_status
        assert snapshot.latest_charge_id == "ch-latest"
        assert snapshot.payment_intent_id == "pi_latest"
        if expected == "failed":
            assert json.loads(snapshot.payment_intent_object) == payload
        else:
            assert snapshot.payment_intent_object == "{}"
        assert snapshot.receipt_url == ""
        assert snapshot.payment_method == ""
        if expected == "failed":
            assert snapshot.failure_code == "card_declined"
            assert snapshot.failure_message == "Card declined"
        assert order.status == ORDER_STATUS_TO_BE_PAID


@pytest.mark.parametrize(
    "missing", ["metadata", "order", "integration", "snapshot", "attempt"]
)
def test_stripe_callback_requires_order_attempt_and_integration_ownership(
    missing: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order = _order(payment_integration_bid="integration-valid")
        snapshot = _snapshot(order)
        metadata = {"order_bid": order.order_bid}
        expected_integration = ""
        if missing == "metadata":
            metadata = {}
        elif missing == "order":
            metadata["order_bid"] = "absent"
            expected_integration = "integration-valid"
        elif missing == "integration":
            expected_integration = "integration-wrong"
        elif missing == "snapshot":
            snapshot.biz_domain = "billing"
        else:
            metadata["stripe_order_bid"] = "wrong-attempt"
        db.session.commit()
        notification = PaymentNotificationResult(
            "", "payment_intent.succeeded", {"data": {"object": {"metadata": metadata}}}
        )
        monkeypatch.setattr(
            funs,
            "get_payment_provider",
            Mock(return_value=Mock(verify_webhook=Mock(return_value=notification))),
        )
        result, status = funs.handle_stripe_webhook(
            app, b"body", "sig", expected_integration_bid=expected_integration
        )
        assert result["status"] == ("error" if expected_integration else "ignored")
        assert status == (400 if expected_integration else 202)
        db.session.expire_all()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == 0


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


@pytest.mark.parametrize(
    "gate", ["order", "owner", "provider", "snapshot", "attempt", "billing-domain"]
)
def test_native_manual_sync_rejects_inaccessible_or_unusable_payment(
    gate: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order = _order("alipay")
        snapshot = _snapshot(order)
        if gate == "order":
            order.deleted = 1
        elif gate == "provider":
            order.payment_channel = "pingxx"
        elif gate == "snapshot":
            snapshot.deleted = 1
        elif gate == "attempt":
            snapshot.provider_attempt_id = ""
        elif gate == "billing-domain":
            snapshot.biz_domain = "billing"
        db.session.commit()
        with pytest.raises(AppError):
            funs.sync_native_payment_order(
                app,
                order.order_bid,
                expected_user="other" if gate == "owner" else order.user_bid,
            )
        provider.sync_reference.assert_not_called()


def test_native_sync_late_failure_rolls_back_snapshot_order_and_notification(
    app: Flask, payment_side_effects: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order = _order("alipay")
        snapshot = _snapshot(order)
        notification = PaymentNotificationResult(
            snapshot.provider_attempt_id,
            "TRADE_SUCCESS",
            {"trade_status": "TRADE_SUCCESS", "total_amount": "10.00"},
            "trade-paid",
        )
        monkeypatch.setattr(
            funs,
            "get_payment_provider",
            Mock(return_value=Mock(sync_reference=Mock(return_value=notification))),
        )
        monkeypatch.setattr(
            funs,
            "get_payment_details",
            Mock(side_effect=RuntimeError("late serialization failure")),
        )
        with pytest.raises(RuntimeError, match="late serialization failure"):
            funs.sync_native_payment_order(
                app, order.order_bid, expected_user=order.user_bid
            )
        db.session.expire_all()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == 0
        assert snapshot.raw_response == "{}"
        payment_side_effects.assert_not_called()


@pytest.mark.parametrize(
    "gate",
    [
        "mismatched-mode",
        "expired",
        "malformed-expiry",
        "no-credential",
        "legacy-intent",
    ],
)
def test_resume_stripe_requires_usable_unexpired_credentials(
    gate: str, app: Flask
) -> None:
    with app.app_context():
        order = _order()
        checkout = {
            "url": "https://checkout.example.test/pay",
            "expires_at": 9999999999,
        }
        if gate == "expired":
            checkout["expires_at"] = 1
        elif gate == "malformed-expiry":
            checkout["expires_at"] = "bad"
        elif gate in {"no-credential", "legacy-intent"}:
            checkout = {}
        snapshot = _snapshot(
            order,
            checkout_session_object=json.dumps(checkout),
            checkout_session_id="" if gate == "legacy-intent" else "cs-test",
            payment_intent_object="{'client_secret': 'legacy-secret'}"
            if gate == "legacy-intent"
            else "invalid",
        )
        result = funs._resume_pending_charge(
            app,
            order,
            payment_channel="stripe",
            provider_channel="payment_intent" if gate == "mismatched-mode" else None,
        )
        if gate == "legacy-intent":
            assert result is not None
            assert result.payment_payload["client_secret"] == "legacy-secret"
            assert (
                result.payment_payload["payment_intent_id"]
                == snapshot.payment_intent_id
            )
        else:
            assert result is None


@pytest.mark.parametrize(
    ("channel", "metadata", "response", "valid"),
    [
        ("wx_pub", {"prepay_id": "prepay-test"}, {}, True),
        ("wx_pub", {}, {}, False),
        ("wx_pub_qr", {"qr_url": "weixin://pay"}, {}, True),
        ("wx_pub_qr", {}, {}, False),
    ],
)
def test_resume_native_payment_reconstructs_qr_or_fresh_jsapi_signature(
    channel: str,
    metadata: dict,
    response: dict,
    valid: bool,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock(build_jsapi_params=Mock(return_value={"paySign": "new-signature"}))
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    with app.app_context():
        order = _order("wechatpay")
        _snapshot(
            order,
            channel=channel,
            metadata_json=json.dumps(metadata),
            raw_response=json.dumps(response),
        )
        result = funs._resume_pending_charge(
            app, order, payment_channel="wechatpay", provider_channel=channel
        )
        if not valid:
            assert result is None
            provider.build_jsapi_params.assert_not_called()
        elif channel == "wx_pub":
            assert result.payment_payload["jsapi_params"] == {
                "paySign": "new-signature"
            }
            provider.build_jsapi_params.assert_called_once_with(prepay_id="prepay-test")
        else:
            assert result.payment_payload["qr_url"] == "weixin://pay"


@pytest.mark.parametrize(
    "failure", ["acquire", "extend-false", "extend-error", "release", "none"]
)
def test_lifecycle_lock_rejects_lost_ownership_and_resets_request_context(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = Mock(
        acquire=Mock(return_value=failure != "acquire"),
        extend=Mock(return_value=failure != "extend-false"),
    )
    if failure == "extend-error":
        lock.extend.side_effect = RuntimeError("redis unavailable")
    if failure == "release":
        lock.release.side_effect = RuntimeError("lease expired")
    monkeypatch.setattr(funs.cache_provider, "lock", Mock(return_value=lock))
    stop = Mock(wait=Mock(side_effect=[False, True]))
    lost = Mock(is_set=Mock(return_value=False))
    lost.set.side_effect = lambda: setattr(lost.is_set, "return_value", True)
    monkeypatch.setattr(funs.threading, "Event", Mock(side_effect=[stop, lost]))
    thread = Mock()

    def make_thread(*, target: object, daemon: bool) -> Mock:
        assert daemon is True
        thread.start.side_effect = target
        return thread

    monkeypatch.setattr(funs.threading, "Thread", make_thread)
    previous = funs._payment_lock_ownership_events.get()
    if failure != "none":
        with pytest.raises(AppError), funs.payment_lifecycle_lock("order-test"):
            pass
    else:
        with funs.payment_lifecycle_lock("order-test"):
            funs._assert_payment_lifecycle_lock_owned()
    assert funs._payment_lock_ownership_events.get() == previous
    if failure != "acquire":
        lock.release.assert_called_once()
        thread.join.assert_called_once_with(timeout=1)


@pytest.mark.parametrize(
    "gate", ["missing-order", "wrong-owner", "refunded", "paid", "missing-course"]
)
def test_generate_charge_authorizes_before_provider_and_does_not_recharge_paid_order(
    gate: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    monkeypatch.setattr(funs, "get_shifu_creator_bid", Mock(return_value=""))
    monkeypatch.setattr(
        funs, "_resolve_payment_channel", Mock(return_value=("alipay", "alipay_qr"))
    )
    monkeypatch.setattr(funs, "get_shifu_info", Mock(return_value=None))
    with app.app_context():
        status = {"paid": ORDER_STATUS_SUCCESS, "refunded": ORDER_STATUS_REFUND}.get(
            gate, ORDER_STATUS_INIT
        )
        order = _order("alipay", status=status)
        if gate == "paid":
            result = funs._generate_charge_locked(
                app,
                order.order_bid,
                "alipay_qr",
                "127.0.0.1",
                expected_user=order.user_bid,
            )
            assert result.order_id == order.order_bid
        else:
            with pytest.raises(AppError):
                funs._generate_charge_locked(
                    app,
                    "absent" if gate == "missing-order" else order.order_bid,
                    "alipay_qr",
                    "127.0.0.1",
                    expected_user="other" if gate == "wrong-owner" else order.user_bid,
                )
        provider.create_payment.assert_not_called()


@pytest.mark.parametrize("provider_name", ["stripe", "alipay", "wechatpay"])
@pytest.mark.parametrize(
    "failure",
    [
        "missing-reference",
        "provider-error",
        "not-cancelled",
        "order-settled",
        "attempt-settled",
    ],
)
def test_repricing_cancellation_restores_claim_or_preserves_concurrent_settlement(
    provider_name: str,
    failure: str,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with app.app_context():
        order = _order(provider_name)
        snapshot = _snapshot(order)
        if failure == "missing-reference":
            if provider_name == "stripe":
                snapshot.checkout_session_id = ""
                snapshot.payment_intent_id = ""
            else:
                snapshot.provider_attempt_id = ""
            db.session.commit()

        def cancel(**_kwargs: object) -> object:
            if failure == "provider-error":
                message = "provider temporarily unavailable"
                raise RuntimeError(message)
            if failure == "order-settled":
                order.status = ORDER_STATUS_SUCCESS
                db.session.commit()
            elif failure == "attempt-settled":
                snapshot.status = 1
                db.session.commit()
            return SimpleNamespace(
                status="paid" if failure == "not-cancelled" else "cancelled"
            )

        provider = Mock(cancel_payment=Mock(side_effect=cancel))
        monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
        with pytest.raises(AppError):
            funs.cancel_pending_payment_for_repricing(
                app, order.order_bid, expected_user=order.user_bid
            )
        db.session.expire_all()
        if failure == "order-settled":
            assert order.status == ORDER_STATUS_SUCCESS
        elif failure == "attempt-settled":
            assert order.status == funs.ORDER_STATUS_REPRICING
        else:
            assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == (1 if failure == "attempt-settled" else 0)
        if failure == "missing-reference":
            provider.cancel_payment.assert_not_called()
        else:
            provider.cancel_payment.assert_called_once()


@pytest.mark.parametrize("keep_claim", [True, False])
def test_repricing_without_active_attempt_needs_no_provider_cancellation(
    keep_claim: bool,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_factory = Mock()
    monkeypatch.setattr(funs, "get_payment_provider", provider_factory)
    with app.app_context():
        order = _order("wechatpay")
        assert (
            funs.cancel_pending_payment_for_repricing(
                app,
                order.order_bid,
                expected_user=order.user_bid,
                keep_repricing_claim=keep_claim,
            )
            is False
        )
        db.session.expire_all()
        assert order.status == (
            funs.ORDER_STATUS_REPRICING if keep_claim else ORDER_STATUS_INIT
        )
        provider_factory.assert_not_called()


@pytest.mark.parametrize(
    "scenario",
    [
        "wechat-jsapi",
        "no-user",
        "missing-open-id",
        "provider-error",
        "late-snapshot-error",
    ],
)
def test_wechat_charge_enforces_app_scoped_identity_and_rolls_back_partial_attempt(
    scenario: str,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.order.payment_providers.base import PaymentCreationResult

    course = SimpleNamespace(bid="course-test", title="Course title", description="")
    user = Mock(
        wechat_open_id_for_app=Mock(
            return_value="" if scenario == "missing-open-id" else " open-in-app "
        )
    )
    monkeypatch.setattr(funs, "get_shifu_info", Mock(return_value=course))
    monkeypatch.setattr(
        funs, "get_shifu_creator_bid", Mock(return_value="creator-test")
    )
    monkeypatch.setattr(
        funs, "resolve_creator_public_integrations", Mock(return_value={})
    )
    monkeypatch.setattr(
        funs, "resolve_payment_integration_for_new_order", Mock(return_value=None)
    )
    monkeypatch.setattr(
        funs, "_resolve_payment_channel", Mock(return_value=("wechatpay", "wx_pub"))
    )
    monkeypatch.setattr(
        funs, "_resolve_charge_wechat_app_id", Mock(return_value="creator-app")
    )
    monkeypatch.setattr(
        funs,
        "load_user_aggregate",
        Mock(return_value=None if scenario == "no-user" else user),
    )
    provider = Mock(
        create_payment=Mock(
            return_value=PaymentCreationResult(
                "attempt-test",
                {"prepay_id": "prepay-test"},
                extra={
                    "mode": "jsapi",
                    "prepay_id": "prepay-test",
                    "jsapi_params": {"paySign": "fresh-signature"},
                },
            )
        )
    )
    if scenario == "provider-error":
        provider.create_payment.side_effect = RuntimeError("provider unavailable")
    monkeypatch.setattr(funs, "get_payment_provider", Mock(return_value=provider))
    if scenario == "late-snapshot-error":
        original = funs.upsert_native_snapshot

        def persist_then_fail(**kwargs: object) -> object:
            snapshot = original(**kwargs)
            db.session.add(snapshot)
            db.session.flush()
            message = "snapshot persistence failure"
            raise RuntimeError(message)

        monkeypatch.setattr(funs, "upsert_native_snapshot", persist_then_fail)
    with app.app_context():
        order = _order("alipay", status=ORDER_STATUS_INIT)
        if scenario == "wechat-jsapi":
            result = funs._generate_charge_locked(
                app, order.order_bid, "wx_pub", "127.0.0.1", payment_channel="wechatpay"
            )
            assert result.payment_payload["mode"] == "jsapi"
            assert result.payment_payload["jsapi_params"] == {
                "paySign": "fresh-signature"
            }
            request = provider.create_payment.call_args.kwargs["request"]
            assert request.extra["open_id"] == "open-in-app"
            assert request.body == course.title
            assert request.amount == 1000
            snapshot = WechatPayOrder.query.filter_by(order_bid=order.order_bid).one()
            assert json.loads(snapshot.metadata_json)["prepay_id"] == "prepay-test"
            assert snapshot.provider_attempt_id == "attempt-test"
        else:
            with pytest.raises(
                AppError if scenario in {"no-user", "missing-open-id"} else RuntimeError
            ):
                funs._generate_charge_locked(
                    app,
                    order.order_bid,
                    "wx_pub",
                    "127.0.0.1",
                    payment_channel="wechatpay",
                )
            db.session.expire_all()
            assert order.status == ORDER_STATUS_INIT
            assert order.payment_channel == "alipay"
            assert (
                WechatPayOrder.query.filter_by(order_bid=order.order_bid).count() == 0
            )
        if scenario != "no-user":
            user.wechat_open_id_for_app.assert_called_once_with("creator-app")
        if scenario in {"no-user", "missing-open-id"}:
            provider.create_payment.assert_not_called()
