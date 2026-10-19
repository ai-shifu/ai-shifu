"""Create provider charges for legacy orders and resolve their payment channel."""

from contextlib import AbstractContextManager, nullcontext
from typing import Any

from flask import Flask
from flaskr.common.public_urls import build_stripe_learner_result_url
from flaskr.dao import db
from flaskr.service.billing.api import (
    build_provider_config_overrides,
    resolve_provider_credential_context,
)
from flaskr.service.common.models import raise_error
from flaskr.service.config import config_overrides
from flaskr.service.learn.learn_dtos import LearnShifuInfoDTO
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
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
from flaskr.service.order.payment_channel_resolution import (
    resolve_payment_channel,
)
from flaskr.service.order.payment_lifecycle import (
    _assert_payment_lifecycle_lock_owned,
)
from flaskr.service.order.payment_payloads import (
    _format_response_channel,
    _inject_order_query,
    _sanitize_pingxx_text,
    _stringify_payload,
)
from flaskr.service.order.payment_providers import PaymentRequest
from flaskr.service.order.raw_snapshots import (
    RAW_BIZ_DOMAIN_ORDER,
)


def _order_credential_scope(
    app: Flask, order: Order, context: object = None
) -> AbstractContextManager[None]:
    """Use the immutable credential version snapshotted on the order."""
    integration_bid = str(order.payment_integration_bid or "")
    if not integration_bid:
        return nullcontext()
    context = context or resolve_provider_credential_context(
        app,
        creator_bid=str(order.creator_bid or ""),
        provider=str(order.payment_channel or ""),
        integration_bid=integration_bid,
    )
    if context is None or context.integration_bid != integration_bid:
        raise_error("server.pay.payChannelNotSupport")
    return config_overrides(build_provider_config_overrides(context))


def _resolve_payment_channel(
    *,
    payment_channel_hint: str | None,
    channel_hint: str | None,
    stored_channel: str | None,
    additional_enabled_providers: set[str] | None = None,
) -> tuple[str, str]:
    """Resolve the provider and provider-specific channel based on hints."""
    return resolve_payment_channel(
        payment_channel_hint=payment_channel_hint,
        channel_hint=channel_hint,
        stored_channel=stored_channel,
        additional_enabled_providers=additional_enabled_providers,
    )


def assign_free_order_payment_channel(order: Order) -> None:
    """Attribute a free order to the market provider without creating a charge."""
    recorded_channel = str(order.payment_channel or "").strip()
    if recorded_channel in {"manual", "open_api"} or (
        order.status != ORDER_STATUS_INIT
        and recorded_channel in {"stripe", "alipay", "wechatpay"}
    ):
        return
    order.payment_channel = order_funs.resolve_market_payment_provider()


def _resolve_custom_payment_provider_hints(creator_bid: str) -> set[str]:
    if not creator_bid:
        return set()
    try:
        public_integrations = order_funs.resolve_creator_public_integrations(
            creator_bid
        )
    except Exception:
        from flask import current_app

        current_app.logger.warning(
            "failed to resolve custom payment providers; creator_bid=%s",
            creator_bid,
            exc_info=True,
        )
        return set()
    return {
        provider
        for provider in ("alipay", "wechatpay")
        if provider in public_integrations
    }


def _resolve_charge_wechat_app_id(app: Flask, creator_bid: str) -> str:
    """Return the WeChat app whose open ID this order must be charged with.

    Learners of a creator running their own official account hold an open ID
    scoped to that app, and WeChat rejects an open ID issued by a different one.
    The creator comes from the order rather than the request-scoped shifu
    context, which this endpoint does not set up. A creator without a WeChat
    integration -- or a lookup that fails -- means the platform app, which is
    also the safe answer for a money flow: never a new failure path.
    """
    if not creator_bid:
        return ""
    try:
        return order_funs.resolve_creator_wechat_oauth_app_id(creator_bid)
    except Exception:
        app.logger.warning(
            "failed to resolve creator WeChat app; creator_bid=%s",
            creator_bid,
            exc_info=True,
        )
        return ""


def _generate_pingxx_charge(
    *,
    app: Flask,
    buy_record: Order,
    course: LearnShifuInfoDTO,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
) -> BuyRecordDTO:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    provider = order_funs.get_payment_provider("pingxx")
    pingpp_id = order_funs.get_config("PINGXX_APP_ID")
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
        user = order_funs.load_user_aggregate(buy_record.user_bid)
        wechat_app_id = order_funs._resolve_charge_wechat_app_id(
            app, str(buy_record.creator_bid or "")
        )
        open_id = (
            str(user.wechat_open_id_for_app(wechat_app_id) or "").strip()
            if user
            else ""
        )
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
    _assert_payment_lifecycle_lock_owned()
    result = provider.create_payment(request=payment_request, app=app)
    charge = result.raw_response
    credential = charge.get("credential", {}) or {}
    qr_url = credential.get(qr_url_key) if qr_url_key else ""
    app.logger.info("Pingxx charge created:%s", charge)

    buy_record.status = ORDER_STATUS_TO_BE_PAID
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
    return BuyRecordDTO(
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
    course: LearnShifuInfoDTO,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
) -> BuyRecordDTO:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    _ = course
    provider = order_funs.get_payment_provider("stripe")
    resolved_mode = channel.lower() if channel else "payment_intent"
    if resolved_mode in {"checkout", "checkout_session"}:
        resolved_mode = "checkout_session"
    else:
        resolved_mode = "payment_intent"

    currency = order_funs.get_config("STRIPE_DEFAULT_CURRENCY", "usd")
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
    _assert_payment_lifecycle_lock_owned()
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
    buy_record.status = ORDER_STATUS_TO_BE_PAID

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

    return BuyRecordDTO(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        response_channel,
        qr_value,
        payment_channel="stripe",
        payment_payload=payment_payload,
    )


