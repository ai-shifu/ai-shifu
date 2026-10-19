"""Implement business operations for legacy orders."""

import datetime
import decimal
import threading  # noqa: F401 - re-exported for patching
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

import pytz
from flask import Flask
from flaskr.api.doc.feishu import send_notify
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.common.cache_provider import (  # noqa: F401 - re-exported public API
    redis_cache,
)
from flaskr.common.public_urls import (  # noqa: F401 - re-exported public API
    build_stripe_learner_result_url,
)
from flaskr.common.shifu_context import set_shifu_context
from flaskr.common.swagger import (  # noqa: F401 - re-exported public API
    register_schema_to_swagger,
)
from flaskr.dao import db, retry_on_deadlock, uow
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.i18n import _
from flaskr.service.billing.api import (  # noqa: F401 - re-exported public API
    build_provider_config_overrides,
    resolve_creator_public_integrations,
    resolve_creator_wechat_oauth_app_id,
    resolve_payment_integration_for_new_order,
    resolve_provider_credential_context,
)
from flaskr.service.common.models import raise_error
from flaskr.service.common.native_payment_status import (  # noqa: F401 - re-exported public API
    extract_native_trade_payload,
    extract_native_trade_status,
    native_snapshot_status,
)
from flaskr.service.common.pricing import calculate_percentage_amount
from flaskr.service.config import (  # noqa: F401 - re-exported public API
    config_overrides,
    get_config,
)
from flaskr.service.learn.learn_dtos import LearnShifuInfoDTO
from flaskr.service.learn.learn_funcs import get_shifu_info
from flaskr.service.order.charge_providers import (  # noqa: F401 - re-exported public API
    _generate_alipay_charge,
    _generate_pingxx_charge,
    _generate_stripe_charge,
    _generate_wechatpay_charge,
    _order_credential_scope,
    _resolve_charge_wechat_app_id,
    _resolve_custom_payment_provider_hints,
    _resolve_payment_channel,
    assign_free_order_payment_channel,
)
from flaskr.service.order.charge_repricing import (  # noqa: F401 - re-exported public API
    _resume_pending_charge,
    cancel_pending_payment_for_repricing,
    restore_repricing_order,
)
from flaskr.service.order.consts import (  # noqa: F401 - re-exported public API
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_TO_BE_PAID,
    ORDER_STATUS_VALUES,
)
from flaskr.service.order.legacy_order_dtos import (  # noqa: F401 - re-exported public API
    AICourseBuyRecordDTO,
    BuyRecordDTO,
    DiscountInfo,
    PayItemDto,
)
from flaskr.service.order.models import (  # noqa: F401 - re-exported public API
    Order,
    PingxxOrder,
    StripeOrder,
)
from flaskr.service.order.order_discounts import (  # noqa: F401 - re-exported public API
    _sum_discount_items,
    _supplement_promo_discount_items,
    calculate_discount_value,
)
from flaskr.service.order.payment_attempts import (
    _is_stripe_payment_successful,
    _stripe_attempt_can_complete,
    _stripe_attempt_matches_order,
    _stripe_provider_objects_match_attempt,
    _update_stripe_order_snapshot,
)
from flaskr.service.order.payment_channel_resolution import (  # noqa: F401 - re-exported public API
    resolve_market_payment_provider,
    resolve_payment_channel,
)
from flaskr.service.order.payment_completion import (  # noqa: F401 - re-exported public API
    success_buy_record_from_native,
    success_buy_record_from_pingxx,
)
from flaskr.service.order.payment_lifecycle import (  # noqa: F401 - re-exported public API
    _assert_payment_lifecycle_lock_owned,
    _payment_lock_ownership_events,
    payment_lifecycle_lock,
)
from flaskr.service.order.payment_payloads import (
    _format_response_channel,
)
from flaskr.service.order.payment_providers import (  # noqa: F401 - re-exported public API
    PaymentRequest,
    get_payment_provider,
)
from flaskr.service.order.payment_providers.base import (  # noqa: F401 - re-exported public API
    PaymentNotificationResult,
    PaymentRefundRequest,
)
from flaskr.service.order.payment_sync import (  # noqa: F401 - re-exported public API
    get_payment_details,
    handle_stripe_webhook,
    refund_order_payment,
    sync_native_payment_order,
)
from flaskr.service.order.raw_snapshots import (  # noqa: F401 - re-exported public API
    RAW_BIZ_DOMAIN_ORDER,
    legacy_native_snapshot_query,
    legacy_pingxx_snapshot_query,
    legacy_stripe_snapshot_query,
    native_snapshot_model,
    should_update_native_snapshot_status,
    upsert_native_snapshot,
)
from flaskr.service.promo.consts import (  # noqa: F401 - re-exported public API
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
)
from flaskr.service.promo.funcs import (
    apply_promo_campaigns,
    query_promo_campaign_applications,
    timeout_coupon_code_rollback,
    void_promo_campaign_applications,
)
from flaskr.service.promo.models import (  # noqa: F401 - re-exported public API
    Coupon,
    PromoCampaign,
    PromoRedemption,
)
from flaskr.service.promo.models import (
    CouponUsage as CouponUsageModel,
)
from flaskr.service.shifu.utils import get_shifu_creator_bid
from flaskr.service.user.consts import (
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
)
from flaskr.service.user.models import UserConversion
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import (
    STATE_TO_PUBLIC_STATE,
    load_user_aggregate,
    set_user_state,
)
from flaskr.util.datetime import (  # noqa: F401 - re-exported public API
    now_utc,
)
from flaskr.util.uuid import generate_id as get_uuid


