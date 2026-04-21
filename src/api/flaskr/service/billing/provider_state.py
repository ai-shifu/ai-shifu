"""Provider state transition helpers for billing orders and subscriptions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask

from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
)
from .models import BillingOrder, BillingSubscription
from .queries import (
    extract_order_metadata_datetime as _extract_order_metadata_datetime,
    load_latest_subscription_renewal_order as _load_latest_subscription_renewal_order,
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
)
from .primitives import coerce_datetime as _coerce_datetime
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import normalize_json_value as _normalize_json_value
from .subscriptions import (
    sync_subscription_lifecycle_events as _sync_subscription_lifecycle_events,
)
from .value_objects import JsonObjectMap

_STRIPE_SUCCESS_EVENT_TYPES = {
    "payment_intent.succeeded",
    "checkout.session.completed",
}

_STRIPE_FAIL_EVENT_TYPES = {
    "payment_intent.payment_failed",
}

_STRIPE_REFUND_EVENT_TYPES = {
    "charge.refunded",
    "refund.created",
}

_STRIPE_CANCEL_EVENT_TYPES = {
    "payment_intent.canceled",
}

_STRIPE_SUBSCRIPTION_STATUS_MAP = {
    "active": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    "trialing": BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    "past_due": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    "unpaid": BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    "paused": BILLING_SUBSCRIPTION_STATUS_PAUSED,
    "canceled": BILLING_SUBSCRIPTION_STATUS_CANCELED,
    "incomplete_expired": BILLING_SUBSCRIPTION_STATUS_EXPIRED,
}


def _apply_billing_order_provider_update(
    order: BillingOrder,
    *,
    provider: str,
    event_type: str,
    source: str,
    payload: dict[str, Any],
    provider_reference_id: str,
    target_status: int | None,
    failure_code: str = "",
    failure_message: str = "",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if provider_reference_id:
        order.provider_reference_id = provider_reference_id
    order.metadata_json = _merge_provider_metadata(
        existing=order.metadata_json,
        provider=provider,
        source=source,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
    ).to_metadata_json()

    if not _can_transition_billing_order_status(
        current_status=int(order.status or 0),
        target_status=target_status,
        source=source,
    ):
        return False

    now = event_time or datetime.now()
    order.status = int(target_status or order.status or 0)
    order.updated_at = datetime.now()
    if target_status == BILLING_ORDER_STATUS_PENDING:
        return True
    if target_status == BILLING_ORDER_STATUS_PAID:
        order.paid_amount = int(order.payable_amount or 0)
        order.paid_at = order.paid_at or now
        order.failed_at = None
        order.failure_code = ""
        order.failure_message = ""
        return True
    if target_status == BILLING_ORDER_STATUS_FAILED:
        order.failed_at = order.failed_at or now
        order.failure_code = failure_code or order.failure_code
        order.failure_message = failure_message or order.failure_message
        return True
    if target_status == BILLING_ORDER_STATUS_REFUNDED:
        order.refunded_at = order.refunded_at or now
        return True
    if target_status in {
        BILLING_ORDER_STATUS_CANCELED,
        BILLING_ORDER_STATUS_TIMEOUT,
    }:
        order.failed_at = order.failed_at or now
        return True
    return True


def _can_transition_billing_order_status(
    *,
    current_status: int,
    target_status: int | None,
    source: str,
) -> bool:
    if target_status is None or current_status == target_status:
        return False
    if current_status == BILLING_ORDER_STATUS_REFUNDED:
        return False
    if current_status == BILLING_ORDER_STATUS_PAID:
        return target_status == BILLING_ORDER_STATUS_REFUNDED
    if current_status in {
        BILLING_ORDER_STATUS_CANCELED,
        BILLING_ORDER_STATUS_TIMEOUT,
    }:
        return False
    if current_status == BILLING_ORDER_STATUS_FAILED:
        return (
            source in {"sync", "webhook"} and target_status == BILLING_ORDER_STATUS_PAID
        )
    return True


def _map_stripe_order_status(event_type: str) -> int | None:
    if event_type in _STRIPE_SUCCESS_EVENT_TYPES:
        return BILLING_ORDER_STATUS_PAID
    if event_type in _STRIPE_FAIL_EVENT_TYPES:
        return BILLING_ORDER_STATUS_FAILED
    if event_type in _STRIPE_REFUND_EVENT_TYPES:
        return BILLING_ORDER_STATUS_REFUNDED
    if event_type in _STRIPE_CANCEL_EVENT_TYPES:
        return BILLING_ORDER_STATUS_CANCELED
    return None


def _resolve_stripe_subscription_order_status(
    order: BillingOrder,
    data_object: dict[str, Any],
) -> int | None:
    if order.order_type != BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return None

    subscription_status = str(data_object.get("status") or "").strip().lower()
    if subscription_status in {"active", "trialing"}:
        if _stripe_subscription_cycle_matches_renewal_order(order, data_object):
            return BILLING_ORDER_STATUS_PAID
        return BILLING_ORDER_STATUS_PENDING
    if subscription_status in {"past_due", "unpaid", "incomplete_expired", "canceled"}:
        return BILLING_ORDER_STATUS_FAILED
    return BILLING_ORDER_STATUS_PENDING


def _stripe_subscription_cycle_matches_renewal_order(
    order: BillingOrder,
    data_object: dict[str, Any],
) -> bool:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    expected_cycle_start = _extract_order_metadata_datetime(
        metadata, "renewal_cycle_start_at"
    )
    expected_cycle_end = _extract_order_metadata_datetime(
        metadata, "renewal_cycle_end_at"
    )
    current_period_start = _coerce_datetime(data_object.get("current_period_start"))
    current_period_end = _coerce_datetime(data_object.get("current_period_end"))

    if expected_cycle_end is not None and current_period_end is not None:
        if current_period_end >= expected_cycle_end:
            if expected_cycle_start is None or current_period_start is None:
                return True
            return current_period_start >= expected_cycle_start
        return False

    if expected_cycle_start is not None and current_period_start is not None:
        return current_period_start >= expected_cycle_start

    return False


def _load_billing_renewal_order_for_stripe_event(
    subscription_bid: str,
    data_object: dict[str, Any],
) -> BillingOrder | None:
    subscription_status = str(data_object.get("status") or "").strip().lower()
    current_period_start = _coerce_datetime(data_object.get("current_period_start"))
    current_period_end = _coerce_datetime(data_object.get("current_period_end"))

    if subscription_status in {"active", "trialing"}:
        return _load_subscription_renewal_order_by_cycle(
            subscription_bid,
            cycle_start_at=current_period_start,
            cycle_end_at=current_period_end,
            statuses=(
                BILLING_ORDER_STATUS_PENDING,
                BILLING_ORDER_STATUS_FAILED,
            ),
        )

    if subscription_status in {"past_due", "unpaid", "incomplete_expired", "canceled"}:
        return _load_latest_subscription_renewal_order(
            subscription_bid,
            statuses=(
                BILLING_ORDER_STATUS_PENDING,
                BILLING_ORDER_STATUS_FAILED,
            ),
        )

    return None


def _extract_stripe_provider_reference(
    *,
    order: BillingOrder,
    event_type: str,
    data_object: dict[str, Any],
) -> str:
    reference = _normalize_bid(data_object.get("id"))
    if event_type == "checkout.session.completed" and reference.startswith("cs_"):
        return reference
    return order.provider_reference_id


def _extract_stripe_failure_code(data_object: dict[str, Any]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("code") or "")


def _extract_stripe_failure_message(data_object: dict[str, Any]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("message") or "")


def _apply_billing_subscription_provider_update(
    app: Flask,
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    data_object: dict[str, Any],
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    provider_subscription_id = _normalize_bid(data_object.get("id"))
    if provider_subscription_id.startswith("sub_"):
        subscription.provider_subscription_id = provider_subscription_id
    customer_id = _normalize_bid(data_object.get("customer"))
    if customer_id:
        subscription.provider_customer_id = customer_id

    status = str(data_object.get("status") or "").strip().lower()
    mapped_status = _STRIPE_SUBSCRIPTION_STATUS_MAP.get(status)
    if status == "active" and int(data_object.get("cancel_at_period_end") or 0) == 1:
        mapped_status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
    if event_type == "customer.subscription.deleted":
        mapped_status = BILLING_SUBSCRIPTION_STATUS_CANCELED
    if mapped_status is not None:
        subscription.status = mapped_status

    subscription.cancel_at_period_end = (
        1 if data_object.get("cancel_at_period_end") else 0
    )
    subscription.billing_anchor_at = (
        _coerce_datetime(data_object.get("billing_cycle_anchor"))
        or subscription.billing_anchor_at
    )
    subscription.current_period_start_at = (
        _coerce_datetime(data_object.get("current_period_start"))
        or subscription.current_period_start_at
    )
    subscription.current_period_end_at = (
        _coerce_datetime(data_object.get("current_period_end"))
        or subscription.current_period_end_at
    )

    now = event_time or datetime.now()
    if mapped_status in {
        BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    }:
        subscription.last_renewed_at = now
    if mapped_status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        subscription.last_failed_at = now
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _apply_subscription_checkout_success(
    app: Flask,
    subscription: BillingSubscription,
    *,
    payload: dict[str, Any],
    provider: str,
    event_type: str,
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    provider_subscription_id = _normalize_bid(
        payload.get("subscription")
        or (
            payload.get("id") if str(payload.get("id") or "").startswith("sub_") else ""
        )
    )
    if provider_subscription_id:
        subscription.provider_subscription_id = provider_subscription_id
    customer_id = _normalize_bid(payload.get("customer"))
    if customer_id:
        subscription.provider_customer_id = customer_id
    subscription.cancel_at_period_end = 1 if payload.get("cancel_at_period_end") else 0
    subscription.status = (
        BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        if subscription.cancel_at_period_end
        else BILLING_SUBSCRIPTION_STATUS_ACTIVE
    )
    now = event_time or datetime.now()
    subscription.last_renewed_at = now
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _apply_subscription_checkout_failure(
    app: Flask,
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    source: str = "webhook",
) -> bool:
    event_time = _extract_provider_event_time(payload)
    if not _should_apply_subscription_event(subscription, event_time):
        return False

    _record_subscription_provider_event(
        subscription,
        provider=provider,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
        source=source,
    )
    subscription.billing_provider = provider
    subscription.status = BILLING_SUBSCRIPTION_STATUS_PAST_DUE
    subscription.last_failed_at = event_time or datetime.now()
    subscription.updated_at = datetime.now()
    _sync_subscription_lifecycle_events(app, subscription)
    return True


def _should_apply_subscription_event(
    subscription: BillingSubscription,
    event_time: datetime | None,
) -> bool:
    if event_time is None:
        return True
    metadata = (
        subscription.metadata_json
        if isinstance(subscription.metadata_json, dict)
        else {}
    )
    latest_event_time = _coerce_datetime(metadata.get("latest_event_time"))
    if latest_event_time is None:
        return True
    return event_time >= latest_event_time


def _record_subscription_provider_event(
    subscription: BillingSubscription,
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    event_time: datetime | None,
    source: str,
) -> None:
    subscription.metadata_json = _merge_provider_metadata(
        existing=subscription.metadata_json,
        provider=provider,
        source=source,
        event_type=event_type,
        payload=payload,
        event_time=event_time,
    ).to_metadata_json()


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


def _extract_provider_event_time(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("created", "time_paid", "current_period_end", "current_period_start"):
        value = _coerce_datetime(payload.get(key))
        if value is not None:
            return value
    data_object = payload.get("data", {}).get("object", {}) or {}
    for key in ("created", "time_paid", "current_period_end", "current_period_start"):
        value = _coerce_datetime(data_object.get(key))
        if value is not None:
            return value
    checkout_session = payload.get("checkout_session", {}) or {}
    for key in ("created",):
        value = _coerce_datetime(checkout_session.get(key))
        if value is not None:
            return value
    charge = payload.get("charge", {}) or {}
    for key in ("time_paid", "created"):
        value = _coerce_datetime(charge.get(key))
        if value is not None:
            return value
    subscription = payload.get("subscription", {}) or {}
    if isinstance(subscription, dict):
        for key in ("created", "current_period_end", "current_period_start"):
            value = _coerce_datetime(subscription.get(key))
            if value is not None:
                return value
    return None


def _is_stripe_checkout_paid(
    session: dict[str, Any],
    intent: dict[str, Any] | None,
) -> bool:
    if session.get("payment_status") == "paid":
        return True
    if session.get("status") == "complete" and not session.get("payment_status"):
        return True
    if intent and intent.get("status") == "succeeded":
        return True
    return False


apply_billing_order_provider_update = _apply_billing_order_provider_update
map_stripe_order_status = _map_stripe_order_status
resolve_stripe_subscription_order_status = _resolve_stripe_subscription_order_status
load_billing_renewal_order_for_stripe_event = (
    _load_billing_renewal_order_for_stripe_event
)
extract_stripe_provider_reference = _extract_stripe_provider_reference
extract_stripe_failure_code = _extract_stripe_failure_code
extract_stripe_failure_message = _extract_stripe_failure_message
apply_billing_subscription_provider_update = _apply_billing_subscription_provider_update
apply_subscription_checkout_success = _apply_subscription_checkout_success
apply_subscription_checkout_failure = _apply_subscription_checkout_failure
merge_provider_metadata = _merge_provider_metadata
extract_provider_event_time = _extract_provider_event_time
coerce_datetime = _coerce_datetime
is_stripe_checkout_paid = _is_stripe_checkout_paid
normalize_bid = _normalize_bid
