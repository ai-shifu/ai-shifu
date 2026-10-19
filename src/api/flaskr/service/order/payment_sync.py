"""Synchronize native payment status, Stripe webhooks and refunds for legacy orders."""

import json
from contextlib import nullcontext
from typing import Any

from flask import Flask
from flaskr.dao import db, uow
from flaskr.dao.uow import app_context_scope
from flaskr.service.billing.api import (
    build_provider_config_overrides,
    resolve_provider_credential_context,
)
from flaskr.service.common.models import raise_error
from flaskr.service.config import (
    config_overrides,
)
from flaskr.service.order.consts import (
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.funs_lookup import order_funs
from flaskr.service.order.models import (
    Order,
    PingxxOrder,
    StripeOrder,
)
from flaskr.service.order.payment_attempts import (
    _apply_native_snapshot_update,
    _extract_native_notification_amount,
    _is_native_payment_successful,
    _is_stripe_payment_successful,
    _load_payment_sync_order,
    _stripe_attempt_can_complete,
    _stripe_attempt_matches_order,
    _stripe_intent_event_matches_attempt,
    _stripe_provider_objects_match_attempt,
    _stripe_refund_event_matches_attempt,
)
from flaskr.service.order.payment_lifecycle import (
    _assert_payment_lifecycle_lock_owned,
)
from flaskr.service.order.payment_payloads import (
    _stringify_payload,
)
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
)
from flaskr.service.order.raw_snapshots import (
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_model,
)

# Shared session-scope guard; see flaskr/dao/uow.py for the rationale.
_app_context_scope = app_context_scope


def sync_native_payment_order(
    app: Flask,
    order_id: str,
    *,
    expected_user: str | None = None,
    payment_channel: str | None = None,
) -> dict[str, Any]:
    """Synchronize native payment order."""
    uow.require_transaction_owner("payment synchronization", app)
    with _app_context_scope(app), order_funs.unit_of_work(discard=True):
        order = _load_payment_sync_order(order_id, expected_user=expected_user)
        provider_name = str(payment_channel or order.payment_channel or "").lower()
        provider_attempt_id = ""
        credential_context = None
        if provider_name in {"alipay", "wechatpay"}:
            native_model = native_snapshot_model(provider_name)
            snapshot = (
                legacy_native_snapshot_query(provider_name)
                .filter(native_model.order_bid == order.order_bid)
                .order_by(native_model.id.desc())
                .first()
            )
            if snapshot is None or not snapshot.provider_attempt_id:
                raise_error("server.order.orderNotFound")
            provider_attempt_id = str(snapshot.provider_attempt_id)
            integration_bid = str(order.payment_integration_bid or "")
            if integration_bid:
                credential_context = resolve_provider_credential_context(
                    app,
                    creator_bid=str(order.creator_bid or ""),
                    provider=provider_name,
                    integration_bid=integration_bid,
                )
                if (
                    credential_context is None
                    or credential_context.integration_bid != integration_bid
                ):
                    raise_error("server.pay.payChannelNotSupport")

    if provider_name == "stripe":
        return order_funs.sync_stripe_checkout_session(
            app,
            order_id,
            expected_user=expected_user,
        )
    if provider_name not in {"alipay", "wechatpay"}:
        raise_error("server.pay.payChannelNotSupport")

    provider = order_funs.get_payment_provider(provider_name)
    credential_scope = (
        config_overrides(build_provider_config_overrides(credential_context))
        if credential_context is not None
        else nullcontext()
    )
    with _app_context_scope(app), credential_scope:
        sync_result = provider.sync_reference(
            provider_reference=provider_attempt_id,
            reference_type="payment",
            app=app,
        )

    with (
        _app_context_scope(app),
        order_funs.payment_lifecycle_lock(order_id) as lifecycle_lease,
        order_funs.unit_of_work(),
    ):
        order = _load_payment_sync_order(
            order_id,
            expected_user=expected_user,
            for_update=True,
        )
        current_provider = str(payment_channel or order.payment_channel or "").lower()
        if current_provider != provider_name:
            raise_error("server.pay.payChannelNotSupport")

        native_model = native_snapshot_model(provider_name)
        snapshot = (
            legacy_native_snapshot_query(provider_name)
            .filter(
                native_model.order_bid == order.order_bid,
            )
            .order_by(native_model.id.desc())
            .first()
        )
        if (
            snapshot is None
            or str(snapshot.provider_attempt_id or "") != provider_attempt_id
        ):
            raise_error("server.order.orderNotFound")

        _apply_native_snapshot_update(
            snapshot=snapshot,
            provider=provider_name,
            notification=sync_result,
            source="sync",
        )
        actual_amount = _extract_native_notification_amount(
            provider_name,
            sync_result.provider_payload or {},
        )
        amount_matches = True
        if actual_amount is not None and int(snapshot.amount or 0) != actual_amount:
            amount_matches = False
            app.logger.warning(
                "native payment sync amount mismatch provider=%s order_bid=%s provider_attempt_id=%s expected=%s actual=%s",
                provider_name,
                order.order_bid,
                snapshot.provider_attempt_id,
                snapshot.amount,
                actual_amount,
            )
        if (
            _is_native_payment_successful(provider_name, sync_result.provider_payload)
            and amount_matches
            and order.status != ORDER_STATUS_SUCCESS
        ):
            order_funs.success_buy_record(app, order.order_bid)
        db.session.add(snapshot)
        _assert_payment_lifecycle_lock_owned()
        lifecycle_lease.release_checked()
        return order_funs.get_payment_details(app, order.order_bid)


