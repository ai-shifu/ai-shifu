"""Cover malformed persisted policies and operator input boundary conditions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.billing import credit_notifications as notifications
from flaskr.service.common.models import AppError


def _rule(**changes: object) -> dict:
    return {
        "rule_bid": "rule-test",
        "name": "Credit reminder",
        "trigger_event": "credit_granted",
        "channel": "sms",
        "template_code": "template-test",
        "enabled": True,
    } | changes


@pytest.mark.parametrize(
    "rules",
    [
        {},
        [None],
        [_rule(trigger_event="unknown")],
        [_rule(name="")],
        [_rule(name="x" * 129)],
        [_rule(rule_bid="x" * 65)],
        [_rule(channel="push")],
        [_rule(template_code="")],
        [_rule(channel="email", locale_template_codes="invalid")],
        [_rule(channel="email", locale_template_codes={"": "template"})],
        [_rule(channel="email", locale_template_codes={"x" * 31: "template"})],
        [_rule(channel="email", locale_template_codes={"en-US": "template"})],
        [_rule(trigger_event="credit_expiring", conditions={"windows": []})],
        [_rule(trigger_event="credit_expiring", conditions={"windows": ["tomorrow"]})],
        [_rule(trigger_event="low_balance", conditions={"thresholds": []})],
        [_rule(), _rule()],
    ],
)
def test_notification_rule_rejects_invalid_operator_input(rules: object) -> None:
    with pytest.raises(AppError):
        notifications._normalize_notification_rules(Flask(__name__), rules)


def test_notification_rule_normalizes_localized_email_and_legacy_expiration() -> None:
    rules = notifications._normalize_notification_rules(
        Flask(__name__),
        [
            _rule(
                rule_bid=" localized ",
                name=" Localized reminder ",
                channel="email",
                locale_template_codes={" zh-CN ": " template-zh "},
            ),
            _rule(
                rule_bid="legacy-credit_expiring",
                legacy=True,
                trigger_event="credit_expiring",
                conditions={"windows": [], "merge_same_creator": "off"},
            ),
        ],
    )
    assert rules[0]["rule_bid"] == "localized"
    assert rules[0]["name"] == "Localized reminder"
    assert rules[0]["locale_template_codes"] == {"zh-CN": "template-zh"}
    assert rules[1]["legacy"] is True
    assert rules[1]["conditions"] == {"windows": [], "merge_same_creator": False}


@pytest.mark.parametrize(
    "payload",
    [
        {"types": []},
        {"blacklist": {"creator_bids": "not-a-list"}},
        {"quiet_hours": {"start": "22"}},
        {"quiet_hours": {"start": "aa:bb"}},
        {"quiet_hours": {"start": "24:00"}},
        {"quiet_hours": {"end": "12:60"}},
        {"softlimit": {"threshold": {"kind": "estimated_days", "value": "1"}}},
        {"softlimit": {"threshold": {"value": "NaN"}}},
        {
            "enabled": True,
            "types": {"credit_granted": {"enabled": True, "template_code": ""}},
        },
        {"types": {"low_balance": {"thresholds": "invalid"}}},
        {"types": {"low_balance": {"thresholds": [None]}}},
        {
            "types": {
                "low_balance": {
                    "thresholds": [
                        {
                            "kind": "estimated_days",
                            "days": "invalid",
                            "lookback_days": 7,
                            "min_consumed_days": 1,
                        }
                    ]
                }
            }
        },
        {"types": {"low_balance": {"thresholds": [{"kind": "unknown"}]}}},
    ],
)
def test_policy_validation_rejects_invalid_threshold_and_quiet_hour_contracts(
    payload: dict,
) -> None:
    with pytest.raises(AppError):
        notifications._validate_policy_for_save(Flask(__name__), payload)


def test_policy_normalization_tolerates_bad_optional_budget_and_preserves_defaults() -> (
    None
):
    defaults = json.dumps(
        notifications.DEFAULT_CREDIT_NOTIFICATION_SMS_CONFIG, sort_keys=True
    )
    normalized = notifications._validate_policy_for_save(
        Flask(__name__),
        {
            "enabled": 0,
            "frequency": {
                "per_mobile_per_day": "invalid",
                "per_creator_per_type_per_day": -10,
            },
            "budget": {"daily_sms_limit": None, "sms_unit_cost": "invalid"},
            "quiet_hours": {"start": "9:5", "end": "10:1"},
        },
    )
    assert normalized["enabled"] is False
    assert normalized["frequency"] == {
        "per_mobile_per_day": 0,
        "per_creator_per_type_per_day": 0,
    }
    assert normalized["budget"]["daily_sms_limit"] == 0
    assert Decimal(normalized["budget"]["sms_unit_cost"]) == 0
    assert normalized["quiet_hours"]["start"] == "09:05"
    assert normalized["quiet_hours"]["end"] == "10:01"
    assert (
        json.dumps(notifications.DEFAULT_CREDIT_NOTIFICATION_SMS_CONFIG, sort_keys=True)
        == defaults
    )


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        '{"channel":"unknown","types":[]}',
        '{"types":{"credit_granted":null}}',
        None,
    ],
)
def test_malformed_stored_policy_degrades_to_safe_disabled_defaults(
    raw: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notifications, "get_config", Mock(return_value=raw))
    policy = notifications.load_credit_notification_policy()
    assert policy["enabled"] is False
    assert policy["channel"] == "sms"
    assert isinstance(policy["rules"], list)
    for notification_type in ["credit_granted", "credit_expiring", "low_balance"]:
        assert isinstance(policy["types"][notification_type], dict)
        assert isinstance(policy["types"][notification_type]["enabled"], bool)


def test_missing_stored_policy_config_uses_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notifications, "get_config", Mock(side_effect=KeyError("unconfigured"))
    )
    assert notifications.load_credit_notification_policy()["enabled"] is False


def _email_template(**changes: object) -> dict:
    return {
        "template_code": "email-test",
        "template_name": "Reminder",
        "email_subject": "You have ${credits} credits",
        "email_html_body": "<p>Your ${credits} credits expire ${expires_at}.</p>",
        "template_status": "draft",
    } | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"template_code": "x" * 129},
        {"template_name": ""},
        {"template_name": "x" * 256},
        {"locale": "x" * 17},
        {"email_subject": "x" * 256},
        {"email_html_body": "x" * 100001},
        {"email_html_body": "<script>hidden only</script>"},
        {"template_status": "unknown"},
        {"applicable_notification_types": ["unknown"]},
        {"applicable_notification_types": ["low_balance"]},
        {"template_status": "active", "applicable_notification_types": []},
    ],
)
def test_email_templates_reject_invalid_content_and_incompatible_events(
    changes: dict,
) -> None:
    with pytest.raises(AppError):
        notifications._normalize_email_template_payload(_email_template(**changes))


def test_email_template_normalization_removes_executable_text_and_deduplicates_events() -> (
    None
):
    template = notifications._normalize_email_template_payload(
        _email_template(
            email_html_body="<head><title>Hidden title</title></head><style>.x{}</style><script>hidden()</script><p>${credits} &amp; more</p><div>Expires ${expires_at}</div>",
            applicable_notification_types="credit_granted,credit_expiring,credit_granted",
        )
    )
    assert template["template_content"] == "${credits} & more\nExpires ${expires_at}"
    assert template["placeholders"] == ["credits", "expires_at"]
    assert template["applicable_notification_types"] == [
        "credit_granted",
        "credit_expiring",
    ]


def test_legacy_threshold_loader_ignores_bad_entries_and_retains_usable_thresholds() -> (
    None
):
    thresholds = notifications._load_low_balance_thresholds(
        {
            "types": {
                "low_balance": {
                    "thresholds": [
                        None,
                        {"kind": "unsupported"},
                        {"kind": "fixed", "value": "invalid"},
                        {
                            "kind": "estimated_days",
                            "days": 0,
                            "lookback_days": 7,
                            "min_consumed_days": 1,
                        },
                        {
                            "kind": "estimated_days",
                            "days": 3,
                            "lookback_days": 7,
                            "min_consumed_days": 2,
                            "fallback_fixed_value": "12.5",
                        },
                        {
                            "kind": "estimated_days",
                            "days": 2,
                            "lookback_days": 5,
                            "min_consumed_days": 1,
                        },
                    ]
                }
            }
        }
    )
    assert len(thresholds) == 3
    assert thresholds[0]["kind"] == "fixed"
    assert Decimal(thresholds[0]["value"]) == 0
    assert thresholds[1] | {"fallback_fixed_value": "12.5"} == {
        "kind": "estimated_days",
        "days": 3,
        "lookback_days": 7,
        "min_consumed_days": 2,
        "fallback_fixed_value": "12.5",
    }
    assert Decimal(thresholds[1]["fallback_fixed_value"]) == Decimal("12.5")
    assert "fallback_fixed_value" not in thresholds[2]


@pytest.mark.parametrize("thresholds", [None, [], [None], [{"kind": "unsupported"}]])
def test_no_usable_legacy_thresholds_falls_back_to_zero_balance(
    thresholds: object,
) -> None:
    result = notifications._load_low_balance_thresholds(
        {"types": {"low_balance": {"thresholds": thresholds}}}
    )
    assert len(result) == 1
    assert result[0]["kind"] == "fixed"
    assert Decimal(result[0]["value"]) == 0


@pytest.mark.parametrize(
    ("start", "end", "hour", "expected"),
    [
        ("9:00", "17:00", 9, True),
        ("9:00", "17:00", 17, False),
        ("22:00", "6:00", 23, True),
        ("22:00", "6:00", 6, False),
        ("invalid", "6:00", 23, False),
    ],
)
def test_quiet_hours_respects_boundaries_even_with_invalid_timezone(
    start: str, end: str, hour: int, expected: bool
) -> None:
    policy = {
        "quiet_hours": {
            "enabled": True,
            "start": start,
            "end": end,
            "timezone": "Invalid/Timezone",
        }
    }
    assert notifications._is_quiet_hours(policy, datetime(2026, 1, 1, hour)) is expected


def test_quiet_hours_converts_aware_utc_time_to_policy_timezone() -> None:
    policy = {
        "quiet_hours": {
            "enabled": True,
            "start": "22:00",
            "end": "6:00",
            "timezone": "Asia/Shanghai",
        }
    }
    assert (
        notifications._is_quiet_hours(policy, datetime(2026, 1, 1, 15, tzinfo=UTC))
        is True
    )


@pytest.mark.parametrize(
    "notification_type", ["credit_expiring", "low_balance", "credit_granted", ""]
)
def test_dry_run_selects_requested_scans_and_aggregates_without_delivery(
    notification_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    expiring = Mock(
        return_value={
            "candidate_count": 2,
            "estimated_sms_cost": "0.12",
            "notifications": [{"source_bid": "bucket-test"}],
        }
    )
    low = Mock(
        return_value={
            "candidate_count": 1,
            "estimated_sms_cost": "0.06",
            "notifications": [{"source_bid": "wallet-test"}],
        }
    )
    monkeypatch.setattr(notifications, "scan_credit_expiring_notifications", expiring)
    monkeypatch.setattr(notifications, "scan_low_balance_notifications", low)
    result = notifications.dry_run_credit_notifications(
        Flask(__name__), notification_type=notification_type, creator_bid="creator-test"
    )
    if notification_type == "credit_granted":
        assert result["status"] == "event_trigger_only"
        assert result["candidate_count"] == 0
        expiring.assert_not_called()
        low.assert_not_called()
    elif notification_type == "credit_expiring":
        assert result["candidate_count"] == 2
        low.assert_not_called()
    elif notification_type == "low_balance":
        assert result["candidate_count"] == 1
        expiring.assert_not_called()
    else:
        assert result["candidate_count"] == 3
        assert Decimal(result["estimated_sms_cost"]) == Decimal("0.18")
        assert result["created_count"] == 0
        assert result["dry_run"] is True
        assert len(result["notifications"]) == 2
    for scanner in [expiring, low]:
        if scanner.called:
            assert scanner.call_args.kwargs == {
                "creator_bid": "creator-test",
                "dry_run": True,
            }
