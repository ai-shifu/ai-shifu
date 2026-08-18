from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import flaskr.dao as dao
from flask import Flask
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)

_UNSET = object()

__all__ = [
    "add_reserved_renewal_activation_state",
    "build_cycle_state_app",
    "create_cycle_state_renewal_order",
    "create_cycle_state_renewal_product",
]


def build_cycle_state_app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    return app


def create_cycle_state_renewal_order(
    *,
    bill_order_bid: str = "order-renewal-activation-boundary",
    subscription_bid: str = "subscription-renewal-activation-boundary",
    creator_bid: str = "creator-renewal-activation-boundary",
    metadata_json: dict | None = None,
    payment_provider: str = "pingxx",
    paid_at: datetime | None | object = _UNSET,
    order_type: int = BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=order_type,
        product_bid="bill-product-renewal-boundary",
        subscription_bid=subscription_bid,
        currency="CNY",
        payable_amount=0,
        paid_amount=0,
        payment_provider=payment_provider,
        channel="manual",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=(datetime(2026, 4, 10, 0, 0, 0) if paid_at is _UNSET else paid_at),
        metadata_json=metadata_json or {},
    )


def create_cycle_state_renewal_product() -> BillingProduct:
    return BillingProduct(
        product_bid="bill-product-renewal-boundary",
        product_code="renewal-boundary",
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        display_name_i18n_key="billing.product.renewal_boundary",
        description_i18n_key="billing.product.renewal_boundary.description",
        currency="CNY",
        price_amount=0,
        credit_amount=Decimal("1000.0000000000"),
        allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
        auto_renew_enabled=1,
        status=BILLING_PRODUCT_STATUS_ACTIVE,
    )


def add_reserved_renewal_activation_state(
    *,
    product: BillingProduct,
    subscription: BillingSubscription,
    order: BillingOrder,
    current_cycle_start: datetime,
    current_cycle_end: datetime,
    next_cycle_end: datetime,
) -> tuple[CreditWallet, CreditWalletBucket, CreditLedgerEntry]:
    wallet = CreditWallet(
        wallet_bid=f"wallet-{order.creator_bid}",
        creator_bid=order.creator_bid,
        available_credits=Decimal("3.0000000000"),
        reserved_credits=Decimal("1000.0000000000"),
        lifetime_granted_credits=Decimal("1003.0000000000"),
        lifetime_consumed_credits=Decimal("0"),
        last_settled_usage_id=0,
        version=0,
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{order.bill_order_bid}",
        wallet_bid=wallet.wallet_bid,
        creator_bid=order.creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid="order-current-cycle",
        priority=20,
        original_credits=Decimal("1003.0000000000"),
        available_credits=Decimal("3.0000000000"),
        reserved_credits=Decimal("1000.0000000000"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
        effective_from=current_cycle_start,
        effective_to=current_cycle_end,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={"bill_order_bid": "order-current-cycle"},
        created_at=current_cycle_start,
        updated_at=current_cycle_start,
    )
    grant_entry = CreditLedgerEntry(
        ledger_bid=f"ledger-{order.bill_order_bid}",
        creator_bid=order.creator_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=order.bill_order_bid,
        idempotency_key=f"grant:{order.bill_order_bid}",
        amount=Decimal("1000.0000000000"),
        balance_after=Decimal("3.0000000000"),
        expires_at=next_cycle_end,
        consumable_from=current_cycle_end,
        metadata_json={
            "bill_order_bid": order.bill_order_bid,
            "subscription_bid": subscription.subscription_bid,
            "product_bid": product.product_bid,
            "payment_provider": order.payment_provider,
            "grant_reason": "subscription_renewal",
            "bucket_credit_state": "reserved",
            "reserved_until": current_cycle_end.isoformat(),
        },
        created_at=current_cycle_end - timedelta(days=5),
        updated_at=current_cycle_end - timedelta(days=5),
    )
    dao.db.session.add_all([wallet, bucket, grant_entry])
    return wallet, bucket, grant_entry
