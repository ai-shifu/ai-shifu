"""Learner gateway requests and snapshot serialization, without purchase state changes."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, Unpack
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flaskr.common.public_urls import (
    build_payment_result_url,
    build_stripe_learner_result_url,
)
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.config import get_config
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.payment_providers import payment_definition
from flaskr.service.order.payment_providers.base import (
    PaymentCreationResult,
    PaymentProvider,
    PaymentRequest,
)
from flaskr.service.order.payment_providers.contracts import (
    CheckoutTerms,
    PaymentAction,
)
from flaskr.service.order.payment_providers.normalization import creation_action
from flaskr.service.order.raw_snapshots import (
    RAW_BIZ_DOMAIN_ORDER,
    native_snapshot_bid_attr,
    native_snapshot_model,
    registered_native_payment_providers,
    upsert_native_snapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

    from .models import Order


class CoursePaymentDescription(Protocol):
    """Only the trusted course identity and display title reach protocol serialization."""

    bid: str
    title: str


class PaymentAmountArgs(TypedDict):
    """Authorized purchase amounts and display text."""

    amount: int
    subject: str
    body: str
    client_ip: str
    order_no: str


class LearnerChargeArgs(PaymentAmountArgs):
    """Stable compatibility signature for a learner checkout."""

    app: Flask
    buy_record: Order
    course: CoursePaymentDescription
    channel: str


class AttemptCreationArgs(LearnerChargeArgs):
    """Protocol context supplied by the purchase transaction owner."""

    provider: PaymentProvider
    open_id: str
    before_provider_call: Callable[[], None]


@dataclass(slots=True)
class PaymentPresentation:
    """Compatibility presentation returned by a persisted provider attempt."""

    order_bid: str
    user_bid: str
    paid_price: object
    channel: str
    qr_url: object
    payment_channel: str
    payment_payload: dict[str, Any]
    payment_action: PaymentAction | None = None


@dataclass(slots=True)
class PreparedDirectPayment:
    """Committed attempt identity and authorized request, detached from ORM state."""

    provider_name: str
    request: PaymentRequest
    order_bid: str
    paid_price: object
    metadata: dict[str, Any]
    provider: PaymentProvider = field(repr=False)
    snapshot_id: int | None = None
    credential_overrides: dict[str, Any] = field(default_factory=dict, repr=False)


def _stringify_payload(payload: object) -> str:
    if not payload:
        return "{}"
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload)


def _format_response_channel(payment_channel: str, provider_channel: str) -> str:
    if payment_channel == "stripe":
        return (
            "stripe"
            if provider_channel == "payment_intent"
            else f"stripe:{provider_channel}"
        )
    return provider_channel


def _inject_order_query(url: str, order_id: str) -> str:
    if not url:
        return url
    parsed = urlsplit(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "order_id" not in query_items:
        query_items["order_id"] = order_id
    new_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            parsed.fragment,
        )
    )


def _generate_direct_charge(
    *,
    provider_name: str,
    app: Flask,
    buy_record: Order,
    course: CoursePaymentDescription,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
    provider: PaymentProvider,
    open_id: str,
    before_provider_call: Callable[[], None],
    prepare_only: bool = False,
) -> PaymentPresentation | PreparedDirectPayment:
    """Create a direct attempt using registered capabilities and snapshot storage."""
    definition = payment_definition(provider_name)
    sanitized_subject = _sanitize_pingxx_text(
        subject,
        fallback=course.title or "",
        max_length=definition.subject_limit,
    )
    sanitized_body = _sanitize_pingxx_text(
        body,
        fallback=sanitized_subject,
        max_length=definition.body_limit,
    )
    extra = {
        "metadata": {
            "order_bid": buy_record.order_bid,
            "user_bid": buy_record.user_bid,
            "shifu_bid": buy_record.shifu_bid,
        }
    }
    route = next(
        (route for route in definition.routes if route.channel == channel), None
    )
    if route and route.requires_open_id:
        if not open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        extra["open_id"] = open_id
    if route and route.action == "redirect":
        extra.update(
            provider.checkout_options(
                CheckoutTerms(
                    order_reference=order_no,
                    product_reference=buy_record.shifu_bid,
                    amount=amount,
                    currency="CNY",
                    payment_mode="payment",
                    channel=channel,
                    metadata=extra["metadata"],
                    open_id=open_id,
                    success_url=_inject_order_query(
                        build_payment_result_url("/payment/result"),
                        buy_record.order_bid,
                    ),
                    cancel_url=_inject_order_query(
                        build_payment_result_url("/payment/result", canceled=True),
                        buy_record.order_bid,
                    ),
                )
            )
        )
    payment_request = PaymentRequest(
        order_bid=order_no,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        channel=channel,
        currency="CNY",
        subject=sanitized_subject,
        body=sanitized_body,
        client_ip=client_ip,
        extra=extra,
    )
    prepared = PreparedDirectPayment(
        provider_name,
        payment_request,
        buy_record.order_bid,
        buy_record.paid_price,
        {
            "course_bid": course.bid,
            "subject": sanitized_subject,
            "body": sanitized_body,
        },
        provider,
    )
    if prepare_only:
        snapshot = upsert_native_snapshot(
            biz_domain=RAW_BIZ_DOMAIN_ORDER,
            payment_provider=provider_name,
            native_payment_order_bid=order_no,
            provider_attempt_id=order_no,
            order_bid=buy_record.order_bid,
            user_bid=buy_record.user_bid,
            shifu_bid=buy_record.shifu_bid,
            amount=amount,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
            channel=channel,
            metadata={
                **prepared.metadata,
                "prepared_payment_request": asdict(payment_request),
            },
        )
        db.session.add(snapshot)
        db.session.flush()
        prepared.snapshot_id = snapshot.id
        return prepared
    before_provider_call()
    result = provider.create_payment(request=payment_request, app=app)
    return persist_direct_creation(prepared, result)


def recover_direct_creation(
    *,
    provider_name: str,
    order: Order,
    snapshot: object,
    provider: PaymentProvider,
) -> PreparedDirectPayment | None:
    """Retry the original merchant request after a lost response or worker restart."""
    metadata = json.loads(snapshot.metadata_json or "{}")
    stored = (
        metadata.get("prepared_payment_request") if isinstance(metadata, dict) else None
    )
    if not isinstance(stored, dict):
        return None
    try:
        payment_request = PaymentRequest(**stored)
    except (TypeError, ValueError):
        raise_error("server.order.orderStatusError")
    if (
        payment_request.order_bid
        != getattr(snapshot, native_snapshot_bid_attr(provider_name))
        or payment_request.amount != snapshot.amount
        or payment_request.user_bid != order.user_bid
        or payment_request.shifu_bid != order.shifu_bid
        or payment_request.channel != snapshot.channel
        or payment_request.currency != snapshot.currency
    ):
        raise_error("server.order.orderStatusError")
    return PreparedDirectPayment(
        provider_name,
        payment_request,
        order.order_bid,
        order.paid_price,
        {
            key: metadata[key]
            for key in ("course_bid", "subject", "body")
            if key in metadata
        },
        provider,
        snapshot_id=snapshot.id,
    )


def persist_direct_creation(
    prepared: PreparedDirectPayment,
    result: PaymentCreationResult,
) -> PaymentPresentation:
    """Attach the provider response without rewinding an early callback's state."""
    provider_name, payment_request = prepared.provider_name, prepared.request
    channel = payment_request.channel
    action = creation_action(provider_name, channel, result)
    metadata = {**prepared.metadata, "payment_action": action.to_dict()}
    if result.extra.get("prepay_id"):
        metadata["prepay_id"] = result.extra["prepay_id"]
    if prepared.snapshot_id is None:
        snapshot = upsert_native_snapshot(
            biz_domain=RAW_BIZ_DOMAIN_ORDER,
            payment_provider=provider_name,
            native_payment_order_bid=payment_request.order_bid,
            provider_attempt_id=str(
                result.provider_reference or payment_request.order_bid
            ),
            order_bid=prepared.order_bid,
            user_bid=payment_request.user_bid,
            shifu_bid=payment_request.shifu_bid,
            amount=payment_request.amount,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
            channel=channel,
            raw_request=result.extra.get("raw_request") or {},
            raw_response=result.raw_response,
            metadata=metadata,
        )
    else:
        snapshot = (
            native_snapshot_model(provider_name)
            .query.filter_by(id=prepared.snapshot_id)
            .first()
        )
        if (
            snapshot is None
            or snapshot.deleted != 0
            or snapshot.biz_domain != RAW_BIZ_DOMAIN_ORDER
            or snapshot.order_bid != prepared.order_bid
            or snapshot.amount != payment_request.amount
        ):
            raise_error("server.order.orderNotFound")
        existing_metadata = json.loads(snapshot.metadata_json or "{}")
        verified_reference = existing_metadata.get("verified_provider_reference")
        returned_reference = str(result.provider_reference or "")
        if (
            verified_reference
            and returned_reference
            and verified_reference != returned_reference
        ):
            # A verified early callback already bound this payment. Retain a
            # conflicting late result for reconciliation without presenting it.
            action = PaymentAction("none")
            metadata.update(
                payment_action=action.to_dict(),
                conflicting_creation_result=asdict(result),
            )
        else:
            snapshot.provider_attempt_id = (
                verified_reference or returned_reference or payment_request.order_bid
            )
        snapshot.raw_request = _stringify_payload(result.extra.get("raw_request") or {})
        snapshot.raw_response = _stringify_payload(result.raw_response)
        snapshot.metadata_json = _stringify_payload({**existing_metadata, **metadata})
    stored_metadata = json.loads(snapshot.metadata_json or "{}")
    stored_metadata.pop("prepared_payment_request", None)
    snapshot.metadata_json = _stringify_payload(stored_metadata)
    db.session.add(snapshot)
    payload = {
        "qr_url": action.url or "",
        "credential": result.extra.get("credential") or {},
    }
    if action.type == "jsapi":
        payload.update(
            {
                "mode": "jsapi",
                "prepay_id": result.extra.get("prepay_id"),
                "jsapi_params": action.parameters,
            }
        )
    return PaymentPresentation(
        prepared.order_bid,
        payment_request.user_bid,
        prepared.paid_price,
        channel,
        action.url or "",
        payment_channel=provider_name,
        payment_payload=payload,
        payment_action=action,
    )


