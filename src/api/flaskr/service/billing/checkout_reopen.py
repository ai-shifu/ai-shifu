"""Reopening, replacing, and closing pending billing checkout attempts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flaskr.common.public_urls import build_stripe_billing_result_url
from flaskr.dao import db
from flaskr.dao.uow import (
    unit_of_work,
)
from flaskr.service.common.models import raise_error
from flaskr.service.common.native_payment_status import (
    NATIVE_PAYMENT_STATE_CANCELED,
    is_native_payment_payable,
    resolve_native_payment_state,
)
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .checkout_orders import (
    _build_checkout_response_payload,
    _build_manual_payment_payload,
    _load_billing_order_by_bid,
    _load_reopen_targets,
    _resolve_billing_order_expires_at,
    _resolve_billing_order_payment_mode,
)
from .checkout_pricing import (
    _resolve_required_stripe_provider_price_mapping,
    _stored_provider_price_snapshot_matches_mapping,
)
from .checkout_provider import (
    _build_provider_checkout_request,
    _inject_billing_query,
    _ProviderCheckoutRequest,
)
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
)
from .dtos import (
    BillingCheckoutResultDTO,
)
from .models import (
    BillingOrder,
)
from .payment_policy import is_manual_payment_provider
from .primitives import normalize_bid as _normalize_bid

if TYPE_CHECKING:
    from types import ModuleType

    from flask import Flask


def _checkout_facade() -> ModuleType:
    """Resolve collaborators through ``checkout`` so its patch points stay live."""
    from . import checkout

    return checkout


def _prepare_existing_billing_order_checkout(
    app: Flask,
    *,
    creator_bid: str,
    bill_order_bid: str,
    product_bid: str,
    requested_channel: str = "",
) -> BillingCheckoutResultDTO | _ProviderCheckoutRequest:
    """Reopen a pending order: read, reconcile at the provider, build the request.

    Provider reconciliation runs between persistence steps. A saved native QR
    is reusable only while the provider confirms that its trade is payable.
    """
    pending_stripe_session_id = ""
    saved_manual_checkout: BillingCheckoutResultDTO | None = None
    manual_attempt_needs_replacement = False
    with unit_of_work():
        order, product = _load_reopen_targets(bill_order_bid, product_bid)
        if (
            is_manual_payment_provider(order.payment_provider)
            and order.provider_reference_id
        ):
            saved_manual_checkout = _build_saved_manual_checkout(
                order, requested_channel=requested_channel
            )
            manual_attempt_needs_replacement = True
        if _normalize_bid(order.payment_provider) == "stripe":
            provider_price_mapping = _resolve_required_stripe_provider_price_mapping(
                app,
                product=product,
            )
            order_metadata = (
                order.metadata_json if isinstance(order.metadata_json, dict) else {}
            )
            if not _stored_provider_price_snapshot_matches_mapping(
                order,
                provider_price_mapping,
                metadata=order_metadata,
            ):
                raise_error("server.order.orderStatusError")
            stored_checkout_result = _build_stored_stripe_checkout_result(app, order)
            if stored_checkout_result is not None:
                return stored_checkout_result
            pending_stripe_session_id = _stored_stripe_checkout_session_id(order)

    if saved_manual_checkout is not None:
        if saved_manual_checkout.provider == "pingxx":
            return saved_manual_checkout
        if _saved_native_checkout_is_still_payable(app, creator_bid, bill_order_bid):
            return saved_manual_checkout

    if manual_attempt_needs_replacement:
        bill_order_bid = _replace_closed_manual_attempt(
            app,
            creator_bid=creator_bid,
            bill_order_bid=bill_order_bid,
            requested_channel=requested_channel,
        )

    if pending_stripe_session_id:
        _reconcile_stored_stripe_checkout_before_replacement(
            app,
            bill_order_bid=bill_order_bid,
            checkout_session_id=pending_stripe_session_id,
        )

    with unit_of_work():
        order, product = _load_reopen_targets(bill_order_bid, product_bid)
        provider_price_mapping = (
            _resolve_required_stripe_provider_price_mapping(app, product=product)
            if _normalize_bid(order.payment_provider) == "stripe"
            else None
        )
        order.channel = (
            requested_channel or _normalize_bid(order.channel) or "alipay_qr"
        )
        return _build_provider_checkout_request(
            app,
            creator_bid=creator_bid,
            order=order,
            product=product,
            payment_provider=order.payment_provider,
            payment_mode=_resolve_billing_order_payment_mode(order),
            channel=order.channel,
            reused_existing_order=True,
            provider_price_mapping=provider_price_mapping,
        )


def _build_saved_manual_checkout(
    order: BillingOrder,
    *,
    requested_channel: str,
) -> BillingCheckoutResultDTO | None:
    """Rebuild the saved manual-payment response when its credential is reusable."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    extra = metadata.get("provider_extra") or {}
    if (not requested_channel or requested_channel == order.channel) and (
        extra.get("credential") or extra.get("jsapi_params")
    ):
        response = _build_checkout_response_payload(
            order,
            payment_provider=order.payment_provider,
            payment_mode=_resolve_billing_order_payment_mode(order),
            status="pending",
            reused_existing_order=True,
        )
        response["payment_payload"] = _build_manual_payment_payload(
            order.provider_reference_id,
            metadata.get("checkout") or {},
            extra,
        )
        return BillingCheckoutResultDTO(**response)
    return None


