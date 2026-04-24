"""SQLAlchemy models for creator billing core tables."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from flaskr.dao import db

from .consts import (
    BILLING_MODE_MANUAL,
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
    BILLING_ORDER_STATUS_INIT,
    BILLING_ORDER_TYPE_MANUAL,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
    BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
    CREDIT_ROUNDING_MODE_CEIL,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)


CREDIT_NUMERIC = Numeric(20, 10)


class BillingTableMixin:
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Primary key")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag",
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


class BillingProduct(BillingTableMixin, db.Model):
    __tablename__ = "bill_products"
    __table_args__ = (
        UniqueConstraint(
            "product_bid",
            name="uq_bill_products_product_bid",
        ),
        Index(
            "ix_bill_products_product_type_status",
            "product_type",
            "status",
        ),
        {"comment": "Billing product catalog"},
    )

    product_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing product business identifier",
    )
    product_code = Column(
        String(64),
        nullable=False,
        default="",
        unique=True,
        comment="Billing product code",
    )
    product_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing product type code",
    )
    billing_mode = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_MODE_MANUAL,
        comment="Billing mode code",
    )
    billing_interval = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Billing interval code",
    )
    billing_interval_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Billing interval count",
    )
    display_name_i18n_key = Column(
        String(128),
        nullable=False,
        default="",
        comment="Display name i18n key",
    )
    description_i18n_key = Column(
        String(128),
        nullable=False,
        default="",
        comment="Description i18n key",
    )
    currency = Column(
        String(16),
        nullable=False,
        default="CNY",
        comment="Currency code",
    )
    price_amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Product price amount",
    )
    credit_amount = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Credit amount",
    )
    allocation_interval = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Credit allocation interval code",
    )
    auto_renew_enabled = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Auto renew enabled flag",
    )
    entitlement_payload = Column(
        JSON,
        nullable=True,
        comment="Entitlement payload",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Billing product metadata",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_PRODUCT_STATUS_ACTIVE,
        index=True,
        comment="Billing product status code",
    )
    sort_order = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Sort order",
    )


class BillingSubscription(BillingTableMixin, db.Model):
    __tablename__ = "bill_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "subscription_bid",
            name="uq_bill_subscriptions_subscription_bid",
        ),
        Index(
            "ix_bill_subscriptions_creator_status",
            "creator_bid",
            "status",
        ),
        {"comment": "Billing subscriptions"},
    )

    subscription_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing subscription business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    product_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Current billing product business identifier",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_SUBSCRIPTION_STATUS_DRAFT,
        index=True,
        comment="Billing subscription status code",
    )
    billing_provider = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Billing provider name",
    )
    provider_subscription_id = Column(
        String(255),
        nullable=False,
        default="",
        comment="Provider subscription identifier",
    )
    provider_customer_id = Column(
        String(255),
        nullable=False,
        default="",
        comment="Provider customer identifier",
    )
    billing_anchor_at = Column(
        DateTime,
        nullable=True,
        comment="Billing anchor timestamp",
    )
    current_period_start_at = Column(
        DateTime,
        nullable=True,
        comment="Current period start timestamp",
    )
    current_period_end_at = Column(
        DateTime,
        nullable=True,
        comment="Current period end timestamp",
    )
    grace_period_end_at = Column(
        DateTime,
        nullable=True,
        comment="Grace period end timestamp",
    )
    cancel_at_period_end = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Cancel at period end flag",
    )
    next_product_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Next billing product business identifier",
    )
    last_renewed_at = Column(
        DateTime,
        nullable=True,
        comment="Last renewed timestamp",
    )
    last_failed_at = Column(
        DateTime,
        nullable=True,
        comment="Last failed timestamp",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Billing subscription metadata",
    )


class BillingOrder(BillingTableMixin, db.Model):
    __tablename__ = "bill_orders"
    __table_args__ = (
        UniqueConstraint(
            "bill_order_bid",
            name="uq_bill_orders_bill_order_bid",
        ),
        Index("ix_bill_orders_creator_status", "creator_bid", "status"),
        {"comment": "Billing orders"},
    )

    bill_order_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing order business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    order_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        default=BILLING_ORDER_TYPE_MANUAL,
        comment="Billing order type code",
    )
    product_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing product business identifier",
    )
    subscription_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing subscription business identifier",
    )
    currency = Column(
        String(16),
        nullable=False,
        default="CNY",
        comment="Currency code",
    )
    payable_amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Payable amount",
    )
    paid_amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Paid amount",
    )
    payment_provider = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Payment provider name",
    )
    channel = Column(
        String(64),
        nullable=False,
        default="",
        comment="Payment channel",
    )
    provider_reference_id = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Provider reference identifier",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_ORDER_STATUS_INIT,
        index=True,
        comment="Billing order status code",
    )
    paid_at = Column(
        DateTime,
        nullable=True,
        comment="Paid timestamp",
    )
    failed_at = Column(
        DateTime,
        nullable=True,
        comment="Failed timestamp",
    )
    refunded_at = Column(
        DateTime,
        nullable=True,
        comment="Refunded timestamp",
    )
    failure_code = Column(
        String(255),
        nullable=False,
        default="",
        comment="Failure code",
    )
    failure_message = Column(
        String(255),
        nullable=False,
        default="",
        comment="Failure message",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Billing order metadata",
    )


class CreditWallet(BillingTableMixin, db.Model):
    __tablename__ = "credit_wallets"
    __table_args__ = (
        UniqueConstraint(
            "wallet_bid",
            name="uq_credit_wallets_wallet_bid",
        ),
        {"comment": "Credit wallets"},
    )

    wallet_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit wallet business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        unique=True,
        comment="Creator business identifier",
    )
    available_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Available credits",
    )
    reserved_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Reserved credits",
    )
    lifetime_granted_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Lifetime granted credits",
    )
    lifetime_consumed_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Lifetime consumed credits",
    )
    last_settled_usage_id = Column(
        BIGINT,
        nullable=False,
        default=0,
        index=True,
        comment="Last settled usage record id",
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Wallet version",
    )


class CreditWalletBucket(BillingTableMixin, db.Model):
    __tablename__ = "credit_wallet_buckets"
    __table_args__ = (
        UniqueConstraint(
            "wallet_bucket_bid",
            name="uq_credit_wallet_buckets_wallet_bucket_bid",
        ),
        Index(
            "ix_credit_wallet_buckets_wallet_status_priority_effective_to",
            "wallet_bid",
            "status",
            "priority",
            "effective_to",
        ),
        Index(
            "ix_credit_wallet_buckets_creator_status_priority_effective_to",
            "creator_bid",
            "status",
            "priority",
            "effective_to",
        ),
        Index(
            "ix_credit_wallet_buckets_source_type_source_bid",
            "source_type",
            "source_bid",
        ),
        {"comment": "Credit wallet buckets"},
    )

    wallet_bucket_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit wallet bucket business identifier",
    )
    wallet_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit wallet business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    bucket_category = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Credit bucket category code",
    )
    source_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing ledger source type code",
    )
    source_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit bucket source business identifier",
    )
    priority = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Credit bucket priority",
    )
    original_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Original credits",
    )
    available_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Available credits",
    )
    reserved_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Reserved credits",
    )
    consumed_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Consumed credits",
    )
    expired_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Expired credits",
    )
    effective_from = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Effective from timestamp",
    )
    effective_to = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Effective to timestamp",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=CREDIT_BUCKET_STATUS_ACTIVE,
        index=True,
        comment="Credit bucket status code",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Credit wallet bucket metadata",
    )


class CreditLedgerEntry(BillingTableMixin, db.Model):
    __tablename__ = "credit_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "ledger_bid",
            name="uq_credit_ledger_entries_ledger_bid",
        ),
        Index(
            "ix_credit_ledger_entries_creator_created",
            "creator_bid",
            "created_at",
        ),
        Index(
            "ix_credit_ledger_entries_source_type_source_bid",
            "source_type",
            "source_bid",
        ),
        UniqueConstraint(
            "creator_bid",
            "idempotency_key",
            name="uq_credit_ledger_entries_creator_idempotency",
        ),
        {"comment": "Credit ledger entries"},
    )

    ledger_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit ledger business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    wallet_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit wallet business identifier",
    )
    wallet_bucket_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit wallet bucket business identifier",
    )
    entry_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing ledger entry type code",
    )
    source_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing ledger source type code",
    )
    source_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Ledger source business identifier",
    )
    idempotency_key = Column(
        String(128),
        nullable=False,
        default="",
        index=True,
        comment="Ledger idempotency key",
    )
    amount = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Ledger amount",
    )
    balance_after = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Balance after entry",
    )
    expires_at = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Entry expiration timestamp",
    )
    consumable_from = Column(
        DateTime,
        nullable=True,
        comment="Consumable from timestamp",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Billing ledger metadata",
    )


class CreditUsageRate(BillingTableMixin, db.Model):
    __tablename__ = "credit_usage_rates"
    __table_args__ = (
        UniqueConstraint(
            "rate_bid",
            name="uq_credit_usage_rates_rate_bid",
        ),
        UniqueConstraint(
            "usage_type",
            "provider",
            "model",
            "usage_scene",
            "billing_metric",
            "effective_from",
            name="uq_credit_usage_rates_lookup",
        ),
        Index(
            "ix_credit_usage_rates_lookup",
            "usage_type",
            "provider",
            "model",
            "usage_scene",
            "billing_metric",
            "effective_from",
        ),
        {"comment": "Credit usage rates"},
    )

    rate_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Credit usage rate business identifier",
    )
    usage_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Usage type code",
    )
    provider = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Provider name",
    )
    model = Column(
        String(100),
        nullable=False,
        default="",
        index=True,
        comment="Provider model",
    )
    usage_scene = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Usage scene code",
    )
    billing_metric = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing metric code",
    )
    unit_size = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Billing unit size",
    )
    credits_per_unit = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Credits per unit",
    )
    rounding_mode = Column(
        SmallInteger,
        nullable=False,
        default=CREDIT_ROUNDING_MODE_CEIL,
        comment="Rounding mode code",
    )
    effective_from = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Effective from timestamp",
    )
    effective_to = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Effective to timestamp",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=CREDIT_USAGE_RATE_STATUS_ACTIVE,
        index=True,
        comment="Credit usage rate status code",
    )


class BillingRenewalEvent(BillingTableMixin, db.Model):
    __tablename__ = "bill_renewal_events"
    __table_args__ = (
        UniqueConstraint(
            "renewal_event_bid",
            name="uq_bill_renewal_events_renewal_event_bid",
        ),
        UniqueConstraint(
            "subscription_bid",
            "event_type",
            "scheduled_at",
            name="uq_bill_renewal_events_subscription_event_scheduled",
        ),
        Index(
            "ix_bill_renewal_events_subscription_event_scheduled",
            "subscription_bid",
            "event_type",
            "scheduled_at",
        ),
        Index(
            "ix_bill_renewal_events_status_scheduled",
            "status",
            "scheduled_at",
        ),
        {"comment": "Billing renewal events"},
    )

    renewal_event_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing renewal event business identifier",
    )
    subscription_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing subscription business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    event_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Renewal event type code",
    )
    scheduled_at = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Scheduled timestamp",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_RENEWAL_EVENT_STATUS_PENDING,
        index=True,
        comment="Renewal event status code",
    )
    attempt_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Attempt count",
    )
    last_error = Column(
        String(255),
        nullable=False,
        default="",
        comment="Last error message",
    )
    payload_json = Column(
        "payload",
        JSON,
        nullable=True,
        comment="Renewal event payload",
    )
    processed_at = Column(
        DateTime,
        nullable=True,
        comment="Processed timestamp",
    )


class BillingEntitlement(BillingTableMixin, db.Model):
    __tablename__ = "bill_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "entitlement_bid",
            name="uq_bill_entitlements_entitlement_bid",
        ),
        Index(
            "ix_bill_entitlements_creator_effective_to",
            "creator_bid",
            "effective_to",
        ),
        Index(
            "ix_bill_entitlements_source_type_source_bid",
            "source_type",
            "source_bid",
        ),
        {"comment": "Billing entitlements"},
    )

    entitlement_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing entitlement business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    source_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Entitlement source type code",
    )
    source_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Entitlement source business identifier",
    )
    branding_enabled = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Branding enabled flag",
    )
    custom_domain_enabled = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Custom domain enabled flag",
    )
    priority_class = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_ENTITLEMENT_PRIORITY_CLASS_STANDARD,
        comment="Priority class code",
    )
    analytics_tier = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_ENTITLEMENT_ANALYTICS_TIER_BASIC,
        comment="Analytics tier code",
    )
    support_tier = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_ENTITLEMENT_SUPPORT_TIER_SELF_SERVE,
        comment="Support tier code",
    )
    feature_payload = Column(
        JSON,
        nullable=True,
        comment="Entitlement feature payload",
    )
    effective_from = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Effective from timestamp",
    )
    effective_to = Column(
        DateTime,
        nullable=True,
        index=True,
        comment="Effective to timestamp",
    )


class BillingDomainBinding(BillingTableMixin, db.Model):
    __tablename__ = "bill_domain_bindings"
    __table_args__ = (
        UniqueConstraint(
            "domain_binding_bid",
            name="uq_bill_domain_bindings_domain_binding_bid",
        ),
        UniqueConstraint(
            "host",
            name="uq_bill_domain_bindings_host",
        ),
        Index(
            "ix_bill_domain_bindings_creator_status",
            "creator_bid",
            "status",
        ),
        {"comment": "Billing domain bindings"},
    )

    domain_binding_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Billing domain binding business identifier",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    host = Column(
        String(255),
        nullable=False,
        default="",
        unique=True,
        comment="Custom domain host",
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_DOMAIN_BINDING_STATUS_PENDING,
        index=True,
        comment="Domain binding status code",
    )
    verification_method = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
        comment="Verification method code",
    )
    verification_token = Column(
        String(255),
        nullable=False,
        default="",
        comment="Verification token",
    )
    last_verified_at = Column(
        DateTime,
        nullable=True,
        comment="Last verified timestamp",
    )
    ssl_status = Column(
        SmallInteger,
        nullable=False,
        default=BILLING_DOMAIN_SSL_STATUS_NOT_REQUESTED,
        comment="SSL status code",
    )
    metadata_json = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="Domain binding metadata",
    )


class BillingDailyUsageMetric(BillingTableMixin, db.Model):
    __tablename__ = "bill_daily_usage_metrics"
    __table_args__ = (
        UniqueConstraint(
            "daily_usage_metric_bid",
            name="uq_bill_daily_usage_metrics_daily_usage_metric_bid",
        ),
        UniqueConstraint(
            "stat_date",
            "creator_bid",
            "shifu_bid",
            "usage_scene",
            "usage_type",
            "provider",
            "model",
            "billing_metric",
            name="uq_bill_daily_usage_metrics_lookup",
        ),
        Index(
            "ix_bill_daily_usage_metrics_stat_creator",
            "stat_date",
            "creator_bid",
        ),
        {"comment": "Billing daily usage metrics"},
    )

    daily_usage_metric_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Daily usage metric business identifier",
    )
    stat_date = Column(
        String(10),
        nullable=False,
        default="",
        index=True,
        comment="Statistic date",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Shifu business identifier",
    )
    usage_scene = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Usage scene code",
    )
    usage_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Usage type code",
    )
    provider = Column(
        String(32),
        nullable=False,
        default="",
        index=True,
        comment="Provider name",
    )
    model = Column(
        String(100),
        nullable=False,
        default="",
        index=True,
        comment="Provider model",
    )
    billing_metric = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing metric code",
    )
    raw_amount = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Raw amount",
    )
    record_count = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Record count",
    )
    consumed_credits = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Consumed credits",
    )
    window_started_at = Column(
        DateTime,
        nullable=False,
        comment="Window start timestamp",
    )
    window_ended_at = Column(
        DateTime,
        nullable=False,
        comment="Window end timestamp",
    )


class BillingDailyLedgerSummary(BillingTableMixin, db.Model):
    __tablename__ = "bill_daily_ledger_summary"
    __table_args__ = (
        UniqueConstraint(
            "daily_ledger_summary_bid",
            name="uq_bill_daily_ledger_summary_daily_ledger_summary_bid",
        ),
        UniqueConstraint(
            "stat_date",
            "creator_bid",
            "entry_type",
            "source_type",
            name="uq_bill_daily_ledger_summary_lookup",
        ),
        Index(
            "ix_bill_daily_ledger_summary_stat_creator",
            "stat_date",
            "creator_bid",
        ),
        {"comment": "Billing daily ledger summary"},
    )

    daily_ledger_summary_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Daily ledger summary business identifier",
    )
    stat_date = Column(
        String(10),
        nullable=False,
        default="",
        index=True,
        comment="Statistic date",
    )
    creator_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator business identifier",
    )
    entry_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing ledger entry type code",
    )
    source_type = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Billing ledger source type code",
    )
    amount = Column(
        CREDIT_NUMERIC,
        nullable=False,
        default=0,
        comment="Ledger amount total",
    )
    entry_count = Column(
        BIGINT,
        nullable=False,
        default=0,
        comment="Ledger entry count",
    )
    window_started_at = Column(
        DateTime,
        nullable=False,
        comment="Window start timestamp",
    )
    window_ended_at = Column(
        DateTime,
        nullable=False,
        comment="Window end timestamp",
    )
