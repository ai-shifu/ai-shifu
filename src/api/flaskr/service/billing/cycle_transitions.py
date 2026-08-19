"""Cycle window resolution helpers for billing state transitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from .consts import (
    BILLING_INTERVAL_DAY,
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_YEAR,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
)
from .queries import (
    extract_resolved_order_cycle_end_at,
    extract_resolved_order_cycle_start_at,
)


def resolve_order_effective_from(
    *,
    order: Any,
    default_effective_from: datetime,
    load_subscription_by_bid: Callable[[str], Any | None],
) -> datetime:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return default_effective_from
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
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
    order: Any,
    product: Any,
    effective_from: datetime,
    load_subscription_by_bid: Callable[[str], Any | None],
    resolve_topup_effective_to: Callable[[str, datetime], datetime | None],
    is_self_managed_order: Callable[[Any], bool],
    calculate_provider_cycle_end: Callable[[Any, datetime], datetime | None],
    calculate_self_managed_cycle_end: Callable[[Any, datetime], datetime | None],
) -> datetime | None:
    if order.order_type == BILLING_ORDER_TYPE_TOPUP:
        return resolve_topup_effective_to(order.creator_bid, effective_from)

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    resolved_cycle_end_at = extract_resolved_order_cycle_end_at(metadata)
    if resolved_cycle_end_at is not None:
        return resolved_cycle_end_at

    if (
        order.subscription_bid
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START
    ):
        subscription = load_subscription_by_bid(order.subscription_bid)
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
