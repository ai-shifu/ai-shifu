"""Billing order deadlines, invalidation, locks, and shared checkout payloads."""

from __future__ import annotations

from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from flaskr.common import cache_provider
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_channel_resolution import resolve_payment_channel
from flaskr.util.datetime import now_utc

from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_INIT,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_LABELS,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PENDING_ORDER_TIMEOUT_DELTA,
    BILLING_PENDING_ORDER_TIMEOUT_MINUTES,
)
from .dtos import (
    BillingOrderSyncResultDTO,
)
from .models import (
    BillingOrder,
    BillingProduct,
)
from .payment_policy import is_manual_payment_provider
from .preorders import (
    PREORDER_CHECKOUT_TYPE,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .queries import normalize_payment_provider_hint as _normalize_payment_provider_hint
from .subscriptions import (
    load_billing_product_by_bid as _load_billing_product_by_bid,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from flask import Flask


_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS = {
    BILLING_ORDER_STATUS_INIT: 0,
    BILLING_ORDER_STATUS_PENDING: 0,
    BILLING_ORDER_STATUS_PAID: 1,
    BILLING_ORDER_STATUS_REFUNDED: 2,
    BILLING_ORDER_STATUS_CANCELED: 3,
    BILLING_ORDER_STATUS_TIMEOUT: 3,
    BILLING_ORDER_STATUS_FAILED: 4,
}


_SUBSCRIPTION_CHECKOUT_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}


def _resolve_billing_order_expires_at(
    *,
    now: datetime | None = None,
) -> datetime:
    return (now or now_utc()) + BILLING_PENDING_ORDER_TIMEOUT_DELTA


def _resolve_effective_billing_order_expires_at(
    order: BillingOrder,
) -> datetime | None:
    if order.expires_at is not None:
        return order.expires_at
    if not _is_subscription_checkout_order(order):
        return None
    if order.created_at is None:
        return None
    return order.created_at + BILLING_PENDING_ORDER_TIMEOUT_DELTA


def _hydrate_legacy_billing_order_expires_at(
    order: BillingOrder,
) -> bool:
    if order.expires_at is not None:
        return False
    resolved = _resolve_effective_billing_order_expires_at(order)
    if resolved is None:
        return False
    order.expires_at = resolved
    return True


def _calculate_billing_order_expires_in_seconds(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> int | None:
    resolved_expires_at = _resolve_effective_billing_order_expires_at(order)
    if resolved_expires_at is None:
        return None
    remaining = int((resolved_expires_at - (now or now_utc())).total_seconds())
    return max(0, remaining)


def _is_subscription_checkout_order(order: BillingOrder) -> bool:
    return int(order.order_type or 0) in _SUBSCRIPTION_CHECKOUT_ORDER_TYPES


def _is_same_subscription_checkout_target(
    order: BillingOrder,
    *,
    product_bid: str,
    order_type: int,
    payment_provider: str,
    channel: str,
    currency: str,
    payable_amount: int,
    checkout_metadata: dict[str, object],
    provider_price_bid: str = "",
    campaign_bid: str = "",
    campaign_provider_discount_bid: str = "",
) -> bool:
    if _normalize_bid(order.product_bid) != _normalize_bid(product_bid) or int(
        order.order_type or 0
    ) != int(order_type or 0):
        return False
    if (
        _normalize_bid(order.payment_provider) != _normalize_bid(payment_provider)
        or _normalize_bid(order.channel) != _normalize_bid(channel)
        or order.currency != currency
        or int(order.payable_amount or 0) != payable_amount
    ):
        return False
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    for key in (
        "checkout_type",
        "preorder_order_bid",
        "prepaid_offset_amount",
        "current_product_bid",
        "target_product_bid",
        "preorder_effective_at",
        "renewal_cycle_start_at",
        "renewal_cycle_end_at",
    ):
        if metadata.get(key) != checkout_metadata.get(key):
            return False
    if _normalize_bid(order.campaign_bid) != _normalize_bid(campaign_bid):
        return False
    if _normalize_bid(metadata.get("campaign_provider_discount_bid")) != _normalize_bid(
        campaign_provider_discount_bid
    ):
        return False
    normalized_provider_price_bid = _normalize_bid(provider_price_bid)
    if not normalized_provider_price_bid:
        return True
    return (
        _normalize_bid(metadata.get("provider_price_bid"))
        == normalized_provider_price_bid
    )


def _is_managed_pending_subscription_checkout_order(order: BillingOrder) -> bool:
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING:
        return False
    if not _is_subscription_checkout_order(order):
        return False
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return str(metadata.get("checkout_type") or "").strip() != PREORDER_CHECKOUT_TYPE


def _is_billing_order_expired(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> bool:
    resolved_expires_at = _resolve_effective_billing_order_expires_at(order)
    if resolved_expires_at is None:
        return False
    return resolved_expires_at <= (now or now_utc())


def _mark_billing_order_invalidated(
    order: BillingOrder,
    *,
    target_status: int,
    reason: str,
    invalidated_at: datetime | None = None,
    replaced_by_bill_order_bid: str = "",
) -> None:
    now = invalidated_at or now_utc()
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    metadata["invalidated_reason"] = reason
    metadata["invalidated_at"] = now.isoformat()
    if replaced_by_bill_order_bid:
        metadata["replaced_by_bill_order_bid"] = replaced_by_bill_order_bid
    order.metadata_json = _normalize_json_object(metadata).to_metadata_json()
    order.status = target_status
    order.updated_at = now
    order.failed_at = order.failed_at or now
    order.failure_code = reason
    if target_status == BILLING_ORDER_STATUS_TIMEOUT:
        order.failure_message = f"Billing order expired after {BILLING_PENDING_ORDER_TIMEOUT_MINUTES} minutes"
    elif target_status == BILLING_ORDER_STATUS_CANCELED:
        order.failure_message = "Billing order invalidated by a newer package checkout"


def _expire_pending_billing_order_if_due(
    order: BillingOrder,
    *,
    now: datetime | None = None,
) -> bool:
    # Any order carrying an explicit deadline can time out; orders without
    # one keep the legacy subscription-only behaviour through
    # _resolve_effective_billing_order_expires_at.
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING or not (
        _is_billing_order_expired(order, now=now)
    ):
        return False
    _mark_billing_order_invalidated(
        order,
        target_status=BILLING_ORDER_STATUS_TIMEOUT,
        reason="timeout",
        invalidated_at=now,
    )
    return True


def _build_subscription_checkout_lock_key(app: Flask, creator_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu").rstrip(
        ":"
    )
    return f"{prefix}:billing:subscription-checkout:{creator_bid}"


@contextmanager
def _subscription_checkout_lock(app: Flask, creator_bid: str) -> Iterator[None]:
    """Serialize subscription checkout per creator to avoid duplicate pending orders without taking row locks on the pending-order query itself."""
    lock = cache_provider.cache.lock(
        _build_subscription_checkout_lock_key(app, creator_bid),
        timeout=30,
        blocking_timeout=10,
    )
    acquired = bool(lock.acquire(blocking=True))
    if not acquired:
        raise_error("server.billing.subscriptionCheckoutBusy")
    try:
        yield
    finally:
        with suppress(Exception):
            lock.release()


_CREDIT_LEDGER_LOCK_TIMEOUT_SECONDS = 60


_CREDIT_LEDGER_LOCK_BLOCKING_TIMEOUT_SECONDS = 60


def _build_credit_ledger_lock_key(app: Flask, creator_bid: str) -> str:
    prefix = str(app.config.get("REDIS_KEY_PREFIX", "ai-shifu") or "ai-shifu").rstrip(
        ":"
    )
    scope = str(creator_bid or "").strip() or "unknown"
    return f"{prefix}:billing:credit-ledger:{scope}"


@contextmanager
def _credit_ledger_lock(app: Flask, creator_bid: str) -> Iterator[None]:
    """Serialize credit-ledger writes for a creator.

    Concurrent order syncs for the same creator (timeout scan vs renewal
    reconcile vs manual sync) otherwise both pass the ``existing_entry`` grant
    pre-check and then trip the ``(creator_bid, idempotency_key)`` unique key at
    commit, and contend on the same ``bill_orders`` row (seen in production as
    ``Lock wait timeout``). Serializing per creator lets the second caller re-run
    the pre-check inside the lock, find the first caller's committed grant, and
    take the idempotent repair path instead. Mirrors ``_usage_settlement_lock``
    in ``settlement.py``: on lock-backend failure it degrades to running without
    the lock rather than blocking the sync.
    """
    lock = cache_provider.cache.lock(
        _build_credit_ledger_lock_key(app, creator_bid),
        timeout=_CREDIT_LEDGER_LOCK_TIMEOUT_SECONDS,
        blocking_timeout=_CREDIT_LEDGER_LOCK_BLOCKING_TIMEOUT_SECONDS,
    )
    acquired = False
    try:
        if lock is not None:
            acquired = bool(lock.acquire(blocking=True))
    except Exception as exc:
        # Lock-backend failure (e.g. Redis outage): degrade to running without
        # the lock rather than crashing the order sync. The grant idempotency
        # pre-check and unique key still guard correctness.
        app.logger.warning(
            "credit-ledger lock acquire failed; running without lock: %s", exc
        )
    if lock is not None and not acquired:
        # Blocking timeout elapsed under contention: acquire() returned False.
        # Log so this fail-open path is observable rather than silent.
        app.logger.warning(
            "credit-ledger lock not acquired within timeout for %s; "
            "running without lock",
            _build_credit_ledger_lock_key(app, creator_bid),
        )
    try:
        yield
    finally:
        if acquired and lock is not None:
            try:
                lock.release()
            except Exception as exc:
                app.logger.warning("credit-ledger lock release failed: %s", exc)


def _load_active_pending_subscription_orders(
    creator_bid: str,
) -> list[BillingOrder]:
    orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == creator_bid,
            BillingOrder.status.in_(
                (
                    BILLING_ORDER_STATUS_PENDING,
                    BILLING_ORDER_STATUS_TIMEOUT,
                    BILLING_ORDER_STATUS_FAILED,
                )
            ),
            BillingOrder.order_type.in_(_SUBSCRIPTION_CHECKOUT_ORDER_TYPES),
        )
        .order_by(BillingOrder.id.desc())
        .all()
    )
    return [
        order
        for order in orders
        if _is_managed_pending_subscription_checkout_order(order)
        or (
            is_manual_payment_provider(order.payment_provider)
            and order.provider_reference_id
        )
    ]


def _load_billing_order_by_bid(bill_order_bid: str) -> BillingOrder | None:
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid == bill_order_bid,
        )
        .order_by(BillingOrder.id.desc())
        .first()
    )


