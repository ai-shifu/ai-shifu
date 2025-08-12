from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    Numeric,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db

from .consts import BUY_STATUS_INIT


class Order(db.Model):
    """
    Order
    """

    __tablename__ = "order_orders"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    order_bid = Column(
        String(36), nullable=False, default="", comment="Order business ID", index=True
    )
    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Shifu business ID", index=True
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User business ID", index=True
    )
    payable_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Shifu original price"
    )
    paid_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Paid price"
    )
    status = Column(
        Integer,
        nullable=False,
        default=BUY_STATUS_INIT,
        comment="Status of the order: 501-init, 502-paid, 503-refunded, 504-unpaid, 505-timeout",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation timestamp",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )


class PingxxOrder(db.Model):
    """
    Pingxx Order
    """

    __tablename__ = "order_pingxx_orders"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    pingxx_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx Order Business ID",
    )
    user_bid = Column(
        String(36), index=True, nullable=False, default="", comment="User Business ID"
    )
    shifu_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Shifu Business ID"
    )
    order_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Order Business ID"
    )
    transaction_no = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx transaction number",
    )
    app_id = Column(
        String(36), index=True, nullable=False, default="", comment="Pingxx app ID"
    )
    channel = Column(String(36), nullable=False, default="", comment="Payment channel")
    channel = Column(String(36), nullable=False, default="", comment="Payment channel")
    amount = Column(BIGINT, nullable=False, default="0.00", comment="Payment amount")
    currency = Column(String(36), nullable=False, default="CNY", comment="Currency")
    subject = Column(String(255), nullable=False, default="", comment="Payment subject")
    body = Column(String(255), nullable=False, default="", comment="Payment body")
    order_no = Column(String(255), nullable=False, default="", comment="Order number")
    client_ip = Column(String(255), nullable=False, default="", comment="Client IP")
    extra = Column(Text, nullable=False, comment="Extra information")
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the order: 0-unpaid, 1-paid, 2-refunded, 3-closed, 4-failed",
    )
    charge_id = Column(
        String(255), nullable=False, index=True, default="", comment="Charge ID"
    )
    paid_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Payment time"
    )
    refunded_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Refund time"
    )
    closed_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Close time"
    )
    failed_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Failed time"
    )
    refund_id = Column(
        String(255), nullable=False, index=True, default="", comment="Refund ID"
    )
    failure_code = Column(
        String(255), nullable=False, default="", comment="Failure code"
    )
    failure_msg = Column(
        String(255), nullable=False, default="", comment="Failure message"
    )
    charge_object = Column(Text, nullable=False, comment="Pingxx's raw charge object")
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )


# 优惠券
class Coupon(db.Model):
    """
    Coupon
    """

    __tablename__ = "promo_coupons"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    coupon_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Coupon Business ID"
    )
    coupon_code = Column(
        String(36), index=True, nullable=False, default="", comment="Coupon code"
    )
    coupon_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Coupon type: 701-fixed, 702-percent",
    )
    coupon_apply_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Coupon apply type: 801: one coupon code for multiple times, 802: one coupon code for one time",
    )
    coupon_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Coupon value"
    )
    coupon_start = Column(
        DateTime, nullable=False, default=func.now(), comment="Coupon start time"
    )
    coupon_end = Column(
        DateTime, nullable=False, default=func.now(), comment="Coupon end time"
    )
    coupon_channel = Column(
        String(36), nullable=False, default="", comment="Discount channel"
    )
    coupon_filter = Column(Text, nullable=False, comment="Coupon filter")
    coupon_total_count = Column(
        BIGINT, nullable=False, default=0, comment="Coupon total count"
    )
    coupon_used_count = Column(
        BIGINT, nullable=False, default=0, comment="Coupon used count"
    )
    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the discount: 0-inactive, 1-active",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class CouponUsage(db.Model):
    """
    Coupon Usage Record
    Generated:

    1. Generated one when user use a coupon code that could be used multiple times
    2. Generated `coupon_total_count` when coupon that could be used multiple times is created
    """

    __tablename__ = "promo_coupon_usages"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    coupon_usage_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Coupon Usage Business ID",
    )
    coupon_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Coupon Business ID",
    )
    coupon_name = Column(String(255), nullable=False, default="", comment="Coupon name")
    user_bid = Column(
        String(36), index=True, nullable=False, default="", comment="User Business ID"
    )
    shifu_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Shifu Business ID"
    )
    order_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Order Business ID"
    )
    coupon_code = Column(String(36), nullable=False, default="", comment="Coupon Code")
    coupon_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Coupon Type: 701-fixed, 702-percent",
    )
    coupon_value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment="Coupon value: would be calculated to amount by coupon type",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the record: 901-inactive, 902-active, 903-used, 904-timeout",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class BannerInfo(db.Model):
    __tablename__ = "order_banner_info"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    banner_id = Column(
        String(36), nullable=False, default="", index=True, comment="Banner ID"
    )
    course_id = Column(
        String(36), nullable=False, default="", index=True, comment="Course ID"
    )
    show_banner = Column(Integer, nullable=False, default=0, comment="Show banner")
    show_lesson_banner = Column(
        Integer, nullable=False, default=0, comment="Show lesson banner"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )
