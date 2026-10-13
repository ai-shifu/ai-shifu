"""Normalize existing provider results without changing protocol acceptance."""

from __future__ import annotations

from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import Any

from flaskr.service.config import get_config

from .base import PaymentCreationResult, PaymentNotificationResult, PaymentRequest
from .contracts import PaymentAction, PaymentFacts, SubscriptionFacts


def _event_object(payload: dict[str, Any]) -> dict[str, Any]:
    """Read optional event envelopes without turning malformed data into evidence."""
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    return obj if isinstance(obj, dict) else {}


def trade_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Read native query and notification envelopes at the adapter boundary."""
    for name in ("trade", "resource"):
        value = payload.get(name)
        if isinstance(value, dict) and value:
            return value
    return payload


def native_facts(provider: str, payload: dict[str, Any]) -> PaymentFacts:
    """Preserve existing native status and amount semantics, including absence."""
    trade = trade_payload(payload)
    if provider == "alipay":
        raw_status = str(trade.get("trade_status") or "")
        value = trade.get("total_amount")
        total = None
        if value not in (None, ""):
            with suppress(InvalidOperation, ValueError, OverflowError):
                total = int((Decimal(str(value)) * 100).to_integral_value())
        state = {
            "TRADE_SUCCESS": "paid",
            "TRADE_FINISHED": "paid",
            "TRADE_CLOSED": "canceled",
            "WAIT_BUYER_PAY": "pending",
        }.get(raw_status.upper(), "unknown")
        return PaymentFacts(
            state=state,
            order_amount=total,
            currency="CNY",
            raw_status=raw_status,
            provider_reference=str(trade.get("out_trade_no") or "") or None,
            invalid_validation_amount=value not in (None, "") and total is None,
        )
    if provider == "wechatpay":
        raw_status = str(trade.get("trade_state") or "")
        amount = trade.get("amount")
        amount = amount if isinstance(amount, dict) else {}
        total = amount.get("total")
        payer = amount.get("payer_total")
        state = {
            "SUCCESS": "paid",
            "CLOSED": "canceled",
            "REVOKED": "canceled",
            "PAYERROR": "failed",
            "NOTPAY": "pending",
        }.get(raw_status.upper(), "unknown")
        return PaymentFacts(
            state=state,
            order_amount=_optional_int(total),
            payer_amount=_optional_int(payer),
            invalid_validation_amount=(
                payer not in (None, "") and _optional_int(payer) is None
            )
            if "payer_total" in amount
            else (total not in (None, "") and _optional_int(total) is None),
            currency=str(amount.get("currency") or "") or None,
            validation_amount_source="payer" if "payer_total" in amount else "order",
            raw_status=raw_status,
            provider_reference=str(trade.get("out_trade_no") or "") or None,
        )
    from . import _PROVIDER_REGISTRY

    provider_cls = _PROVIDER_REGISTRY.get(provider)
    return provider_cls.read_payment_facts(payload) if provider_cls else PaymentFacts()


def legacy_native_amount(facts: PaymentFacts) -> int | None:
    """Keep the existing payer-total fallback until the native protocol PRs."""
    if facts.invalid_validation_amount:
        message = "Invalid reported payment amount"
        raise ValueError(message)
    return (
        facts.payer_amount
        if facts.validation_amount_source == "payer"
        else facts.order_amount
    )


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def stripe_paid_amount(payload: dict[str, Any]) -> int | None:
    """Preserve the existing Checkout/PaymentIntent amount precedence."""
    session = payload.get("checkout_session", payload)
    intent = payload.get("payment_intent", {})
    session = session if isinstance(session, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    for value in (
        session.get("amount_total"),
        intent.get("amount_received"),
        intent.get("amount"),
    ):
        amount = _optional_int(value)
        if amount is not None:
            return amount
    return None


def stripe_paid_currency(payload: dict[str, Any]) -> str:
    """Preserve the existing currency fallback without inventing a currency."""
    session = payload.get("checkout_session", payload)
    intent = payload.get("payment_intent", {})
    session = session if isinstance(session, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    return str(session.get("currency") or intent.get("currency") or "").upper()


def notification_facts(
    provider: str, result: PaymentNotificationResult
) -> PaymentFacts:
    """Resolve normalized evidence for old snapshots and new adapter results."""
    if getattr(result, "facts", None) is not None:
        return result.facts
    payload = result.provider_payload or {}
    event_type = str(result.status or "")
    source = "query" if event_type == "manual_sync" else "notification"
    if provider not in {"stripe", "pingxx"}:
        facts = native_facts(provider, payload)
        return PaymentFacts(
            state=facts.state,
            order_amount=facts.order_amount,
            payer_amount=facts.payer_amount,
            provider_reference=facts.provider_reference,
            currency=facts.currency,
            raw_status=facts.raw_status,
            validation_amount_source=facts.validation_amount_source,
            invalid_validation_amount=facts.invalid_validation_amount,
            event_type=event_type,
            event_id=str(payload.get("id") or "") or None,
            event_time=_optional_int(payload.get("create_time")),
            source=source,
        )
    if provider == "pingxx":
        charge = payload.get("charge") or _event_object(payload) or {}
        state = "paid" if charge.get("paid") else "pending"
        if charge.get("refunded"):
            state = "refunded"
        elif not charge.get("paid") and charge.get("failure_code"):
            state = "failed"
        return PaymentFacts(
            state=state,
            order_amount=_optional_int(charge.get("amount")),
            currency=str(charge.get("currency") or "").upper() or None,
            event_type=event_type,
            event_id=str(payload.get("id") or "") or None,
            event_time=_optional_int(payload.get("created")),
            source=source,
        )
    if provider == "stripe":
        obj = _event_object(payload) or {}
        session = payload.get("checkout_session") or (
            obj if str(obj.get("id") or "").startswith("cs_") else {}
        )
        intent = payload.get("payment_intent") or (
            obj if str(obj.get("id") or "").startswith("pi_") else {}
        )
        evidence = {"checkout_session": session, "payment_intent": intent}
        state = "unknown"
        if session:
            state = "paid" if session.get("payment_status") == "paid" else "pending"
            if session.get("status") == "expired":
                state = "canceled"
        elif intent:
            state = {
                "succeeded": "paid",
                "canceled": "canceled",
                "requires_payment_method": "failed",
            }.get(str(intent.get("status") or ""), "pending")
        # Subscription status events are not payment evidence.
        return PaymentFacts(
            state=state,
            order_amount=stripe_paid_amount(evidence),
            currency=stripe_paid_currency(evidence) or None,
            raw_status=str(session.get("status") or intent.get("status") or ""),
            event_type=event_type,
            event_id=str(payload.get("id") or "") or None,
            event_time=_optional_int(payload.get("created")),
            source=source,
        )
    return PaymentFacts(event_type=event_type, source=source)


def normalized_notification(
    provider: str,
    *,
    order_bid: str,
    status: str,
    provider_payload: dict[str, Any],
    charge_id: str | None = None,
) -> PaymentNotificationResult:
    """Build a provider result with payment evidence separate from raw snapshots."""
    result = PaymentNotificationResult(order_bid, status, provider_payload, charge_id)
    result.facts = notification_facts(provider, result)
    if provider == "stripe":
        obj = (
            provider_payload.get("subscription")
            or _event_object(provider_payload)
            or {}
        )
        if str(obj.get("id") or "").startswith("sub_"):
            result.subscription = SubscriptionFacts(
                provider_reference=str(obj["id"]),
                status=str(obj.get("status") or ""),
                customer_reference=str(obj.get("customer") or ""),
                period_start=_optional_int(obj.get("current_period_start")),
                period_end=_optional_int(obj.get("current_period_end")),
                billing_anchor=_optional_int(obj.get("billing_cycle_anchor")),
                cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
            )
    return result


def creation_action(
    provider: str, channel: str, result: PaymentCreationResult
) -> PaymentAction:
    """Interpret legacy creation payloads once, at the payment boundary."""
    if getattr(result, "action", None) is not None:
        return result.action
    extra = result.extra or {}
    raw = result.raw_response or {}
    channel = channel.split(":", 1)[-1]
    if provider == "stripe":
        url = str(extra.get("url") or raw.get("url") or "")
        if url:
            return PaymentAction(
                "redirect", url=url, session_id=result.checkout_session_id
            )
        if result.client_secret:
            return PaymentAction(
                "sdk_confirm",
                sdk="stripe",
                client_secret=result.client_secret,
                publishable_key=str(get_config("STRIPE_PUBLISHABLE_KEY", "") or "")
                or None,
            )
        return PaymentAction("none")
    params = extra.get("jsapi_params")
    if isinstance(params, dict) and params:
        return PaymentAction("jsapi", parameters=dict(params))
    credential = extra.get("credential") or raw.get("credential") or {}
    value = credential.get(channel) if isinstance(credential, dict) else None
    if channel == "wx_pub" and isinstance(value, dict):
        return PaymentAction("jsapi", parameters=dict(value))
    url = extra.get("qr_url") or value or ""
    if isinstance(url, str) and url:
        return PaymentAction("redirect" if channel == "wx_wap" else "qr", url=url)
    return PaymentAction("none")


def normalized_creation(
    provider: str,
    request: PaymentRequest,
    *,
    provider_reference: str,
    raw_response: dict[str, Any],
    client_secret: str | None = None,
    checkout_session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> PaymentCreationResult:
    """Expose an explicit action alongside the legacy compatibility fields."""
    result = PaymentCreationResult(
        provider_reference,
        raw_response,
        client_secret,
        checkout_session_id,
        extra or {},
    )
    result.action = creation_action(provider, request.channel, result)
    return result
