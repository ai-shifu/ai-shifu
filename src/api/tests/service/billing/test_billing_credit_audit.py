from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import json

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.cli import register_billing_commands
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.credit_audit import audit_credit_state
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)


@pytest.fixture
def billing_credit_audit_app():
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

    @app.cli.group()
    def console():
        """Test console root."""

    register_billing_commands(console)

    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_audit_credit_state_returns_ok_for_balanced_wallet(
    billing_credit_audit_app: Flask,
) -> None:
    now = datetime(2026, 7, 29, 12, 0, 0)
    with billing_credit_audit_app.app_context():
        _seed_wallet_with_bucket(
            creator_bid="creator-audit-ok",
            wallet_bid="wallet-audit-ok",
            bucket_bid="bucket-audit-ok",
            original=Decimal("10.0000000000"),
            available=Decimal("6.0000000000"),
            consumed=Decimal("4.0000000000"),
        )
        _seed_active_subscription(
            creator_bid="creator-audit-ok",
            subscription_bid="sub-audit-ok",
        )
        dao.db.session.commit()

        report = audit_credit_state(creator_bid="creator-audit-ok", as_of=now)

    assert report.status == "ok"
    assert report.issue_count == 0
    assert report.checked_wallet_count == 1
    assert report.checked_bucket_count == 1


def test_audit_credit_state_reports_wallet_and_bucket_mismatch(
    billing_credit_audit_app: Flask,
) -> None:
    now = datetime(2026, 7, 29, 12, 0, 0)
    with billing_credit_audit_app.app_context():
        _seed_wallet_with_bucket(
            creator_bid="creator-audit-mismatch",
            wallet_bid="wallet-audit-mismatch",
            bucket_bid="bucket-audit-mismatch",
            wallet_available=Decimal("1.0000000000"),
            original=Decimal("10.0000000000"),
            available=Decimal("7.0000000000"),
            consumed=Decimal("1.0000000000"),
        )
        _seed_active_subscription(
            creator_bid="creator-audit-mismatch",
            subscription_bid="sub-audit-mismatch",
        )
        dao.db.session.commit()

        payload = audit_credit_state(
            creator_bid="creator-audit-mismatch",
            as_of=now,
        ).to_payload()

    assert payload["status"] == "issues_found"
    assert payload["counts_by_code"] == {
        "wallet_snapshot_mismatch": 1,
        "bucket_balance_mismatch": 1,
    }


def test_audit_credit_state_reports_overdue_reserved_grant(
    billing_credit_audit_app: Flask,
) -> None:
    now = datetime(2026, 7, 29, 12, 0, 0)
    with billing_credit_audit_app.app_context():
        wallet, bucket = _seed_wallet_with_bucket(
            creator_bid="creator-audit-reserved",
            wallet_bid="wallet-audit-reserved",
            bucket_bid="bucket-audit-reserved",
            wallet_available=Decimal("0"),
            wallet_reserved=Decimal("5.0000000000"),
            original=Decimal("5.0000000000"),
            available=Decimal("0"),
            reserved=Decimal("5.0000000000"),
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-audit-reserved",
                creator_bid=wallet.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="order-audit-reserved",
                idempotency_key="grant:audit-reserved",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("0"),
                consumable_from=now - timedelta(days=1),
                expires_at=now + timedelta(days=30),
                metadata_json={"bucket_credit_state": "reserved"},
            )
        )
        dao.db.session.commit()

        payload = audit_credit_state(
            creator_bid="creator-audit-reserved",
            as_of=now,
        ).to_payload()

    assert payload["counts_by_code"] == {"overdue_reserved_grant": 1}
    assert payload["issues"][0]["ledger_bid"] == "ledger-audit-reserved"


