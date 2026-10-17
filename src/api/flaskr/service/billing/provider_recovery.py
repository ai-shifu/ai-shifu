"""Protocol recovery of stored actions and closure, isolated from checkout policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flaskr.common.public_urls import build_stripe_billing_result_url
from flaskr.service.common.models import raise_error
from flaskr.service.order.payment_providers.api import (
    PaymentAction,
    historical_payment_definition,
    stored_payment_action,
)

from .primitives import normalize_bid as _normalize_bid

if TYPE_CHECKING:
    from flask import Flask

    from .models import BillingOrder


def _inject_billing_query(url: str, bill_order_bid: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("bill_order_bid", bill_order_bid)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _as_plain_dict(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    return {}


def _reconcile_stored_stripe_checkout_before_replacement(
    app: Flask,
    *,
    bill_order_bid: str,
    checkout_session_id: str,
    provider: object,
) -> None:
    """Expire the stale Stripe session. Runs with NO transaction open.

    Takes plain values rather than the order row: it only talks to the
    provider, so it must not hold a transaction open while it does.
    """
    if not checkout_session_id:
        return

    try:
        session = _as_plain_dict(
            provider.retrieve_checkout_session(
                session_id=checkout_session_id,
                app=app,
            )
        )
    except Exception as exc:
        app.logger.warning(
            "Failed to retrieve Stripe checkout session %s before billing order %s replacement: %s",
            checkout_session_id,
            bill_order_bid,
            exc,
        )
        raise_error("server.order.orderStatusError")

    session_status = str(session.get("status") or "").strip().lower()
    payment_status = str(session.get("payment_status") or "").strip().lower()
    if session_status == "expired":
        return
    if session_status == "complete" or payment_status == "paid":
        app.logger.warning(
            "Refusing to replace billing order %s checkout because Stripe session %s is already %s/%s",
            bill_order_bid,
            checkout_session_id,
            session_status,
            payment_status,
        )
        raise_error("server.order.orderStatusError")
    if session_status != "open":
        app.logger.warning(
            "Refusing to replace billing order %s checkout because Stripe session %s has unsafe status %s/%s",
            bill_order_bid,
            checkout_session_id,
            session_status,
            payment_status,
        )
        raise_error("server.order.orderStatusError")

    try:
        provider.expire_checkout_session(
            session_id=checkout_session_id,
            app=app,
        )
    except Exception as exc:
        app.logger.warning(
            "Failed to expire Stripe checkout session %s before billing order %s replacement: %s",
            checkout_session_id,
            bill_order_bid,
            exc,
        )
        raise_error("server.order.orderStatusError")


def _stored_stripe_checkout_session_id(order: BillingOrder) -> str:
    """Return the Stripe session stored on the order, if any."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    checkout_payload = (
        metadata.get("checkout", {})
        if isinstance(metadata.get("checkout"), dict)
        else {}
    )
    return (
        _normalize_bid(checkout_payload.get("id"))
        or _normalize_bid(order.provider_reference_id)
        or ""
    )


def _stored_stripe_checkout_urls_match_current_origin(
    app: Flask,
    *,
    order: BillingOrder,
    checkout_payload: dict[str, Any],
) -> bool:
    stored_success_url = str(checkout_payload.get("success_url") or "").strip()
    stored_cancel_url = str(checkout_payload.get("cancel_url") or "").strip()

    # Older stored payloads may not include callback URLs; keep legacy reuse.
    if not stored_success_url and not stored_cancel_url:
        return True

    expected_success_url = _inject_billing_query(
        build_stripe_billing_result_url(),
        order.bill_order_bid,
    )
    expected_cancel_url = _inject_billing_query(
        build_stripe_billing_result_url(canceled=True),
        order.bill_order_bid,
    )

    if stored_success_url and stored_success_url != expected_success_url:
        app.logger.info(
            "Skipping Stripe checkout reuse for billing order %s because success_url changed",
            order.bill_order_bid,
        )
        return False
    if stored_cancel_url and stored_cancel_url != expected_cancel_url:
        app.logger.info(
            "Skipping Stripe checkout reuse for billing order %s because cancel_url changed",
            order.bill_order_bid,
        )
        return False
    return True


def _stripe_stored_action(app: Flask, order: BillingOrder) -> PaymentAction | None:
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    payload = metadata.get("checkout") or {}
    if not isinstance(
        payload, dict
    ) or not _stored_stripe_checkout_urls_match_current_origin(
        app, order=order, checkout_payload=payload
    ):
        return None
    url = str(payload.get("url") or "").strip()
    return (
        PaymentAction(
            "redirect", url=url, session_id=_stored_stripe_checkout_session_id(order)
        )
        if url
        else None
    )


_ACTION_READERS = {"stripe": _stripe_stored_action}
_REFERENCE_READERS = {"stripe": _stored_stripe_checkout_session_id}
_CLOSERS = {"stripe": _reconcile_stored_stripe_checkout_before_replacement}


def uses_generic_payment_recovery(provider: str) -> bool:
    """Use declared payment operations unless a legacy protocol owns recovery."""
    return provider not in _CLOSERS


def stored_checkout_action(app: Flask, order: BillingOrder) -> PaymentAction | None:
    """Resolve a stored action using the protocol's own compatibility reader."""
    reader = _ACTION_READERS.get(order.payment_provider)
    if reader:
        return reader(app, order)
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    return stored_payment_action(metadata.get("payment_action"))


def stored_checkout_reference(order: BillingOrder) -> str:
    """Resolve a reference in its integration's original snapshot schema."""
    reader = _REFERENCE_READERS.get(order.payment_provider)
    return reader(order) if reader else str(order.provider_reference_id or "")


def reconcile_checkout_before_replacement(
    app: Flask,
    *,
    provider_name: str,
    bill_order_bid: str,
    reference: str,
    client: object,
) -> None:
    """Run an integration-owned close protocol; success means safe replacement."""
    closer = _CLOSERS.get(provider_name)
    if closer:
        closer(
            app,
            bill_order_bid=bill_order_bid,
            checkout_session_id=reference,
            provider=client,
        )
        return
    definition = historical_payment_definition(provider_name)
    if not reference or not definition.capabilities.close:
        raise_error("server.order.orderStatusError")
    result = client.cancel_payment(
        provider_reference=reference,
        reference_type=definition.operation_reference_type("close"),
        app=app,
    )
    if not result.is_closed:
        raise_error("server.order.orderStatusError")
