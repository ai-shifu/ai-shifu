import datetime
import decimal
import json
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from flask import Flask

from flaskr.service.config import get_config
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.i18n import _
from flaskr.service.active import (
    query_active_record,
    query_and_join_active,
    query_to_failure_active,
)
from flaskr.service.common.dtos import USER_STATE_PAID, USER_STATE_REGISTERED
from flaskr.service.learn.learn_dtos import LearnShifuInfoDTO
from flaskr.service.learn.learn_funcs import get_shifu_info
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_TO_BE_PAID,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_VALUES,
)
from flaskr.service.order.query_discount import query_discount_record
from flaskr.service.promo.consts import COUPON_TYPE_FIXED, COUPON_TYPE_PERCENT
from flaskr.service.promo.models import Coupon, CouponUsage as CouponUsageModel
from flaskr.service.user.models import UserConversion
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import (
    load_user_aggregate,
    set_user_state,
)
from flaskr.api.doc.feishu import send_notify
from flaskr.service.order.payment_providers import PaymentRequest, get_payment_provider
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundRequest,
)
from flaskr.util.uuid import generate_id as get_uuid
from flaskr.dao import db, redis_client
from flaskr.service.common.models import raise_error
from flaskr.service.order.models import Order, PingxxOrder, StripeOrder
import pytz
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from flaskr.common.shifu_context import set_shifu_context
from flaskr.service.shifu.utils import get_shifu_creator_bid


@register_schema_to_swagger
class AICourseLessonAttendDTO:
    """
    AICourseLessonAttendDTO
    """

    attend_id: str
    lesson_id: str
    course_id: str
    user_id: str
    status: int
    index: int

    def __init__(self, attend_id, lesson_id, course_id, user_id, status, index):
        self.attend_id = attend_id
        self.lesson_id = lesson_id
        self.course_id = course_id
        self.user_id = user_id
        self.status = status
        self.index = index

    def __json__(self):
        return {
            "attend_id": self.attend_id,
            "lesson_id": self.lesson_id,
            "course_id": self.course_id,
            "user_id": self.user_id,
            "status": self.status,
            "index": self.index,
        }


@register_schema_to_swagger
class PayItemDto:
    """
    PayItemDto
    """

    name: str
    price_name: str
    price: str
    is_discount: bool
    discount_code: str

    def __init__(self, name, price_name, price, is_discount, discount_code):
        self.name = name
        self.price_name = price_name
        self.price = price
        self.is_discount = is_discount
        self.discount_code = discount_code

    def __json__(self):
        return {
            "name": self.name,
            "price_name": self.price_name,
            "price": str(self.price),
            "is_discount": self.is_discount,
        }


@register_schema_to_swagger
class AICourseBuyRecordDTO:
    """
    AICourseBuyRecordDTO
    """

    order_id: str
    user_id: str
    course_id: str
    price: decimal.Decimal
    status: int
    discount: str
    active_discount: str
    value_to_pay: str
    price_item: List[PayItemDto]

    def __init__(
        self, record_id, user_id, course_id, price, status, discount, price_item
    ):
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = price
        self.status = status
        self.discount = discount
        self.value_to_pay = str(decimal.Decimal(price) - decimal.Decimal(discount))
        self.price_item = price_item

    def __json__(self):
        def format_decimal(value):
            if isinstance(value, str):
                formatted_value = value  # Convert to string with two decimal places
            else:
                formatted_value = "{0:.2f}".format(value)
            # If the decimal part is .00, remove it
            if formatted_value.endswith(".00"):
                return formatted_value[:-3]
            return formatted_value

        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "course_id": self.course_id,
            "price": format_decimal(self.price),
            "status": self.status,
            "status_desc": ORDER_STATUS_VALUES[self.status],
            "discount": format_decimal(self.discount),
            "value_to_pay": format_decimal(self.value_to_pay),
            "price_item": [item.__json__() for item in self.price_item],
        }


