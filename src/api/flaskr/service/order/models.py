from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Text,
    Numeric,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


# AI Shifu Order
class OrderItem(db.Model):
    """
    Order Item
    """

    __tablename__ = "order_items"

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
    price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Price of the course"
    )
    pay_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Payment value"
    )
    discount_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Discount value"
    )
    created = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the record: 501-unpaid, 502-paid, 503-refunded, 504-closed, 505-failed",
    )


class ShifuUserComsumptionRecord(db.Model):
    """
    Shifu User Comsumption
    """

    __tablename__ = "shifu_user_comsumption_records"

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    usage_bid = Column(
        String(36), nullable=False, default="", comment="Usage Business ID", index=True
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
    outline_postion = Column(
        String(36), nullable=False, default="", comment="Outline postion"
    )
    outline_name = Column(
        String(36), nullable=False, default="", comment="Outline name"
    )
    user_bid = Column(
        String(36), nullable=False, default="", comment="User UUID", index=True
    )
    outline_updated = Column(
        Integer, nullable=False, default=0, comment="Usage is  updated"
    )

    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the comsumption: 601-not started, 602-in progress, 603-completed, 604-refund, 605-locked, 606-unavailable, 607-branch, 608-reset",
        index=True,
    )
    block_position_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="block position index of the comsumption",
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class PingxxOrder(db.Model):
    __tablename__ = "order_paychannel_pingxx_orders"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    pingxx_order_bid = Column(
        String(36), index=True, nullable=False, default="", comment="Pingxx Order Business ID"
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
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the order: 0-unpaid, 1-paid, 2-refunded, 3-closed, 4-failed",
    )
    charge_id = Column(String(255), nullable=False, default="", comment="Charge ID")
    paid_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Payment time"
    )
    refunded_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Refund time"
    )
    closed_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Close time"
    )
    failed_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Failed time"
    )
    refund_id = Column(String(255), nullable=False, default="", comment="Refund ID")
    failure_code = Column(
        String(255), nullable=False, default="", comment="Failure code"
    )
    failure_msg = Column(
        String(255), nullable=False, default="", comment="Failure message"
    )
    charge_object = Column(Text, nullable=False, comment="Charge object")


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
        comment="Discount apply type: 801-all, 802-specific",
    )
    discount_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Discount value"
    )
    discount_limit = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Discount limit"
    )
    discount_start = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Discount start time"
    )
    discount_end = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Discount end time"
    )
    discount_channel = Column(
        String(36), nullable=False, default="", comment="Discount channel"
    )
    discount_filter = Column(Text, nullable=False, comment="Discount filter")
    discount_count = Column(BIGINT, nullable=False, default=0, comment="Discount count")
    discount_used = Column(BIGINT, nullable=False, default=0, comment="Discount used")
    discount_generated_user = Column(
        String(36), nullable=False, default="", comment="Discount generated user"
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the discount: 0-inactive, 1-active",
    )


class DiscountUsageRecord(db.Model):
    """
    Discount Usage Record
    """

    __tablename__ = "order_discount_usage_records"
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
        Integer, nullable=False, default=0, comment="Discount Type: 0-percent, 1-amount"
    )
    discount_value = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Discount value"
    )
    status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Status of the record: 901-inactive, 902-active, 903-used, 904-timeout",
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
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
