"""Implement business operations for legacy orders."""

import datetime
import decimal
import json
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext, suppress
from contextvars import ContextVar
from dataclasses import asdict, replace
from functools import cached_property
from typing import Any, Unpack
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytz
from flask import Flask
from flaskr.api.doc.feishu import send_notify
from flaskr.common.cache_provider import RenewableLockLease
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.common.shifu_context import set_shifu_context
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.dao import db, retry_on_deadlock, uow
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.i18n import _
from flaskr.service.billing.api import (
    build_provider_config_overrides,
    resolve_creator_payment_options,
    resolve_creator_public_integrations,
    resolve_creator_wechat_oauth_app_id,
    resolve_payment_integration_for_new_order,
    resolve_provider_credential_context,
)
from flaskr.service.common.models import raise_error
from flaskr.service.common.native_payment_status import (
    reported_payment_currency_matches,
)
from flaskr.service.common.pricing import calculate_percentage_amount
from flaskr.service.config import config_overrides
from flaskr.service.learn.learn_dtos import LearnShifuInfoDTO
from flaskr.service.learn.learn_funcs import get_shifu_info
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_TO_BE_PAID,
    ORDER_STATUS_VALUES,
)
from flaskr.service.order.learner_payments import (
    LearnerChargeArgs,
    PaymentAmountArgs,
    PreparedDirectPayment,
    _format_response_channel,
)
from flaskr.service.order.models import (
    Order,
    StripeOrder,
)
from flaskr.service.order.payment_channel_resolution import (
    resolve_market_payment_provider,
    resolve_payment_channel,
)
from flaskr.service.order.payment_policy import (
    purchase_attempt_can_complete,
    purchase_attempt_matches,
    saved_refund_controls_state,
)
from flaskr.service.order.payment_providers import (
    describe_notification,
    describe_query,
    get_payment_provider,
    historical_payment_definition,
    payment_definition,
    registered_payment_providers,
)
from flaskr.service.order.payment_providers.base import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundRequest,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.contracts import (
    PaymentAction,
    PaymentQueryTerms,
)
from flaskr.service.order.payment_providers.normalization import (
    creation_action,
    legacy_native_amount,
)
from flaskr.service.order.payment_snapshots import (
    _apply_native_snapshot_update,
    _extract_native_notification_amount,
    _is_native_payment_successful,
    _native_raw_status,
    _native_snapshot_status,
    bind_native_notification_reference,
    latest_attempt,
    pending_attempts,
)
from flaskr.service.order.raw_snapshots import (
    legacy_native_reference_query,
    legacy_native_snapshot_query,
    native_snapshot_model,
    registered_native_payment_providers,
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
    timeout_coupon_code_rollback,
    void_promo_campaign_applications,
)
from flaskr.service.promo.models import (
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
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id as get_uuid


@register_schema_to_swagger
class PayItemDto:
    """PayItemDto."""

    name: str
    price_name: str
    price: str
    is_discount: bool
    discount_code: str

    def __init__(
        self,
        name: object,
        price_name: object,
        price: object,
        is_discount: object,
        discount_code: object,
    ) -> None:
        """Build the pay item payload."""
        self.name = name
        self.price_name = price_name
        self.price = price
        self.is_discount = is_discount
        self.discount_code = discount_code

    def __json__(self) -> dict:
        """Return the pay item as JSON-compatible data."""
        return {
            "name": self.name,
            "price_name": self.price_name,
            "price": str(self.price),
            "is_discount": self.is_discount,
        }


@register_schema_to_swagger
class AICourseBuyRecordDTO:
    """AICourseBuyRecordDTO."""

    order_id: str
    user_id: str
    course_id: str
    price: decimal.Decimal
    status: int
    discount: str
    active_discount: str
    value_to_pay: str
    price_item: list[PayItemDto]

    def __init__(
        self,
        record_id: object,
        user_id: object,
        course_id: object,
        price: object,
        status: object,
        discount: object,
        price_item: object,
        payment_channel: object = "",
        creator_bid: str = "",
    ) -> None:
        """Build the AI course buy record payload."""
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = price
        self.status = status
        self.discount = discount
        self.value_to_pay = str(decimal.Decimal(price) - decimal.Decimal(discount))
        self.price_item = price_item
        self.payment_channel = payment_channel
        self._creator_bid = creator_bid

    @cached_property
    def payment_options(self) -> list[dict[str, object]] | None:
        """Load checkout options only when a payable order response needs them."""
        if self.status not in {
            ORDER_STATUS_INIT,
            ORDER_STATUS_TO_BE_PAID,
            ORDER_STATUS_REPRICING,
        }:
            return []
        try:
            return resolve_creator_payment_options(self._creator_bid)
        except Exception:
            from flask import current_app

            current_app.logger.warning(
                "failed to resolve payment options; creator_bid=%s",
                self._creator_bid,
                exc_info=True,
            )
            # Omit unavailable metadata so existing clients retain legacy recovery.
            # An explicitly empty option list still means no new payment is admitted.
            return None

    def __json__(self) -> dict:
        """Return the AI course buy record as JSON-compatible data."""

        def format_decimal(value: object) -> str:
            # Convert to a string with two decimal places
            formatted_value = value if isinstance(value, str) else f"{value:.2f}"
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
            **(
                {"payment_options": self.payment_options}
                if self.payment_options is not None
                else {}
            ),
        }


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
            creator_bid=str(buy_record.creator_bid or creator_bid or ""),
        )


