"""Billing purchase notification orchestration helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Flask

from flaskr.api.doc.feishu import send_notify
from flaskr.api.sms.aliyun import send_sms_ali
from flaskr.dao import db
from flaskr.i18n import _ as translate
from flaskr.i18n import get_current_language, set_language
from flaskr.service.user.models import UserConversion
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.timezone import format_with_app_timezone

from .consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from .models import BillingOrder, BillingProduct, BillingSubscription
from .primitives import normalize_bid as _normalize_bid
from .queries import (
    extract_resolved_order_cycle_end_at as _extract_resolved_order_cycle_end_at,
    load_subscription_by_bid as _load_subscription_by_bid,
)

TASK_NAME = "billing.send_subscription_purchase_sms"
BILLING_PAID_FEISHU_TASK_NAME = "billing.send_billing_paid_feishu"
_NOTIFICATIONS_KEY = "notifications"
_SUBSCRIPTION_PURCHASE_SMS_KEY = "subscription_purchase_sms"
_BILLING_PAID_FEISHU_KEY = "billing_paid_feishu"
_PROCESSABLE_STATUSES = {"pending", "failed_provider"}
_SUPPORTED_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
}
_SUPPORTED_FEISHU_ORDER_TYPES = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
}
_FEISHU_CHANNEL_LABELS = {
    "pingxx": "用户购买 (Pingxx)",
    "stripe": "用户购买 (Stripe)",
    "alipay": "用户购买 (支付宝)",
    "wechatpay": "用户购买 (微信支付)",
    "manual": "手动导入",
    "open_api": "Open API",
}
_FEISHU_ORDER_TYPE_LABELS = {
    BILLING_ORDER_TYPE_SUBSCRIPTION_START: "订阅开通",
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE: "订阅升级",
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL: "订阅续费",
    BILLING_ORDER_TYPE_TOPUP: "积分包",
}
_COUNTED_SUBSCRIPTION_STATUSES = {
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
}


def _build_result(
    status: str,
    *,
    bill_order_bid: str | None = None,
    creator_bid: str | None = None,
    mobile: str | None = None,
    product: str | None = None,
    date: str | None = None,
    message: str | None = None,
    notification_status: str | None = None,
    enqueued: bool | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "bill_order_bid": bill_order_bid,
        "creator_bid": creator_bid,
        "mobile": mobile,
        "product": product,
        "date": date,
        "notification_status": notification_status,
        "task_name": TASK_NAME,
    }
    if message is not None:
        payload["message"] = message
    if enqueued is not None:
        payload["enqueued"] = enqueued
    return payload


def _supports_subscription_purchase_sms(order: BillingOrder | None) -> bool:
    if order is None:
        return False
    return int(order.order_type or 0) in _SUPPORTED_ORDER_TYPES


def _read_order_metadata(order: BillingOrder) -> dict[str, Any]:
    if isinstance(order.metadata_json, dict):
        return deepcopy(order.metadata_json)
    return {}


def _read_notification_payload_by_key(
    order: BillingOrder,
    notification_key: str,
) -> dict[str, Any]:
    metadata = _read_order_metadata(order)
    notifications = metadata.get(_NOTIFICATIONS_KEY)
    if not isinstance(notifications, dict):
        return {}
    payload = notifications.get(notification_key)
    if not isinstance(payload, dict):
        return {}
    return dict(payload)


def _write_notification_payload_by_key(
    order: BillingOrder,
    notification_key: str,
    payload: dict[str, Any],
) -> None:
    metadata = _read_order_metadata(order)
    notifications = metadata.get(_NOTIFICATIONS_KEY)
    if not isinstance(notifications, dict):
        notifications = {}
    notifications[notification_key] = dict(payload)
    metadata[_NOTIFICATIONS_KEY] = notifications
    order.metadata_json = metadata


def _read_notification_payload(order: BillingOrder) -> dict[str, Any]:
    return _read_notification_payload_by_key(order, _SUBSCRIPTION_PURCHASE_SMS_KEY)


def _write_notification_payload(
    order: BillingOrder,
    payload: dict[str, Any],
) -> None:
    _write_notification_payload_by_key(
        order,
        _SUBSCRIPTION_PURCHASE_SMS_KEY,
        payload,
    )


def stage_subscription_purchase_sms_for_paid_order(
    order: BillingOrder,
    *,
    previous_status: int | None,
) -> bool:
    """Mark one newly paid subscription order as pending SMS delivery."""

    if not _supports_subscription_purchase_sms(order):
        return False
    if int(order.status or 0) != BILLING_ORDER_STATUS_PAID:
        return False
    if int(previous_status or 0) == BILLING_ORDER_STATUS_PAID:
        return False

    payload = _read_notification_payload(order)
    current_status = _normalize_bid(payload.get("status"))
    if current_status:
        return False

    now = datetime.now().isoformat()
    payload["status"] = "pending"
    payload["requested_at"] = now
    payload["updated_at"] = now
    _write_notification_payload(order, payload)
    return True


def _supports_billing_paid_feishu(order: BillingOrder | None) -> bool:
    if order is None:
        return False
    if int(order.order_type or 0) not in _SUPPORTED_FEISHU_ORDER_TYPES:
        return False
    if int(order.status or 0) != BILLING_ORDER_STATUS_PAID:
        return False
    paid_amount = int(order.paid_amount or 0)
    payable_amount = int(order.payable_amount or 0)
    return max(paid_amount, payable_amount) > 0


def stage_billing_paid_feishu_for_paid_order(
    order: BillingOrder,
    *,
    previous_status: int | None,
) -> bool:
    """Mark one newly paid billing order as pending Feishu delivery."""

    if not _supports_billing_paid_feishu(order):
        return False
    if int(previous_status or 0) == BILLING_ORDER_STATUS_PAID:
        return False

    payload = _read_notification_payload_by_key(order, _BILLING_PAID_FEISHU_KEY)
    current_status = _normalize_bid(payload.get("status"))
    if current_status:
        return False

    now = datetime.now().isoformat()
    payload["status"] = "pending"
    payload["requested_at"] = now
    payload["updated_at"] = now
    _write_notification_payload_by_key(order, _BILLING_PAID_FEISHU_KEY, payload)
    return True


def enqueue_subscription_purchase_sms(
    app: Flask,
    *,
    bill_order_bid: str,
) -> dict[str, Any]:
    """Enqueue the subscription purchase SMS worker after commit."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        return _build_result(
            "invalid_bill_order_bid",
            enqueued=False,
        )

    try:
        from flaskr.common.celery_app import get_celery_app

        celery_app = get_celery_app(flask_app=app)
        task = celery_app.tasks.get(TASK_NAME)
        if task is None:
            app.logger.warning(
                "%s is unavailable for bill_order_bid=%s",
                TASK_NAME,
                normalized_bill_order_bid,
            )
            return _build_result(
                "task_unavailable",
                bill_order_bid=normalized_bill_order_bid,
                enqueued=False,
            )
        task.apply_async(kwargs={"bill_order_bid": normalized_bill_order_bid})
        return _build_result(
            "enqueued",
            bill_order_bid=normalized_bill_order_bid,
            enqueued=True,
        )
    except Exception as exc:
        app.logger.error(
            "Failed to enqueue %s for bill_order_bid=%s: %s",
            TASK_NAME,
            normalized_bill_order_bid,
            exc,
            exc_info=True,
        )
        return _build_result(
            "enqueue_failed",
            bill_order_bid=normalized_bill_order_bid,
            message=str(exc),
            enqueued=False,
        )


