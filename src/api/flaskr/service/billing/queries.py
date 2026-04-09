"""Query, filter, and pagination helpers for billing surfaces."""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any

from sqlalchemy import case

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error

from .consts import (
    BILLING_DOMAIN_BINDING_STATUS_LABELS,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_STATUS_LABELS,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
)
from .models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingDomainBinding,
    BillingEntitlement,
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditWallet,
)
from .serializers import coerce_datetime as _coerce_datetime
from .serializers import normalize_bid as _normalize_bid

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)

_SUBSCRIPTION_STATUS_SORT = {
    BILLING_SUBSCRIPTION_STATUS_ACTIVE: 1,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE: 2,
    BILLING_SUBSCRIPTION_STATUS_PAUSED: 3,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED: 4,
    BILLING_SUBSCRIPTION_STATUS_DRAFT: 5,
    BILLING_SUBSCRIPTION_STATUS_CANCELED: 6,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED: 7,
}

_SUBSCRIPTION_STATUS_CODES_BY_LABEL = {
    label: code for code, label in BILLING_SUBSCRIPTION_STATUS_LABELS.items()
}

_ORDER_STATUS_CODES_BY_LABEL = {
    label: code for code, label in BILLING_ORDER_STATUS_LABELS.items()
}

_DOMAIN_BINDING_STATUS_CODES_BY_LABEL = {
    label: code for code, label in BILLING_DOMAIN_BINDING_STATUS_LABELS.items()
}


def normalize_pagination(page_index: int, page_size: int) -> tuple[int, int]:
    """Normalize list pagination parameters to the shared admin defaults."""

    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)


def _normalize_stat_date_filter(value: Any, *, parameter_name: str) -> str:
    normalized_value = _normalize_bid(value)
    if not normalized_value:
        return ""
    try:
        datetime.strptime(normalized_value, "%Y-%m-%d")
    except ValueError:
        raise_param_error(parameter_name)
    return normalized_value


def _normalize_payment_provider_hint(value: Any) -> str:
    provider = str(value or "").strip().lower()
    if not provider:
        return ""
    if provider not in {"stripe", "pingxx"}:
        raise_error("server.pay.payChannelNotSupport")
    return provider


def _load_subscription_by_bid(subscription_bid: str) -> BillingSubscription | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.subscription_bid == normalized_subscription_bid,
        )
        .order_by(BillingSubscription.id.desc())
        .first()
    )


def _load_latest_billing_order_by_subscription(
    subscription_bid: str,
) -> BillingOrder | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.subscription_bid == normalized_subscription_bid,
        )
        .order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        .first()
    )


def _load_latest_subscription_renewal_order(
    subscription_bid: str,
    *,
    statuses: tuple[int, ...] | None = None,
) -> BillingOrder | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.subscription_bid == normalized_subscription_bid,
        BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    )
    if statuses:
        query = query.filter(BillingOrder.status.in_(statuses))
    return query.order_by(
        BillingOrder.created_at.desc(), BillingOrder.id.desc()
    ).first()


def _extract_order_metadata_datetime(metadata: Any, key: str) -> datetime | None:
    if not isinstance(metadata, dict):
        return None
    return _coerce_datetime(metadata.get(key))


def _serialize_order_metadata_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _extract_resolved_order_cycle_start_at(metadata: Any) -> datetime | None:
    return _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_start_at",
    ) or _extract_order_metadata_datetime(metadata, "renewal_cycle_start_at")


def _extract_resolved_order_cycle_end_at(metadata: Any) -> datetime | None:
    return _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_end_at",
    ) or _extract_order_metadata_datetime(metadata, "renewal_cycle_end_at")


def _load_subscription_renewal_order_by_cycle(
    subscription_bid: str,
    *,
    cycle_start_at: datetime | None = None,
    cycle_end_at: datetime | None = None,
    statuses: tuple[int, ...] | None = None,
) -> BillingOrder | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.subscription_bid == normalized_subscription_bid,
        BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    )
    if statuses:
        query = query.filter(BillingOrder.status.in_(statuses))
    rows = query.order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc()).all()
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        expected_start = _extract_order_metadata_datetime(
            metadata, "renewal_cycle_start_at"
        )
        expected_end = _extract_order_metadata_datetime(
            metadata, "renewal_cycle_end_at"
        )
        if cycle_start_at is not None and expected_start != cycle_start_at:
            continue
        if cycle_end_at is not None and expected_end != cycle_end_at:
            continue
        return row
    return None


def _calculate_billing_cycle_end(
    product: BillingProduct,
    *,
    cycle_start_at: datetime,
) -> datetime | None:
    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_MONTH:
        return _add_months(cycle_start_at, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return _add_years(cycle_start_at, interval_count)
    return None


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def _load_current_subscription(creator_bid: str) -> BillingSubscription | None:
    prioritized = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .order_by(
            case(
                *[
                    (BillingSubscription.status == status, rank)
                    for status, rank in _SUBSCRIPTION_STATUS_SORT.items()
                ],
                else_=99,
            ),
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )
    if prioritized is not None:
        return prioritized
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
        )
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .first()
    )


def _load_product_code_map(product_bids: list[str]) -> dict[str, str]:
    normalized_bids = [bid for bid in product_bids if bid]
    if not normalized_bids:
        return {}
    rows = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid.in_(normalized_bids),
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    return {row.product_bid: row.product_code for row in rows}