@register_schema_to_swagger
class BuyRecordDTO:
    """BuyRecordDTO."""

    order_id: str
    user_id: str  # 用户id
    price: str  # 价格
    channel: str  # 支付渠道
    qr_url: str  # 二维码地址

    def __init__(
        self,
        record_id: object,
        user_id: object,
        price: object,
        channel: object,
        qr_url: object,
        payment_channel: str = "",
        payment_payload: dict[str, object] | None = None,
        payment_action: PaymentAction | None = None,
        status: int | None = None,
    ) -> None:
        """Build the buy record payload."""
        self.order_id = record_id
        self.user_id = user_id
        self.price = price
        self.channel = channel
        self.qr_url = qr_url
        self.payment_channel = payment_channel
        self.payment_payload = payment_payload or {}
        self.status = status
        action_extra = dict(self.payment_payload)
        action_extra.setdefault("qr_url", qr_url)
        action_extra["url"] = self.payment_payload.get("checkout_session_url") or ""
        self.payment_action = payment_action or creation_action(
            payment_channel,
            str(channel),
            PaymentCreationResult(
                "",
                {},
                client_secret=self.payment_payload.get("client_secret"),
                checkout_session_id=self.payment_payload.get("checkout_session_id"),
                extra=action_extra,
            ),
        )
        try:
            self.poll_provider = payment_definition(
                payment_channel
            ).capabilities.poll_provider
        except ValueError:
            self.poll_provider = False

    def __json__(self) -> dict:
        """Return the buy record as JSON-compatible data."""
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "price": str(self.price),
            "channel": self.channel,
            "qr_url": self.qr_url,
            "payment_channel": self.payment_channel,
            "payment_payload": self.payment_payload,
            "payment_action": self.payment_action.to_dict(),
            "payment_contract_version": 1,
            "poll_provider": self.poll_provider,
            **({"status": self.status} if self.status is not None else {}),
        }


def generate_charge(
    app: Flask,
    record_id: str,
    channel: str,
    client_ip: str,
    payment_channel: str | None = None,
    expected_user: str | None = None,
) -> BuyRecordDTO:
    """Serialize payment creation and coupon repricing for one business order."""
    uow.require_transaction_owner("learner payment creation", app)
    # Creation/repricing serialize separately from callbacks, which must be able
    # to settle the committed attempt while the provider call is in flight.
    with payment_lifecycle_lock(f"create:{record_id}") as creation_lease:
        with payment_lifecycle_lock(record_id):
            prepared = _recover_prepared_direct_charge(
                app, record_id, channel, payment_channel, expected_user
            )
            if prepared is None:
                resumed = _resume_or_close_pending_charge(
                    app,
                    record_id,
                    channel=channel,
                    payment_channel=payment_channel,
                    expected_user=expected_user,
                )
                if resumed is not None:
                    return resumed
                prepared = _generate_charge_locked(
                    app,
                    record_id,
                    channel,
                    client_ip,
                    payment_channel=payment_channel,
                    expected_user=expected_user,
                    prepare_direct=True,
                )
        if isinstance(prepared, PreparedDirectPayment):
            return _run_prepared_direct_charge(app, prepared, creation_lease)
        return prepared


_payment_lock_ownership_events: ContextVar[tuple[threading.Event, ...]] = ContextVar(
    "payment_lock_ownership_events", default=()
)


def _assert_payment_lifecycle_lock_owned() -> None:
    if any(event.is_set() for event in _payment_lock_ownership_events.get()):
        raise_error("server.order.orderStatusError")


class _PaymentLifecycleLease(RenewableLockLease):
    """Keep learner lock errors compatible while sharing the existing renewal loop."""

    def _raise_lost(self) -> None:
        raise_error("server.order.orderStatusError")


@contextmanager
def payment_lifecycle_lock(order_bid: str) -> Iterator[_PaymentLifecycleLease]:
    """Serialize external provider work that belongs to one business order."""
    with _payment_operation_lock(f"order-payment-lifecycle:{order_bid}") as lease:
        yield lease


@contextmanager
def _learner_refund_lock(order_bid: str) -> Iterator[_PaymentLifecycleLease]:
    """Keep refund callers serialized while callbacks retain lifecycle access."""
    with _payment_operation_lock(f"order-payment-refund:{order_bid}") as lease:
        yield lease


@contextmanager
def _payment_operation_lock(key: str) -> Iterator[_PaymentLifecycleLease]:
    lock = cache_provider.lock(
        key,
        timeout=60,
        blocking_timeout=60,
        thread_local=False,
    )
    if not lock or not lock.acquire(blocking=True):
        raise_error("server.order.orderStatusError")
    lease = _PaymentLifecycleLease(lock)
    ownership_token = _payment_lock_ownership_events.set(
        (*_payment_lock_ownership_events.get(), lease.ownership_lost)
    )
    try:
        yield lease
    finally:
        try:
            lease.release_checked()
        finally:
            _payment_lock_ownership_events.reset(ownership_token)


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
    prepare_direct: bool = False,
) -> BuyRecordDTO | PreparedDirectPayment:
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

        with _order_credential_scope(app, buy_record, integration):
            result = _generate_registered_charge(
                provider_name=payment_channel,
                app=app,
                buy_record=buy_record,
                course=shifu_info,
                channel=provider_channel,
                client_ip=client_ip,
                amount=amount,
                subject=subject,
                body=body,
                order_no=order_no,
                prepare_direct=prepare_direct,
            )
            if isinstance(result, PreparedDirectPayment):
                result.credential_overrides = _order_credential_overrides(
                    app, buy_record, integration
                )
            return result

    return None


