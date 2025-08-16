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

from .consts import (
    ORDER_STATUS_INIT,
)


class Order(db.Model):
    """
    Order
    """

    __tablename__ = "order_orders"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    order_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Order business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    payable_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Shifu original price"
    )
    paid_price = Column(
        Numeric(10, 2), nullable=False, default="0.00", comment="Paid price"
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=ORDER_STATUS_INIT,
        comment="Status of the order: 501=init, 502=paid, 503=refunded, 504=unpaid, 505=timeout",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )


class PingxxOrder(db.Model):
    """
    Pingxx Order
    """

    __tablename__ = "order_pingxx_orders"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    pingxx_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx order business identifier",
    )
    user_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="User business identifier",
    )
    shifu_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Shifu business identifier",
    )
    order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Order business identifier",
    )
    transaction_no = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx transaction number",
    )
    app_id = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx app identifier",
    )
    channel = Column(String(36), nullable=False, default="", comment="Payment channel")
    amount = Column(BIGINT, nullable=False, default="0.00", comment="Payment amount")
    currency = Column(String(36), nullable=False, default="CNY", comment="Currency")
    subject = Column(String(255), nullable=False, default="", comment="Payment subject")
    body = Column(String(255), nullable=False, default="", comment="Payment body")
    client_ip = Column(String(255), nullable=False, default="", comment="Client IP")
    extra = Column(Text, nullable=False, comment="Extra information")
    # Reconsider the design
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status of the order: 0=unpaid, 1=paid, 2=refunded, 3=closed, 4=failed",
    )
    charge_id = Column(
        String(255), nullable=False, index=True, default="", comment="Charge identifier"
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
        String(255), nullable=False, index=True, default="", comment="Refund identifier"
    )
    failure_code = Column(
        String(255), nullable=False, default="", comment="Failure code"
    )
    failure_msg = Column(
        String(255), nullable=False, default="", comment="Failure message"
    )
    charge_object = Column(Text, nullable=False, comment="Pingxx raw charge object")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )


class BannerInfo(db.Model):
    __tablename__ = "order_banner_info"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    banner_id = Column(
        String(36), nullable=False, default="", index=True, comment="Banner identifier"
    )
    course_id = Column(
        String(36), nullable=False, default="", index=True, comment="Course identifier"
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
        DateTime, nullable=False, default=func.now(), comment="Creation time"
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
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )
