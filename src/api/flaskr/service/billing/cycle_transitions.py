"""Cycle window resolution helpers for billing state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
)
from .payment_policy import is_provider_managed_payment_provider
from .queries import (
    extract_order_metadata_datetime,
    extract_resolved_order_cycle_end_at,
    extract_resolved_order_cycle_start_at,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def resolve_order_effective_from(
    *,
    order: object,
    default_effective_from: datetime,
    load_subscription_by_bid: Callable[[str], object | None],
) -> datetime:
    """Resolve order effective from."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        if _has_provider_period(order):
            return (
                extract_order_metadata_datetime(metadata, "provider_period_start_at")
                or default_effective_from
            )
        return default_effective_from
    renewal_cycle_start_at = extract_resolved_order_cycle_start_at(metadata)
    if renewal_cycle_start_at is not None:
        return renewal_cycle_start_at
    subscription = load_subscription_by_bid(order.subscription_bid)
    if (
        subscription is None
        or subscription.current_period_end_at is None
        or subscription.current_period_end_at <= default_effective_from
    ):
        return default_effective_from
    return subscription.current_period_end_at


def resolve_order_effective_to(
    *,
    order: object,
    product: object,
    effective_from: datetime,
    load_subscription_by_bid: Callable[[str], object | None],
    resolve_topup_effective_to: Callable[[str, datetime], datetime | None],
    is_self_managed_order: Callable[[object], bool],
    calculate_provider_cycle_end: Callable[[object, datetime], datetime | None],
    calculate_self_managed_cycle_end: Callable[[object, datetime], datetime | None],
) -> datetime | None:
    """Resolve order effective to."""
    if order.order_type == BILLING_ORDER_TYPE_TOPUP:
        return resolve_topup_effective_to(order.creator_bid, effective_from)

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    resolved_cycle_end_at = extract_resolved_order_cycle_end_at(metadata)
    if resolved_cycle_end_at is not None:
        return resolved_cycle_end_at
    if order.subscription_bid and (
        order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
        or _has_provider_period(order)
    ):
        subscription = load_subscription_by_bid(order.subscription_bid)
        if (
            subscription is not None
            and subscription.current_period_start_at == effective_from
            and subscription.current_period_end_at is not None
            and subscription.current_period_end_at > effective_from
        ):
            return subscription.current_period_end_at

    if _has_provider_period(order):
        provider_period_end = extract_order_metadata_datetime(
            metadata, "provider_period_end_at"
        )
        if provider_period_end is not None:
            return provider_period_end

    interval = int(product.billing_interval or 0)
    interval_count = max(int(product.billing_interval_count or 0), 0)
    if interval_count <= 0:
        return None
    if interval == BILLING_INTERVAL_DAY:
        if is_self_managed_order(order):
            return calculate_self_managed_cycle_end(product, effective_from)
        return effective_from + timedelta(days=interval_count)
    if interval == BILLING_INTERVAL_MONTH:
        if is_self_managed_order(order):
            return calculate_self_managed_cycle_end(product, effective_from)
        return calculate_provider_cycle_end(product, effective_from)
    if interval == BILLING_INTERVAL_YEAR:
        if is_self_managed_order(order):
            return calculate_self_managed_cycle_end(product, effective_from)
        return calculate_provider_cycle_end(product, effective_from)
    return None


def _has_provider_period(order: object) -> bool:
    """Identify initial or upgraded contracts with an authoritative period snapshot."""
    return order.order_type in {
        BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    } and is_provider_managed_payment_provider(getattr(order, "payment_provider", ""))