def _recover_prepared_direct_charge(
    app: Flask,
    order_bid: str,
    channel: str,
    requested_provider: str | None,
    expected_user: str | None,
) -> PreparedDirectPayment | None:
    from .learner_payments import recover_direct_creation

    with _app_context_scope(app), unit_of_work():
        order = _load_payment_sync_order(
            order_bid, expected_user=expected_user, for_update=True
        )
        provider_name = str(order.payment_channel or "").strip().lower()
        if (
            order.status != ORDER_STATUS_TO_BE_PAID
            or provider_name not in registered_native_payment_providers()
        ):
            return None
        attempt = latest_attempt(provider_name, order_bid)
        if (
            attempt is None
            or attempt.status != 0
            or not attempt.metadata.get("prepared_payment_request")
        ):
            return None
        target_provider, target_channel = _resolve_payment_channel(
            payment_channel_hint=requested_provider,
            channel_hint=channel,
            stored_channel=provider_name,
            additional_enabled_providers=_resolve_custom_payment_provider_hints(
                str(order.creator_bid or "")
            ),
        )
        if (
            target_provider != provider_name
            or target_channel != attempt.record.channel
            or attempt.amount != int(decimal.Decimal(order.paid_price or 0) * 100)
        ):
            return None
        overrides = _order_credential_overrides(app, order)
        with config_overrides(overrides):
            prepared = recover_direct_creation(
                provider_name=provider_name,
                order=order,
                snapshot=attempt.record,
                provider=get_payment_provider(provider_name),
            )
        if prepared is not None:
            prepared.credential_overrides = overrides
        return prepared


def _prepared_paid_response(
    order: Order, prepared: PreparedDirectPayment
) -> BuyRecordDTO:
    return BuyRecordDTO(
        order.order_bid,
        order.user_bid,
        order.paid_price,
        prepared.request.channel,
        "",
        payment_channel=prepared.provider_name,
        payment_action=PaymentAction("none"),
        status=order.status,
    )


def _run_prepared_direct_charge(
    app: Flask,
    prepared: PreparedDirectPayment,
    creation_lease: _PaymentLifecycleLease,
) -> BuyRecordDTO:
    from .learner_payments import persist_direct_creation

    uow.require_transaction_owner("direct provider call", app)
    _assert_payment_lifecycle_lock_owned()
    try:
        with _app_context_scope(app), config_overrides(prepared.credential_overrides):
            result = prepared.provider.create_payment(request=prepared.request, app=app)
    except Exception:
        # A successful callback is durable even if the HTTP response is lost.
        with (
            _app_context_scope(app),
            payment_lifecycle_lock(prepared.order_bid) as lease,
            unit_of_work(),
        ):
            order = _load_payment_sync_order(
                prepared.order_bid,
                expected_user=prepared.request.user_bid,
                for_update=True,
            )
            attempt = latest_attempt(prepared.provider_name, prepared.order_bid)
            if (
                order.status == ORDER_STATUS_SUCCESS
                and order.payment_channel == prepared.provider_name
                and attempt is not None
                and attempt.record.id == prepared.snapshot_id
                and int(decimal.Decimal(order.paid_price or 0) * 100)
                == prepared.request.amount
            ):
                lease.release_checked()
                creation_lease.release_checked()
                return _prepared_paid_response(order, prepared)
        # The committed request remains retryable with its original merchant ID.
        raise

    with (
        _app_context_scope(app),
        payment_lifecycle_lock(prepared.order_bid) as lease,
        unit_of_work(),
    ):
        order = _load_payment_sync_order(
            prepared.order_bid, expected_user=prepared.request.user_bid, for_update=True
        )
        attempt = latest_attempt(prepared.provider_name, prepared.order_bid)
        matches = (
            order.payment_channel == prepared.provider_name
            and attempt is not None
            and attempt.record.id == prepared.snapshot_id
            and int(decimal.Decimal(order.paid_price or 0) * 100)
            == prepared.request.amount
            and order.status in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_SUCCESS}
        )
        view = persist_direct_creation(prepared, result)
        if matches and order.status == ORDER_STATUS_SUCCESS:
            response = _prepared_paid_response(order, prepared)
        else:
            response = BuyRecordDTO(
                view.order_bid,
                view.user_bid,
                view.paid_price,
                view.channel,
                view.qr_url,
                payment_channel=view.payment_channel,
                payment_payload=view.payment_payload,
                payment_action=view.payment_action,
            )
        _assert_payment_lifecycle_lock_owned()
        lease.release_checked()
        creation_lease.release_checked()
    if not matches:
        raise_error("server.order.orderStatusError")
    return response


def _resume_pending_charge(
    app: Flask,
    buy_record: Order,
    *,
    payment_channel: str | None = None,
    provider_channel: str | None = None,
) -> BuyRecordDTO | None:
    """Authorize the current amount; storage owns legacy presentation recovery."""
    from .learner_recovery import _resume_pending_charge as recover

    view = recover(
        app,
        buy_record,
        payment_channel=payment_channel,
        provider_channel=provider_channel,
        expected_amount=int(decimal.Decimal(buy_record.paid_price or 0) * 100),
    )
    return (
        BuyRecordDTO(
            view.order_bid,
            view.user_bid,
            view.paid_price,
            view.channel,
            view.qr_url,
            payment_channel=view.payment_channel,
            payment_payload=view.payment_payload,
            payment_action=view.payment_action,
        )
        if view is not None
        else None
    )