# to do : add to plugins
def send_order_feishu(app: Flask, record_id: str):
    order_info = query_buy_record(app, record_id)
    if order_info is None:
        return
    aggregate = load_user_aggregate(order_info.user_id)
    if not aggregate:
        app.logger.warning(
            "order notify skipped: user aggregate missing for %s",
            order_info.user_id,
        )
        return
    shifu_info: LearnShifuInfoDTO = get_shifu_info(app, order_info.course_id, False)
    if not shifu_info:
        return

    title = "购买课程通知"
    msgs = []
    msgs.append("手机号：{}".format(aggregate.mobile))
    msgs.append("昵称：{}".format(aggregate.name))
    msgs.append("课程名称：{}".format(shifu_info.title))
    msgs.append("实付金额：{}".format(order_info.price))
    user_convertion = UserConversion.query.filter(
        UserConversion.user_id == order_info.user_id
    ).first()
    channel = ""
    if user_convertion:
        channel = user_convertion.conversion_source
    msgs.append("渠道：{}".format(channel))
    for item in order_info.price_item:
        msgs.append("{}-{}-{}".format(item.name, item.price_name, item.price))
        if item.is_discount:
            msgs.append("优惠码：{}".format(item.discount_code))
    user_count = UserEntity.query.filter(
        UserEntity.state == USER_STATE_PAID, UserEntity.deleted == 0
    ).count()
    msgs.append("总付费用户数：{}".format(user_count))
    user_reg_count = UserEntity.query.filter(
        UserEntity.state >= USER_STATE_REGISTERED, UserEntity.deleted == 0
    ).count()
    msgs.append("总注册用户数：{}".format(user_reg_count))
    user_total_count = UserEntity.query.filter(UserEntity.deleted == 0).count()
    msgs.append("总访客数：{}".format(user_total_count))
    send_notify(app, title, msgs)


def is_order_has_timeout(app: Flask, origin_record: Order):
    pay_order_expire_time = app.config.get("PAY_ORDER_EXPIRE_TIME", 10 * 60)
    if pay_order_expire_time is None:
        return False
    pay_order_expire_time = int(pay_order_expire_time)

    created_at = origin_record.created_at
    if created_at.tzinfo is None:
        created_at = pytz.UTC.localize(created_at)
    else:
        created_at = created_at.astimezone(pytz.UTC)

    current_time = datetime.datetime.now(pytz.UTC)
    if current_time > created_at + datetime.timedelta(seconds=pay_order_expire_time):
        # Order timeout
        origin_record.status = ORDER_STATUS_TIMEOUT
        db.session.commit()
        from flaskr.service.promo.funcs import timeout_coupon_code_rollback

        timeout_coupon_code_rollback(
            app, origin_record.user_bid, origin_record.order_bid
        )
        return True
    return False


@contextmanager
def _order_init_lock(app: Flask, user_id: str, course_id: str) -> Iterator[None]:
    """
    Serialize order initialization for a user-course pair to avoid duplicate
    unpaid orders created by concurrent requests.
    """

    lock = None
    acquired = False

    if redis_client is not None:
        try:
            prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
            lock_key = f"{prefix}:order:init:{user_id}:{course_id}"
            lock = redis_client.lock(lock_key, timeout=10, blocking_timeout=10)
            if lock is not None:
                acquired = lock.acquire(blocking=True)
        except Exception:
            lock = None
            acquired = False

    try:
        yield
    finally:
        if acquired and lock is not None:
            try:
                lock.release()
            except Exception:
                pass


def init_buy_record(app: Flask, user_id: str, course_id: str, active_id: str = None):
    with app.app_context():
        set_shifu_context(course_id, get_shifu_creator_bid(app, course_id))
        shifu_info: LearnShifuInfoDTO = get_shifu_info(app, course_id, False)
        app.logger.info(f"shifu_info: {shifu_info}")
        if not shifu_info:
            raise_error("server.shifu.courseNotFound")

        with _order_init_lock(app, user_id, course_id):
            order_timeout_make_new_order = False
            find_active_id = None

            # By default, each user should only have one unpaid order per course (shifu).
            # Unpaid orders are those in INIT or TO_BE_PAID status and not timed out.
            origin_record = (
                Order.query.filter(
                    Order.user_bid == user_id,
                    Order.shifu_bid == course_id,
                    Order.status.in_([ORDER_STATUS_INIT, ORDER_STATUS_TO_BE_PAID]),
                )
                .order_by(Order.id.desc())
                .first()
            )
            if origin_record:
                if origin_record.status != ORDER_STATUS_SUCCESS:
                    order_timeout_make_new_order = is_order_has_timeout(
                        app, origin_record
                    )
                if order_timeout_make_new_order:
                    # Check if there are any coupons in the order. If there are, make them failure
                    find_active_id = query_to_failure_active(
                        app, origin_record.user_bid, origin_record.order_bid
                    )
            else:
                order_timeout_make_new_order = True
                find_active_id = None
            if (
                (not order_timeout_make_new_order)
                and origin_record
                and active_id is None
            ):
                return query_buy_record(app, origin_record.order_bid)
            # raise_error("server.order.orderNotFound")
            order_id = str(get_uuid(app))
            if order_timeout_make_new_order:
                buy_record = Order()
                buy_record.user_bid = user_id
                buy_record.shifu_bid = course_id
                buy_record.payable_price = decimal.Decimal(shifu_info.price)
                buy_record.status = ORDER_STATUS_INIT
                buy_record.order_bid = order_id
                buy_record.payable_price = decimal.Decimal(shifu_info.price)
            else:
                buy_record = origin_record
                order_id = origin_record.order_bid
            if find_active_id:
                active_id = find_active_id
            active_records = query_and_join_active(
                app, course_id, user_id, order_id, active_id
            )
            price_items = []
            price_items.append(
                PayItemDto(
                    _("server.order.payItemProduct"),
                    _("server.order.payItemBasePrice"),
                    buy_record.payable_price,
                    False,
                    None,
                )
            )
            discount_value = decimal.Decimal(0.00)
            if active_records:
                for active_record in active_records:
                    discount_value = decimal.Decimal(discount_value) + decimal.Decimal(
                        active_record.price
                    )
                    price_items.append(
                        PayItemDto(
                            _("server.order.payItemPromotion"),
                            active_record.active_name,
                            active_record.price,
                            True,
                            None,
                        )
                    )
            buy_record.paid_price = decimal.Decimal(
                buy_record.payable_price
            ) - decimal.Decimal(discount_value)
            db.session.merge(buy_record)
            db.session.commit()
            return AICourseBuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.shifu_bid,
                buy_record.payable_price,
                buy_record.status,
                discount_value,
                price_items,
            )


