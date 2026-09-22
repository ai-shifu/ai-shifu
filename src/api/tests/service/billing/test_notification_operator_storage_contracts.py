"""Verify notification operator queries, provider caching and durable suppression."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import credit_notifications as notifications
from flaskr.service.billing.models import NotificationRecord, NotificationTemplate
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc

from tests.service.billing.test_credit_notifications import (
    _seed_creator,
)
from tests.service.billing.test_credit_notifications import (
    credit_notifications_app as notification_app,
)

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["notification_app"]


def _record(**changes: object) -> NotificationRecord:
    record = NotificationRecord(
        **{
            "notification_bid": uuid4().hex,
            "dedupe_key": uuid4().hex,
            "creator_bid": "teacher-1",
            "target_user_bid": "teacher-1",
            "notification_type": "credit_expiring",
            "channel": "sms",
            "source_type": "wallet_bucket",
            "source_bid": "bucket-1",
            "status": "pending",
            "mobile_snapshot": "13800000000",
            "template_code": "SMS-1",
            "created_at": now_utc(),
            **changes,
        }
    )
    db.session.add(record)
    return record


def _template(**changes: object) -> NotificationTemplate:
    template = NotificationTemplate(
        **{
            "notification_template_bid": uuid4().hex,
            "template_code": uuid4().hex,
            "template_name": "Expiry notice",
            "channel": "sms",
            "provider": "aliyun",
            "template_content": "Balance ${credits}",
            "template_status": "1",
            "placeholders_json": ["credits"],
            "sync_status": "synced",
            **changes,
        }
    )
    db.session.add(template)
    return template


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"delivery_status": "pending"}, ["pending"]),
        ({"delivery_status": "sent"}, ["sent"]),
        ({"delivery_status": "failed"}, ["failed_provider"]),
        ({"delivery_status": "not_sent"}, ["skipped_opt_out"]),
        (
            {"delivery_status": "unknown"},
            ["pending", "sent", "failed_provider", "skipped_opt_out"],
        ),
        ({"status": "sent"}, ["sent"]),
        ({"status": "skipped"}, ["skipped_opt_out"]),
        (
            {"mobile": "13800000000", "source_bid": "bucket-1", "status": "pending"},
            ["pending"],
        ),
        (
            {"creator_keyword": "teacher-1"},
            ["pending", "sent", "failed_provider", "skipped_opt_out"],
        ),
        (
            {"creator_keyword": "Mathematics"},
            ["pending", "sent", "failed_provider", "skipped_opt_out"],
        ),
        ({"creator_keyword": "unmatched-user"}, []),
    ],
)
def test_operator_filters_are_applied_to_persisted_records(
    notification_app: Flask,
    filters: dict,
    expected: list[str],
) -> None:
    app = notification_app
    _seed_creator(app, creator_bid="teacher-1", nickname="Mathematics Teacher")
    now = now_utc()
    for index, status in enumerate(
        ["pending", "sent", "failed_provider", "skipped_opt_out"]
    ):
        _record(status=status, created_at=now - timedelta(minutes=index))
    _record(deleted=1)
    _record(
        creator_bid="other", target_user_bid="other", created_at=now - timedelta(days=2)
    )
    db.session.commit()
    result = notifications.list_credit_notifications(
        app,
        filters={"start_time": now - timedelta(hours=1), "end_time": now, **filters},
    )
    assert result["total"] == len(expected)
    assert [row["status"] for row in result["items"]] == expected
    assert all(row["creator_bid"] == "teacher-1" for row in result["items"])


def test_overview_and_pagination_ignore_deleted_records(
    notification_app: Flask,
) -> None:
    for status in [
        "pending",
        "sent",
        "sent",
        "failed_provider",
        "skipped_opt_out",
        "suppressed_duplicate",
    ]:
        _record(status=status)
    _record(deleted=1)
    db.session.commit()
    assert notifications.get_operator_credit_notification_overview(
        notification_app
    ) == {
        "total": 6,
        "pending": 1,
        "sent": 2,
        "failed": 1,
        "skipped": 2,
    }
    result = notifications.list_credit_notifications(
        notification_app, page_index=2, page_size=2
    )
    assert result["page_count"] == 3
    assert result["total"] == 6
    assert len(result["items"]) == 2
    assert (
        notifications.list_credit_notifications(notification_app, page_size=1000)[
            "page_size"
        ]
        == 100
    )


@pytest.mark.parametrize("bid", ["", "missing"])
def test_missing_notification_detail_is_rejected(
    notification_app: Flask, bid: str
) -> None:
    with pytest.raises(AppError):
        notifications.get_credit_notification_detail(
            notification_app, notification_bid=bid
        )


@pytest.mark.parametrize("configured", [False, True])
def test_email_template_listing_keeps_local_drafts_when_smtp_is_unavailable(
    notification_app: Flask,
    configured: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _template(channel="email", provider="smtp", template_status="draft")
    _template(channel="email", provider="smtp", deleted=1)
    _template()
    _template(channel="email", provider="other")
    db.session.commit()
    monkeypatch.setattr(notifications, "is_smtp_configured", lambda _: configured)
    result = notifications.list_credit_notification_email_templates(notification_app)
    assert result["provider_available"] is configured
    assert result["error_code"] == ("" if configured else "smtp_configuration_missing")
    assert [row["notification_template_bid"] for row in result["items"]] == [
        draft.notification_template_bid
    ]
    assert result["items"][0]["template_status"] == "draft"


@pytest.mark.parametrize("damage", ["empty-bid", "status", "missing", "incompatible"])
def test_email_status_rejects_invalid_target_without_mutation(
    notification_app: Flask,
    damage: str,
) -> None:
    template = _template(
        channel="email",
        provider="smtp",
        template_status="draft",
        email_subject="${unknown}",
        email_html_body="${unknown}",
    )
    db.session.commit()
    bid = (
        ""
        if damage == "empty-bid"
        else "missing"
        if damage == "missing"
        else template.notification_template_bid
    )
    with pytest.raises(AppError):
        notifications.update_credit_notification_email_template_status(
            notification_app,
            notification_template_bid=bid,
            template_status="bad" if damage == "status" else "active",
        )
    db.session.expire_all()
    assert template.template_status == "draft"


@pytest.mark.parametrize("target", ["missing", "sms", "foreign-provider"])
def test_email_template_edit_does_not_overwrite_another_channel(
    notification_app: Flask,
    target: str,
) -> None:
    template = _template(
        channel="sms" if target == "sms" else "email", provider="other"
    )
    db.session.commit()
    with pytest.raises(AppError):
        notifications.save_credit_notification_email_template(
            notification_app,
            notification_template_bid="missing"
            if target == "missing"
            else template.notification_template_bid,
            payload={
                "template_name": "Edited",
                "email_subject": "Credits",
                "email_html_body": "<p>Credits</p>",
            },
        )
    db.session.expire_all()
    assert template.template_name == "Expiry notice"


def test_generated_email_code_collision_preserves_existing_template(
    notification_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = _template(
        channel="email", provider="smtp", template_code="EMAIL_DUPLICATE"
    )
    db.session.commit()
    monkeypatch.setattr(notifications, "generate_id", lambda _: "duplicate")
    with pytest.raises(AppError):
        notifications.save_credit_notification_email_template(
            notification_app,
            payload={
                "template_name": "Edited",
                "email_subject": "Credits",
                "email_html_body": "<p>Credits</p>",
            },
        )
    db.session.expire_all()
    assert NotificationTemplate.query.count() == 1
    assert template.template_name == "Expiry notice"


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(body=None),
        SimpleNamespace(body=SimpleNamespace(code="Denied", request_id="request-1")),
    ],
)
def test_sms_template_rejection_is_persisted_and_safe_to_retry(
    notification_app: Flask,
    response: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = notification_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="test",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="test",
    )
    provider = Mock(return_value=response)
    monkeypatch.setattr(notifications, "get_sms_template_ali", provider)
    result = notifications.sync_credit_notification_template(
        app, notification_type="credit_granted", template_code="SMS-REJECTED"
    )
    assert result["sync_status"] == "failed_provider"
    assert result["error_code"] == (
        "provider_failed" if response.body is None else "Denied"
    )
    template = NotificationTemplate.query.filter_by(template_code="SMS-REJECTED").one()
    assert template.error_code == result["error_code"]
    provider.return_value = SimpleNamespace(
        body=SimpleNamespace(
            code="OK", template_content="${credits}", template_status="1"
        )
    )
    retry = notifications.sync_credit_notification_template(
        app, notification_type="credit_granted", template_code="SMS-REJECTED"
    )
    db.session.expire_all()
    assert retry["sync_status"] == "synced"
    assert template.error_code == ""
    assert NotificationTemplate.query.count() == 1


@pytest.mark.parametrize(
    "body", [None, SimpleNamespace(code="Denied", message="No permission")]
)
def test_provider_template_list_failure_keeps_local_cache(
    notification_app: Flask,
    body: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = notification_app
    template = _template(template_code="CACHED")
    db.session.commit()
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="test",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="test",
    )
    monkeypatch.setattr(
        notifications,
        "query_sms_template_list_ali",
        Mock(return_value=SimpleNamespace(body=body)),
    )
    result = notifications.list_credit_notification_templates(app)
    assert result["source"] == "local"
    assert result["provider_available"] is False
    assert result["items"][0]["template_code"] == template.template_code
    db.session.expire_all()
    assert template.sync_status == "synced"


@pytest.mark.parametrize("stop", ["duplicate-page", "page-limit"])
def test_provider_template_pagination_stops_on_repeated_pages_or_configured_limit(
    notification_app: Flask,
    stop: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = notification_app
    app.config.update(
        ALIBABA_CLOUD_SMS_ACCESS_KEY_ID="test",
        ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET="test",
    )
    monkeypatch.setattr(notifications, "ALIYUN_TEMPLATE_LIST_PAGE_SIZE", 2)
    monkeypatch.setattr(notifications, "ALIYUN_TEMPLATE_LIST_MAX_PAGES", 2)
    calls = []

    def provider(_: Flask, *, page_index: int, page_size: int) -> object:
        calls.append(page_index)
        assert page_size == 2
        codes = (
            ["A", "B"] if stop == "duplicate-page" or page_index == 1 else ["C", "D"]
        )
        return SimpleNamespace(
            body=SimpleNamespace(
                code="OK",
                sms_template_list=[
                    SimpleNamespace(template_code=code, template_content="${credits}")
                    for code in codes
                ],
            )
        )

    monkeypatch.setattr(notifications, "query_sms_template_list_ali", provider)
    result = notifications.list_credit_notification_templates(app)
    assert calls == [1, 2]
    assert [row["template_code"] for row in result["items"]] == (
        ["A", "B"] if stop == "duplicate-page" else ["A", "B", "C", "D"]
    )
    assert NotificationTemplate.query.count() == len(result["items"])


@pytest.mark.parametrize("rollback", [False, True])
def test_extending_expiry_suppresses_only_processable_reminders_in_callers_transaction(
    notification_app: Flask,
    rollback: bool,
) -> None:
    pending = _record()
    failed = _record(status="failed_provider")
    preserved = [
        _record(status="sent"),
        _record(source_bid="other"),
        _record(notification_type="credit_granted"),
        _record(source_type="other"),
        _record(deleted=1),
    ]
    db.session.commit()
    statuses = [row.status for row in preserved]
    extended = now_utc() + timedelta(days=30)

    def suppress() -> None:
        assert (
            notifications.suppress_pending_expiring_notifications_for_bucket(
                notification_app,
                wallet_bucket_bid="bucket-1",
                effective_to=extended,
            )
            == 2
        )
        assert pending.status == failed.status == "skipped"
        if rollback:
            message = "renewal write failed"
            raise RuntimeError(message)

    if rollback:
        with pytest.raises(RuntimeError, match="renewal write failed"), unit_of_work():
            suppress()
    else:
        with unit_of_work():
            suppress()
    db.session.expire_all()
    assert [row.status for row in preserved] == statuses
    if rollback:
        assert pending.status == "pending"
        assert failed.status == "failed_provider"
        assert pending.attempted_at is None
    else:
        assert pending.error_code == failed.error_code == "expiry_extended"
        assert datetime.fromisoformat(
            pending.metadata_json["superseded_by_effective_to"]
        ) == extended.replace(microsecond=0)
        with unit_of_work():
            assert (
                notifications.suppress_pending_expiring_notifications_for_bucket(
                    notification_app, wallet_bucket_bid="bucket-1"
                )
                == 0
            )


def test_email_stage_persists_missing_contact_without_enqueuing(
    notification_app: Flask,
) -> None:
    _seed_creator(notification_app, creator_bid="teacher-1", mobile=None)
    with unit_of_work():
        result = notifications._stage_notification_record(
            notification_app,
            notification_type="credit_granted",
            creator_bid="teacher-1",
            source_type="credit_ledger",
            source_bid="ledger-1",
            dedupe_key="grant:ledger-1",
            template_params={"credits": "10"},
            policy={"enabled": True},
            rule={"channel": "email", "template_code": "EMAIL-1"},
        )
    record = NotificationRecord.query.one()
    assert result.status == record.status == "skipped"
    assert record.error_code == "missing_email"
    assert record.attempted_at is not None
    assert record.recipient_snapshot == ""
