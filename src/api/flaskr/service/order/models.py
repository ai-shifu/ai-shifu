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

from .consts import BUY_STATUS_INIT, ATTEND_STATUS_LOCKED


# AI Shifu Order
class Order(db.Model):
    """
    Order Item
    """

    __tablename__ = "order_orders"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    order_bid = Column(
        String(36), nullable=False, default="", comment="Order Business ID", index=True
    )
    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Shifu Business ID", index=True
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User Business ID", index=True
    )
    order_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Order Price"
    )
    paid_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Paid Price"
    )
    status = Column(
        Integer,
        nullable=BUY_STATUS_INIT,
        default=0,
        comment="Status of the record: 501-init, 502-paid, 503-refunded, 504-to be paid, 505-timeout",
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


class LearnOutlineItemRecord(db.Model):
    """
    Shifu User Comsumption
    """

    __tablename__ = "learn_outlineitems_records"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    learn_outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Learn Outline Item Business ID",
        index=True,
    )

    shifu_bid = Column(
        String(36), nullable=False, default="", comment="Shifu Business ID", index=True
    )
    outline_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline Business ID",
        index=True,
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User Business ID", index=True
    )
    outline_updated = Column(
        Integer, nullable=False, default=0, comment="Usage is updated"
    )
    status = Column(
        Integer,
        nullable=False,
        default=ATTEND_STATUS_LOCKED,
        comment="Status of the comsumption: 601-not started, 602-in progress, 603-completed, 604-refund, 605-locked, 606-unavailable, 607-branch, 608-reset",
        index=True,
    )
    block_position_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="block position index of the comsumption",
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

    __tablename__ = "order_paychannel_pingxx_orders"
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
    pingxx_transaction_no = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx transaction number",
    )
    pingxx_app_id = Column(
        String(36), index=True, nullable=False, default="", comment="Pingxx app ID"
    )
    pingxx_channel = Column(
        String(36), nullable=False, default="", comment="Payment channel"
    )
    pingxx_id = Column(String(36), nullable=False, default="", comment="Pingxx ID")
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
    charge_id = Column(String(255), nullable=False, default="", comment="Charge ID")
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
    refund_id = Column(String(255), nullable=False, default="", comment="Refund ID")
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


# 折扣码
class Discount(db.Model):
    __tablename__ = "order_discounts"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    discount_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Discount UUID"
    )
    discount_code = Column(
        String(36), index=True, nullable=False, default="", comment="Discount code"
    )
    discount_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Discount type: 701-fixed, 702-percent",
    )
    discount_apply_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Discount apply type: 801: one discount code for multiple times, 802: one discount code for one time",
    )
    discount_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Discount value"
    )
    discount_start = Column(
        DateTime, nullable=False, default=func.now(), comment="Discount start time"
    )
    discount_end = Column(
        DateTime, nullable=False, default=func.now(), comment="Discount end time"
    )
    discount_channel = Column(
        String(36), nullable=False, default="", comment="Discount channel"
    )
    discount_filter = Column(Text, nullable=False, comment="Discount filter")
    discount_total_count = Column(
        BIGINT, nullable=False, default=0, comment="Discount total count"
    )
    discount_used_count = Column(
        BIGINT, nullable=False, default=0, comment="Discount used count"
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


class DiscountUsage(db.Model):
    """
    Discount Usage Record
    Generated:

    1. Generated one when user use a discount code that could be used multiple times
    2. Generated `discount_total_count` when discount that could be used multiple times is created
    """

    __tablename__ = "order_discount_usages"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    discount_usage_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Discount Usage Business ID",
    )
    discount_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Discount Business ID",
    )
    discount_name = Column(
        String(255), nullable=False, default="", comment="Discount name"
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
    discount_code = Column(
        String(36), nullable=False, default="", comment="Discount Code"
    )
    discount_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Discount Type: 701-fixed, 702-percent",
    )
    discount_value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment="Discount value: would be calculated to amount by discount type",
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
