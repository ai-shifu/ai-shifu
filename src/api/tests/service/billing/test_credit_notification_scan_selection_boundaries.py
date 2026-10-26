"""Verify scan filtering, previews, deduplication, and incomplete grant references."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing import credit_notifications as notifications
from flaskr.service.billing.models import NotificationRecord

from tests.service.billing.test_credit_notifications import (
    _enable_policy,
    _seed_bucket,
    _seed_creator,
    _seed_daily_consumption,
    _seed_wallet,
)
from tests.service.billing.test_credit_notifications import (
    credit_notifications_app as scan_app,
)

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["scan_app"]

SCAN_TIME = datetime(2026, 5, 10, 12)


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> Mock:
    task = Mock()
    monkeypatch.setattr(
        "flaskr.common.celery_app.get_celery_app",
        lambda **_kwargs: SimpleNamespace(tasks={notifications.TASK_NAME: task}),
    )
    return task


def _set_expiring_rule(app: Flask, *, merge: bool) -> None:
    _enable_policy(app)
    policy = notifications.load_credit_notification_policy()
    rule = next(
        rule for rule in policy["rules"] if rule["trigger_event"] == "credit_expiring"
    )
    rule["conditions"] = {"windows": ["1d"], "merge_same_creator": merge}
    notifications.save_credit_notification_policy(app, policy)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("creator_filter", ["", "teacher-a"])
def test_unmerged_expiry_scan_selects_each_eligible_bucket_and_filters_creator(
    scan_app: Flask, broker: Mock, dry_run: bool, creator_filter: str
) -> None:
    _set_expiring_rule(scan_app, merge=False)
    for creator, mobile, is_creator in [
        ("teacher-a", "13800000001", True),
        ("teacher-b", "13800000002", True),
        ("learner", "13800000003", False),
    ]:
        _seed_creator(
            scan_app, creator_bid=creator, mobile=mobile, is_creator=is_creator
        )
        _seed_bucket(
            creator_bid=creator, effective_to=SCAN_TIME + timedelta(days=1, hours=2)
        )
    _seed_bucket(
        creator_bid="teacher-a",
        wallet_bucket_bid="second-a",
        effective_to=SCAN_TIME + timedelta(days=1, hours=3),
    )
    db.session.commit()
    result = notifications.scan_credit_expiring_notifications(
        scan_app, now=SCAN_TIME, creator_bid=creator_filter, dry_run=dry_run
    )
    expected = 2 if creator_filter else 3
    assert result["candidate_count"] == expected
    assert result["created_count"] == (0 if dry_run else expected)
    assert {item["source_bid"] for item in result["notifications"]} == (
        {"bucket-teacher-a", "second-a"}
        | (set() if creator_filter else {"bucket-teacher-b"})
    )
    assert NotificationRecord.query.count() == (0 if dry_run else expected)
    assert broker.apply_async.call_count == (0 if dry_run else expected)
    if not dry_run:
        again = notifications.scan_credit_expiring_notifications(
            scan_app, now=SCAN_TIME, creator_bid=creator_filter
        )
        assert again["created_count"] == 0
        assert NotificationRecord.query.count() == expected
        assert {item["status"] for item in again["notifications"]} == {
            "suppressed_duplicate"
        }


def test_merged_expiry_preview_does_not_write_and_subsequent_scan_is_idempotent(
    scan_app: Flask, broker: Mock
) -> None:
    _set_expiring_rule(scan_app, merge=True)
    _seed_creator(scan_app)
    for index in range(2):
        _seed_bucket(
            wallet_bucket_bid=f"bucket-{index}",
            effective_to=SCAN_TIME + timedelta(days=1, hours=index + 1),
        )
    db.session.commit()
    preview = notifications.scan_credit_expiring_notifications(
        scan_app, now=SCAN_TIME, dry_run=True
    )
    assert preview["candidate_count"] == 1
    assert preview["notifications"][0]["status"] == "candidate"
    assert NotificationRecord.query.count() == 0
    broker.apply_async.assert_not_called()
    notifications.scan_credit_expiring_notifications(scan_app, now=SCAN_TIME)
    record = NotificationRecord.query.one()
    # Daily deduplication is based on requested_at, independently of the bucket expiry.
    record.requested_at = SCAN_TIME
    db.session.commit()
    replay = notifications.scan_credit_expiring_notifications(scan_app, now=SCAN_TIME)
    assert replay["created_count"] == 0
    assert replay["notifications"][0]["status"] == "suppressed_duplicate"
    assert NotificationRecord.query.count() == 1


@pytest.mark.parametrize(
    ("available", "days", "fallback", "dry_run", "expected_reason"),
    [
        ("4", 1, "3", True, "insufficient_consumed_days_fallback_not_reached"),
        ("4", 1, None, True, "insufficient_consumed_days"),
        ("4", 1, "3", False, None),
        ("4", 1, None, False, None),
        ("30", 2, None, False, None),
    ],
)
def test_estimated_balance_scan_explains_insufficient_history_without_queuing(
    scan_app: Flask,
    broker: Mock,
    available: str,
    days: int,
    fallback: str | None,
    dry_run: bool,
    expected_reason: str | None,
) -> None:
    threshold = {
        "kind": "estimated_days",
        "days": 3,
        "lookback_days": 7,
        "min_consumed_days": 2,
    }
    if fallback is not None:
        threshold["fallback_fixed_value"] = fallback
    _enable_policy(scan_app, low_balance_thresholds=[threshold])
    _seed_creator(scan_app)
    _seed_wallet(available_credits=available)
    for index in range(days):
        _seed_daily_consumption(stat_date=f"2026-05-0{9 - index}", amount="7")
    db.session.commit()
    result = notifications.scan_low_balance_notifications(
        scan_app, now=SCAN_TIME, creator_bid="creator-1", dry_run=dry_run
    )
    assert result["created_count"] == result["candidate_count"] == 0
    if expected_reason:
        assert result["notifications"][0]["reason"] == expected_reason
    else:
        assert result["notifications"] == []
    assert NotificationRecord.query.count() == 0
    broker.apply_async.assert_not_called()


@pytest.mark.parametrize(
    ("available", "expected_count"), [("2", 1), ("4", 0), ("0", 0)]
)
def test_fixed_balance_preview_respects_threshold_and_zero_balance_gate(
    scan_app: Flask, broker: Mock, available: str, expected_count: int
) -> None:
    _enable_policy(scan_app)
    _seed_creator(scan_app)
    _seed_wallet(available_credits=available)
    db.session.commit()
    result = notifications.scan_low_balance_notifications(
        scan_app, now=SCAN_TIME, dry_run=True
    )
    assert result["candidate_count"] == expected_count
    assert result["created_count"] == 0
    if expected_count:
        assert result["notifications"][0]["available_credits"] == "2.00"
    assert NotificationRecord.query.count() == 0
    broker.apply_async.assert_not_called()


@pytest.mark.parametrize("kind", ["credit_expiring", "low_balance"])
def test_disabled_scanner_does_not_create_notifications(
    scan_app: Flask, broker: Mock, kind: str
) -> None:
    notifications.save_credit_notification_policy(
        scan_app, {"enabled": False, "rules": []}
    )
    result = getattr(notifications, f"scan_{kind}_notifications")(
        scan_app, now=SCAN_TIME
    )
    assert result["status"] == "noop_disabled"
    assert result["notifications"] == []
    assert NotificationRecord.query.count() == 0
    broker.apply_async.assert_not_called()


@pytest.mark.parametrize("source", ["ledger", "order"])
@pytest.mark.parametrize("source_bid", [" ", "missing"])
def test_missing_grant_reference_cannot_stage_notification(
    scan_app: Flask, source: str, source_bid: str
) -> None:
    _enable_policy(scan_app)
    if source == "ledger":
        result = notifications.stage_credit_granted_notification(
            scan_app, ledger_bid=source_bid
        )
        invalid = "invalid_ledger_bid"
    else:
        result = notifications.stage_credit_granted_notification_for_order(
            scan_app, creator_bid="creator-1", bill_order_bid=source_bid
        )
        invalid = "invalid_order"
    assert result["status"] == ("not_found" if source_bid.strip() else invalid)
    assert NotificationRecord.query.count() == 0


@pytest.mark.parametrize("stage", ["missing_identity", "disabled", "enabled"])
def test_direct_staging_resolves_current_rule_before_persisting(
    scan_app: Flask, stage: str
) -> None:
    _enable_policy(scan_app)
    _seed_creator(scan_app)
    if stage == "disabled":
        notifications.save_credit_notification_policy(
            scan_app, {"enabled": False, "rules": []}
        )
    result = notifications._stage_notification_record(
        scan_app,
        notification_type="credit_granted",
        creator_bid=" " if stage == "missing_identity" else "creator-1",
        source_type="ledger",
        source_bid="ledger-direct",
        dedupe_key="grant-direct",
        template_params={
            "credits": "3",
            "source": "manual",
            "expires_at": "2026-05-20",
        },
    )
    assert (
        result.status
        == {
            "missing_identity": "invalid",
            "disabled": "noop_disabled",
            "enabled": "pending",
        }[stage]
    )
    assert NotificationRecord.query.count() == int(stage == "enabled")
