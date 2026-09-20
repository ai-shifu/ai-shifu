"""Verify operator searches and attention thresholds against persisted records."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import read_models
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
)
from flaskr.service.billing.models import BillingDailyUsageMetric, BillingOrder
from flaskr.service.common.models import AppError
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)

from tests.common.fixtures.bill_products import build_billing_product
from tests.service.billing import test_admin_billing_routes as route_fixtures

admin_billing_client = route_fixtures.admin_billing_client


def _search_order() -> tuple:
    product = build_billing_product(
        "bill-product-plan-monthly",
        overrides={
            "product_bid": uuid4().hex,
            "product_code": "search-contract-product",
            "display_name_i18n_key": "test.product.localized",
            "price_amount": 9876,
            "credit_amount": Decimal("345.5"),
        },
    )
    order = BillingOrder(
        bill_order_bid=uuid4().hex,
        creator_bid="creator-1",
        product_bid=product.product_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        payment_provider="stripe",
        status=BILLING_ORDER_STATUS_PAID,
        payable_amount=9876,
        paid_amount=9876,
    )
    db.session.add_all([product, order])
    db.session.commit()
    return product, order


@pytest.mark.parametrize(
    ("keyword", "matches"),
    [
        ("search-contract-product", True),
        ("345.5", True),
        ("98.76", True),
        ("9,876", True),
        ("lesson package", True),
        ("课程积分包", True),
        ("crédits pédagogiques", True),
        ("NaN", False),
        ("Infinity", False),
        ("no-product-matches", False),
    ],
)
def test_operator_product_search_matches_code_numeric_price_credits_and_localized_name(
    keyword: str,
    matches: bool,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, order = _search_order()
    names = {
        "en-US": "Lesson package",
        "zh-CN": "课程积分包",
        "fr-FR": "Crédits pédagogiques",
    }

    def translate(key: str) -> str:
        return (
            names.get(read_models.get_current_language(), key)
            if key == "test.product.localized"
            else key
        )

    monkeypatch.setattr(read_models, "translate", translate)
    original_language = read_models.get_current_language()
    result = read_models.build_operator_credit_orders_page(
        admin_billing_client["app"],
        product_keyword=keyword,
        bill_order_bid=order.bill_order_bid,
    )
    assert result.total == int(matches)
    assert read_models.get_current_language() == original_language
    if matches:
        assert result.items[0].bill_order_bid == order.bill_order_bid


def test_localized_product_search_restores_language_when_translation_fails(
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _search_order()
    original_language = read_models.get_current_language()
    monkeypatch.setattr(
        read_models,
        "translate",
        Mock(side_effect=RuntimeError("translation unavailable")),
    )
    with pytest.raises(RuntimeError, match="translation unavailable"):
        read_models.build_operator_credit_orders_page(
            admin_billing_client["app"], product_keyword="translated name"
        )
    assert read_models.get_current_language() == original_language


@pytest.mark.parametrize("field", ["credit_order_kind", "status"])
def test_operator_search_rejects_unknown_filter_labels(
    field: str, admin_billing_client: dict
) -> None:
    with pytest.raises(AppError):
        read_models.build_operator_credit_orders_page(
            admin_billing_client["app"], **{field: "invalid"}
        )


@pytest.mark.parametrize("bid", ["", "missing"])
def test_operator_order_detail_distinguishes_invalid_or_missing_order(
    bid: str, admin_billing_client: dict
) -> None:
    with pytest.raises(AppError):
        read_models.get_operator_credit_order_detail(
            admin_billing_client["app"], bill_order_bid=bid
        )


@pytest.mark.parametrize(
    ("amount", "creator", "note"),
    [
        ("invalid", "creator-1", ""),
        (0, "creator-1", ""),
        (1, "", ""),
        (1, "creator-1", "x" * 256),
    ],
)
def test_manual_ledger_adjustment_rejects_invalid_request_before_any_balance_change(
    amount: object,
    creator: str,
    note: str,
    admin_billing_client: dict,
) -> None:
    with pytest.raises(AppError):
        read_models.adjust_admin_billing_ledger(
            admin_billing_client["app"],
            operator_user_bid="admin-test",
            payload={"creator_bid": creator, "amount": amount, "note": note},
        )


@pytest.mark.parametrize(
    ("current", "previous", "active_days", "scene", "expected"),
    [
        (
            "8",
            "0",
            1,
            BILL_USAGE_SCENE_DEBUG,
            {"high_consumption", "debug_preview_heavy", "rapid_growth"},
        ),
        ("8", "4", 1, BILL_USAGE_SCENE_PROD, {"high_consumption", "active_production"}),
        (
            "16",
            "8",
            1,
            BILL_USAGE_SCENE_PROD,
            {"high_consumption", "active_production", "rapid_growth"},
        ),
        ("3", "0", 3, BILL_USAGE_SCENE_DEBUG, {"sustained_activity"}),
        ("0", "0", 1, BILL_USAGE_SCENE_DEBUG, set()),
        ("1", "0", 1, BILL_USAGE_SCENE_PROD, set()),
    ],
)
def test_focus_teacher_attention_rules_use_current_and_previous_windows(
    current: str,
    previous: str,
    active_days: int,
    scene: int,
    expected: set,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = datetime(2026, 4, 6, 12)
    monkeypatch.setattr(read_models, "now_utc", lambda: clock)
    teacher = uuid4().hex
    rows = []
    for offset in range(active_days):
        day = clock - timedelta(days=offset)
        rows.append(
            BillingDailyUsageMetric(
                daily_usage_metric_bid=uuid4().hex,
                stat_date=day.date().isoformat(),
                creator_bid=teacher,
                shifu_bid="test-course",
                usage_scene=scene,
                usage_type=BILL_USAGE_TYPE_LLM,
                provider="test",
                model="test",
                billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                consumed_credits=Decimal(current) / active_days,
                record_count=1,
                window_started_at=day.replace(hour=0),
                window_ended_at=day + timedelta(days=1),
            )
        )
    previous_day = clock - timedelta(days=8)
    rows.append(
        BillingDailyUsageMetric(
            daily_usage_metric_bid=uuid4().hex,
            stat_date=previous_day.date().isoformat(),
            creator_bid=teacher,
            shifu_bid="test-course",
            usage_scene=scene,
            usage_type=BILL_USAGE_TYPE_LLM,
            provider="test",
            model="test",
            billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
            consumed_credits=Decimal(previous),
            record_count=1,
            window_started_at=previous_day.replace(hour=0),
            window_ended_at=previous_day + timedelta(days=1),
        )
    )
    db.session.add_all(rows)
    db.session.commit()
    result = read_models.build_admin_billing_focus_teachers_page(
        admin_billing_client["app"]
    )
    selected = [item for item in result.items if item.creator_bid == teacher]
    assert len(selected) == int(bool(expected))
    if expected:
        item = selected[0]
        assert set(item.attention_reasons) == expected
        assert item.credits_7d == Decimal(current)
        assert item.credits_30d == Decimal(current) + Decimal(previous)
        assert item.active_days_7d == active_days
        assert item.latest_usage_at == clock.replace(hour=0)
        assert item.production_ratio_30d == (1 if scene == BILL_USAGE_SCENE_PROD else 0)