@register_schema_to_swagger
class BuyRecordDTO:
    """
    BuyRecordDTO
    """

    order_id: str
    user_id: str  # 用户id
    price: str  # 价格
    channel: str  # 支付渠道
    qr_url: str  # 二维码地址

    def __init__(
        self,
        record_id,
        user_id,
        price,
        channel,
        qr_url,
        payment_channel: str = "",
        payment_payload: Optional[Dict[str, Any]] = None,
    ):
        self.order_id = record_id
        self.user_id = user_id
        self.price = price
        self.channel = channel
        self.qr_url = qr_url
        self.payment_channel = payment_channel
        self.payment_payload = payment_payload or {}

    def __json__(self):
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "price": str(self.price),
            "channel": self.channel,
            "qr_url": self.qr_url,
            "payment_channel": self.payment_channel,
            "payment_payload": self.payment_payload,
        }


def generate_charge(
    app: Flask,
    record_id: str,
    channel: str,
    client_ip: str,
    payment_channel: Optional[str] = None,
) -> BuyRecordDTO:
    """
    Generate charge
    """
    with app.app_context():
        app.logger.info(
            "generate charge for record:{} channel:{}".format(record_id, channel)
        )

        buy_record: Order = Order.query.filter(
            Order.order_bid == record_id,
            Order.status != ORDER_STATUS_TIMEOUT,
        ).first()
        if not buy_record:
            raise_error("server.order.orderNotFound")
        set_shifu_context(
            buy_record.shifu_bid,
            get_shifu_creator_bid(app, buy_record.shifu_bid),
        )
        shifu_info: LearnShifuInfoDTO = get_shifu_info(app, buy_record.shifu_bid, False)
        if not shifu_info:
            raise_error("server.shifu.shifuNotFound")
        app.logger.info("buy record found:{}".format(buy_record))
        if buy_record.status == ORDER_STATUS_SUCCESS:
            app.logger.warning("buy record:{} status is not init".format(record_id))
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                channel,
                "",
                payment_channel=buy_record.payment_channel,
            )
            # raise_error("server.order.orderHasPaid")
        amount = int(buy_record.paid_price * 100)
        subject = shifu_info.title
        body = shifu_info.description
        if body is None or body == "":
            body = shifu_info.title
        order_no = str(get_uuid(app))

        # Only treat stored payment channel as a hint once a payment attempt has
        # been made. For newly initialized orders, we rely on explicit hints and
        # configuration to choose the provider so that model defaults do not
        # force an unintended channel.
        stored_payment_channel = (
            buy_record.payment_channel if buy_record.status != ORDER_STATUS_INIT else ""
        )
        payment_channel, provider_channel = _resolve_payment_channel(
            payment_channel_hint=payment_channel,
            channel_hint=channel,
            stored_channel=stored_payment_channel or None,
        )
        buy_record.payment_channel = payment_channel
        db.session.flush()

        if amount == 0:
            success_buy_record(app, buy_record.order_bid)
            response_channel = _format_response_channel(
                payment_channel, provider_channel
            )
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                response_channel,
                "",
                payment_channel=payment_channel,
            )

        if payment_channel == "pingxx":
            return _generate_pingxx_charge(
                app=app,
                buy_record=buy_record,
                course=shifu_info,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

        if payment_channel == "stripe":
            return _generate_stripe_charge(
                app=app,
                buy_record=buy_record,
                course=shifu_info,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

        app.logger.error("payment channel not support: %s", payment_channel)
        raise_error("server.pay.payChannelNotSupport")


def _resolve_payment_channel(
    *,
    payment_channel_hint: Optional[str],
    channel_hint: Optional[str],
    stored_channel: Optional[str],
) -> Tuple[str, str]:
    """Resolve the provider and provider-specific channel based on hints."""

    requested_payment_channel = (payment_channel_hint or "").strip().lower()
    requested_channel = (channel_hint or "").strip()

    # Read enabled payment providers from configuration.
    enabled_raw = str(get_config("PAYMENT_CHANNELS_ENABLED", "pingxx,stripe") or "")
    enabled_providers = {
        item.strip().lower() for item in enabled_raw.split(",") if item.strip()
    } or {"pingxx", "stripe"}

    # If using the default configuration, automatically disable providers that
    # are missing required credentials so that environments with only Stripe
    # (or only Ping++) configured do not accidentally use the wrong channel.
    if enabled_raw.strip().lower() == "pingxx,stripe":
        if "pingxx" in enabled_providers:
            pingxx_key = str(get_config("PINGXX_SECRET_KEY", "") or "")
            pingxx_app = str(get_config("PINGXX_APP_ID", "") or "")
            pingxx_key_path = str(get_config("PINGXX_PRIVATE_KEY_PATH", "") or "")
            if not (pingxx_key and pingxx_app and pingxx_key_path):
                enabled_providers.discard("pingxx")
        if "stripe" in enabled_providers:
            stripe_key = str(get_config("STRIPE_SECRET_KEY", "") or "")
            if not stripe_key:
                enabled_providers.discard("stripe")
        if not enabled_providers:
            enabled_providers = {"pingxx", "stripe"}

    provider_from_channel = ""
    if ":" in requested_channel:
        prefix, _ = requested_channel.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix in {"stripe", "pingxx"}:
            provider_from_channel = prefix
    elif requested_channel.lower() in {"stripe", "pingxx"}:
        provider_from_channel = requested_channel.lower()
    elif requested_channel:
        # Non-empty channel without explicit provider prefix is treated as a
        # Ping++ sub-channel (e.g., wx_pub_qr, alipay_qr).
        provider_from_channel = "pingxx"

    target_provider = requested_payment_channel or provider_from_channel

    # Fallback to stored provider or configuration defaults when no explicit
    # provider has been requested.
    if not target_provider:
        stored = (stored_channel or "").strip().lower()
        if stored in {"pingxx", "stripe"} and stored in enabled_providers:
            target_provider = stored
        else:
            if not enabled_providers:
                raise_error("server.pay.payChannelNotSupport")
            if len(enabled_providers) == 1:
                target_provider = next(iter(enabled_providers))
            elif "stripe" in enabled_providers:
                target_provider = "stripe"
            elif "pingxx" in enabled_providers:
                target_provider = "pingxx"
            else:
                raise_error("server.pay.payChannelNotSupport")

    # Validate requested provider name and configuration.
    if target_provider not in {"pingxx", "stripe"}:
        raise_error("server.pay.payChannelNotSupport")
    if target_provider not in enabled_providers:
        raise_error("server.pay.payChannelNotSupport")

    if target_provider == "stripe":
        normalized_channel = requested_channel.lower()
        # Default to Checkout Session for backward compatibility.
        provider_channel = "checkout_session"
        if ":" in normalized_channel:
            _, provider_channel = normalized_channel.split(":", 1)
        elif normalized_channel and normalized_channel != "stripe":
            provider_channel = normalized_channel

        provider_channel = provider_channel or "checkout_session"
        if provider_channel in {"checkout", "checkout_session"}:
            provider_channel = "checkout_session"
        elif provider_channel in {"intent", "payment_intent"}:
            provider_channel = "payment_intent"
        else:
            # Fallback to checkout session for unknown values.
            provider_channel = "checkout_session"
        return "stripe", provider_channel

    # Ping++ requires explicit channel input.
    provider_channel = requested_channel or ""
    if not provider_channel:
        raise_error("server.pay.payChannelNotSupport")
    return "pingxx", provider_channel


def _format_response_channel(payment_channel: str, provider_channel: str) -> str:
    if payment_channel == "stripe":
        return (
            "stripe"
            if provider_channel == "payment_intent"
            else f"stripe:{provider_channel}"
        )
    return provider_channel


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
    provider = get_payment_provider("pingxx")
    pingpp_id = get_config("PINGXX_APP_ID")
    provider_options: Dict[str, Any] = {"app_id": pingpp_id}
    charge_extra: Dict[str, Any] = {}
    qr_url_key: Optional[str] = None
    product_id = course.bid

    if channel == "wx_pub_qr":  # wxpay scan
        charge_extra = {"product_id": product_id}
        qr_url_key = "wx_pub_qr"
    elif channel == "alipay_qr":  # alipay scan
        charge_extra = {}
        qr_url_key = "alipay_qr"
    elif channel == "wx_pub":  # wxpay JSAPI
        user = load_user_aggregate(buy_record.user_bid)
        charge_extra = {"open_id": user.wechat_open_id} if user else {}
        qr_url_key = "wx_pub"
    elif channel == "wx_wap":  # wxpay H5
        charge_extra = {}
    else:
        app.logger.error("channel:%s not support", channel)
        raise_error("server.pay.payChannelNotSupport")

    provider_options["charge_extra"] = charge_extra
    payment_request = PaymentRequest(
        order_bid=order_no,
        user_bid=buy_record.user_bid,
        shifu_bid=buy_record.shifu_bid,
        amount=amount,
        channel=channel,
        currency="cny",
        subject=subject,
        body=body,
        client_ip=client_ip,
        extra=provider_options,
    )
    result = provider.create_payment(request=payment_request, app=app)
    charge = result.raw_response
    credential = charge.get("credential", {}) or {}
    qr_url = credential.get(qr_url_key) if qr_url_key else ""
    app.logger.info("Pingxx charge created:%s", charge)

    buy_record.status = ORDER_STATUS_TO_BE_PAID
    pingxx_order = PingxxOrder()
    pingxx_order.pingxx_order_bid = order_no
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
    db.session.commit()
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
    provider = get_payment_provider("stripe")
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
    provider_options: Dict[str, Any] = {
        "mode": resolved_mode,
        "metadata": metadata,
    }

    if resolved_mode == "checkout_session":
        success_url = get_config("STRIPE_SUCCESS_URL")
        cancel_url = get_config("STRIPE_CANCEL_URL")
        if success_url:
            provider_options["success_url"] = _inject_order_query(
                success_url, buy_record.order_bid
            )
        if cancel_url:
            provider_options["cancel_url"] = _inject_order_query(
                cancel_url, buy_record.order_bid
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
    result = provider.create_payment(request=payment_request, app=app)

    stripe_order = StripeOrder()
    stripe_order.order_bid = buy_record.order_bid
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
    db.session.commit()

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


def sync_stripe_checkout_session(
    app: Flask,
    order_id: str,
    session_id: Optional[str] = None,
    expected_user: Optional[str] = None,
):
    with app.app_context():
        order = (
            Order.query.filter(
                Order.order_bid == order_id,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .first()
        )
        if not order:
            raise_error("server.order.orderNotFound")
        if expected_user and order.user_bid != expected_user:
            raise_error("server.order.orderNotFound")

        if order.payment_channel != "stripe":
            raise_error("server.pay.payChannelNotSupport")

        stripe_order = (
            StripeOrder.query.filter(
                StripeOrder.order_bid == order.order_bid,
                StripeOrder.deleted == 0,
            )
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if not stripe_order:
            raise_error("server.order.orderNotFound")

        resolved_session_id = session_id or stripe_order.checkout_session_id
        if resolved_session_id and isinstance(resolved_session_id, str):
            placeholder = resolved_session_id.strip().strip("{}").upper()
            if placeholder in {"CHECKOUT_SESSION_ID", "SESSION_ID"}:
                resolved_session_id = stripe_order.checkout_session_id

        if not resolved_session_id:
            raise_error("server.order.orderNotFound")

        provider = get_payment_provider("stripe")
        session = provider.retrieve_checkout_session(
            session_id=resolved_session_id, app=app
        )
        intent = None
        intent_id = session.get("payment_intent") or stripe_order.payment_intent_id
        if intent_id:
            intent = provider.retrieve_payment_intent(intent_id=intent_id, app=app)

        _update_stripe_order_snapshot(
            stripe_order=stripe_order, session=session, intent=intent
        )
        paid = _is_stripe_payment_successful(session=session, intent=intent)

        if paid and order.status != ORDER_STATUS_SUCCESS:
            success_buy_record(app, order.order_bid)

        db.session.commit()
        return get_payment_details(app, order.order_bid)


def _update_stripe_order_snapshot(
    *,
    stripe_order: StripeOrder,
    session: Dict[str, Any],
    intent: Optional[Dict[str, Any]],
):
    if session:
        stripe_order.checkout_session_id = session.get(
            "id", stripe_order.checkout_session_id
        )
        stripe_order.checkout_session_object = _stringify_payload(session)
        payment_status = session.get("payment_status")
        status = session.get("status")
        if payment_status == "paid" or status == "complete":
            stripe_order.status = 1
        elif status == "expired":
            stripe_order.status = 3
        else:
            stripe_order.status = 0

    if intent:
        stripe_order.payment_intent_id = intent.get(
            "id", stripe_order.payment_intent_id
        )
        stripe_order.payment_intent_object = _stringify_payload(intent)
        latest_charge = intent.get("latest_charge")
        if latest_charge:
            stripe_order.latest_charge_id = latest_charge
        charges = intent.get("charges", {}).get("data", [])
        if charges:
            receipt_url = charges[0].get("receipt_url")
            if receipt_url:
                stripe_order.receipt_url = receipt_url


def _is_stripe_payment_successful(
    *, session: Optional[Dict[str, Any]], intent: Optional[Dict[str, Any]]
) -> bool:
    if session:
        if session.get("payment_status") == "paid":
            return True
        if session.get("status") == "complete":
            return True
    if intent and intent.get("status") == "succeeded":
        return True
    return False


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


def _stringify_payload(payload: Any) -> str:
    if not payload:
        return "{}"
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload)


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


def handle_stripe_webhook(
    app: Flask, raw_body: bytes, sig_header: str
) -> Tuple[Dict[str, Any], int]:
    provider = get_payment_provider("stripe")
    try:
        notification: PaymentNotificationResult = provider.handle_notification(
            payload={"raw_body": raw_body, "sig_header": sig_header}, app=app
        )
    except Exception as exc:  # pragma: no cover - verified via tests for error path
        app.logger.exception("Stripe webhook verification failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
        }, 400

    event = notification.provider_payload or {}
    event_type = notification.status
    data_object = event.get("data", {}).get("object", {}) or {}
    metadata = data_object.get("metadata", {}) or {}
    order_bid = notification.order_bid or metadata.get("order_bid", "")

    if not order_bid:
        app.logger.warning("Stripe webhook missing order metadata. type=%s", event_type)
        return {
            "status": "ignored",
            "reason": "missing order metadata",
            "event_type": event_type,
        }, 202

    with app.app_context():
        stripe_order: Optional[StripeOrder] = (
            StripeOrder.query.filter(StripeOrder.order_bid == order_bid)
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if not stripe_order:
            app.logger.warning("Stripe order not found for order_bid=%s", order_bid)
            return {
                "status": "ignored",
                "order_bid": order_bid,
                "reason": "stripe order not found",
                "event_type": event_type,
            }, 202

        response_status = "acknowledged"
        http_status = 202

        if notification.charge_id:
            stripe_order.latest_charge_id = notification.charge_id
        payment_intent_id = data_object.get("payment_intent") or data_object.get("id")
        if payment_intent_id and payment_intent_id.startswith("pi_"):
            stripe_order.payment_intent_id = payment_intent_id
        if metadata:
            stripe_order.metadata_json = _stringify_payload(metadata)

        if event_type == "checkout.session.completed":
            stripe_order.checkout_session_id = data_object.get(
                "id", stripe_order.checkout_session_id
            )
            stripe_order.checkout_session_object = _stringify_payload(data_object)

        if event_type.startswith("payment_intent"):
            stripe_order.payment_intent_object = _stringify_payload(data_object)
            stripe_order.payment_method = data_object.get(
                "payment_method", stripe_order.payment_method
            )
            charges = data_object.get("charges", {}).get("data", [])
            if charges:
                stripe_order.receipt_url = charges[0].get(
                    "receipt_url", stripe_order.receipt_url
                )

        success_events = {
            "payment_intent.succeeded",
            "checkout.session.completed",
        }
        fail_events = {
            "payment_intent.payment_failed",
        }
        refund_events = {
            "charge.refunded",
            "refund.created",
        }
        cancel_events = {
            "payment_intent.canceled",
        }

        if event_type in success_events:
            stripe_order.status = 1
            success_buy_record(app, order_bid)
            response_status = "paid"
            http_status = 200
        elif event_type in fail_events:
            stripe_order.status = 4
            error_info = data_object.get("last_payment_error", {}) or {}
            stripe_order.failure_code = error_info.get("code", "")
            stripe_order.failure_message = error_info.get("message", "")
            response_status = "failed"
            http_status = 200
        elif event_type in refund_events:
            stripe_order.status = 2
            response_status = "refunded"
            http_status = 200
        elif event_type in cancel_events:
            stripe_order.status = 3
            response_status = "cancelled"
            http_status = 200

        db.session.commit()

    return {
        "status": response_status,
        "order_bid": order_bid,
        "event_type": event_type,
    }, http_status


def refund_order_payment(
    app: Flask,
    order_bid: str,
    amount: Optional[int] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    with app.app_context():
        order = Order.query.filter(Order.order_bid == order_bid).first()
        if not order:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        provider = get_payment_provider(payment_channel)

        if payment_channel != "stripe":
            app.logger.error("Refund not implemented for channel: %s", payment_channel)
            raise_error("server.pay.payChannelNotSupport")

        stripe_order = (
            StripeOrder.query.filter(StripeOrder.order_bid == order_bid)
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if not stripe_order:
            raise_error("server.order.orderNotFound")

        refund_amount = amount if amount is not None else stripe_order.amount
        metadata = {
            "order_bid": order_bid,
            "payment_intent_id": stripe_order.payment_intent_id,
            "charge_id": stripe_order.latest_charge_id,
        }

        refund_request = PaymentRefundRequest(
            order_bid=order_bid,
            amount=refund_amount,
            reason=reason,
            metadata=metadata,
        )

        result = provider.refund_payment(request=refund_request, app=app)

        metadata_dict = {}
        if stripe_order.metadata_json:
            try:
                metadata_dict = json.loads(stripe_order.metadata_json)
            except json.JSONDecodeError:
                metadata_dict = {}
        metadata_dict["last_refund_id"] = result.provider_reference
        stripe_order.metadata_json = json.dumps(metadata_dict)
        stripe_order.payment_intent_object = _stringify_payload(result.raw_response)

        refund_status = (result.status or "").lower()
        if refund_status == "succeeded":
            stripe_order.status = 2
            order.status = ORDER_STATUS_REFUND
        elif refund_status in {"pending", "requires_action"}:
            stripe_order.status = stripe_order.status or 1
        else:
            stripe_order.status = 4
            stripe_order.failure_code = refund_status or stripe_order.failure_code

        db.session.commit()

    return {
        "status": result.status,
        "order_bid": order_bid,
        "refund_id": result.provider_reference,
        "amount": refund_amount,
    }


def get_payment_details(app: Flask, order_bid: str) -> Dict[str, Any]:
    with app.app_context():
        order = Order.query.filter(Order.order_bid == order_bid).first()
        if not order:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        if payment_channel == "stripe":
            stripe_order = (
                StripeOrder.query.filter(StripeOrder.order_bid == order_bid)
                .order_by(StripeOrder.id.desc())
                .first()
            )
            if not stripe_order:
                raise_error("server.order.orderNotFound")
            return {
                "payment_channel": "stripe",
                "course_id": order.shifu_bid,
                "order_bid": order_bid,
                "payment_intent_id": stripe_order.payment_intent_id,
                "checkout_session_id": stripe_order.checkout_session_id,
                "latest_charge_id": stripe_order.latest_charge_id,
                "status": stripe_order.status,
                "receipt_url": stripe_order.receipt_url,
                "payment_method": stripe_order.payment_method,
                "metadata": _parse_json_payload(stripe_order.metadata_json),
                "payment_intent_object": _parse_json_payload(
                    stripe_order.payment_intent_object
                ),
                "checkout_session_object": _parse_json_payload(
                    stripe_order.checkout_session_object
                ),
            }

        pingxx_order = (
            PingxxOrder.query.filter(PingxxOrder.order_bid == order.order_bid)
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        if not pingxx_order:
            raise_error("server.order.orderNotFound")
        return {
            "payment_channel": "pingxx",
            "course_id": order.shifu_bid,
            "order_bid": order_bid,
            "charge_id": pingxx_order.charge_id,
            "transaction_no": pingxx_order.transaction_no,
            "status": pingxx_order.status,
            "amount": pingxx_order.amount,
            "currency": pingxx_order.currency,
            "channel": pingxx_order.channel,
            "extra": pingxx_order.extra,
            "charge_object": pingxx_order.charge_object,
        }


def success_buy_record_from_pingxx(app: Flask, charge_id: str, body: dict):
    """
    Success buy record from pingxx
    """
    with app.app_context():
        pingxx_order = PingxxOrder.query.filter(
            PingxxOrder.charge_id == charge_id
        ).first()
        if not pingxx_order:
            return
        lock = redis_client.lock(
            "success_buy_record_from_pingxx" + charge_id,
            timeout=10,
            blocking_timeout=10,
        )

        if not lock:
            app.logger.error('lock failed for charge:"{}"'.format(charge_id))
        if lock.acquire(blocking=True):
            try:
                app.logger.info(
                    'success buy record from pingxx charge:"{}"'.format(charge_id)
                )
                pingxx_order: PingxxOrder = PingxxOrder.query.filter(
                    PingxxOrder.charge_id == charge_id
                ).first()
                if not pingxx_order:
                    lock.release()
                    return None
                pingxx_order.update = datetime.datetime.now()
                pingxx_order.status = 1
                pingxx_order.charge_object = json.dumps(body)
                if pingxx_order:
                    buy_record: Order = Order.query.filter(
                        Order.order_bid == pingxx_order.order_bid,
                    ).first()
                    if buy_record:
                        set_shifu_context(
                            buy_record.shifu_bid,
                            get_shifu_creator_bid(app, buy_record.shifu_bid),
                        )

                    if buy_record and buy_record.status == ORDER_STATUS_TO_BE_PAID:
                        try:
                            set_user_state(buy_record.user_bid, USER_STATE_PAID)
                        except Exception as e:
                            app.logger.error("update user state error:%s", e)
                        buy_record.status = ORDER_STATUS_SUCCESS
                        db.session.commit()
                        send_order_feishu(app, buy_record.order_bid)
                        return query_buy_record(app, buy_record.order_bid)
                    else:
                        app.logger.error(
                            "record:{} not found".format(pingxx_order.order_bid)
                        )
                else:
                    app.logger.error("charge:{} not found".format(charge_id))
                return None
            except Exception as e:
                app.logger.error(
                    'success buy record from pingxx charge:"{}" error:{}'.format(
                        charge_id, e
                    )
                )
            finally:
                lock.release()


def success_buy_record(app: Flask, record_id: str):
    """
    Success buy record
    """
    with app.app_context():
        app.logger.info('success buy record:"{}"'.format(record_id))
        buy_record = Order.query.filter(Order.order_bid == record_id).first()
        if buy_record:
            set_shifu_context(
                buy_record.shifu_bid,
                get_shifu_creator_bid(app, buy_record.shifu_bid),
            )
            try:
                set_user_state(buy_record.user_bid, USER_STATE_PAID)
            except Exception as e:
                app.logger.error("update user state error:%s", e)
            buy_record.status = ORDER_STATUS_SUCCESS
            db.session.commit()
            send_order_feishu(app, buy_record.order_bid)
            return query_buy_record(app, record_id)
        else:
            app.logger.error("record:{} not found".format(record_id))
        return None


def query_raw_buy_record(app: Flask, user_id, course_id) -> Order:
    """
    Query raw buy record
    """
    with app.app_context():
        buy_record = Order.query.filter(
            Order.shifu_bid == course_id,
            Order.user_bid == user_id,
            Order.status != ORDER_STATUS_TIMEOUT,
            Order.deleted == 0,
        ).first()
        if buy_record:
            return buy_record
        return None


class DiscountInfo:
    discount_value: str
    items: list[PayItemDto]

    def __init__(self, discount_value, items):
        self.discount_value = discount_value
        self.items = items


def calculate_discount_value(
    app: Flask,
    price: str,
    active_records: list,
    discount_records: list[CouponUsageModel],
) -> DiscountInfo:
    """
    Calculate discount value
    """
    discount_value = 0
    items = []
    if active_records is not None and len(active_records) > 0:
        for active_record in active_records:
            discount_value += active_record.price
            items.append(
                PayItemDto(
                    _("server.order.payItemPromotion"),
                    active_record.active_name,
                    active_record.price,
                    True,
                    None,
                )
            )
    if discount_records is not None and len(discount_records) > 0:
        discount_ids = [i.coupon_bid for i in discount_records]
        coupons: list[Coupon] = Coupon.query.filter(
            Coupon.coupon_bid.in_(discount_ids)
        ).all()
        coupon_maps: dict[str, Coupon] = {i.coupon_bid: i for i in coupons}
        for discount_record in discount_records:
            discount = coupon_maps.get(discount_record.coupon_bid, None)
            if discount:
                if discount.discount_type == COUPON_TYPE_FIXED:
                    discount_value += discount.value
                elif discount.discount_type == COUPON_TYPE_PERCENT:
                    discount_value += discount.value * price / 100
                items.append(
                    PayItemDto(
                        _("server.order.payItemCoupon"),
                        discount.channel,
                        discount.value,
                        True,
                        discount.channel,
                    )
                )
    if discount_value > price:
        discount_value = price
    return DiscountInfo(discount_value, items)


def query_buy_record(app: Flask, record_id: str) -> AICourseBuyRecordDTO:
    with app.app_context():
        app.logger.info('query buy record:"{}"'.format(record_id))
        buy_record: Order = Order.query.filter(Order.order_bid == record_id).first()
        print("buy_record: ", buy_record.payable_price, buy_record.paid_price)
        if buy_record:
            item = []
            item.append(
                PayItemDto(
                    _("server.order.payItemProduct"),
                    _("server.order.payItemBasePrice"),
                    buy_record.payable_price,
                    False,
                    None,
                )
            )
            recaul_discount = buy_record.status != ORDER_STATUS_SUCCESS
            if buy_record.payable_price > 0:
                aitive_records = query_active_record(app, record_id, recaul_discount)
                discount_records = query_discount_record(
                    app, record_id, recaul_discount
                )
                discount_info = calculate_discount_value(
                    app, buy_record.payable_price, aitive_records, discount_records
                )
                if (
                    recaul_discount
                    and discount_info.discount_value != buy_record.payable_price
                ):
                    app.logger.info(
                        "update discount value for buy record:{}".format(record_id)
                    )
                    # buy_record.payable_price = discount_info.discount_value
                    buy_record.paid_price = decimal.Decimal(
                        buy_record.payable_price
                    ) - decimal.Decimal(discount_info.discount_value)
                    buy_record.updated_at = datetime.datetime.now()
                    db.session.commit()
                item = discount_info.items

            return AICourseBuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.shifu_bid,
                buy_record.payable_price,
                buy_record.status,
                decimal.Decimal(buy_record.payable_price)
                - decimal.Decimal(buy_record.paid_price),
                item,
            )

        raise_error("server.order.orderNotFound")
