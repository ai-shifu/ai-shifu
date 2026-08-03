from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.cycle_state_transitions import (
    apply_paid_subscription_cycle_state,
    realign_active_topup_bucket_effective_to,
    resolve_effective_subscription_cycle_window,
    subscription_has_effective_cycle,
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)


def _build_app() -> Flask:
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


def test_subscription_has_effective_cycle_uses_current_period_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-state",
        creator_bid="creator-cycle-state",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is True

    subscription.current_period_end_at = current_at

    assert subscription_has_effective_cycle(subscription, as_of=current_at) is False
    assert subscription_has_effective_cycle(None, as_of=current_at) is False


def test_resolve_effective_subscription_cycle_window_returns_current_window() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    cycle_start = current_at
    cycle_end = current_at + timedelta(days=30)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window",
        creator_bid="creator-cycle-window",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=cycle_start,
        current_period_end_at=cycle_end,
    )

    window = resolve_effective_subscription_cycle_window(
        subscription,
        as_of=current_at,
    )

    assert window is not None
    assert window.start_at == cycle_start
    assert window.end_at == cycle_end


def test_resolve_effective_subscription_cycle_window_rejects_invalid_windows() -> None:
    current_at = datetime(2026, 4, 10, 0, 0, 0)
    subscription = BillingSubscription(
        subscription_bid="subscription-cycle-window-invalid",
        creator_bid="creator-cycle-window-invalid",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=current_at - timedelta(days=1),
        current_period_end_at=current_at + timedelta(days=1),
    )

    subscription.current_period_start_at = None
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at + timedelta(seconds=1)
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )

    subscription.current_period_start_at = current_at - timedelta(days=1)
    subscription.current_period_end_at = current_at
    assert (
        resolve_effective_subscription_cycle_window(subscription, as_of=current_at)
        is None
    )


def test_realign_active_topup_bucket_effective_to_updates_bucket_and_grant_ledgers() -> (
    None
):
    app = _build_app()
    creator_bid = "creator-cycle-state-topup"
    cycle_start = datetime(2026, 4, 10, 0, 0, 0)
    cycle_end = datetime(2026, 5, 10, 0, 0, 0)
    old_topup_end = datetime(2026, 4, 9, 0, 0, 0)

    with app.app_context():
        dao.db.create_all()
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-topup",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-topup",
            priority=30,
            original_credits=Decimal("20.0000000000"),
            available_credits=Decimal("20.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        future_topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-future-topup",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-future-topup",
            priority=30,
            original_credits=Decimal("5.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=cycle_start + timedelta(days=1),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-subscription",
            wallet_bid="wallet-cycle-state-topup",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-cycle-state-subscription",
            priority=20,
            original_credits=Decimal("50.0000000000"),
            available_credits=Decimal("50.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-topup",
            wallet_bucket_bid=topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-topup",
            amount=Decimal("20.0000000000"),
            balance_after=Decimal("20.0000000000"),
            expires_at=old_topup_end,
            consumable_from=topup_bucket.effective_from,
        )
        future_topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-future-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-topup",
            wallet_bucket_bid=future_topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=future_topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-future-topup",
            amount=Decimal("5.0000000000"),
            balance_after=Decimal("25.0000000000"),
            expires_at=old_topup_end,
            consumable_from=future_topup_bucket.effective_from,
        )
        dao.db.session.add_all(
            [
                topup_bucket,
                future_topup_bucket,
                subscription_bucket,
                topup_ledger,
                future_topup_ledger,
            ]
        )
        dao.db.session.commit()

        realign_active_topup_bucket_effective_to(
            creator_bid=creator_bid,
            effective_from=cycle_start,
            effective_to=cycle_end,
        )
        dao.db.session.flush()

        assert topup_bucket.effective_to == cycle_end
        assert topup_ledger.expires_at == cycle_end
        assert future_topup_bucket.effective_to == old_topup_end
        assert future_topup_ledger.expires_at == old_topup_end
        assert subscription_bucket.effective_to == old_topup_end


def test_apply_paid_subscription_cycle_state_advances_renewal_and_realigns_topup() -> (
    None
):
    app = _build_app()
    creator_bid = "creator-cycle-state-renewal"
    cycle_start = datetime(2026, 6, 1, 0, 0, 0)
    cycle_end = datetime(2026, 7, 1, 0, 0, 0)
    old_topup_end = datetime(2026, 5, 31, 0, 0, 0)

    with app.app_context():
        dao.db.create_all()
        subscription = BillingSubscription(
            subscription_bid="subscription-cycle-state-renewal",
            creator_bid=creator_bid,
            product_bid="bill-product-old",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            cancel_at_period_end=1,
            next_product_bid="bill-product-downgrade",
            current_period_start_at=datetime(2026, 5, 1, 0, 0, 0),
            current_period_end_at=cycle_start,
        )
        topup_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-cycle-state-renewal-topup",
            wallet_bid="wallet-cycle-state-renewal",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-cycle-state-renewal-topup",
            priority=30,
            original_credits=Decimal("20.0000000000"),
            available_credits=Decimal("20.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=old_topup_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        topup_ledger = CreditLedgerEntry(
            ledger_bid="ledger-cycle-state-renewal-topup",
            creator_bid=creator_bid,
            wallet_bid="wallet-cycle-state-renewal",
            wallet_bucket_bid=topup_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=topup_bucket.source_bid,
            idempotency_key="grant:order-cycle-state-renewal-topup",
            amount=Decimal("20.0000000000"),
            balance_after=Decimal("20.0000000000"),
            expires_at=old_topup_end,
            consumable_from=topup_bucket.effective_from,
        )
        dao.db.session.add_all([subscription, topup_bucket, topup_ledger])
        dao.db.session.commit()

        apply_paid_subscription_cycle_state(
            subscription,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            order_product_bid="bill-product-renewal-order",
            effective_from=cycle_start,
            effective_to=cycle_end,
        )
        dao.db.session.flush()

        assert subscription.product_bid == "bill-product-downgrade"
        assert subscription.next_product_bid == ""
        assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
        assert subscription.current_period_start_at == cycle_start
        assert subscription.current_period_end_at == cycle_end
        assert subscription.last_renewed_at == cycle_start
        assert topup_bucket.effective_to == cycle_end
        assert topup_ledger.expires_at == cycle_end