def _saved_native_checkout_is_still_payable(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
) -> bool:
    """Reconcile at the provider and report whether the saved trade is payable."""
    _checkout_facade().sync_billing_order(app, creator_bid, bill_order_bid, {})
    with unit_of_work():
        order = _load_billing_order_by_bid(bill_order_bid)
        if order is None or order.status == BILLING_ORDER_STATUS_PAID:
            raise_error("server.order.orderStatusError")
        metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
        return bool(
            order.status == BILLING_ORDER_STATUS_PENDING
            and is_native_payment_payable(
                order.payment_provider,
                metadata.get("latest_provider_payload") or {},
            )
        )


def _replace_closed_manual_attempt(
    app: Flask,
    *,
    creator_bid: str,
    bill_order_bid: str,
    requested_channel: str,
) -> str:
    """Close the old manual attempt and create its pending replacement order."""
    _checkout_facade()._close_manual_payment_before_replacement(
        app, creator_bid, bill_order_bid
    )
    with unit_of_work():
        old_order = _load_billing_order_by_bid(bill_order_bid)
        if old_order is None or old_order.status != BILLING_ORDER_STATUS_CANCELED:
            raise_error("server.order.orderStatusError")
        old_metadata = (
            old_order.metadata_json if isinstance(old_order.metadata_json, dict) else {}
        )
        metadata = dict(old_metadata)
        for key in (
            "checkout",
            "provider_extra",
            "latest_provider_payload",
            "latest_event_time",
            "latest_source",
            "latest_event_type",
            "invalidated_reason",
            "invalidated_at",
        ):
            metadata.pop(key, None)
        metadata["replaces_bill_order_bid"] = old_order.bill_order_bid
        replacement = BillingOrder(
            bill_order_bid=generate_id(app),
            creator_bid=old_order.creator_bid,
            order_type=old_order.order_type,
            product_bid=old_order.product_bid,
            subscription_bid=old_order.subscription_bid,
            currency=old_order.currency,
            payable_amount=old_order.payable_amount,
            paid_amount=0,
            payment_provider=old_order.payment_provider,
            channel=requested_channel or old_order.channel,
            provider_reference_id="",
            status=BILLING_ORDER_STATUS_PENDING,
            expires_at=_resolve_billing_order_expires_at(now=now_utc()),
            metadata_json=metadata,
            campaign_bid=old_order.campaign_bid,
            campaign_benefit_type=old_order.campaign_benefit_type,
            campaign_discount_amount=old_order.campaign_discount_amount,
            campaign_bonus_credit_amount=old_order.campaign_bonus_credit_amount,
        )
        old_order.metadata_json = {
            **old_metadata,
            "replaced_by_bill_order_bid": replacement.bill_order_bid,
        }
        db.session.add(replacement)
        db.session.flush()
        return replacement.bill_order_bid


class _ManualPaymentNeedsClosureError(Exception):
    """Move provider I/O out of the checkout preparation transaction."""

    def __init__(self, bill_order_bid: str) -> None:
        super().__init__(bill_order_bid)
        self.bill_order_bid = bill_order_bid


def _record_confirmed_manual_payment_closure(order: BillingOrder) -> bool:
    """Persist closure confirmed by the latest provider reconciliation."""
    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    payload = metadata.get("latest_provider_payload") or {}
    closed = (
        bool((payload.get("charge") or {}).get("reversed"))
        if order.payment_provider == "pingxx"
        else resolve_native_payment_state(order.payment_provider, payload)
        == NATIVE_PAYMENT_STATE_CANCELED
    )
    if not closed:
        return False
    # A timeout cannot become canceled through the generic status guard.
    order.status = BILLING_ORDER_STATUS_CANCELED
    order.updated_at = now_utc()
    db.session.add(order)
    return True


def _close_manual_payment_before_replacement(
    app: Flask,
    creator_bid: str,
    bill_order_bid: str,
) -> None:
    """Reconcile, close, and confirm an old attempt before allowing a new one."""
    _checkout_facade().sync_billing_order(app, creator_bid, bill_order_bid, {})
    with unit_of_work():
        order = _load_billing_order_by_bid(bill_order_bid)
        if order is None or order.creator_bid != creator_bid:
            raise_error("server.order.orderNotFound")
        if order.status == BILLING_ORDER_STATUS_PAID:
            # Payment has already been applied durably; re-evaluate the plan on retry.
            raise_error("server.order.orderStatusError")
        if order.status == BILLING_ORDER_STATUS_CANCELED:
            return
        if _record_confirmed_manual_payment_closure(order):
            return
        provider_name = order.payment_provider
        reference = order.provider_reference_id
    result = (
        _checkout_facade()
        .get_payment_provider(provider_name)
        .cancel_payment(
            provider_reference=reference,
            reference_type="charge" if provider_name == "pingxx" else "trade",
            app=app,
        )
    )
    if result.status != "cancelled":
        raise_error("server.order.orderStatusError")
    _checkout_facade().sync_billing_order(app, creator_bid, bill_order_bid, {})
    with unit_of_work():
        order = _load_billing_order_by_bid(bill_order_bid)
        if (
            order is None
            or order.creator_bid != creator_bid
            or order.status == BILLING_ORDER_STATUS_PAID
        ):
            raise_error("server.order.orderStatusError")
        if not _record_confirmed_manual_payment_closure(order):
            raise_error("server.order.orderStatusError")


def _prepare_pending_order_for_replacement(app: Flask, order: BillingOrder) -> None:
    """Expire the stale provider session of an order about to be replaced.

    This one deliberately stays inside the caller's transaction: the session
    has to be expired at the provider BEFORE the order is canceled locally.
    Deferring it past the commit would leave a payable Stripe session pointing
    at an order that no longer accepts payment.
    """
    if (
        is_manual_payment_provider(order.payment_provider)
        and order.provider_reference_id
    ):
        raise _ManualPaymentNeedsClosureError(order.bill_order_bid)
    if _normalize_bid(order.payment_provider) != "stripe":
        return
    _reconcile_stored_stripe_checkout_before_replacement(
        app,
        bill_order_bid=order.bill_order_bid,
        checkout_session_id=_stored_stripe_checkout_session_id(order),
    )


def _build_stored_stripe_checkout_result(
    app: Flask,
    order: BillingOrder,
) -> BillingCheckoutResultDTO | None:
    if _normalize_bid(order.payment_provider) != "stripe":
        return None

    metadata = order.metadata_json if isinstance(order.metadata_json, dict) else {}
    checkout_payload = (
        metadata.get("checkout", {})
        if isinstance(metadata.get("checkout"), dict)
        else {}
    )
    redirect_url = str(checkout_payload.get("url") or "").strip()
    checkout_session_id = (
        _normalize_bid(checkout_payload.get("id"))
        or _normalize_bid(order.provider_reference_id)
        or None
    )
    if not _stored_stripe_checkout_urls_match_current_origin(
        app,
        order=order,
        checkout_payload=checkout_payload,
    ):
        return None
    if not redirect_url:
        return None

    response = _build_checkout_response_payload(
        order,
        payment_provider="stripe",
        payment_mode=_resolve_billing_order_payment_mode(order),
        status="pending",
        reused_existing_order=True,
    )
    response["redirect_url"] = redirect_url
    response["checkout_session_id"] = checkout_session_id
    return BillingCheckoutResultDTO(**response)


def _as_plain_dict(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    return {}


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


def _reconcile_stored_stripe_checkout_before_replacement(
    app: Flask,
    *,
    bill_order_bid: str,
    checkout_session_id: str,
) -> None:
    """Expire the stale Stripe session. Runs with NO transaction open.

    Takes plain values rather than the order row: it only talks to the
    provider, so it must not hold a transaction open while it does.
    """
    if not checkout_session_id:
        return

    provider = _checkout_facade().get_payment_provider("stripe")
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