def handle_stripe_webhook(
    app: Flask,
    raw_body: bytes,
    sig_header: str,
    *,
    expected_integration_bid: str = "",
) -> tuple[dict[str, object], int]:
    """Handle stripe webhook."""
    provider = order_funs.get_payment_provider("stripe")
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
    from flaskr.service.billing.webhooks import (
        apply_billing_stripe_catalog_notification,
        is_billing_stripe_catalog_event,
    )

    if is_billing_stripe_catalog_event(event_type):
        return apply_billing_stripe_catalog_notification(app, notification)

    metadata = data_object.get("metadata", {}) or {}
    bill_order_bid = metadata.get("bill_order_bid", "")
    is_billing_subscription_event = bool(
        data_object.get("subscription")
        or str(data_object.get("id") or "").startswith("sub_")
    )
    if bill_order_bid or is_billing_subscription_event:
        from flaskr.service.billing.webhooks import apply_billing_stripe_notification

        billing_result = apply_billing_stripe_notification(app, notification)
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

    with (
        _app_context_scope(app),
        order_funs.unit_of_work(),
        order_funs.payment_lifecycle_lock(order_bid),
    ):
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

        response_status, http_status = _apply_stripe_order_event(
            app,
            order_bid=order_bid,
            event_type=event_type,
            data_object=data_object,
            metadata=metadata,
            notification=notification,
            order=order,
            stripe_order=stripe_order,
        )
        _assert_payment_lifecycle_lock_owned()

    return {
        "status": response_status,
        "order_bid": order_bid,
        "event_type": event_type,
    }, http_status


