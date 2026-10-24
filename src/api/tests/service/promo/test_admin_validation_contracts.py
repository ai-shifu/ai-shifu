"""Protect promotion validation, time windows and immutable discount terms."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.promo import admin
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_ALL,
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
)
from flaskr.service.promo.models import Coupon, CouponUsage, PromoCampaign

from tests.service.promo.test_admin_promotions import (
    _isolate_tables as promotion_tables,
)

__all__ = ["promotion_tables"]


def _coupon_payload(**changes: object) -> dict:
    return {
        "name": "Coupon",
        "usage_type": COUPON_APPLY_TYPE_ALL,
        "discount_type": COUPON_TYPE_FIXED,
        "value": "10",
        "total_count": 5,
        "scope_type": "all_courses",
        "shifu_bid": "",
        "start_at": "2099-01-01",
        "end_at": "2099-12-31",
        "code": "TESTCOUPON",
        "enabled": False,
    } | changes


def _campaign_payload(**changes: object) -> dict:
    return {
        "name": "Campaign",
        "apply_type": PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
        "discount_type": COUPON_TYPE_FIXED,
        "value": "10",
        "shifu_bid": "course",
        "start_at": "2099-01-01",
        "end_at": "2099-12-31",
        "enabled": False,
    } | changes


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"usage_type": -1},
        {"usage_type": "invalid"},
        {"discount_type": -1},
        {"value": "bad"},
        {"value": "0"},
        {"value": "-1"},
        {"discount_type": COUPON_TYPE_PERCENT, "value": "101"},
        {"total_count": None},
        {"total_count": 0},
        {"total_count": "invalid"},
        {"scope_type": "unknown"},
        {"scope_type": "single_course", "shifu_bid": ""},
        {"end_at": "2098-01-01"},
        {"start_at": ""},
        {"start_at": "invalid"},
        {"enabled": "unknown"},
    ],
)
def test_invalid_coupon_creation_never_persists_batch_or_usage_rows(
    app: object, changes: dict
) -> None:
    with pytest.raises(AppError) as caught:
        admin.create_operator_promotion_coupon(
            app, "operator", _coupon_payload(**changes)
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    with app.app_context():
        assert Coupon.query.count() == 0
        assert CouponUsage.query.count() == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"apply_type": -1},
        {"shifu_bid": ""},
        {"discount_type": -1},
        {"discount_type": COUPON_TYPE_PERCENT, "value": "101"},
        {"end_at": "2098-01-01"},
        {"enabled": "unknown"},
    ],
)
def test_invalid_campaign_creation_leaves_no_audit_rows(
    app: object, changes: dict
) -> None:
    with pytest.raises(AppError) as caught:
        admin.create_operator_promotion_campaign(
            app, "operator", _campaign_payload(**changes)
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    with app.app_context():
        assert PromoCampaign.query.count() == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"usage_type": COUPON_APPLY_TYPE_SPECIFIC},
        {"discount_type": COUPON_TYPE_PERCENT},
        {"value": "11"},
        {"total_count": None},
        {"total_count": 0},
        {"scope_type": "unknown"},
        {"scope_type": "single_course", "shifu_bid": ""},
        {"scope_type": "single_course", "shifu_bid": "other"},
        {"end_at": "2098-01-01"},
        {"code": "REPLACED"},
    ],
)
def test_invalid_coupon_update_preserves_original_terms_and_operator(
    app: object, changes: dict
) -> None:
    bid = admin.create_operator_promotion_coupon(app, "original", _coupon_payload())[
        "coupon_bid"
    ]
    with pytest.raises(AppError) as caught:
        admin.update_operator_promotion_coupon(
            app, "replacement", bid, _coupon_payload(**changes)
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    with app.app_context():
        row = Coupon.query.filter_by(coupon_bid=bid).one()
        assert row.name == "Coupon"
        assert row.value == Decimal(10)
        assert row.code == "TESTCOUPON"
        assert row.total_count == 5
        assert row.updated_user_bid == "original"


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"apply_type": -1},
        {"shifu_bid": "other"},
        {"discount_type": COUPON_TYPE_PERCENT},
        {"value": "11"},
        {"end_at": "2098-01-01"},
        {"channel": "changed"},
    ],
)
def test_invalid_campaign_update_preserves_original_terms(
    app: object, changes: dict
) -> None:
    bid = admin.create_operator_promotion_campaign(
        app, "original", _campaign_payload()
    )["promo_bid"]
    with pytest.raises(AppError) as caught:
        admin.update_operator_promotion_campaign(
            app, "replacement", bid, _campaign_payload(**changes)
        )
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]
    with app.app_context():
        row = PromoCampaign.query.filter_by(promo_bid=bid).one()
        assert row.name == "Campaign"
        assert row.value == Decimal(10)
        assert row.updated_user_bid == "original"
        assert row.channel == ""


@pytest.mark.parametrize(
    ("value", "end", "expected"),
    [
        ("2026-09-20", False, datetime(2026, 9, 20)),
        ("2026-09-20", True, datetime(2026, 9, 20, 23, 59, 59)),
        ("2026-09-20T08:00:00+08:00", False, datetime(2026, 9, 20)),
        ("2026-09-20T00:00:00Z", False, datetime(2026, 9, 20)),
        ("2026-09-20 00:00", False, datetime(2026, 9, 20)),
    ],
)
def test_promotion_dates_normalize_to_naive_utc(
    value: str, end: bool, expected: datetime
) -> None:
    assert admin._parse_datetime(value, "date", is_end=end) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("1", True),
        ("false", False),
        ("0", False),
    ],
)
def test_promotion_boolean_form_values_have_explicit_meanings(
    value: object, expected: bool
) -> None:
    assert admin._parse_bool_value(value, "enabled") is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("invalid", ("all_courses", "")),
        ("[]", ("all_courses", "")),
        ('{"course_id":"lesson"}', ("single_course", "lesson")),
        ('{"course_id":""}', ("all_courses", "")),
    ],
)
def test_legacy_coupon_scope_preserves_known_course_and_tolerates_invalid_data(
    raw: str, expected: tuple
) -> None:
    assert admin._parse_coupon_scope(raw) == expected


@pytest.mark.parametrize("kind", ["coupon", "campaign"])
def test_status_filters_select_only_matching_utc_window_and_enabled_state(
    app: object, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    now = datetime(2026, 9, 20, 12)
    monkeypatch.setattr(admin, "now_utc", lambda: now)
    windows = {
        "active": ("2026-09-19", "2026-09-21", True),
        "not_started": ("2026-09-21", "2026-09-22", True),
        "expired" if kind == "coupon" else "ended": ("2026-09-18", "2026-09-19", True),
        "inactive": ("2026-09-19", "2026-09-21", False),
    }
    for index, (name, (start, end, enabled)) in enumerate(windows.items()):
        if kind == "coupon":
            admin.create_operator_promotion_coupon(
                app,
                "operator",
                _coupon_payload(
                    name=name,
                    start_at=start,
                    end_at=end,
                    enabled=enabled,
                    code=f"CODE{index}",
                ),
            )
        else:
            admin.create_operator_promotion_campaign(
                app,
                "operator",
                _campaign_payload(
                    name=name,
                    start_at=start,
                    end_at=end,
                    enabled=enabled,
                    shifu_bid=f"course-{index}",
                ),
            )
    model = Coupon if kind == "coupon" else PromoCampaign
    build = (
        admin._build_coupon_status_filter
        if kind == "coupon"
        else admin._build_campaign_status_filter
    )
    with app.app_context():
        for name in windows:
            assert [row.name for row in model.query.filter(build(name)).all()] == [name]
        assert build("") is None


def test_coupon_code_generation_retries_collisions_across_batch_and_usage(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin.create_operator_promotion_coupon(app, "operator", _coupon_payload())
    with app.app_context():
        db.session.add(
            CouponUsage(
                coupon_usage_bid="used", coupon_bid="batch", code="USED", name="Used"
            )
        )
        db.session.commit()
        generate = Mock(side_effect=["TESTCOUPON", "USED", "UNIQUE"])
        monkeypatch.setattr(admin, "_generate_random_coupon_code", generate)
        assert admin._generate_unique_coupon_code() == "UNIQUE"
        assert generate.call_count == 3
        assert admin._generate_unique_coupon_codes(0) == []


def test_coupon_code_exhaustion_has_bounded_attempts_and_no_partial_rows(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin.create_operator_promotion_coupon(app, "operator", _coupon_payload())
    generate = Mock(return_value="TESTCOUPON")
    monkeypatch.setattr(admin, "_generate_random_coupon_code", generate)
    with app.app_context():
        with pytest.raises(AppError) as caught:
            admin._generate_unique_coupon_code()
        assert (
            caught.value.code
            == ERROR_CODE["server.discount.couponCodeGenerationFailed"]
        )
        assert generate.call_count == 20
        assert Coupon.query.count() == 1
        assert CouponUsage.query.count() == 0
