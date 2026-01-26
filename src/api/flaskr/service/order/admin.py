from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from collections import defaultdict
import re
from typing import Any, Dict, List, Optional

from flask import Flask

from flaskr.service.active.consts import (
    ACTIVE_JOIN_STATUS_ENABLE,
    ACTIVE_JOIN_STATUS_FAILURE,
)
from flaskr.service.active.models import ActiveUserRecord
from flaskr.dao import db
from flaskr.service.common.dtos import (
    PageNationDTO,
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.common.models import (
    AppException,
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.order.admin_dtos import (
    OrderAdminActivityDTO,
    OrderAdminCouponDTO,
    OrderAdminDetailDTO,
    OrderAdminPaymentDTO,
    OrderAdminSummaryDTO,
)
from flaskr.service.order.funs import init_buy_record, success_buy_record
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import Order, PingxxOrder, StripeOrder
from flaskr.service.promo.consts import (
    COUPON_STATUS_ACTIVE,
    COUPON_STATUS_INACTIVE,
    COUPON_STATUS_TIMEOUT,
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
)
from flaskr.service.promo.models import CouponUsage
from flaskr.service.shifu.models import DraftShifu
from flaskr.service.shifu.shifu_draft_funcs import get_user_created_shifu_bids
from flaskr.service.shifu.utils import get_shifu_creator_bid
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    get_user_entity_by_bid,
    update_user_entity_fields,
    upsert_credential,
)


ORDER_STATUS_KEY_MAP = {
    ORDER_STATUS_INIT: "server.order.orderStatusInit",
    ORDER_STATUS_SUCCESS: "server.order.orderStatusSuccess",
    ORDER_STATUS_REFUND: "server.order.orderStatusRefund",
    ORDER_STATUS_TO_BE_PAID: "server.order.orderStatusToBePaid",
    ORDER_STATUS_TIMEOUT: "server.order.orderStatusTimeout",
}

PAYMENT_STATUS_KEY_MAP = {
    0: "module.order.paymentStatus.pending",
    1: "module.order.paymentStatus.paid",
    2: "module.order.paymentStatus.refunded",
    3: "module.order.paymentStatus.closed",
    4: "module.order.paymentStatus.failed",
}

ACTIVE_STATUS_KEY_MAP = {
    ACTIVE_JOIN_STATUS_ENABLE: "module.order.activeStatus.active",
    ACTIVE_JOIN_STATUS_FAILURE: "module.order.activeStatus.failed",
}

COUPON_STATUS_KEY_MAP = {
    COUPON_STATUS_INACTIVE: "module.order.couponStatus.inactive",
    COUPON_STATUS_ACTIVE: "module.order.couponStatus.active",
    COUPON_STATUS_USED: "module.order.couponStatus.used",
    COUPON_STATUS_TIMEOUT: "module.order.couponStatus.timeout",
}

COUPON_TYPE_KEY_MAP = {
    COUPON_TYPE_FIXED: "module.order.couponType.fixed",
    COUPON_TYPE_PERCENT: "module.order.couponType.percent",
}

PAYMENT_CHANNEL_KEY_MAP = {
    "pingxx": "module.order.paymentChannel.pingxx",
    "stripe": "module.order.paymentChannel.stripe",
    "manual": "module.order.paymentChannel.manual",
}

MOBILE_PATTERN = re.compile(r"^\d{11}$")


def normalize_mobile(mobile: str) -> str:
    """Normalize and validate a mobile number (11 digits)."""
    normalized_mobile = str(mobile or "").strip()
    if not normalized_mobile:
        raise_param_error("mobile")
    if not MOBILE_PATTERN.fullmatch(normalized_mobile):
        raise_param_error(f"mobile format invalid: {normalized_mobile}")
    return normalized_mobile


def _format_decimal(value: Optional[Decimal]) -> str:
    """Format a Decimal or numeric string to trimmed two-decimal string."""
    if value is None:
        return "0"
    if isinstance(value, str):
        normalized = value
    else:
        normalized = "{0:.2f}".format(value)
    if normalized.endswith(".00"):
        return normalized[:-3]
    return normalized


def _format_cents(value: Optional[int]) -> str:
    """Convert cents integer to string representation in units."""
    if value is None:
        return "0"
    try:
        return _format_decimal(Decimal(value) / Decimal(100))
    except (ArithmeticError, ValueError):
        return "0"


def _format_datetime(value: Optional[datetime]) -> str:
    """Format datetime to standard string."""
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: str, is_end: bool = False) -> Optional[datetime]:
    """Parse date/time string with multiple formats; auto fill day bounds."""
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                if is_end:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                else:
                    parsed = parsed.replace(hour=0, minute=0, second=0)
            return parsed
        except ValueError:
            continue
    return None


