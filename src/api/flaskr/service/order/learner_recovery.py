"""Read historical learner snapshot payloads without making purchase decisions."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any

from flaskr.util.datetime import now_utc

from .learner_payments import PaymentPresentation, _format_response_channel
from .models import PingxxOrder, StripeOrder
from .payment_providers.base import PaymentCreationResult
from .payment_providers.contracts import stored_payment_action
from .payment_providers.normalization import creation_action
from .raw_snapshots import (
    _parse_json_payload,
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_model,
    registered_native_payment_providers,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

    from .models import Order


def _parse_stored_mapping(value: object) -> dict[str, Any]:
    parsed = _parse_json_payload(value)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        try:
            legacy_parsed = ast.literal_eval(parsed)
        except (SyntaxError, ValueError):
            return {}
        return legacy_parsed if isinstance(legacy_parsed, dict) else {}
    return {}


def _payment_payload_has_expired(payload: dict[str, Any], field: str) -> bool:
    raw_expiry = payload.get(field)
    if raw_expiry in (None, ""):
        return False
    try:
        return float(raw_expiry) <= now_utc().timestamp()
    except (TypeError, ValueError):
        return True


def _resume_pending_charge(
    app: Flask,
    buy_record: Order,
    *,
    payment_channel: str | None = None,
    provider_channel: str | None = None,
    expected_amount: int,
) -> PaymentPresentation | None:
    """Return only a live attempt matching the requested payment contract."""
    from .funs import _order_credential_scope, get_payment_provider

    payment_channel = (
        str(payment_channel or buy_record.payment_channel or "").strip().lower()
    )
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
            return PaymentPresentation(
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
            with _order_credential_scope(app, buy_record):
                return PaymentPresentation(
                    buy_record.order_bid,
                    buy_record.user_bid,
                    buy_record.paid_price,
                    _format_response_channel("stripe", mode),
                    checkout_url or client_secret,
                    payment_channel="stripe",
                    payment_action=creation_action(
                        "stripe",
                        mode,
                        PaymentCreationResult(
                            "",
                            {},
                            client_secret=client_secret,
                            checkout_session_id=snapshot.checkout_session_id,
                            extra={"url": checkout_url},
                        ),
                    ),
                    payment_payload={
                        "mode": mode,
                        "client_secret": client_secret,
                        "checkout_session_url": checkout_url,
                        "checkout_session_id": snapshot.checkout_session_id,
                        "payment_intent_id": snapshot.payment_intent_id,
                        "latest_charge_id": snapshot.latest_charge_id,
                    },
                )
    elif payment_channel in registered_native_payment_providers():
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
            raw_action = metadata.get("payment_action")
            stored_action = stored_payment_action(raw_action)
            if (
                isinstance(raw_action, dict)
                and isinstance(raw_action.get("type"), str)
                and raw_action["type"]
                not in {"qr", "redirect", "jsapi", "sdk_confirm", "none"}
            ):
                # An explicit unsupported action cannot become a legacy QR.
                return None
            qr_url = str(
                (stored_action.url if stored_action else None)
                or response.get("qr_code")
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
                    provider = get_payment_provider(payment_channel)
                    jsapi_params = provider.build_jsapi_params(prepay_id=prepay_id)
                payment_payload.update(
                    {
                        "mode": "jsapi",
                        "prepay_id": prepay_id,
                        "jsapi_params": jsapi_params,
                    }
                )
            elif stored_action and stored_action.type == "jsapi":
                payment_payload.update(
                    mode="jsapi", jsapi_params=stored_action.parameters
                )
            elif stored_action and stored_action.type == "sdk_confirm":
                payment_payload.update(
                    client_secret=stored_action.client_secret,
                )
            elif not qr_url:
                return None
            return PaymentPresentation(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                snapshot.channel,
                qr_url,
                payment_channel=payment_channel,
                payment_payload=payment_payload,
                payment_action=stored_action
                if stored_action and snapshot.channel != "wx_pub"
                else None,
            )
    app.logger.warning(
        "pending payment snapshot cannot be resumed for order:%s; creating a replacement attempt",
        buy_record.order_bid,
    )
    return None


def _legacy_stripe_sync(
    app: Flask, order_id: str, *, expected_user: str | None = None
) -> dict[str, object]:
    from .funs import sync_stripe_checkout_session

    return sync_stripe_checkout_session(app, order_id, expected_user=expected_user)


_LEGACY_SYNC_HANDLERS = {"stripe": _legacy_stripe_sync}


def legacy_sync_handler(provider: str) -> Callable[..., dict[str, object]] | None:
    """Keep historical transport dispatch out of purchase rules."""
    from .payment_providers import historical_payment_definition

    return _LEGACY_SYNC_HANDLERS.get(
        historical_payment_definition(provider).snapshot_kind
    )
