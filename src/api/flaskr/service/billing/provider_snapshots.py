"""Provider-specific snapshot serialization, isolated from billing business policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.payment_providers.api import (
    billing_native_snapshot_query,
    billing_pingxx_snapshot_query,
    billing_stripe_snapshot_query,
    describe_notification,
    native_snapshot_model,
    registered_native_payment_providers,
    saved_refund_controls_state,
    upsert_billing_pingxx_snapshot,
    upsert_billing_stripe_snapshot,
    upsert_native_snapshot,
)
from flaskr.service.order.payment_providers.api import event_object as _event_object

from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_INIT,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
)
from .primitives import normalize_bid as _normalize_bid

if TYPE_CHECKING:
    from collections.abc import Callable

    from flaskr.service.order.payment_providers.api import (
        PaymentCreationResult,
        PaymentNotificationResult,
        PaymentRefundResult,
    )

    from .models import BillingOrder
_RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS = {
    BILLING_ORDER_STATUS_INIT: 0,
    BILLING_ORDER_STATUS_PENDING: 0,
    BILLING_ORDER_STATUS_PAID: 1,
    BILLING_ORDER_STATUS_REFUNDED: 2,
    BILLING_ORDER_STATUS_CANCELED: 3,
    BILLING_ORDER_STATUS_TIMEOUT: 3,
    BILLING_ORDER_STATUS_FAILED: 4,
}


def persist_stripe_notification(
    order: BillingOrder, notification: PaymentNotificationResult
) -> None:
    """Serialize the original Stripe object without leaking its schema to business code."""
    data = _event_object(notification.provider_payload or {})
    reference = str(data.get("id") or "")
    metadata = {
        **(data.get("metadata") or {}),
        "last_provider_notification": notification.provider_payload,
    }
    if reference.startswith("re_"):
        metadata = {**metadata, "last_refund_id": reference}
    charges = data.get("charges", {}).get("data", []) or []
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=True,
        metadata=metadata or None,
        checkout_session_id=reference if reference.startswith("cs_") else "",
        checkout_object=data if reference.startswith("cs_") else None,
        payment_intent_id=str(data.get("payment_intent") or "")
        if reference.startswith("cs_")
        else "",
        payment_object=data if reference.startswith("pi_") else None,
        latest_charge_id=str(notification.charge_id or data.get("latest_charge") or ""),
        receipt_url=str(charges[0].get("receipt_url") or "") if charges else "",
        payment_method=str(data.get("payment_method") or ""),
    )


_NOTIFICATION_WRITERS = {"stripe": persist_stripe_notification}


def register_notification_writer(
    provider: str, writer: Callable[[BillingOrder, PaymentNotificationResult], None]
) -> None:
    """Register storage for a protocol whose raw schema differs from native snapshots."""
    _NOTIFICATION_WRITERS[provider] = writer


def persist_notification(
    order: BillingOrder, provider: str, notification: PaymentNotificationResult
) -> None:
    """Store evidence without making order, subscription or entitlement decisions."""
    writer = _NOTIFICATION_WRITERS.get(provider)
    if writer is not None:
        writer(order, notification)
        return
    if provider not in registered_native_payment_providers():
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        order.metadata_json = {
            **metadata,
            "last_provider_notification": notification.provider_payload,
        }
        return
    from flaskr.service.order.payment_providers.api import notification_facts

    facts = notification_facts(provider, notification)
    managed_refund = saved_refund_controls_state(
        describe_notification(provider, notification), order.metadata_json
    )
    _persist_billing_native_raw_snapshot(
        order,
        create_if_missing=True,
        provider_attempt_id=order.provider_reference_id,
        transaction_id=notification.charge_id or "",
        raw_status=facts.raw_status,
        raw_snapshot_status=None
        if managed_refund
        else {"paid": 1, "refunded": 2, "canceled": 3, "failed": 4}.get(facts.state),
        raw_notification=notification.provider_payload,
        metadata={"latest_source": "webhook"},
    )


def persist_stripe_query(
    order: BillingOrder, notification: PaymentNotificationResult
) -> None:
    """Save Checkout, intent or contract-query snapshots in their original schema."""
    payload = notification.provider_payload or {}
    if "subscription" in payload:
        _persist_billing_stripe_raw_snapshot(
            order,
            create_if_missing=False,
            metadata=(payload["subscription"] or {}).get("metadata") or None,
        )
        return
    session, intent = (
        payload.get("checkout_session") or {},
        payload.get("payment_intent") or {},
    )
    charges = intent.get("charges", {}).get("data", []) or []
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata=session.get("metadata") or intent.get("metadata") or None,
        checkout_session_id=str(session.get("id") or order.provider_reference_id),
        checkout_object=session,
        payment_intent_id=str(intent.get("id") or ""),
        payment_object=intent or None,
        latest_charge_id=str(intent.get("latest_charge") or ""),
        receipt_url=str(charges[0].get("receipt_url") or "") if charges else "",
        payment_method=str(intent.get("payment_method") or ""),
    )


def persist_pingxx_query(
    order: BillingOrder, notification: PaymentNotificationResult
) -> None:
    """Store the legacy charge shape without changing billing state."""
    charge = notification.provider_payload.get("charge") or {}
    _persist_billing_pingxx_raw_snapshot(
        order,
        create_if_missing=False,
        charge_id=str(charge.get("id") or order.provider_reference_id),
        charge_object=charge,
        transaction_no=str(charge.get("order_no") or ""),
        app_id=str(charge.get("app", {}).get("id") or "")
        if isinstance(charge.get("app"), dict)
        else str(charge.get("app") or ""),
        channel=str(charge.get("channel") or order.channel or ""),
        subject=str(charge.get("subject") or ""),
        body=str(charge.get("body") or ""),
        client_ip=str(charge.get("client_ip") or ""),
        extra=charge.get("extra"),
    )


_QUERY_WRITERS = {"stripe": persist_stripe_query, "pingxx": persist_pingxx_query}


def register_query_writer(
    provider: str, writer: Callable[[BillingOrder, PaymentNotificationResult], None]
) -> None:
    """Register query evidence storage independently from native table schemas."""
    _QUERY_WRITERS[provider] = writer


def persist_query(order: BillingOrder, notification: PaymentNotificationResult) -> None:
    """Keep query storage and original schemas behind one integration boundary."""
    writer = _QUERY_WRITERS.get(order.payment_provider)
    if writer is not None:
        writer(order, notification)
        return
    if order.payment_provider not in registered_native_payment_providers():
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        order.metadata_json = {
            **metadata,
            "last_provider_query": notification.provider_payload,
        }
        return
    from flaskr.service.order.payment_providers.api import notification_facts

    facts = notification_facts(order.payment_provider, notification)
    _persist_billing_native_raw_snapshot(
        order,
        create_if_missing=False,
        provider_attempt_id=order.provider_reference_id,
        transaction_id=notification.charge_id or "",
        raw_status=facts.raw_status,
        raw_response=notification.provider_payload,
        metadata={"latest_source": "sync"},
    )


_CHECKOUT_WRITERS: dict[str, Callable[..., None]] = {}


def register_checkout_writer(provider: str, writer: Callable[..., None]) -> None:
    """Register original checkout evidence independently from native tables."""
    _CHECKOUT_WRITERS[provider] = writer


def _persist_billing_raw_snapshot_from_checkout(
    order: BillingOrder,
    result: PaymentCreationResult,
    *,
    subject: str = "",
    body: str = "",
    raw_snapshot_status: int | None = None,
    independent: bool = False,
) -> None:
    """Record a provider attempt against the order.

    ``raw_snapshot_status`` overrides the status the snapshot is stored with.
    Pass it for an attempt whose outcome is not the order's: a charge created
    after the order was settled elsewhere is itself still pending.
    ``independent`` retains a conflicting creation result without overwriting
    the current raw payment row; registered writers own the equivalent rule.
    """
    writer = _CHECKOUT_WRITERS.get(order.payment_provider)
    if writer is not None:
        writer(
            order,
            result,
            subject=subject,
            body=body,
            raw_snapshot_status=raw_snapshot_status,
        )
        return
    if independent:
        _persist_checkout_receipt_metadata(
            order,
            result,
            subject=subject,
            body=body,
            raw_snapshot_status=raw_snapshot_status,
        )
        return
    if order.payment_provider == "stripe":
        _persist_billing_stripe_raw_snapshot(
            order,
            create_if_missing=True,
            raw_snapshot_status=raw_snapshot_status,
            metadata=result.extra.get("metadata") or {},
            checkout_session_id=result.checkout_session_id or result.provider_reference,
            checkout_object=result.raw_response or {},
            payment_intent_id=str(result.extra.get("payment_intent_id") or ""),
            payment_object=result.extra.get("payment_intent_object") or None,
            latest_charge_id=str(result.extra.get("latest_charge_id") or ""),
            receipt_url=str(result.extra.get("receipt_url") or ""),
            payment_method=str(result.extra.get("payment_method") or ""),
        )
        return

    if order.payment_provider == "pingxx":
        charge = result.raw_response or {}
        _persist_billing_pingxx_raw_snapshot(
            order,
            create_if_missing=True,
            raw_snapshot_status=raw_snapshot_status,
            charge_id=str(result.provider_reference or ""),
            charge_object=charge,
            transaction_no=str(charge.get("order_no") or ""),
            app_id=(
                str(charge.get("app", {}).get("id") or "")
                if isinstance(charge.get("app"), dict)
                else str(charge.get("app") or "")
            ),
            channel=str(charge.get("channel") or order.channel or ""),
            subject=str(charge.get("subject") or subject or ""),
            body=str(charge.get("body") or body or ""),
            client_ip=str(charge.get("client_ip") or ""),
            extra=charge.get("extra"),
        )
        return

    if order.payment_provider in registered_native_payment_providers():
        _persist_billing_native_raw_snapshot(
            order,
            create_if_missing=True,
            raw_snapshot_status=raw_snapshot_status,
            provider_attempt_id=str(result.provider_reference or order.bill_order_bid),
            transaction_id="",
            raw_status="pending",
            raw_request=result.extra.get("raw_request") or {},
            raw_response=result.raw_response or {},
            metadata={
                "provider_extra": result.extra or {},
                "subject": subject,
                "body": body,
            },
        )
        return

    _persist_checkout_receipt_metadata(
        order,
        result,
        subject=subject,
        body=body,
        raw_snapshot_status=raw_snapshot_status,
    )


def _persist_checkout_receipt_metadata(
    order: BillingOrder,
    result: PaymentCreationResult,
    *,
    subject: str,
    body: str,
    raw_snapshot_status: int | None,
) -> None:
    """Keep an independent receipt without changing the current raw payment row."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    stored = metadata.get("provider_checkout_attempts") or []
    attempts = list(stored) if isinstance(stored, list) else []
    receipt = {
        "result": asdict(result),
        "subject": subject,
        "body": body,
        "status": raw_snapshot_status
        if raw_snapshot_status is not None
        else _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(int(order.status or 0), 0),
    }
    attempts = [
        entry
        for entry in attempts
        if not isinstance(entry, dict)
        or (entry.get("result") or {}).get("provider_reference")
        != result.provider_reference
    ]
    order.metadata_json = {
        **metadata,
        "provider_checkout_attempts": [*attempts, receipt],
    }