def _load_shifu_map(shifu_bids: list[str]) -> Dict[str, DraftShifu]:
    """Load latest draft shifu records for given bids and map by bid."""
    if not shifu_bids:
        return {}
    shifu_drafts = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid.in_(shifu_bids),
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .all()
    )
    shifu_map: Dict[str, DraftShifu] = {}
    for shifu in shifu_drafts:
        if shifu.shifu_bid and shifu.shifu_bid not in shifu_map:
            shifu_map[shifu.shifu_bid] = shifu
    return shifu_map


def _load_user_map(user_bids: list[str]) -> Dict[str, Dict[str, str]]:
    """Load user mobile/nickname info for given user bids."""
    if not user_bids:
        return {}
    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(user_bids),
            AuthCredential.provider_name == "phone",
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    for credential in credentials:
        if credential.user_bid and credential.user_bid not in phone_map:
            phone_map[credential.user_bid] = credential.identifier or ""

    users = UserEntity.query.filter(UserEntity.user_bid.in_(user_bids)).all()
    user_map: Dict[str, Dict[str, str]] = {}
    for user in users:
        mobile = phone_map.get(user.user_bid, "")
        if not mobile and (user.user_identify or "").isdigit():
            mobile = user.user_identify
        user_map[user.user_bid] = {
            "mobile": mobile or "",
            "nickname": user.nickname or "",
            "identify": user.user_identify or "",
        }
    return user_map


def _load_coupon_code_map(order_bids: list[str]) -> Dict[str, List[str]]:
    """Load coupon codes for given orders and map by order bid."""
    if not order_bids:
        return {}
    records = (
        CouponUsage.query.filter(
            CouponUsage.order_bid.in_(order_bids),
            CouponUsage.deleted == 0,
        )
        .order_by(CouponUsage.id.desc())
        .all()
    )
    coupon_map: Dict[str, List[str]] = defaultdict(list)
    for record in records:
        order_bid = record.order_bid or ""
        code = record.code or ""
        if not order_bid or not code:
            continue
        if code in coupon_map[order_bid]:
            continue
        coupon_map[order_bid].append(code)
    return dict(coupon_map)


def _build_order_item(
    order: Order,
    shifu_map: Dict[str, DraftShifu],
    user_map: Dict[str, Dict[str, str]],
    coupon_map: Optional[Dict[str, List[str]]] = None,
) -> OrderAdminSummaryDTO:
    """Build admin order summary DTO from order plus shifu/user lookups."""
    shifu = shifu_map.get(order.shifu_bid)
    user = user_map.get(order.user_bid, {})
    payment_channel = order.payment_channel or ""
    status_key = ORDER_STATUS_KEY_MAP.get(order.status, "server.order.orderStatusInit")
    coupon_codes = []
    if coupon_map is not None:
        coupon_codes = coupon_map.get(order.order_bid, []) or []
    return OrderAdminSummaryDTO(
        order_bid=order.order_bid,
        shifu_bid=order.shifu_bid,
        shifu_name=shifu.title if shifu else "",
        user_bid=order.user_bid,
        user_mobile=user.get("mobile", ""),
        user_nickname=user.get("nickname", ""),
        payable_price=_format_decimal(order.payable_price),
        paid_price=_format_decimal(order.paid_price),
        discount_amount=_format_decimal(
            Decimal(order.payable_price or 0) - Decimal(order.paid_price or 0)
        ),
        status=order.status,
        status_key=status_key,
        payment_channel=payment_channel,
        payment_channel_key=PAYMENT_CHANNEL_KEY_MAP.get(
            payment_channel, "module.order.paymentChannel.unknown"
        ),
        coupon_codes=coupon_codes,
        created_at=_format_datetime(order.created_at),
        updated_at=_format_datetime(order.updated_at),
    )


