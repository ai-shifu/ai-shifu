"""Match provider payment notifications to legacy order payment attempts."""

import decimal

from flaskr.service.common.models import raise_error
from flaskr.service.common.native_payment_status import (
    extract_native_trade_payload,
    extract_native_trade_status,
    native_snapshot_status,
)
from flaskr.service.order.consts import (
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.funs_lookup import order_funs
from flaskr.service.order.models import (
    Order,
    StripeOrder,
)
from flaskr.service.order.payment_payloads import (
    _parse_json_payload,
    _stringify_payload,
)
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
)
from flaskr.service.order.raw_snapshots import (
    should_update_native_snapshot_status,
)


def _load_payment_sync_order(
    order_id: str,
    *,
    expected_user: str | None,
    for_update: bool = False,
) -> Order:
    """Load one learner-owned order for provider synchronization."""
    query = Order.query.filter(
        Order.order_bid == order_id,
        Order.deleted == 0,
    ).order_by(Order.id.desc())
    if for_update:
        query = query.with_for_update()
    order = query.first()
    if not order:
        raise_error("server.order.orderNotFound")
    if expected_user and order.user_bid != expected_user:
        raise_error("server.order.orderNotFound")
    return order


def _update_stripe_order_snapshot(
    *,
    stripe_order: StripeOrder,
    session: dict[str, object],
    intent: dict[str, object] | None,
) -> None:
    if session:
        stripe_order.checkout_session_id = session.get(
            "id", stripe_order.checkout_session_id
        )
        stripe_order.checkout_session_object = _stringify_payload(session)
        payment_status = session.get("payment_status")
        status = session.get("status")
        if payment_status == "paid":
            stripe_order.status = 1
        elif status == "expired":
            stripe_order.status = 3
        else:
            stripe_order.status = 0

    if intent:
        stripe_order.payment_intent_id = intent.get(
            "id", stripe_order.payment_intent_id
        )
        stripe_order.payment_intent_object = _stringify_payload(intent)
        latest_charge = intent.get("latest_charge")
        if latest_charge:
            stripe_order.latest_charge_id = latest_charge
        charges = intent.get("charges", {}).get("data", [])
        if charges:
            receipt_url = charges[0].get("receipt_url")
            if receipt_url:
                stripe_order.receipt_url = receipt_url


def _is_stripe_payment_successful(
    *, session: dict[str, object] | None, intent: dict[str, object] | None
) -> bool:
    if session and session.get("payment_status") == "paid":
        return True
    return bool(intent and intent.get("status") == "succeeded")


def _stripe_provider_objects_match_attempt(
    *,
    order: Order,
    stripe_order: StripeOrder,
    notification_order_bid: str,
    session: dict[str, object] | None,
    intent: dict[str, object] | None,
) -> bool:
    """Verify remote Stripe objects belong to the local payment attempt."""
    session = session or {}
    intent = intent or {}
    session_metadata = session.get("metadata") or {}
    intent_metadata = intent.get("metadata") or {}
    if not isinstance(session_metadata, dict) or not isinstance(intent_metadata, dict):
        return False
    if notification_order_bid != order.order_bid:
        return False
    session_order_bid = session_metadata.get("order_bid")
    if session and session_order_bid and session_order_bid != order.order_bid:
        return False
    if intent and intent_metadata.get("order_bid") != order.order_bid:
        return False
    if session and not session_order_bid and not intent:
        return False

    remote_session_id = str(session.get("id") or "")
    if session and remote_session_id != str(stripe_order.checkout_session_id or ""):
        return False
    remote_intent_id = str(intent.get("id") or session.get("payment_intent") or "")
    session_intent_id = str(session.get("payment_intent") or "")
    if intent and session_intent_id and remote_intent_id != session_intent_id:
        return False
    local_intent_id = str(stripe_order.payment_intent_id or "")
    if local_intent_id and remote_intent_id != local_intent_id:
        return False

    local_amount = int(stripe_order.amount or 0)
    for payload, field in ((session, "amount_total"), (intent, "amount")):
        if not payload or payload.get(field) in (None, ""):
            continue
        try:
            if int(payload[field]) != local_amount:
                return False
        except (TypeError, ValueError):
            return False
    local_currency = str(stripe_order.currency or "").lower()
    for payload in (session, intent):
        remote_currency = str((payload or {}).get("currency") or "").lower()
        if remote_currency and local_currency and remote_currency != local_currency:
            return False
    return True