def _generate_alipay_charge(
    *,
    app: Flask,
    buy_record: Order,
    course: LearnShifuInfoDTO,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
) -> BuyRecordDTO:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    provider = order_funs.get_payment_provider("alipay")
    sanitized_subject = _sanitize_pingxx_text(
        subject,
        fallback=course.title or "订单支付",
        max_length=64,
    )
    sanitized_body = _sanitize_pingxx_text(
        body,
        fallback=sanitized_subject,
        max_length=128,
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
        extra={
            "metadata": {
                "order_bid": buy_record.order_bid,
                "user_bid": buy_record.user_bid,
                "shifu_bid": buy_record.shifu_bid,
            }
        },
    )
    _assert_payment_lifecycle_lock_owned()
    result = provider.create_payment(request=payment_request, app=app)
    credential = result.extra.get("credential", {}) or {}
    qr_url = str(result.extra.get("qr_url") or credential.get("alipay_qr") or "")

    buy_record.status = ORDER_STATUS_TO_BE_PAID
    snapshot = order_funs.upsert_native_snapshot(
        biz_domain=RAW_BIZ_DOMAIN_ORDER,
        payment_provider="alipay",
        native_payment_order_bid=order_no,
        provider_attempt_id=str(result.provider_reference or order_no),
        order_bid=buy_record.order_bid,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        currency="CNY",
        raw_status="pending",
        raw_snapshot_status=0,
        channel=channel,
        raw_request=result.extra.get("raw_request") or {},
        raw_response=result.raw_response,
        metadata={
            "course_bid": course.bid,
            "subject": sanitized_subject,
            "body": sanitized_body,
        },
    )
    db.session.add(snapshot)
    return BuyRecordDTO(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        channel,
        qr_url,
        payment_channel="alipay",
        payment_payload={
            "qr_url": qr_url,
            "credential": credential,
        },
    )


def _generate_wechatpay_charge(
    *,
    app: Flask,
    buy_record: Order,
    course: LearnShifuInfoDTO,
    channel: str,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
) -> BuyRecordDTO:
    """Boundary-joining helper: committed by generate_charge's unit of work."""
    provider = order_funs.get_payment_provider("wechatpay")
    sanitized_subject = _sanitize_pingxx_text(
        subject,
        fallback=course.title or "订单支付",
        max_length=127,
    )
    sanitized_body = _sanitize_pingxx_text(
        body,
        fallback=sanitized_subject,
        max_length=127,
    )
    extra: dict[str, Any] = {
        "metadata": {
            "order_bid": buy_record.order_bid,
            "user_bid": buy_record.user_bid,
            "shifu_bid": buy_record.shifu_bid,
        }
    }
    if channel == "wx_pub":
        user = order_funs.load_user_aggregate(buy_record.user_bid)
        wechat_app_id = order_funs._resolve_charge_wechat_app_id(
            app, str(buy_record.creator_bid or "")
        )
        open_id = (
            str(user.wechat_open_id_for_app(wechat_app_id) or "").strip()
            if user
            else ""
        )
        if not open_id:
            raise_error("server.pay.wechatOpenIdRequired")
        extra["open_id"] = open_id

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
    _assert_payment_lifecycle_lock_owned()
    result = provider.create_payment(request=payment_request, app=app)
    credential = result.extra.get("credential", {}) or {}
    qr_url = str(result.extra.get("qr_url") or credential.get("wx_pub_qr") or "")

    buy_record.status = ORDER_STATUS_TO_BE_PAID
    metadata = {
        "course_bid": course.bid,
        "subject": sanitized_subject,
        "body": sanitized_body,
    }
    if result.extra.get("prepay_id"):
        metadata["prepay_id"] = result.extra.get("prepay_id")
    snapshot = order_funs.upsert_native_snapshot(
        biz_domain=RAW_BIZ_DOMAIN_ORDER,
        payment_provider="wechatpay",
        native_payment_order_bid=order_no,
        provider_attempt_id=str(result.provider_reference or order_no),
        order_bid=buy_record.order_bid,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        currency="CNY",
        raw_status="pending",
        raw_snapshot_status=0,
        channel=channel,
        raw_request=result.extra.get("raw_request") or {},
        raw_response=result.raw_response,
        metadata=metadata,
    )
    db.session.add(snapshot)

    payment_payload: dict[str, Any] = {
        "qr_url": qr_url,
        "credential": credential,
    }
    if result.extra.get("mode") == "jsapi":
        payment_payload.update(
            {
                "mode": "jsapi",
                "prepay_id": result.extra.get("prepay_id"),
                "jsapi_params": result.extra.get("jsapi_params") or {},
            }
        )

    return BuyRecordDTO(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        channel,
        qr_url,
        payment_channel="wechatpay",
        payment_payload=payment_payload,
    )
