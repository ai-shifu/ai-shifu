from __future__ import annotations

import json
from typing import Any

from .models import AlipayOrder, PingxxOrder, StripeOrder, WechatPayOrder

RAW_BIZ_DOMAIN_ORDER = "order"
RAW_BIZ_DOMAIN_BILLING = "billing"

_NATIVE_PAYMENT_MODELS = {
    "alipay": AlipayOrder,
    "wechatpay": WechatPayOrder,
}

_NATIVE_PAYMENT_BID_ATTRS = {
    "alipay": "alipay_order_bid",
    "wechatpay": "wechatpay_order_bid",
}


def legacy_stripe_snapshot_query():
    return StripeOrder.query.filter(
        StripeOrder.deleted == 0,
        StripeOrder.biz_domain == RAW_BIZ_DOMAIN_ORDER,
    )


def legacy_pingxx_snapshot_query():
    return PingxxOrder.query.filter(
        PingxxOrder.deleted == 0,
        PingxxOrder.biz_domain == RAW_BIZ_DOMAIN_ORDER,
    )


def billing_stripe_snapshot_query():
    return StripeOrder.query.filter(
        StripeOrder.deleted == 0,
        StripeOrder.biz_domain == RAW_BIZ_DOMAIN_BILLING,
    )


def billing_pingxx_snapshot_query():
    return PingxxOrder.query.filter(
        PingxxOrder.deleted == 0,
        PingxxOrder.biz_domain == RAW_BIZ_DOMAIN_BILLING,
    )


def native_snapshot_model(payment_provider: str):
    provider = str(payment_provider or "").strip().lower()
    model = _NATIVE_PAYMENT_MODELS.get(provider)
    if model is None:
        raise ValueError(f"Unsupported native payment provider: {payment_provider}")
    return model


def native_snapshot_bid_attr(payment_provider: str) -> str:
    provider = str(payment_provider or "").strip().lower()
    attr = _NATIVE_PAYMENT_BID_ATTRS.get(provider)
    if attr is None:
        raise ValueError(f"Unsupported native payment provider: {payment_provider}")
    return attr


def native_snapshot_query(payment_provider: str, biz_domain: str):
    model = native_snapshot_model(payment_provider)
    return model.query.filter(
        model.deleted == 0,
        model.biz_domain == str(biz_domain or RAW_BIZ_DOMAIN_ORDER),
    )


def legacy_native_snapshot_query(payment_provider: str):
    return native_snapshot_query(payment_provider, RAW_BIZ_DOMAIN_ORDER)


def billing_native_snapshot_query(payment_provider: str):
    return native_snapshot_query(payment_provider, RAW_BIZ_DOMAIN_BILLING)