def import_activation_order(
    app: Flask,
    mobile: str,
    course_id: str,
    user_nick_name: Optional[str] = None,
) -> Dict[str, str]:
    """Create activation order for a mobile user and shifu (manual import)."""
    with app.app_context():
        normalized_mobile = normalize_mobile(mobile)

        normalized_course_id = str(course_id or "").strip()
        if not normalized_course_id:
            raise_param_error("course_id")

        normalized_nickname = str(user_nick_name or "").strip()
        defaults = {
            "identify": normalized_mobile,
            "nickname": normalized_nickname or normalized_mobile,
            "language": "en-US",
            "state": USER_STATE_REGISTERED,
        }
        aggregate, _ = ensure_user_for_identifier(
            app,
            provider="phone",
            identifier=normalized_mobile,
            defaults=defaults,
        )

        if not aggregate:
            raise_error("server.user.userNotFound")

        user_id = aggregate.user_bid

        existing_success_order = (
            Order.query.filter(
                Order.user_bid == user_id,
                Order.shifu_bid == normalized_course_id,
                Order.status == ORDER_STATUS_SUCCESS,
                Order.deleted == 0,
            )
            .order_by(Order.id.desc())
            .first()
        )
        if existing_success_order:
            raise_error_with_args(
                "server.order.mobileAlreadyActivated", mobile=normalized_mobile
            )

        entity = get_user_entity_by_bid(user_id, include_deleted=True)
        if entity:
            updates = {"identify": normalized_mobile}
            if normalized_nickname:
                updates["nickname"] = normalized_nickname
            if aggregate.state == USER_STATE_UNREGISTERED:
                updates["state"] = USER_STATE_REGISTERED
            update_user_entity_fields(entity, **updates)

        upsert_credential(
            app,
            user_bid=user_id,
            provider_name="phone",
            subject_id=normalized_mobile,
            subject_format="phone",
            identifier=normalized_mobile,
            metadata={"course_id": normalized_course_id},
            verified=True,
        )
        db.session.commit()

        buy_record = init_buy_record(app, user_id, normalized_course_id)
        order = Order.query.filter(Order.order_bid == buy_record.order_id).first()
        if not order:
            raise_error("server.order.orderNotFound")

        order.payable_price = Decimal("0")
        order.paid_price = Decimal("0")
        order.payment_channel = "manual"
        db.session.commit()

        success_buy_record(app, order.order_bid)

        return {"order_bid": order.order_bid}