def _sanitize_pingxx_text(value: str | None, *, fallback: str, max_length: int) -> str:
    text = (value or fallback or "").strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if not text:
        text = fallback.strip() or "订单支付"
    return text[:max_length]


def _generate_pingxx_charge(
    *,
    app: Flask,
    buy_record: Order,
    course: CoursePaymentDescription,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
    provider: PaymentProvider,
    open_id: str,
    before_provider_call: Callable[[], None],
) -> PaymentPresentation:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    pingpp_id = get_config("PINGXX_APP_ID")
    provider_options: dict[str, Any] = {"app_id": pingpp_id}
    charge_extra: dict[str, Any] = {}
    qr_url_key: str | None = None
    product_id = course.bid

    if channel == "wx_pub_qr":  # wxpay scan
        charge_extra = {"product_id": product_id}
        qr_url_key = "wx_pub_qr"
    elif channel == "alipay_qr":  # alipay scan
        charge_extra = {}
        qr_url_key = "alipay_qr"
    elif channel == "wx_pub":  # wxpay JSAPI
        if not open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        charge_extra = {"open_id": open_id}
        qr_url_key = "wx_pub"
    elif channel == "wx_wap":  # wxpay H5
        charge_extra = {}
    else:
        app.logger.error("channel:%s not support", channel)
        raise_error("server.pay.payChannelNotSupport")

    provider_options["charge_extra"] = charge_extra
    sanitized_subject = _sanitize_pingxx_text(
        subject,
        fallback=course.title or "订单支付",
        max_length=32,
    )
    sanitized_body = _sanitize_pingxx_text(
        body,
        fallback=sanitized_subject,
        max_length=128,
    )
    if sanitized_subject != (subject or "") or sanitized_body != (body or ""):
        app.logger.info(
            "Sanitized pingxx payment text for order=%s subject_changed=%s body_changed=%s",
            order_no,
            sanitized_subject != (subject or ""),
            sanitized_body != (body or ""),
        )
    payment_request = PaymentRequest(
        order_bid=order_no,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        channel=channel,
        currency="cny",
        subject=sanitized_subject,
        body=sanitized_body,
        client_ip=client_ip,
        extra=provider_options,
    )
    before_provider_call()
    result = provider.create_payment(request=payment_request, app=app)
    charge = result.raw_response
    credential = charge.get("credential", {}) or {}
    qr_url = credential.get(qr_url_key) if qr_url_key else ""
    app.logger.info("Pingxx charge created:%s", charge)

    pingxx_order = PingxxOrder()
    pingxx_order.pingxx_order_bid = order_no
    pingxx_order.biz_domain = RAW_BIZ_DOMAIN_ORDER
    pingxx_order.user_bid = buy_record.user_bid
    pingxx_order.shifu_bid = buy_record.shifu_bid
    pingxx_order.order_bid = buy_record.order_bid
    pingxx_order.transaction_no = charge["order_no"]
    pingxx_order.app_id = charge["app"]
    pingxx_order.channel = charge["channel"]
    pingxx_order.amount = amount
    pingxx_order.currency = charge["currency"]
    pingxx_order.subject = charge["subject"]
    pingxx_order.body = charge["body"]
    pingxx_order.client_ip = charge["client_ip"]
    pingxx_order.extra = str(charge["extra"])
    pingxx_order.charge_id = charge["id"]
    pingxx_order.status = 0
    pingxx_order.charge_object = str(charge)
    db.session.add(pingxx_order)
    return PaymentPresentation(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        channel,
        qr_url or "",
        payment_channel="pingxx",
        payment_payload={
            "qr_url": qr_url or "",
            "credential": credential,
        },
    )