def cancel_pending_payment_for_repricing(
    app: Flask,
    order_bid: str,
    *,
    expected_user: str,
    keep_repricing_claim: bool = False,
) -> bool:
    """Close the current provider attempt before a coupon changes its amount."""
    with _app_context_scope(app), unit_of_work():
        order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.user_bid == expected_user,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if not order:
            raise_error("server.order.orderNotFound")
        if order.status == ORDER_STATUS_INIT:
            return False
        if order.status not in {ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_REPRICING}:
            raise_error("server.order.orderStatusError")
        order.status = ORDER_STATUS_REPRICING
        order.updated_at = now_utc()
        db.session.add(order)
        payment_channel = str(order.payment_channel or "pingxx").strip().lower()
        projected_attempts = pending_attempts(payment_channel, order_bid)
        snapshots = [attempt.record for attempt in projected_attempts]

        if not snapshots:
            if not keep_repricing_claim:
                order.status = ORDER_STATUS_INIT
            return False
        snapshot_ids = [snapshot.id for snapshot in snapshots]
        snapshot_model = snapshots[0].__class__
        attempts = [attempt.reference for attempt in projected_attempts]
        credential_order = Order(
            creator_bid=str(order.creator_bid or ""),
            payment_channel=str(order.payment_channel or ""),
            payment_integration_bid=str(order.payment_integration_bid or ""),
        )

    try:
        with _app_context_scope(app), _order_credential_scope(app, credential_order):
            provider = get_payment_provider(payment_channel)
            for provider_reference, reference_type in attempts:
                _assert_payment_lifecycle_lock_owned()
                if not provider_reference:
                    raise_error("server.order.orderStatusError")
                cancellation = provider.cancel_payment(
                    provider_reference=provider_reference,
                    reference_type=reference_type,
                    app=app,
                )
                if not cancellation.is_closed:
                    raise_error("server.order.orderStatusError")
    except Exception:
        app.logger.exception(
            "Failed to close payment attempts before repricing order=%s provider=%s",
            order_bid,
            payment_channel,
        )
        restore_repricing_order(app, order_bid, expected_user=expected_user)
        raise_error("server.order.orderStatusError")

    with _app_context_scope(app):
        with unit_of_work():
            locked_order = (
                Order.query.filter(
                    Order.order_bid == order_bid,
                    Order.user_bid == expected_user,
                    Order.deleted == 0,
                )
                .with_for_update()
                .first()
            )
            if not locked_order or locked_order.status != ORDER_STATUS_REPRICING:
                raise_error("server.order.orderStatusError")
            active_statuses = [0, 4] if snapshot_model is StripeOrder else [0]
            locked_snapshots = snapshot_model.query.filter(
                snapshot_model.id.in_(snapshot_ids),
                snapshot_model.status.in_(active_statuses),
            ).all()
            if len(locked_snapshots) != len(snapshot_ids):
                raise_error("server.order.orderStatusError")
            for locked_snapshot in locked_snapshots:
                locked_snapshot.status = 3
                locked_snapshot.updated_at = now_utc()
                db.session.add(locked_snapshot)
            if not keep_repricing_claim:
                locked_order.status = ORDER_STATUS_INIT
                locked_order.updated_at = now_utc()
                db.session.add(locked_order)
        return True


def restore_repricing_order(
    app: Flask,
    order_bid: str,
    *,
    expected_user: str,
    target_status: int = ORDER_STATUS_TO_BE_PAID,
) -> None:
    """Return an interrupted repricing claim to its payable state."""
    with _app_context_scope(app), unit_of_work():
        order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.user_bid == expected_user,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if order and order.status == ORDER_STATUS_REPRICING:
            order.status = target_status
            order.updated_at = now_utc()
            db.session.add(order)


def _order_credential_scope(
    app: Flask, order: Order, context: object = None
) -> AbstractContextManager[None]:
    """Use the immutable credential version snapshotted on the order."""
    overrides = _order_credential_overrides(app, order, context)
    return config_overrides(overrides) if overrides else nullcontext()


def _order_credential_overrides(
    app: Flask, order: Order, context: object = None
) -> dict:
    """Copy the frozen merchant context before leaving the prepare transaction."""
    integration_bid = str(order.payment_integration_bid or "")
    if not integration_bid:
        return {}
    context = context or resolve_provider_credential_context(
        app,
        creator_bid=str(order.creator_bid or ""),
        provider=str(order.payment_channel or ""),
        integration_bid=integration_bid,
    )
    if context is None or context.integration_bid != integration_bid:
        raise_error("server.pay.payChannelNotSupport")
    return build_provider_config_overrides(context)


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
    if recorded_channel in {"manual", "open_api"}:
        return
    if order.status != ORDER_STATUS_INIT:
        try:
            definition = historical_payment_definition(recorded_channel)
        except KeyError:
            definition = None
        if definition is not None and definition.preserve_free_order_attribution:
            return
    order.payment_channel = resolve_market_payment_provider()


def _resolve_custom_payment_provider_hints(creator_bid: str) -> set[str]:
    if not creator_bid:
        return set()
    try:
        public_integrations = resolve_creator_public_integrations(creator_bid)
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
        for provider in registered_payment_providers()
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
        return resolve_creator_wechat_oauth_app_id(creator_bid)
    except Exception:
        app.logger.warning(
            "failed to resolve creator WeChat app; creator_bid=%s",
            creator_bid,
            exc_info=True,
        )
        return ""