def _apply_stripe_order_event(
    app: Flask,
    *,
    order_bid: str,
    event_type: str,
    data_object: dict,
    metadata: dict,
    notification: PaymentNotificationResult,
    order: Order | None,
    stripe_order: StripeOrder,
) -> tuple[str, int]:
    """Apply one Stripe order event to the locked attempt and report the outcome."""
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
    }
    cancel_events = {
        "payment_intent.canceled",
    }
    if event_type in success_events:
        session = data_object if event_type.startswith("checkout.session.") else None
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
            order_funs.success_buy_record(app, order_bid)
            response_status = "paid"
            http_status = 200
        else:
            response_status = "ignored"
    elif event_type == "payment_intent.payment_failed" and (
        order
        and _stripe_attempt_matches_order(order, stripe_order)
        and _stripe_intent_event_matches_attempt(stripe_order, data_object, metadata)
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
        and _stripe_refund_event_matches_attempt(stripe_order, data_object, event_type)
    ):
        stripe_order.status = 2
        response_status = "refunded"
        http_status = 200
    elif (
        event_type in cancel_events
        and order
        and _stripe_attempt_matches_order(order, stripe_order)
        and _stripe_intent_event_matches_attempt(stripe_order, data_object, metadata)
        and stripe_order.status != 1
    ):
        stripe_order.status = 3
        response_status = "cancelled"
        http_status = 200
    return response_status, http_status


