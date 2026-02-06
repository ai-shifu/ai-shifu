from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    SmallInteger,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .consts import (
    COUPON_TYPE_FIXED,
    COUPON_APPLY_TYPE_ALL,
    COUPON_STATUS_ACTIVE,
    PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_STATUS_INACTIVE,
)


class Coupon(db.Model):
    """
    Coupon
    """

    __tablename__ = "promo_coupons"
    __table_args__ = {"comment": "Promo coupons"}
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
    __table_args__ = {"comment": "Promo coupon usages"}
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


class PromoCampaign(db.Model):
    """Promotion campaign definition."""

    __tablename__ = "promo_promos"
    __table_args__ = {
        "comment": (
            "Promotion campaign definition table. Defines a discount campaign for a specific "
            "Shifu (join/apply type, time window, discount configuration, channel, and targeting "
            "filter). Stores configuration only; user participation/claim/redemption records are "
            "stored in table promo_redemptions."
        )
    }

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    promo_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Promotion business identifier",
    )
    shifu_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Shifu business identifier",
    )
    name = Column(String(255), nullable=False, default="", comment="Promotion name")
    description = Column(
        Text, nullable=False, default="", comment="Promotion description"
    )
    apply_type = Column(
        SmallInteger,
        nullable=False,
        default=PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
        comment=(
            "Apply/join type: 2101=auto(eligible users get it automatically), "
            "2102=event(granted on specific events), 2103=manual(granted manually)"
        ),
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=PROMO_CAMPAIGN_STATUS_INACTIVE,
        index=True,
        comment="Status: 0=inactive, 1=active",
    )
    start_at = Column(
        DateTime,
        nullable=False,
        index=True,
        default=func.now(),
        comment="Promotion start time(inclusive)",
    )
    end_at = Column(
        DateTime,
        nullable=False,
        index=True,
        default=func.now(),
        comment="Promotion end time(recommended exclusive): start_at <= now < end_at",
    )
    discount_type = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_TYPE_FIXED,
        comment="Discount type: 701=fixed, 702=percent",
    )
    value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment=(
            "Discount value: interpreted by discount_type(fixed = amount off; percent = percentage off)"
        ),
    )
    channel = Column(
        String(36),
        nullable=False,
        default="",
        comment="Promotion channel(e.g., web/app/partner; business-defined)",
    )
    filter = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Promotion filter: JSON string for user/shifu targeting;{} means no restriction.",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Creation timestamp",
    )
    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )
    updated_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Last updater user business identifier",
    )


class PromoRedemption(db.Model):
    """Promotion campaign redemption ledger."""

    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint(
            "order_bid",
            "promo_bid",
            "deleted",
            name="uk_promo_campaign_application_order_campaign_deleted",
        ),
        {
            "comment": (
                "Promotion campaign redemption ledger. Records each time a user redeems/applies a "
                "promo campaign to an order, including snapshot fields (campaign name/discount "
                "type/value) and the computed discount amount. This table is transactional/"
                "immutable-by-intent; campaign definitions live in promo_promos."
            )
        },
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    redemption_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Promotion application business identifier",
    )
    promo_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Promotion business identifier",
    )
    order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Order business identifier",
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
    promo_name = Column(
        String(255), nullable=False, default="", comment="Promotion name snapshot"
    )
    discount_type = Column(
        SmallInteger,
        nullable=False,
        default=COUPON_TYPE_FIXED,
        comment="Discount type snapshot: 701=fixed, 702=percent",
    )
    value = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment="Discount value snapshot: interpreted by discount_type",
    )
    discount_amount = Column(
        Numeric(10, 2),
        nullable=False,
        default="0.00",
        comment=(
            "Discount amount actually applied to this order (computed result for this redemption)"
        ),
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=PROMO_CAMPAIGN_APPLICATION_STATUS_APPLIED,
        index=True,
        comment="Status: 4101=applied, 4102=voided",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
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
        onupdate=func.now(),
        comment="Last update timestamp",
    )
