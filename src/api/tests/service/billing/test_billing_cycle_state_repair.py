from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from flaskr import dao
from flaskr.service.billing import subscriptions as subscriptions_mod
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWalletBucket,
)
from tests.service.billing.cycle_state_test_helpers import build_cycle_state_app


@pytest.mark.parametrize(
    (
        "case_id",
        "current_period_start_at",
        "current_period_end_at",
        "initial_bucket_start",
        "initial_bucket_end",
        "expected_changed",
        "expected_bucket_start",
        "expected_bucket_end",
    ),
    [
        (
            "nostart",
            None,
            datetime(2026, 5, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
        ),
        (
            "noend",
            datetime(2026, 4, 1, 0, 0, 0),
            None,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "zero",
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "rev",
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "expired",
            datetime(2026, 4, 1, 0, 0, 0),
            datetime(2026, 4, 9, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "future",
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 5, 11, 0, 0, 0),
            datetime(2026, 4, 12, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            False,
            datetime(2026, 4, 12, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
        ),
        (
            "endat",
            datetime(2026, 4, 1, 0, 0, 0),
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
            False,
            datetime(2026, 3, 1, 0, 0, 0),
            datetime(2026, 5, 1, 0, 0, 0),
        ),
        (
            "startat",
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 5, 10, 0, 0, 0),
            datetime(2026, 4, 11, 0, 0, 0),
            datetime(2026, 6, 1, 0, 0, 0),
            True,
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 5, 10, 0, 0, 0),
        ),
    ],
    ids=(
        "missing_start",
        "missing_end",
        "zero_length",
        "reversed",
        "expired",
        "future",
        "end_at_as_of",
        "start_at_as_of",
    ),
)
def test_repair_paid_reserved_grant_handles_cycle_window_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    current_period_start_at: datetime | None,
    current_period_end_at: datetime | None,
    initial_bucket_start: datetime,
    initial_bucket_end: datetime,
    expected_changed: bool,
    expected_bucket_start: datetime,
    expected_bucket_end: datetime,
) -> None:
    app = build_cycle_state_app()
    repair_at = datetime(2026, 4, 10, 0, 0, 0)
    creator_bid = "creator-invalid-cycle-caller"
    subscription_bid = "subscription-invalid-cycle-caller"
    order_bid = f"order-inv-cycle-{case_id}"

    monkeypatch.setattr(subscriptions_mod, "now_utc", lambda: repair_at)

    with app.app_context():
        dao.db.create_all()
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-invalid-cycle-caller",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=current_period_start_at,
            current_period_end_at=current_period_end_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=repair_at - timedelta(days=1),
            metadata_json={},
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid=f"bucket-inv-cycle-{case_id}",
            wallet_bid="wallet-invalid-cycle-caller",
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=initial_bucket_start,
            effective_to=initial_bucket_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
        )
        ledger = CreditLedgerEntry(
            ledger_bid=f"ledger-inv-cycle-{case_id}",
            creator_bid=creator_bid,
            wallet_bid=bucket.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=datetime(2026, 6, 1, 0, 0, 0),
            consumable_from=repair_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([subscription, order, bucket, ledger])
        dao.db.session.commit()

        changed = subscriptions_mod._repair_existing_paid_order_grant_bucket(
            app,
            order=order,
            grant_entry=ledger,
        )
        dao.db.session.refresh(bucket)

        assert changed is expected_changed
        assert bucket.effective_from == expected_bucket_start
        assert bucket.effective_to == expected_bucket_end
