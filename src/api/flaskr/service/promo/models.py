from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .consts import (
    COUPON_TYPE_FIXED,
    COUPON_APPLY_TYPE_ALL,
    COUPON_STATUS_ACTIVE,
)


class Coupon(db.Model):
    """
    Coupon
    """

    __tablename__ = "promo_coupons"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    coupon_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Coupon business identifier",
    )
    code = Column(
        String(36), index=True, nullable=False, default="", comment="Coupon code"
    )
    discount_type = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_TYPE_FIXED,
        comment="Coupon type: 701=fixed, 702=percent",
    )
    usage_type = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_APPLY_TYPE_ALL,
        comment="Coupon apply type: 801=one coupon code for multiple times, 802=one coupon code for one time",
    )
    value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment="Coupon value: would be calculated to amount by coupon type",
    )
    start = Column(
        DateTime, nullable=False, default=func.now(), comment="Coupon start time"
    )
    end = Column(
        DateTime, nullable=False, default=func.now(), comment="Coupon end time"
    )
    channel = Column(String(36), nullable=False, default="", comment="Coupon channel")
    filter = Column(
        Text,
        nullable=False,
        comment="Coupon filter: would be used to filter user and shifu",
    )
    total_count = Column(
        BIGINT, nullable=False, default=0, comment="Coupon total count"
    )
    used_count = Column(BIGINT, nullable=False, default=0, comment="Coupon used count")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status of the discount: 0=inactive, 1=active",
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
        server_default=func.now(),
        comment="Creation timestamp",
    )
    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Update timestamp",
    )


class CouponUsage(db.Model):
    """
    Coupon Usage Record
    Generated:

    1. Generated one when user use a coupon code that could be used multiple times
    2. Generated `coupon_total_count` when coupon that could be used multiple times is created
    """

    __tablename__ = "promo_coupon_usages"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    coupon_usage_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Coupon usage business identifier",
    )
    coupon_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Coupon business identifier",
    )
    name = Column(String(255), nullable=False, default="", comment="Coupon name")
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
    code = Column(String(36), nullable=False, default="", comment="Coupon code")
    discount_type = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_TYPE_FIXED,
        comment="Coupon Type: 701=fixed, 702=percent",
    )
    value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment="Coupon value: would be calculated to amount by coupon type",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_STATUS_ACTIVE,
        comment="Status of the record: 901=inactive, 902=active, 903=used, 904=timeout",
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
        server_default=func.now(),
        comment="Creation timestamp",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Update timestamp",
    )