def requeue_subscription_purchase_sms(
    app: Flask,
    *,
    bill_order_bid: str,
) -> dict[str, Any]:
    """Re-enqueue one pending or provider-failed subscription purchase SMS."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        return _build_result("invalid_bill_order_bid", enqueued=False)

    with app.app_context():
        order = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == normalized_bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if order is None:
            return _build_result(
                "not_found",
                bill_order_bid=normalized_bill_order_bid,
                enqueued=False,
            )

        payload = _read_notification_payload(order)
        notification_status = _normalize_bid(payload.get("status"))
        if notification_status not in _PROCESSABLE_STATUSES:
            return _build_result(
                "not_requeueable",
                bill_order_bid=normalized_bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status=notification_status or None,
                enqueued=False,
            )

    result = enqueue_subscription_purchase_sms(
        app,
        bill_order_bid=normalized_bill_order_bid,
    )
    result["creator_bid"] = order.creator_bid
    result["notification_status"] = notification_status
    return result


def _resolve_notification_order(
    bill_order_bid: str,
) -> BillingOrder | None:
    return (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.bill_order_bid == bill_order_bid,
        )
        .order_by(BillingOrder.id.desc())
        .with_for_update()
        .first()
    )


def _resolve_notification_product_name(
    order: BillingOrder,
    *,
    language: str,
) -> str:
    product = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == order.product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )
    if product is None:
        return _normalize_bid(order.product_bid) or _normalize_bid(order.bill_order_bid)

    display_name_key = _normalize_bid(product.display_name_i18n_key)
    original_language = get_current_language()
    try:
        if language:
            set_language(language)
        translated_name = ""
        if display_name_key:
            translated_name = str(translate(display_name_key) or "").strip()
            if translated_name == display_name_key:
                translated_name = ""
        return (
            translated_name
            or _normalize_bid(product.product_code)
            or product.product_bid
        )
    finally:
        set_language(original_language)


def _resolve_notification_date_text(
    app: Flask,
    order: BillingOrder,
) -> str:
    subscription = (
        _load_subscription_by_bid(order.subscription_bid)
        if _normalize_bid(order.subscription_bid)
        else None
    )
    expiry_at = (
        subscription.current_period_end_at if subscription is not None else None
    ) or _extract_resolved_order_cycle_end_at(order.metadata_json)
    if expiry_at is None:
        return ""
    return (
        format_with_app_timezone(
            app,
            expiry_at,
            "%Y-%m-%d %H:%M:%S",
        )
        or ""
    )


def _build_feishu_result(
    status: str,
    *,
    bill_order_bid: str | None = None,
    creator_bid: str | None = None,
    message: str | None = None,
    notification_status: str | None = None,
    enqueued: bool | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "bill_order_bid": bill_order_bid,
        "creator_bid": creator_bid,
        "notification_status": notification_status,
        "notification": _BILLING_PAID_FEISHU_KEY,
        "task_name": BILLING_PAID_FEISHU_TASK_NAME,
    }
    if message is not None:
        payload["message"] = message
    if enqueued is not None:
        payload["enqueued"] = enqueued
    return payload


def enqueue_billing_paid_feishu(
    app: Flask,
    *,
    bill_order_bid: str,
) -> dict[str, Any]:
    """Enqueue the billing paid Feishu worker after commit."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        return _build_feishu_result(
            "invalid_bill_order_bid",
            enqueued=False,
        )

    try:
        from flaskr.common.celery_app import get_celery_app

        celery_app = get_celery_app(flask_app=app)
        task = celery_app.tasks.get(BILLING_PAID_FEISHU_TASK_NAME)
        if task is None:
            app.logger.warning(
                "%s is unavailable for bill_order_bid=%s",
                BILLING_PAID_FEISHU_TASK_NAME,
                normalized_bill_order_bid,
            )
            return _build_feishu_result(
                "task_unavailable",
                bill_order_bid=normalized_bill_order_bid,
                enqueued=False,
            )
        task.apply_async(kwargs={"bill_order_bid": normalized_bill_order_bid})
        return _build_feishu_result(
            "enqueued",
            bill_order_bid=normalized_bill_order_bid,
            enqueued=True,
        )
    except Exception as exc:
        app.logger.error(
            "Failed to enqueue %s for bill_order_bid=%s: %s",
            BILLING_PAID_FEISHU_TASK_NAME,
            normalized_bill_order_bid,
            exc,
            exc_info=True,
        )
        return _build_feishu_result(
            "enqueue_failed",
            bill_order_bid=normalized_bill_order_bid,
            message=str(exc),
            enqueued=False,
        )


def _load_notification_product(order: BillingOrder) -> BillingProduct | None:
    return (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid == order.product_bid,
        )
        .order_by(BillingProduct.id.desc())
        .first()
    )


def _format_minor_currency_amount(currency: str | None, amount: Any) -> str:
    try:
        major_amount = Decimal(str(amount or 0)) / Decimal("100")
    except (InvalidOperation, TypeError, ValueError):
        major_amount = Decimal("0")
    return f"{_normalize_bid(currency) or 'CNY'} {major_amount:.2f}"


def _format_credit_amount(amount: Any) -> str:
    try:
        credit_amount = Decimal(str(amount or 0))
    except (InvalidOperation, TypeError, ValueError):
        credit_amount = Decimal("0")
    if credit_amount == credit_amount.to_integral_value():
        return str(int(credit_amount))
    return format(credit_amount.normalize(), "f").rstrip("0").rstrip(".")


def _resolve_feishu_channel_label(order: BillingOrder) -> str:
    provider = _normalize_bid(order.payment_provider)
    if provider in _FEISHU_CHANNEL_LABELS:
        return _FEISHU_CHANNEL_LABELS[provider]
    channel = _normalize_bid(order.channel)
    return channel or "未知"


def _resolve_user_conversion_source(user_bid: str) -> str:
    user_convertion = UserConversion.query.filter(
        UserConversion.user_id == user_bid
    ).first()
    if user_convertion:
        return _normalize_bid(user_convertion.conversion_source)
    return ""