def _persist_billing_stripe_raw_snapshot(
    order: BillingOrder,
    *,
    create_if_missing: bool,
    raw_snapshot_status: int | None = None,
    metadata: object | None = None,
    checkout_session_id: str = "",
    checkout_object: object | None = None,
    payment_intent_id: str = "",
    payment_object: object | None = None,
    latest_charge_id: str = "",
    receipt_url: str = "",
    payment_method: str = "",
) -> None:
    raw_status = (
        int(raw_snapshot_status)
        if raw_snapshot_status is not None
        else _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
            int(order.status or BILLING_ORDER_STATUS_INIT), 0
        )
    )
    existing = (
        billing_stripe_snapshot_query()
        .filter(StripeOrder.bill_order_bid == order.bill_order_bid)
        .order_by(StripeOrder.id.desc())
        .first()
    )
    if existing is None and not create_if_missing:
        return

    snapshot = upsert_billing_stripe_snapshot(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        amount=int(order.payable_amount or 0),
        currency=str(order.currency or "usd").lower(),
        raw_status=raw_status,
        metadata=metadata,
        checkout_session_id=checkout_session_id,
        checkout_object=checkout_object,
        payment_intent_id=payment_intent_id,
        payment_object=payment_object,
        latest_charge_id=latest_charge_id,
        receipt_url=receipt_url,
        payment_method=payment_method,
    )
    db.session.add(snapshot)