def _stripe_attempt_matches_order(order: Order, stripe_order: StripeOrder) -> bool:
    """Check that an attempt is the current snapshot for the order amount."""
    latest_attempt = (
        order_funs.legacy_stripe_snapshot_query()
        .filter(StripeOrder.order_bid == order.order_bid)
        .order_by(StripeOrder.id.desc())
        .with_entities(StripeOrder.id)
        .first()
    )
    latest_attempt_id = latest_attempt[0] if latest_attempt else None
    amount_matches = decimal.Decimal(order.paid_price or 0) <= 0 or int(
        stripe_order.amount or 0
    ) == int(decimal.Decimal(order.paid_price) * 100)
    return bool(stripe_order.id == latest_attempt_id and amount_matches)


def _stripe_attempt_can_complete(order: Order, stripe_order: StripeOrder) -> bool:
    """Apply the lifecycle gate shared by Stripe sync and webhooks."""
    return bool(
        stripe_order.status in {0, 4}
        and _stripe_attempt_matches_order(order, stripe_order)
        and order.status in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}
    )


def _stripe_intent_event_matches_attempt(
    stripe_order: StripeOrder,
    data_object: dict[str, object],
    metadata: dict[str, object],
) -> bool:
    """Reject delayed PaymentIntent events from another payment attempt."""
    remote_intent_id = str(data_object.get("id") or "")
    if not remote_intent_id.startswith("pi_"):
        return False
    local_intent_id = str(stripe_order.payment_intent_id or "")
    if local_intent_id:
        return remote_intent_id == local_intent_id
    return str(metadata.get("stripe_order_bid") or "") == str(
        stripe_order.stripe_order_bid or ""
    )


def _stripe_refund_event_matches_attempt(
    stripe_order: StripeOrder,
    data_object: dict[str, object],
    event_type: str,
) -> bool:
    """Match refund evidence to the stored PaymentIntent or charge."""
    payment_intent_id = str(data_object.get("payment_intent") or "")
    charge_id = str(data_object.get("charge") or "")
    if event_type == "charge.refunded":
        charge_id = str(data_object.get("id") or charge_id)
    return bool(
        (
            payment_intent_id
            and payment_intent_id == str(stripe_order.payment_intent_id or "")
        )
        or (charge_id and charge_id == str(stripe_order.latest_charge_id or ""))
    )


def _apply_native_snapshot_update(
    *,
    snapshot: object,
    provider: str,
    notification: PaymentNotificationResult,
    source: str,
) -> None:
    payload = notification.provider_payload or {}
    raw_status = _native_raw_status(provider, payload, notification.status)
    incoming_status = _native_snapshot_status(provider, payload, raw_status)
    if should_update_native_snapshot_status(snapshot.status, incoming_status):
        snapshot.raw_status = raw_status
        snapshot.status = incoming_status
    if notification.charge_id:
        snapshot.transaction_id = notification.charge_id
    if notification.order_bid:
        snapshot.provider_attempt_id = notification.order_bid
    if source == "webhook":
        snapshot.raw_notification = _stringify_payload(payload)
    else:
        snapshot.raw_response = _stringify_payload(payload)
    metadata = _parse_json_payload(snapshot.metadata_json)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["latest_source"] = source
    metadata["latest_provider_payload"] = payload
    snapshot.metadata_json = _stringify_payload(metadata)


def _native_raw_status(
    provider: str,
    payload: dict[str, object],
    fallback: str = "",
) -> str:
    return extract_native_trade_status(provider, payload) or str(fallback or "")


def _native_snapshot_status(
    provider: str,
    payload: dict[str, object],
    raw_status: str,
) -> int:
    if raw_status and not extract_native_trade_status(provider, payload):
        payload = (
            {"trade_status": raw_status}
            if provider == "alipay"
            else {"trade_state": raw_status}
        )
    return native_snapshot_status(provider, payload)


def _is_native_payment_successful(
    provider: str,
    payload: dict[str, object],
) -> bool:
    raw_status = _native_raw_status(provider, payload)
    return _native_snapshot_status(provider, payload, raw_status) == 1


def _extract_native_notification_amount(
    provider: str,
    payload: dict[str, object],
) -> int | None:
    trade_payload = extract_native_trade_payload(payload)
    if provider == "alipay":
        total_amount = (
            trade_payload.get("total_amount")
            if isinstance(trade_payload, dict)
            else None
        )
        if total_amount in (None, ""):
            return None
        return int((decimal.Decimal(str(total_amount)) * 100).to_integral_value())
    if provider == "wechatpay":
        amount = (
            trade_payload.get("amount", {}) if isinstance(trade_payload, dict) else {}
        )
        if not isinstance(amount, dict):
            return None
        value = amount.get("payer_total", amount.get("total"))
        if value in (None, ""):
            return None
        return int(value)
    return None
