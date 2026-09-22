"""Verify persisted delivery gates, provider failures, and requeue races."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import credit_notifications as notifications
from flaskr.service.billing.models import NotificationRecord, NotificationTemplate
from flaskr.util.datetime import now_utc

if TYPE_CHECKING:
    from flask import Flask


def _record(**changes: object) -> NotificationRecord:
    record = NotificationRecord(
        **(
            {
                "notification_bid": uuid4().hex,
                "dedupe_key": uuid4().hex,
                "creator_bid": uuid4().hex,
                "target_user_bid": uuid4().hex,
                "channel": "email",
                "notification_type": "credit_granted",
                "status": "pending",
                "recipient_snapshot": "teacher@example.test",
                "template_code": uuid4().hex,
                "template_params_json": {"credits": "10"},
                "policy_snapshot_json": {},
            }
            | changes
        )
    )
    db.session.add(record)
    db.session.commit()
    return record


def _template(record: NotificationRecord, **changes: object) -> NotificationTemplate:
    template = NotificationTemplate(
        **(
            {
                "notification_template_bid": uuid4().hex,
                "template_code": record.template_code,
                "channel": "email",
                "provider": "smtp",
                "template_status": "active",
                "email_subject": "Received ${credits}",
                "template_content": "Balance ${credits}",
                "email_html_body": "<p>Balance ${credits}</p>",
            }
            | changes
        )
    )
    db.session.add(template)
    db.session.commit()
    return template


@pytest.fixture(autouse=True)
def delivery_policy(monkeypatch: pytest.MonkeyPatch) -> dict:
    policy = {
        "enabled": True,
        "types": {
            "credit_granted": {"enabled": True, "template_code": "grant"},
            "low_balance": {"enabled": True, "template_code": "low"},
        },
    }
    monkeypatch.setattr(
        notifications, "load_credit_notification_policy", lambda: policy
    )
    return policy


@pytest.mark.parametrize(
    ("gate", "status", "error_code"),
    [
        ("disabled", "skipped_opt_out", "policy_disabled"),
        ("invalid-email", "skipped", "missing_email"),
        ("missing-template", "failed_provider", "email_template_unavailable"),
        ("draft-template", "failed_provider", "email_template_unavailable"),
        ("missing-params", "skipped", "missing_template_params"),
        (
            "zero-balance",
            "skipped_opt_out",
            "zero_balance_missing_estimated_remaining_days",
        ),
        ("opt-out", "skipped_opt_out", "opt_out"),
        ("blacklist", "skipped_opt_out", "blacklisted"),
        ("quiet-hours", "skipped_opt_out", "quiet_hours"),
    ],
)
def test_email_delivery_finalizes_rejected_attempt_without_sending(
    gate: str,
    status: str,
    error_code: str,
    app: Flask,
    delivery_policy: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = Mock()
    monkeypatch.setattr(notifications, "send_smtp_email", sender)
    with app.app_context():
        record = _record()
        template = _template(record)
        if gate == "disabled":
            delivery_policy["enabled"] = False
        elif gate == "invalid-email":
            record.recipient_snapshot = "not-an-email"
        elif gate == "missing-template":
            template.deleted = 1
        elif gate == "draft-template":
            template.template_status = "draft"
        elif gate == "missing-params":
            record.template_params_json = {}
        elif gate == "zero-balance":
            record.notification_type = "low_balance"
            record.template_params_json = {"available_credits": "0"}
        elif gate == "opt-out":
            delivery_policy["opt_out"] = {"creator_bids": [record.creator_bid]}
        elif gate == "blacklist":
            delivery_policy["blacklist"] = {"creator_bids": [record.creator_bid]}
        else:
            delivery_policy["quiet_hours"] = {
                "enabled": True,
                "start": "00:00",
                "end": "23:59",
                "timezone": "UTC",
            }
            monkeypatch.setattr(
                notifications, "now_utc", lambda: now_utc().replace(hour=12)
            )
        db.session.commit()
        result = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        db.session.expire_all()
        assert result["status"] == status
        assert record.status == status
        assert record.error_code == error_code
        assert record.attempted_at is not None
        assert record.sent_at is None
        sender.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        notifications.SmtpConfigurationError("missing configuration"),
        OSError("mail unavailable"),
        RuntimeError("mail unavailable"),
        ValueError("invalid sender"),
    ],
)
def test_email_provider_failure_is_persisted_and_remains_retryable(
    error: Exception,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = Mock(side_effect=error)
    monkeypatch.setattr(notifications, "send_smtp_email", sender)
    with app.app_context():
        record = _record()
        _template(record)
        result = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        db.session.expire_all()
        code = (
            "smtp_configuration_error"
            if isinstance(error, notifications.SmtpConfigurationError)
            else "smtp_exception"
        )
        assert result["error_code"] == code
        assert record.status == "failed_provider"
        assert record.provider_response_json == {
            "provider": "smtp",
            "error": str(error),
        }
        assert record.sent_at is None
        sender.assert_called_once()


def test_email_sent_record_cannot_send_again_and_html_values_are_escaped(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = Mock(return_value={"provider": "smtp", "accepted": True})
    monkeypatch.setattr(notifications, "send_smtp_email", sender)
    with app.app_context():
        record = _record(
            recipient_snapshot=" Teacher@Example.Test ",
            template_params_json={"credits": "<10 & 20>"},
        )
        _template(record)
        first = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        repeat = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        assert first["status"] == "sent"
        assert repeat["status"] == "noop"
        db.session.expire_all()
        assert record.sent_at is not None
        sender.assert_called_once_with(
            app,
            recipient="teacher@example.test",
            subject="Received <10 & 20>",
            plain_body="Balance <10 & 20>",
            html_body="<p>Balance &lt;10 &amp; 20&gt;</p>",
        )


@pytest.mark.parametrize(
    ("mobile", "code"), [("", "missing_mobile"), ("bad-mobile", "invalid_mobile")]
)
def test_sms_delivery_rechecks_current_mobile_before_provider_call(
    mobile: str,
    code: str,
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = Mock()
    monkeypatch.setattr(notifications, "send_sms_ali", sender)
    monkeypatch.setattr(
        notifications, "load_creator_mobile_snapshot", lambda _bid: mobile
    )
    with app.app_context():
        record = _record(channel="sms", mobile_snapshot="13800000000")
        result = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        db.session.expire_all()
        assert result["status"] == "skipped_no_mobile"
        assert record.error_code == code
        sender.assert_not_called()


def test_sms_missing_template_is_failure_without_network_call(
    app: Flask,
    delivery_policy: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_policy["types"]["credit_granted"]["template_code"] = ""
    sender = Mock()
    monkeypatch.setattr(notifications, "send_sms_ali", sender)
    monkeypatch.setattr(
        notifications, "load_creator_mobile_snapshot", lambda _bid: "13800000000"
    )
    with app.app_context():
        record = _record(channel="sms", template_code="")
        result = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        db.session.expire_all()
        assert result["status"] == "failed_provider"
        assert record.error_code == "missing_template_code"
        sender.assert_not_called()


@pytest.mark.parametrize("gate", ["recipient", "creator", "budget"])
def test_delivery_limits_count_only_current_day_successful_eligible_records(
    gate: str,
    app: Flask,
    delivery_policy: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = Mock(return_value=SimpleNamespace(to_map=lambda: {"Code": "OK"}))
    mobile = "13800000000"
    monkeypatch.setattr(notifications, "send_sms_ali", sender)
    monkeypatch.setattr(
        notifications, "load_creator_mobile_snapshot", lambda _bid: mobile
    )
    with app.app_context():
        # A future isolated day keeps suite-wide sent records outside this budget.
        now = now_utc().replace(year=2040, hour=12)
        monkeypatch.setattr(notifications, "now_utc", lambda: now)
        record = _record(channel="sms")
        if gate == "budget":
            delivery_policy["budget"] = {"daily_sms_limit": 1}
        else:
            delivery_policy["frequency"] = {
                "per_mobile_per_day": int(gate == "recipient"),
                "per_creator_per_type_per_day": int(gate == "creator"),
            }
        _record(
            channel="sms",
            creator_bid=record.creator_bid,
            mobile_snapshot=mobile,
            status="sent",
            sent_at=now - timedelta(days=1),
        )
        _record(
            channel="sms",
            creator_bid=record.creator_bid,
            mobile_snapshot=mobile,
            status="failed_provider",
            sent_at=now,
        )
        first = notifications.deliver_credit_notification(
            app, notification_bid=record.notification_bid
        )
        assert first["status"] == "sent"
        second = _record(channel="sms", creator_bid=record.creator_bid)
        result = notifications.deliver_credit_notification(
            app, notification_bid=second.notification_bid
        )
        assert result["status"] == "skipped_opt_out"
        assert (
            result["reason"]
            == {
                "recipient": "frequency_mobile_daily",
                "creator": "frequency_creator_type_daily",
                "budget": "budget_daily_sms_limit",
            }[gate]
        )
        sender.assert_called_once()
        # Remove future evidence so later parametrizations have a clean day.
        NotificationRecord.query.filter(
            NotificationRecord.creator_bid == record.creator_bid
        ).update({"deleted": 1})
        db.session.commit()


@pytest.mark.parametrize(
    ("operation", "bid", "status"),
    [
        ("deliver", " ", "invalid_notification_bid"),
        ("deliver", "nonexistent", "not_found"),
        ("requeue", " ", "invalid_notification_bid"),
        ("requeue", "nonexistent", "not_found"),
    ],
)
def test_missing_notification_cannot_be_delivered_or_requeued(
    operation: str, bid: str, status: str, app: Flask
) -> None:
    callback = (
        notifications.deliver_credit_notification
        if operation == "deliver"
        else notifications.requeue_credit_notification
    )
    with app.app_context():
        assert callback(app, notification_bid=bid)["status"] == status


@pytest.mark.parametrize(
    "outcome", ["missing-task", "broker-error", "success", "invalid-bid"]
)
def test_enqueue_reports_dispatch_acceptance_and_broker_failures(
    outcome: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.common import celery_app

    task = Mock()
    if outcome == "broker-error":
        task.apply_async.side_effect = RuntimeError("broker unavailable")
    factory = Mock(
        return_value=SimpleNamespace(
            tasks={} if outcome == "missing-task" else {notifications.TASK_NAME: task}
        )
    )
    monkeypatch.setattr(celery_app, "get_celery_app", factory)
    result = notifications.enqueue_credit_notification(
        app, notification_bid=" " if outcome == "invalid-bid" else " notification-test "
    )
    assert (
        result["status"]
        == {
            "missing-task": "task_unavailable",
            "broker-error": "enqueue_failed",
            "success": "enqueued",
            "invalid-bid": "invalid_notification_bid",
        }[outcome]
    )
    assert result["enqueued"] is (outcome == "success")
    if outcome in {"success", "broker-error"}:
        task.apply_async.assert_called_once_with(
            kwargs={"notification_bid": "notification-test"}
        )
    else:
        task.apply_async.assert_not_called()


@pytest.mark.parametrize("concurrent_change", ["sent", "deleted", "already-pending"])
def test_requeue_preserves_status_changed_while_broker_dispatches(
    concurrent_change: str, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        record = _record(
            status="pending"
            if concurrent_change == "already-pending"
            else "failed_provider"
        )

        def dispatch(_app: Flask, *, notification_bid: str) -> dict:
            if concurrent_change == "deleted":
                record.deleted = 1
            else:
                record.status = "sent"
            db.session.commit()
            return {
                "status": "enqueued",
                "enqueued": True,
                "notification_bid": notification_bid,
            }

        enqueue = Mock(side_effect=dispatch)
        monkeypatch.setattr(notifications, "enqueue_credit_notification", enqueue)
        result = notifications.requeue_credit_notification(
            app, notification_bid=record.notification_bid
        )
        if concurrent_change == "already-pending":
            assert result["status"] == "not_requeueable"
            enqueue.assert_not_called()
        else:
            assert result["notification_status"] == (
                "not_found" if concurrent_change == "deleted" else "sent"
            )
            db.session.expire_all()
            assert record.status != "pending"
