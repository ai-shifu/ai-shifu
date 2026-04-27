"""Stripe and Pingxx webhook handlers for billing state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.order.payment_providers import (
    PaymentNotificationResult,
    get_payment_provider,
)

from .checkout import (
    load_billing_order_for_pingxx_event as _load_billing_order_for_pingxx_event,
    load_billing_order_for_native_event as _load_billing_order_for_native_event,
    load_billing_order_for_stripe_event as _load_billing_order_for_stripe_event,
    load_billing_subscription_for_stripe_event as _load_billing_subscription_for_stripe_event,
    persist_billing_native_raw_snapshot as _persist_billing_native_raw_snapshot,
    persist_billing_pingxx_raw_snapshot as _persist_billing_pingxx_raw_snapshot,
    persist_billing_stripe_raw_snapshot as _persist_billing_stripe_raw_snapshot,
)
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
)
from .provider_state import (
    BillingOrderProviderUpdateResult,
    apply_billing_order_provider_update as _apply_billing_order_provider_update,
    apply_billing_subscription_provider_update as _apply_billing_subscription_provider_update,
    apply_subscription_checkout_failure as _apply_subscription_checkout_failure,
    apply_subscription_checkout_success as _apply_subscription_checkout_success,
    extract_stripe_failure_code as _extract_stripe_failure_code,
    extract_stripe_failure_message as _extract_stripe_failure_message,
    extract_stripe_provider_reference as _extract_stripe_provider_reference,
    load_billing_renewal_order_for_stripe_event as _load_billing_renewal_order_for_stripe_event,
    map_stripe_order_status as _map_stripe_order_status,
    resolve_stripe_subscription_order_status as _resolve_stripe_subscription_order_status,
)
from .queries import (
    load_latest_billing_order_by_subscription as _load_latest_billing_order_by_subscription,
)
from .primitives import normalize_bid as _normalize_bid

_STRIPE_SUBSCRIPTION_EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


@dataclass(slots=True, frozen=True)
class BillingWebhookResult:
    status: str
    status_code: int
    message: str | None = None
    matched: bool | None = None
    event_type: str | None = None
    bill_order_bid: str | None = None
    subscription_bid: str | None = None
    charge_id: str | None = None
    order_no: str | None = None

    def to_response_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "event_type": self.event_type,
            "bill_order_bid": self.bill_order_bid,
            "subscription_bid": self.subscription_bid,
            "matched": self.matched,
            "charge_id": self.charge_id,
            "order_no": self.order_no,
        }
        if self.message is not None:
            payload["message"] = self.message
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.to_response_dict()[key]

    def __iter__(self):
        yield self.to_response_dict()
        yield self.status_code


def handle_billing_stripe_webhook(
    app: Flask,
    raw_body: bytes,
    sig_header: str,
) -> BillingWebhookResult:
    """Handle Stripe billing webhooks using the shared provider verifier."""

    provider = get_payment_provider("stripe")
    try:
        notification: PaymentNotificationResult = provider.verify_webhook(
            headers={"Stripe-Signature": sig_header},
            raw_body=raw_body,
            app=app,
        )
    except Exception as exc:  # pragma: no cover - verified via route tests
        app.logger.exception("Stripe billing webhook verification failed: %s", exc)
        return BillingWebhookResult(
            status="error",
            message=str(exc),
            status_code=400,
        )

    return apply_billing_stripe_notification(app, notification)


def apply_billing_stripe_notification(
    app: Flask,
    notification: PaymentNotificationResult,
) -> BillingWebhookResult:
    """Apply a normalized Stripe notification to billing state."""

    event = notification.provider_payload or {}
    event_type = str(notification.status or event.get("type") or "")
    data_object = event.get("data", {}).get("object", {}) or {}
    metadata = data_object.get("metadata", {}) or {}
    bill_order_bid = _normalize_bid(
        metadata.get("bill_order_bid")
        or notification.order_bid
        or metadata.get("order_bid")
    )

    with app.app_context():
        order = _load_billing_order_for_stripe_event(
            bill_order_bid=bill_order_bid,
            data_object=data_object,
        )
        subscription = _load_billing_subscription_for_stripe_event(
            order=order,
            data_object=data_object,
            metadata=metadata,
        )
        if order is None and subscription is not None:
            order = _load_billing_renewal_order_for_stripe_event(
                subscription.subscription_bid,
                data_object,
            )
        if order is None and subscription is not None:
            order = _load_latest_billing_order_by_subscription(
                subscription.subscription_bid
            )

        if order is None and subscription is None:
            app.logger.warning(
                "Billing Stripe webhook ignored. event_type=%s bill_order_bid=%s",
                event_type,
                bill_order_bid,
            )
            return BillingWebhookResult(
                status="ignored",
                event_type=event_type,
                bill_order_bid=bill_order_bid or None,
                status_code=202,
            )

        response_status = "acknowledged"
        order_update = BillingOrderProviderUpdateResult()
        if order is not None:
            target_status = _map_stripe_order_status(event_type)
            if target_status is None and event_type in _STRIPE_SUBSCRIPTION_EVENT_TYPES:
                target_status = _resolve_stripe_subscription_order_status(
                    order,
                    data_object,
                )
            order_update = _apply_billing_order_provider_update(
                order,
                provider="stripe",
                event_type=event_type,
                source="webhook",
                payload=event,
                provider_reference_id=_extract_stripe_provider_reference(
                    order=order,
                    event_type=event_type,
                    data_object=data_object,
                ),
                target_status=target_status,
                failure_code=_extract_stripe_failure_code(data_object),
                failure_message=_extract_stripe_failure_message(data_object),
            )
            stripe_object_id = str(data_object.get("id") or "")
            refund_metadata: dict[str, Any] = {}
            if stripe_object_id.startswith("re_"):
                refund_metadata["last_refund_id"] = stripe_object_id
            checkout_object = (
                data_object if stripe_object_id.startswith("cs_") else None
            )
            payment_object = data_object if stripe_object_id.startswith("pi_") else None
            receipt_url = ""
            charges = data_object.get("charges", {}).get("data", []) or []
            if charges:
                receipt_url = str(charges[0].get("receipt_url") or "")
            _persist_billing_stripe_raw_snapshot(
                order,
                create_if_missing=False,
                metadata=(metadata or refund_metadata)
                if (metadata or refund_metadata)
                else None,
                checkout_session_id=(
                    stripe_object_id if stripe_object_id.startswith("cs_") else ""
                ),
                checkout_object=checkout_object,
                payment_intent_id=(
                    str(data_object.get("payment_intent") or "")
                    if checkout_object is not None
                    else ""
                ),
                payment_object=payment_object,
                latest_charge_id=_normalize_bid(
                    notification.charge_id or data_object.get("latest_charge")
                ),
                receipt_url=receipt_url,
                payment_method=str(data_object.get("payment_method") or ""),
            )
            if target_status == BILLING_ORDER_STATUS_PAID:
                response_status = "paid"
            elif target_status == BILLING_ORDER_STATUS_FAILED:
                response_status = "failed" if order_update else "acknowledged"
            elif target_status == BILLING_ORDER_STATUS_REFUNDED:
                response_status = "refunded" if order_update else "acknowledged"
            elif target_status == BILLING_ORDER_STATUS_CANCELED:
                response_status = "canceled" if order_update else "acknowledged"

        if subscription is not None:
            if event_type in _STRIPE_SUBSCRIPTION_EVENT_TYPES:
                _apply_billing_subscription_provider_update(
                    app,
                    subscription,
                    provider="stripe",
                    event_type=event_type,
                    payload=event,
                    data_object=data_object,
                )
            elif _map_stripe_order_status(event_type) == BILLING_ORDER_STATUS_PAID:
                _apply_subscription_checkout_success(
                    app,
                    subscription,
                    payload={
                        **data_object,
                        "created": event.get("created"),
                    },
                    provider="stripe",
                    event_type=event_type,
                )
            elif _map_stripe_order_status(event_type) == BILLING_ORDER_STATUS_FAILED:
                _apply_subscription_checkout_failure(
                    app,
                    subscription,
                    provider="stripe",
                    event_type=event_type,
                    payload=event,
                )

        order_update.stage_after_state_changes(app, order)

        db.session.commit()
        order_update.dispatch_after_commit(app)
        return BillingWebhookResult(
            status=response_status,
            event_type=event_type,
            bill_order_bid=order.bill_order_bid if order else None,
            subscription_bid=subscription.subscription_bid if subscription else None,
            status_code=200,
        )


def handle_billing_pingxx_webhook(
    app: Flask,
    payload: dict[str, Any],
) -> BillingWebhookResult:
    """Handle Pingxx billing callbacks using the shared billing state machine."""

    event_type = str((payload or {}).get("type", "") or "")
    charge = (payload or {}).get("data", {}).get("object", {}) or {}
    charge_id = _normalize_bid(charge.get("id"))
    order_no = _normalize_bid(charge.get("order_no"))

    with app.app_context():
        order = _load_billing_order_for_pingxx_event(
            charge_id=charge_id,
            order_no=order_no,
        )
        if order is None:
            return BillingWebhookResult(
                status="not_billing",
                matched=False,
                event_type=event_type or None,
                charge_id=charge_id or None,
                order_no=order_no or None,
                status_code=202,
            )

        target_status = None
        if event_type == "charge.succeeded":
            target_status = BILLING_ORDER_STATUS_PAID

        order_update = _apply_billing_order_provider_update(
            order,
            provider="pingxx",
            event_type=event_type,
            source="webhook",
            payload=payload,
            provider_reference_id=charge_id or order.provider_reference_id,
            target_status=target_status,
        )
        _persist_billing_pingxx_raw_snapshot(
            order,
            create_if_missing=False,
            charge_id=charge_id or order.provider_reference_id,
            charge_object=charge,
            transaction_no=order_no,
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
        order_update.stage_after_state_changes(app, order)
        db.session.commit()
        order_update.dispatch_after_commit(app)
        return BillingWebhookResult(
            status="paid"
            if target_status == BILLING_ORDER_STATUS_PAID
            else "acknowledged",
            matched=True,
            event_type=event_type or None,
            bill_order_bid=order.bill_order_bid,
            status_code=200,
        )


def handle_billing_alipay_webhook(
    app: Flask,
    payload: dict[str, Any],
) -> BillingWebhookResult:
    provider = get_payment_provider("alipay")
    try:
        notification = provider.handle_notification(payload=payload, app=app)
    except Exception as exc:  # pragma: no cover - route-level verification path
        app.logger.exception("Alipay billing webhook verification failed: %s", exc)
        return BillingWebhookResult(status="error", message=str(exc), status_code=400)
    return apply_billing_native_notification(app, "alipay", notification)


def handle_billing_wechatpay_webhook(
    app: Flask,
    *,
    raw_body: bytes,
    headers: dict[str, str],
) -> BillingWebhookResult:
    provider = get_payment_provider("wechatpay")
    try:
        notification = provider.verify_webhook(
            headers=headers,
            raw_body=raw_body,
            app=app,
        )
    except Exception as exc:  # pragma: no cover - route-level verification path
        app.logger.exception("WeChat Pay billing webhook verification failed: %s", exc)
        return BillingWebhookResult(status="error", message=str(exc), status_code=400)
    return apply_billing_native_notification(app, "wechatpay", notification)


def apply_billing_native_notification(
    app: Flask,
    provider: str,
    notification: PaymentNotificationResult,
) -> BillingWebhookResult:
    normalized_provider = _normalize_bid(provider)
    event_type = str(notification.status or "")
    provider_attempt_id = _normalize_bid(notification.order_bid)
    transaction_id = _normalize_bid(notification.charge_id)
    provider_payload = notification.provider_payload or {}
    trade_payload = _native_trade_payload(provider_payload)

    with app.app_context():
        order = _load_billing_order_for_native_event(
            provider=normalized_provider,
            provider_attempt_id=provider_attempt_id,
            transaction_id=transaction_id,
        )
        if order is None:
            return BillingWebhookResult(
                status="not_billing",
                matched=False,
                event_type=event_type or None,
                charge_id=transaction_id or None,
                order_no=provider_attempt_id or None,
                status_code=202,
            )

        actual_amount = _extract_native_amount(normalized_provider, provider_payload)
        if (
            actual_amount is not None
            and int(order.payable_amount or 0) != actual_amount
        ):
            raise RuntimeError("Billing native payment amount mismatch")

        target_status = _native_target_status(normalized_provider, trade_payload)
        order_update = _apply_billing_order_provider_update(
            order,
            provider=normalized_provider,
            event_type=event_type or "payment.notification",
            source="webhook",
            payload=provider_payload,
            provider_reference_id=provider_attempt_id or order.provider_reference_id,
            target_status=target_status,
        )
        _persist_billing_native_raw_snapshot(
            order,
            create_if_missing=False,
            provider_attempt_id=provider_attempt_id or order.provider_reference_id,
            transaction_id=transaction_id,
            raw_status=_native_status(normalized_provider, trade_payload),
            raw_notification=provider_payload,
            metadata={"latest_source": "webhook"},
        )
        if order.subscription_bid and target_status == BILLING_ORDER_STATUS_PAID:
            from .subscriptions import load_subscription_by_bid

            subscription = load_subscription_by_bid(order.subscription_bid)
            if subscription is not None:
                _apply_subscription_checkout_success(
                    app,
                    subscription,
                    payload=trade_payload,
                    provider=normalized_provider,
                    event_type=event_type or "payment.notification",
                )

        order_update.stage_after_state_changes(app, order)
        db.session.commit()
        order_update.dispatch_after_commit(app)
        return BillingWebhookResult(
            status="paid"
            if target_status == BILLING_ORDER_STATUS_PAID
            else "acknowledged",
            matched=True,
            event_type=event_type or None,
            bill_order_bid=order.bill_order_bid,
            charge_id=transaction_id or None,
            order_no=provider_attempt_id or None,
            status_code=200,
        )


def _native_trade_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    trade = payload.get("trade", {})
    if isinstance(trade, dict) and trade:
        return trade
    resource = payload.get("resource", {})
    if isinstance(resource, dict) and resource:
        return resource
    return payload


def _native_status(provider: str, payload: dict[str, Any]) -> str:
    if provider == "alipay":
        return str(payload.get("trade_status") or "")
    if provider == "wechatpay":
        return str(payload.get("trade_state") or "")
    return ""


def _native_target_status(provider: str, payload: dict[str, Any]) -> int | None:
    status = _native_status(provider, payload).upper()
    if provider == "alipay":
        if status in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return BILLING_ORDER_STATUS_PAID
        if status == "TRADE_CLOSED":
            return BILLING_ORDER_STATUS_CANCELED
        return None
    if provider == "wechatpay":
        if status == "SUCCESS":
            return BILLING_ORDER_STATUS_PAID
        if status in {"CLOSED", "REVOKED"}:
            return BILLING_ORDER_STATUS_CANCELED
        if status == "PAYERROR":
            return BILLING_ORDER_STATUS_FAILED
        return None
    return None


def _extract_native_amount(provider: str, payload: dict[str, Any]) -> int | None:
    if provider == "alipay":
        value = payload.get("total_amount") if isinstance(payload, dict) else None
        if value in (None, ""):
            return None
        from decimal import Decimal

        return int((Decimal(str(value)) * 100).to_integral_value())
    if provider == "wechatpay":
        resource = payload.get("resource", {}) if isinstance(payload, dict) else {}
        amount = resource.get("amount", {}) if isinstance(resource, dict) else {}
        if not isinstance(amount, dict):
            return None
        value = amount.get("payer_total", amount.get("total"))
        if value in (None, ""):
            return None
        return int(value)
    return None
