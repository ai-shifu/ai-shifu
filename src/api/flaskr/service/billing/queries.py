"""Query, filter, and pagination helpers for billing surfaces."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case

from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error

from .primitives import coerce_datetime, normalize_bid
from .consts import (
    BILLING_DOMAIN_BINDING_STATUS_LABELS,
    BILLING_INTERVAL_DAY,
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
from .value_objects import PageWindow

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


def normalize_stat_date_filter(value: Any, *, parameter_name: str) -> str:
    normalized_value = normalize_bid(value)
    if not normalized_value:
        return ""
    try:
        datetime.strptime(normalized_value, "%Y-%m-%d")
    except ValueError:
        raise_param_error(parameter_name)
    return normalized_value


def normalize_payment_provider_hint(value: Any) -> str:
    provider = str(value or "").strip().lower()
    if not provider:
        return ""
    if provider not in {"stripe", "pingxx"}:
        raise_error("server.pay.payChannelNotSupport")
    return provider


def load_subscription_by_bid(subscription_bid: str) -> BillingSubscription | None:
    normalized_subscription_bid = normalize_bid(subscription_bid)
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


def load_latest_billing_order_by_subscription(
    subscription_bid: str,
) -> BillingOrder | None:
    normalized_subscription_bid = normalize_bid(subscription_bid)
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


def load_latest_subscription_renewal_order(
    subscription_bid: str,
    *,
    statuses: tuple[int, ...] | None = None,
) -> BillingOrder | None:
    normalized_subscription_bid = normalize_bid(subscription_bid)
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


def extract_order_metadata_datetime(metadata: Any, key: str) -> datetime | None:
    if not isinstance(metadata, dict):
        return None
    return coerce_datetime(metadata.get(key))


def serialize_order_metadata_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def extract_resolved_order_cycle_start_at(metadata: Any) -> datetime | None:
    return extract_order_metadata_datetime(
        metadata,
        "applied_cycle_start_at",
    ) or extract_order_metadata_datetime(metadata, "renewal_cycle_start_at")


def extract_resolved_order_cycle_end_at(metadata: Any) -> datetime | None:
    return extract_order_metadata_datetime(
        metadata,
        "applied_cycle_end_at",
    ) or extract_order_metadata_datetime(metadata, "renewal_cycle_end_at")


def load_subscription_renewal_order_by_cycle(
    subscription_bid: str,
    *,
    cycle_start_at: datetime | None = None,
    cycle_end_at: datetime | None = None,
    statuses: tuple[int, ...] | None = None,
) -> BillingOrder | None:
    normalized_subscription_bid = normalize_bid(subscription_bid)
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
        expected_start = extract_order_metadata_datetime(
            metadata, "renewal_cycle_start_at"
        )
        expected_end = extract_order_metadata_datetime(metadata, "renewal_cycle_end_at")
        if cycle_start_at is not None and expected_start != cycle_start_at:
            continue
        if cycle_end_at is not None and expected_end != cycle_end_at:
            continue
        return row
    return None


def calculate_billing_cycle_end(
    product: BillingProduct,
    *,
    cycle_start_at: datetime,
) -> datetime | None:
    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_DAY:
        return cycle_start_at + timedelta(days=interval_count)
    if interval == BILLING_INTERVAL_MONTH:
        return add_months(cycle_start_at, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return add_years(cycle_start_at, interval_count)
    return None


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def load_primary_active_subscription(
    creator_bid: str,
    *,
    as_of: datetime | None = None,
) -> BillingSubscription | None:
    normalized_creator_bid = normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return None

    resolved_at = as_of or datetime.now()
    product_sort_order = case(
        (BillingProduct.sort_order.is_(None), -1),
        else_=BillingProduct.sort_order,
    )
    return (
        BillingSubscription.query.outerjoin(
            BillingProduct,
            (BillingProduct.product_bid == BillingSubscription.product_bid)
            & (BillingProduct.deleted == 0),
        )
        .filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == normalized_creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
            (
                BillingSubscription.current_period_start_at.is_(None)
                | (BillingSubscription.current_period_start_at <= resolved_at)
            ),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at > resolved_at,
        )
        .order_by(
            product_sort_order.desc(),
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )


def load_current_subscription(creator_bid: str) -> BillingSubscription | None:
    normalized_creator_bid = normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return None

    prioritized = load_primary_active_subscription(normalized_creator_bid)
    if prioritized is not None:
        return prioritized
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == normalized_creator_bid,
        )
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .first()
    )


def load_product_code_map(product_bids: list[str]) -> dict[str, str]:
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


def load_wallet_map(creator_bids: list[str]) -> dict[str, CreditWallet]:
    normalized_creator_bids = [normalize_bid(bid) for bid in creator_bids if bid]
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


def load_latest_renewal_event_map(
    subscription_bids: list[str],
) -> dict[str, BillingRenewalEvent]:
    normalized_subscription_bids = [
        normalize_bid(bid) for bid in subscription_bids if bid
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


def load_admin_creator_bids(*, creator_bid: str = "") -> list[str]:
    normalized_creator_bid = normalize_bid(creator_bid)
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
            for normalized in (normalize_bid(row[0]) for row in rows)
            if normalized
        )
    return sorted(creator_bids)


def subscription_has_attention(
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


def resolve_subscription_status_filter(value: str) -> int | None:
    normalized_value = normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _SUBSCRIPTION_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _SUBSCRIPTION_STATUS_CODES_BY_LABEL[normalized_value]


def resolve_order_status_filter(value: str) -> int | None:
    normalized_value = normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _ORDER_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _ORDER_STATUS_CODES_BY_LABEL[normalized_value]


def resolve_domain_binding_status_filter(value: str) -> int | None:
    normalized_value = normalize_bid(value)
    if not normalized_value:
        return None
    if normalized_value not in _DOMAIN_BINDING_STATUS_CODES_BY_LABEL:
        raise_param_error("status")
    return _DOMAIN_BINDING_STATUS_CODES_BY_LABEL[normalized_value]


def build_page_payload(
    query, *, page_index: int, page_size: int, serializer
) -> PageWindow[Any]:
    total = query.order_by(None).count()
    if total == 0:
        return PageWindow(
            items=[],
            page=page_index,
            page_count=0,
            page_size=page_size,
            total=0,
        )

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()
    return PageWindow(
        items=[serializer(row) for row in rows],
        page=resolved_page,
        page_count=page_count,
        page_size=page_size,
        total=total,
    )


def build_list_page_payload(
    items: list[Any],
    *,
    page_index: int,
    page_size: int,
) -> PageWindow[Any]:
    total = len(items)
    if total == 0:
        return PageWindow(
            items=[],
            page=page_index,
            page_count=0,
            page_size=page_size,
            total=0,
        )

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    return PageWindow(
        items=items[offset : offset + page_size],
        page=resolved_page,
        page_count=page_count,
        page_size=page_size,
        total=total,
    )