def _load_reopen_targets(
    bill_order_bid: str, product_bid: str
) -> tuple[BillingOrder, BillingProduct]:
    order = _load_billing_order_by_bid(bill_order_bid)
    if order is None:
        raise_error("server.order.orderNotFound")
    # A webhook or a sync can settle the order between the two units of work
    # of the reopen flow; a settled order must not be reopened.
    if int(order.status or 0) != BILLING_ORDER_STATUS_PENDING:
        raise_error("server.order.orderStatusError")
    product = _load_billing_product_by_bid(product_bid)
    if product is None:
        raise_error("server.order.orderNotFound")
    return order, product


def _build_billing_order_sync_result(
    order: BillingOrder,
) -> BillingOrderSyncResultDTO:
    status_label = {
        BILLING_ORDER_STATUS_PENDING: "pending",
        BILLING_ORDER_STATUS_PAID: "paid",
        BILLING_ORDER_STATUS_FAILED: "failed",
        BILLING_ORDER_STATUS_CANCELED: "canceled",
        BILLING_ORDER_STATUS_TIMEOUT: "timeout",
        BILLING_ORDER_STATUS_REFUNDED: "refunded",
    }.get(int(order.status or 0))
    if not status_label:
        raise_error("server.order.orderStatusError")
    return BillingOrderSyncResultDTO(
        bill_order_bid=order.bill_order_bid,
        status=status_label,
        expires_at=order.expires_at,
        expires_in_seconds=_calculate_billing_order_expires_in_seconds(order),
    )


