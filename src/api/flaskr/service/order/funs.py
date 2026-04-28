import datetime
import decimal
import json
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from flask import Flask

from flaskr.service.config import get_config
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.i18n import _
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
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.funcs import (
    apply_promo_campaigns,
    query_promo_campaign_applications,
    void_promo_campaign_applications,
)
from flaskr.service.promo.models import (
    Coupon,
    CouponUsage as CouponUsageModel,
    PromoCampaign,
    PromoRedemption,
)
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
from flaskr.service.common.native_payment_status import (
    extract_native_trade_payload,
    extract_native_trade_status,
    native_snapshot_status,
)
from flaskr.service.order.payment_channel_resolution import resolve_payment_channel
from flaskr.util.uuid import generate_id as get_uuid
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import db
from flaskr.service.common.models import raise_error
from flaskr.service.order.models import (
    Order,
    PingxxOrder,
    StripeOrder,
)
from flaskr.service.order.raw_snapshots import (
    RAW_BIZ_DOMAIN_ORDER,
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_model,
    should_update_native_snapshot_status,
    upsert_native_snapshot,
)
import pytz
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from flaskr.common.shifu_context import set_shifu_context
from flaskr.service.shifu.utils import get_shifu_creator_bid


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
        self,
        record_id,
        user_id,
        course_id,
        price,
        status,
        discount,
        price_item,
        payment_channel="",
    ):
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = price
        self.status = status
        self.discount = discount
        self.value_to_pay = str(decimal.Decimal(price) - decimal.Decimal(discount))
        self.price_item = price_item
        self.payment_channel = payment_channel

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

    _CHANNEL_LABEL = {
        "pingxx": "用户购买 (Pingxx)",
        "stripe": "用户购买 (Stripe)",
        "alipay": "用户购买 (支付宝)",
        "wechatpay": "用户购买 (微信支付)",
        "manual": "手动导入",
        "open_api": "Open API",
    }
    title = "购买课程通知"
    msgs = []
    msgs.append("手机号：{}".format(aggregate.mobile))
    msgs.append("昵称：{}".format(aggregate.name))
    msgs.append("课程名称：{}".format(shifu_info.title))
    msgs.append("实付金额：{}".format(order_info.price))
    channel = getattr(order_info, "payment_channel", "") or ""
    source_label = _CHANNEL_LABEL.get(channel, channel or "未知")
    msgs.append("订单来源：{}".format(source_label))
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


def send_revoke_feishu(app: Flask, order_bid: str, user_identify: str):
    order: Order = Order.query.filter(Order.order_bid == order_bid).first()
    if not order:
        return
    shifu_info: LearnShifuInfoDTO = get_shifu_info(app, order.shifu_bid, False)
    title = "取消课程授权通知"
    msgs = [
        "用户标识：{}".format(user_identify),
        "课程名称：{}".format(shifu_info.title if shifu_info else order.shifu_bid),
        "订单号：{}".format(order_bid),
        "来源：Open API",
    ]
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

    try:
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        lock_key = f"{prefix}:order:init:{user_id}:{course_id}"
        lock = cache_provider.lock(lock_key, timeout=10, blocking_timeout=10)
        acquired = bool(lock.acquire(blocking=True))
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


