"""Provider sync, refund metadata, and webhook order lookups for billing orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flaskr.service.common.models import raise_error
from flaskr.service.common.native_payment_status import (
    NATIVE_PAYMENT_STATE_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED,
    NATIVE_PAYMENT_STATE_PAID,
    extract_native_trade_payload,
    extract_native_trade_status,
    resolve_native_payment_state,
)
from flaskr.service.order.raw_snapshots import (
    billing_native_snapshot_query,
    native_snapshot_model,
)

from .checkout_orders import (
    _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS,
)
from .checkout_snapshots import (
    _persist_billing_native_raw_snapshot,
    _persist_billing_pingxx_raw_snapshot,
    _persist_billing_stripe_raw_snapshot,
)
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
)
from .models import (
    BillingOrder,
    BillingSubscription,
)
from .primitives import normalize_bid as _normalize_bid
from .provider_state import (
    BillingOrderProviderUpdateResult,
)
from .provider_state import (
    apply_billing_order_provider_update as _apply_billing_order_provider_update,
)
from .provider_state import (
    apply_billing_subscription_provider_update as _apply_billing_subscription_provider_update,
)
from .provider_state import (
    apply_subscription_checkout_success as _apply_subscription_checkout_success,
)
from .provider_state import (
    is_stripe_checkout_paid as _is_stripe_checkout_paid,
)
from .provider_state import (
    resolve_stripe_paid_amount as _resolve_stripe_paid_amount,
)
from .provider_state import (
    resolve_stripe_paid_currency as _resolve_stripe_paid_currency,
)
from .provider_state import (
    resolve_stripe_subscription_order_status as _resolve_stripe_subscription_order_status,
)
from .subscriptions import (
    load_subscription_by_bid as _load_subscription_by_bid,
)

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _checkout_facade() -> ModuleType:
    """Resolve collaborators through ``checkout`` so its patch points stay live."""
    from . import checkout

    return checkout


_BILLING_STATUS_BY_NATIVE_STATE = {
    NATIVE_PAYMENT_STATE_PAID: BILLING_ORDER_STATUS_PAID,
    NATIVE_PAYMENT_STATE_CANCELED: BILLING_ORDER_STATUS_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED: BILLING_ORDER_STATUS_FAILED,
}


@dataclass(slots=True, frozen=True)
class RefundProviderMetadata:
    """Carry metadata for refund provider."""

    bill_order_bid: str
    creator_bid: str
    payment_intent_id: str | None = None
    charge_id: str | None = None

    def to_provider_payload(self) -> dict[str, Any]:
        """Serialize this value for the payment provider."""
        payload = {
            "bill_order_bid": self.bill_order_bid,
            "creator_bid": self.creator_bid,
        }
        if self.payment_intent_id:
            payload["payment_intent_id"] = self.payment_intent_id
        if self.charge_id:
            payload["charge_id"] = self.charge_id
        return payload


def _build_refund_provider_metadata(order: BillingOrder) -> RefundProviderMetadata:
    metadata = (
        dict(order.metadata_json) if isinstance(order.metadata_json, dict) else {}
    )
    provider_extra = metadata.get("provider_extra", {}) or {}
    latest_provider_payload = metadata.get("latest_provider_payload", {}) or {}

    payment_intent_id = _normalize_bid(provider_extra.get("payment_intent_id"))
    charge_id = _normalize_bid(provider_extra.get("charge_id"))

    payment_intent_payload = latest_provider_payload.get("payment_intent", {}) or {}
    charge_payload = latest_provider_payload.get("charge", {}) or {}
    payment_intent_id = payment_intent_id or _normalize_bid(
        payment_intent_payload.get("id")
    )
    charge_id = charge_id or _normalize_bid(charge_payload.get("id"))
    charge_id = charge_id or _normalize_bid(payment_intent_payload.get("latest_charge"))

    return RefundProviderMetadata(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        payment_intent_id=payment_intent_id or None,
        charge_id=charge_id or None,
    )


def _sync_stripe_order(
    app: Flask,
    order: BillingOrder,
    *,
    session_id: str,
) -> BillingOrderProviderUpdateResult:
    stored_provider_reference = _normalize_bid(order.provider_reference_id)
    if session_id and session_id != stored_provider_reference:
        raise_error("server.order.orderStatusError")

    reference_type = _resolve_billing_order_provider_reference_type(order)
    if reference_type == "subscription":
        resolved_subscription_id = session_id or stored_provider_reference
        if not resolved_subscription_id:
            raise_error("server.order.orderNotFound")
        return _sync_stripe_subscription_order(
            app,
            order,
            subscription_id=resolved_subscription_id,
        )

    provider = _checkout_facade().get_payment_provider("stripe")
    resolved_session_id = session_id or stored_provider_reference
    if not resolved_session_id:
        raise_error("server.order.orderNotFound")

    sync_result = provider.sync_reference(
        provider_reference=resolved_session_id,
        reference_type="checkout_session",
        app=app,
    )
    session = sync_result.provider_payload.get("checkout_session", {}) or {}
    intent = sync_result.provider_payload.get("payment_intent") or None
    _validate_stripe_checkout_evidence(
        app,
        order,
        expected_session_id=resolved_session_id,
        session=session,
        intent=intent,
    )
    target_status = BILLING_ORDER_STATUS_PENDING
    failure_code = ""
    failure_message = ""
    if _is_stripe_checkout_paid(session, intent):
        target_status = BILLING_ORDER_STATUS_PAID
        paid_amount = _resolve_stripe_paid_amount(
            {"checkout_session": session, "payment_intent": intent or {}}
        )
        paid_currency = _resolve_stripe_paid_currency(
            {"checkout_session": session, "payment_intent": intent or {}}
        )
        expected_currency = str(order.currency or "").strip().upper()
        if paid_amount is None:
            target_status = BILLING_ORDER_STATUS_FAILED
            failure_code = "provider_amount_missing"
            failure_message = "Stripe checkout paid amount is missing"
        elif not paid_currency:
            target_status = BILLING_ORDER_STATUS_FAILED
            failure_code = "provider_currency_missing"
            failure_message = "Stripe checkout currency is missing"
        elif paid_amount != int(order.payable_amount or 0):
            target_status = BILLING_ORDER_STATUS_FAILED
            failure_code = "provider_amount_mismatch"
            failure_message = "Stripe checkout paid amount does not match billing order"
        elif paid_currency and expected_currency and paid_currency != expected_currency:
            target_status = BILLING_ORDER_STATUS_FAILED
            failure_code = "provider_currency_mismatch"
            failure_message = "Stripe checkout currency does not match billing order"
    elif session.get("status") == "expired":
        target_status = BILLING_ORDER_STATUS_TIMEOUT
        failure_code = "expired"
        failure_message = "Stripe checkout session expired"

    order_update = _apply_billing_order_provider_update(
        order,
        provider="stripe",
        event_type="manual_sync",
        source="sync",
        payload={
            "checkout_session": session,
            "payment_intent": intent or {},
        },
        provider_reference_id=str(session.get("id") or resolved_session_id),
        target_status=target_status,
        failure_code=failure_code,
        failure_message=failure_message,
    )
    receipt_url = ""
    charges = (intent or {}).get("charges", {}).get("data", []) if intent else []
    if charges:
        receipt_url = str(charges[0].get("receipt_url") or "")
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata=session.get("metadata") or (intent or {}).get("metadata") or None,
        checkout_session_id=str(session.get("id") or resolved_session_id),
        checkout_object=session,
        payment_intent_id=str((intent or {}).get("id") or ""),
        payment_object=intent,
        latest_charge_id=str((intent or {}).get("latest_charge") or ""),
        receipt_url=receipt_url,
        payment_method=str((intent or {}).get("payment_method") or ""),
    )
    if order.subscription_bid and target_status == BILLING_ORDER_STATUS_PAID:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_subscription_checkout_success(
                app,
                subscription,
                payload=session,
                provider="stripe",
                event_type="manual_sync",
                source="sync",
            )
    return order_update


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


def _resolve_billing_order_provider_reference_type(order: BillingOrder) -> str:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    normalized_reference_type = _normalize_bid(
        metadata.get("provider_reference_type")
    ).lower()
    if normalized_reference_type:
        return normalized_reference_type
    if (
        order.payment_provider == "stripe"
        and order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL
    ):
        return "subscription"
    if order.payment_provider == "stripe":
        return "checkout_session"
    if order.payment_provider == "pingxx":
        return "charge"
    if order.payment_provider in {"alipay", "wechatpay"}:
        return "payment"
    return ""


def _sync_stripe_subscription_order(
    app: Flask,
    order: BillingOrder,
    *,
    subscription_id: str,
) -> BillingOrderProviderUpdateResult:
    provider = _checkout_facade().get_payment_provider("stripe")
    sync_result = provider.sync_reference(
        provider_reference=subscription_id,
        reference_type="subscription",
        app=app,
    )
    subscription_payload = sync_result.provider_payload.get("subscription", {}) or {}
    target_status = _resolve_stripe_subscription_order_status(
        order, subscription_payload
    )
    failure_code = ""
    failure_message = ""
    if target_status == BILLING_ORDER_STATUS_FAILED:
        failure_code = str(subscription_payload.get("status") or "subscription_sync")
        failure_message = "Stripe subscription sync indicates renewal is not paid yet"

    order_update = _apply_billing_order_provider_update(
        order,
        provider="stripe",
        event_type="manual_sync",
        source="sync",
        payload=subscription_payload,
        provider_reference_id=str(subscription_payload.get("id") or subscription_id),
        target_status=target_status,
        failure_code=failure_code,
        failure_message=failure_message,
    )
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata=subscription_payload.get("metadata") or None,
    )
    if order.subscription_bid:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_billing_subscription_provider_update(
                app,
                subscription,
                provider="stripe",
                event_type="customer.subscription.updated",
                payload=subscription_payload,
                data_object=subscription_payload,
                source="sync",
            )
    return order_update


def _sync_pingxx_order(
    app: Flask,
    order: BillingOrder,
) -> BillingOrderProviderUpdateResult:
    if not order.provider_reference_id:
        # No pingxx charge was ever created for this order (e.g. a subscription
        # renewal preorder whose charge creation never happened). Treat it as
        # still unpaid instead of raising orderNotFound so callers such as the
        # pending-order timeout scan can expire it normally.
        return _apply_billing_order_provider_update(
            order,
            provider="pingxx",
            event_type="manual_sync",
            source="sync",
            payload={},
            provider_reference_id="",
            target_status=BILLING_ORDER_STATUS_PENDING,
        )

    provider = _checkout_facade().get_payment_provider("pingxx")
    sync_result = provider.sync_reference(
        provider_reference=order.provider_reference_id,
        reference_type="charge",
        app=app,
    )
    charge = sync_result.provider_payload.get("charge", {}) or {}
    target_status = BILLING_ORDER_STATUS_PENDING
    if charge.get("paid") or charge.get("time_paid"):
        target_status = BILLING_ORDER_STATUS_PAID
    elif charge.get("reversed"):
        target_status = BILLING_ORDER_STATUS_CANCELED

    order_update = _apply_billing_order_provider_update(
        order,
        provider="pingxx",
        event_type="manual_sync",
        source="sync",
        payload={"charge": charge},
        provider_reference_id=str(charge.get("id") or order.provider_reference_id),
        target_status=target_status,
    )
    _persist_billing_pingxx_raw_snapshot(
        order,
        create_if_missing=False,
        charge_id=str(charge.get("id") or order.provider_reference_id),
        charge_object=charge,
        transaction_no=str(charge.get("order_no") or ""),
        app_id=(
            str(charge.get("app", {}).get("id") or "")
            if isinstance(charge.get("app"), dict)
            else str(charge.get("app") or "")
        ),
        channel=str(charge.get("channel") or order.channel or ""),
        subject=str(charge.get("subject") or ""),
        body=str(charge.get("body") or ""),
        client_ip=str(charge.get("client_ip") or ""),
        extra=charge.get("extra"),
    )
    if (
        order_update.applied
        and order.subscription_bid
        and target_status == BILLING_ORDER_STATUS_PAID
    ):
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_subscription_checkout_success(
                app,
                subscription,
                payload=charge,
                provider="pingxx",
                event_type="manual_sync",
                source="sync",
            )

    return order_update


def _sync_native_order(
    app: Flask,
    order: BillingOrder,
) -> BillingOrderProviderUpdateResult:
    provider_name = _normalize_bid(order.payment_provider)
    if not order.provider_reference_id:
        # Same as pingxx: no native trade was ever created for this order, so
        # treat it as still unpaid instead of raising orderNotFound and let the
        # caller (e.g. the pending-order timeout scan) expire it normally.
        return _apply_billing_order_provider_update(
            order,
            provider=provider_name,
            event_type="manual_sync",
            source="sync",
            payload={},
            provider_reference_id="",
            target_status=BILLING_ORDER_STATUS_PENDING,
        )

    provider = _checkout_facade().get_payment_provider(provider_name)
    sync_result = provider.sync_reference(
        provider_reference=order.provider_reference_id,
        reference_type="payment",
        app=app,
    )
    trade_payload = extract_native_trade_payload(sync_result.provider_payload)
    target_status = _resolve_native_billing_order_status(
        provider_name,
        trade_payload,
    )
    raw_status = extract_native_trade_status(provider_name, trade_payload)

    order_update = _apply_billing_order_provider_update(
        order,
        provider=provider_name,
        event_type="manual_sync",
        source="sync",
        payload={"trade": trade_payload},
        provider_reference_id=str(
            trade_payload.get("out_trade_no") or order.provider_reference_id
        ),
        target_status=target_status,
    )
    _persist_billing_native_raw_snapshot(
        order,
        create_if_missing=False,
        provider_attempt_id=str(
            trade_payload.get("out_trade_no") or order.provider_reference_id
        ),
        transaction_id=str(
            trade_payload.get("trade_no")
            or trade_payload.get("transaction_id")
            or sync_result.charge_id
            or ""
        ),
        raw_status=raw_status,
        raw_snapshot_status=_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
            target_status or order.status,
            0,
        ),
        raw_response={"trade": trade_payload},
        metadata={"latest_source": "sync"},
    )
    if order.subscription_bid and target_status == BILLING_ORDER_STATUS_PAID:
        subscription = _load_subscription_by_bid(order.subscription_bid)
        if subscription is not None:
            _apply_subscription_checkout_success(
                app,
                subscription,
                payload=trade_payload,
                provider=provider_name,
                event_type="manual_sync",
                source="sync",
            )
    return order_update


def _resolve_native_billing_order_status(
    provider: str,
    payload: dict[str, object],
) -> int | None:
    return _BILLING_STATUS_BY_NATIVE_STATE.get(
        resolve_native_payment_state(provider, payload)
    )


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


def _load_billing_order_for_native_event(
    *,
    provider: str,
    provider_attempt_id: str,
    transaction_id: str = "",
) -> BillingOrder | None:
    query = BillingOrder.query.filter(
        BillingOrder.deleted == 0,
        BillingOrder.payment_provider == provider,
    )
    if provider_attempt_id:
        order = (
            query.filter(
                BillingOrder.provider_reference_id == provider_attempt_id,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
        order = (
            query.filter(BillingOrder.bill_order_bid == provider_attempt_id)
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is not None:
            return order
    if transaction_id:
        native_model = native_snapshot_model(provider)
        snapshot = (
            billing_native_snapshot_query(provider)
            .filter(
                native_model.transaction_id == transaction_id,
            )
            .order_by(native_model.id.desc())
            .first()
        )
        if snapshot is not None and snapshot.bill_order_bid:
            return (
                query.filter(BillingOrder.bill_order_bid == snapshot.bill_order_bid)
                .order_by(BillingOrder.id.desc())
                .first()
            )
    return None