def _resolve_billing_payment_channel(
    payload: dict[str, object],
    *,
    default_pingxx_channel: str,
) -> tuple[str, str]:
    return resolve_payment_channel(
        payment_channel_hint=_normalize_payment_provider_hint(
            payload.get("payment_provider")
        )
        or None,
        channel_hint=_normalize_bid(payload.get("channel")) or None,
        stored_channel=None,
        default_pingxx_channel=default_pingxx_channel,
    )


def _build_manual_payment_payload(
    provider_reference: str,
    raw_response: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Keep persisted-credential reuse and new checkout responses identical."""
    return _normalize_json_object(
        {
            "provider_reference_id": provider_reference,
            "credential": extra.get("credential"),
            "mode": extra.get("mode"),
            "prepay_id": extra.get("prepay_id"),
            "jsapi_params": extra.get("jsapi_params"),
            "raw_response": raw_response,
        }
    ).to_metadata_json()


def _build_checkout_response_payload(
    order: BillingOrder,
    *,
    payment_provider: str,
    payment_mode: str,
    status: str,
    reused_existing_order: bool = False,
) -> dict[str, object]:
    order_metadata = (
        order.metadata_json if isinstance(order.metadata_json, dict) else {}
    )
    return {
        "bill_order_bid": order.bill_order_bid,
        "provider": payment_provider,
        "payment_mode": payment_mode,
        "status": status,
        "reused_existing_order": reused_existing_order,
        "checkout_type": order_metadata.get("checkout_type") or None,
        "effective_mode": order_metadata.get("effective_mode")
        or (
            "cycle_end"
            if order_metadata.get("checkout_type") == PREORDER_CHECKOUT_TYPE
            else "immediate"
        ),
        "current_product_bid": order_metadata.get("current_product_bid") or None,
        "target_product_bid": order_metadata.get("target_product_bid")
        or order.product_bid,
        "preorder_order_bid": order_metadata.get("preorder_order_bid") or None,
        "prepaid_offset_amount": int(order_metadata.get("prepaid_offset_amount") or 0),
        "payable_amount": int(order.payable_amount or 0),
        "currency": str(order.currency or "CNY"),
        "expires_at": order.expires_at,
        "expires_in_seconds": _calculate_billing_order_expires_in_seconds(order),
        "campaign": order_metadata.get("campaign") or None,
    }


def _resolve_billing_order_payment_mode(order: BillingOrder) -> str:
    order_label = BILLING_ORDER_TYPE_LABELS.get(int(order.order_type or 0), "manual")
    if order_label.startswith("subscription_"):
        return "subscription"
    return "one_time"