def _generate_registered_charge(
    *,
    provider_name: str,
    app: Flask,
    buy_record: Order,
    course: LearnShifuInfoDTO,
    channel: str,
    prepare_direct: bool = False,
    **kwargs: Unpack[PaymentAmountArgs],
) -> BuyRecordDTO | PreparedDirectPayment:
    """Keep purchase state transitions independent from request/snapshot protocols."""
    from .learner_payments import create_learner_attempt

    definition = payment_definition(provider_name)
    route = next((item for item in definition.routes if item.channel == channel), None)
    open_id = ""
    if route and route.requires_open_id:
        user = load_user_aggregate(buy_record.user_bid)
        app_id = _resolve_charge_wechat_app_id(app, str(buy_record.creator_bid or ""))
        open_id = str(user.wechat_open_id_for_app(app_id) or "").strip() if user else ""
    result = create_learner_attempt(
        provider_name=provider_name,
        app=app,
        buy_record=buy_record,
        course=course,
        channel=channel,
        provider=get_payment_provider(provider_name),
        open_id=open_id,
        before_provider_call=_assert_payment_lifecycle_lock_owned,
        prepare_direct=prepare_direct,
        **kwargs,
    )
    buy_record.status = ORDER_STATUS_TO_BE_PAID
    if isinstance(result, PreparedDirectPayment):
        return result
    return BuyRecordDTO(
        buy_record.order_bid,
        buy_record.user_bid,
        buy_record.paid_price,
        result.channel,
        result.qr_url,
        payment_channel=result.payment_channel,
        payment_payload=result.payment_payload,
        payment_action=result.payment_action,
    )


def _generate_pingxx_charge(**kwargs: Unpack[LearnerChargeArgs]) -> BuyRecordDTO:
    return _generate_registered_charge(provider_name="pingxx", **kwargs)


def _generate_stripe_charge(**kwargs: Unpack[LearnerChargeArgs]) -> BuyRecordDTO:
    return _generate_registered_charge(provider_name="stripe", **kwargs)


def _generate_direct_charge(
    *, provider_name: str, **kwargs: Unpack[LearnerChargeArgs]
) -> BuyRecordDTO:
    return _generate_registered_charge(provider_name=provider_name, **kwargs)


def sync_stripe_checkout_session(
    app: Flask,
    order_id: str,
    session_id: str | None = None,
    expected_user: str | None = None,
) -> dict[str, Any]:
    """Preserve the old public sync entry while delegating Stripe protocol handling."""
    from .learner_stripe import sync_stripe_checkout_session as synchronize

    return synchronize(
        app, order_id, session_id=session_id, expected_user=expected_user
    )


def sync_native_payment_order(
    app: Flask,
    order_id: str,
    *,
    expected_user: str | None = None,
    payment_channel: str | None = None,
) -> dict[str, Any]:
    """Synchronize native payment order."""
    uow.require_transaction_owner("payment synchronization", app)
    with _app_context_scope(app), unit_of_work(discard=True):
        order = _load_payment_sync_order(order_id, expected_user=expected_user)
        provider_name = (
            str(payment_channel or order.payment_channel or "").strip().lower()
        )
        if provider_name != str(order.payment_channel or "").strip().lower():
            raise_error("server.pay.payChannelNotSupport")
        provider_attempt_id = ""
        provider_attempt_row_id = None
        credential_context = None
        if provider_name in registered_native_payment_providers():
            if not payment_definition(provider_name).capabilities.query:
                return get_payment_details(app, order_id, expected_user=expected_user)
            native_model = native_snapshot_model(provider_name)
            snapshot = (
                legacy_native_snapshot_query(provider_name)
                .filter(native_model.order_bid == order.order_bid)
                .order_by(native_model.id.desc())
                .first()
            )
            if snapshot is None or not snapshot.provider_attempt_id:
                raise_error("server.order.orderNotFound")
            provider_attempt_id = str(snapshot.provider_attempt_id)
            provider_attempt_row_id = snapshot.id
            integration_bid = str(order.payment_integration_bid or "")
            if integration_bid:
                credential_context = resolve_provider_credential_context(
                    app,
                    creator_bid=str(order.creator_bid or ""),
                    provider=provider_name,
                    integration_bid=integration_bid,
                )
                if (
                    credential_context is None
                    or credential_context.integration_bid != integration_bid
                ):
                    raise_error("server.pay.payChannelNotSupport")

    from .learner_recovery import legacy_sync_handler

    legacy_handler = legacy_sync_handler(provider_name)
    if legacy_handler is not None:
        return legacy_handler(app, order_id, expected_user=expected_user)
    if provider_name not in registered_native_payment_providers():
        raise_error("server.pay.payChannelNotSupport")

    provider = get_payment_provider(provider_name)
    credential_scope = (
        config_overrides(build_provider_config_overrides(credential_context))
        if credential_context is not None
        else nullcontext()
    )
    with _app_context_scope(app), credential_scope:
        sync_result = provider.sync_reference(
            provider_reference=provider_attempt_id,
            reference_type=payment_definition(provider_name).operation_reference_type(
                "query"
            ),
            app=app,
        )

    with (
        _app_context_scope(app),
        payment_lifecycle_lock(order_id) as lifecycle_lease,
        unit_of_work(),
    ):
        order = _load_payment_sync_order(
            order_id,
            expected_user=expected_user,
            for_update=True,
        )
        current_provider = str(order.payment_channel or "").strip().lower()
        if current_provider != provider_name:
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
        if (
            snapshot is None
            or snapshot.id != provider_attempt_row_id
            or str(snapshot.provider_attempt_id or "") != provider_attempt_id
        ):
            raise_error("server.order.orderNotFound")

        event = describe_query(
            provider_name,
            sync_result,
            PaymentQueryTerms(
                provider_attempt_id,
                payment_definition(provider_name).operation_reference_type("query"),
                order.order_bid,
                order.user_bid,
                order.shifu_bid,
                reference_kind="payment",
            ),
        )
        facts = event.payment
        if not reported_payment_currency_matches(
            expected_currency=snapshot.currency,
            reported_currency=facts.currency,
        ):
            app.logger.warning(
                "Native payment sync currency mismatch provider=%s order_bid=%s",
                provider_name,
                order.order_bid,
            )
            return get_payment_details(app, order.order_bid)
        can_complete = purchase_attempt_can_complete(
            order_status=order.status,
            attempt_status=snapshot.status,
            current_attempt=purchase_attempt_matches(
                price=order.paid_price,
                attempt_amount=int(snapshot.amount or 0),
                attempt_id=snapshot.id,
                latest_id=provider_attempt_row_id,
            ),
        )
        if (
            facts.state == "paid"
            and not can_complete
            and order.status != ORDER_STATUS_SUCCESS
        ):
            return get_payment_details(app, order.order_bid)
        actual_amount = legacy_native_amount(facts)
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
        if facts.state == "paid" and amount_matches and can_complete:
            success_buy_record(app, order.order_bid)
        managed_refund = saved_refund_controls_state(
            event, _parse_json_payload(snapshot.metadata_json)
        )
        if amount_matches and purchase_attempt_matches(
            price=order.paid_price,
            attempt_amount=int(snapshot.amount or 0),
            attempt_id=snapshot.id,
            latest_id=provider_attempt_row_id,
        ):
            from .learner_refunds import reconcile_learner_refund

            attempt = latest_attempt(provider_name, order.order_bid, for_update=True)
            if attempt is not None and attempt.record.id == snapshot.id:
                reconcile_learner_refund(
                    order, attempt, event, sync_result.provider_payload
                )
        _apply_native_snapshot_update(
            snapshot=snapshot,
            notification=replace(sync_result, order_bid=provider_attempt_id),
            source="sync",
            facts=facts,
            project_status=not managed_refund,
        )
        db.session.add(snapshot)
        _assert_payment_lifecycle_lock_owned()
        lifecycle_lease.release_checked()
        return get_payment_details(app, order.order_bid)


