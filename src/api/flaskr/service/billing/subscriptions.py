"""Subscription lifecycle, renewal orchestration, and credit grants."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_providers import get_payment_provider
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
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
    load_subscription_by_bid as _load_subscription_by_bid,
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
    serialize_order_metadata_datetime as _serialize_order_metadata_datetime,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import normalize_json_value as _normalize_json_value
from .primitives import to_decimal as _to_decimal
from .serializers import serialize_subscription as _serialize_subscription
from .wallets import (
    persist_credit_wallet_snapshot,
    refresh_credit_wallet_snapshot,
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
            billing_order_bid=generate_id(app),
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


def _grant_paid_order_credits(app: Flask, order: BillingOrder) -> bool:
    grant_context = _resolve_credit_grant_context(order)
    if grant_context is None:
        return False

    product = _load_billing_product_by_bid(order.product_bid)
    if product is None:
        return False
    _ensure_pingxx_renewal_applied_cycle(order, product)

    amount = _to_decimal(product.credit_amount)
    if amount <= 0:
        return False

    idempotency_key = f"grant:{order.billing_order_bid}"
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

    bucket = CreditWalletBucket(
        wallet_bucket_bid=generate_id(app),
        wallet_bid=wallet.wallet_bid,
        creator_bid=order.creator_bid,
        bucket_category=grant_context.bucket_category,
        source_type=grant_context.source_type,
        source_bid=order.billing_order_bid,
        priority=grant_context.priority,
        original_credits=amount,
        available_credits=amount,
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=effective_from,
        effective_to=effective_to,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json=_normalize_json_object(
            {
                "billing_order_bid": order.billing_order_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
            }
        ).to_metadata_json(),
    )

    db.session.add(bucket)
    sync_credit_bucket_status(bucket)
    refresh_credit_wallet_snapshot(wallet)
    balance_after = _to_decimal(wallet.available_credits)
    next_lifetime_granted = _to_decimal(wallet.lifetime_granted_credits) + amount
    ledger_entry = CreditLedgerEntry(
        ledger_bid=generate_id(app),
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=grant_context.source_type,
        source_bid=order.billing_order_bid,
        idempotency_key=idempotency_key,
        amount=amount,
        balance_after=balance_after,
        expires_at=effective_to,
        consumable_from=effective_from,
        metadata_json=_normalize_json_object(
            {
                "billing_order_bid": order.billing_order_bid,
                "subscription_bid": order.subscription_bid or None,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": grant_context.grant_reason,
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
    if order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        renewal_cycle_end_at = _extract_resolved_order_cycle_end_at(metadata)
        if renewal_cycle_end_at is not None:
            return renewal_cycle_end_at

    if (
        order.subscription_bid
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
    ):
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None and subscription.current_period_end_at is not None:
            return subscription.current_period_end_at

    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_MONTH:
        return _add_months(effective_from, interval_count)
    if interval == BILLING_INTERVAL_YEAR:
        return _add_years(effective_from, interval_count)
    return None


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