def upsert_native_snapshot(
    *,
    biz_domain: str,
    payment_provider: str,
    provider_attempt_id: str,
    amount: int,
    currency: str,
    raw_status: str,
    raw_snapshot_status: int,
    native_payment_order_bid: str = "",
    order_bid: str = "",
    bill_order_bid: str = "",
    creator_bid: str = "",
    user_bid: str = "",
    shifu_bid: str = "",
    transaction_id: str = "",
    channel: str = "",
    raw_request: Any | None = None,
    raw_response: Any | None = None,
    raw_notification: Any | None = None,
    metadata: Any | None = None,
) -> AlipayOrder | WechatPayOrder:
    model = native_snapshot_model(payment_provider)
    provider_bid_attr = native_snapshot_bid_attr(payment_provider)
    query = model.query.filter(
        model.deleted == 0,
        model.biz_domain == str(biz_domain or RAW_BIZ_DOMAIN_ORDER),
    )
    if provider_attempt_id:
        query = query.filter(model.provider_attempt_id == str(provider_attempt_id))
    elif order_bid:
        query = query.filter(model.order_bid == str(order_bid))
    elif bill_order_bid:
        query = query.filter(model.bill_order_bid == str(bill_order_bid))

    snapshot = query.order_by(model.id.desc()).first()
    if snapshot is None:
        snapshot = model(
            biz_domain=str(biz_domain or RAW_BIZ_DOMAIN_ORDER),
            raw_request="{}",
            raw_response="{}",
            raw_notification="{}",
            metadata_json="{}",
        )

    provider_bid = (
        native_payment_order_bid
        or getattr(snapshot, provider_bid_attr, "")
        or provider_attempt_id
        or order_bid
        or bill_order_bid
    )
    setattr(snapshot, provider_bid_attr, provider_bid)
    snapshot.biz_domain = str(biz_domain or snapshot.biz_domain or RAW_BIZ_DOMAIN_ORDER)
    snapshot.order_bid = str(order_bid or snapshot.order_bid or "")
    snapshot.bill_order_bid = str(bill_order_bid or snapshot.bill_order_bid or "")
    snapshot.creator_bid = str(creator_bid or snapshot.creator_bid or "")
    snapshot.user_bid = str(user_bid or snapshot.user_bid or "")
    snapshot.shifu_bid = str(shifu_bid or snapshot.shifu_bid or "")
    snapshot.provider_attempt_id = str(
        provider_attempt_id or snapshot.provider_attempt_id or ""
    )
    snapshot.transaction_id = str(transaction_id or snapshot.transaction_id or "")
    snapshot.channel = str(channel or snapshot.channel or "")
    snapshot.amount = int(amount or snapshot.amount or 0)
    snapshot.currency = str(currency or snapshot.currency or "CNY")
    snapshot.status = int(raw_snapshot_status)
    snapshot.raw_status = str(raw_status or snapshot.raw_status or "")

    if raw_request is not None:
        snapshot.raw_request = _stringify_payload(raw_request)
    elif not snapshot.raw_request:
        snapshot.raw_request = "{}"
    if raw_response is not None:
        snapshot.raw_response = _stringify_payload(raw_response)
    elif not snapshot.raw_response:
        snapshot.raw_response = "{}"
    if raw_notification is not None:
        snapshot.raw_notification = _stringify_payload(raw_notification)
    elif not snapshot.raw_notification:
        snapshot.raw_notification = "{}"

    if metadata is not None:
        existing_metadata = _parse_json_payload(snapshot.metadata_json)
        if isinstance(existing_metadata, dict) and isinstance(metadata, dict):
            snapshot.metadata_json = _stringify_payload(
                {
                    **existing_metadata,
                    **metadata,
                }
            )
        else:
            snapshot.metadata_json = _stringify_payload(metadata)
    elif not snapshot.metadata_json:
        snapshot.metadata_json = "{}"

    return snapshot