# to do : add to plugins
def send_order_feishu(app: Flask, record_id: str) -> None:
    """Send order feishu."""
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
    shifu_info: LearnShifuInfoDTO = get_shifu_info(
        app, order_info.course_id, preview_mode=False
    )
    if not shifu_info:
        return

    channel_labels = {
        "pingxx": "用户购买 (Pingxx)",
        "stripe": "用户购买 (Stripe)",
        "alipay": "用户购买 (支付宝)",
        "wechatpay": "用户购买 (微信支付)",
        "manual": "手动导入",
        "open_api": "Open API",
    }
    title = "购买课程通知"
    msgs = []
    msgs.append(f"手机号：{aggregate.mobile}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    msgs.append(f"昵称：{aggregate.name}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    msgs.append(f"课程名称：{shifu_info.title}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    msgs.append(f"实付金额：{order_info.price}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    channel = getattr(order_info, "payment_channel", "") or ""
    source_label = channel_labels.get(channel, channel or "未知")
    msgs.append(f"订单来源：{source_label}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    user_convertion = UserConversion.query.filter(
        UserConversion.user_id == order_info.user_id
    ).first()
    channel = ""
    if user_convertion:
        channel = user_convertion.conversion_source
    msgs.append(f"渠道：{channel}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    for item in order_info.price_item:
        msgs.append(f"{item.name}-{item.price_name}-{item.price}")
        if item.is_discount:
            msgs.append(f"优惠码：{item.discount_code}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    # Historical rows can retain the public state codes until separately normalized.
    paid_states = (USER_STATE_PAID, STATE_TO_PUBLIC_STATE[USER_STATE_PAID])
    verified_states = (USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID)
    user_count = UserEntity.query.filter(
        UserEntity.state.in_(paid_states), UserEntity.deleted == 0
    ).count()
    msgs.append(f"总付费用户数：{user_count}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    user_reg_count = UserEntity.query.filter(
        UserEntity.state.in_(
            (
                *verified_states,
                *(STATE_TO_PUBLIC_STATE[state] for state in verified_states),
            )
        ),
        UserEntity.deleted == 0,
    ).count()
    msgs.append(f"总注册用户数：{user_reg_count}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    user_total_count = UserEntity.query.filter(UserEntity.deleted == 0).count()
    msgs.append(f"总访客数：{user_total_count}")  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    send_notify(app, title, msgs)


def send_revoke_feishu(app: Flask, order_bid: str, user_identify: str) -> None:
    """Send revoke feishu."""
    order: Order = Order.query.filter(Order.order_bid == order_bid).first()
    if not order:
        return
    shifu_info: LearnShifuInfoDTO = get_shifu_info(
        app, order.shifu_bid, preview_mode=False
    )
    title = "取消课程授权通知"
    msgs = [
        f"用户标识：{user_identify}",  # noqa: RUF001 - intentional fullwidth Chinese punctuation
        f"课程名称：{shifu_info.title if shifu_info else order.shifu_bid}",  # noqa: RUF001 - intentional fullwidth Chinese punctuation
        f"订单号：{order_bid}",  # noqa: RUF001 - intentional fullwidth Chinese punctuation
        "来源：Open API",  # noqa: RUF001 - intentional fullwidth Chinese punctuation
    ]
    send_notify(app, title, msgs)


# Shared session-scope guard; see flaskr/dao/uow.py for the rationale.
_app_context_scope = app_context_scope


def is_order_has_timeout(app: Flask, origin_record: Order) -> bool:
    """Return True when an unpaid order is older than PAY_ORDER_EXPIRE_TIME.

    Pure predicate: it no longer flips the order status or rolls back coupon
    state. The caller decides what to do with a timed-out order inside its own
    unit of work (see ``init_buy_record``).
    """
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
    return current_time > created_at + datetime.timedelta(seconds=pay_order_expire_time)


@contextmanager
def _order_init_lock(app: Flask, user_id: str, course_id: str) -> Iterator[None]:
    """Serialize order initialization for a user-course pair to avoid duplicate unpaid orders created by concurrent requests."""
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
            with suppress(Exception):
                lock.release()


def _sync_order_campaign_pricing(
    app: Flask,
    *,
    buy_record: Order,
    user_id: str,
    course_id: str,
    active_id: str | None,
) -> tuple[list, decimal.Decimal]:
    """Refresh eligible campaigns for an unpaid order and recalculate paid price.

    Boundary-joining helper: it flushes but never commits; the pricing update
    persists (or rolls back) with the caller's unit of work.
    """
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
    coupon_records: list[CouponUsageModel] = CouponUsageModel.query.filter(
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
        coupon_map: dict[str, Coupon] = {}
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
                coupon_discount_value += calculate_percentage_amount(
                    decimal.Decimal(buy_record.payable_price), coupon_value
                )
    total_discount_value = discount_value + coupon_discount_value
    total_discount_value = min(total_discount_value, buy_record.payable_price)
    buy_record.paid_price = (
        decimal.Decimal(buy_record.payable_price) - total_discount_value
    )
    db.session.add(buy_record)
    db.session.flush()
    return campaign_applications, discount_value


@retry_on_deadlock()
def init_buy_record(
    app: Flask, user_id: str, course_id: str, active_id: str | None = None
) -> AICourseBuyRecordDTO:
    """Initialize buy record."""
    creator_bid = get_shifu_creator_bid(app, course_id)
    set_shifu_context(course_id, creator_bid)
    shifu_info: LearnShifuInfoDTO = get_shifu_info(app, course_id, preview_mode=False)
    app.logger.info("shifu_info: %s", shifu_info)
    if not shifu_info:
        raise_error("server.shifu.courseNotFound")

    with _order_init_lock(app, user_id, course_id), unit_of_work():
        order_timeout_make_new_order = False

        # By default, each user should only have one unpaid order per course (shifu).
        # Unpaid orders are those in INIT or TO_BE_PAID status and not timed out.
        origin_record = (
            Order.query.filter(
                Order.user_bid == user_id,
                Order.shifu_bid == course_id,
                Order.status.in_(
                    [
                        ORDER_STATUS_INIT,
                        ORDER_STATUS_TO_BE_PAID,
                        ORDER_STATUS_REPRICING,
                        ORDER_STATUS_SUCCESS,
                    ]
                ),
            )
            .order_by(Order.id.desc())
            .first()
        )
        if origin_record:
            if origin_record.status == ORDER_STATUS_REPRICING:
                return query_buy_record(app, origin_record.order_bid)
            if origin_record.status != ORDER_STATUS_SUCCESS:
                order_timeout_make_new_order = is_order_has_timeout(app, origin_record)
            if order_timeout_make_new_order:
                # The timeout flip is an explicit part of this unit of work:
                # it commits together with the replacement order below, or
                # rolls back with it, in which case a retry re-detects the
                # timeout (it is derived from created_at) and re-flips.
                origin_record.status = ORDER_STATUS_TIMEOUT
                # Both promo helpers join this unit of work, so the coupon
                # release and the campaign void commit (or roll back) together
                # with the timeout flip and the replacement order.
                timeout_coupon_code_rollback(
                    app, origin_record.user_bid, origin_record.order_bid
                )
                # Check if there are any coupons in the order. If there are, make them failure
                void_promo_campaign_applications(
                    app, origin_record.user_bid, origin_record.order_bid
                )
        else:
            order_timeout_make_new_order = True
        if origin_record and origin_record.status == ORDER_STATUS_SUCCESS:
            # A successful order is immutable purchase history. Reusing it must
            # not apply newer campaigns or repeat completion side effects.
            return query_buy_record(app, origin_record.order_bid)
        if (not order_timeout_make_new_order) and origin_record and active_id is None:
            _sync_order_campaign_pricing(
                app,
                buy_record=origin_record,
                user_id=user_id,
                course_id=course_id,
                active_id=None,
            )
            if decimal.Decimal(origin_record.paid_price) == decimal.Decimal(0):
                assign_free_order_payment_channel(origin_record)
                success_buy_record(app, origin_record.order_bid)
            return query_buy_record(app, origin_record.order_bid)
        order_id = str(get_uuid(app))
        if order_timeout_make_new_order:
            buy_record = Order()
            buy_record.user_bid = user_id
            buy_record.shifu_bid = course_id
            buy_record.creator_bid = creator_bid or ""
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
        if decimal.Decimal(buy_record.paid_price) == decimal.Decimal(0):
            assign_free_order_payment_channel(buy_record)
            success_buy_record(app, buy_record.order_bid)
        price_items = []
        price_items.append(
            PayItemDto(
                _("server.order.payItemProduct"),
                _("server.order.payItemBasePrice"),
                buy_record.payable_price,
                is_discount=False,
                discount_code=None,
            )
        )
        if campaign_applications:
            price_items.extend(
                PayItemDto(
                    _("server.order.payItemPromotion"),
                    campaign_application.promo_name,
                    campaign_application.discount_amount,
                    is_discount=True,
                    discount_code=None,
                )
                for campaign_application in campaign_applications
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


def generate_charge(
    app: Flask,
    record_id: str,
    channel: str,
    client_ip: str,
    payment_channel: str | None = None,
    expected_user: str | None = None,
) -> BuyRecordDTO:
    """Serialize payment creation and coupon repricing for one business order."""
    with payment_lifecycle_lock(record_id):
        resumed = _resume_or_close_pending_charge(
            app,
            record_id,
            channel=channel,
            payment_channel=payment_channel,
            expected_user=expected_user,
        )
        if resumed is not None:
            return resumed
        return _generate_charge_locked(
            app,
            record_id,
            channel,
            client_ip,
            payment_channel=payment_channel,
            expected_user=expected_user,
        )


def _resume_or_close_pending_charge(
    app: Flask,
    record_id: str,
    *,
    channel: str,
    payment_channel: str | None,
    expected_user: str | None,
) -> BuyRecordDTO | None:
    """Reuse a compatible attempt or close obsolete attempts before replacement."""
    with _app_context_scope(app):
        order = Order.query.filter(
            Order.order_bid == record_id,
            Order.deleted == 0,
        ).first()
        if not order or order.status != ORDER_STATUS_TO_BE_PAID:
            return None
        if expected_user and order.user_bid != expected_user:
            raise_error("server.order.orderNotFound")
        creator_bid = get_shifu_creator_bid(app, order.shifu_bid) or ""
        target_provider, target_channel = _resolve_payment_channel(
            payment_channel_hint=payment_channel,
            channel_hint=channel,
            stored_channel=str(order.payment_channel or "") or None,
            additional_enabled_providers=_resolve_custom_payment_provider_hints(
                creator_bid
            ),
        )
        resumed = _resume_pending_charge(
            app,
            order,
            payment_channel=target_provider,
            provider_channel=target_channel,
        )
        if resumed is not None:
            return resumed
        owner = str(expected_user or order.user_bid or "")
    cancel_pending_payment_for_repricing(app, record_id, expected_user=owner)
    return None


def _generate_charge_locked(
    app: Flask,
    record_id: str,
    channel: str,
    client_ip: str,
    payment_channel: str | None = None,
    expected_user: str | None = None,
) -> BuyRecordDTO:
    """Generate or resume a compatible provider payment attempt."""
    with _app_context_scope(app), unit_of_work():
        app.logger.info("generate charge for record:%s channel:%s", record_id, channel)

        buy_record: Order = (
            Order.query.filter(
                Order.order_bid == record_id,
                Order.status.in_(
                    [
                        ORDER_STATUS_INIT,
                        ORDER_STATUS_TO_BE_PAID,
                        ORDER_STATUS_SUCCESS,
                        ORDER_STATUS_REFUND,
                    ]
                ),
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if not buy_record:
            raise_error("server.order.orderNotFound")
        if expected_user and buy_record.user_bid != expected_user:
            raise_error("server.order.orderNotFound")
        if buy_record.status == ORDER_STATUS_REFUND:
            raise_error("server.order.orderStatusError")
        creator_bid = get_shifu_creator_bid(app, buy_record.shifu_bid) or ""
        set_shifu_context(buy_record.shifu_bid, creator_bid)
        buy_record.creator_bid = creator_bid
        if buy_record.status == ORDER_STATUS_SUCCESS:
            app.logger.warning("buy record:%s status is not init", record_id)
            return BuyRecordDTO(
                buy_record.order_bid,
                buy_record.user_bid,
                buy_record.paid_price,
                channel,
                "",
                payment_channel=buy_record.payment_channel,
            )
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
            additional_enabled_providers=_resolve_custom_payment_provider_hints(
                creator_bid
            ),
        )
        if buy_record.status == ORDER_STATUS_TO_BE_PAID:
            resumed_charge = _resume_pending_charge(
                app,
                buy_record,
                payment_channel=payment_channel,
                provider_channel=provider_channel,
            )
            if resumed_charge is not None:
                return resumed_charge
        shifu_info: LearnShifuInfoDTO = get_shifu_info(
            app, buy_record.shifu_bid, preview_mode=False
        )
        if not shifu_info:
            raise_error("server.shifu.shifuNotFound")
        app.logger.info("buy record found:%s", buy_record)
        amount = int(buy_record.paid_price * 100)
        subject = shifu_info.title
        body = shifu_info.description
        if body is None or body == "":
            body = shifu_info.title
        order_no = str(get_uuid(app))
        buy_record.payment_channel = payment_channel
        integration = resolve_payment_integration_for_new_order(
            app, creator_bid, payment_channel
        )
        buy_record.payment_integration_bid = (
            integration.integration_bid if integration else ""
        )
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

        return _generate_provider_charge(
            app,
            buy_record=buy_record,
            integration=integration,
            payment_channel=payment_channel,
            provider_channel=provider_channel,
            course=shifu_info,
            client_ip=client_ip,
            amount=amount,
            subject=subject,
            body=body,
            order_no=order_no,
        )
    return None


def _generate_provider_charge(
    app: Flask,
    *,
    buy_record: Order,
    integration: object,
    payment_channel: str,
    provider_channel: str,
    course: LearnShifuInfoDTO,
    client_ip: str,
    amount: int,
    subject: str,
    body: str,
    order_no: str,
) -> BuyRecordDTO:
    """Create the charge with the provider selected for this order."""
    if payment_channel == "pingxx":
        with _order_credential_scope(app, buy_record, integration):
            return _generate_pingxx_charge(
                app=app,
                buy_record=buy_record,
                course=course,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

    if payment_channel == "stripe":
        with _order_credential_scope(app, buy_record, integration):
            return _generate_stripe_charge(
                app=app,
                buy_record=buy_record,
                course=course,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

    if payment_channel == "alipay":
        with _order_credential_scope(app, buy_record, integration):
            return _generate_alipay_charge(
                app=app,
                buy_record=buy_record,
                course=course,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

    if payment_channel == "wechatpay":
        with _order_credential_scope(app, buy_record, integration):
            return _generate_wechatpay_charge(
                app=app,
                buy_record=buy_record,
                course=course,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
            )

    app.logger.error("payment channel not support: %s", payment_channel)
    raise_error("server.pay.payChannelNotSupport")
    return None


def sync_stripe_checkout_session(
    app: Flask,
    order_id: str,
    session_id: str | None = None,
    expected_user: str | None = None,
) -> dict[str, Any]:
    """Synchronize stripe checkout session."""
    with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_id):
        order = (
            Order.query.filter(
                Order.order_bid == order_id,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .with_for_update()
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
            .with_for_update()
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
        if resolved_session_id != stripe_order.checkout_session_id:
            raise_error("server.order.orderNotFound")

        provider = get_payment_provider("stripe")
        with _order_credential_scope(app, order):
            sync_result = provider.sync_reference(
                provider_reference=resolved_session_id,
                reference_type="checkout_session",
                app=app,
            )
        session = sync_result.provider_payload.get("checkout_session", {}) or {}
        intent = sync_result.provider_payload.get("payment_intent") or None
        if not _stripe_provider_objects_match_attempt(
            order=order,
            stripe_order=stripe_order,
            notification_order_bid=sync_result.order_bid,
            session=session,
            intent=intent,
        ):
            raise_error("server.order.orderNotFound")

        paid = _is_stripe_payment_successful(session=session, intent=intent)
        if paid:
            already_completed = (
                order.status == ORDER_STATUS_SUCCESS
                # Earlier syncs left fulfilled orders with pending/expired snapshots.
                and stripe_order.status in {0, 1, 3}
                and _stripe_attempt_matches_order(order, stripe_order)
            )
            if not already_completed and not _stripe_attempt_can_complete(
                order, stripe_order
            ):
                raise_error("server.order.orderStatusError")

        _update_stripe_order_snapshot(
            stripe_order=stripe_order, session=session, intent=intent
        )
        if paid:
            stripe_order.status = 1

        if paid and order.status != ORDER_STATUS_SUCCESS:
            success_buy_record(app, order.order_bid)

        _assert_payment_lifecycle_lock_owned()
        return get_payment_details(app, order.order_bid)


def success_buy_record(app: Flask, record_id: str) -> AICourseBuyRecordDTO | None:
    """Success buy record.

    Owns a unit of work so legacy callers (coupon_funcs, order admin) keep
    their self-committing behavior; when invoked inside another unit of work
    (generate_charge, payment webhooks, sync flows) the nested block joins
    the caller's transaction and the caller commits.
    """
    app.logger.info('success buy record:"%s"', record_id)
    buy_record = Order.query.filter(Order.order_bid == record_id).first()
    if buy_record:
        with unit_of_work():
            set_shifu_context(
                buy_record.shifu_bid,
                get_shifu_creator_bid(app, buy_record.shifu_bid),
            )
            try:
                set_user_state(buy_record.user_bid, USER_STATE_PAID)
            except Exception:
                app.logger.exception("update user state error")
            buy_record.status = ORDER_STATUS_SUCCESS
            # Notify only once the SUCCESS flip is durable: nested inside a
            # caller's unit of work this defers to the caller's commit (and
            # is dropped on rollback); at top level it fires right after our
            # own commit, matching the pre-migration ordering.
            order_bid = buy_record.order_bid
            uow.on_commit(lambda: send_order_feishu(app, order_bid))
        return query_buy_record(app, record_id)
    app.logger.error("record:%s not found", record_id)
    return None


def query_buy_record(
    app: Flask, record_id: str, expected_user: str | None = None
) -> AICourseBuyRecordDTO:
    # Read-only: reuses the caller's session so reads inside an open unit of
    # work see that transaction's pending state.
    """Query buy record."""
    with _app_context_scope(app):
        app.logger.info('query buy record:"%s"', record_id)
        buy_record: Order = Order.query.filter(
            Order.order_bid == record_id,
            Order.deleted == 0,
        ).first()
        if buy_record and expected_user and buy_record.user_bid != expected_user:
            raise_error("server.order.orderNotFound")
        if buy_record:
            item = []
            item.append(
                PayItemDto(
                    _("server.order.payItemProduct"),
                    _("server.order.payItemBasePrice"),
                    buy_record.payable_price,
                    is_discount=False,
                    discount_code=None,
                )
            )
            if buy_record.payable_price > 0:
                campaign_applications = query_promo_campaign_applications(
                    app, record_id, recalc_discount=False
                )
                discount_records = CouponUsageModel.query.filter(
                    CouponUsageModel.order_bid == record_id
                ).all()
                discount_info = calculate_discount_value(
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
    return None
