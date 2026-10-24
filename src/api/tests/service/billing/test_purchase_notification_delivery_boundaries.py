"""Exercise persisted purchase-notification gates and delivery races."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing import notifications
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.util.datetime import now_utc

from tests.service.billing.test_billing_subscription_sms import (
    _create_paid_start_order,
    _create_subscription,
    _seed_creator,
)
from tests.service.billing.test_billing_subscription_sms import (
    billing_subscription_sms_app as message_app,
)

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["message_app"]


def _stage(message_app: Flask, channel: str, *, creator: bool = True) -> BillingOrder:
    if creator:
        _seed_creator(message_app)
    now = now_utc()
    subscription = _create_subscription(
        subscription_bid="delivery-subscription",
        current_period_start_at=now,
        current_period_end_at=now + timedelta(days=30),
    )
    order = _create_paid_start_order(
        bill_order_bid="delivery-order",
        subscription_bid=subscription.subscription_bid,
        paid_at=now,
        metadata_json={"notifications": {channel: {"status": "pending"}}},
    )
    db.session.add_all([subscription, order])
    db.session.commit()
    return order


@pytest.mark.parametrize(
    "channel", ["billing_paid_feishu", "subscription_purchase_sms"]
)
def test_deleted_order_is_not_resurrected_after_successful_provider_delivery(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, channel: str
) -> None:
    order = _stage(message_app, channel)
    order_bid = order.bill_order_bid

    def provider(*_args: object, **_kwargs: object) -> dict[str, bool]:
        persisted = BillingOrder.query.filter_by(bill_order_bid=order_bid).one()
        assert (
            persisted.metadata_json["notifications"][channel]["status"] == "processing"
        )
        persisted.deleted = 1
        db.session.commit()
        return {"accepted": True}

    transport = Mock(side_effect=provider)
    monkeypatch.setattr(
        notifications,
        "send_notify" if channel == "billing_paid_feishu" else "send_sms_ali",
        transport,
    )
    deliver = getattr(notifications, f"deliver_{channel}")
    result = deliver(message_app, bill_order_bid=order_bid)
    assert result["status"] == "not_found"
    db.session.expire_all()
    assert order.deleted == 1
    assert order.metadata_json["notifications"][channel]["status"] == "processing"
    assert deliver(message_app, bill_order_bid=order_bid)["status"] == "not_found"
    transport.assert_called_once()


@pytest.mark.parametrize("failure", [None, RuntimeError("delivery unavailable")])
def test_feishu_provider_failure_is_retryable_and_success_clears_failure(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    order = _stage(message_app, "billing_paid_feishu")
    transport = Mock(side_effect=failure) if failure else Mock(return_value=None)
    monkeypatch.setattr(notifications, "send_notify", transport)
    result = notifications.deliver_billing_paid_feishu(
        message_app, bill_order_bid=order.bill_order_bid
    )
    assert result["status"] == "failed_provider"
    db.session.expire_all()
    payload = order.metadata_json["notifications"]["billing_paid_feishu"]
    assert payload["error_code"] == "provider_failed"
    assert payload["error_message"]
    assert payload["processed_at"].endswith("Z")
    transport.side_effect = None
    transport.return_value = {"ok": True}
    result = notifications.deliver_billing_paid_feishu(
        message_app, bill_order_bid=order.bill_order_bid
    )
    assert result["status"] == "sent"
    db.session.expire_all()
    payload = order.metadata_json["notifications"]["billing_paid_feishu"]
    assert "error_code" not in payload
    assert "error_message" not in payload
    assert payload["sent_at"].endswith("Z")
    assert (
        notifications.deliver_billing_paid_feishu(
            message_app, bill_order_bid=order.bill_order_bid
        )["status"]
        == "noop"
    )
    assert transport.call_count == 2


@pytest.mark.parametrize(
    "ineligible", ["unpaid", "free", "unsupported", "missing_user"]
)
def test_feishu_ineligible_paid_notification_is_finalized_without_external_send(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, ineligible: str
) -> None:
    order = _stage(
        message_app, "billing_paid_feishu", creator=ineligible != "missing_user"
    )
    if ineligible == "unpaid":
        order.status = BILLING_ORDER_STATUS_PENDING
    elif ineligible == "free":
        order.paid_amount = order.payable_amount = 0
    elif ineligible == "unsupported":
        order.order_type = 9999
    db.session.commit()
    transport = Mock()
    monkeypatch.setattr(notifications, "send_notify", transport)
    result = notifications.deliver_billing_paid_feishu(
        message_app, bill_order_bid=order.bill_order_bid
    )
    expected = (
        "skipped_missing_user"
        if ineligible == "missing_user"
        else "skipped_unsupported"
    )
    assert result["status"] == expected
    db.session.expire_all()
    assert (
        order.metadata_json["notifications"]["billing_paid_feishu"]["status"]
        == expected
    )
    transport.assert_not_called()


@pytest.mark.parametrize(
    "channel", ["billing_paid_feishu", "subscription_purchase_sms"]
)
@pytest.mark.parametrize("order_bid", [" ", "missing"])
def test_delivery_rejects_missing_order_without_provider_call(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, channel: str, order_bid: str
) -> None:
    transport = Mock()
    monkeypatch.setattr(
        notifications,
        "send_notify" if channel == "billing_paid_feishu" else "send_sms_ali",
        transport,
    )
    result = getattr(notifications, f"deliver_{channel}")(
        message_app, bill_order_bid=order_bid
    )
    assert result["status"] == (
        "not_found" if order_bid.strip() else "invalid_bill_order_bid"
    )
    transport.assert_not_called()


@pytest.mark.parametrize(
    "channel", ["billing_paid_feishu", "subscription_purchase_sms"]
)
@pytest.mark.parametrize("broker", ["missing_task", "unavailable", "blank"])
def test_enqueue_reports_broker_outcome_without_falsely_claiming_delivery(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, channel: str, broker: str
) -> None:
    task = Mock()
    if broker == "unavailable":
        task.apply_async.side_effect = RuntimeError("broker unavailable")
    task_name = (
        notifications.BILLING_PAID_FEISHU_TASK_NAME
        if channel == "billing_paid_feishu"
        else notifications.TASK_NAME
    )
    factory = Mock(
        return_value=SimpleNamespace(
            tasks={} if broker == "missing_task" else {task_name: task}
        )
    )
    monkeypatch.setattr("flaskr.common.celery_app.get_celery_app", factory)
    result = getattr(notifications, f"enqueue_{channel}")(
        message_app, bill_order_bid=" " if broker == "blank" else " delivery-order "
    )
    assert result["enqueued"] is False
    assert (
        result["status"]
        == {
            "blank": "invalid_bill_order_bid",
            "missing_task": "task_unavailable",
            "unavailable": "enqueue_failed",
        }[broker]
    )
    if broker == "blank":
        factory.assert_not_called()
    elif broker == "unavailable":
        task.apply_async.assert_called_once_with(
            kwargs={"bill_order_bid": "delivery-order"}
        )
        assert result["message"] == "broker unavailable"


@pytest.mark.parametrize("state", ["blank", "missing", "sent", "failed_provider"])
def test_manual_sms_requeue_preserves_persisted_delivery_state(
    message_app: Flask, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    task = Mock()
    monkeypatch.setattr(
        "flaskr.common.celery_app.get_celery_app",
        lambda **_kwargs: SimpleNamespace(tasks={notifications.TASK_NAME: task}),
    )
    bid = " " if state == "blank" else "delivery-order"
    before = None
    if state in {"sent", "failed_provider"}:
        order = _stage(message_app, "subscription_purchase_sms")
        order.metadata_json = {
            "notifications": {"subscription_purchase_sms": {"status": state}}
        }
        db.session.commit()
        before = deepcopy(order.metadata_json)
    result = notifications.requeue_subscription_purchase_sms(
        message_app, bill_order_bid=bid
    )
    assert (
        result["status"]
        == {
            "blank": "invalid_bill_order_bid",
            "missing": "not_found",
            "sent": "not_requeueable",
            "failed_provider": "enqueued",
        }[state]
    )
    if before:
        db.session.expire_all()
        assert order.metadata_json == before
    assert task.apply_async.call_count == int(state == "failed_provider")


@pytest.mark.parametrize(
    "channel", ["billing_paid_feishu", "subscription_purchase_sms"]
)
@pytest.mark.parametrize(
    "gate", ["unpaid", "already_paid", "already_staged", "malformed_metadata"]
)
def test_purchase_staging_preserves_payment_transition_and_existing_notifications(
    message_app: Flask, channel: str, gate: str
) -> None:
    order = _stage(message_app, channel)
    previous = BILLING_ORDER_STATUS_PENDING
    if gate == "unpaid":
        order.status = BILLING_ORDER_STATUS_PENDING
    elif gate == "already_paid":
        previous = BILLING_ORDER_STATUS_PAID
    elif gate == "malformed_metadata":
        order.metadata_json = ["legacy-invalid-object"]
    before = deepcopy(order.metadata_json)
    staged = getattr(notifications, f"stage_{channel}_for_paid_order")(
        order, previous_status=previous
    )
    assert staged is (gate == "malformed_metadata")
    if staged:
        db.session.commit()
        db.session.expire_all()
        assert order.metadata_json["notifications"][channel]["status"] == "pending"
    else:
        assert order.metadata_json == before


def test_sms_does_not_stage_topups(message_app: Flask) -> None:
    order = _stage(message_app, "subscription_purchase_sms")
    order.order_type = BILLING_ORDER_TYPE_TOPUP
    assert (
        notifications.stage_subscription_purchase_sms_for_paid_order(
            order, previous_status=BILLING_ORDER_STATUS_PENDING
        )
        is False
    )


@pytest.mark.parametrize(
    ("amount", "expected"), [("invalid", "0"), ("12.5000", "12.5")]
)
def test_message_credit_formatting_handles_provider_values(
    amount: str, expected: str
) -> None:
    assert notifications._format_credit_amount(amount) == expected


def test_message_amount_formatting_handles_unparseable_legacy_amount() -> None:
    assert notifications._format_minor_currency_amount(None, "invalid") == "CNY 0.00"
