"""Resume pending provider charges and close them before an order is repriced."""

import decimal
from typing import Any

from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.order.charge_providers import (
    _order_credential_scope,
)
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.funs_lookup import order_funs
from flaskr.service.order.legacy_order_dtos import (
    BuyRecordDTO,
)
from flaskr.service.order.models import (
    Order,
    PingxxOrder,
    StripeOrder,
)
from flaskr.service.order.payment_lifecycle import (
    _assert_payment_lifecycle_lock_owned,
)
from flaskr.service.order.payment_payloads import (
    _format_response_channel,
    _parse_stored_mapping,
    _payment_payload_has_expired,
)
from flaskr.service.order.raw_snapshots import (
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_model,
)
from flaskr.util.datetime import now_utc

# Shared session-scope guard; see flaskr/dao/uow.py for the rationale.
_app_context_scope = app_context_scope


def _resume_pending_charge(
    app: Flask,
    buy_record: Order,
    *,
    payment_channel: str | None = None,
    provider_channel: str | None = None,
) -> BuyRecordDTO | None:
    """Return only a live attempt matching the requested payment contract."""
    payment_channel = (
        str(payment_channel or buy_record.payment_channel or "").strip().lower()
    )
    expected_amount = int(decimal.Decimal(buy_record.paid_price or 0) * 100)
    if payment_channel == "pingxx":
        snapshot = (
            legacy_pingxx_snapshot_query()
            .filter(
                PingxxOrder.order_bid == buy_record.order_bid,
                PingxxOrder.status == 0,
                PingxxOrder.amount == expected_amount,
            )
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        if snapshot and (not provider_channel or snapshot.channel == provider_channel):
            charge = _parse_stored_mapping(snapshot.charge_object)
            if _payment_payload_has_expired(charge, "time_expire"):
                return None
            credential = charge.get("credential") or {}
            qr_url = credential.get(snapshot.channel) or ""
            if not isinstance(qr_url, (str, dict)) or not qr_url:
                return None
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                snapshot.channel,
                qr_url,
                payment_channel="pingxx",
                payment_payload={"qr_url": qr_url, "credential": credential},
            )
    elif payment_channel == "stripe":
        snapshot = (
            legacy_stripe_snapshot_query()
            .filter(
                StripeOrder.order_bid == buy_record.order_bid,
                StripeOrder.status.in_([0, 4]),
                StripeOrder.amount == expected_amount,
            )
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if snapshot:
            intent = _parse_stored_mapping(snapshot.payment_intent_object)
            checkout = _parse_stored_mapping(snapshot.checkout_session_object)
            mode = (
                "checkout_session" if snapshot.checkout_session_id else "payment_intent"
            )
            if provider_channel and mode != provider_channel:
                return None
            checkout_url = str(checkout.get("url") or "")
            client_secret = str(intent.get("client_secret") or "")
            if checkout_url and _payment_payload_has_expired(checkout, "expires_at"):
                return None
            if not checkout_url and not client_secret:
                return None
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                _format_response_channel("stripe", mode),
                checkout_url or client_secret,
                payment_channel="stripe",
                payment_payload={
                    "mode": mode,
                    "client_secret": client_secret,
                    "checkout_session_url": checkout_url,
                    "checkout_session_id": snapshot.checkout_session_id,
                    "payment_intent_id": snapshot.payment_intent_id,
                    "latest_charge_id": snapshot.latest_charge_id,
                },
            )
    elif payment_channel in {"alipay", "wechatpay"}:
        model = native_snapshot_model(payment_channel)
        snapshot = (
            legacy_native_snapshot_query(payment_channel)
            .filter(
                model.order_bid == buy_record.order_bid,
                model.status == 0,
                model.amount == expected_amount,
            )
            .order_by(model.id.desc())
            .first()
        )
        if snapshot and (not provider_channel or snapshot.channel == provider_channel):
            response = _parse_stored_mapping(snapshot.raw_response)
            metadata = _parse_stored_mapping(snapshot.metadata_json)
            qr_url = str(
                response.get("qr_code")
                or response.get("code_url")
                or metadata.get("qr_url")
                or ""
            )
            payment_payload: dict[str, Any] = {
                "qr_url": qr_url,
                "credential": {snapshot.channel: qr_url} if qr_url else {},
            }
            if snapshot.channel == "wx_pub":
                prepay_id = str(
                    metadata.get("prepay_id") or response.get("prepay_id") or ""
                )
                if not prepay_id:
                    return None
                with _order_credential_scope(app, buy_record):
                    provider = order_funs.get_payment_provider("wechatpay")
                    jsapi_params = provider.build_jsapi_params(prepay_id=prepay_id)
                payment_payload.update(
                    {
                        "mode": "jsapi",
                        "prepay_id": prepay_id,
                        "jsapi_params": jsapi_params,
                    }
                )
            elif not qr_url:
                return None
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                snapshot.channel,
                qr_url,
                payment_channel=payment_channel,
                payment_payload=payment_payload,
            )
    app.logger.warning(
        "pending payment snapshot cannot be resumed for order:%s; creating a replacement attempt",
        buy_record.order_bid,
    )
    return None


