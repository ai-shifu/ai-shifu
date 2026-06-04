"""Subscription preorder state helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
)
from .models import BillingOrder, BillingProduct, BillingSubscription
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object

CHECKOUT_ACTION_PREORDER = "preorder"
CHECKOUT_ACTION_UPGRADE_IMMEDIATE = "upgrade_immediate"

PREORDER_CHECKOUT_TYPE = "subscription_preorder"
PREORDER_STATE_PENDING_EFFECTIVE = "pending_effective"
PREORDER_STATE_EFFECTIVE_APPLIED = "effective_applied"
PREORDER_STATE_ABSORBED_BY_UPGRADE = "absorbed_by_upgrade"
PREORDER_STATE_VOIDED_ADMIN_ONLY = "voided_admin_only"

PLAN_TIER_METADATA_KEY = "plan_tier"
SUBSCRIPTION_PREORDER_ORDER_BID_KEY = "preorder_order_bid"
SUBSCRIPTION_PREORDER_PROVIDER_KEY = "preorder_payment_provider"
SUBSCRIPTION_PREORDER_CHANNEL_KEY = "preorder_channel"

_ACTIVE_PREORDER_STATES = {PREORDER_STATE_PENDING_EFFECTIVE}
_ACTIVE_PREORDER_ORDER_STATUSES = {BILLING_ORDER_STATUS_PAID}


def normalize_checkout_action(value: Any) -> str:
    return str(value or CHECKOUT_ACTION_UPGRADE_IMMEDIATE).strip().lower()


def resolve_plan_tier(product: BillingProduct | None) -> int | None:
    if product is None:
        return None
    metadata = product.metadata_json if isinstance(product.metadata_json, dict) else {}
    raw_tier = metadata.get(PLAN_TIER_METADATA_KEY)
    try:
        return int(raw_tier)
    except (TypeError, ValueError):
        pass
    try:
        return int(product.sort_order)
    except (TypeError, ValueError):
        return None


def is_preorder_order(order: BillingOrder | None) -> bool:
    if order is None:
        return False
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return str(metadata.get("checkout_type") or "").strip() == PREORDER_CHECKOUT_TYPE


def preorder_state(order: BillingOrder | None) -> str:
    if not is_preorder_order(order):
        return ""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return str(metadata.get("preorder_state") or "").strip()


def is_active_preorder_order(order: BillingOrder | None) -> bool:
    return (
        is_preorder_order(order)
        and preorder_state(order) in _ACTIVE_PREORDER_STATES
        and int(order.status or 0) in _ACTIVE_PREORDER_ORDER_STATUSES
    )


def load_active_preorder_order(subscription_bid: str) -> BillingOrder | None:
    normalized_subscription_bid = _normalize_bid(subscription_bid)
    if not normalized_subscription_bid:
        return None

    rows = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.subscription_bid == normalized_subscription_bid,
            BillingOrder.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            BillingOrder.status.in_(tuple(_ACTIVE_PREORDER_ORDER_STATUSES)),
        )
        .order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        .all()
    )
    for row in rows:
        if is_active_preorder_order(row):
            return row
    return None


def build_preorder_order_metadata(
    *,
    subscription: BillingSubscription,
    current_product: BillingProduct,
    target_product: BillingProduct,
    effective_at: datetime,
    cycle_end_at: datetime,
    checkout_started: bool = True,
) -> dict[str, Any]:
    return _normalize_json_object(
        {
            "checkout_type": PREORDER_CHECKOUT_TYPE,
            "checkout_started": checkout_started,
            "preorder_state": PREORDER_STATE_PENDING_EFFECTIVE,
            "current_product_bid": current_product.product_bid,
            "target_product_bid": target_product.product_bid,
            "preorder_target_product_bid": target_product.product_bid,
            "preorder_effective_at": effective_at.isoformat(),
            "preorder_source_subscription_bid": subscription.subscription_bid,
            "absorbed_by_bill_order_bid": None,
            "absorbed_at": None,
            "renewal_cycle_start_at": effective_at.isoformat(),
            "renewal_cycle_end_at": cycle_end_at.isoformat(),
            "subscription_bid": subscription.subscription_bid,
            "product_bid": target_product.product_bid,
            "provider_reference_type": "charge",
        }
    ).to_metadata_json()


def mark_subscription_preorder_pending(
    subscription: BillingSubscription,
    order: BillingOrder,
) -> None:
    metadata = (
        dict(subscription.metadata_json)
        if isinstance(subscription.metadata_json, dict)
        else {}
    )
    metadata.update(
        _normalize_json_object(
            {
                SUBSCRIPTION_PREORDER_ORDER_BID_KEY: order.bill_order_bid,
                SUBSCRIPTION_PREORDER_PROVIDER_KEY: order.payment_provider,
                SUBSCRIPTION_PREORDER_CHANNEL_KEY: order.channel,
            }
        )
    )
    subscription.next_product_bid = order.product_bid
    subscription.metadata_json = metadata
    subscription.updated_at = datetime.now()


def clear_subscription_preorder_metadata(subscription: BillingSubscription) -> None:
    metadata = (
        dict(subscription.metadata_json)
        if isinstance(subscription.metadata_json, dict)
        else {}
    )
    for key in (
        SUBSCRIPTION_PREORDER_ORDER_BID_KEY,
        SUBSCRIPTION_PREORDER_PROVIDER_KEY,
        SUBSCRIPTION_PREORDER_CHANNEL_KEY,
    ):
        metadata.pop(key, None)
    subscription.metadata_json = metadata


def mark_preorder_absorbed_by_upgrade(
    preorder_order: BillingOrder,
    *,
    upgrade_order_bid: str,
    absorbed_at: datetime | None = None,
) -> None:
    now = absorbed_at or datetime.now()
    metadata = (
        dict(preorder_order.metadata_json)
        if isinstance(preorder_order.metadata_json, dict)
        else {}
    )
    metadata.update(
        _normalize_json_object(
            {
                "preorder_state": PREORDER_STATE_ABSORBED_BY_UPGRADE,
                "absorbed_by_bill_order_bid": upgrade_order_bid,
                "absorbed_at": now.isoformat(),
            }
        )
    )
    preorder_order.metadata_json = metadata
    preorder_order.updated_at = datetime.now()


def mark_preorder_effective_applied(order: BillingOrder) -> None:
    if not is_preorder_order(order):
        return
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    current_state = str(metadata.get("preorder_state") or "").strip()
    if current_state != PREORDER_STATE_PENDING_EFFECTIVE:
        return
    metadata.update(
        _normalize_json_object(
            {
                "preorder_state": PREORDER_STATE_EFFECTIVE_APPLIED,
                "effective_applied_at": datetime.now().isoformat(),
            }
        )
    )
    order.metadata_json = metadata
    order.updated_at = datetime.now()