def _load_payment_sync_order(
    order_id: str,
    *,
    expected_user: str | None,
    for_update: bool = False,
) -> Order:
    """Load one learner-owned order for provider synchronization."""
    query = Order.query.filter(
        Order.order_bid == order_id,
        Order.deleted == 0,
    ).order_by(Order.id.desc())
    if for_update:
        query = query.with_for_update()
    order = query.first()
    if not order:
        raise_error("server.order.orderNotFound")
    if expected_user and order.user_bid != expected_user:
        raise_error("server.order.orderNotFound")
    return order


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


def _stringify_payload(payload: object) -> str:
    if not payload:
        return "{}"
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload)


def _parse_json_payload(value: object) -> object:
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
    app: Flask, raw_body: bytes, sig_header: str, *, expected_integration_bid: str = ""
) -> tuple[dict[str, object], int]:
    """Preserve the signed legacy endpoint and its integration identity."""
    from .learner_stripe import handle_stripe_webhook as handle_signed_notification

    return handle_signed_notification(
        app, raw_body, sig_header, expected_integration_bid=expected_integration_bid
    )


def refund_order_payment(
    app: Flask,
    order_bid: str,
    amount: int | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Serialize refund requests independently from payment callbacks."""
    uow.require_transaction_owner("order refund", app)
    with (
        _app_context_scope(app),
        _learner_refund_lock(order_bid) as refund_lease,
    ):
        return _refund_order_payment_locked(
            app, order_bid, amount, reason, refund_lease
        )


def _refund_order_payment_locked(
    app: Flask,
    order_bid: str,
    amount: int | None,
    reason: str | None,
    refund_lease: _PaymentLifecycleLease,
) -> dict[str, object]:
    """Commit the request and receipt separately from local refund effects."""
    with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_bid):
        order = (
            Order.query.filter(Order.order_bid == order_bid)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if not order:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        provider = get_payment_provider(payment_channel)

        if not payment_definition(payment_channel).capabilities.refund:
            app.logger.error("Refund not implemented for channel: %s", payment_channel)
            raise_error("server.pay.payChannelNotSupport")

        attempt = latest_attempt(payment_channel, order_bid, for_update=True)
        if attempt is None:
            raise_error("server.order.orderNotFound")

        refund_amount = amount if amount is not None else attempt.amount
        original_attempt_amount = attempt.amount
        refund_key = f"order-refund:{order_bid}:{attempt.attempt_bid}:{refund_amount}"
        metadata_dict = attempt.metadata
        existing_operation = metadata_dict.get("refund_operation") or {}
        if existing_operation.get("status") in {"failed", "canceled"}:
            # Only a definitive rejection permits a new money operation.
            # Retain old receipts so their delayed events cannot claim a retry.
            history = list(metadata_dict.get("refund_operation_history") or [])
            metadata_dict["refund_operation_history"] = [*history, existing_operation]
            existing_operation = {}
            refund_key = f"{refund_key}:{get_uuid(app)}"
        elif existing_operation.get("amount") == refund_amount:
            # A retry of the new operation must keep its original random key,
            # including after an uncertain response or receipt commit failure.
            refund_key = existing_operation.get("idempotency_key") or refund_key
        if (
            existing_operation.get("idempotency_key") == refund_key
            and existing_operation.get("status") == "succeeded"
        ):
            return {
                "status": "succeeded",
                "order_bid": order_bid,
                "refund_id": existing_operation.get("provider_reference", ""),
                "amount": refund_amount,
            }
        if (
            existing_operation.get("status")
            in {"pending", "requires_action", "provider_completed"}
            and existing_operation.get("idempotency_key") != refund_key
        ):
            raise_error("server.order.orderStatusError")
        refund_attempt_bid = str(attempt.attempt_bid or "")
        request_metadata = attempt.refund_metadata(
            order_bid=order_bid, idempotency_key=refund_key
        )
        refund_request = PaymentRefundRequest(
            order_bid=order_bid,
            amount=refund_amount,
            reason=reason,
            metadata=request_metadata,
        )
        same_operation = existing_operation.get("idempotency_key") == refund_key
        if same_operation and existing_operation.get("request"):
            refund_request = PaymentRefundRequest(**existing_operation["request"])
        operation = dict(existing_operation) if same_operation else {}
        operation.update(
            idempotency_key=refund_key,
            status=operation.get("status") or "pending",
            amount=refund_amount,
            request=asdict(refund_request),
        )
        result = (
            PaymentRefundResult(**operation["response"])
            if operation.get("response")
            else None
        )
        metadata_dict["refund_operation"] = operation
        attempt.metadata = metadata_dict
        credential_context = None
        integration_bid = str(order.payment_integration_bid or "")
        if integration_bid:
            credential_context = resolve_provider_credential_context(
                app,
                creator_bid=str(order.creator_bid or ""),
                provider=payment_channel,
                integration_bid=integration_bid,
            )
            if (
                credential_context is None
                or credential_context.integration_bid != integration_bid
            ):
                raise_error("server.pay.payChannelNotSupport")
        _assert_payment_lifecycle_lock_owned()

    credential_scope = (
        config_overrides(build_provider_config_overrides(credential_context))
        if credential_context is not None
        else nullcontext()
    )
    if result is None:
        refund_lease.check_owned()
        with _app_context_scope(app), credential_scope:
            result = provider.refund_payment(request=refund_request, app=app)
        # Retain a known response even if ownership or later effects fail. Row
        # locking and the original operation key prevent replacing another claim.
        with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_bid):
            attempt = latest_attempt(
                payment_channel,
                order_bid,
                for_update=True,
                attempt_bid=refund_attempt_bid,
            )
            if attempt is None:
                raise_error("server.order.orderNotFound")
            metadata_dict = attempt.metadata
            operation = metadata_dict.get("refund_operation") or {}
            if operation.get("idempotency_key") != refund_key:
                raise_error("server.order.orderStatusError")
            if operation.get("response"):
                stored = PaymentRefundResult(**operation["response"])
                result = stored.merge_receipt(result)
                if result != stored:
                    operation.setdefault("initial_response", asdict(stored))
                    if str(stored.status or "").lower() not in {
                        "succeeded",
                        "failed",
                        "canceled",
                    }:
                        operation["status"] = (
                            "provider_completed"
                            if result.status == "succeeded"
                            else result.status
                            if result.status in {"failed", "canceled"}
                            else operation["status"]
                        )
                    operation.update(
                        response=asdict(result),
                        provider_reference=result.provider_reference,
                    )
                    attempt.metadata = {**metadata_dict, "refund_operation": operation}
            else:
                operation.update(status="provider_completed", response=asdict(result))
                attempt.metadata = {**metadata_dict, "refund_operation": operation}

    refund_lease.check_owned()
    with _app_context_scope(app), unit_of_work(), payment_lifecycle_lock(order_bid):
        order = (
            Order.query.filter(Order.order_bid == order_bid)
            .with_for_update()
            .populate_existing()
            .first()
        )
        attempt = latest_attempt(
            payment_channel, order_bid, for_update=True, attempt_bid=refund_attempt_bid
        )
        if not order or attempt is None:
            raise_error("server.order.orderNotFound")
        metadata_dict = attempt.metadata
        operation = metadata_dict.get("refund_operation") or {}
        if (
            operation.get("idempotency_key") != refund_key
            or order.payment_channel != payment_channel
            or attempt.amount != original_attempt_amount
        ):
            raise_error("server.order.orderStatusError")
        # A callback can commit after receipt persistence and before this lock.
        # Reconcile the freshly loaded evidence before projecting any outcome.
        if operation.get("response"):
            stored = PaymentRefundResult(**operation["response"])
            result = stored.merge_receipt(result)
            if result != stored:
                operation.setdefault("initial_response", asdict(stored))
        operation.update(
            {
                "status": result.status,
                "provider_reference": result.provider_reference,
                "response": asdict(result),
            }
        )
        metadata_dict["refund_operation"] = operation
        metadata_dict["last_refund_id"] = result.provider_reference
        attempt.metadata = metadata_dict
        attempt.persist_refund(result)

        refund_status = (result.status or "").lower()
        if refund_status == "succeeded":
            attempt.status = 2
            order.status = ORDER_STATUS_REFUND
        elif refund_status in {"pending", "requires_action"}:
            attempt.status = attempt.status or 1
        else:
            attempt.status = 4
        _assert_payment_lifecycle_lock_owned()

    return {
        "status": result.status,
        "order_bid": order_bid,
        "refund_id": result.provider_reference,
        "amount": refund_amount,
    }


def get_payment_details(
    app: Flask, order_bid: str, expected_user: str | None = None
) -> dict[str, object]:
    # Read-only: reuses the caller's session so reads inside an open unit of
    # work see that transaction's pending state.
    """Return payment details."""
    with _app_context_scope(app):
        order = Order.query.filter(
            Order.order_bid == order_bid,
            Order.deleted == 0,
        ).first()
        if not order:
            raise_error("server.order.orderNotFound")
        if expected_user and order.user_bid != expected_user:
            raise_error("server.order.orderNotFound")

        payment_channel = order.payment_channel or "pingxx"
        attempt = latest_attempt(payment_channel, order.order_bid)
        if attempt is None:
            raise_error("server.order.orderNotFound")
        return {
            "payment_channel": payment_channel,
            "course_id": order.shifu_bid,
            "order_bid": order_bid,
            "status": attempt.status,
        }


def success_buy_record_from_native(
    app: Flask,
    provider_name: str,
    notification: PaymentNotificationResult,
) -> bool:
    """Apply a successful native-payment notification to the purchase record."""
    uow.require_transaction_owner("native payment notification", app)
    with _app_context_scope(app), unit_of_work(discard=True):
        provider = str(provider_name or "").strip().lower()
        if provider not in registered_native_payment_providers():
            raise_error("server.pay.payChannelNotSupport")
        provider_attempt_id = str(notification.order_bid or "").strip()
        transaction_id = str(notification.charge_id or "").strip()
        native_model = native_snapshot_model(provider)
        query = legacy_native_snapshot_query(provider)
        if provider_attempt_id:
            native_order = (
                legacy_native_reference_query(provider, provider_attempt_id)
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
        order_bid = str(native_order.order_bid or "")
        native_order_id = native_order.id

    with (
        _app_context_scope(app),
        payment_lifecycle_lock(order_bid) as lifecycle_lease,
        unit_of_work(),
    ):
        buy_record: Order = (
            Order.query.filter(
                Order.order_bid == order_bid,
                Order.deleted == 0,
            )
            .with_for_update()
            .first()
        )
        if not buy_record:
            return False

        native_order = (
            native_model.query.filter(
                native_model.id == native_order_id,
                native_model.deleted == 0,
            )
            .with_for_update()
            .populate_existing()
            .first()
        )
        if native_order is None:
            return False

        event = describe_notification(provider, notification)
        facts = event.payment
        if not reported_payment_currency_matches(
            expected_currency=native_order.currency,
            reported_currency=facts.currency,
        ):
            message = "Native payment currency mismatch"
            raise RuntimeError(message)
        actual_amount = legacy_native_amount(facts)
        if actual_amount is not None and int(native_order.amount or 0) != actual_amount:
            message = "Native payment amount mismatch"
            raise RuntimeError(message)

        bind_native_notification_reference(provider, native_order, facts)
        was_pending_attempt = native_order.status == 0
        latest = (
            legacy_native_snapshot_query(provider)
            .filter(native_model.order_bid == native_order.order_bid)
            .order_by(native_model.id.desc())
            .with_entities(native_model.id)
            .first()
        )
        current = str(
            buy_record.payment_channel or ""
        ).strip().lower() == provider and purchase_attempt_matches(
            price=buy_record.paid_price,
            attempt_amount=int(native_order.amount or 0),
            attempt_id=native_order.id,
            latest_id=latest[0] if latest else None,
        )
        if facts.state == "paid" and purchase_attempt_can_complete(
            order_status=buy_record.status,
            attempt_status=0 if was_pending_attempt else native_order.status,
            current_attempt=current,
        ):
            success_buy_record(app, buy_record.order_bid)
        managed_refund = saved_refund_controls_state(
            event, _parse_json_payload(native_order.metadata_json)
        )
        if current:
            from .learner_refunds import reconcile_learner_refund

            attempt = latest_attempt(provider, buy_record.order_bid, for_update=True)
            if attempt is not None and attempt.record.id == native_order.id:
                reconcile_learner_refund(
                    buy_record, attempt, event, notification.provider_payload
                )
        _apply_native_snapshot_update(
            snapshot=native_order,
            notification=notification,
            source="webhook",
            facts=facts,
            project_status=not managed_refund,
        )
        db.session.add(native_order)
        _assert_payment_lifecycle_lock_owned()
        lifecycle_lease.release_checked()
        return True


def success_buy_record_from_pingxx(
    app: Flask, charge_id: str, body: dict
) -> AICourseBuyRecordDTO | None:
    """Keep the legacy callback entry point while protocol handling stays isolated."""
    from .learner_pingxx import success_buy_record_from_pingxx as apply_legacy_callback

    return apply_legacy_callback(app, charge_id, body)


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


class DiscountInfo:
    """Describe discounts applied to an order."""

    discount_value: str
    items: list[PayItemDto]

    def __init__(self, discount_value: object, items: object) -> None:
        """Capture the discount value and affected payment items."""
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
                is_discount=True,
                discount_code=None,
            )
        )
        current_discount_value += item_discount
        if promo_name:
            existing_price_names.add(promo_name)
    return items


def calculate_discount_value(
    price: decimal.Decimal,
    campaign_applications: list,
    discount_records: list[CouponUsageModel],
) -> DiscountInfo:
    """Calculate discount value."""
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
                    is_discount=True,
                    discount_code=None,
                )
            )
    if discount_records is not None and len(discount_records) > 0:
        discount_ids = [i.coupon_bid for i in discount_records]
        coupons: list[Coupon] = Coupon.query.filter(
            Coupon.coupon_bid.in_(discount_ids)
        ).all()
        coupon_maps: dict[str, Coupon] = {i.coupon_bid: i for i in coupons}
        for discount_record in discount_records:
            discount = coupon_maps.get(discount_record.coupon_bid)
            if discount:
                coupon_amount = decimal.Decimal(discount.value)
                if discount.discount_type == COUPON_TYPE_FIXED:
                    discount_value += coupon_amount
                elif discount.discount_type == COUPON_TYPE_PERCENT:
                    coupon_amount = calculate_percentage_amount(price, coupon_amount)
                    discount_value += coupon_amount
                items.append(
                    PayItemDto(
                        _("server.order.payItemCoupon"),
                        _resolve_coupon_display_name(discount),
                        coupon_amount,
                        is_discount=True,
                        discount_code=discount.code,
                    )
                )
    discount_value = min(discount_value, price)
    return DiscountInfo(discount_value, items)


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
                creator_bid=str(buy_record.creator_bid or ""),
            )

        raise_error("server.order.orderNotFound")
    return None


# Preserve historical helper imports used by integrations and regression tests.
__all__ = [
    "_apply_native_snapshot_update",
    "_extract_native_notification_amount",
    "_is_native_payment_successful",
    "_native_raw_status",
    "_native_snapshot_status",
]
