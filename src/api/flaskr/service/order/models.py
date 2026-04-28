from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    Numeric,
    SmallInteger,
    DateTime,
    Index,
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
    __table_args__ = {"comment": "Order orders"}
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
    payment_channel = Column(
        String(50),
        nullable=False,
        default="pingxx",
        comment="Payment channel",
        index=True,
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
    __table_args__ = (
        Index(
            "ix_order_pingxx_orders_biz_domain_order_bid",
            "biz_domain",
            "order_bid",
        ),
        Index(
            "ix_order_pingxx_orders_biz_domain_bill_order_bid",
            "biz_domain",
            "bill_order_bid",
        ),
        {"comment": "Order pingxx orders"},
    )
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    pingxx_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Pingxx order business identifier",
    )
    biz_domain = Column(
        String(16),
        index=True,
        nullable=False,
        default="order",
        comment="Business domain",
    )
    bill_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Billing order business identifier",
    )
    creator_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Creator business identifier",
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


class StripeOrder(db.Model):
    """
    Stripe Order
    """

    __tablename__ = "order_stripe_orders"
    __table_args__ = (
        Index(
            "ix_order_stripe_orders_biz_domain_order_bid",
            "biz_domain",
            "order_bid",
        ),
        Index(
            "ix_order_stripe_orders_biz_domain_bill_order_bid",
            "biz_domain",
            "bill_order_bid",
        ),
        {"comment": "Order stripe orders"},
    )
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    stripe_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Stripe order business identifier",
    )
    biz_domain = Column(
        String(16),
        index=True,
        nullable=False,
        default="order",
        comment="Business domain",
    )
    bill_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Billing order business identifier",
    )
    creator_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Creator business identifier",
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
    payment_intent_id = Column(
        String(255),
        nullable=False,
        index=True,
        default="",
        comment="Stripe payment intent identifier",
    )
    checkout_session_id = Column(
        String(255),
        nullable=False,
        index=True,
        default="",
        comment="Stripe checkout session identifier",
    )
    latest_charge_id = Column(
        String(255),
        nullable=False,
        index=True,
        default="",
        comment="Latest Stripe charge identifier",
    )
    amount = Column(
        BIGINT, nullable=False, default=0, comment="Payment amount in cents"
    )
    currency = Column(String(36), nullable=False, default="usd", comment="Currency")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status of the order: 0=pending, 1=paid, 2=refunded, 3=closed, 4=failed",
    )
    receipt_url = Column(
        String(255),
        nullable=False,
        default="",
        comment="Stripe receipt URL",
    )
    payment_method = Column(
        String(255),
        nullable=False,
        default="",
        comment="Stripe payment method identifier",
    )
    failure_code = Column(
        String(255), nullable=False, default="", comment="Failure code"
    )
    failure_message = Column(
        String(255), nullable=False, default="", comment="Failure message"
    )
    metadata_json = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Stripe metadata JSON string",
    )
    payment_intent_object = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Stripe payment intent raw object",
    )
    checkout_session_object = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Stripe checkout session raw object",
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


class _NativeProviderOrderBase(db.Model):
    """
    Common raw native payment snapshot fields.
    """

    __abstract__ = True
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    biz_domain = Column(
        String(16),
        index=True,
        nullable=False,
        default="order",
        comment="Business domain",
    )
    bill_order_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Billing order business identifier",
    )
    creator_bid = Column(
        String(36),
        index=True,
        nullable=False,
        default="",
        comment="Creator business identifier",
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
    provider_attempt_id = Column(
        String(64),
        index=True,
        nullable=False,
        default="",
        comment="Provider-side merchant order identifier",
    )
    transaction_id = Column(
        String(128),
        index=True,
        nullable=False,
        default="",
        comment="Provider transaction identifier",
    )
    channel = Column(String(36), nullable=False, default="", comment="Payment channel")
    amount = Column(BIGINT, nullable=False, default=0, comment="Payment amount")
    currency = Column(String(36), nullable=False, default="CNY", comment="Currency")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Status of the order: 0=pending, 1=paid, 2=refunded, 3=closed, 4=failed",
    )
    raw_status = Column(
        String(64),
        nullable=False,
        default="",
        comment="Provider raw status or event type",
    )
    raw_request = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Raw provider request payload",
    )
    raw_response = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Raw provider response payload",
    )
    raw_notification = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Raw provider notification payload",
    )
    metadata_json = Column(
        Text,
        nullable=False,
        default="{}",
        comment="Provider metadata JSON string",
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


class AlipayOrder(_NativeProviderOrderBase):
    """
    Raw direct Alipay payment snapshot.
    """

    __tablename__ = "order_alipay_orders"
    __table_args__ = (
        Index(
            "ix_order_alipay_orders_biz_domain_order_bid",
            "biz_domain",
            "order_bid",
        ),
        Index(
            "ix_order_alipay_orders_biz_domain_bill_order_bid",
            "biz_domain",
            "bill_order_bid",
        ),
        {"comment": "Order Alipay payment provider snapshots"},
    )
    alipay_order_bid = Column(
        String(36),
        index=True,
        unique=True,
        nullable=False,
        default="",
        comment="Alipay payment snapshot business identifier",
    )


class WechatPayOrder(_NativeProviderOrderBase):
    """
    Raw direct WeChat Pay payment snapshot.
    """

    __tablename__ = "order_wechatpay_orders"
    __table_args__ = (
        Index(
            "ix_order_wechatpay_orders_biz_domain_order_bid",
            "biz_domain",
            "order_bid",
        ),
        Index(
            "ix_order_wechatpay_orders_biz_domain_bill_order_bid",
            "biz_domain",
            "bill_order_bid",
        ),
        {"comment": "Order WeChat Pay payment provider snapshots"},
    )
    wechatpay_order_bid = Column(
        String(36),
        index=True,
        unique=True,
        nullable=False,
        default="",
        comment="WeChat Pay payment snapshot business identifier",
    )


class BannerInfo(db.Model):
    __tablename__ = "order_banner_info"
    __table_args__ = {"comment": "Order banner info"}
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