def _generate_stripe_charge(
    *,
    app: Flask,
    buy_record: Order,
    course: CoursePaymentDescription,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
    provider: PaymentProvider,
    open_id: str,
    before_provider_call: Callable[[], None],
) -> PaymentPresentation:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    del course, open_id
    resolved_mode = channel.lower() if channel else "payment_intent"
    if resolved_mode in {"checkout", "checkout_session"}:
        resolved_mode = "checkout_session"
    else:
        resolved_mode = "payment_intent"

    currency = get_config("STRIPE_DEFAULT_CURRENCY", "usd")
    metadata = {
        "order_bid": buy_record.order_bid,
        "stripe_order_bid": order_no,
        "user_bid": buy_record.user_bid,
        "shifu_bid": buy_record.shifu_bid,
    }
    provider_options: dict[str, Any] = {
        "mode": resolved_mode,
        "metadata": metadata,
    }

    if resolved_mode == "checkout_session":
        provider_options["success_url"] = _inject_order_query(
            build_stripe_learner_result_url(), buy_record.order_bid
        )
        provider_options["cancel_url"] = _inject_order_query(
            build_stripe_learner_result_url(canceled=True), buy_record.order_bid
        )
        provider_options["line_items"] = [
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount,
                    "product_data": {"name": subject},
                },
                "quantity": 1,
            }
        ]

    payment_request = PaymentRequest(
        order_bid=order_no,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        channel=resolved_mode,
        currency=currency,
        subject=subject,
        body=body,
        client_ip=client_ip,
        extra=provider_options,
    )
    before_provider_call()
    result = provider.create_payment(request=payment_request, app=app)

    stripe_order = StripeOrder()
    stripe_order.order_bid = buy_record.order_bid
    stripe_order.biz_domain = RAW_BIZ_DOMAIN_ORDER
    stripe_order.user_bid = buy_record.user_bid
    stripe_order.shifu_bid = buy_record.shifu_bid
    stripe_order.stripe_order_bid = order_no
    stripe_order.payment_intent_id = result.extra.get(
        "payment_intent_id",
        result.provider_reference if resolved_mode == "payment_intent" else "",
    )
    stripe_order.checkout_session_id = result.checkout_session_id or (
        result.provider_reference if resolved_mode == "checkout_session" else ""
    )
    stripe_order.latest_charge_id = result.extra.get("latest_charge_id", "")
    stripe_order.amount = amount
    stripe_order.currency = currency
    stripe_order.status = 0
    stripe_order.receipt_url = result.extra.get("receipt_url", "")
    stripe_order.payment_method = result.extra.get("payment_method", "")
    stripe_order.failure_code = ""
    stripe_order.failure_message = ""
    stripe_order.metadata_json = _stringify_payload(result.extra.get("metadata", {}))
    stripe_order.payment_intent_object = _stringify_payload(
        result.extra.get(
            "payment_intent_object",
            result.raw_response if resolved_mode == "payment_intent" else {},
        )
    )
    stripe_order.checkout_session_object = _stringify_payload(
        result.raw_response
        if resolved_mode == "checkout_session"
        else result.extra.get("checkout_session_object", {})
    )
    db.session.add(stripe_order)

    response_channel = _format_response_channel("stripe", resolved_mode)
    qr_value = result.extra.get("url") or result.client_secret or ""
    app.logger.info("Stripe payment created: %s", result.provider_reference)

    payment_payload = {
        "mode": resolved_mode,
        "client_secret": result.client_secret or "",
        "checkout_session_url": result.extra.get("url", ""),
        "checkout_session_id": stripe_order.checkout_session_id,
        "payment_intent_id": stripe_order.payment_intent_id,
        "latest_charge_id": stripe_order.latest_charge_id,
    }

    return PaymentPresentation(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        response_channel,
        qr_value,
        payment_channel="stripe",
        payment_payload=payment_payload,
    )


_LEARNER_CREATORS = {
    "pingxx": _generate_pingxx_charge,
    "stripe": _generate_stripe_charge,
}


def supports_learner_attempt(provider: str) -> bool:
    """Admit learner checkout only when its attempt can be stored and recovered."""
    return (
        provider in _LEARNER_CREATORS
        or provider in registered_native_payment_providers()
    )


def create_learner_attempt(
    *,
    provider_name: str,
    prepare_direct: bool = False,
    **kwargs: Unpack[AttemptCreationArgs],
) -> PaymentPresentation | PreparedDirectPayment:
    """Dispatch protocol work at registration boundaries, never in purchase rules."""
    creator = _LEARNER_CREATORS.get(provider_name)
    if creator is not None:
        return creator(**kwargs)
    if not supports_learner_attempt(provider_name):
        raise_error("server.pay.payChannelNotSupport")
    return _generate_direct_charge(
        provider_name=provider_name, prepare_only=prepare_direct, **kwargs
    )
