"""Normalize existing provider results without changing protocol acceptance."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from flaskr.service.config import get_config

from .base import PaymentCreationResult, PaymentNotificationResult, PaymentRequest
from .contracts import (
    PaymentAction,
    PaymentEvent,
    PaymentFacts,
    PaymentQueryTerms,
    SubscriptionFacts,
)


def _event_object(payload: dict[str, Any]) -> dict[str, Any]:
    """Read optional event envelopes without turning malformed data into evidence."""
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    return obj if isinstance(obj, dict) else {}


def subscription_facts(
    payload: dict[str, Any], *, deleted: bool = False
) -> SubscriptionFacts:
    """Translate legacy contract fields before applying channel-independent policy."""
    raw_status = str(payload.get("status") or "").strip().lower()
    status = {
        "active": "active",
        "trialing": "trialing",
        "past_due": "past_due",
        "paused": "paused",
        "canceled": "canceled",
        "unpaid": "past_due",
        "incomplete_expired": "expired",
    }.get(raw_status, "unknown")
    if deleted:
        status = "canceled"
    reference = str(payload.get("id") or "")
    return SubscriptionFacts(
        provider_reference=reference if reference.startswith("sub_") else "",
        status=status,
        customer_reference=str(payload.get("customer") or ""),
        period_start=payload.get("current_period_start"),
        period_end=payload.get("current_period_end"),
        billing_anchor=payload.get("billing_cycle_anchor"),
        cancel_at_period_end=bool(payload.get("cancel_at_period_end")),
    )


def stripe_event(notification: PaymentNotificationResult) -> PaymentEvent:
    """Interpret Stripe protocol once while preserving existing settlement rules."""
    payload = notification.provider_payload or {}
    obj = _event_object(payload)
    event_type = str(notification.status or payload.get("type") or "")
    reference = str(obj.get("id") or "")
    metadata = obj.get("metadata") or {}
    facts = notification_facts("stripe", notification)
    state = "unknown"
    kind = "payment"
    contract = None
    if event_type.startswith("customer.subscription."):
        kind = "contract"
        contract = subscription_facts(
            obj, deleted=event_type == "customer.subscription.deleted"
        )
    elif event_type == "checkout.session.completed":
        if obj.get("payment_status") in {"paid", "no_payment_required"}:
            state = "paid"
    elif event_type in {
        "payment_intent.succeeded",
        "checkout.session.async_payment_succeeded",
    }:
        state = "paid"
    elif event_type in {
        "payment_intent.payment_failed",
        "checkout.session.async_payment_failed",
    }:
        state = "failed"
    elif event_type == "charge.refunded":
        kind, state = "refund", "refunded"
    elif event_type in {
        "refund.created",
        "refund.updated",
        "refund.failed",
        "charge.refund.updated",
    }:
        kind = "refund"
        # Preserve the original refund.created payment projection for reversals
        # without a saved operation. Managed refunds use refund_status instead.
        if (
            event_type == "refund.created"
            or str(obj.get("status") or "").lower() == "succeeded"
        ):
            state = "refunded"
    elif event_type == "payment_intent.canceled":
        state = "canceled"
    error = obj.get("last_payment_error") or {}
    return PaymentEvent(
        kind=kind,
        refund_status=(
            "succeeded"
            if event_type == "charge.refunded"
            else str(obj.get("status") or "unknown").lower()
        )
        if kind == "refund"
        else None,
        refund_reference=reference
        if kind == "refund" and reference.startswith("re_")
        else "",
        payment=replace(
            facts,
            state=state,
            event_time=facts.event_time
            or _optional_int(obj.get("created"))
            or _optional_int(obj.get("current_period_end"))
            or _optional_int(obj.get("current_period_start")),
        ),
        contract=contract,
        checkout_contract=SubscriptionFacts(
            provider_reference=str(obj.get("subscription") or ""),
            customer_reference=str(obj.get("customer") or ""),
            status="active",
            cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
        )
        if state == "paid"
        else None,
        order_reference=str(
            metadata.get("bill_order_bid")
            or notification.order_bid
            or metadata.get("order_bid")
            or ""
        ),
        subscription_reference=str(metadata.get("subscription_bid") or ""),
        contract_reference=str(
            obj.get("subscription")
            or (reference if reference.startswith("sub_") else "")
        ),
        customer_reference=str(obj.get("customer") or ""),
        lookup_reference=reference if reference.startswith("cs_") else "",
        updated_payment_reference=reference
        if event_type == "checkout.session.completed" and reference.startswith("cs_")
        else "",
        failure_code=str(error.get("code") or ""),
        failure_message=str(error.get("message") or ""),
        validate_paid_amount=state == "paid" and reference.startswith(("cs_", "pi_")),
        validate_reported_amount=False,
        authoritative_contract=kind == "contract",
        update_subscription_on_failure=True,
    )


def stripe_query(
    notification: PaymentNotificationResult, terms: PaymentQueryTerms
) -> PaymentEvent:
    """Preserve Stripe's identity and unpaid-session recovery rules at its boundary."""
    from flaskr.service.common.models import raise_error

    payload = notification.provider_payload or {}
    if terms.is_contract:
        raw = payload.get("subscription") or {}
        facts = subscription_facts(raw)
        if (
            not facts.provider_reference
            or facts.provider_reference.strip() != terms.reference.strip()
        ):
            raise_error("server.order.orderStatusError")
        return PaymentEvent(
            kind="contract",
            contract=facts,
            contract_event_type="customer.subscription.updated",
            contract_reference=facts.provider_reference,
            payment=PaymentFacts(
                source="query",
                event_type="manual_sync",
                event_time=_optional_int(
                    raw.get("created")
                    or raw.get("current_period_end")
                    or raw.get("current_period_start")
                ),
            ),
            failure_code=str(raw.get("status") or "subscription_sync")
            if facts.status in {"past_due", "expired", "canceled"}
            else "",
            failure_message="Stripe subscription sync indicates renewal is not paid yet"
            if facts.status in {"past_due", "expired", "canceled"}
            else "",
            validate_reported_amount=False,
            authoritative_contract=True,
        )
    session = payload.get("checkout_session") or {}
    intent = payload.get("payment_intent") or {}
    paid = (
        session.get("payment_status") in {"paid", "no_payment_required"}
        or intent.get("status") == "succeeded"
    )
    if str(session.get("id") or "").strip() != terms.reference.strip():
        raise_error("server.order.orderStatusError")
    candidates = [item.get("metadata") for item in (session, intent)]
    expected = {
        "bill_order_bid": terms.order_reference,
        "creator_bid": terms.customer_reference,
        "product_bid": terms.product_reference,
    }
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key, value in expected.items():
                actual = str(candidate.get(key) or "").strip()
                if actual and actual != str(value).strip():
                    raise_error("server.order.orderStatusError")
    bound = next(
        (
            item
            for item in candidates
            if isinstance(item, dict) and item.get("bill_order_bid")
        ),
        None,
    )
    if bound is None and paid:
        raise_error("server.order.orderStatusError")
    facts = notification_facts("stripe", notification)
    facts = replace(
        facts,
        state="paid" if paid else "pending",
        source="query",
        event_time=_optional_int(session.get("created")) or facts.event_time,
    )
    return PaymentEvent(
        kind="payment",
        payment=facts,
        checkout_contract=SubscriptionFacts(
            provider_reference=str(session.get("subscription") or ""),
            customer_reference=str(session.get("customer") or ""),
            status="active",
            cancel_at_period_end=bool(session.get("cancel_at_period_end")),
        )
        if paid
        else None,
        contract_reference=str(session.get("subscription") or ""),
        customer_reference=str(session.get("customer") or ""),
        updated_payment_reference=str(session.get("id") or terms.reference),
        validate_paid_amount=paid,
        expired=not paid and session.get("status") == "expired",
        validate_reported_amount=False,
        authoritative_contract=False,
    )


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


def saved_query_state(provider: str, payload: dict[str, Any]) -> str:
    """Read pre-contract query snapshots only at the protocol compatibility boundary."""
    if provider == "pingxx":
        charge = payload.get("charge") or {}
        return (
            "paid"
            if charge.get("paid") or charge.get("time_paid")
            else "canceled"
            if charge.get("reversed")
            else "pending"
        )
    return native_facts(provider, payload).state


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
    event_type = str(getattr(result, "status", "") or "")
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


def saved_checkout_is_payable(provider: str, metadata: dict[str, Any]) -> bool:
    """Prefer normalized query evidence and retain pre-contract snapshot semantics."""
    if "latest_payment_state" in metadata:
        return metadata["latest_payment_state"] == "pending"
    from flaskr.service.common.native_payment_status import is_native_payment_payable

    return is_native_payment_payable(
        provider, metadata.get("latest_provider_payload") or {}
    )
