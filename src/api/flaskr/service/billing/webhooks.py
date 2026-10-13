"""Stripe and Pingxx webhook handlers for billing state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from flaskr.dao import uow
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.native_payment_status import (
    NATIVE_PAYMENT_STATE_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED,
    NATIVE_PAYMENT_STATE_PAID,
    reported_payment_currency_matches,
    resolve_native_payment_state,
)
from flaskr.service.order.payment_providers import (
    PaymentNotificationResult,
    describe_notification,
    get_payment_provider,
)
from flaskr.service.order.payment_providers.api import (
    SubscriptionFacts,
    legacy_native_amount,
    native_facts,
    saved_refund_controls_state,
)

from .checkout import (
    load_billing_order_for_native_event as _load_billing_order_for_native_event,
)
from .checkout import (
    load_billing_order_for_pingxx_event as _load_billing_order_for_pingxx_event,
)
from .checkout import (
    persist_billing_pingxx_raw_snapshot as _persist_billing_pingxx_raw_snapshot,
)
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
)
from .models import BillingOrder, BillingSubscription
from .primitives import coerce_datetime
from .primitives import normalize_bid as _normalize_bid
from .provider_catalog_sync import (
    apply_stripe_catalog_notification as _apply_stripe_catalog_notification,
)
from .provider_catalog_sync import (
    is_stripe_catalog_event as _is_stripe_catalog_event,
)
from .provider_state import (
    BillingOrderProviderUpdateResult,
    apply_subscription_contract,
    contract_can_activate,
    contract_renewal_order_status,
    paid_upgrade_can_rebind_contract,
    renewal_order_for_contract,
)
from .provider_state import (
    apply_billing_order_provider_update as _apply_billing_order_provider_update,
)
from .provider_state import (
    apply_subscription_checkout_failure as _apply_subscription_checkout_failure,
)
from .provider_state import (
    apply_subscription_checkout_success as _apply_subscription_checkout_success,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

_STRIPE_SUBSCRIPTION_EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}

_BILLING_STATUS_BY_NATIVE_STATE = {
    NATIVE_PAYMENT_STATE_PAID: BILLING_ORDER_STATUS_PAID,
    NATIVE_PAYMENT_STATE_CANCELED: BILLING_ORDER_STATUS_CANCELED,
    NATIVE_PAYMENT_STATE_FAILED: BILLING_ORDER_STATUS_FAILED,
}


@dataclass(slots=True, frozen=True)
class BillingWebhookResult:
    """Capture how an incoming billing webhook was handled."""

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
        """Serialize this result for an API response."""
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

    def __getitem__(self, key: str) -> object:
        """Return a response field by key."""
        return self.to_response_dict()[key]

    def __iter__(self) -> Iterator[Any]:
        """Yield the response payload and status code for unpacking."""
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
        app.logger.exception("Stripe billing webhook verification failed")
        return BillingWebhookResult(
            status="error",
            message=str(exc),
            status_code=400,
        )

    return apply_billing_stripe_notification(app, notification)


def is_billing_stripe_catalog_event(event_type: object) -> bool:
    """Return whether a Stripe event type belongs to billing catalog sync."""
    return _is_stripe_catalog_event(event_type)


def apply_billing_stripe_catalog_notification(
    app: Flask,
    notification: PaymentNotificationResult,
) -> tuple[dict[str, object], int]:
    """Apply a Stripe catalog notification and return a route response."""
    result = _apply_stripe_catalog_notification(app, notification)
    return result.to_response_dict(), result.status_code


def apply_billing_stripe_notification(
    app: Flask,
    notification: PaymentNotificationResult,
) -> BillingWebhookResult:
    """Compatibility entry point; all business decisions consume typed evidence."""
    return apply_billing_provider_notification(app, "stripe", notification)


def apply_billing_provider_notification(
    app: Flask,
    provider: str,
    notification: PaymentNotificationResult,
) -> BillingWebhookResult:
    """Apply a hosted payment/contract event without inspecting its protocol payload."""
    from .provider_catalog_sync import apply_registered_catalog_notification

    catalog_result = apply_registered_catalog_notification(app, provider, notification)
    if catalog_result is not None:
        return BillingWebhookResult(
            status=catalog_result.status,
            status_code=catalog_result.status_code,
            matched=True,
            event_type=catalog_result.event_type,
        )
    event = describe_notification(provider, notification)
    event_type = event.payment.event_type or notification.status
    with app_context_scope(app), unit_of_work():
        order = None
        query = BillingOrder.query.filter(
            BillingOrder.deleted == 0, BillingOrder.payment_provider == provider
        )
        if event.order_reference:
            order = (
                query.filter(BillingOrder.bill_order_bid == event.order_reference)
                .order_by(BillingOrder.id.desc())
                .first()
            )
        elif event.lookup_reference:
            order = (
                query.filter(
                    BillingOrder.payment_provider == provider,
                    BillingOrder.provider_reference_id == event.lookup_reference,
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )
        if order is None:
            from flaskr.service.order.payment_providers.api import (
                registered_native_payment_providers,
            )

            if provider in registered_native_payment_providers():
                order = _load_billing_order_for_native_event(
                    provider=provider,
                    provider_attempt_id=event.lookup_reference,
                    transaction_id=notification.charge_id or "",
                )
        subscription = None
        if order is not None and order.subscription_bid:
            from .subscriptions import load_subscription_by_bid

            subscription = load_subscription_by_bid(order.subscription_bid)
        if subscription is None and event.subscription_reference:
            from .subscriptions import load_subscription_by_bid

            subscription = load_subscription_by_bid(event.subscription_reference)
        if subscription is None and event.contract_reference:
            subscription = (
                BillingSubscription.query.filter(
                    BillingSubscription.deleted == 0,
                    BillingSubscription.billing_provider == provider,
                    BillingSubscription.provider_subscription_id
                    == event.contract_reference,
                )
                .order_by(BillingSubscription.id.desc())
                .first()
            )
        if (
            order is None
            and subscription is not None
            and subscription.billing_provider != provider
        ):
            subscription = None
        if (
            order is not None
            and subscription is not None
            and order.creator_bid != subscription.creator_bid
        ):
            message = "Payment order and contract owner mismatch"
            raise RuntimeError(message)
        if order is None and subscription is not None and event.contract is not None:
            order = renewal_order_for_contract(
                subscription.subscription_bid, event.contract
            )
        if order is None and subscription is not None:
            order = (
                query.filter(
                    BillingOrder.subscription_bid == subscription.subscription_bid
                )
                .order_by(BillingOrder.id.desc())
                .first()
            )
        if order is None and subscription is None:
            return BillingWebhookResult(
                status="ignored",
                event_type=event_type,
                bill_order_bid=event.order_reference or None,
                status_code=202,
            )

        statuses = {
            "paid": BILLING_ORDER_STATUS_PAID,
            "failed": BILLING_ORDER_STATUS_FAILED,
            "refunded": BILLING_ORDER_STATUS_REFUNDED,
            "canceled": BILLING_ORDER_STATUS_CANCELED,
        }
        target = statuses.get(event.payment.state)
        failure_code, failure_message = event.failure_code, event.failure_message
        update = BillingOrderProviderUpdateResult()
        response_status = "acknowledged"
        if order is not None:
            # Reload under the row lock before admitting a payment reference;
            # competing callbacks cannot both establish the first binding.
            order = (
                query.filter(BillingOrder.id == order.id)
                .with_for_update()
                .populate_existing()
                .first()
            )
            if order is None:
                message = "Billing payment attempt changed during notification"
                raise RuntimeError(message)
            if saved_refund_controls_state(event, order.metadata_json):
                # Saved operations own refund admission; inspect fresh locked
                # state so a concurrent retry cannot bypass identity checks.
                # Unrequested reversals retain the existing payment projection.
                target = None
            reported_reference = event.updated_payment_reference
            if (
                reported_reference
                and order.provider_reference_id
                and reported_reference != order.provider_reference_id
            ):
                message = "Billing payment notification reference mismatch"
                raise RuntimeError(message)
            if (
                target is None
                and event.kind == "contract"
                and event.contract is not None
            ):
                target = contract_renewal_order_status(order, event.contract)
            if event.validate_reported_amount:
                if not reported_payment_currency_matches(
                    expected_currency=order.currency,
                    reported_currency=event.payment.currency,
                ):
                    message = "Billing native payment currency mismatch"
                    raise RuntimeError(message)
                amount = legacy_native_amount(event.payment)
                if amount is not None and amount != int(order.payable_amount or 0):
                    message = "Billing native payment amount mismatch"
                    raise RuntimeError(message)
            if event.validate_paid_amount:
                if event.payment.order_amount is None:
                    failure_code, failure_message = (
                        "provider_amount_missing",
                        "Stripe checkout paid amount is missing",
                    )
                elif not event.payment.currency:
                    failure_code, failure_message = (
                        "provider_currency_missing",
                        "Stripe checkout currency is missing",
                    )
                elif event.payment.order_amount != int(order.payable_amount or 0):
                    failure_code, failure_message = (
                        "provider_amount_mismatch",
                        "Stripe checkout paid amount does not match billing order",
                    )
                elif (
                    str(order.currency or "").strip().upper()
                    and event.payment.currency.upper()
                    != str(order.currency).strip().upper()
                ):
                    failure_code, failure_message = (
                        "provider_currency_mismatch",
                        "Stripe checkout currency does not match billing order",
                    )
                if failure_code:
                    target = BILLING_ORDER_STATUS_FAILED
            update = _apply_billing_order_provider_update(
                order,
                provider=provider,
                event_type=event_type,
                source="webhook",
                payload=notification.provider_payload,
                provider_reference_id=event.updated_payment_reference
                or order.provider_reference_id,
                target_status=target,
                failure_code=failure_code,
                failure_message=failure_message,
                payment_facts=event.payment,
                contract_facts=event.contract if event.authoritative_contract else None,
            )
            from .checkout import apply_billing_refund_evidence

            apply_billing_refund_evidence(
                app, order, event, notification.provider_payload
            )
            # Project the admitted business state into raw snapshots, too.
            persist_provider_notification(order, provider, notification)
            response_status = {
                BILLING_ORDER_STATUS_PAID: "paid",
                BILLING_ORDER_STATUS_FAILED: "failed",
                BILLING_ORDER_STATUS_REFUNDED: "refunded",
                BILLING_ORDER_STATUS_CANCELED: "canceled",
            }.get(target, "acknowledged")
            if target != BILLING_ORDER_STATUS_PAID and not update:
                response_status = "acknowledged"
            if (
                event.kind == "refund"
                and order.status == BILLING_ORDER_STATUS_REFUNDED
                and update.previous_status != BILLING_ORDER_STATUS_REFUNDED
            ):
                response_status = "refunded"
        if subscription is not None:
            subscription = (
                BillingSubscription.query.filter(
                    BillingSubscription.id == subscription.id,
                    BillingSubscription.deleted == 0,
                )
                .with_for_update()
                .populate_existing()
                .first()
            )
            if subscription is None:
                message = "Billing subscription changed during notification"
                raise RuntimeError(message)
            if event.kind == "contract" and event.contract is not None:
                apply_subscription_contract(
                    app,
                    subscription,
                    provider=provider,
                    event_type=event_type,
                    payload=notification.provider_payload,
                    facts=event.contract,
                    allow_activation=contract_can_activate(order),
                    event_time=coerce_datetime(event.payment.event_time),
                    confirmed=event.authoritative_contract,
                    allow_rebinding=paid_upgrade_can_rebind_contract(order, update),
                )
            elif (
                target == BILLING_ORDER_STATUS_PAID
                and update.applied
                and order is not None
                and order.status == BILLING_ORDER_STATUS_PAID
                and not order.metadata_json.get("provider_period_start_at")
            ):
                apply_subscription_contract(
                    app,
                    subscription,
                    provider=provider,
                    event_type=event_type,
                    payload=notification.provider_payload,
                    facts=event.checkout_contract
                    or SubscriptionFacts(
                        provider_reference=event.contract_reference,
                        customer_reference=event.customer_reference,
                        status="active",
                    ),
                    event_time=coerce_datetime(event.payment.event_time),
                    confirmed=False,
                    allow_rebinding=paid_upgrade_can_rebind_contract(order, update),
                )
            elif (
                target == BILLING_ORDER_STATUS_FAILED
                and event.update_subscription_on_failure
            ):
                _apply_subscription_checkout_failure(
                    app,
                    subscription,
                    provider=provider,
                    event_type=event_type,
                    payload=notification.provider_payload,
                    payment_facts=event.payment,
                )
        update.stage_after_state_changes(app, order)
        uow.on_commit(lambda: update.dispatch_after_commit(app))
        return BillingWebhookResult(
            status=response_status,
            event_type=event_type,
            bill_order_bid=order.bill_order_bid if order else None,
            subscription_bid=subscription.subscription_bid if subscription else None,
            status_code=200,
        )


def persist_provider_notification(
    order: BillingOrder, provider: str, notification: PaymentNotificationResult
) -> None:
    """Dispatch only protocol persistence at the explicit integration boundary."""
    from .provider_snapshots import persist_notification

    persist_notification(order, provider, notification)


def handle_billing_pingxx_webhook(
    app: Flask,
    payload: dict[str, object],
) -> BillingWebhookResult:
    """Handle Pingxx billing callbacks using the shared billing state machine."""
    event_type = str((payload or {}).get("type", "") or "")
    charge = (payload or {}).get("data", {}).get("object", {}) or {}
    charge_id = _normalize_bid(charge.get("id"))
    order_no = _normalize_bid(charge.get("order_no"))

    with app_context_scope(app), unit_of_work():
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
        if (
            order_update.applied
            and order.subscription_bid
            and target_status == BILLING_ORDER_STATUS_PAID
        ):
            from .subscriptions import load_subscription_by_bid

            subscription = load_subscription_by_bid(order.subscription_bid)
            if subscription is not None:
                _apply_subscription_checkout_success(
                    app,
                    subscription,
                    payload=charge,
                    provider="pingxx",
                    event_type=event_type or "charge.succeeded",
                )

        order_update.stage_after_state_changes(app, order)
        uow.on_commit(lambda: order_update.dispatch_after_commit(app))
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
    payload: dict[str, object],
) -> BillingWebhookResult:
    """Handle billing alipay webhook."""
    provider = get_payment_provider("alipay")
    try:
        notification = provider.handle_notification(payload=payload, app=app)
    except Exception as exc:  # pragma: no cover - route-level verification path
        app.logger.exception("Alipay billing webhook verification failed")
        return BillingWebhookResult(status="error", message=str(exc), status_code=400)
    return apply_billing_native_notification(app, "alipay", notification)


def handle_billing_wechatpay_webhook(
    app: Flask,
    *,
    raw_body: bytes,
    headers: dict[str, str],
) -> BillingWebhookResult:
    """Handle billing wechatpay webhook."""
    provider = get_payment_provider("wechatpay")
    try:
        notification = provider.verify_webhook(
            headers=headers,
            raw_body=raw_body,
            app=app,
        )
    except Exception as exc:  # pragma: no cover - route-level verification path
        app.logger.exception("WeChat Pay billing webhook verification failed")
        return BillingWebhookResult(status="error", message=str(exc), status_code=400)
    return apply_billing_native_notification(app, "wechatpay", notification)


def apply_billing_native_notification(
    app: Flask, provider: str, notification: PaymentNotificationResult
) -> BillingWebhookResult:
    """Keep legacy routing acknowledgement while applying the common evidence path."""
    result = apply_billing_provider_notification(app, provider, notification)
    if result.status == "ignored":
        return replace(
            result,
            status="not_billing",
            matched=False,
            charge_id=notification.charge_id or None,
            order_no=notification.order_bid or None,
        )
    return replace(
        result,
        status="paid" if result.status == "paid" else "acknowledged",
        matched=True,
        charge_id=notification.charge_id or None,
        order_no=notification.order_bid or None,
    )


def _native_target_status(provider: str, payload: dict[str, object]) -> int | None:
    return _BILLING_STATUS_BY_NATIVE_STATE.get(
        resolve_native_payment_state(provider, payload)
    )


def _native_raw_snapshot_status(
    target_status: int | None,
    current_status: int | None,
) -> int:
    status = int(target_status or current_status or 0)
    if status == BILLING_ORDER_STATUS_PAID:
        return 1
    if status == BILLING_ORDER_STATUS_CANCELED:
        return 3
    if status == BILLING_ORDER_STATUS_FAILED:
        return 4
    if status == BILLING_ORDER_STATUS_REFUNDED:
        return 2
    return 0


def _extract_native_amount(provider: str, payload: dict[str, object]) -> int | None:
    """Preserve native amount validation through the shared adapter contract."""
    return legacy_native_amount(native_facts(provider, payload))
