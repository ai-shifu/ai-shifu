"""Admin billing subscription, entitlement and report read models."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.common.pagination import (
    DEFAULT_PAGE_INDEX,
    DEFAULT_PAGE_SIZE,
    normalize_pagination,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from sqlalchemy import case

from .consts import (
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from .dtos import (
    AdminBillingDailyLedgerSummaryPageDTO,
    AdminBillingDailyUsageMetricsPageDTO,
    AdminBillingFocusTeacherDTO,
    AdminBillingFocusTeachersPageDTO,
    BillingEntitlementsPageDTO,
    BillingLedgerAdjustResultDTO,
    BillingSubscriptionsPageDTO,
)
from .entitlements import (
    resolve_creator_entitlement_state,
)
from .models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingEntitlement,
    BillingSubscription,
)
from .primitives import credit_decimal_to_number
from .primitives import normalize_bid as _normalize_bid
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .queries import (
    build_list_page_payload as _build_list_page_payload,
)
from .queries import (
    build_page_payload as _build_page_payload,
)
from .queries import (
    load_admin_creator_bids as _load_admin_creator_bids,
)
from .queries import (
    load_latest_renewal_event_map as _load_latest_renewal_event_map,
)
from .queries import (
    load_product_code_map as _load_product_code_map,
)
from .queries import (
    load_wallet_map as _load_wallet_map,
)
from .queries import (
    normalize_stat_date_filter as _normalize_stat_date_filter,
)
from .queries import (
    resolve_subscription_status_filter as _resolve_subscription_status_filter,
)
from .queries import (
    subscription_has_attention as _subscription_has_attention,
)
from .read_model_lookups import (
    _load_credit_order_product_map,
    _load_matching_creator_bids_for_keyword,
    _load_operator_creator_map,
    _parse_stat_date,
    _sort_admin_billing_focus_attention_reasons,
)
from .serializers import (
    serialize_admin_daily_ledger_summary as _serialize_admin_daily_ledger_summary,
)
from .serializers import (
    serialize_admin_daily_usage_metric as _serialize_admin_daily_usage_metric,
)
from .serializers import (
    serialize_admin_entitlement_state as _serialize_admin_entitlement_state,
)
from .serializers import (
    serialize_admin_subscription as _serialize_admin_subscription,
)
from .wallets import (
    adjust_credit_wallet_balance,
)

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _read_models_facade() -> ModuleType:
    """Resolve collaborators through ``read_models`` so its patch points stay live."""
    from . import read_models

    return read_models


def build_admin_bill_subscriptions_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    creator_keyword: str = "",
    status: str = "",
    attention_only: bool = False,
) -> BillingSubscriptionsPageDTO:
    """Return paginated billing subscriptions for the admin billing surface."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_creator_keyword = str(creator_keyword or "").strip()
    status_code = _resolve_subscription_status_filter(status)

    with app.app_context():
        query = BillingSubscription.query.filter(BillingSubscription.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
        elif normalized_creator_keyword:
            matched_creator_bids = _load_matching_creator_bids_for_keyword(
                normalized_creator_keyword
            )
            if matched_creator_bids:
                query = query.filter(
                    BillingSubscription.creator_bid.in_(matched_creator_bids)
                )
            else:
                query = query.filter(BillingSubscription.id == 0)
        if status_code is not None:
            query = query.filter(BillingSubscription.status == status_code)

        query = query.order_by(
            case(
                (
                    BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                    1,
                ),
                (
                    BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_PAUSED,
                    2,
                ),
                (
                    BillingSubscription.status
                    == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
                    3,
                ),
                else_=9,
            ),
            BillingSubscription.updated_at.desc(),
            BillingSubscription.id.desc(),
        )
        if attention_only:
            ordered_rows = query.all()
            renewal_events = _load_latest_renewal_event_map(
                [row.subscription_bid for row in ordered_rows]
            )
            attention_rows = [
                row
                for row in ordered_rows
                if _subscription_has_attention(
                    row,
                    renewal_event=renewal_events.get(row.subscription_bid),
                )
            ]
            total = len(attention_rows)
            if total == 0:
                return BillingSubscriptionsPageDTO(
                    items=[],
                    page=safe_page_index,
                    page_count=0,
                    page_size=safe_page_size,
                    total=0,
                )

            page_count = (total + safe_page_size - 1) // safe_page_size
            resolved_page = min(safe_page_index, max(page_count, 1))
            offset = (resolved_page - 1) * safe_page_size
            rows = attention_rows[offset : offset + safe_page_size]
            page_renewal_events = {
                row.subscription_bid: renewal_events.get(row.subscription_bid)
                for row in rows
            }
        else:
            total = query.order_by(None).count()
            if total == 0:
                return BillingSubscriptionsPageDTO(
                    items=[],
                    page=safe_page_index,
                    page_count=0,
                    page_size=safe_page_size,
                    total=0,
                )

            page_count = (total + safe_page_size - 1) // safe_page_size
            resolved_page = min(safe_page_index, max(page_count, 1))
            offset = (resolved_page - 1) * safe_page_size
            rows = query.offset(offset).limit(safe_page_size).all()
            page_renewal_events = _load_latest_renewal_event_map(
                [row.subscription_bid for row in rows]
            )

        creator_map = _load_operator_creator_map(
            [str(row.creator_bid or "").strip() for row in rows]
        )
        product_map = _load_credit_order_product_map(
            [
                *[str(row.product_bid or "").strip() for row in rows],
                *[
                    str(row.next_product_bid or "").strip()
                    for row in rows
                    if _normalize_bid(row.next_product_bid)
                ],
            ]
        )
        product_codes = _load_product_code_map(
            [
                *[row.product_bid for row in rows],
                *[
                    row.next_product_bid
                    for row in rows
                    if _normalize_bid(row.next_product_bid)
                ],
            ]
        )
        wallets = _load_wallet_map([row.creator_bid for row in rows])
        return BillingSubscriptionsPageDTO(
            items=[
                _serialize_admin_subscription(
                    app,
                    row,
                    creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
                    product=product_map.get(str(row.product_bid or "").strip()),
                    next_product=product_map.get(
                        str(_normalize_bid(row.next_product_bid) or "")
                    ),
                    product_codes=product_codes,
                    wallet=wallets.get(row.creator_bid),
                    renewal_event=page_renewal_events.get(row.subscription_bid),
                )
                for row in rows
            ],
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_admin_bill_entitlements_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    independent_only: bool = False,
) -> BillingEntitlementsPageDTO:
    """Return paginated effective entitlement snapshots for admin billing."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)

    with app.app_context():
        creator_bids = (
            _load_independent_entitlement_creator_bids(
                creator_bid=normalized_creator_bid
            )
            if independent_only
            else _load_admin_creator_bids(creator_bid=normalized_creator_bid)
        )
        creator_map = _load_operator_creator_map(creator_bids)
        states = {
            candidate_creator_bid: resolve_creator_entitlement_state(
                candidate_creator_bid
            )
            for candidate_creator_bid in creator_bids
        }
        product_map = _load_credit_order_product_map(
            [
                str(state.product_bid or "").strip()
                for state in states.values()
                if state.product_bid
            ]
        )
        items = [
            _serialize_admin_entitlement_state(
                app,
                states[candidate_creator_bid],
                creator=creator_map.get(candidate_creator_bid, {}),
                product=product_map.get(
                    str(states[candidate_creator_bid].product_bid or "").strip()
                ),
            )
            for candidate_creator_bid in creator_bids
        ]
        if independent_only:
            items = [
                item
                for item in items
                if item.branding_enabled
                or item.custom_domain_enabled
                or item.custom_wechat_enabled
                or item.custom_payment_enabled
            ]
        payload = _build_list_page_payload(
            items,
            page_index=safe_page_index,
            page_size=safe_page_size,
        )
        return BillingEntitlementsPageDTO(**payload.to_dto_kwargs())


def _load_independent_entitlement_creator_bids(*, creator_bid: str = "") -> list[str]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    now = _read_models_facade().now_utc()
    query = db.session.query(
        BillingEntitlement.creator_bid,
        BillingEntitlement.branding_enabled,
        BillingEntitlement.custom_domain_enabled,
        BillingEntitlement.feature_payload,
    ).filter(
        BillingEntitlement.deleted == 0,
        BillingEntitlement.creator_bid != "",
        BillingEntitlement.source_type == CREDIT_SOURCE_TYPE_MANUAL,
        BillingEntitlement.effective_from <= now,
        (
            (BillingEntitlement.effective_to.is_(None))
            | (BillingEntitlement.effective_to > now)
        ),
    )
    if normalized_creator_bid:
        query = query.filter(BillingEntitlement.creator_bid == normalized_creator_bid)
    rows = query.all()
    return sorted(
        {
            normalized
            for row in rows
            for normalized in [_normalize_bid(row[0])]
            if normalized and _is_independent_entitlement_row(row)
        }
    )


def _is_independent_entitlement_row(row: object) -> bool:
    if bool(row[1]) or bool(row[2]):
        return True
    payload = row[3] if isinstance(row[3], dict) else {}
    return _payload_bool(payload.get("custom_wechat_enabled")) or _payload_bool(
        payload.get("custom_payment_enabled")
    )


def _payload_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def build_admin_bill_daily_usage_metrics_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    stat_date_from: str = "",
    stat_date_to: str = "",
) -> AdminBillingDailyUsageMetricsPageDTO:
    """Return paginated cross-creator daily usage rows for admin reporting."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.deleted == 0
        )
        if normalized_creator_bid:
            query = query.filter(
                BillingDailyUsageMetric.creator_bid == normalized_creator_bid,
            )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyUsageMetric.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyUsageMetric.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyUsageMetric.stat_date.desc(),
            BillingDailyUsageMetric.creator_bid.asc(),
            BillingDailyUsageMetric.consumed_credits.desc(),
            BillingDailyUsageMetric.raw_amount.desc(),
            BillingDailyUsageMetric.id.desc(),
        )
        total = query.order_by(None).count()
        if total == 0:
            return AdminBillingDailyUsageMetricsPageDTO(
                items=[],
                page=safe_page_index,
                page_count=0,
                page_size=safe_page_size,
                total=0,
            )

        page_count = (total + safe_page_size - 1) // safe_page_size
        resolved_page = min(safe_page_index, max(page_count, 1))
        offset = (resolved_page - 1) * safe_page_size
        rows = query.offset(offset).limit(safe_page_size).all()
        creator_map = _load_operator_creator_map(
            [str(row.creator_bid or "").strip() for row in rows]
        )
        return AdminBillingDailyUsageMetricsPageDTO(
            items=[
                _serialize_admin_daily_usage_metric(
                    app,
                    row,
                    creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
                )
                for row in rows
            ],
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_admin_billing_focus_teachers_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AdminBillingFocusTeachersPageDTO:
    """Return operator-focused teachers that match billing attention rules."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    today = _read_models_facade().now_utc().date()
    current_30d_start = today - timedelta(days=29)

    with app.app_context():
        rows = (
            BillingDailyUsageMetric.query.filter(
                BillingDailyUsageMetric.deleted == 0,
                BillingDailyUsageMetric.stat_date >= current_30d_start.isoformat(),
                BillingDailyUsageMetric.stat_date <= today.isoformat(),
            )
            .order_by(
                BillingDailyUsageMetric.stat_date.desc(),
                BillingDailyUsageMetric.creator_bid.asc(),
                BillingDailyUsageMetric.id.desc(),
            )
            .all()
        )

        creator_map = _load_operator_creator_map(
            [str(row.creator_bid or "").strip() for row in rows]
        )

        aggregated = _aggregate_focus_teacher_usage(rows, today=today)

        focus_items: list[AdminBillingFocusTeacherDTO] = []
        for creator_bid, stats in aggregated.items():
            focus_item = _build_focus_teacher_item(
                creator_bid,
                stats,
                creator=creator_map.get(creator_bid, {}),
            )
            if focus_item is not None:
                focus_items.append(focus_item)

        focus_items.sort(
            key=lambda item: (
                "rapid_growth" not in item.attention_reasons,
                -len(item.attention_reasons),
                -float(item.credits_30d or 0),
                -(
                    int(item.latest_usage_at.timestamp())
                    if item.latest_usage_at is not None
                    else 0
                ),
                str(item.creator_bid or ""),
            )
        )

        payload = _build_list_page_payload(
            focus_items,
            page_index=safe_page_index,
            page_size=safe_page_size,
        )
        return AdminBillingFocusTeachersPageDTO(**payload.to_dto_kwargs())


def _aggregate_focus_teacher_usage(
    rows: list[BillingDailyUsageMetric],
    *,
    today: date,
) -> dict[str, dict[str, Any]]:
    """Sum 30-day, current-7-day and previous-7-day usage per creator."""
    current_7d_start = today - timedelta(days=6)
    previous_7d_start = current_7d_start - timedelta(days=7)
    previous_7d_end = current_7d_start - timedelta(days=1)

    aggregated: dict[str, dict[str, Any]] = {}
    for row in rows:
        creator_bid = str(row.creator_bid or "").strip()
        if not creator_bid:
            continue
        stat_date = _parse_stat_date(row.stat_date)
        if stat_date is None:
            continue

        item = aggregated.setdefault(
            creator_bid,
            {
                "creator_bid": creator_bid,
                "credits_7d": Decimal(0),
                "credits_prev_7d": Decimal(0),
                "credits_30d": Decimal(0),
                "record_count_7d": 0,
                "active_days_7d": set(),
                "production_credits_30d": Decimal(0),
                "debug_preview_credits_30d": Decimal(0),
                "total_credits_30d": Decimal(0),
                "latest_usage_at": None,
            },
        )

        credit_amount = Decimal(
            str(credit_decimal_to_number(row.consumed_credits) or 0)
        )
        record_count = int(row.record_count or 0)
        # Use the start of the UTC stat window as the visible "latest
        # active" day. `window_ended_at` points at the next UTC day
        # boundary and can render as a future local date in the admin UI.
        latest_usage_at = row.window_started_at or row.window_ended_at

        item["credits_30d"] += credit_amount
        item["total_credits_30d"] += credit_amount
        if row.usage_scene == BILL_USAGE_SCENE_PROD:
            item["production_credits_30d"] += credit_amount
        elif row.usage_scene in (BILL_USAGE_SCENE_DEBUG, BILL_USAGE_SCENE_PREVIEW):
            item["debug_preview_credits_30d"] += credit_amount

        if latest_usage_at is not None and (
            item["latest_usage_at"] is None or latest_usage_at > item["latest_usage_at"]
        ):
            item["latest_usage_at"] = latest_usage_at

        if current_7d_start <= stat_date <= today:
            item["credits_7d"] += credit_amount
            item["record_count_7d"] += record_count
            if credit_amount > 0:
                item["active_days_7d"].add(stat_date.isoformat())
        elif previous_7d_start <= stat_date <= previous_7d_end:
            item["credits_prev_7d"] += credit_amount
    return aggregated


def _build_focus_teacher_item(
    creator_bid: str,
    stats: dict[str, Any],
    *,
    creator: dict[str, Any],
) -> AdminBillingFocusTeacherDTO | None:
    """Apply the attention rules; return ``None`` when no rule matches."""
    credits_7d = stats["credits_7d"]
    credits_prev_7d = stats["credits_prev_7d"]
    credits_30d = stats["credits_30d"]
    total_credits_30d = stats["total_credits_30d"]
    production_credits_30d = stats["production_credits_30d"]
    debug_preview_credits_30d = stats["debug_preview_credits_30d"]
    record_count_7d = int(stats["record_count_7d"] or 0)
    active_days_7d = len(stats["active_days_7d"])

    reasons: set[str] = set()
    if credits_30d >= Decimal(8):
        reasons.add("high_consumption")
    if record_count_7d >= 5:
        reasons.add("high_frequency")
    if production_credits_30d >= Decimal(8):
        reasons.add("active_production")
    if (
        total_credits_30d >= Decimal(8)
        and total_credits_30d > 0
        and (debug_preview_credits_30d / total_credits_30d) >= Decimal("0.7")
    ):
        reasons.add("debug_preview_heavy")
    if active_days_7d >= 3:
        reasons.add("sustained_activity")

    growth_delta = credits_7d - credits_prev_7d
    if credits_prev_7d > 0:
        growth_ratio = growth_delta / credits_prev_7d
        if growth_ratio >= Decimal(1) and growth_delta >= Decimal(8):
            reasons.add("rapid_growth")
    elif credits_7d >= Decimal(8):
        reasons.add("rapid_growth")

    if not reasons:
        return None

    production_ratio_30d = Decimal(0)
    if total_credits_30d > 0:
        production_ratio_30d = production_credits_30d / total_credits_30d

    return AdminBillingFocusTeacherDTO(
        creator_bid=creator_bid,
        creator_mobile=str(creator.get("mobile") or ""),
        creator_email=str(creator.get("email") or ""),
        creator_nickname=str(creator.get("nickname") or ""),
        credits_7d=credit_decimal_to_number(credits_7d),
        credits_30d=credit_decimal_to_number(credits_30d),
        record_count_7d=record_count_7d,
        active_days_7d=active_days_7d,
        production_credits_30d=credit_decimal_to_number(production_credits_30d),
        debug_preview_credits_30d=credit_decimal_to_number(debug_preview_credits_30d),
        total_credits_30d=credit_decimal_to_number(total_credits_30d),
        production_ratio_30d=round(float(production_ratio_30d), 4),
        latest_usage_at=stats["latest_usage_at"],
        attention_reasons=_sort_admin_billing_focus_attention_reasons(reasons),
    )


def build_admin_bill_daily_ledger_summary_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    stat_date_from: str = "",
    stat_date_to: str = "",
) -> AdminBillingDailyLedgerSummaryPageDTO:
    """Return paginated cross-creator daily ledger rows for admin reporting."""
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.deleted == 0,
        )
        if normalized_creator_bid:
            query = query.filter(
                BillingDailyLedgerSummary.creator_bid == normalized_creator_bid,
            )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyLedgerSummary.stat_date.desc(),
            BillingDailyLedgerSummary.creator_bid.asc(),
            BillingDailyLedgerSummary.entry_count.desc(),
            BillingDailyLedgerSummary.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_admin_daily_ledger_summary(
                app,
                row,
            ),
        )
        return AdminBillingDailyLedgerSummaryPageDTO(**payload.to_dto_kwargs())


def adjust_admin_billing_ledger(
    app: Flask,
    *,
    operator_user_bid: str,
    payload: dict[str, object],
) -> BillingLedgerAdjustResultDTO:
    """Apply a manual admin ledger adjustment through wallet buckets."""
    normalized_creator_bid = _normalize_bid(payload.get("creator_bid"))
    if not normalized_creator_bid:
        raise_param_error("creator_bid")

    amount = payload.get("amount")
    try:
        normalized_amount = _to_decimal(amount)
    except Exception:
        raise_param_error("amount")
    if normalized_amount == 0:
        raise_param_error("amount")
    if _quantize_credit_amount(normalized_amount, precision=2) != normalized_amount:
        raise_param_error("amount")

    note = str(payload.get("note") or payload.get("reason") or "").strip()
    if len(note) > 255:
        raise_param_error("note")

    return adjust_credit_wallet_balance(
        app,
        creator_bid=normalized_creator_bid,
        amount=normalized_amount,
        note=note,
        operator_user_bid=_normalize_bid(operator_user_bid),
    )