def upsert_billing_stripe_snapshot(
    *,
    bill_order_bid: str,
    creator_bid: str,
    amount: int,
    currency: str,
    raw_status: int,
    metadata: Any | None = None,
    checkout_session_id: str = "",
    checkout_object: Any | None = None,
    payment_intent_id: str = "",
    payment_object: Any | None = None,
    latest_charge_id: str = "",
    receipt_url: str = "",
    payment_method: str = "",
) -> StripeOrder:
    snapshot = (
        billing_stripe_snapshot_query()
        .filter(StripeOrder.bill_order_bid == bill_order_bid)
        .order_by(StripeOrder.id.desc())
        .first()
    )
    if snapshot is None:
        snapshot = StripeOrder(
            stripe_order_bid=bill_order_bid,
            biz_domain=RAW_BIZ_DOMAIN_BILLING,
            bill_order_bid=bill_order_bid,
            creator_bid=creator_bid,
            user_bid="",
            shifu_bid="",
            order_bid="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )

    snapshot.biz_domain = RAW_BIZ_DOMAIN_BILLING
    snapshot.stripe_order_bid = bill_order_bid
    snapshot.bill_order_bid = bill_order_bid
    snapshot.creator_bid = creator_bid
    snapshot.order_bid = ""
    snapshot.user_bid = ""
    snapshot.shifu_bid = ""
    snapshot.amount = int(amount or 0)
    snapshot.currency = str(currency or snapshot.currency or "usd")
    snapshot.status = int(raw_status)
    snapshot.latest_charge_id = latest_charge_id or snapshot.latest_charge_id
    snapshot.receipt_url = receipt_url or snapshot.receipt_url
    snapshot.payment_method = payment_method or snapshot.payment_method

    resolved_checkout_session_id = checkout_session_id or _extract_object_id(
        checkout_object, prefix="cs_"
    )
    if resolved_checkout_session_id:
        snapshot.checkout_session_id = resolved_checkout_session_id

    resolved_payment_intent_id = payment_intent_id or _extract_object_id(
        payment_object, prefix="pi_"
    )
    if resolved_payment_intent_id:
        snapshot.payment_intent_id = resolved_payment_intent_id

    if metadata is not None:
        existing_metadata = _parse_json_payload(snapshot.metadata_json)
        if isinstance(existing_metadata, dict) and isinstance(metadata, dict):
            snapshot.metadata_json = _stringify_payload(
                {
                    **existing_metadata,
                    **metadata,
                }
            )
        else:
            snapshot.metadata_json = _stringify_payload(metadata)

    if checkout_object is not None:
        snapshot.checkout_session_object = _stringify_payload(checkout_object)
    elif not snapshot.checkout_session_object:
        snapshot.checkout_session_object = "{}"

    if payment_object is not None:
        snapshot.payment_intent_object = _stringify_payload(payment_object)
    elif not snapshot.payment_intent_object:
        snapshot.payment_intent_object = "{}"

    return snapshot


def upsert_billing_pingxx_snapshot(
    *,
    bill_order_bid: str,
    creator_bid: str,
    amount: int,
    currency: str,
    raw_status: int,
    charge_id: str = "",
    charge_object: Any | None = None,
    transaction_no: str = "",
    app_id: str = "",
    channel: str = "",
    subject: str = "",
    body: str = "",
    client_ip: str = "",
    extra: Any | None = None,
) -> PingxxOrder:
    snapshot = (
        billing_pingxx_snapshot_query()
        .filter(PingxxOrder.bill_order_bid == bill_order_bid)
        .order_by(PingxxOrder.id.desc())
        .first()
    )
    if snapshot is None:
        snapshot = PingxxOrder(
            pingxx_order_bid=bill_order_bid,
            biz_domain=RAW_BIZ_DOMAIN_BILLING,
            bill_order_bid=bill_order_bid,
            creator_bid=creator_bid,
            user_bid="",
            shifu_bid="",
            order_bid="",
            extra="{}",
            charge_object="{}",
        )

    payload_charge_id = _extract_object_id(charge_object, prefix="ch_")
    snapshot.biz_domain = RAW_BIZ_DOMAIN_BILLING
    snapshot.pingxx_order_bid = bill_order_bid
    snapshot.bill_order_bid = bill_order_bid
    snapshot.creator_bid = creator_bid
    snapshot.order_bid = ""
    snapshot.user_bid = ""
    snapshot.shifu_bid = ""
    snapshot.amount = int(amount or 0)
    snapshot.currency = str(currency or snapshot.currency or "CNY")
    snapshot.status = int(raw_status)
    snapshot.charge_id = charge_id or payload_charge_id or snapshot.charge_id
    snapshot.transaction_no = (
        transaction_no
        or _extract_order_no(charge_object)
        or snapshot.transaction_no
        or bill_order_bid
    )
    snapshot.app_id = app_id or _extract_pingxx_app_id(charge_object) or snapshot.app_id
    snapshot.channel = (
        channel or _extract_object_value(charge_object, "channel") or snapshot.channel
    )
    snapshot.subject = (
        subject or _extract_object_value(charge_object, "subject") or snapshot.subject
    )
    snapshot.body = (
        body or _extract_object_value(charge_object, "body") or snapshot.body
    )
    snapshot.client_ip = (
        client_ip
        or _extract_object_value(charge_object, "client_ip")
        or snapshot.client_ip
    )

    resolved_extra = extra
    if resolved_extra is None and isinstance(charge_object, dict):
        resolved_extra = charge_object.get("extra")
    if resolved_extra is not None:
        snapshot.extra = _stringify_payload(resolved_extra)
    elif not snapshot.extra:
        snapshot.extra = "{}"

    if charge_object is not None:
        snapshot.charge_object = _stringify_payload(charge_object)
    elif not snapshot.charge_object:
        snapshot.charge_object = "{}"

    return snapshot


def _extract_object_id(payload: Any, *, prefix: str) -> str:
    if not isinstance(payload, dict):
        return ""
    value = str(payload.get("id") or "")
    if value.startswith(prefix):
        return value
    return ""


def _extract_order_no(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("order_no") or "")


def _extract_pingxx_app_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("app")
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def _extract_object_value(payload: Any, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get(key) or "")


def _parse_json_payload(value: Any) -> Any:
    if not value:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _stringify_payload(payload: Any) -> str:
    if not payload:
        return "{}"
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload)
