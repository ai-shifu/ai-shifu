from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flaskr import dao
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
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from tests.service.billing.cycle_state_test_helpers import build_cycle_state_app


def test_realign_active_topup_bucket_effective_to_updates_bucket_and_grant_ledgers() -> (
    None
):
    app = build_cycle_state_app()
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
    app = build_cycle_state_app()
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