def refund_order_payment(
    app: Flask,
    order_bid: str,
    amount: int | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Refund order payment."""
    uow.require_transaction_owner("Stripe refund", app)
    with (
        _app_context_scope(app),
        order_funs.unit_of_work(),
        order_funs.payment_lifecycle_lock(order_bid),
    ):
        order = (
            Order.query.filter(Order.order_bid == order_bid).with_for_update().first()
        )
        if not order:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        provider = order_funs.get_payment_provider(payment_channel)

        if payment_channel != "stripe":
            app.logger.error("Refund not implemented for channel: %s", payment_channel)
            raise_error("server.pay.payChannelNotSupport")

        stripe_order = (
            legacy_stripe_snapshot_query()
            .filter(StripeOrder.order_bid == order_bid)
            .order_by(StripeOrder.id.desc())
            .with_for_update()
            .first()
        )
        if not stripe_order:
            raise_error("server.order.orderNotFound")

        refund_amount = amount if amount is not None else stripe_order.amount
        refund_key = (
            f"order-refund:{order_bid}:{stripe_order.stripe_order_bid}:{refund_amount}"
        )
        metadata_dict = {}
        if stripe_order.metadata_json:
            try:
                metadata_dict = json.loads(stripe_order.metadata_json)
            except json.JSONDecodeError:
                metadata_dict = {}
        existing_operation = metadata_dict.get("refund_operation") or {}
        if (
            existing_operation.get("idempotency_key") == refund_key
            and existing_operation.get("status") == "succeeded"
        ):
            return {
                "status": "succeeded",
                "order_bid": order_bid,
                "refund_id": existing_operation.get("provider_reference", ""),
                "amount": refund_amount,
            }
        metadata_dict["refund_operation"] = {
            "idempotency_key": refund_key,
            "status": "pending",
            "amount": refund_amount,
        }
        stripe_order.metadata_json = json.dumps(metadata_dict)
        stripe_attempt_bid = str(stripe_order.stripe_order_bid or "")
        request_metadata = {
            "order_bid": order_bid,
            "payment_intent_id": stripe_order.payment_intent_id,
            "charge_id": stripe_order.latest_charge_id,
            "idempotency_key": refund_key,
        }
        refund_request = PaymentRefundRequest(
            order_bid=order_bid,
            amount=refund_amount,
            reason=reason,
            metadata=request_metadata,
        )
        credential_context = None
        integration_bid = str(order.payment_integration_bid or "")
        if integration_bid:
            credential_context = resolve_provider_credential_context(
                app,
                creator_bid=str(order.creator_bid or ""),
                provider="stripe",
                integration_bid=integration_bid,
            )
            if (
                credential_context is None
                or credential_context.integration_bid != integration_bid
            ):
                raise_error("server.pay.payChannelNotSupport")
        _assert_payment_lifecycle_lock_owned()

    credential_scope = (
        config_overrides(build_provider_config_overrides(credential_context))
        if credential_context is not None
        else nullcontext()
    )
    with _app_context_scope(app), credential_scope:
        result = provider.refund_payment(request=refund_request, app=app)

    _record_stripe_refund_result(
        app,
        order_bid=order_bid,
        stripe_attempt_bid=stripe_attempt_bid,
        refund_key=refund_key,
        result=result,
    )

    return {
        "status": result.status,
        "order_bid": order_bid,
        "refund_id": result.provider_reference,
        "amount": refund_amount,
    }


def _record_stripe_refund_result(
    app: Flask,
    *,
    order_bid: str,
    stripe_attempt_bid: str,
    refund_key: str,
    result: PaymentRefundResult,
) -> None:
    """Persist a provider refund result on the order and its Stripe attempt."""
    with (
        _app_context_scope(app),
        order_funs.unit_of_work(),
        order_funs.payment_lifecycle_lock(order_bid),
    ):
        order = (
            Order.query.filter(Order.order_bid == order_bid).with_for_update().first()
        )
        stripe_order = (
            legacy_stripe_snapshot_query()
            .filter(
                StripeOrder.order_bid == order_bid,
                StripeOrder.stripe_order_bid == stripe_attempt_bid,
            )
            .with_for_update()
            .first()
        )
        if not order or not stripe_order:
            raise_error("server.order.orderNotFound")
        metadata_dict = json.loads(stripe_order.metadata_json or "{}")
        operation = metadata_dict.get("refund_operation") or {}
        if operation.get("idempotency_key") != refund_key:
            raise_error("server.order.orderStatusError")
        operation.update(
            {
                "status": result.status,
                "provider_reference": result.provider_reference,
            }
        )
        metadata_dict["refund_operation"] = operation
        metadata_dict["last_refund_id"] = result.provider_reference
        stripe_order.metadata_json = json.dumps(metadata_dict)
        stripe_order.payment_intent_object = _stringify_payload(result.raw_response)

        refund_status = (result.status or "").lower()
        if refund_status == "succeeded":
            stripe_order.status = 2
            order.status = ORDER_STATUS_REFUND
        elif refund_status in {"pending", "requires_action"}:
            stripe_order.status = stripe_order.status or 1
        else:
            stripe_order.status = 4
            stripe_order.failure_code = refund_status or stripe_order.failure_code
        _assert_payment_lifecycle_lock_owned()


def get_payment_details(
    app: Flask, order_bid: str, expected_user: str | None = None
) -> dict[str, object]:
    # Read-only: reuses the caller's session so reads inside an open unit of
    # work see that transaction's pending state.
    """Return payment details."""
    with _app_context_scope(app):
        order = Order.query.filter(
            Order.order_bid == order_bid,
            Order.deleted == 0,
        ).first()
        if not order:
            raise_error("server.order.orderNotFound")
        if expected_user and order.user_bid != expected_user:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        if payment_channel == "stripe":
            stripe_order = (
                legacy_stripe_snapshot_query()
                .filter(StripeOrder.order_bid == order_bid)
                .order_by(StripeOrder.id.desc())
                .first()
            )
            if not stripe_order:
                raise_error("server.order.orderNotFound")
            return {
                "payment_channel": "stripe",
                "course_id": order.shifu_bid,
                "order_bid": order_bid,
                "status": stripe_order.status,
            }

        if payment_channel in {"alipay", "wechatpay"}:
            native_model = native_snapshot_model(payment_channel)
            native_order = (
                legacy_native_snapshot_query(payment_channel)
                .filter(
                    native_model.order_bid == order.order_bid,
                )
                .order_by(native_model.id.desc())
                .first()
            )
            if not native_order:
                raise_error("server.order.orderNotFound")
            return {
                "payment_channel": payment_channel,
                "course_id": order.shifu_bid,
                "order_bid": order_bid,
                "status": native_order.status,
            }

        pingxx_order = (
            legacy_pingxx_snapshot_query()
            .filter(PingxxOrder.order_bid == order.order_bid)
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        if not pingxx_order:
            raise_error("server.order.orderNotFound")
        return {
            "payment_channel": "pingxx",
            "course_id": order.shifu_bid,
            "order_bid": order_bid,
            "status": pingxx_order.status,
        }
