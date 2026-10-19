"""Local admin-billing sample data seeded by the billing Flask CLI."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import click
from flask import current_app
from flaskr.dao.uow import unit_of_work
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import (
    create_user_entity,
    get_user_entity_by_bid,
    mark_user_roles,
    update_user_entity_fields,
    upsert_credential,
)

from .cli_support import _upsert_bootstrap_rows
from .consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from .models import (
    BillingDailyUsageMetric,
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
)

if TYPE_CHECKING:
    from types import ModuleType

_SAMPLE_EXCEPTION_SEED_METADATA = {"seed_source": "sample_exception_orders"}

_SAMPLE_EXCEPTION_CREATOR_SPECS = (
    {
        "user_bid": "billing-debug-creator-failed",
        "identify": "13900001001",
        "mobile": "13900001001",
        "nickname": "Teacher Failed",
    },
    {
        "user_bid": "billing-debug-creator-pending",
        "identify": "13900001002",
        "mobile": "13900001002",
        "nickname": "Teacher Pending",
    },
    {
        "user_bid": "billing-debug-creator-timeout",
        "identify": "13900001003",
        "mobile": "13900001003",
        "nickname": "",
    },
)

_FOCUS_TEACHER_CREATOR_SPECS = (
    {
        "user_bid": "billing-focus-creator-growth",
        "identify": "13900002001",
        "mobile": "13900002001",
        "nickname": "增长很快老师",
    },
    {
        "user_bid": "billing-focus-creator-debug",
        "identify": "13900002002",
        "mobile": "13900002002",
        "nickname": "调试偏高老师",
    },
    {
        "user_bid": "billing-focus-creator-steady",
        "identify": "13900002003",
        "mobile": "13900002003",
        "nickname": "稳定使用老师",
    },
    {
        "user_bid": "billing-focus-creator-recent",
        "identify": "13900002004",
        "mobile": "13900002004",
        "nickname": "近期活跃老师",
    },
)

# (bid, stat_days_ago, creator_bid, shifu_bid, usage_scene, metric,
#  credit_amount, record_count, raw_amount), in insertion order.
_FOCUS_TEACHER_METRIC_SPECS = (
    (
        "billing-focus-growth-current-1",
        1,
        "billing-focus-creator-growth",
        "billing-focus-shifu-growth",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "4.2",
        3,
        3200,
    ),
    (
        "billing-focus-growth-current-2",
        3,
        "billing-focus-creator-growth",
        "billing-focus-shifu-growth",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_INPUT_TOKENS,
        "5.4",
        2,
        4100,
    ),
    (
        "billing-focus-growth-current-3",
        5,
        "billing-focus-creator-growth",
        "billing-focus-shifu-growth",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "3.8",
        2,
        2800,
    ),
    (
        "billing-focus-growth-prev-1",
        10,
        "billing-focus-creator-growth",
        "billing-focus-shifu-growth",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "1.4",
        1,
        1000,
    ),
    (
        "billing-focus-debug-current-1",
        0,
        "billing-focus-creator-debug",
        "billing-focus-shifu-debug",
        BILL_USAGE_SCENE_DEBUG,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "3.6",
        2,
        2600,
    ),
    (
        "billing-focus-debug-current-2",
        2,
        "billing-focus-creator-debug",
        "billing-focus-shifu-debug",
        BILL_USAGE_SCENE_PREVIEW,
        BILLING_METRIC_LLM_INPUT_TOKENS,
        "3.1",
        2,
        2200,
    ),
    (
        "billing-focus-debug-current-3",
        6,
        "billing-focus-creator-debug",
        "billing-focus-shifu-debug",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "1.6",
        2,
        1400,
    ),
    (
        "billing-focus-debug-30d-1",
        12,
        "billing-focus-creator-debug",
        "billing-focus-shifu-debug",
        BILL_USAGE_SCENE_DEBUG,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "2.4",
        1,
        1800,
    ),
    (
        "billing-focus-steady-current-1",
        1,
        "billing-focus-creator-steady",
        "billing-focus-shifu-steady",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "2.8",
        1,
        1900,
    ),
    (
        "billing-focus-steady-current-2",
        3,
        "billing-focus-creator-steady",
        "billing-focus-shifu-steady",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_INPUT_TOKENS,
        "2.7",
        2,
        2000,
    ),
    (
        "billing-focus-steady-current-3",
        6,
        "billing-focus-creator-steady",
        "billing-focus-shifu-steady",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "3.4",
        2,
        2500,
    ),
    (
        "billing-focus-recent-current-1",
        0,
        "billing-focus-creator-recent",
        "billing-focus-shifu-recent",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "4.6",
        2,
        3300,
    ),
    (
        "billing-focus-recent-current-2",
        4,
        "billing-focus-creator-recent",
        "billing-focus-shifu-recent",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_INPUT_TOKENS,
        "3.7",
        2,
        2600,
    ),
    (
        "billing-focus-recent-prev-1",
        9,
        "billing-focus-creator-recent",
        "billing-focus-shifu-recent",
        BILL_USAGE_SCENE_PROD,
        BILLING_METRIC_LLM_OUTPUT_TOKENS,
        "0.8",
        1,
        700,
    ),
)


def _cli_facade() -> ModuleType:
    """Resolve collaborators through ``cli`` so its patch points stay live."""
    from . import cli

    return cli


def seed_sample_exception_orders() -> dict[str, object]:
    """Seed sample exception orders."""
    current_time = _cli_facade().now_utc().replace(microsecond=0)
    plan_product_bid = _load_first_active_product_bid(BILLING_PRODUCT_TYPE_PLAN)
    topup_product_bid = _load_first_active_product_bid(BILLING_PRODUCT_TYPE_TOPUP)

    if not plan_product_bid or not topup_product_bid:
        message = (
            "Active billing plan/topup products are required before seeding "
            "sample exception orders."
        )
        raise click.ClickException(message)

    creator_specs = _SAMPLE_EXCEPTION_CREATOR_SPECS

    creator_inserted = 0
    creator_updated = 0
    for creator_spec in creator_specs:
        if _upsert_sample_exception_creator(
            user_bid=creator_spec["user_bid"],
            identify=creator_spec["identify"],
            mobile=creator_spec["mobile"],
            nickname=creator_spec["nickname"],
        ):
            creator_inserted += 1
        else:
            creator_updated += 1

    subscription_result = _upsert_bootstrap_rows(
        model=BillingSubscription,
        key_field="subscription_bid",
        rows=_sample_exception_subscription_rows(
            plan_product_bid=plan_product_bid,
            current_time=current_time,
        ),
    )
    renewal_result = _upsert_bootstrap_rows(
        model=BillingRenewalEvent,
        key_field="renewal_event_bid",
        rows=_sample_exception_renewal_rows(current_time=current_time),
    )

    order_result = _upsert_bootstrap_rows(
        model=BillingOrder,
        key_field="bill_order_bid",
        rows=_sample_exception_order_rows(
            plan_product_bid=plan_product_bid,
            topup_product_bid=topup_product_bid,
            current_time=current_time,
        ),
    )
    with unit_of_work():
        pass
    return {
        "status": "seeded",
        "creators": {
            "count": len(creator_specs),
            "inserted": creator_inserted,
            "updated": creator_updated,
        },
        "subscriptions": subscription_result,
        "renewal_events": renewal_result,
        "orders": order_result,
        "order_bids": [
            "billing-debug-order-failed",
            "billing-debug-order-pending",
            "billing-debug-order-timeout",
        ],
    }


def _sample_exception_subscription_row(
    *,
    subscription_bid: str,
    creator_bid: str,
    product_bid: str,
    status: int,
    billing_provider: str,
    provider_customer_id: str,
    grace_period_end_at: datetime | None,
    cancel_at_period_end: int,
    last_failed_at: datetime | None,
    current_time: datetime,
) -> dict[str, Any]:
    return {
        "subscription_bid": subscription_bid,
        "creator_bid": creator_bid,
        "product_bid": product_bid,
        "status": status,
        "billing_provider": billing_provider,
        "provider_subscription_id": f"{subscription_bid}-ref",
        "provider_customer_id": provider_customer_id,
        "billing_anchor_at": current_time,
        "current_period_start_at": current_time,
        "current_period_end_at": current_time,
        "grace_period_end_at": grace_period_end_at,
        "cancel_at_period_end": cancel_at_period_end,
        "next_product_bid": "",
        "last_renewed_at": current_time,
        "last_failed_at": last_failed_at,
        "metadata_json": dict(_SAMPLE_EXCEPTION_SEED_METADATA),
        "deleted": 0,
        "created_at": current_time,
        "updated_at": current_time,
    }


def _sample_exception_subscription_rows(
    *, plan_product_bid: str, current_time: datetime
) -> list[dict[str, Any]]:
    return [
        _sample_exception_subscription_row(
            subscription_bid="billing-debug-subscription-failed",
            creator_bid="billing-debug-creator-failed",
            product_bid=plan_product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
            billing_provider="stripe",
            provider_customer_id="billing-debug-customer-failed",
            grace_period_end_at=current_time,
            cancel_at_period_end=0,
            last_failed_at=current_time,
            current_time=current_time,
        ),
        _sample_exception_subscription_row(
            subscription_bid="billing-debug-subscription-pending",
            creator_bid="billing-debug-creator-pending",
            product_bid=plan_product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            billing_provider="pingxx",
            provider_customer_id="billing-debug-customer-pending",
            grace_period_end_at=None,
            cancel_at_period_end=1,
            last_failed_at=None,
            current_time=current_time,
        ),
        _sample_exception_subscription_row(
            subscription_bid="billing-debug-subscription-paused",
            creator_bid="billing-debug-creator-timeout",
            product_bid=plan_product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_PAUSED,
            billing_provider="manual",
            provider_customer_id="billing-debug-customer-timeout",
            grace_period_end_at=None,
            cancel_at_period_end=0,
            last_failed_at=None,
            current_time=current_time,
        ),
    ]


def _sample_exception_renewal_row(
    *,
    renewal_event_bid: str,
    subscription_bid: str,
    creator_bid: str,
    status: int,
    attempt_count: int,
    last_error: str,
    bill_order_bid: str,
    processed_at: datetime | None,
    current_time: datetime,
) -> dict[str, Any]:
    return {
        "renewal_event_bid": renewal_event_bid,
        "subscription_bid": subscription_bid,
        "creator_bid": creator_bid,
        "event_type": BILLING_RENEWAL_EVENT_TYPE_RETRY,
        "scheduled_at": current_time,
        "status": status,
        "attempt_count": attempt_count,
        "last_error": last_error,
        "payload_json": {"bill_order_bid": bill_order_bid},
        "processed_at": processed_at,
        "deleted": 0,
        "created_at": current_time,
        "updated_at": current_time,
    }


def _sample_exception_renewal_rows(*, current_time: datetime) -> list[dict[str, Any]]:
    return [
        _sample_exception_renewal_row(
            renewal_event_bid="billing-debug-renewal-failed",
            subscription_bid="billing-debug-subscription-failed",
            creator_bid="billing-debug-creator-failed",
            status=BILLING_RENEWAL_EVENT_STATUS_FAILED,
            attempt_count=2,
            last_error="card_declined",
            bill_order_bid="billing-debug-order-failed",
            processed_at=current_time,
            current_time=current_time,
        ),
        _sample_exception_renewal_row(
            renewal_event_bid="billing-debug-renewal-pending",
            subscription_bid="billing-debug-subscription-pending",
            creator_bid="billing-debug-creator-pending",
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=1,
            last_error="",
            bill_order_bid="billing-debug-order-pending",
            processed_at=None,
            current_time=current_time,
        ),
    ]


def _sample_exception_order_row(
    *,
    bill_order_bid: str,
    creator_bid: str,
    order_type: int,
    product_bid: str,
    subscription_bid: str,
    payable_amount: int,
    payment_provider: str,
    channel: str,
    status: int,
    failed_at: datetime | None,
    expires_at: datetime | None,
    failure_code: str,
    failure_message: str,
    current_time: datetime,
) -> dict[str, Any]:
    return {
        "bill_order_bid": bill_order_bid,
        "creator_bid": creator_bid,
        "order_type": order_type,
        "product_bid": product_bid,
        "subscription_bid": subscription_bid,
        "currency": "CNY",
        "payable_amount": payable_amount,
        "paid_amount": 0,
        "payment_provider": payment_provider,
        "channel": channel,
        "provider_reference_id": f"{bill_order_bid}-ref",
        "status": status,
        "paid_at": None,
        "failed_at": failed_at,
        "refunded_at": None,
        "expires_at": expires_at,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "metadata_json": dict(_SAMPLE_EXCEPTION_SEED_METADATA),
        "campaign_bid": "",
        "campaign_benefit_type": 0,
        "campaign_discount_amount": 0,
        "campaign_bonus_credit_amount": Decimal(0),
        "deleted": 0,
        "created_at": current_time,
        "updated_at": current_time,
    }


def _sample_exception_order_rows(
    *,
    plan_product_bid: str,
    topup_product_bid: str,
    current_time: datetime,
) -> list[dict[str, Any]]:
    return [
        _sample_exception_order_row(
            bill_order_bid="billing-debug-order-failed",
            creator_bid="billing-debug-creator-failed",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=plan_product_bid,
            subscription_bid="billing-debug-subscription-failed",
            payable_amount=29900,
            payment_provider="stripe",
            channel="checkout_session",
            status=BILLING_ORDER_STATUS_FAILED,
            failed_at=current_time,
            expires_at=None,
            failure_code="card_declined",
            failure_message="Card was declined",
            current_time=current_time,
        ),
        _sample_exception_order_row(
            bill_order_bid="billing-debug-order-pending",
            creator_bid="billing-debug-creator-pending",
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            product_bid=plan_product_bid,
            subscription_bid="",
            payable_amount=9900,
            payment_provider="pingxx",
            channel="alipay_qr",
            status=BILLING_ORDER_STATUS_PENDING,
            failed_at=None,
            expires_at=current_time,
            failure_code="",
            failure_message="",
            current_time=current_time,
        ),
        _sample_exception_order_row(
            bill_order_bid="billing-debug-order-timeout",
            creator_bid="billing-debug-creator-timeout",
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid=topup_product_bid,
            subscription_bid="",
            payable_amount=19900,
            payment_provider="pingxx",
            channel="wx_pub",
            status=BILLING_ORDER_STATUS_TIMEOUT,
            failed_at=None,
            expires_at=current_time,
            failure_code="checkout_timeout",
            failure_message="Checkout expired",
            current_time=current_time,
        ),
    ]


def seed_sample_focus_teachers() -> dict[str, object]:
    """Seed sample focus teachers."""
    current_time = _cli_facade().now_utc().replace(microsecond=0)
    today = current_time.date()

    creator_specs = _FOCUS_TEACHER_CREATOR_SPECS

    creator_inserted = 0
    creator_updated = 0
    for creator_spec in creator_specs:
        if _upsert_debug_creator(
            user_bid=creator_spec["user_bid"],
            identify=creator_spec["identify"],
            mobile=creator_spec["mobile"],
            nickname=creator_spec["nickname"],
            seed_source="sample_focus_teachers",
        ):
            creator_inserted += 1
        else:
            creator_updated += 1

    rows: list[dict[str, Any]] = [
        _build_focus_teacher_metric_row(
            bid=bid,
            stat_days_ago=stat_days_ago,
            creator_bid=creator_bid,
            shifu_bid=shifu_bid,
            usage_scene=usage_scene,
            metric=metric,
            credit_amount=credit_amount,
            record_count=record_count,
            raw_amount=raw_amount,
            today=today,
            current_time=current_time,
        )
        for (
            bid,
            stat_days_ago,
            creator_bid,
            shifu_bid,
            usage_scene,
            metric,
            credit_amount,
            record_count,
            raw_amount,
        ) in _FOCUS_TEACHER_METRIC_SPECS
    ]

    usage_metric_result = _upsert_bootstrap_rows(
        model=BillingDailyUsageMetric, key_field="daily_usage_metric_bid", rows=rows
    )

    with unit_of_work():
        pass
    return {
        "status": "seeded",
        "creators": {
            "count": len(creator_specs),
            "inserted": creator_inserted,
            "updated": creator_updated,
        },
        "usage_metrics": usage_metric_result,
    }


def _build_focus_teacher_metric_row(
    *,
    bid: str,
    stat_days_ago: int,
    creator_bid: str,
    shifu_bid: str,
    usage_scene: int,
    metric: int,
    credit_amount: str,
    record_count: int,
    raw_amount: int,
    today: date,
    current_time: datetime,
) -> dict[str, Any]:
    stat_day = today - timedelta(days=stat_days_ago)
    window_started_at = current_time.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ) - timedelta(days=stat_days_ago)
    window_ended_at = window_started_at + timedelta(days=1)
    return {
        "daily_usage_metric_bid": bid,
        "stat_date": stat_day.isoformat(),
        "creator_bid": creator_bid,
        "shifu_bid": shifu_bid,
        "usage_scene": usage_scene,
        "usage_type": BILL_USAGE_TYPE_LLM,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "billing_metric": metric,
        "raw_amount": raw_amount,
        "record_count": record_count,
        "consumed_credits": Decimal(credit_amount),
        "window_started_at": window_started_at,
        "window_ended_at": window_ended_at,
        "created_at": current_time,
        "updated_at": current_time,
        "deleted": 0,
    }


def _load_first_active_product_bid(product_type: int) -> str:
    row = (
        BillingProduct.query.filter(
            BillingProduct.product_type == product_type,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
            BillingProduct.deleted == 0,
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
        .first()
    )
    return str(row.product_bid or "").strip() if row is not None else ""


def _upsert_debug_creator(
    *,
    user_bid: str,
    identify: str,
    mobile: str,
    nickname: str,
    seed_source: str,
) -> bool:
    entity = get_user_entity_by_bid(user_bid, include_deleted=True)
    created = entity is None

    if entity is None:
        create_user_entity(
            user_bid=user_bid,
            identify=identify,
            nickname=nickname,
            language="zh-CN",
            state=USER_STATE_REGISTERED,
        )
    else:
        update_user_entity_fields(
            entity,
            identify=identify,
            nickname=nickname,
            language="zh-CN",
            state=USER_STATE_REGISTERED,
            deleted=False,
        )

    mark_user_roles(user_bid, is_creator=True)
    upsert_credential(
        current_app,
        user_bid=user_bid,
        provider_name="phone",
        subject_id=mobile,
        subject_format="phone",
        identifier=mobile,
        metadata={"seed_source": seed_source},
        verified=True,
    )
    return created


def _upsert_sample_exception_creator(
    *,
    user_bid: str,
    identify: str,
    mobile: str,
    nickname: str,
) -> bool:
    return _upsert_debug_creator(
        user_bid=user_bid,
        identify=identify,
        mobile=mobile,
        nickname=nickname,
        seed_source="sample_exception_orders",
    )