def _sync_order_campaign_pricing(
    app: Flask,
    *,
    buy_record: Order,
    user_id: str,
    course_id: str,
    active_id: Optional[str],
) -> Tuple[List, decimal.Decimal]:
    """Refresh eligible campaigns for an unpaid order and recalculate paid price."""
    campaign_applications = apply_promo_campaigns(
        app,
        shifu_bid=course_id,
        user_bid=user_id,
        order_bid=buy_record.order_bid,
        promo_bid=active_id,
        payable_price=buy_record.payable_price,
    )
    discount_value = decimal.Decimal("0.00")
    if campaign_applications:
        for campaign_application in campaign_applications:
            discount_value += decimal.Decimal(campaign_application.discount_amount)
    coupon_discount_value = decimal.Decimal("0.00")
    coupon_records: List[CouponUsageModel] = CouponUsageModel.query.filter(
        CouponUsageModel.order_bid == buy_record.order_bid,
        CouponUsageModel.status == COUPON_STATUS_USED,
        CouponUsageModel.deleted == 0,
    ).all()
    if coupon_records:
        coupon_bids = [
            coupon_record.coupon_bid
            for coupon_record in coupon_records
            if coupon_record.coupon_bid
        ]
        coupon_map: Dict[str, Coupon] = {}
        if coupon_bids:
            coupon_map = {
                coupon.coupon_bid: coupon
                for coupon in Coupon.query.filter(
                    Coupon.coupon_bid.in_(coupon_bids)
                ).all()
            }
        for coupon_record in coupon_records:
            coupon = coupon_map.get(coupon_record.coupon_bid)
            if not coupon:
                continue
            coupon_value = decimal.Decimal(
                str(getattr(coupon_record, "value", None) or coupon.value or 0)
            )
            if coupon.discount_type == COUPON_TYPE_FIXED:
                coupon_discount_value += coupon_value
            elif coupon.discount_type == COUPON_TYPE_PERCENT:
                coupon_discount_value += (
                    decimal.Decimal(buy_record.payable_price) * coupon_value / 100
                )
    total_discount_value = discount_value + coupon_discount_value
    if total_discount_value > buy_record.payable_price:
        total_discount_value = buy_record.payable_price
    buy_record.paid_price = (
        decimal.Decimal(buy_record.payable_price) - total_discount_value
    )
    db.session.add(buy_record)
    db.session.commit()
    return campaign_applications, discount_value


