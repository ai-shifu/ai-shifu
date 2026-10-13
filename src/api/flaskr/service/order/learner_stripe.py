"""Stripe's legacy learner protocol, delegating purchase rules and fulfillment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import raise_error

from .consts import ORDER_STATUS_SUCCESS
from .learner_payments import _stringify_payload
from .models import Order, StripeOrder
from .payment_policy import (
    purchase_attempt_can_complete,
    purchase_attempt_matches,
    saved_refund_controls_state,
)
from .raw_snapshots import legacy_stripe_snapshot_query

if TYPE_CHECKING:
    from flask import Flask

    from .payment_providers.base import PaymentNotificationResult


def sync_stripe_checkout_session(
    app: Flask,
    order_id: str,
    session_id: str | None = None,
    expected_user: str | None = None,
) -> dict[str, Any]:
    """Synchronize stripe checkout session."""
    from .funs import (
        _app_context_scope,
        _assert_payment_lifecycle_lock_owned,
        _order_credential_scope,
        get_payment_details,
        get_payment_provider,
        payment_lifecycle_lock,
        success_buy_record,
    )

    with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_id):
        order = (
            Order.query.filter(
                Order.order_bid == order_id,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .with_for_update()
            .first()
        )
        if not order:
            raise_error("server.order.orderNotFound")
        if expected_user and order.user_bid != expected_user:
            raise_error("server.order.orderNotFound")

        if order.payment_channel != "stripe":
            raise_error("server.pay.payChannelNotSupport")

        stripe_order = (
            legacy_stripe_snapshot_query()
            .filter(
                StripeOrder.order_bid == order.order_bid,
            )
            .order_by(StripeOrder.id.desc())
            .with_for_update()
            .first()
        )
        if not stripe_order:
            raise_error("server.order.orderNotFound")

        resolved_session_id = session_id or stripe_order.checkout_session_id
        if resolved_session_id and isinstance(resolved_session_id, str):
            placeholder = resolved_session_id.strip().strip("{}").upper()
            if placeholder in {"CHECKOUT_SESSION_ID", "SESSION_ID"}:
                resolved_session_id = stripe_order.checkout_session_id

        if not resolved_session_id:
            raise_error("server.order.orderNotFound")
        if resolved_session_id != stripe_order.checkout_session_id:
            raise_error("server.order.orderNotFound")

        provider = get_payment_provider("stripe")
        with _order_credential_scope(app, order):
            sync_result = provider.sync_reference(
                provider_reference=resolved_session_id,
                reference_type="checkout_session",
                app=app,
            )
        session = sync_result.provider_payload.get("checkout_session", {}) or {}
        intent = sync_result.provider_payload.get("payment_intent") or None
        if not _stripe_provider_objects_match_attempt(
            order=order,
            stripe_order=stripe_order,
            notification_order_bid=sync_result.order_bid,
            session=session,
            intent=intent,
        ):
            raise_error("server.order.orderNotFound")

        paid = _is_stripe_payment_successful(session=session, intent=intent)
        if paid:
            already_completed = (
                order.status == ORDER_STATUS_SUCCESS
                # Earlier syncs left fulfilled orders with pending/expired snapshots.
                and stripe_order.status in {0, 1, 3}
                and _stripe_attempt_matches_order(order, stripe_order)
            )
            if not already_completed and not _stripe_attempt_can_complete(
                order, stripe_order
            ):
                raise_error("server.order.orderStatusError")

        _update_stripe_order_snapshot(
            stripe_order=stripe_order, session=session, intent=intent
        )
        if paid:
            stripe_order.status = 1

        if paid and order.status != ORDER_STATUS_SUCCESS:
            success_buy_record(app, order.order_bid)

        _assert_payment_lifecycle_lock_owned()
        return get_payment_details(app, order.order_bid)


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
        legacy_stripe_snapshot_query()
        .filter(StripeOrder.order_bid == order.order_bid)
        .order_by(StripeOrder.id.desc())
        .with_entities(StripeOrder.id)
        .first()
    )
    latest_attempt_id = latest_attempt[0] if latest_attempt else None
    return purchase_attempt_matches(
        price=order.paid_price,
        attempt_amount=int(stripe_order.amount or 0),
        attempt_id=stripe_order.id,
        latest_id=latest_attempt_id,
    )


def _stripe_attempt_can_complete(order: Order, stripe_order: StripeOrder) -> bool:
    """Apply the lifecycle gate shared by Stripe sync and webhooks."""
    return purchase_attempt_can_complete(
        order_status=order.status,
        attempt_status=stripe_order.status,
        current_attempt=_stripe_attempt_matches_order(order, stripe_order),
        eligible_attempt_statuses=(0, 4),
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


def handle_stripe_webhook(
    app: Flask,
    raw_body: bytes,
    sig_header: str,
    *,
    expected_integration_bid: str = "",
) -> tuple[dict[str, object], int]:
    """Handle stripe webhook."""
    from .funs import (
        _app_context_scope,
        _assert_payment_lifecycle_lock_owned,
        get_payment_provider,
        payment_lifecycle_lock,
        success_buy_record,
    )

    provider = get_payment_provider("stripe")
    try:
        notification: PaymentNotificationResult = provider.verify_webhook(
            headers={"Stripe-Signature": sig_header},
            raw_body=raw_body,
            app=app,
        )
    except Exception as exc:  # pragma: no cover - verified via tests for error path
        app.logger.exception("Stripe webhook verification failed")
        return {
            "status": "error",
            "message": str(exc),
        }, 400

    event = notification.provider_payload or {}
    event_type = notification.status
    data_object = event.get("data", {}).get("object", {}) or {}
    from flaskr.service.billing.api import (
        apply_stripe_catalog_notification,
        is_stripe_catalog_event,
    )

    if is_stripe_catalog_event(event_type):
        return apply_stripe_catalog_notification(app, notification)

    metadata = data_object.get("metadata", {}) or {}
    bill_order_bid = metadata.get("bill_order_bid", "")
    is_billing_subscription_event = bool(
        data_object.get("subscription")
        or str(data_object.get("id") or "").startswith("sub_")
    )
    if bill_order_bid or is_billing_subscription_event:
        from flaskr.service.billing.api import apply_payment_notification

        billing_result = apply_payment_notification(app, "stripe", notification)
        return billing_result.to_response_dict(), billing_result.status_code
    order_bid = notification.order_bid or metadata.get("order_bid", "")

    if expected_integration_bid and order_bid:
        scoped_order = Order.query.filter(
            Order.order_bid == order_bid,
            Order.deleted == 0,
        ).first()
        if (
            scoped_order is None
            or scoped_order.payment_integration_bid != expected_integration_bid
        ):
            return {"status": "error", "message": "integration mismatch"}, 400

    if not order_bid:
        app.logger.warning("Stripe webhook missing order metadata. type=%s", event_type)
        return {
            "status": "ignored",
            "reason": "missing order metadata",
            "event_type": event_type,
        }, 202

    with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_bid):
        order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        stripe_attempt_bid = str(metadata.get("stripe_order_bid") or "")
        stripe_query = legacy_stripe_snapshot_query().filter(
            StripeOrder.order_bid == order_bid
        )
        if stripe_attempt_bid:
            stripe_query = stripe_query.filter(
                StripeOrder.stripe_order_bid == stripe_attempt_bid
            )
        stripe_order: StripeOrder | None = (
            stripe_query.order_by(StripeOrder.id.desc()).with_for_update().first()
        )
        if not stripe_order:
            app.logger.warning("Stripe order not found for order_bid=%s", order_bid)
            return {
                "status": "ignored",
                "order_bid": order_bid,
                "reason": "stripe order not found",
                "event_type": event_type,
            }, 202

        response_status = "acknowledged"
        http_status = 202

        success_events = {
            "payment_intent.succeeded",
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }
        refund_events = {
            "charge.refunded",
            "refund.created",
            "refund.updated",
            "refund.failed",
            "charge.refund.updated",
        }
        cancel_events = {
            "payment_intent.canceled",
        }
        if event_type in success_events:
            session = (
                data_object if event_type.startswith("checkout.session.") else None
            )
            intent = data_object if event_type == "payment_intent.succeeded" else None
            if (
                order
                and _stripe_provider_objects_match_attempt(
                    order=order,
                    stripe_order=stripe_order,
                    notification_order_bid=str(order_bid),
                    session=session,
                    intent=intent,
                )
                and (
                    event_type == "payment_intent.succeeded"
                    or _is_stripe_payment_successful(session=session, intent=intent)
                )
                and _stripe_attempt_can_complete(order, stripe_order)
            ):
                _assert_payment_lifecycle_lock_owned()
                if notification.charge_id:
                    stripe_order.latest_charge_id = notification.charge_id
                if metadata:
                    stripe_order.metadata_json = _stringify_payload(metadata)
                if session:
                    payment_intent_id = str(session.get("payment_intent") or "")
                    if payment_intent_id:
                        stripe_order.payment_intent_id = payment_intent_id
                    stripe_order.checkout_session_object = _stringify_payload(session)
                if intent:
                    stripe_order.payment_intent_id = str(
                        intent.get("id") or stripe_order.payment_intent_id or ""
                    )
                    stripe_order.payment_intent_object = _stringify_payload(intent)
                    stripe_order.payment_method = intent.get(
                        "payment_method", stripe_order.payment_method
                    )
                    charges = intent.get("charges", {}).get("data", [])
                    if charges:
                        stripe_order.receipt_url = charges[0].get(
                            "receipt_url", stripe_order.receipt_url
                        )
                stripe_order.status = 1
                success_buy_record(app, order_bid)
                response_status = "paid"
                http_status = 200
            else:
                response_status = "ignored"
        elif event_type == "payment_intent.payment_failed" and (
            order
            and _stripe_attempt_matches_order(order, stripe_order)
            and _stripe_intent_event_matches_attempt(
                stripe_order, data_object, metadata
            )
            and stripe_order.status != 1
        ):
            if notification.charge_id:
                stripe_order.latest_charge_id = notification.charge_id
            payment_intent_id = data_object.get("id")
            if payment_intent_id and payment_intent_id.startswith("pi_"):
                stripe_order.payment_intent_id = payment_intent_id
            if metadata:
                stripe_order.metadata_json = _stringify_payload(metadata)
            stripe_order.payment_intent_object = _stringify_payload(data_object)
            stripe_order.status = 4
            error_info = data_object.get("last_payment_error", {}) or {}
            stripe_order.failure_code = error_info.get("code", "")
            stripe_order.failure_message = error_info.get("message", "")
            response_status = "failed"
            http_status = 200
        elif event_type == "checkout.session.async_payment_failed":
            if (
                order
                and stripe_order.status != 1
                and _stripe_attempt_matches_order(order, stripe_order)
                and _stripe_provider_objects_match_attempt(
                    order=order,
                    stripe_order=stripe_order,
                    notification_order_bid=str(order_bid),
                    session=data_object,
                    intent=None,
                )
            ):
                stripe_order.checkout_session_object = _stringify_payload(data_object)
                stripe_order.status = 4
                response_status = "failed"
                http_status = 200
        elif (
            event_type in refund_events
            and order
            and _stripe_attempt_matches_order(order, stripe_order)
            and _stripe_refund_event_matches_attempt(
                stripe_order, data_object, event_type
            )
        ):
            from .payment_providers.normalization import stripe_event

            refund_event = stripe_event(notification)
            refund_status = refund_event.refund_status or "unknown"
            from .learner_refunds import reconcile_learner_refund
            from .payment_snapshots import latest_attempt

            attempt = latest_attempt(
                "stripe",
                order.order_bid,
                for_update=True,
                attempt_bid=stripe_order.stripe_order_bid,
            )
            metadata = attempt.metadata if attempt is not None else {}
            saved_refund = saved_refund_controls_state(refund_event, metadata)
            if attempt is not None:
                reconcile_learner_refund(order, attempt, refund_event, event)
            # Retain the baseline projection for unrequested external reversals.
            # Saved operations always require their own admitted final outcome.
            if not saved_refund and refund_event.payment.state == "refunded":
                stripe_order.status = 2
                response_status = "refunded"
            elif refund_status == "succeeded" and stripe_order.status == 2:
                response_status = "refunded"
            http_status = 200
        elif (
            event_type in cancel_events
            and order
            and _stripe_attempt_matches_order(order, stripe_order)
            and _stripe_intent_event_matches_attempt(
                stripe_order, data_object, metadata
            )
            and stripe_order.status != 1
        ):
            stripe_order.status = 3
            response_status = "cancelled"
            http_status = 200
        _assert_payment_lifecycle_lock_owned()

    return {
        "status": response_status,
        "order_bid": order_bid,
        "event_type": event_type,
    }, http_status