def _load_wallet_map(creator_bids: list[str]) -> dict[str, CreditWallet]:
    normalized_creator_bids = [_normalize_bid(bid) for bid in creator_bids if bid]
    if not normalized_creator_bids:
        return {}
    rows = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid.in_(normalized_creator_bids),
        )
        .order_by(CreditWallet.creator_bid.asc(), CreditWallet.id.desc())
        .all()
    )
    payload: dict[str, CreditWallet] = {}
    for row in rows:
        payload.setdefault(row.creator_bid, row)
    return payload


def _load_latest_renewal_event_map(
    subscription_bids: list[str],
) -> dict[str, BillingRenewalEvent]:
    normalized_subscription_bids = [
        _normalize_bid(bid) for bid in subscription_bids if bid
    ]
    if not normalized_subscription_bids:
        return {}
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid.in_(normalized_subscription_bids),
        )
        .order_by(
            BillingRenewalEvent.subscription_bid.asc(),
            BillingRenewalEvent.scheduled_at.desc(),
            BillingRenewalEvent.id.desc(),
        )
        .all()
    )
    payload: dict[str, BillingRenewalEvent] = {}
    for row in rows:
        payload.setdefault(row.subscription_bid, row)
    return payload


def _load_admin_creator_bids(*, creator_bid: str = "") -> list[str]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if normalized_creator_bid:
        return [normalized_creator_bid]

    creator_bids: set[str] = set()
    creator_columns = (
        (BillingEntitlement, BillingEntitlement.creator_bid),
        (BillingSubscription, BillingSubscription.creator_bid),
        (BillingOrder, BillingOrder.creator_bid),
        (BillingDomainBinding, BillingDomainBinding.creator_bid),
        (CreditWallet, CreditWallet.creator_bid),
        (BillingDailyUsageMetric, BillingDailyUsageMetric.creator_bid),
        (BillingDailyLedgerSummary, BillingDailyLedgerSummary.creator_bid),
    )
    for model, column in creator_columns:
        rows = (
            db.session.query(column)
            .filter(model.deleted == 0, column != "")
            .distinct()
            .all()
        )
        creator_bids.update(
            normalized
            for normalized in (_normalize_bid(row[0]) for row in rows)
            if normalized
        )
    return sorted(creator_bids)


def _subscription_has_attention(
    row: BillingSubscription,
    *,
    renewal_event: BillingRenewalEvent | None,
) -> bool:
    if row.status in {
        BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
        BILLING_SUBSCRIPTION_STATUS_PAUSED,
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    }:
        return True
    if renewal_event is None:
        return False
    if renewal_event.status in {
        BILLING_RENEWAL_EVENT_STATUS_PENDING,
        BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
        BILLING_RENEWAL_EVENT_STATUS_FAILED,
    }:
        return True
    return bool(str(renewal_event.last_error or "").strip())


def _resolve_subscription_status_filter(value: str) -> int | None:
    normalized_value = _normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _SUBSCRIPTION_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _SUBSCRIPTION_STATUS_CODES_BY_LABEL[normalized_value]


def _resolve_order_status_filter(value: str) -> int | None:
    normalized_value = _normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _ORDER_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _ORDER_STATUS_CODES_BY_LABEL[normalized_value]


def _resolve_domain_binding_status_filter(value: str) -> int | None:
    normalized_value = _normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _DOMAIN_BINDING_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _DOMAIN_BINDING_STATUS_CODES_BY_LABEL[normalized_value]


def _build_page_payload(
    query, *, page_index: int, page_size: int, serializer
) -> dict[str, Any]:
    total = query.order_by(None).count()
    if total == 0:
        return {
            "items": [],
            "page": page_index,
            "page_count": 0,
            "page_size": page_size,
            "total": 0,
        }

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()
    return {
        "items": [serializer(row) for row in rows],
        "page": resolved_page,
        "page_count": page_count,
        "page_size": page_size,
        "total": total,
    }


def _build_list_page_payload(
    items: list[dict[str, Any]],
    *,
    page_index: int,
    page_size: int,
) -> dict[str, Any]:
    total = len(items)
    if total == 0:
        return {
            "items": [],
            "page": page_index,
            "page_count": 0,
            "page_size": page_size,
            "total": 0,
        }

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    return {
        "items": items[offset : offset + page_size],
        "page": resolved_page,
        "page_count": page_count,
        "page_size": page_size,
        "total": total,
    }


normalize_stat_date_filter = _normalize_stat_date_filter
normalize_payment_provider_hint = _normalize_payment_provider_hint
load_subscription_by_bid = _load_subscription_by_bid
load_latest_billing_order_by_subscription = _load_latest_billing_order_by_subscription
load_latest_subscription_renewal_order = _load_latest_subscription_renewal_order
extract_order_metadata_datetime = _extract_order_metadata_datetime
serialize_order_metadata_datetime = _serialize_order_metadata_datetime
extract_resolved_order_cycle_start_at = _extract_resolved_order_cycle_start_at
extract_resolved_order_cycle_end_at = _extract_resolved_order_cycle_end_at
load_subscription_renewal_order_by_cycle = _load_subscription_renewal_order_by_cycle
calculate_billing_cycle_end = _calculate_billing_cycle_end
add_months = _add_months
add_years = _add_years
load_current_subscription = _load_current_subscription
load_product_code_map = _load_product_code_map
load_wallet_map = _load_wallet_map
load_latest_renewal_event_map = _load_latest_renewal_event_map
load_admin_creator_bids = _load_admin_creator_bids
subscription_has_attention = _subscription_has_attention
resolve_subscription_status_filter = _resolve_subscription_status_filter
resolve_order_status_filter = _resolve_order_status_filter
resolve_domain_binding_status_filter = _resolve_domain_binding_status_filter
build_page_payload = _build_page_payload
build_list_page_payload = _build_list_page_payload
