"""Protocol compatibility for historical Stripe billing call sites.

New business consumers use typed payment and subscription facts. These functions
retain historical public/helper signatures at the protocol boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.service.common.models import raise_error
from flaskr.service.config import get_config
from flaskr.service.order.payment_providers.api import (
    payment_definition,
    registered_payment_providers,
    stripe_paid_amount,
    stripe_paid_currency,
)
from flaskr.service.user.api import load_user_aggregate

from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
)
from .models import BillingOrder, BillingSubscription
from .primitives import coerce_datetime as _coerce_datetime
from .primitives import normalize_bid as _normalize_bid
from .queries import (
    extract_order_metadata_datetime as _extract_order_metadata_datetime,
)
from .queries import (
    load_latest_subscription_renewal_order as _load_latest_subscription_renewal_order,
)
from .queries import (
    load_subscription_renewal_order_by_cycle as _load_subscription_renewal_order_by_cycle,
)
from .subscriptions import load_subscription_by_bid as _load_subscription_by_bid

if TYPE_CHECKING:
    from datetime import datetime

    from flask import Flask

    from .models import BillingProduct


_STRIPE_SUCCESS_EVENT_TYPES = {
    "payment_intent.succeeded",
    "checkout.session.async_payment_succeeded",
}


_STRIPE_FAIL_EVENT_TYPES = {
    "payment_intent.payment_failed",
    "checkout.session.async_payment_failed",
}


_STRIPE_REFUND_EVENT_TYPES = {
    "charge.refunded",
    "refund.created",
}


_STRIPE_CANCEL_EVENT_TYPES = {
    "payment_intent.canceled",
}


def _map_stripe_order_status(
    event_type: str,
    data_object: dict[str, object] | None = None,
) -> int | None:
    if event_type == "checkout.session.completed":
        payment_status = (
            str((data_object or {}).get("payment_status") or "").strip().lower()
        )
        if payment_status in {"paid", "no_payment_required"}:
            return BILLING_ORDER_STATUS_PAID
        return None
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
    data_object: dict[str, object],
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
    data_object: dict[str, object],
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
    data_object: dict[str, object],
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
    data_object: dict[str, object],
) -> str:
    reference = _normalize_bid(data_object.get("id"))
    if event_type == "checkout.session.completed" and reference.startswith("cs_"):
        return reference
    return order.provider_reference_id


def _extract_stripe_failure_code(data_object: dict[str, object]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("code") or "")


def _extract_stripe_failure_message(data_object: dict[str, object]) -> str:
    error_info = data_object.get("last_payment_error", {}) or {}
    return str(error_info.get("message") or "")


def extract_stripe_paid_amount(payload: dict[str, Any]) -> int | None:
    """Read Stripe payment evidence through the adapter boundary."""
    return stripe_paid_amount(payload)


def extract_stripe_paid_currency(payload: dict[str, Any]) -> str:
    """Read Stripe payment currency through the adapter boundary."""
    return stripe_paid_currency(payload)


def _extract_provider_event_time(payload: object) -> datetime | None:
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
    session: dict[str, object],
    intent: dict[str, object] | None,
) -> bool:
    if session.get("payment_status") in {"paid", "no_payment_required"}:
        return True
    return bool(intent and intent.get("status") == "succeeded")


def _build_pingxx_provider_options(
    *,
    creator_bid: str,
    product: BillingProduct,
    channel: str,
) -> dict[str, object]:
    normalized_channel = _normalize_bid(channel)
    charge_extra: dict[str, Any]

    if normalized_channel == "wx_pub_qr":
        charge_extra = {"product_id": product.product_bid}
    elif normalized_channel == "alipay_qr":
        charge_extra = {}
    elif normalized_channel == "wx_pub":
        user = load_user_aggregate(creator_bid)
        open_id = str(user.wechat_open_id or "").strip() if user else ""
        if not open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        charge_extra = {"open_id": open_id}
    elif normalized_channel == "wx_wap":
        charge_extra = {}
    else:
        raise_error("server.pay.payChannelNotSupport")

    return {
        "app_id": str(get_config("PINGXX_APP_ID", "") or "").strip(),
        "charge_extra": charge_extra,
    }


def _build_native_provider_options(
    *,
    creator_bid: str,
    product: BillingProduct,
    provider: str,
    channel: str,
) -> dict[str, object]:
    normalized_channel = _normalize_bid(channel)
    del product
    if provider == "alipay":
        if normalized_channel != "alipay_qr":
            raise_error("server.pay.payChannelNotSupport")
        return {}
    if provider == "wechatpay":
        if normalized_channel == "wx_pub_qr":
            return {}
        if normalized_channel == "wx_pub":
            user = load_user_aggregate(creator_bid)
            open_id = str(user.wechat_open_id or "").strip() if user else ""
            if not open_id:
                raise_error("server.pay.wechatOpenIdRequired")
            return {"open_id": open_id}
        raise_error("server.pay.payChannelNotSupport")
    if provider not in registered_payment_providers():
        raise_error("server.pay.payChannelNotSupport")
    definition = payment_definition(provider)
    if any(route.channel == normalized_channel for route in definition.routes):
        return {}
    raise_error("server.pay.payChannelNotSupport")
    return None


def _validate_stripe_checkout_evidence(
    app: Flask,
    order: BillingOrder,
    *,
    expected_session_id: str,
    session: dict[str, object],
    intent: dict[str, object] | None,
) -> None:
    actual_session_id = _normalize_bid(session.get("id"))
    if actual_session_id != _normalize_bid(expected_session_id):
        raise_error("server.order.orderStatusError")

    metadata_candidates = [
        payload.get("metadata")
        for payload in (session, intent or {})
        if isinstance(payload, dict)
    ]
    for candidate in metadata_candidates:
        if not isinstance(candidate, dict):
            continue
        for key, expected_value in (
            ("bill_order_bid", order.bill_order_bid),
            ("creator_bid", order.creator_bid),
            ("product_bid", order.product_bid),
        ):
            actual_value = _normalize_bid(candidate.get(key))
            if actual_value and actual_value != _normalize_bid(expected_value):
                raise_error("server.order.orderStatusError")
    metadata = next(
        (
            candidate
            for candidate in metadata_candidates
            if isinstance(candidate, dict) and candidate.get("bill_order_bid")
        ),
        None,
    )
    if metadata is None:
        # Stripe has attached nothing to match against. A payment-mode
        # session has no PaymentIntent until the buyer starts paying, and
        # sessions created before the provider began writing session metadata
        # carry none at all.
        if _is_unbound_unpaid_stripe_checkout(session, intent):
            app.logger.warning(
                "Accepted metadata-free unpaid Stripe Checkout Session for billing order: %s",
                order.bill_order_bid,
            )
            return
        raise_error("server.order.orderStatusError")

    if _normalize_bid(metadata.get("bill_order_bid")) != order.bill_order_bid:
        raise_error("server.order.orderStatusError")
    for key, expected_value in (
        ("creator_bid", order.creator_bid),
        ("product_bid", order.product_bid),
    ):
        actual_value = _normalize_bid(metadata.get(key))
        if actual_value and actual_value != _normalize_bid(expected_value):
            raise_error("server.order.orderStatusError")


def _is_unbound_unpaid_stripe_checkout(
    session: dict[str, object],
    intent: dict[str, object] | None,
) -> bool:
    """Accept an unpaid Session that carries nothing to match the order against.

    The session id has already been matched against the reference stored on
    the order, and every identity key either payload does carry has already
    been checked, so the only evidence still missing is proof of payment --
    which an unpaid session cannot produce. Waiting for Stripe to expire the
    session first would leave the order failing every scan for as long as
    Stripe keeps the session open: 24 hours by default, against a local
    deadline of 30 minutes.

    Expiring the order is not final. A payment that lands afterwards still
    moves it to paid through sync or webhook.
    """
    return not _is_stripe_checkout_paid(session, intent)


def _load_billing_order_for_stripe_event(
    *,
    bill_order_bid: str,
    data_object: dict[str, object],
) -> BillingOrder | None:
    query = BillingOrder.query.filter(BillingOrder.deleted == 0)
    if bill_order_bid:
        return (
            query.filter(BillingOrder.bill_order_bid == bill_order_bid)
            .order_by(BillingOrder.id.desc())
            .first()
        )

    provider_reference_id = _normalize_bid(data_object.get("id"))
    if provider_reference_id.startswith("cs_"):
        return (
            query.filter(
                BillingOrder.payment_provider == "stripe",
                BillingOrder.provider_reference_id == provider_reference_id,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
    return None


def _load_billing_subscription_for_stripe_event(
    *,
    order: BillingOrder | None,
    data_object: dict[str, object],
    metadata: dict[str, object],
) -> BillingSubscription | None:
    if order is not None and order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            return subscription

    subscription_bid = _normalize_bid(metadata.get("subscription_bid"))
    if subscription_bid:
        subscription = _load_subscription_by_bid(subscription_bid)
        if subscription is not None:
            return subscription

    provider_subscription_id = _normalize_bid(
        data_object.get("subscription")
        or (
            data_object.get("id")
            if str(data_object.get("id") or "").startswith("sub_")
            else ""
        )
    )
    if provider_subscription_id:
        return (
            BillingSubscription.query.filter(
                BillingSubscription.deleted == 0,
                BillingSubscription.billing_provider == "stripe",
                BillingSubscription.provider_subscription_id
                == provider_subscription_id,
            )
            .order_by(BillingSubscription.id.desc())
            .first()
        )
    return None


def _load_billing_order_for_pingxx_event(
    *,
    charge_id: str,
    order_no: str,
) -> BillingOrder | None:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.payment_provider == "pingxx",
    )
    if charge_id:
        order = (
            query.filter(BillingOrder.provider_reference_id == charge_id)
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
    if order_no:
        return (
            query.filter(BillingOrder.bill_order_bid == order_no)
            .order_by(BillingOrder.id.desc())
            .first()
        )
    return None