def _append_subscription_user_count_line(msgs: list[str]) -> None:
    now = datetime.now()
    subscription_user_count = (
        BillingSubscription.query.with_entities(BillingSubscription.creator_bid)
        .join(
            BillingProduct,
            (BillingProduct.product_bid == BillingSubscription.product_bid)
            & (BillingProduct.deleted == 0),
        )
        .filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid != "",
            BillingSubscription.status.in_(_COUNTED_SUBSCRIPTION_STATUSES),
            BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
            BillingProduct.price_amount > 0,
            (
                BillingSubscription.current_period_start_at.is_(None)
                | (BillingSubscription.current_period_start_at <= now)
            ),
            BillingSubscription.current_period_end_at.isnot(None),
            BillingSubscription.current_period_end_at > now,
        )
        .distinct()
        .count()
    )
    msgs.append("订阅用户数：{}".format(subscription_user_count))


def _build_billing_paid_feishu_message(
    app: Flask,
    order: BillingOrder,
    *,
    aggregate: Any,
    product: BillingProduct | None,
    product_name: str,
) -> tuple[str, list[str]]:
    order_type = int(order.order_type or 0)
    is_topup = order_type == BILLING_ORDER_TYPE_TOPUP
    title = "购买积分包通知" if is_topup else "购买订阅套餐通知"
    product_label = "积分包名称" if is_topup else "套餐名称"
    order_type_label = _FEISHU_ORDER_TYPE_LABELS.get(order_type, "订单")
    amount_text = _format_minor_currency_amount(
        order.currency,
        order.paid_amount or order.payable_amount,
    )

    msgs = [
        "手机号：{}".format(getattr(aggregate, "mobile", "")),
        "昵称：{}".format(getattr(aggregate, "name", "")),
        "{}：{}".format(product_label, product_name),
        "实付金额：{}".format(amount_text),
        "订单来源：{}".format(_resolve_feishu_channel_label(order)),
        "渠道：{}".format(_resolve_user_conversion_source(order.creator_bid)),
        "{}-{}-{}".format(order_type_label, product_name, amount_text),
    ]
    if product is not None:
        msgs.append("积分数量：{}".format(_format_credit_amount(product.credit_amount)))
    paid_at_text = format_with_app_timezone(
        app,
        order.paid_at,
        "%Y-%m-%d %H:%M:%S",
    )
    if paid_at_text:
        msgs.append("支付时间：{}".format(paid_at_text))
    msgs.append("订单号：{}".format(order.bill_order_bid))
    _append_subscription_user_count_line(msgs)
    return title, msgs


def _finalize_billing_paid_feishu_notification(
    order: BillingOrder,
    *,
    status: str,
    now: datetime,
    error_code: str = "",
    error_message: str = "",
) -> None:
    payload = _read_notification_payload_by_key(order, _BILLING_PAID_FEISHU_KEY)
    payload["status"] = status
    payload["updated_at"] = now.isoformat()
    payload["processed_at"] = now.isoformat()
    if status == "sent":
        payload["sent_at"] = now.isoformat()
        payload.pop("error_code", None)
        payload.pop("error_message", None)
    else:
        if error_code:
            payload["error_code"] = error_code
        if error_message:
            payload["error_message"] = error_message
    _write_notification_payload_by_key(order, _BILLING_PAID_FEISHU_KEY, payload)


def _finalize_notification(
    order: BillingOrder,
    *,
    status: str,
    now: datetime,
    error_code: str = "",
    error_message: str = "",
) -> None:
    payload = _read_notification_payload(order)
    payload["status"] = status
    payload["updated_at"] = now.isoformat()
    payload["processed_at"] = now.isoformat()
    if status == "sent":
        payload["sent_at"] = now.isoformat()
        payload.pop("error_code", None)
        payload.pop("error_message", None)
    else:
        if error_code:
            payload["error_code"] = error_code
        if error_message:
            payload["error_message"] = error_message
    _write_notification_payload(order, payload)


def deliver_billing_paid_feishu(
    app: Flask,
    *,
    bill_order_bid: str,
) -> dict[str, Any]:
    """Send one billing paid Feishu notification if the order is pending."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        return _build_feishu_result("invalid_bill_order_bid")

    with app.app_context():
        order = _resolve_notification_order(normalized_bill_order_bid)
        if order is None:
            return _build_feishu_result(
                "not_found",
                bill_order_bid=normalized_bill_order_bid,
            )

        payload = _read_notification_payload_by_key(
            order,
            _BILLING_PAID_FEISHU_KEY,
        )
        notification_status = _normalize_bid(payload.get("status"))
        if notification_status not in _PROCESSABLE_STATUSES:
            return _build_feishu_result(
                "noop",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status=notification_status or None,
            )

        if not _supports_billing_paid_feishu(order):
            now = datetime.now()
            _finalize_billing_paid_feishu_notification(
                order,
                status="skipped_unsupported",
                now=now,
                error_code="unsupported_order",
                error_message="Billing order is not a paid subscription or topup.",
            )
            db.session.add(order)
            db.session.commit()
            return _build_feishu_result(
                "skipped_unsupported",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status="skipped_unsupported",
            )

        aggregate = load_user_aggregate(order.creator_bid)
        if not aggregate:
            app.logger.warning(
                "billing paid feishu notify skipped: user aggregate missing for %s",
                order.creator_bid,
            )
            now = datetime.now()
            _finalize_billing_paid_feishu_notification(
                order,
                status="skipped_missing_user",
                now=now,
                error_code="missing_user",
                error_message="Creator aggregate is missing.",
            )
            db.session.add(order)
            db.session.commit()
            return _build_feishu_result(
                "skipped_missing_user",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status="skipped_missing_user",
            )

        product = _load_notification_product(order)
        product_name = _resolve_notification_product_name(order, language="zh-CN")
        title, msgs = _build_billing_paid_feishu_message(
            app,
            order,
            aggregate=aggregate,
            product=product,
            product_name=product_name,
        )
        now = datetime.now()
        payload["status"] = "processing"
        payload["attempted_at"] = now.isoformat()
        payload["updated_at"] = now.isoformat()
        _write_notification_payload_by_key(order, _BILLING_PAID_FEISHU_KEY, payload)
        db.session.add(order)
        db.session.commit()

    response = None
    provider_error_message = ""
    try:
        with app.app_context():
            response = send_notify(app, title, msgs)
    except Exception as exc:
        provider_error_message = str(exc)
        app.logger.error(
            "Billing paid Feishu provider failed for bill_order_bid=%s: %s",
            normalized_bill_order_bid,
            exc,
            exc_info=True,
        )

    with app.app_context():
        order = _resolve_notification_order(normalized_bill_order_bid)
        if order is None:
            return _build_feishu_result(
                "not_found",
                bill_order_bid=normalized_bill_order_bid,
            )

        now = datetime.now()
        if response is not None:
            _finalize_billing_paid_feishu_notification(
                order,
                status="sent",
                now=now,
            )
            db.session.add(order)
            db.session.commit()
            return _build_feishu_result(
                "sent",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status="sent",
            )

        error_message = (
            provider_error_message
            or "Feishu notification provider returned no response."
        )
        _finalize_billing_paid_feishu_notification(
            order,
            status="failed_provider",
            now=now,
            error_code="provider_failed",
            error_message=error_message,
        )
        db.session.add(order)
        db.session.commit()
        return _build_feishu_result(
            "failed_provider",
            bill_order_bid=order.bill_order_bid,
            creator_bid=order.creator_bid,
            message=error_message,
            notification_status="failed_provider",
        )


def deliver_subscription_purchase_sms(
    app: Flask,
    *,
    bill_order_bid: str,
) -> dict[str, Any]:
    """Send one subscription purchase SMS if the billing order is pending."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        return _build_result("invalid_bill_order_bid")

    with app.app_context():
        order = _resolve_notification_order(normalized_bill_order_bid)
        if order is None:
            return _build_result(
                "not_found",
                bill_order_bid=normalized_bill_order_bid,
            )

        payload = _read_notification_payload(order)
        notification_status = _normalize_bid(payload.get("status"))
        if notification_status not in _PROCESSABLE_STATUSES:
            return _build_result(
                "noop",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                notification_status=notification_status or None,
            )

        aggregate = load_user_aggregate(order.creator_bid)
        mobile = _normalize_bid(getattr(aggregate, "mobile", ""))
        language = _normalize_bid(getattr(aggregate, "user_language", ""))
        product_name = _resolve_notification_product_name(order, language=language)
        date_text = _resolve_notification_date_text(app, order)
        now = datetime.now()

        if not mobile:
            _finalize_notification(
                order,
                status="skipped_no_mobile",
                now=now,
                error_code="missing_mobile",
                error_message="Creator mobile is empty.",
            )
            db.session.add(order)
            db.session.commit()
            return _build_result(
                "skipped_no_mobile",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                product=product_name,
                notification_status="skipped_no_mobile",
            )

        if not date_text:
            _finalize_notification(
                order,
                status="failed_missing_date",
                now=now,
                error_code="missing_date",
                error_message="Subscription expiry date could not be resolved.",
            )
            db.session.add(order)
            db.session.commit()
            return _build_result(
                "failed_missing_date",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                mobile=mobile,
                product=product_name,
                notification_status="failed_missing_date",
            )

        payload["status"] = "processing"
        payload["attempted_at"] = now.isoformat()
        payload["updated_at"] = now.isoformat()
        _write_notification_payload(order, payload)
        db.session.add(order)
        db.session.commit()

    response = None
    provider_error_message = ""
    try:
        response = send_sms_ali(
            app,
            mobile,
            template_code=app.config.get(
                "ALIBABA_CLOUD_SMS_SUBSCRIPTION_SUCCESS_TEMPLATE_CODE",
                "",
            ),
            template_params={"product": product_name, "date": date_text},
        )
    except Exception as exc:  # pragma: no cover - guarded by send_sms_ali
        provider_error_message = str(exc)
        app.logger.error(
            "Subscription purchase SMS provider failed for bill_order_bid=%s: %s",
            normalized_bill_order_bid,
            exc,
            exc_info=True,
        )

    with app.app_context():
        order = _resolve_notification_order(normalized_bill_order_bid)
        if order is None:
            return _build_result(
                "not_found",
                bill_order_bid=normalized_bill_order_bid,
                mobile=mobile or None,
                product=product_name,
                date=date_text,
            )

        now = datetime.now()
        if response is not None:
            _finalize_notification(order, status="sent", now=now)
            db.session.add(order)
            db.session.commit()
            return _build_result(
                "sent",
                bill_order_bid=order.bill_order_bid,
                creator_bid=order.creator_bid,
                mobile=mobile,
                product=product_name,
                date=date_text,
                notification_status="sent",
            )

        error_message = (
            provider_error_message or "Aliyun SMS provider returned no response."
        )
        _finalize_notification(
            order,
            status="failed_provider",
            now=now,
            error_code="provider_failed",
            error_message=error_message,
        )
        db.session.add(order)
        db.session.commit()
        return _build_result(
            "failed_provider",
            bill_order_bid=order.bill_order_bid,
            creator_bid=order.creator_bid,
            mobile=mobile,
            product=product_name,
            date=date_text,
            message=error_message,
            notification_status="failed_provider",
        )
