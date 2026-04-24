"""Subscription lifecycle, renewal orchestration, and credit grants."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_providers import get_payment_provider
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from .bucket_categories import (
    resolve_bucket_category_from_order_type,
    resolve_credit_bucket_priority,
)
from .dtos import BillingSubscriptionDTO
from .models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .queries import (
    extract_order_metadata_datetime as _extract_order_metadata_datetime,
    extract_resolved_order_cycle_end_at as _extract_resolved_order_cycle_end_at,
    extract_resolved_order_cycle_start_at as _extract_resolved_order_cycle_start_at,
    load_latest_subscription_renewal_order as _load_latest_subscription_renewal_order,
    load_primary_active_subscription as _load_primary_active_subscription,
    load_subscription_by_bid as _load_subscription_by_bid,
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
    serialize_order_metadata_datetime as _serialize_order_metadata_datetime,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import normalize_json_value as _normalize_json_value
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal
from .serializers import serialize_subscription as _serialize_subscription
from .wallets import (
    load_or_create_credit_bucket_by_category,
    load_primary_credit_bucket_by_category,
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
    resolve_bucket_source_type_for_category,
    sync_credit_bucket_status,
)
from .value_objects import JsonObjectMap

_MANAGED_RENEWAL_EVENT_TYPES = (
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
)

_PENDING_RENEWAL_EVENT_STATUSES = (
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
)


@dataclass(slots=True, frozen=True)
class CreditGrantContext:
    source_type: int
    bucket_category: int
    priority: int
    grant_reason: str


@dataclass(slots=True, frozen=True)
class TopupExpiryRepairRecord:
    wallet_bucket_bid: str
    bill_order_bid: str | None
    previous_effective_to: datetime | None
    effective_to: datetime
    ledger_bids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "bill_order_bid": self.bill_order_bid,
            "previous_effective_to": self.previous_effective_to,
            "effective_to": self.effective_to,
            "ledger_bids": list(self.ledger_bids),
        }


@dataclass(slots=True, frozen=True)
class TopupExpiryRepairResult:
    status: str
    creator_bid: str | None
    inspected_bucket_count: int
    repaired_bucket_count: int
    repaired_ledger_count: int
    repaired_records: list[TopupExpiryRepairRecord] = field(default_factory=list)
    skipped_bucket_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "inspected_bucket_count": self.inspected_bucket_count,
            "repaired_bucket_count": self.repaired_bucket_count,
            "repaired_ledger_count": self.repaired_ledger_count,
            "repaired_records": [item.to_payload() for item in self.repaired_records],
            "skipped_bucket_bids": list(self.skipped_bucket_bids),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class SubscriptionCycleRepairRecord:
    subscription_bid: str
    creator_bid: str
    bill_order_bid: str | None
    wallet_bucket_bid: str | None
    previous_current_period_start_at: datetime | None
    previous_current_period_end_at: datetime | None
    current_period_start_at: datetime
    current_period_end_at: datetime
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "subscription_bid": self.subscription_bid,
            "creator_bid": self.creator_bid,
            "bill_order_bid": self.bill_order_bid,
            "wallet_bucket_bid": self.wallet_bucket_bid,
            "previous_current_period_start_at": self.previous_current_period_start_at,
            "previous_current_period_end_at": self.previous_current_period_end_at,
            "current_period_start_at": self.current_period_start_at,
            "current_period_end_at": self.current_period_end_at,
            "reason": self.reason,
        }


@dataclass(slots=True, frozen=True)
class SubscriptionCycleRepairResult:
    status: str
    creator_bid: str | None
    subscription_bid: str | None
    inspected_subscription_count: int
    repaired_subscription_count: int
    repaired_records: list[SubscriptionCycleRepairRecord] = field(default_factory=list)
    skipped_subscription_bids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "subscription_bid": self.subscription_bid,
            "inspected_subscription_count": self.inspected_subscription_count,
            "repaired_subscription_count": self.repaired_subscription_count,
            "repaired_records": [item.to_payload() for item in self.repaired_records],
            "skipped_subscription_bids": list(self.skipped_subscription_bids),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_payload()[key]


@dataclass(slots=True, frozen=True)
class _SubscriptionCycleEvidence:
    effective_from: datetime | None
    effective_to: datetime | None
    bill_order_bid: str | None
    wallet_bucket_bid: str | None
    reason: str
    is_current_window: bool = False


def _load_owned_subscription(
    creator_bid: str,
    subscription_bid: str,
) -> BillingSubscription:
    query = BillingSubscription.query.filter(
        BillingSubscription.deleted == 0,
        BillingSubscription.creator_bid == creator_bid,
    )
    if subscription_bid:
        query = query.filter(BillingSubscription.subscription_bid == subscription_bid)
    subscription = query.order_by(BillingSubscription.created_at.desc()).first()
    if subscription is None:
        raise_error("server.order.orderNotFound")
    return subscription


def load_effective_topup_subscription(
    creator_bid: str,
    *,
    as_of: datetime | None = None,
) -> BillingSubscription | None:
    return _load_primary_active_subscription(creator_bid, as_of=as_of)


def _load_topup_expiry_subscription_for_bucket(
    creator_bid: str,
    *,
    bucket_effective_from: datetime,
    bucket_effective_to: datetime | None,
) -> BillingSubscription | None:
    rows = BillingSubscription.query.filter(
        BillingSubscription.deleted == 0,
        BillingSubscription.creator_bid == creator_bid,
        BillingSubscription.status.in_(
            (
                BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                BILLING_SUBSCRIPTION_STATUS_PAUSED,
                BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            )
        ),
        BillingSubscription.current_period_end_at.isnot(None),
        BillingSubscription.current_period_end_at > bucket_effective_from,
    )
    if bucket_effective_to is not None:
        rows = rows.filter(
            (BillingSubscription.current_period_start_at.is_(None))
            | (BillingSubscription.current_period_start_at <= bucket_effective_to)
        )

    subscriptions = rows.order_by(
        BillingSubscription.created_at.asc(),
        BillingSubscription.id.asc(),
    ).all()
    if not subscriptions:
        return None

    def _sort_key(
        row: BillingSubscription,
    ) -> tuple[int, datetime, datetime, datetime, int]:
        product = _load_billing_product_by_bid(row.product_bid)
        product_sort_order = int(product.sort_order) if product is not None else -1
        return (
            product_sort_order,
            row.current_period_start_at or datetime.min,
            row.current_period_end_at or datetime.min,
            row.created_at or datetime.min,
            int(row.id or 0),
        )

    return max(subscriptions, key=_sort_key)


def _merge_provider_metadata(
    *,
    existing: Any,
    provider: str,
    source: str,
    event_type: str,
    payload: dict[str, Any],
    event_time: datetime | None,
) -> JsonObjectMap:
    if isinstance(existing, JsonObjectMap):
        metadata = existing.copy()
    elif isinstance(existing, dict):
        metadata = JsonObjectMap(values=dict(existing))
    else:
        metadata = JsonObjectMap()
    metadata["provider"] = provider
    metadata["latest_source"] = source
    metadata["latest_event_type"] = event_type
    metadata["latest_provider_payload"] = _normalize_json_value(payload)
    if event_time is not None:
        metadata["latest_event_time"] = event_time.isoformat()
    return _normalize_json_object(metadata)


def _resolve_pingxx_renewal_scheduled_at(
    subscription: BillingSubscription,
) -> datetime | None:
    scheduled_at = subscription.current_period_end_at
    if scheduled_at is None:
        return None
    renewal_at = scheduled_at - timedelta(days=7)
    current_period_start_at = subscription.current_period_start_at
    if current_period_start_at is not None and current_period_start_at > renewal_at:
        return current_period_start_at
    return renewal_at


def cancel_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> BillingSubscriptionDTO:
    """Mark the current subscription to cancel at period end."""

    with app.app_context():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
        if _normalize_bid(subscription.billing_provider) == "manual":
            raise_error("server.order.orderStatusError")
        if subscription.status not in (
            BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            BILLING_SUBSCRIPTION_STATUS_PAUSED,
            BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
        ):
            raise_error("server.order.orderStatusError")
        if subscription.provider_subscription_id:
            provider = get_payment_provider(subscription.billing_provider)
            provider_result = provider.cancel_subscription(
                subscription_bid=subscription.subscription_bid,
                provider_subscription_id=subscription.provider_subscription_id,
                app=app,
            )
            subscription.metadata_json = _merge_provider_metadata(
                existing=subscription.metadata_json,
                provider=subscription.billing_provider,
                source="api_cancel",
                event_type="cancel_subscription",
                payload=provider_result.raw_response,
                event_time=None,
            ).to_metadata_json()
        subscription.cancel_at_period_end = 1
        subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        subscription.updated_at = datetime.now()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        db.session.commit()
        return _serialize_subscription(app, subscription)


def resume_billing_subscription(
    app: Flask,
    creator_bid: str,
    payload: dict[str, Any],
) -> BillingSubscriptionDTO:
    """Resume a cancel-scheduled subscription."""

    with app.app_context():
        subscription = _load_owned_subscription(
            _normalize_bid(creator_bid),
            _normalize_bid(payload.get("subscription_bid")),
        )
        if _normalize_bid(subscription.billing_provider) == "manual":
            raise_error("server.order.orderStatusError")
        if subscription.status not in (
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
            BILLING_SUBSCRIPTION_STATUS_PAUSED,
        ):
            raise_error("server.order.orderStatusError")
        if subscription.provider_subscription_id:
            provider = get_payment_provider(subscription.billing_provider)
            provider_result = provider.resume_subscription(
                subscription_bid=subscription.subscription_bid,
                provider_subscription_id=subscription.provider_subscription_id,
                app=app,
            )
            subscription.metadata_json = _merge_provider_metadata(
                existing=subscription.metadata_json,
                provider=subscription.billing_provider,
                source="api_resume",
                event_type="resume_subscription",
                payload=provider_result.raw_response,
                event_time=None,
            ).to_metadata_json()
        subscription.cancel_at_period_end = 0
        subscription.status = BILLING_SUBSCRIPTION_STATUS_ACTIVE
        subscription.updated_at = datetime.now()
        _sync_subscription_lifecycle_events(app, subscription)
        db.session.add(subscription)
        db.session.commit()
        return _serialize_subscription(app, subscription)


def ensure_subscription_renewal_order(
    app: Flask,
    subscription: BillingSubscription,
    *,
    renewal_event_bid: str = "",
    scheduled_at: datetime | None = None,
) -> BillingOrder | None:
    cycle_start_at = scheduled_at or subscription.current_period_end_at
    provider_name = _normalize_bid(subscription.billing_provider)
    if provider_name == "pingxx" and subscription.current_period_end_at is not None:
        cycle_start_at = subscription.current_period_end_at
    if cycle_start_at is None:
        return None

    provider_reference_id = _normalize_bid(subscription.provider_subscription_id)
    if provider_name not in {"stripe", "pingxx"}:
        return None
    if provider_name == "stripe" and not provider_reference_id:
        return None

    product_bid = _normalize_bid(subscription.next_product_bid) or _normalize_bid(
        subscription.product_bid
    )
    product = _load_billing_product_by_bid(product_bid)
    if product is None:
        return None

    cycle_end_at = _calculate_billing_cycle_end(product, cycle_start_at=cycle_start_at)
    if cycle_end_at is None:
        return None

    order = _load_subscription_renewal_order_by_cycle(
        subscription.subscription_bid,
        cycle_start_at=cycle_start_at,
        cycle_end_at=cycle_end_at,
    )
    metadata = (
        dict(order.metadata_json)
        if order and isinstance(order.metadata_json, dict)
        else {}
    )
    metadata.update(
        _normalize_json_object(
            {
                "checkout_type": "subscription_renewal",
                "provider_reference_type": (
                    "subscription" if provider_name == "stripe" else "charge"
                ),
                "renewal_event_bid": _normalize_bid(renewal_event_bid) or None,
                "renewal_cycle_start_at": _serialize_order_metadata_datetime(
                    cycle_start_at
                ),
                "renewal_cycle_end_at": _serialize_order_metadata_datetime(
                    cycle_end_at
                ),
                "subscription_bid": subscription.subscription_bid,
                "product_bid": product.product_bid,
            }
        )
    )

    if order is None:
        order = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=subscription.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency=product.currency,
            payable_amount=int(product.price_amount or 0),
            paid_amount=0,
            payment_provider=provider_name,
            channel="subscription" if provider_name == "stripe" else "alipay_qr",
            provider_reference_id=provider_reference_id
            if provider_name == "stripe"
            else "",
            status=BILLING_ORDER_STATUS_PENDING,
            metadata_json=metadata,
        )
    else:
        order.creator_bid = subscription.creator_bid
        order.product_bid = product.product_bid
        order.currency = product.currency
        order.payable_amount = int(product.price_amount or 0)
        order.payment_provider = provider_name
        order.channel = order.channel or (
            "subscription" if provider_name == "stripe" else "alipay_qr"
        )
        if provider_name == "stripe":
            order.provider_reference_id = provider_reference_id
        order.metadata_json = metadata

    db.session.add(order)
    db.session.flush()
    return order


def _ensure_pingxx_renewal_applied_cycle(
    order: BillingOrder,
    product: BillingProduct,
) -> None:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or order.payment_provider != "pingxx"
        or order.paid_at is None
    ):
        return

    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    applied_cycle_start_at = _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_start_at",
    )
    applied_cycle_end_at = _extract_order_metadata_datetime(
        metadata,
        "applied_cycle_end_at",
    )
    if applied_cycle_start_at is not None and applied_cycle_end_at is not None:
        return

    renewal_cycle_end_at = _extract_order_metadata_datetime(
        metadata,
        "renewal_cycle_end_at",
    )
    if renewal_cycle_end_at is None or order.paid_at < renewal_cycle_end_at:
        return

    shifted_cycle_start_at = order.paid_at
    shifted_cycle_end_at = _calculate_billing_cycle_end(
        product,
        cycle_start_at=shifted_cycle_start_at,
    )
    if shifted_cycle_end_at is None:
        return

    metadata.update(
        _normalize_json_object(
            {
                "applied_cycle_start_at": _serialize_order_metadata_datetime(
                    shifted_cycle_start_at
                ),
                "applied_cycle_end_at": _serialize_order_metadata_datetime(
                    shifted_cycle_end_at
                ),
            }
        )
    )
    order.metadata_json = metadata
    db.session.add(order)


def _calculate_billing_cycle_end(
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
        return _add_months(cycle_start_at, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return _add_years(cycle_start_at, interval_count)
    return None


def _should_defer_pingxx_renewal_activation(order: BillingOrder) -> bool:
    if (
        order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        or order.payment_provider != "pingxx"
        or order.paid_at is None
    ):
        return False

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    if _extract_order_metadata_datetime(metadata, "applied_cycle_start_at") is not None:
        return False

    renewal_cycle_start_at = _extract_order_metadata_datetime(
        metadata,
        "renewal_cycle_start_at",
    )
    if renewal_cycle_start_at is None:
        return False
    return order.paid_at < renewal_cycle_start_at


def _activate_subscription_for_paid_order(
    app: Flask,
    order: BillingOrder,
    *,
    subscription: BillingSubscription | None = None,
    force: bool = False,
) -> bool:
    if not order.subscription_bid:
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False
    _ensure_pingxx_renewal_applied_cycle(order, product)

    subscription = subscription or _load_subscription_by_bid(order.subscription_bid)
    if subscription is None:
        return False

    effective_from = _resolve_credit_bucket_effective_from(
        order=order,
        default_effective_from=order.paid_at or datetime.now(),
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )

    if (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        and not force
        and _should_defer_pingxx_renewal_activation(order)
    ):
        return False

    if order.order_type in {
        BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
        BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    }:
        if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
            _activate_reserved_subscription_grant_for_order(
                app,
                order=order,
                effective_from=effective_from,
                effective_to=effective_to,
            )
        if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
            subscription.product_bid = (
                _normalize_bid(subscription.next_product_bid) or order.product_bid
            )
            subscription.next_product_bid = ""
        else:
            subscription.product_bid = order.product_bid
            subscription.next_product_bid = ""
        subscription.status = (
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            if subscription.cancel_at_period_end
            else BILLING_SUBSCRIPTION_STATUS_ACTIVE
        )
        subscription.current_period_start_at = effective_from
        subscription.current_period_end_at = effective_to
        subscription.last_renewed_at = effective_from
        _realign_active_topup_bucket_effective_to(
            creator_bid=order.creator_bid,
            effective_from=effective_from,
            effective_to=effective_to,
        )
    else:
        subscription.current_period_start_at = (
            subscription.current_period_start_at or effective_from
        )
        subscription.current_period_end_at = (
            subscription.current_period_end_at or effective_to
        )

    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    db.session.add(subscription)
    return True


def _realign_active_topup_bucket_effective_to(
    *,
    creator_bid: str,
    effective_from: datetime,
    effective_to: datetime | None,
) -> None:
    _realign_active_credit_bucket_effective_to(
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
        effective_from=effective_from,
        effective_to=effective_to,
        include_effective_to_boundary=True,
    )


def _realign_active_credit_bucket_effective_to(
    *,
    creator_bid: str,
    bucket_category: int,
    effective_from: datetime,
    effective_to: datetime | None,
    include_effective_to_boundary: bool,
) -> None:
    if effective_to is None:
        return

    bucket = load_primary_credit_bucket_by_category(
        creator_bid,
        bucket_category=bucket_category,
    )
    if bucket is None:
        return

    now = datetime.now()
    if bucket.effective_from is not None and bucket.effective_from > effective_from:
        return
    if bucket.effective_to is not None:
        if include_effective_to_boundary:
            if bucket.effective_to < effective_from:
                return
        elif bucket.effective_to <= effective_from:
            return
    if bucket.effective_to != effective_to:
        bucket.effective_to = effective_to
        bucket.updated_at = now
        db.session.add(bucket)

    grant_entries = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            (
                CreditLedgerEntry.expires_at.is_(None)
                | (CreditLedgerEntry.expires_at >= effective_from)
            ),
        )
        .order_by(CreditLedgerEntry.id.asc())
        .all()
    )
    for entry in grant_entries:
        entry.expires_at = effective_to
        entry.updated_at = now
        db.session.add(entry)


def _build_bucket_metadata_from_order(order: BillingOrder) -> dict[str, Any]:
    return _normalize_json_object(
        {
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": order.subscription_bid or None,
            "product_bid": order.product_bid,
            "payment_provider": order.payment_provider,
        }
    ).to_metadata_json()


def _load_grant_ledger_entry_for_order(order: BillingOrder) -> CreditLedgerEntry | None:
    return (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == f"grant:{order.bill_order_bid}",
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )


def _should_reserve_subscription_renewal_grant(
    order: BillingOrder,
    *,
    effective_from: datetime,
) -> bool:
    return (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
        and effective_from > datetime.now()
    )


def _expire_credit_bucket_balance_for_transition(
    app: Flask,
    *,
    wallet: CreditWallet,
    bucket: CreditWalletBucket,
    order: BillingOrder,
    transition_at: datetime,
) -> Decimal:
    available = _to_decimal(bucket.available_credits)
    if available <= 0:
        return Decimal("0")

    idempotency_key = f"cycle_expire:{order.bill_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        return Decimal("0")

    previous_effective_to = bucket.effective_to
    bucket.available_credits = Decimal("0")
    bucket.expired_credits = _quantize_credit_amount(
        _to_decimal(bucket.expired_credits) + available
    )
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)

    refresh_credit_wallet_snapshot(wallet)
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        source_type=resolve_bucket_source_type_for_category(bucket.bucket_category),
        source_bid=order.bill_order_bid,
        idempotency_key=idempotency_key,
        amount=-available,
        balance_after=_quantize_credit_amount(wallet.available_credits),
        expires_at=previous_effective_to,
        consumable_from=bucket.effective_from,
        metadata_json={
            "expired_bucket_bid": bucket.wallet_bucket_bid,
            "transition_order_bid": order.bill_order_bid,
            "transition_at": transition_at.isoformat(),
            "reason": "subscription_cycle_transition",
        },
    )
    db.session.add(ledger_entry)
    return available


def _upsert_paid_order_credit_bucket(
    app: Flask,
    *,
    wallet: CreditWallet,
    order: BillingOrder,
    grant_context: CreditGrantContext,
    amount: Decimal,
    effective_from: datetime,
    effective_to: datetime | None,
) -> tuple[CreditWalletBucket, bool]:
    bucket = load_or_create_credit_bucket_by_category(
        app,
        wallet=wallet,
        creator_bid=order.creator_bid,
        bucket_category=grant_context.bucket_category,
        source_bid=order.bill_order_bid,
        metadata=_build_bucket_metadata_from_order(order),
        effective_from=effective_from,
        effective_to=effective_to,
    )
    now = datetime.now()
    current_available = _to_decimal(bucket.available_credits)
    current_reserved = _to_decimal(bucket.reserved_credits)

    bucket.wallet_bid = wallet.wallet_bid
    bucket.bucket_category = grant_context.bucket_category
    bucket.source_type = resolve_bucket_source_type_for_category(
        grant_context.bucket_category
    )
    bucket.source_bid = order.bill_order_bid
    bucket.priority = grant_context.priority
    bucket.original_credits = _quantize_credit_amount(
        _to_decimal(bucket.original_credits) + amount
    )
    bucket.metadata_json = {
        **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
        **_build_bucket_metadata_from_order(order),
    }

    reserve_grant = False
    if grant_context.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        bucket.available_credits = _quantize_credit_amount(current_available + amount)
        bucket.reserved_credits = _quantize_credit_amount(current_reserved)
        if current_available > 0 or current_reserved > 0:
            if bucket.effective_from is None or bucket.effective_from > effective_from:
                bucket.effective_from = effective_from
        else:
            bucket.effective_from = effective_from
        bucket.effective_to = effective_to
    else:
        reserve_grant = _should_reserve_subscription_renewal_grant(
            order,
            effective_from=effective_from,
        )
        if reserve_grant:
            bucket.reserved_credits = _quantize_credit_amount(current_reserved + amount)
            if bucket.effective_from is None:
                bucket.effective_from = effective_from
            if bucket.effective_to is None:
                bucket.effective_to = effective_to
        else:
            if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
                _expire_credit_bucket_balance_for_transition(
                    app,
                    wallet=wallet,
                    bucket=bucket,
                    order=order,
                    transition_at=effective_from,
                )
            bucket.available_credits = _quantize_credit_amount(
                _to_decimal(bucket.available_credits) + amount
            )
            bucket.reserved_credits = _quantize_credit_amount(
                _to_decimal(bucket.reserved_credits)
            )
            bucket.effective_from = effective_from
            bucket.effective_to = effective_to

    bucket.updated_at = now
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)
    return bucket, reserve_grant


def _activate_reserved_subscription_grant_for_order(
    app: Flask,
    *,
    order: BillingOrder,
    effective_from: datetime,
    effective_to: datetime | None,
) -> bool:
    grant_entry = _load_grant_ledger_entry_for_order(order)
    if grant_entry is None:
        return False

    metadata = _normalize_json_object(grant_entry.metadata_json)
    if str(metadata.get("bucket_credit_state") or "").strip().lower() != "reserved":
        return False

    bucket = None
    if _normalize_bid(grant_entry.wallet_bucket_bid):
        bucket = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.wallet_bucket_bid == grant_entry.wallet_bucket_bid,
            )
            .order_by(CreditWalletBucket.id.desc())
            .first()
        )
    if bucket is None:
        bucket = load_primary_credit_bucket_by_category(
            order.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        )
    if bucket is None:
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    _expire_credit_bucket_balance_for_transition(
        app,
        wallet=wallet,
        bucket=bucket,
        order=order,
        transition_at=effective_from,
    )

    now = datetime.now()
    release_amount = min(
        _to_decimal(grant_entry.amount),
        _to_decimal(bucket.reserved_credits),
    )
    bucket.wallet_bid = wallet.wallet_bid
    bucket.bucket_category = CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    bucket.source_type = resolve_bucket_source_type_for_category(
        CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    )
    bucket.source_bid = order.bill_order_bid
    bucket.priority = resolve_credit_bucket_priority(
        CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
    )
    bucket.reserved_credits = _quantize_credit_amount(
        _to_decimal(bucket.reserved_credits) - release_amount
    )
    bucket.available_credits = _quantize_credit_amount(
        _to_decimal(bucket.available_credits) + release_amount
    )
    bucket.effective_from = effective_from
    bucket.effective_to = effective_to
    bucket.metadata_json = {
        **(bucket.metadata_json if isinstance(bucket.metadata_json, dict) else {}),
        **_build_bucket_metadata_from_order(order),
    }
    bucket.updated_at = now
    sync_credit_bucket_status(bucket)
    db.session.add(bucket)

    metadata["bucket_credit_state"] = "available"
    metadata["activated_at"] = now.isoformat()
    grant_entry.expires_at = effective_to
    grant_entry.consumable_from = effective_from
    grant_entry.metadata_json = metadata.to_metadata_json()
    grant_entry.updated_at = now
    db.session.add(grant_entry)

    refresh_credit_wallet_snapshot(wallet)
    persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        updated_at=now,
    )
    grant_entry.balance_after = _quantize_credit_amount(wallet.available_credits)
    return True


def _grant_paid_order_credits(app: Flask, order: BillingOrder) -> bool:
    grant_context = _resolve_credit_grant_context(order)
    if grant_context is None:
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False
    _ensure_pingxx_renewal_applied_cycle(order, product)

    amount = _quantize_credit_amount(product.credit_amount)
    if amount <= 0:
        return False

    idempotency_key = f"grant:{order.bill_order_bid}"
    existing_entry = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == order.creator_bid,
            CreditLedgerEntry.idempotency_key == idempotency_key,
        )
        .order_by(CreditLedgerEntry.id.desc())
        .first()
    )
    if existing_entry is not None:
        _activate_subscription_for_paid_order(app, order)
        return False

    wallet = _load_or_create_credit_wallet(app, order.creator_bid)
    effective_from = _resolve_credit_bucket_effective_from(
        order=order,
        default_effective_from=order.paid_at or datetime.now(),
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=order,
        product=product,
        effective_from=effective_from,
    )

    bucket, reserve_grant = _upsert_paid_order_credit_bucket(
        app,
        wallet=wallet,
        order=order,
        grant_context=grant_context,
        amount=amount,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    if (
        grant_context.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        and order.order_type
        in {
            BILLING_ORDER_TYPE_SUBSCRIPTION_START,
            BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
        }
    ):
        _realign_active_credit_bucket_effective_to(
            creator_bid=order.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            effective_from=effective_from,
            effective_to=effective_to,
            include_effective_to_boundary=False,
        )

    refresh_credit_wallet_snapshot(wallet)
    balance_after = _quantize_credit_amount(wallet.available_credits)
    next_lifetime_granted = _quantize_credit_amount(
        _to_decimal(wallet.lifetime_granted_credits) + amount
    )
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=grant_context.source_type,
        source_bid=order.bill_order_bid,
        idempotency_key=idempotency_key,
        amount=amount,
        balance_after=balance_after,
        expires_at=effective_to,
        consumable_from=effective_from,
        metadata_json=_normalize_json_object(
            {
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": order.subscription_bid or None,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": grant_context.grant_reason,
                "bucket_credit_state": "reserved" if reserve_grant else "available",
                "reserved_until": (
                    effective_from.isoformat() if reserve_grant else None
                ),
            }
        ).to_metadata_json(),
    )

    wallet.available_credits = balance_after
    persist_credit_wallet_snapshot(
        wallet,
        available_credits=wallet.available_credits,
        reserved_credits=wallet.reserved_credits,
        lifetime_granted_credits=next_lifetime_granted,
        updated_at=datetime.now(),
    )
    db.session.add(ledger_entry)

    _activate_subscription_for_paid_order(app, order)

    return True


def _resolve_credit_grant_context(order: BillingOrder) -> CreditGrantContext | None:
    bucket_category = resolve_bucket_category_from_order_type(
        int(order.order_type or 0)
    )
    if bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION:
        return CreditGrantContext(
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            priority=resolve_credit_bucket_priority(
                CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            ),
            grant_reason="subscription",
        )
    if bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP:
        return CreditGrantContext(
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            priority=resolve_credit_bucket_priority(CREDIT_BUCKET_CATEGORY_TOPUP),
            grant_reason="topup",
        )
    return None


def _load_billing_product_by_bid(product_bid: str) -> BillingProduct | None:
    normalized_product_bid = _normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == normalized_product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _load_or_create_credit_wallet(app: Flask, creator_bid: str) -> CreditWallet:
    wallet = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid == creator_bid,
        )
        .order_by(CreditWallet.id.desc())
        .first()
    )
    if wallet is not None:
        return wallet

    wallet = CreditWallet(
        wallet_bid=generate_id(app),
        creator_bid=creator_bid,
        available_credits=Decimal("0"),
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal("0"),
        lifetime_consumed_credits=Decimal("0"),
        last_settled_usage_id=0,
        version=0,
    )
    db.session.add(wallet)
    db.session.flush()
    return wallet


def _resolve_credit_bucket_effective_to(
    *,
    order: BillingOrder,
    product: BillingProduct,
    effective_from: datetime,
) -> datetime | None:
    if order.order_type == BILLING_ORDER_TYPE_TOPUP:
        return _resolve_topup_bucket_effective_to(
            creator_bid=order.creator_bid,
            effective_from=effective_from,
        )

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    resolved_cycle_end_at = _extract_resolved_order_cycle_end_at(metadata)
    if resolved_cycle_end_at is not None:
        return resolved_cycle_end_at

    if (
        order.subscription_bid
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
    ):
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if (
            subscription is not None
            and subscription.current_period_start_at == effective_from
            and subscription.current_period_end_at is not None
            and subscription.current_period_end_at > effective_from
        ):
            return subscription.current_period_end_at

    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_DAY:
        return effective_from + timedelta(days=interval_count)
    if interval == BILLING_INTERVAL_MONTH:
        return _add_months(effective_from, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return _add_years(effective_from, interval_count)
    return None


def _resolve_topup_bucket_effective_to(
    *,
    creator_bid: str,
    effective_from: datetime,
) -> datetime | None:
    subscription = load_effective_topup_subscription(
        creator_bid,
        as_of=effective_from,
    )
    if subscription is None:
        return None
    return subscription.current_period_end_at


def repair_topup_grant_expiries(
    app: Flask,
    *,
    creator_bid: str,
) -> TopupExpiryRepairResult:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return TopupExpiryRepairResult(
            status="noop",
            creator_bid=None,
            inspected_bucket_count=0,
            repaired_bucket_count=0,
            repaired_ledger_count=0,
        )

    with app.app_context():
        buckets = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
                CreditWalletBucket.source_type == CREDIT_SOURCE_TYPE_TOPUP,
            )
            .order_by(
                CreditWalletBucket.created_at.asc(),
                CreditWalletBucket.id.asc(),
            )
            .all()
        )
        if not buckets:
            return TopupExpiryRepairResult(
                status="noop",
                creator_bid=normalized_creator_bid,
                inspected_bucket_count=0,
                repaired_bucket_count=0,
                repaired_ledger_count=0,
            )

        repaired_at = datetime.now()
        repaired_records: list[TopupExpiryRepairRecord] = []
        skipped_bucket_bids: list[str] = []
        repaired_ledger_count = 0

        for bucket in buckets:
            available = _to_decimal(bucket.available_credits)
            if available <= 0:
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            reference_effective_from = bucket.effective_from or (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == normalized_creator_bid,
                    BillingOrder.bill_order_bid == _normalize_bid(bucket.source_bid),
                    BillingOrder.order_type == BILLING_ORDER_TYPE_TOPUP,
                )
                .order_by(BillingOrder.id.desc())
                .with_entities(BillingOrder.paid_at)
                .scalar()
            )
            if reference_effective_from is None:
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            candidate_subscription = _load_topup_expiry_subscription_for_bucket(
                normalized_creator_bid,
                bucket_effective_from=reference_effective_from,
                bucket_effective_to=bucket.effective_to,
            )
            if (
                candidate_subscription is None
                or candidate_subscription.current_period_end_at is None
            ):
                skipped_bucket_bids.append(bucket.wallet_bucket_bid)
                continue

            order = (
                BillingOrder.query.filter(
                    BillingOrder.deleted == 0,
                    BillingOrder.creator_bid == normalized_creator_bid,
                    BillingOrder.bill_order_bid == _normalize_bid(bucket.source_bid),
                    BillingOrder.order_type == BILLING_ORDER_TYPE_TOPUP,
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )
            expected_effective_to = candidate_subscription.current_period_end_at

            grant_entries = (
                CreditLedgerEntry.query.filter(
                    CreditLedgerEntry.deleted == 0,
                    CreditLedgerEntry.creator_bid == normalized_creator_bid,
                    CreditLedgerEntry.wallet_bucket_bid == bucket.wallet_bucket_bid,
                    CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                )
                .order_by(
                    CreditLedgerEntry.created_at.asc(), CreditLedgerEntry.id.asc()
                )
                .all()
            )

            previous_effective_to = bucket.effective_to
            updated_ledger_bids: list[str] = []
            if previous_effective_to != expected_effective_to:
                bucket.effective_to = expected_effective_to
                bucket.updated_at = repaired_at
                db.session.add(bucket)

            for entry in grant_entries:
                if entry.expires_at == expected_effective_to:
                    continue
                entry.expires_at = expected_effective_to
                entry.updated_at = repaired_at
                db.session.add(entry)
                updated_ledger_bids.append(entry.ledger_bid)

            if (
                previous_effective_to == expected_effective_to
                and not updated_ledger_bids
            ):
                continue

            repaired_ledger_count += len(updated_ledger_bids)
            repaired_records.append(
                TopupExpiryRepairRecord(
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    bill_order_bid=order.bill_order_bid if order is not None else None,
                    previous_effective_to=previous_effective_to,
                    effective_to=expected_effective_to,
                    ledger_bids=tuple(updated_ledger_bids),
                )
            )

        if repaired_records:
            db.session.commit()
        else:
            db.session.rollback()

        return TopupExpiryRepairResult(
            status="repaired" if repaired_records else "noop",
            creator_bid=normalized_creator_bid,
            inspected_bucket_count=len(buckets),
            repaired_bucket_count=len(repaired_records),
            repaired_ledger_count=repaired_ledger_count,
            repaired_records=repaired_records,
            skipped_bucket_bids=skipped_bucket_bids,
        )


def repair_subscription_cycle_mismatches(
    app: Flask,
    *,
    creator_bid: str = "",
    subscription_bid: str = "",
) -> SubscriptionCycleRepairResult:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_subscription_bid = _normalize_bid(subscription_bid)

    with app.app_context():
        query = BillingSubscription.query.filter(BillingSubscription.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
        if normalized_subscription_bid:
            query = query.filter(
                BillingSubscription.subscription_bid == normalized_subscription_bid
            )
        subscriptions = query.order_by(
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        ).all()
        repaired_at = datetime.now()
        repaired_records: list[SubscriptionCycleRepairRecord] = []
        skipped_subscription_bids: list[str] = []

        for subscription in subscriptions:
            evidence = _select_subscription_cycle_repair_evidence(
                subscription,
                as_of=repaired_at,
            )
            if (
                evidence is None
                or evidence.effective_from is None
                or evidence.effective_to is None
            ):
                skipped_subscription_bids.append(subscription.subscription_bid)
                continue

            current_start_at = subscription.current_period_start_at
            current_end_at = subscription.current_period_end_at
            matches_evidence = (
                current_start_at == evidence.effective_from
                and current_end_at == evidence.effective_to
            )
            is_future_dated = (
                current_start_at is not None and current_start_at > repaired_at
            )
            is_missing_window = current_start_at is None or current_end_at is None
            is_invalid_window = (
                current_start_at is not None
                and current_end_at is not None
                and current_end_at <= current_start_at
            )
            mismatched_current_window = (
                evidence.is_current_window and not matches_evidence
            )
            if not (
                is_missing_window
                or is_invalid_window
                or is_future_dated
                or mismatched_current_window
            ):
                skipped_subscription_bids.append(subscription.subscription_bid)
                continue

            subscription.current_period_start_at = evidence.effective_from
            subscription.current_period_end_at = evidence.effective_to
            if evidence.effective_to > repaired_at:
                subscription.status = (
                    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
                    if subscription.cancel_at_period_end
                    else BILLING_SUBSCRIPTION_STATUS_ACTIVE
                )
            subscription.last_renewed_at = evidence.effective_from
            subscription.updated_at = repaired_at
            _sync_subscription_lifecycle_events(app, subscription)
            db.session.add(subscription)
            repaired_records.append(
                SubscriptionCycleRepairRecord(
                    subscription_bid=subscription.subscription_bid,
                    creator_bid=subscription.creator_bid,
                    bill_order_bid=evidence.bill_order_bid,
                    wallet_bucket_bid=evidence.wallet_bucket_bid,
                    previous_current_period_start_at=current_start_at,
                    previous_current_period_end_at=current_end_at,
                    current_period_start_at=evidence.effective_from,
                    current_period_end_at=evidence.effective_to,
                    reason=evidence.reason,
                )
            )

        if repaired_records:
            db.session.commit()
        else:
            db.session.rollback()

        return SubscriptionCycleRepairResult(
            status="repaired" if repaired_records else "noop",
            creator_bid=normalized_creator_bid or None,
            subscription_bid=normalized_subscription_bid or None,
            inspected_subscription_count=len(subscriptions),
            repaired_subscription_count=len(repaired_records),
            repaired_records=repaired_records,
            skipped_subscription_bids=skipped_subscription_bids,
        )


def _select_subscription_cycle_repair_evidence(
    subscription: BillingSubscription,
    *,
    as_of: datetime,
) -> _SubscriptionCycleEvidence | None:
    paid_orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == subscription.creator_bid,
            BillingOrder.subscription_bid == subscription.subscription_bid,
            BillingOrder.status == BILLING_ORDER_STATUS_PAID,
            BillingOrder.order_type.in_(
                (
                    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                )
            ),
        )
        .order_by(
            BillingOrder.paid_at.desc(),
            BillingOrder.created_at.desc(),
            BillingOrder.id.desc(),
        )
        .all()
    )
    if not paid_orders:
        return None

    bucket = load_primary_credit_bucket_by_category(
        subscription.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    )
    if bucket is not None:
        if int(bucket.status or 0) in (
            CREDIT_BUCKET_STATUS_ACTIVE,
            CREDIT_BUCKET_STATUS_EXHAUSTED,
        ):
            if (bucket.effective_from is None or bucket.effective_from <= as_of) and (
                bucket.effective_to is None or bucket.effective_to > as_of
            ):
                return _SubscriptionCycleEvidence(
                    effective_from=bucket.effective_from,
                    effective_to=bucket.effective_to,
                    bill_order_bid=bucket.source_bid or None,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    reason="current_subscription_bucket",
                    is_current_window=True,
                )
        return _SubscriptionCycleEvidence(
            effective_from=bucket.effective_from,
            effective_to=bucket.effective_to,
            bill_order_bid=bucket.source_bid or None,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            reason="latest_subscription_bucket",
            is_current_window=False,
        )

    latest_paid_order = paid_orders[0]
    product = _load_billing_product_by_bid(latest_paid_order.product_bid)
    if product is None:
        return None
    default_effective_from = (
        latest_paid_order.paid_at or latest_paid_order.created_at or as_of
    )
    effective_from = _resolve_credit_bucket_effective_from(
        order=latest_paid_order,
        default_effective_from=default_effective_from,
    )
    effective_to = _resolve_credit_bucket_effective_to(
        order=latest_paid_order,
        product=product,
        effective_from=effective_from,
    )
    return _SubscriptionCycleEvidence(
        effective_from=effective_from,
        effective_to=effective_to,
        bill_order_bid=latest_paid_order.bill_order_bid,
        wallet_bucket_bid=None,
        reason="latest_paid_subscription_order",
        is_current_window=(effective_from is None or effective_from <= as_of)
        and (effective_to is None or effective_to > as_of),
    )


def _resolve_credit_bucket_effective_from(
    *,
    order: BillingOrder,
    default_effective_from: datetime,
) -> datetime:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return default_effective_from
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    renewal_cycle_start_at = _extract_resolved_order_cycle_start_at(metadata)
    if renewal_cycle_start_at is not None:
        return renewal_cycle_start_at
    subscription = _load_subscription_by_bid(order.subscription_bid)
    if (
        subscription is None
        or subscription.current_period_end_at is None
        or subscription.current_period_end_at <= default_effective_from
    ):
        return default_effective_from
    return subscription.current_period_end_at


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


def _sync_subscription_lifecycle_events(
    app: Flask,
    subscription: BillingSubscription,
) -> None:
    scheduled_at = subscription.current_period_end_at
    provider_name = _normalize_bid(subscription.billing_provider)
    product = _load_billing_product_by_bid(subscription.product_bid)

    if subscription.status in {
        BILLING_SUBSCRIPTION_STATUS_CANCELED,
        BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    }:
        subscription.grace_period_end_at = None
        _cancel_subscription_renewal_events(subscription.subscription_bid)
        return

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        grace_period_end_at = (
            subscription.grace_period_end_at
            or scheduled_at
            or subscription.current_period_start_at
        )
        subscription.grace_period_end_at = grace_period_end_at
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(
                BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ),
        )
        if grace_period_end_at is not None:
            _upsert_subscription_renewal_event(
                app,
                subscription,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
                scheduled_at=grace_period_end_at,
            )
        return

    subscription.grace_period_end_at = None
    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_RETRY,),
    )

    if scheduled_at is None:
        _cancel_subscription_renewal_events(subscription.subscription_bid)
        return

    if subscription.cancel_at_period_end or (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
    ):
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            scheduled_at=scheduled_at,
        )
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(
                BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
                BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ),
        )
        return

    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,),
    )

    if subscription.next_product_bid:
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            scheduled_at=scheduled_at,
        )
    else:
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,),
        )

    if (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        and product is not None
        and int(product.auto_renew_enabled or 0) == 1
    ):
        renewal_scheduled_at = scheduled_at
        if provider_name == "pingxx":
            renewal_scheduled_at = _resolve_pingxx_renewal_scheduled_at(subscription)
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            scheduled_at=renewal_scheduled_at or scheduled_at,
        )
        if provider_name == "pingxx":
            _upsert_subscription_renewal_event(
                app,
                subscription,
                event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
                scheduled_at=scheduled_at,
            )
        else:
            _cancel_subscription_renewal_events(
                subscription.subscription_bid,
                event_types=(BILLING_RENEWAL_EVENT_TYPE_EXPIRE,),
            )
        return

    if (
        subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
        and product is not None
    ):
        _upsert_subscription_renewal_event(
            app,
            subscription,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=scheduled_at,
        )
        _cancel_subscription_renewal_events(
            subscription.subscription_bid,
            event_types=(BILLING_RENEWAL_EVENT_TYPE_RENEWAL,),
        )
        return

    _cancel_subscription_renewal_events(
        subscription.subscription_bid,
        event_types=(
            BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
        ),
    )


def _upsert_subscription_renewal_event(
    app: Flask,
    subscription: BillingSubscription,
    *,
    event_type: int,
    scheduled_at: datetime,
) -> None:
    payload = _normalize_json_object(
        {
            "subscription_bid": subscription.subscription_bid,
            "creator_bid": subscription.creator_bid,
            "product_bid": subscription.product_bid,
            "next_product_bid": _normalize_bid(subscription.next_product_bid) or None,
            "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(
                subscription.status,
                "draft",
            ),
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
        }
    )
    event = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription.subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.scheduled_at == scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .first()
    )
    if event is None:
        event = BillingRenewalEvent(
            renewal_event_bid=generate_id(app),
            subscription_bid=subscription.subscription_bid,
            creator_bid=subscription.creator_bid,
            event_type=event_type,
            scheduled_at=scheduled_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json=payload.to_metadata_json(),
            processed_at=None,
        )
    else:
        event.creator_bid = subscription.creator_bid
        event.status = BILLING_RENEWAL_EVENT_STATUS_PENDING
        event.last_error = ""
        event.payload_json = payload.to_metadata_json()
        event.processed_at = None
        event.updated_at = datetime.now()

    db.session.add(event)
    _cancel_stale_subscription_renewal_events(
        subscription.subscription_bid,
        event_type=event_type,
        keep_scheduled_at=scheduled_at,
    )


def _cancel_stale_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_type: int,
    keep_scheduled_at: datetime,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type == event_type,
            BillingRenewalEvent.status.in_(_PENDING_RENEWAL_EVENT_STATUSES),
            BillingRenewalEvent.scheduled_at != keep_scheduled_at,
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = datetime.now()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)


def _cancel_subscription_renewal_events(
    subscription_bid: str,
    *,
    event_types: tuple[int, ...] = _MANAGED_RENEWAL_EVENT_TYPES,
) -> None:
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid == subscription_bid,
            BillingRenewalEvent.event_type.in_(event_types),
            BillingRenewalEvent.status.in_(_PENDING_RENEWAL_EVENT_STATUSES),
        )
        .order_by(BillingRenewalEvent.id.desc())
        .all()
    )
    now = datetime.now()
    for row in rows:
        row.status = BILLING_RENEWAL_EVENT_STATUS_CANCELED
        row.processed_at = now
        row.updated_at = now
        db.session.add(row)


activate_subscription_for_paid_order = _activate_subscription_for_paid_order
grant_paid_order_credits = _grant_paid_order_credits
load_subscription_by_bid = _load_subscription_by_bid
load_latest_subscription_renewal_order = _load_latest_subscription_renewal_order
load_subscription_renewal_order_by_cycle = _load_subscription_renewal_order_by_cycle
load_billing_product_by_bid = _load_billing_product_by_bid
load_or_create_credit_wallet = _load_or_create_credit_wallet
sync_subscription_lifecycle_events = _sync_subscription_lifecycle_events
merge_provider_metadata = _merge_provider_metadata