def _persist_billing_pingxx_raw_snapshot(
    order: BillingOrder,
    *,
    create_if_missing: bool,
    raw_snapshot_status: int | None = None,
    charge_id: str = "",
    charge_object: object | None = None,
    transaction_no: str = "",
    app_id: str = "",
    channel: str = "",
    subject: str = "",
    body: str = "",
    client_ip: str = "",
    extra: object | None = None,
) -> None:
    raw_status = (
        int(raw_snapshot_status)
        if raw_snapshot_status is not None
        else _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
            int(order.status or BILLING_ORDER_STATUS_INIT), 0
        )
    )
    existing = (
        billing_pingxx_snapshot_query()
        .filter(PingxxOrder.bill_order_bid == order.bill_order_bid)
        .order_by(PingxxOrder.id.desc())
        .first()
    )
    if existing is None and not create_if_missing:
        return

    snapshot = upsert_billing_pingxx_snapshot(
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        amount=int(order.payable_amount or 0),
        currency=str(order.currency or "CNY"),
        raw_status=raw_status,
        charge_id=charge_id,
        charge_object=charge_object,
        transaction_no=transaction_no,
        app_id=app_id,
        channel=channel,
        subject=subject,
        body=body,
        client_ip=client_ip,
        extra=extra,
    )
    db.session.add(snapshot)