def cancel_pending_payment_for_repricing(
    app: Flask,
    order_bid: str,
    *,
    expected_user: str,
    keep_repricing_claim: bool = False,
) -> bool:
    """Close the current provider attempt before a coupon changes its amount."""
    with _app_context_scope(app), order_funs.unit_of_work():
        order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.user_bid == expected_user,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if not order:
            raise_error("server.order.orderNotFound")
        if order.status == ORDER_STATUS_INIT:
            return False
        if order.status not in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}:
            raise_error("server.order.orderStatusError")
        order.status = ORDER_STATUS_REPRICING
        order.updated_at = now_utc()
        db.session.add(order)
        payment_channel = str(order.payment_channel or "pingxx").strip().lower()
        snapshots: list[PingxxOrder | StripeOrder | Any]
        if payment_channel == "pingxx":
            snapshots = (
                legacy_pingxx_snapshot_query()
                .filter(PingxxOrder.order_bid == order_bid, PingxxOrder.status == 0)
                .order_by(PingxxOrder.id.desc())
                .all()
            )
        elif payment_channel == "stripe":
            snapshots = (
                legacy_stripe_snapshot_query()
                .filter(
                    StripeOrder.order_bid == order_bid,
                    StripeOrder.status.in_([0, 4]),
                )
                .order_by(StripeOrder.id.desc())
                .all()
            )
        elif payment_channel in {"alipay", "wechatpay"}:
            model = native_snapshot_model(payment_channel)
            snapshots = (
                legacy_native_snapshot_query(payment_channel)
                .filter(model.order_bid == order_bid, model.status == 0)
                .order_by(model.id.desc())
                .all()
            )
        else:
            raise_error("server.pay.payChannelNotSupport")

        if not snapshots:
            if not keep_repricing_claim:
                order.status = ORDER_STATUS_INIT
            return False
        snapshot_ids = [snapshot.id for snapshot in snapshots]
        snapshot_model = snapshots[0].__class__
        attempts: list[tuple[str, str]] = []
        for snapshot in snapshots:
            if payment_channel == "pingxx":
                attempts.append((str(snapshot.charge_id or ""), "charge"))
            elif payment_channel == "stripe" and snapshot.checkout_session_id:
                attempts.append((str(snapshot.checkout_session_id), "checkout_session"))
            elif payment_channel == "stripe":
                attempts.append(
                    (str(snapshot.payment_intent_id or ""), "payment_intent")
                )
            else:
                attempts.append((str(snapshot.provider_attempt_id or ""), "trade"))
        credential_order = Order(
            creator_bid=str(order.creator_bid or ""),
            payment_channel=str(order.payment_channel or ""),
            payment_integration_bid=str(order.payment_integration_bid or ""),
        )

    try:
        with _app_context_scope(app), _order_credential_scope(app, credential_order):
            provider = order_funs.get_payment_provider(payment_channel)
            for provider_reference, reference_type in attempts:
                _assert_payment_lifecycle_lock_owned()
                if not provider_reference:
                    raise_error("server.order.orderStatusError")
                cancellation = provider.cancel_payment(
                    provider_reference=provider_reference,
                    reference_type=reference_type,
                    app=app,
                )
                if cancellation.status != "cancelled":
                    raise_error("server.order.orderStatusError")
    except Exception:
        app.logger.exception(
            "Failed to close payment attempts before repricing order=%s provider=%s",
            order_bid,
            payment_channel,
        )
        restore_repricing_order(app, order_bid, expected_user=expected_user)
        raise_error("server.order.orderStatusError")

    with _app_context_scope(app):
        with order_funs.unit_of_work():
            locked_order = (
                Order.query.filter(
                    Order.order_bid == order_bid,
                    Order.user_bid == expected_user,
                    Order.deleted == 0,
                )
                .with_for_update()
                .first()
            )
            if not locked_order or locked_order.status != ORDER_STATUS_REPRICING:
                raise_error("server.order.orderStatusError")
            active_statuses = [0, 4] if snapshot_model is StripeOrder else [0]
            locked_snapshots = snapshot_model.query.filter(
                snapshot_model.id.in_(snapshot_ids),
                snapshot_model.status.in_(active_statuses),
            ).all()
            if len(locked_snapshots) != len(snapshot_ids):
                raise_error("server.order.orderStatusError")
            for locked_snapshot in locked_snapshots:
                locked_snapshot.status = 3
                locked_snapshot.updated_at = now_utc()
                db.session.add(locked_snapshot)
            if not keep_repricing_claim:
                locked_order.status = ORDER_STATUS_INIT
                locked_order.updated_at = now_utc()
                db.session.add(locked_order)
        return True


def restore_repricing_order(
    app: Flask,
    order_bid: str,
    *,
    expected_user: str,
    target_status: int = ORDER_STATUS_TO_BE_PAID,
) -> None:
    """Return an interrupted repricing claim to its payable state."""
    with _app_context_scope(app), order_funs.unit_of_work():
        order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.user_bid == expected_user,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if order and order.status == ORDER_STATUS_REPRICING:
            order.status = target_status
            order.updated_at = now_utc()
            db.session.add(order)