def init_buy_record(app: Flask, user_id: str, course_id: str, active_id: str = None):
    set_shifu_context(course_id, get_shifu_creator_bid(app, course_id))
    shifu_info: LearnShifuInfoDTO = get_shifu_info(app, course_id, False)
    app.logger.info(f"shifu_info: {shifu_info}")
    if not shifu_info:
        raise_error("server.shifu.courseNotFound")

    with _order_init_lock(app, user_id, course_id):
        order_timeout_make_new_order = False

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
                order_timeout_make_new_order = is_order_has_timeout(app, origin_record)
            if order_timeout_make_new_order:
                # Check if there are any coupons in the order. If there are, make them failure
                void_promo_campaign_applications(
                    app, origin_record.user_bid, origin_record.order_bid
                )
        else:
            order_timeout_make_new_order = True
        if (not order_timeout_make_new_order) and origin_record and active_id is None:
            _sync_order_campaign_pricing(
                app,
                buy_record=origin_record,
                user_id=user_id,
                course_id=course_id,
                active_id=None,
            )
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
        campaign_applications, discount_value = _sync_order_campaign_pricing(
            app,
            buy_record=buy_record,
            user_id=user_id,
            course_id=course_id,
            active_id=active_id,
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
        if campaign_applications:
            for campaign_application in campaign_applications:
                price_items.append(
                    PayItemDto(
                        _("server.order.payItemPromotion"),
                        campaign_application.promo_name,
                        campaign_application.discount_amount,
                        True,
                        None,
                    )
                )
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

        if payment_channel == "alipay":
            return _generate_alipay_charge(
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

        if payment_channel == "wechatpay":
            return _generate_wechatpay_charge(
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

    return resolve_payment_channel(
        payment_channel_hint=payment_channel_hint,
        channel_hint=channel_hint,
        stored_channel=stored_channel,
    )


def _format_response_channel(payment_channel: str, provider_channel: str) -> str:
    if payment_channel == "stripe":
        return (
            "stripe"
            if provider_channel == "payment_intent"
            else f"stripe:{provider_channel}"
        )
    return provider_channel


def _sanitize_pingxx_text(
    value: Optional[str], *, fallback: str, max_length: int
) -> str:
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
    provider = get_payment_provider("alipay")
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
    result = provider.create_payment(request=payment_request, app=app)
    credential = result.extra.get("credential", {}) or {}
    qr_url = str(result.extra.get("qr_url") or credential.get("alipay_qr") or "")

    buy_record.status = ORDER_STATUS_TO_BE_PAID
    snapshot = upsert_native_snapshot(
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
    db.session.commit()
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
    provider = get_payment_provider("wechatpay")
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
    extra: Dict[str, Any] = {
        "metadata": {
            "order_bid": buy_record.order_bid,
            "user_bid": buy_record.user_bid,
            "shifu_bid": buy_record.shifu_bid,
        }
    }
    if channel == "wx_pub":
        user = load_user_aggregate(buy_record.user_bid)
        open_id = str(user.wechat_open_id or "").strip() if user else ""
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
    snapshot = upsert_native_snapshot(
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
    db.session.commit()

    payment_payload: Dict[str, Any] = {
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
            legacy_stripe_snapshot_query()
            .filter(
                StripeOrder.order_bid == order.order_bid,
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
        sync_result = provider.sync_reference(
            provider_reference=resolved_session_id,
            reference_type="checkout_session",
            app=app,
        )
        session = sync_result.provider_payload.get("checkout_session", {}) or {}
        intent = sync_result.provider_payload.get("payment_intent") or None

        _update_stripe_order_snapshot(
            stripe_order=stripe_order, session=session, intent=intent
        )
        paid = _is_stripe_payment_successful(session=session, intent=intent)

        if paid and order.status != ORDER_STATUS_SUCCESS:
            success_buy_record(app, order.order_bid)

        db.session.commit()
        return get_payment_details(app, order.order_bid)


def sync_native_payment_order(
    app: Flask,
    order_id: str,
    *,
    expected_user: Optional[str] = None,
    payment_channel: Optional[str] = None,
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

        provider_name = str(payment_channel or order.payment_channel or "").lower()
        if provider_name == "stripe":
            return sync_stripe_checkout_session(
                app,
                order_id,
                expected_user=expected_user,
            )
        if provider_name not in {"alipay", "wechatpay"}:
            raise_error("server.pay.payChannelNotSupport")

        native_model = native_snapshot_model(provider_name)
        snapshot = (
            legacy_native_snapshot_query(provider_name)
            .filter(
                native_model.order_bid == order.order_bid,
            )
            .order_by(native_model.id.desc())
            .first()
        )
        if snapshot is None:
            raise_error("server.order.orderNotFound")
        if not snapshot.provider_attempt_id:
            raise_error("server.order.orderNotFound")

        provider = get_payment_provider(provider_name)
        sync_result = provider.sync_reference(
            provider_reference=snapshot.provider_attempt_id,
            reference_type="payment",
            app=app,
        )
        _apply_native_snapshot_update(
            snapshot=snapshot,
            provider=provider_name,
            notification=sync_result,
            source="sync",
        )
        actual_amount = _extract_native_notification_amount(
            provider_name,
            sync_result.provider_payload or {},
        )
        amount_matches = True
        if actual_amount is not None and int(snapshot.amount or 0) != actual_amount:
            amount_matches = False
            app.logger.warning(
                "native payment sync amount mismatch provider=%s order_bid=%s provider_attempt_id=%s expected=%s actual=%s",
                provider_name,
                order.order_bid,
                snapshot.provider_attempt_id,
                snapshot.amount,
                actual_amount,
            )
        if (
            _is_native_payment_successful(provider_name, sync_result.provider_payload)
            and amount_matches
            and order.status != ORDER_STATUS_SUCCESS
        ):
            success_buy_record(app, order.order_bid)
        db.session.add(snapshot)
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


def _apply_native_snapshot_update(
    *,
    snapshot: Any,
    provider: str,
    notification: PaymentNotificationResult,
    source: str,
) -> None:
    payload = notification.provider_payload or {}
    raw_status = _native_raw_status(provider, payload, notification.status)
    incoming_status = _native_snapshot_status(provider, payload, raw_status)
    if should_update_native_snapshot_status(snapshot.status, incoming_status):
        snapshot.raw_status = raw_status
        snapshot.status = incoming_status
    if notification.charge_id:
        snapshot.transaction_id = notification.charge_id
    if notification.order_bid:
        snapshot.provider_attempt_id = notification.order_bid
    if source == "webhook":
        snapshot.raw_notification = _stringify_payload(payload)
    else:
        snapshot.raw_response = _stringify_payload(payload)
    metadata = _parse_json_payload(snapshot.metadata_json)
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["latest_source"] = source
    metadata["latest_provider_payload"] = payload
    snapshot.metadata_json = _stringify_payload(metadata)


def _native_raw_status(
    provider: str,
    payload: Dict[str, Any],
    fallback: str = "",
) -> str:
    return extract_native_trade_status(provider, payload) or str(fallback or "")


def _native_snapshot_status(
    provider: str,
    payload: Dict[str, Any],
    raw_status: str,
) -> int:
    if raw_status and not extract_native_trade_status(provider, payload):
        payload = (
            {"trade_status": raw_status}
            if provider == "alipay"
            else {"trade_state": raw_status}
        )
    return native_snapshot_status(provider, payload)


def _is_native_payment_successful(
    provider: str,
    payload: Dict[str, Any],
) -> bool:
    raw_status = _native_raw_status(provider, payload)
    return _native_snapshot_status(provider, payload, raw_status) == 1


def _extract_native_notification_amount(
    provider: str,
    payload: Dict[str, Any],
) -> Optional[int]:
    trade_payload = extract_native_trade_payload(payload)
    if provider == "alipay":
        total_amount = (
            trade_payload.get("total_amount")
            if isinstance(trade_payload, dict)
            else None
        )
        if total_amount in (None, ""):
            return None
        return int((decimal.Decimal(str(total_amount)) * 100).to_integral_value())
    if provider == "wechatpay":
        amount = (
            trade_payload.get("amount", {}) if isinstance(trade_payload, dict) else {}
        )
        if not isinstance(amount, dict):
            return None
        value = amount.get("payer_total", amount.get("total"))
        if value in (None, ""):
            return None
        return int(value)
    return None


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
        notification: PaymentNotificationResult = provider.verify_webhook(
            headers={"Stripe-Signature": sig_header},
            raw_body=raw_body,
            app=app,
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
    bill_order_bid = metadata.get("bill_order_bid", "")
    is_billing_subscription_event = bool(
        data_object.get("subscription")
        or str(data_object.get("id") or "").startswith("sub_")
    )
    if bill_order_bid or is_billing_subscription_event:
        from flaskr.service.billing.webhooks import apply_billing_stripe_notification

        billing_result = apply_billing_stripe_notification(app, notification)
        return billing_result.to_response_dict(), billing_result.status_code
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
            legacy_stripe_snapshot_query()
            .filter(StripeOrder.order_bid == order_bid)
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
            legacy_stripe_snapshot_query()
            .filter(StripeOrder.order_bid == order_bid)
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
                legacy_stripe_snapshot_query()
                .filter(StripeOrder.order_bid == order_bid)
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

        if payment_channel in {"alipay", "wechatpay"}:
            native_model = native_snapshot_model(payment_channel)
            native_order = (
                legacy_native_snapshot_query(payment_channel)
                .filter(
                    native_model.order_bid == order.order_bid,
                )
                .order_by(native_model.id.desc())
                .first()
            )
            if not native_order:
                raise_error("server.order.orderNotFound")
            return {
                "payment_channel": payment_channel,
                "course_id": order.shifu_bid,
                "order_bid": order_bid,
                "provider_attempt_id": native_order.provider_attempt_id,
                "transaction_id": native_order.transaction_id,
                "status": native_order.status,
                "raw_status": native_order.raw_status,
                "amount": native_order.amount,
                "currency": native_order.currency,
                "channel": native_order.channel,
                "metadata": _parse_json_payload(native_order.metadata_json),
                "raw_request": _parse_json_payload(native_order.raw_request),
                "raw_response": _parse_json_payload(native_order.raw_response),
                "raw_notification": _parse_json_payload(native_order.raw_notification),
            }

        pingxx_order = (
            legacy_pingxx_snapshot_query()
            .filter(PingxxOrder.order_bid == order.order_bid)
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


def success_buy_record_from_native(
    app: Flask,
    provider_name: str,
    notification: PaymentNotificationResult,
) -> bool:
    with app.app_context():
        provider = str(provider_name or "").strip().lower()
        if provider not in {"alipay", "wechatpay"}:
            raise_error("server.pay.payChannelNotSupport")
        provider_attempt_id = str(notification.order_bid or "").strip()
        transaction_id = str(notification.charge_id or "").strip()
        native_model = native_snapshot_model(provider)
        query = legacy_native_snapshot_query(provider)
        if provider_attempt_id:
            native_order = (
                query.filter(native_model.provider_attempt_id == provider_attempt_id)
                .order_by(native_model.id.desc())
                .first()
            )
        elif transaction_id:
            native_order = (
                query.filter(native_model.transaction_id == transaction_id)
                .order_by(native_model.id.desc())
                .first()
            )
        else:
            native_order = None
        if native_order is None:
            return False

        lock_key = (
            "success_buy_record_from_native"
            f":{provider}:{provider_attempt_id or transaction_id or native_order.id}"
        )
        lock = cache_provider.lock(lock_key, timeout=10, blocking_timeout=10)
        if not lock:
            app.logger.error("native payment success lock unavailable key=%s", lock_key)
            return False
        if not lock.acquire(blocking=True):
            app.logger.error("native payment success lock failed key=%s", lock_key)
            return False

        try:
            native_order = native_model.query.filter(
                native_model.id == native_order.id,
                native_model.deleted == 0,
            ).first()
            if native_order is None:
                return False

            actual_amount = _extract_native_notification_amount(
                provider,
                notification.provider_payload or {},
            )
            if (
                actual_amount is not None
                and int(native_order.amount or 0) != actual_amount
            ):
                raise RuntimeError("Native payment amount mismatch")

            buy_record: Order = Order.query.filter(
                Order.order_bid == native_order.order_bid,
                Order.deleted == 0,
            ).first()
            if not buy_record:
                return False

            _apply_native_snapshot_update(
                snapshot=native_order,
                provider=provider,
                notification=notification,
                source="webhook",
            )
            db.session.add(native_order)

            if (
                _is_native_payment_successful(
                    provider,
                    notification.provider_payload or {},
                )
                and buy_record.status == ORDER_STATUS_TO_BE_PAID
            ):
                success_buy_record(app, buy_record.order_bid)
            else:
                db.session.commit()
            return True
        finally:
            lock.release()


def success_buy_record_from_pingxx(app: Flask, charge_id: str, body: dict):
    """
    Success buy record from pingxx
    """
    with app.app_context():
        pingxx_order = (
            legacy_pingxx_snapshot_query()
            .filter(PingxxOrder.charge_id == charge_id)
            .first()
        )
        if not pingxx_order:
            return
        lock = cache_provider.lock(
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
                pingxx_order = (
                    legacy_pingxx_snapshot_query()
                    .filter(PingxxOrder.charge_id == charge_id)
                    .first()
                )
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


class DiscountInfo:
    discount_value: str
    items: list[PayItemDto]

    def __init__(self, discount_value, items):
        self.discount_value = discount_value
        self.items = items


def _resolve_coupon_display_name(coupon: Coupon) -> str:
    coupon_name = str(getattr(coupon, "name", "") or "").strip()
    coupon_code = str(getattr(coupon, "code", "") or "").strip()
    if coupon_name and coupon_code and coupon_name != coupon_code:
        return f"{coupon_name} ({coupon_code})"
    if coupon_name:
        return coupon_name
    if coupon_code:
        return coupon_code
    return str(getattr(coupon, "channel", "") or "").strip()


def _sum_discount_items(items: list[PayItemDto]) -> decimal.Decimal:
    total = decimal.Decimal("0.00")
    for item in items:
        try:
            total += decimal.Decimal(str(item.price or 0))
        except decimal.InvalidOperation:
            continue
    return total


def _supplement_promo_discount_items(
    record_id: str,
    items: list[PayItemDto],
    expected_discount_value: decimal.Decimal,
) -> list[PayItemDto]:
    current_discount_value = _sum_discount_items(items)
    if current_discount_value >= expected_discount_value:
        return items

    existing_price_names = {
        str(getattr(item, "price_name", "") or "").strip() for item in items
    }
    promo_records = (
        PromoRedemption.query.filter(
            PromoRedemption.order_bid == record_id,
            PromoRedemption.deleted == 0,
            PromoRedemption.status == PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        )
        .order_by(PromoRedemption.updated_at.desc(), PromoRedemption.id.desc())
        .all()
    )
    promo_bids = [record.promo_bid for record in promo_records if record.promo_bid]
    promo_name_map = {}
    if promo_bids:
        promo_name_map = {
            campaign.promo_bid: str(campaign.name or "").strip()
            for campaign in PromoCampaign.query.filter(
                PromoCampaign.promo_bid.in_(promo_bids)
            ).all()
        }
    for record in promo_records:
        remaining_discount = expected_discount_value - current_discount_value
        if remaining_discount <= 0:
            break
        promo_name = (
            promo_name_map.get(record.promo_bid) or str(record.promo_name or "").strip()
        )
        if promo_name and promo_name in existing_price_names:
            continue
        try:
            record_discount = decimal.Decimal(str(record.discount_amount or 0))
        except decimal.InvalidOperation:
            continue
        if record_discount <= 0:
            continue
        item_discount = min(record_discount, remaining_discount)
        items.append(
            PayItemDto(
                _("server.order.payItemPromotion"),
                promo_name,
                item_discount,
                True,
                None,
            )
        )
        current_discount_value += item_discount
        if promo_name:
            existing_price_names.add(promo_name)
    return items


def calculate_discount_value(
    app: Flask,
    price: decimal.Decimal,
    campaign_applications: list,
    discount_records: list[CouponUsageModel],
) -> DiscountInfo:
    """
    Calculate discount value
    """
    discount_value = 0
    items = []
    if campaign_applications is not None and len(campaign_applications) > 0:
        for campaign_application in campaign_applications:
            discount_value += campaign_application.discount_amount
            items.append(
                PayItemDto(
                    _("server.order.payItemPromotion"),
                    campaign_application.promo_name,
                    campaign_application.discount_amount,
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
                        _resolve_coupon_display_name(discount),
                        discount.value,
                        True,
                        discount.code,
                    )
                )
    if discount_value > price:
        discount_value = price
    return DiscountInfo(discount_value, items)


def query_buy_record(app: Flask, record_id: str) -> AICourseBuyRecordDTO:
    with app.app_context():
        app.logger.info('query buy record:"{}"'.format(record_id))
        buy_record: Order = Order.query.filter(Order.order_bid == record_id).first()
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
            if buy_record.payable_price > 0:
                campaign_applications = query_promo_campaign_applications(
                    app, record_id, False
                )
                discount_records = CouponUsageModel.query.filter(
                    CouponUsageModel.order_bid == record_id
                ).all()
                discount_info = calculate_discount_value(
                    app,
                    buy_record.payable_price,
                    campaign_applications,
                    discount_records,
                )
                stored_discount_value = decimal.Decimal(
                    buy_record.payable_price
                ) - decimal.Decimal(buy_record.paid_price)
                discount_info.items = _supplement_promo_discount_items(
                    record_id,
                    discount_info.items,
                    stored_discount_value,
                )
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
                payment_channel=buy_record.payment_channel or "",
            )

        raise_error("server.order.orderNotFound")