def import_activation_orders(
    app: Flask,
    mobiles: List[str],
    course_id: str,
    user_nick_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Bulk import activation orders from a list of mobile numbers."""
    results: Dict[str, Any] = {"success": [], "failed": []}
    for mobile in mobiles:
        normalized_mobile = str(mobile or "").strip()
        try:
            order = import_activation_order(
                app, normalized_mobile, course_id, user_nick_name
            )
            results["success"].append({"mobile": normalized_mobile, **order})
        except AppException as exc:
            if hasattr(app, "logger"):
                app.logger.warning(
                    "import activation failed for %s: %s",
                    normalized_mobile,
                    exc.message,
                )
            results["failed"].append(
                {"mobile": normalized_mobile, "message": exc.message}
            )
        except Exception as exc:  # noqa: BLE001
            if hasattr(app, "logger"):
                app.logger.exception(
                    "import activation unexpected failure for %s", normalized_mobile
                )
            results["failed"].append({"mobile": normalized_mobile, "message": str(exc)})
    return results


def list_orders(
    app: Flask,
    user_id: str,
    page_index: int,
    page_size: int,
    filters: Optional[Dict[str, Any]] = None,
) -> PageNationDTO:
    """List orders visible to the current operator with optional filters."""
    with app.app_context():
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)
        filters = filters or {}

        shifu_bids = get_user_created_shifu_bids(app, user_id)
        if not shifu_bids:
            return PageNationDTO(page_index, page_size, 0, [])

        query = Order.query.filter(
            Order.deleted == 0,
            Order.shifu_bid.in_(shifu_bids),
        )

        order_bid = filters.get("order_bid")
        if order_bid:
            query = query.filter(Order.order_bid == order_bid)

        user_bid = filters.get("user_bid")
        if user_bid:
            identify_value = str(user_bid).strip()
            if identify_value:
                matched_user_bids = [
                    user.user_bid
                    for user in UserEntity.query.filter(
                        UserEntity.user_identify == identify_value
                    ).all()
                ]
                if matched_user_bids:
                    query = query.filter(Order.user_bid.in_(matched_user_bids))
                else:
                    query = query.filter(Order.user_bid == identify_value)

        shifu_bid = filters.get("shifu_bid")
        if shifu_bid:
            if isinstance(shifu_bid, list):
                shifu_bid_list = [
                    str(bid).strip() for bid in shifu_bid if str(bid).strip()
                ]
            else:
                shifu_bid_list = [
                    bid.strip() for bid in str(shifu_bid).split(",") if bid.strip()
                ]
            if shifu_bid_list:
                allowed_bids = [bid for bid in shifu_bid_list if bid in shifu_bids]
                if not allowed_bids:
                    return PageNationDTO(page_index, page_size, 0, [])
                query = query.filter(Order.shifu_bid.in_(allowed_bids))

        status = filters.get("status")
        if status is not None and str(status).isdigit():
            query = query.filter(Order.status == int(status))

        payment_channel = filters.get("payment_channel")
        if payment_channel:
            query = query.filter(Order.payment_channel == payment_channel)

        start_time = _parse_datetime(filters.get("start_time", ""))
        if start_time:
            query = query.filter(Order.created_at >= start_time)

        end_time = _parse_datetime(filters.get("end_time", ""), is_end=True)
        if end_time:
            query = query.filter(Order.created_at <= end_time)

        total = query.count()
        orders = (
            query.order_by(Order.created_at.desc())
            .offset((page_index - 1) * page_size)
            .limit(page_size)
            .all()
        )

        shifu_map = _load_shifu_map([order.shifu_bid for order in orders])
        user_map = _load_user_map([order.user_bid for order in orders])
        coupon_map = _load_coupon_code_map([order.order_bid for order in orders])

        items = [
            _build_order_item(order, shifu_map, user_map, coupon_map)
            for order in orders
        ]
        return PageNationDTO(page_index, page_size, total, items)


def _load_order_activities(order_bid: str) -> List[OrderAdminActivityDTO]:
    """Load activity records tied to an order and format as DTOs."""
    records = ActiveUserRecord.query.filter(
        ActiveUserRecord.order_id == order_bid
    ).all()
    activities: List[OrderAdminActivityDTO] = []
    for record in records:
        activities.append(
            OrderAdminActivityDTO(
                active_id=record.active_id,
                active_name=record.active_name,
                price=_format_decimal(record.price),
                status=record.status,
                status_key=ACTIVE_STATUS_KEY_MAP.get(
                    record.status, "module.order.activeStatus.unknown"
                ),
                created_at=_format_datetime(record.created),
                updated_at=_format_datetime(record.updated),
            )
        )
    return activities


def _load_order_coupons(order_bid: str) -> List[OrderAdminCouponDTO]:
    """Load coupon usage records tied to an order and format as DTOs."""
    records = CouponUsage.query.filter(
        CouponUsage.order_bid == order_bid,
        CouponUsage.deleted == 0,
    ).all()
    coupons: List[OrderAdminCouponDTO] = []
    for record in records:
        coupons.append(
            OrderAdminCouponDTO(
                coupon_bid=record.coupon_bid,
                code=record.code,
                name=record.name,
                discount_type=record.discount_type,
                discount_type_key=COUPON_TYPE_KEY_MAP.get(
                    record.discount_type, "module.order.couponType.unknown"
                ),
                value=_format_decimal(record.value),
                status=record.status,
                status_key=COUPON_STATUS_KEY_MAP.get(
                    record.status, "module.order.couponStatus.unknown"
                ),
                created_at=_format_datetime(record.created_at),
                updated_at=_format_datetime(record.updated_at),
            )
        )
    return coupons


def _load_payment_detail(order: Order) -> Optional[OrderAdminPaymentDTO]:
    """Build payment detail DTO from channel-specific order records."""
    payment_channel = order.payment_channel or ""
    if payment_channel == "stripe":
        stripe_order = (
            StripeOrder.query.filter(
                StripeOrder.order_bid == order.order_bid,
                StripeOrder.deleted == 0,
            )
            .order_by(StripeOrder.id.desc())
            .first()
        )
        if not stripe_order:
            return None
        return OrderAdminPaymentDTO(
            payment_channel="stripe",
            payment_channel_key=PAYMENT_CHANNEL_KEY_MAP.get(
                "stripe", "module.order.paymentChannel.unknown"
            ),
            status=stripe_order.status,
            status_key=PAYMENT_STATUS_KEY_MAP.get(
                stripe_order.status, "module.order.paymentStatus.unknown"
            ),
            amount=_format_cents(stripe_order.amount),
            currency=stripe_order.currency,
            payment_intent_id=stripe_order.payment_intent_id or "",
            checkout_session_id=stripe_order.checkout_session_id or "",
            latest_charge_id=stripe_order.latest_charge_id or "",
            receipt_url=stripe_order.receipt_url or "",
            payment_method=stripe_order.payment_method or "",
            created_at=_format_datetime(stripe_order.created_at),
            updated_at=_format_datetime(stripe_order.updated_at),
        )

    if payment_channel == "pingxx":
        pingxx_order = (
            PingxxOrder.query.filter(
                PingxxOrder.order_bid == order.order_bid,
                PingxxOrder.deleted == 0,
            )
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        if not pingxx_order:
            return None
        return OrderAdminPaymentDTO(
            payment_channel="pingxx",
            payment_channel_key=PAYMENT_CHANNEL_KEY_MAP.get(
                "pingxx", "module.order.paymentChannel.unknown"
            ),
            status=pingxx_order.status,
            status_key=PAYMENT_STATUS_KEY_MAP.get(
                pingxx_order.status, "module.order.paymentStatus.unknown"
            ),
            amount=_format_cents(pingxx_order.amount),
            currency=pingxx_order.currency,
            transaction_no=pingxx_order.transaction_no or "",
            charge_id=pingxx_order.charge_id or "",
            channel=pingxx_order.channel or "",
            created_at=_format_datetime(pingxx_order.created_at),
            updated_at=_format_datetime(pingxx_order.updated_at),
        )

    return None


def get_order_detail(app: Flask, user_id: str, order_bid: str) -> OrderAdminDetailDTO:
    """Return admin order detail after permission check for the operator."""
    with app.app_context():
        order = Order.query.filter(
            Order.order_bid == order_bid,
            Order.deleted == 0,
        ).first()
        if not order:
            raise_error("server.order.orderNotFound")
        creator_bid = get_shifu_creator_bid(app, order.shifu_bid)
        if creator_bid != user_id:
            raise_error("server.shifu.noPermission")

        shifu_map = _load_shifu_map([order.shifu_bid])
        user_map = _load_user_map([order.user_bid])
        coupon_map = _load_coupon_code_map([order.order_bid])
        summary = _build_order_item(order, shifu_map, user_map, coupon_map)
        payment_detail = _load_payment_detail(order)
        if not payment_detail:
            payment_channel = order.payment_channel or ""
            payment_detail = OrderAdminPaymentDTO(
                payment_channel=payment_channel,
                payment_channel_key=PAYMENT_CHANNEL_KEY_MAP.get(
                    payment_channel, "module.order.paymentChannel.unknown"
                ),
                status=0,
                status_key="module.order.paymentStatus.unknown",
                amount="0",
                currency="",
            )

        return OrderAdminDetailDTO(
            order=summary,
            activities=_load_order_activities(order.order_bid),
            coupons=_load_order_coupons(order.order_bid),
            payment=payment_detail,
        )