def test_audit_credit_state_reports_expire_ledger_and_subscription_window_drift(
    billing_credit_audit_app: Flask,
) -> None:
    now = datetime(2026, 7, 29, 12, 0, 0)
    subscription_end = now + timedelta(days=20)
    bucket_end = now + timedelta(days=10)
    with billing_credit_audit_app.app_context():
        wallet, expired_bucket = _seed_wallet_with_bucket(
            creator_bid="creator-audit-drift",
            wallet_bid="wallet-audit-drift",
            bucket_bid="bucket-audit-expired-drift",
            wallet_available=Decimal("0"),
            original=Decimal("10.0000000000"),
            available=Decimal("0"),
            consumed=Decimal("4.0000000000"),
            expired=Decimal("6.0000000000"),
            status=CREDIT_BUCKET_STATUS_EXPIRED,
            effective_to=bucket_end,
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-audit-expire-wrong-window",
                creator_bid=wallet.creator_bid,
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=expired_bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="order-audit-expire",
                idempotency_key="expire:audit-wrong-window",
                amount=Decimal("-6.0000000000"),
                balance_after=Decimal("4.0000000000"),
                consumable_from=now - timedelta(days=30),
                expires_at=bucket_end - timedelta(days=1),
            )
        )
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-audit-window-drift",
                wallet_bid=wallet.wallet_bid,
                creator_bid=wallet.creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="order-audit-window",
                priority=20,
                original_credits=Decimal("4.0000000000"),
                available_credits=Decimal("4.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=now - timedelta(days=1),
                effective_to=bucket_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
            )
        )
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-audit-window-drift",
                creator_bid=wallet.creator_bid,
                product_bid="product-audit-window-drift",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=now - timedelta(days=1),
                current_period_end_at=subscription_end,
            )
        )
        dao.db.session.commit()

        payload = audit_credit_state(
            creator_bid="creator-audit-drift",
            as_of=now,
        ).to_payload()

    assert payload["counts_by_code"] == {
        "wallet_snapshot_mismatch": 1,
        "expire_ledger_bucket_mismatch": 1,
        "subscription_bucket_window_mismatch": 1,
    }


def test_audit_credit_state_cli_outputs_read_only_report(
    billing_credit_audit_app: Flask,
) -> None:
    with billing_credit_audit_app.app_context():
        _seed_wallet_with_bucket(
            creator_bid="creator-audit-cli",
            wallet_bid="wallet-audit-cli",
            bucket_bid="bucket-audit-cli",
            wallet_available=Decimal("0"),
            original=Decimal("2.0000000000"),
            available=Decimal("2.0000000000"),
        )
        _seed_active_subscription(
            creator_bid="creator-audit-cli",
            subscription_bid="sub-audit-cli",
        )
        dao.db.session.commit()

    runner = billing_credit_audit_app.test_cli_runner()
    result = runner.invoke(
        args=[
            "console",
            "billing",
            "audit-credit-state",
            "--creator-bid",
            "creator-audit-cli",
            "--as-of",
            "2026-07-29T12:00:00Z",
        ]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "issues_found"
    assert payload["counts_by_code"] == {"wallet_snapshot_mismatch": 1}


def _seed_wallet_with_bucket(
    *,
    creator_bid: str,
    wallet_bid: str,
    bucket_bid: str,
    wallet_available: Decimal | None = None,
    wallet_reserved: Decimal = Decimal("0"),
    original: Decimal,
    available: Decimal,
    reserved: Decimal = Decimal("0"),
    consumed: Decimal = Decimal("0"),
    expired: Decimal = Decimal("0"),
    status: int = CREDIT_BUCKET_STATUS_ACTIVE,
    effective_to: datetime | None = None,
) -> tuple[CreditWallet, CreditWalletBucket]:
    now = datetime(2026, 7, 1, 0, 0, 0)
    wallet = CreditWallet(
        wallet_bid=wallet_bid,
        creator_bid=creator_bid,
        available_credits=available if wallet_available is None else wallet_available,
        reserved_credits=wallet_reserved,
        lifetime_granted_credits=original,
        lifetime_consumed_credits=consumed,
        last_settled_usage_id=0,
        version=0,
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=bucket_bid,
        wallet_bid=wallet.wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
        source_bid=f"order-{bucket_bid}",
        priority=20,
        original_credits=original,
        available_credits=available,
        reserved_credits=reserved,
        consumed_credits=consumed,
        expired_credits=expired,
        effective_from=now,
        effective_to=effective_to or now + timedelta(days=30),
        status=status,
    )
    dao.db.session.add_all([wallet, bucket])
    return wallet, bucket


def _seed_active_subscription(
    *,
    creator_bid: str,
    subscription_bid: str,
    current_period_end_at: datetime | None = None,
) -> BillingSubscription:
    subscription = BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=f"product-{subscription_bid}",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=datetime(2026, 7, 1, 0, 0, 0),
        current_period_end_at=current_period_end_at or datetime(2026, 7, 31, 0, 0, 0),
    )
    dao.db.session.add(subscription)
    return subscription