def _persist_billing_native_raw_snapshot(
    order: BillingOrder,
    *,
    create_if_missing: bool,
    provider_attempt_id: str = "",
    transaction_id: str = "",
    raw_status: str = "",
    raw_snapshot_status: int | None = None,
    raw_request: object | None = None,
    raw_response: object | None = None,
    raw_notification: object | None = None,
    metadata: object | None = None,
) -> None:
    resolved_raw_snapshot_status = (
        int(raw_snapshot_status)
        if raw_snapshot_status is not None
        else _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS.get(
            int(order.status or BILLING_ORDER_STATUS_INIT), 0
        )
    )
    native_model = native_snapshot_model(order.payment_provider)
    existing = (
        billing_native_snapshot_query(order.payment_provider)
        .filter(
            native_model.bill_order_bid == order.bill_order_bid,
        )
        .order_by(native_model.id.desc())
        .first()
    )
    if existing is None and not create_if_missing:
        return

    snapshot = upsert_native_snapshot(
        biz_domain="billing",
        payment_provider=order.payment_provider,
        native_payment_order_bid=order.bill_order_bid,
        provider_attempt_id=provider_attempt_id or order.provider_reference_id,
        bill_order_bid=order.bill_order_bid,
        creator_bid=order.creator_bid,
        amount=int(order.payable_amount or 0),
        currency=str(order.currency or "CNY"),
        raw_status=raw_status,
        raw_snapshot_status=resolved_raw_snapshot_status,
        transaction_id=transaction_id,
        channel=str(order.channel or ""),
        raw_request=raw_request,
        raw_response=raw_response,
        raw_notification=raw_notification,
        metadata=metadata,
    )
    db.session.add(snapshot)


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


def _stripe_refund_metadata(order: BillingOrder) -> dict[str, object]:
    metadata = _build_refund_provider_metadata(order).to_provider_payload()
    # A verified Checkout callback can precede the creation response. Its
    # original snapshot remains the durable source of the refundable intent,
    # even after later contract/refund events replace the latest payload.
    if not metadata.get("payment_intent_id") and not metadata.get("charge_id"):
        snapshot = (
            billing_stripe_snapshot_query()
            .filter(StripeOrder.bill_order_bid == order.bill_order_bid)
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if snapshot is not None:
            if snapshot.payment_intent_id:
                metadata["payment_intent_id"] = snapshot.payment_intent_id
            if snapshot.latest_charge_id:
                metadata["charge_id"] = snapshot.latest_charge_id
    return metadata


def _persist_stripe_refund(order: BillingOrder, result: PaymentRefundResult) -> None:
    _persist_billing_stripe_raw_snapshot(
        order,
        create_if_missing=False,
        metadata={
            "last_refund_id": result.provider_reference,
            "refund_status": result.status,
        },
        payment_object=result.raw_response,
    )


_REFUND_METADATA_READERS = {"stripe": _stripe_refund_metadata}
_REFUND_WRITERS = {"stripe": _persist_stripe_refund}


def register_refund_writer(
    provider: str, writer: Callable[[BillingOrder, PaymentRefundResult], None]
) -> None:
    """Let a protocol keep refund evidence in its own storage schema."""
    _REFUND_WRITERS[provider] = writer


def refund_metadata(order: BillingOrder) -> dict[str, object]:
    """Resolve protocol refund references without exposing raw shapes to business."""
    reader = _REFUND_METADATA_READERS.get(order.payment_provider)
    if reader:
        return reader(order)
    return {
        "bill_order_bid": order.bill_order_bid,
        "creator_bid": order.creator_bid,
        "provider_reference": order.provider_reference_id,
    }


def persist_refund(order: BillingOrder, result: PaymentRefundResult) -> None:
    """Keep refund storage in the integration's existing schema."""
    writer = _REFUND_WRITERS.get(order.payment_provider)
    if writer:
        writer(order, result)
        return
    if order.payment_provider not in registered_native_payment_providers():
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        order.metadata_json = {
            **metadata,
            "last_refund_id": result.provider_reference,
            "refund_status": result.status,
            "last_refund_response": result.raw_response,
        }
        return
    _persist_billing_native_raw_snapshot(
        order,
        create_if_missing=False,
        metadata={
            "last_refund_id": result.provider_reference,
            "refund_status": result.status,
        },
        raw_response=result.raw_response,
    )
