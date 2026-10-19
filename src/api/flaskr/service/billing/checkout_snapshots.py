"""Raw provider snapshot persistence for billing orders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.raw_snapshots import (
    billing_native_snapshot_query,
    billing_pingxx_snapshot_query,
    billing_stripe_snapshot_query,
    native_snapshot_model,
    upsert_billing_pingxx_snapshot,
    upsert_billing_stripe_snapshot,
    upsert_native_snapshot,
)

from .checkout_orders import (
    _RAW_SNAPSHOT_STATUS_BY_BILLING_STATUS,
)
from .consts import (
    BILLING_ORDER_STATUS_INIT,
)

if TYPE_CHECKING:
    from flaskr.service.order.payment_providers import (
        PaymentCreationResult,
    )

    from .models import (
        BillingOrder,
    )


def _persist_billing_raw_snapshot_from_checkout(
    order: BillingOrder,
    result: PaymentCreationResult,
    *,
    subject: str = "",
    body: str = "",
    raw_snapshot_status: int | None = None,
) -> None:
    """Record a provider attempt against the order.

    ``raw_snapshot_status`` overrides the status the snapshot is stored with.
    Pass it for an attempt whose outcome is not the order's: a charge created
    after the order was settled elsewhere is itself still pending.
    """
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

    if order.payment_provider in {"alipay", "wechatpay"}:
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
