from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from flask import Flask
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import attributes
from sqlalchemy.orm.exc import ObjectDeletedError

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXHAUSTED,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.settlement import settle_bill_usage
from flaskr.service.billing.wallets import (
    _build_expire_ledger_idempotency_key,
    expire_credit_wallet_buckets,
    grant_manual_credit_wallet_balance,
    grant_refund_return_credits,
    repair_credit_bucket_runtime_statuses,
    repair_expire_ledger_bucket_drift,
    repair_renewal_state_drift,
    rebuild_credit_wallet_snapshots,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.datetime import to_utc_iso


@pytest.fixture
def billing_wallet_lifecycle_app():
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
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_monthly_plan_product(
    product_bid: str,
    *,
    credit_amount: Decimal = Decimal("1000.0000000000"),
) -> BillingProduct:
    return BillingProduct(
        product_bid=product_bid,
        product_code=product_bid,
        product_type=1,
        display_name_i18n_key=f"billing.product.{product_bid}",
        description_i18n_key=f"billing.product.{product_bid}.description",
        status=1,
        billing_mode=2,
        billing_interval=2,
        billing_interval_count=1,
        credit_amount=credit_amount,
        currency="CNY",
        price_amount=0,
        allocation_interval=2,
        auto_renew_enabled=1,
    )


def test_expire_credit_wallet_buckets_marks_bucket_expired_and_writes_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-1",
            creator_bid="creator-expire-1",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-expire-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-expire-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                source_bid="order-topup-expire-1",
                priority=30,
                original_credits=Decimal("2.5000000000"),
                available_credits=Decimal("2.5000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=datetime(2026, 4, 1, 0, 0, 0),
                effective_to=datetime(2026, 4, 7, 0, 0, 0),
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
        )
        dao.db.session.commit()

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-expire-1",
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-1"
        ).one()
        wallet = CreditWallet.query.filter_by(creator_bid="creator-expire-1").one()
        ledger = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-1"
        ).one()

        assert payload["status"] == "expired"
        assert payload["bucket_count"] == 1
        assert payload["expired_credits"] == 2.5
        assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
        assert bucket.available_credits == Decimal("0")
        assert bucket.expired_credits == Decimal("2.5000000000")
        assert wallet.available_credits == Decimal("0E-10")
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_EXPIRE
        assert ledger.idempotency_key == "expire:bucket-expire-1:20260407000000"
        assert ledger.amount == Decimal("-2.5000000000")
        assert ledger.balance_after == Decimal("0E-10")


def test_expire_credit_wallet_buckets_skips_bucket_with_conflicting_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    # A concurrent transaction already expired one bucket (its "expire:" ledger
    # row exists). The batch must skip that bucket via the savepoint instead of
    # raising a duplicate-key IntegrityError and aborting the whole scan, and the
    # other bucket of the same wallet must still expire correctly.
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-race",
            creator_bid="creator-expire-race",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        for bid, amount, source in (
            ("bucket-conflict", "3.0000000000", "order-conflict"),
            ("bucket-ok", "2.0000000000", "order-ok"),
        ):
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid=bid,
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-expire-race",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid=source,
                    priority=30,
                    original_credits=Decimal(amount),
                    available_credits=Decimal(amount),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=datetime(2026, 4, 7, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                )
            )
        # Pre-existing "expire:" ledger for bucket-conflict (a concurrent worker
        # already expired it), so re-expiring it would trip the idempotency key.
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid="ledger-conflict-preexisting",
                creator_bid="creator-expire-race",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid="bucket-conflict",
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                source_type=CREDIT_SOURCE_TYPE_TOPUP,
                source_bid="order-conflict",
                idempotency_key=_build_expire_ledger_idempotency_key(
                    "bucket-conflict",
                    effective_to=datetime(2026, 4, 7, 0, 0, 0),
                ),
                amount=Decimal("-3.0000000000"),
                balance_after=Decimal("2.0000000000"),
                expires_at=datetime(2026, 4, 7, 0, 0, 0),
                consumable_from=datetime(2026, 4, 1, 0, 0, 0),
                metadata_json={},
            )
        )
        dao.db.session.commit()

        # Must not raise a duplicate-key IntegrityError.
        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-expire-race",
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        # Only bucket-ok was expired this run; bucket-conflict was skipped.
        assert payload["bucket_count"] == 1
        ok_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-ok"
        ).one()
        assert ok_bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
        assert ok_bucket.available_credits == Decimal("0")
        # No duplicate ledger written for the conflicting bucket.
        conflict_ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-conflict"
        ).all()
        assert len(conflict_ledgers) == 1


def test_expire_credit_wallet_buckets_allows_reused_bucket_after_legacy_expire(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-reused-legacy",
            creator_bid="creator-expire-reused-legacy",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("15.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-reused-legacy",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-reused-legacy-second-cycle",
            priority=30,
            original_credits=Decimal("15.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("2.5000000000"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=datetime(2026, 5, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all(
            [
                wallet,
                bucket,
                CreditLedgerEntry(
                    ledger_bid="ledger-expire-reused-legacy-first-cycle",
                    creator_bid=wallet.creator_bid,
                    wallet_bid=wallet.wallet_bid,
                    wallet_bucket_bid=bucket.wallet_bucket_bid,
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="order-expire-reused-legacy-first-cycle",
                    idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
                    amount=Decimal("-2.5000000000"),
                    balance_after=Decimal("0"),
                    expires_at=datetime(2026, 4, 7, 0, 0, 0),
                    consumable_from=datetime(2026, 4, 1, 0, 0, 0),
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 5, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-reused-legacy"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-reused-legacy"
        ).one()
        expire_ledgers = (
            CreditLedgerEntry.query.filter_by(
                wallet_bucket_bid=bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )

    assert payload["status"] == "expired"
    assert payload["bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal("0")
    assert bucket.expired_credits == Decimal("7.5000000000")
    assert wallet.available_credits == Decimal("0E-10")
    assert len(expire_ledgers) == 2
    assert expire_ledgers[0].idempotency_key == "expire:bucket-expire-reused-legacy"
    assert (
        expire_ledgers[1].idempotency_key
        == "expire:bucket-expire-reused-legacy:20260507000000"
    )


def test_expire_credit_wallet_buckets_skips_bucket_realigned_during_refresh(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    future_effective_to = datetime(2026, 4, 30, 0, 0, 0)
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-realigned",
            creator_bid="creator-expire-realigned",
            available_credits=Decimal("4.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("4.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-realigned",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-expire-realigned",
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-topup-realigned",
            priority=30,
            original_credits=Decimal("4.0000000000"),
            available_credits=Decimal("4.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
            created_at=datetime(2026, 4, 1, 0, 0, 0),
            updated_at=datetime(2026, 4, 1, 0, 0, 0),
        )
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()

        real_refresh = wallets_mod.db.session.refresh

        def _refresh_with_realign(target_bucket):
            if (
                isinstance(target_bucket, CreditWalletBucket)
                and target_bucket.wallet_bucket_bid == "bucket-expire-realigned"
            ):
                attributes.set_committed_value(
                    target_bucket,
                    "effective_to",
                    future_effective_to,
                )
                return None
            return real_refresh(target_bucket)

        monkeypatch.setattr(wallets_mod.db.session, "refresh", _refresh_with_realign)

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-expire-realigned",
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        refreshed_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-realigned"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-realigned"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-realigned"
        ).all()

        assert payload["status"] == "noop"
        assert payload["bucket_count"] == 0
        assert refreshed_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert refreshed_bucket.available_credits == Decimal("4.0000000000")
        assert refreshed_bucket.expired_credits == Decimal("0")
        assert refreshed_bucket.effective_to == datetime(2026, 4, 7, 0, 0, 0)
        assert wallet.available_credits == Decimal("4.0000000000")
        assert ledgers == []


def test_expire_credit_wallet_buckets_skips_bucket_deleted_during_refresh(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-refresh-skip",
            creator_bid="creator-expire-refresh-skip",
            available_credits=Decimal("9.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("9.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        skipped_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-refresh-skip",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-refresh-skip",
            priority=30,
            original_credits=Decimal("4.0000000000"),
            available_credits=Decimal("4.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ok_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-refresh-ok",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-refresh-ok",
            priority=30,
            original_credits=Decimal("5.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, skipped_bucket, ok_bucket])
        dao.db.session.commit()

        real_refresh = wallets_mod.db.session.refresh

        def _refresh_with_deleted_bucket(target_bucket):
            if (
                isinstance(target_bucket, CreditWalletBucket)
                and target_bucket.wallet_bucket_bid == "bucket-expire-refresh-skip"
            ):
                attributes.set_committed_value(target_bucket, "deleted", 1)
                return None
            return real_refresh(target_bucket)

        monkeypatch.setattr(
            wallets_mod.db.session, "refresh", _refresh_with_deleted_bucket
        )

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        skipped_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-refresh-skip"
        ).one()
        ok_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-refresh-ok"
        ).one()

    assert payload["bucket_count"] == 1
    assert payload["expired_credits"] == 5
    assert skipped_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert skipped_bucket.available_credits == Decimal("4.0000000000")
    assert ok_bucket.status == CREDIT_BUCKET_STATUS_EXPIRED


def test_expire_credit_wallet_buckets_skips_bucket_when_refresh_raises_deleted(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-refresh-error",
            creator_bid="creator-expire-refresh-error",
            available_credits=Decimal("8.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("8.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        skipped_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-refresh-error",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-refresh-error",
            priority=30,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ok_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-refresh-error-ok",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-refresh-error-ok",
            priority=30,
            original_credits=Decimal("5.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, skipped_bucket, ok_bucket])
        dao.db.session.commit()

        real_refresh = wallets_mod.db.session.refresh

        def _refresh_with_deleted_error(target_bucket):
            if (
                isinstance(target_bucket, CreditWalletBucket)
                and target_bucket.wallet_bucket_bid == "bucket-expire-refresh-error"
            ):
                raise ObjectDeletedError(target_bucket._sa_instance_state)
            return real_refresh(target_bucket)

        monkeypatch.setattr(
            wallets_mod.db.session, "refresh", _refresh_with_deleted_error
        )

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        skipped_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-refresh-error"
        ).one()
        ok_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-refresh-error-ok"
        ).one()

    assert payload["bucket_count"] == 1
    assert payload["expired_credits"] == 5
    assert skipped_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert skipped_bucket.available_credits == Decimal("3.0000000000")
    assert ok_bucket.status == CREDIT_BUCKET_STATUS_EXPIRED


def test_expire_credit_wallet_buckets_skips_bucket_on_wallet_version_conflict(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A concurrent wallet update makes persist_credit_wallet_snapshot raise
    # credit_wallet_version_conflict for the first bucket. The batch must skip
    # it (savepoint rollback + reload) and still expire the wallet's other
    # bucket instead of crashing the whole scan.
    from flaskr.service.billing import wallets as wallets_mod

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-version-race",
            creator_bid="creator-version-race",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        for bid, amount in (
            ("bucket-v1", "3.0000000000"),
            ("bucket-v2", "2.0000000000"),
        ):
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid=bid,
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-version-race",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid=f"order-{bid}",
                    priority=30,
                    original_credits=Decimal(amount),
                    available_credits=Decimal(amount),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=datetime(2026, 4, 7, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                )
            )
        dao.db.session.commit()

        real_persist = wallets_mod.persist_credit_wallet_snapshot
        state = {"calls": 0}

        def _persist_conflict_once(target_wallet, **kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("credit_wallet_version_conflict")
            return real_persist(target_wallet, **kwargs)

        monkeypatch.setattr(
            wallets_mod, "persist_credit_wallet_snapshot", _persist_conflict_once
        )

        # Must not crash on the version conflict.
        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-version-race",
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        # First bucket skipped on conflict; the second still expired.
        assert payload["bucket_count"] == 1
        expired = CreditWalletBucket.query.filter_by(
            status=CREDIT_BUCKET_STATUS_EXPIRED
        ).all()
        assert len(expired) == 1


def test_repair_credit_bucket_runtime_statuses_reactivates_live_expired_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    future_effective_to = datetime(2099, 6, 9, 23, 59, 59)
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-repair-runtime-1",
            creator_bid="creator-repair-runtime-1",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("105.0000000000"),
            lifetime_consumed_credits=Decimal("9.8500000000"),
            last_settled_usage_id=0,
            version=0,
            created_at=datetime(2026, 5, 11, 14, 11, 8),
            updated_at=datetime(2026, 5, 11, 14, 11, 8),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-repair-runtime-1",
            wallet_bid=wallet.wallet_bid,
            creator_bid="creator-repair-runtime-1",
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="bill-repair-runtime-1",
            priority=20,
            original_credits=Decimal("105.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("9.8500000000"),
            expired_credits=Decimal("90.1500000000"),
            effective_from=datetime(2026, 5, 11, 14, 11, 8),
            effective_to=future_effective_to,
            status=CREDIT_BUCKET_STATUS_EXPIRED,
            metadata_json={},
            created_at=datetime(2026, 5, 11, 14, 11, 8),
            updated_at=datetime(2026, 5, 11, 14, 11, 8),
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-repair-runtime-1",
                creator_bid="creator-repair-runtime-1",
                product_bid="bill-product-repair-runtime",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=datetime(2026, 5, 11, 0, 0, 0),
                current_period_end_at=future_effective_to,
            )
        )
        dao.db.session.add(bucket)
        dao.db.session.commit()

        payload = repair_credit_bucket_runtime_statuses(
            billing_wallet_lifecycle_app,
            creator_bid="creator-repair-runtime-1",
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-repair-runtime-1"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-repair-runtime-1"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["repaired_bucket_bids"] == ["bucket-repair-runtime-1"]
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert wallet.available_credits == Decimal("5.0000000000")


def test_repair_renewal_state_drift_dry_run_reports_stale_subscription_and_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-dry-run",
            creator_bid="creator-renewal-drift-dry-run",
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-dry-run",
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 4, 7, 0, 0, 0),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-renewal-drift-dry-run",
            priority=20,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, subscription, bucket])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=True,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-dry-run"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-drift-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE


def test_repair_renewal_state_drift_expires_bucket_and_subscription(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-apply",
            creator_bid="creator-renewal-drift-apply",
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-apply",
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 4, 7, 0, 0, 0),
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-renewal-drift-apply",
            priority=20,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("3.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, subscription, bucket])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-apply"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid="subscription-renewal-drift-apply"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-renewal-drift-apply"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-apply",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

    assert payload["status"] == "repaired"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["updated_subscription_count"] == 1
    assert payload["expired_bucket_count"] == 1
    assert payload["expired_credits"] == 3.0
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal("0")
    assert bucket.expired_credits == Decimal("3.0000000000")
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_EXPIRED
    assert wallet.available_credits == Decimal("0E-10")
    assert len(ledgers) == 1


def test_repair_renewal_state_drift_dry_run_reports_overdue_reserved_paid_grant(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-protected"
    subscription_bid = "subscription-renewal-drift-protected-dry-run"
    order_bid = "order-renewal-drift-protected-dry-run"
    ledger_bid = "ledger-renewal-drift-protected-dry-run"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-protected-dry-run",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=wallet.creator_bid,
            product_bid="bill-product-renewal-drift-protected",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = _create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=wallet.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid="bill-product-renewal-drift-protected",
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-protected-dry-run",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": boundary_at.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-protected-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-dry-run",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-dry-run"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid=ledger_bid,
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-event-protected-dry-run",
            subscription_bid=subscription.subscription_bid,
            creator_bid=wallet.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"bill_order_bid": order.bill_order_bid},
            processed_at=None,
        )
        dao.db.session.add_all(
            [wallet, subscription, product, order, bucket, ledger, event]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-protected-dry-run"
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(ledger_bid=ledger_bid).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()
        event = BillingRenewalEvent.query.filter_by(
            renewal_event_bid="renewal-event-protected-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["stale_subscription_count"] == 1
    assert payload["stale_bucket_count"] == 1
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]
    assert payload["activated_creator_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_count"] == 0
    assert payload["protected_creator_bids"] == []
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["overdue_reserved_grants"][0]["grant_ledger_bid"] == ledger_bid
    assert payload["overdue_reserved_grants"][0]["renewal_event_bids"] == [
        "renewal-event-protected-dry-run"
    ]
    assert (
        payload["overdue_reserved_grants"][0]["consumable_from"]
        == "2026-04-08T00:00:00Z"
    )
    assert payload["overdue_reserved_grants"][0]["paid_at"] == "2026-04-07T00:00:00Z"
    assert wallet.reserved_credits == Decimal("1000.0000000000")
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.effective_to == boundary_at
    assert bucket.reserved_credits == Decimal("1000.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_end_at == boundary_at
    assert event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING


def test_repair_renewal_state_drift_applies_overdue_reserved_paid_grant_before_expiry(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-protected-apply"
    subscription_bid = "subscription-renewal-drift-protected-apply"
    product_bid = "bill-product-renewal-drift-protected-apply"
    order_bid = "order-renewal-drift-protected-apply"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-protected-apply",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=wallet.creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="manual",
            provider_subscription_id="",
            provider_customer_id="",
            billing_anchor_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
            grace_period_end_at=None,
            cancel_at_period_end=0,
            next_product_bid="",
            last_renewed_at=datetime(2026, 3, 8, 0, 0, 0),
            last_failed_at=None,
            metadata_json={},
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-protected-monthly",
            product_type=1,
            display_name_i18n_key="billing.product.protected_monthly",
            description_i18n_key="billing.product.protected_monthly.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=wallet.creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product.product_bid,
            subscription_bid=subscription.subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-protected-apply",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": boundary_at.isoformat(),
                "renewal_cycle_end_at": next_cycle_end.isoformat(),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-protected-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-apply",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-apply"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-protected-apply",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription.subscription_bid,
                "product_bid": order.product_bid,
                "payment_provider": order.payment_provider,
                "grant_reason": "subscription",
                "bucket_credit_state": "reserved",
                "reserved_until": boundary_at.isoformat(),
            },
        )
        event = BillingRenewalEvent(
            renewal_event_bid="renewal-event-protected-apply",
            subscription_bid=subscription.subscription_bid,
            creator_bid=wallet.creator_bid,
            event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            scheduled_at=boundary_at,
            status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
            attempt_count=0,
            last_error="",
            payload_json={"bill_order_bid": order.bill_order_bid},
            processed_at=None,
        )
        dao.db.session.add_all(
            [wallet, subscription, product, order, bucket, ledger, event]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )

        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-renewal-drift-protected-apply"
        ).one()
        ledger = CreditLedgerEntry.query.filter_by(
            ledger_bid="ledger-renewal-drift-protected-apply"
        ).one()
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=subscription_bid
        ).one()

    assert payload["status"] == "repaired"
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 1
    assert payload["activated_creator_count"] == 1
    assert payload["activated_creator_bids"] == [creator_bid]
    assert payload["protected_creator_count"] == 0
    assert payload["protected_creator_bids"] == []
    assert payload["expired_bucket_count"] == 0
    assert payload["updated_subscription_count"] == 0
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_start_at == boundary_at
    assert subscription.current_period_end_at == next_cycle_end
    assert wallet.available_credits == Decimal("1000.0000000000")
    assert wallet.reserved_credits == Decimal("0E-10")
    assert bucket.source_bid == order_bid
    assert bucket.available_credits == Decimal("1000.0000000000")
    assert bucket.reserved_credits == Decimal("0E-10")
    assert bucket.effective_from == boundary_at
    assert bucket.effective_to == next_cycle_end
    assert ledger.metadata_json["bucket_credit_state"] == "available"


def test_repair_renewal_state_drift_all_scope_includes_reserved_only_creator(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    repaired_at = datetime(2026, 4, 8, 0, 1, 0)
    creator_bid = "creator-renewal-drift-reserved-only"
    subscription_bid = "subscription-renewal-drift-reserved-only"
    order_bid = "order-renewal-drift-reserved-only"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-reserved-only",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-reserved-only",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
        )
        product = _create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-reserved-only",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(datetime(2026, 4, 8, 0, 0, 0)),
                "renewal_cycle_end_at": to_utc_iso(datetime(2026, 5, 8, 0, 0, 0)),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-reserved-only",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-reserved-only",
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 5, 1, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-reserved-only"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-reserved-only",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=datetime(2026, 5, 8, 0, 0, 0),
            consumable_from=datetime(2026, 4, 8, 0, 0, 0),
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([wallet, subscription, product, order, bucket, ledger])
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=repaired_at,
            dry_run=True,
        )

    assert payload["status"] == "dry_run"
    assert payload["creator_count"] == 1
    assert payload["creator_bids"] == [creator_bid]
    assert payload["stale_subscription_count"] == 0
    assert payload["stale_bucket_count"] == 0
    assert payload["overdue_reserved_grant_count"] == 1
    assert payload["activatable_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_counts_only_successful_activations(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-activation-fails"
    subscription_bid = "subscription-renewal-drift-activation-fails"
    order_bid = "order-renewal-drift-activation-fails"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-activation-fails",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("2000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-activation-fails",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = _create_monthly_plan_product(subscription.product_bid)
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-activation-fails",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-activation-fails",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-activation-fails",
            priority=20,
            original_credits=Decimal("1500.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-activation-fails"},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-activation-fails",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order.bill_order_bid,
            idempotency_key=f"grant:{order.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all([wallet, subscription, product, order, bucket, ledger])
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_count"] == 0
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_count"] == 1
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.current_period_end_at == boundary_at
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("1000.0000000000")
    assert bucket.reserved_credits == Decimal("500.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_cycle_when_subscription_grant_missing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-subscription-grant"
    subscription_bid = "subscription-renewal-drift-missing-subscription-grant"
    product_bid = "bill-product-renewal-drift-missing-subscription-grant"
    first_order_bid = "order-renewal-drift-missing-subscription-grant-1"
    missing_order_bid = "order-renewal-drift-missing-subscription-grant-2"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-subscription-grant",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        first_order = BillingOrder(
            bill_order_bid=first_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=first_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        missing_order = BillingOrder(
            bill_order_bid=missing_order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=missing_order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-subscription-grant",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=first_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": first_order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-subscription-grant",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=first_order_bid,
            idempotency_key=f"grant:{first_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": first_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                _create_monthly_plan_product(product_bid),
                first_order,
                missing_order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["activatable_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_unknown_subscription_grant_state(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-unknown-subscription-state"
    subscription_bid = "subscription-renewal-drift-unknown-subscription-state"
    order_bid = "order-renewal-drift-unknown-subscription-state"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-unknown-subscription-state",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-unknown-subscription-state",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-unknown-subscription-state",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-unknown-subscription-state",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "unknown",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                _create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert bucket.reserved_credits == Decimal("1000.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "unknown"


def test_repair_renewal_state_drift_blocks_short_subscription_grant_amount(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-short-subscription-amount"
    subscription_bid = "subscription-renewal-drift-short-subscription-amount"
    order_bid = "order-renewal-drift-short-subscription-amount"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-short-subscription-amount",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1.0000000000"),
            lifetime_granted_credits=Decimal("1.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-short-subscription-amount",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-short-subscription-amount",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-short-subscription-amount",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                _create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        dry_payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )
        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket)
        dao.db.session.refresh(ledger)

    assert dry_payload["activatable_creator_bids"] == []
    assert dry_payload["protected_creator_bids"] == [creator_bid]
    assert dry_payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert bucket.reserved_credits == Decimal("1.0000000000")
    assert ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_all_scope_falls_back_to_source_bid(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-source-bid-fallback"
    order_bid = "order-renewal-drift-source-bid-fallback"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid="subscription-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-source-bid-fallback",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
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
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-source-bid-fallback",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-source-bid-fallback",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": "",
                "subscription_bid": subscription.subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                _create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["creator_bids"] == [creator_bid]
    assert payload["overdue_reserved_grants"][0]["bill_order_bid"] == order_bid
    assert payload["activatable_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_when_campaign_bonus_grant_missing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-missing-campaign-grant"
    subscription_bid = "subscription-renewal-drift-missing-campaign-grant"
    order_bid = "order-renewal-drift-missing-campaign-grant"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-missing-campaign-grant",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            lifetime_granted_credits=Decimal("1000.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-missing-campaign-grant",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=subscription.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id=order_bid,
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-renewal-drift-missing-campaign-grant",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-missing-campaign-grant",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_bid},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-missing-campaign-grant",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                _create_monthly_plan_product(subscription.product_bid),
                order,
                bucket,
                ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=True,
        )

    assert payload["activatable_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["manual_review_creator_bids"] == [creator_bid]


def test_repair_renewal_state_drift_blocks_same_order_when_bonus_only_would_succeed(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-bonus-only-success"
    subscription_bid = "subscription-renewal-drift-bonus-only-success"
    product_bid = "bill-product-renewal-drift-bonus-only-success"
    order_bid = "order-renewal-drift-bonus-only-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-bonus-only-success",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("600.0000000000"),
            lifetime_granted_credits=Decimal("1600.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-bonus-only-success",
            product_type=1,
            display_name_i18n_key="billing.product.repair_bonus_only_success",
            description_i18n_key="billing.product.repair_bonus_only_success.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-bonus-only-success",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-bonus-only-success",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-bonus-only-success-subscription",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-bonus-only-success",
            priority=20,
            original_credits=Decimal("1500.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-bonus-only-success"},
        )
        bonus_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-bonus-only-success-bonus",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("100.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "bill_order_bid": order_bid,
                "grant_reason": "campaign_bonus",
            },
        )
        subscription_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-bonus-only-success-subscription",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=subscription_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        bonus_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-bonus-only-success-bonus",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bonus_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            idempotency_key=f"grant:campaign_bonus:{order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("500.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "campaign_bid": order.campaign_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product,
                order,
                subscription_bucket,
                bonus_bucket,
                subscription_ledger,
                bonus_ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(subscription_bucket)
        dao.db.session.refresh(bonus_bucket)
        dao.db.session.refresh(subscription_ledger)
        dao.db.session.refresh(bonus_ledger)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert payload["updated_subscription_count"] == 0
    assert payload["expired_bucket_count"] == 0
    assert subscription.current_period_end_at == boundary_at
    assert subscription_bucket.reserved_credits == Decimal("500.0000000000")
    assert bonus_bucket.reserved_credits == Decimal("100.0000000000")
    assert subscription_ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert bonus_ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_same_order_when_subscription_only_would_succeed(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-subscription-only-success"
    subscription_bid = "subscription-renewal-drift-subscription-only-success"
    product_bid = "bill-product-renewal-drift-subscription-only-success"
    order_bid = "order-renewal-drift-subscription-only-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-subscription-only-success",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1050.0000000000"),
            lifetime_granted_credits=Decimal("2050.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid=product_bid,
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product = BillingProduct(
            product_bid=product_bid,
            product_code="repair-subscription-only-success",
            product_type=1,
            display_name_i18n_key="billing.product.repair_subscription_only_success",
            description_i18n_key="billing.product.repair_subscription_only_success.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order = BillingOrder(
            bill_order_bid=order_bid,
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-subscription-only-success",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            campaign_bid="campaign-subscription-only-success",
            campaign_bonus_credit_amount=Decimal("100.0000000000"),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        subscription_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-subscription-only-success-subscription",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-subscription-only-success",
            priority=20,
            original_credits=Decimal("2000.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-subscription-only-success"},
        )
        bonus_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-subscription-only-success-bonus",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            priority=20,
            original_credits=Decimal("100.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={
                "bill_order_bid": order_bid,
                "grant_reason": "campaign_bonus",
            },
        )
        subscription_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-subscription-only-success-subscription",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=subscription_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_bid,
            idempotency_key=f"grant:{order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        bonus_ledger = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-subscription-only-success-bonus",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bonus_bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
            source_bid=order_bid,
            idempotency_key=f"grant:campaign_bonus:{order_bid}",
            amount=Decimal("100.0000000000"),
            balance_after=Decimal("1000.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_bid,
                "campaign_bid": order.campaign_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product,
                order,
                subscription_bucket,
                bonus_bucket,
                subscription_ledger,
                bonus_ledger,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(subscription_bucket)
        dao.db.session.refresh(bonus_bucket)
        dao.db.session.refresh(subscription_ledger)
        dao.db.session.refresh(bonus_ledger)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["activated_creator_bids"] == []
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.current_period_end_at == boundary_at
    assert subscription_bucket.reserved_credits == Decimal("1000.0000000000")
    assert bonus_bucket.reserved_credits == Decimal("50.0000000000")
    assert subscription_ledger.metadata_json["bucket_credit_state"] == "reserved"
    assert bonus_ledger.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_blocks_multi_order_cycle_atomically(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-multi-order-blocked"
    subscription_bid = "subscription-renewal-drift-multi-order-blocked"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-multi-order-blocked",
            creator_bid=creator_bid,
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("550.0000000000"),
            lifetime_granted_credits=Decimal("1550.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-multi-order-blocked-a",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product_a = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-blocked-a",
            product_code="repair-multi-order-blocked-a",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_blocked_a",
            description_i18n_key="billing.product.repair_multi_order_blocked_a.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("50.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        product_b = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-blocked-b",
            product_code="repair-multi-order-blocked-b",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_blocked_b",
            description_i18n_key="billing.product.repair_multi_order_blocked_b.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order_a = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-blocked-a",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_a.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-blocked-a",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        order_b = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-blocked-b",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_b.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-blocked-b",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket_a = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-blocked-a",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-multi-order-blocked-a",
            priority=20,
            original_credits=Decimal("1050.0000000000"),
            available_credits=Decimal("1000.0000000000"),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 3, 8, 0, 0, 0),
            effective_to=boundary_at,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": "order-current-multi-order-blocked-a"},
        )
        bucket_b = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-blocked-b",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-current-multi-order-blocked-b",
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("500.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_b.bill_order_bid},
        )
        ledger_a = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-blocked-a",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_a.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            idempotency_key=f"grant:{order_a.bill_order_bid}",
            amount=Decimal("50.0000000000"),
            balance_after=Decimal("50.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_a.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        ledger_b = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-blocked-b",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_b.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            idempotency_key=f"grant:{order_b.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("50.0000000000"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_b.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product_a,
                product_b,
                order_a,
                order_b,
                bucket_a,
                bucket_b,
                ledger_a,
                ledger_b,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(bucket_a)
        dao.db.session.refresh(bucket_b)
        dao.db.session.refresh(ledger_a)
        dao.db.session.refresh(ledger_b)

    assert payload["activated_reserved_order_count"] == 0
    assert payload["protected_creator_bids"] == [creator_bid]
    assert subscription.current_period_end_at == boundary_at
    assert bucket_a.reserved_credits == Decimal("50.0000000000")
    assert bucket_b.reserved_credits == Decimal("500.0000000000")
    assert ledger_a.metadata_json["bucket_credit_state"] == "reserved"
    assert ledger_b.metadata_json["bucket_credit_state"] == "reserved"


def test_repair_renewal_state_drift_counts_all_activated_orders_in_shared_cycle(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    boundary_at = datetime(2026, 4, 8, 0, 0, 0)
    next_cycle_end = datetime(2026, 5, 8, 0, 0, 0)
    creator_bid = "creator-renewal-drift-multi-order-success"
    subscription_bid = "subscription-renewal-drift-multi-order-success"

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-renewal-drift-multi-order-success",
            creator_bid=creator_bid,
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1050.0000000000"),
            lifetime_granted_credits=Decimal("1050.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        subscription = BillingSubscription(
            subscription_bid=subscription_bid,
            creator_bid=creator_bid,
            product_bid="bill-product-renewal-drift-multi-order-success-a",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 3, 8, 0, 0, 0),
            current_period_end_at=boundary_at,
        )
        product_a = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-success-a",
            product_code="repair-multi-order-success-a",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_success_a",
            description_i18n_key="billing.product.repair_multi_order_success_a.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("50.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        product_b = BillingProduct(
            product_bid="bill-product-renewal-drift-multi-order-success-b",
            product_code="repair-multi-order-success-b",
            product_type=1,
            display_name_i18n_key="billing.product.repair_multi_order_success_b",
            description_i18n_key="billing.product.repair_multi_order_success_b.description",
            status=1,
            billing_mode=2,
            billing_interval=2,
            billing_interval_count=1,
            credit_amount=Decimal("1000.0000000000"),
            currency="CNY",
            price_amount=0,
            allocation_interval=2,
            auto_renew_enabled=1,
        )
        order_a = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-success-a",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_a.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-success-a",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 0, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        order_b = BillingOrder(
            bill_order_bid="order-renewal-drift-multi-order-success-b",
            creator_bid=creator_bid,
            order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
            product_bid=product_b.product_bid,
            subscription_bid=subscription_bid,
            currency="CNY",
            payable_amount=0,
            paid_amount=0,
            payment_provider="manual",
            channel="manual",
            provider_reference_id="repair-multi-order-success-b",
            status=BILLING_ORDER_STATUS_PAID,
            paid_at=datetime(2026, 4, 7, 0, 1, 0),
            metadata_json={
                "renewal_cycle_start_at": to_utc_iso(boundary_at),
                "renewal_cycle_end_at": to_utc_iso(next_cycle_end),
            },
        )
        bucket_a = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-success-a",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            priority=20,
            original_credits=Decimal("50.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("50.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_a.bill_order_bid},
        )
        bucket_b = CreditWalletBucket(
            wallet_bucket_bid="bucket-renewal-drift-multi-order-success-b",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            priority=20,
            original_credits=Decimal("1000.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("1000.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=boundary_at,
            effective_to=next_cycle_end,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={"bill_order_bid": order_b.bill_order_bid},
        )
        ledger_a = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-success-a",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_a.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_a.bill_order_bid,
            idempotency_key=f"grant:{order_a.bill_order_bid}",
            amount=Decimal("50.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_a.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        ledger_b = CreditLedgerEntry(
            ledger_bid="ledger-renewal-drift-multi-order-success-b",
            creator_bid=creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket_b.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid=order_b.bill_order_bid,
            idempotency_key=f"grant:{order_b.bill_order_bid}",
            amount=Decimal("1000.0000000000"),
            balance_after=Decimal("0"),
            expires_at=next_cycle_end,
            consumable_from=boundary_at,
            metadata_json={
                "bill_order_bid": order_b.bill_order_bid,
                "subscription_bid": subscription_bid,
                "bucket_credit_state": "reserved",
            },
        )
        dao.db.session.add_all(
            [
                wallet,
                subscription,
                product_a,
                product_b,
                order_a,
                order_b,
                bucket_a,
                bucket_b,
                ledger_a,
                ledger_b,
            ]
        )
        dao.db.session.commit()

        payload = repair_renewal_state_drift(
            billing_wallet_lifecycle_app,
            creator_bid=creator_bid,
            repair_before=boundary_at + timedelta(minutes=1),
            dry_run=False,
        )
        dao.db.session.refresh(subscription)
        dao.db.session.refresh(wallet)
        dao.db.session.refresh(bucket_a)
        dao.db.session.refresh(bucket_b)
        dao.db.session.refresh(ledger_a)
        dao.db.session.refresh(ledger_b)

    assert payload["activated_reserved_order_count"] == 2
    assert payload["activated_creator_count"] == 1
    assert payload["activated_creator_bids"] == [creator_bid]
    assert payload["protected_creator_bids"] == []
    assert subscription.current_period_start_at == boundary_at
    assert subscription.current_period_end_at == next_cycle_end
    assert wallet.available_credits == Decimal("1050.0000000000")
    assert wallet.reserved_credits == Decimal("0E-10")
    assert bucket_a.available_credits == Decimal("50.0000000000")
    assert bucket_a.reserved_credits == Decimal("0E-10")
    assert bucket_b.available_credits == Decimal("1000.0000000000")
    assert bucket_b.reserved_credits == Decimal("0E-10")
    assert ledger_a.metadata_json["bucket_credit_state"] == "available"
    assert ledger_b.metadata_json["bucket_credit_state"] == "available"


def test_repair_expire_ledger_bucket_drift_dry_run_reports_without_writing(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-dry-run",
            creator_bid="creator-expire-ledger-drift-dry-run",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-dry-run",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-dry-run",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-dry-run",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=True,
        )

        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-dry-run"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-dry-run"
        ).one()

    assert payload["status"] == "dry_run"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert payload["buckets"][0]["previous_available_credits"] == 2.5
    assert payload["buckets"][0]["available_credits"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("2.5000000000")


def test_repair_expire_ledger_bucket_drift_applies_bucket_and_wallet_snapshot(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-apply",
            creator_bid="creator-expire-ledger-drift-apply",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-apply",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-apply",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-apply",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-apply"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-apply"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal("0")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.version == 1
    assert len(ledgers) == 1


def test_repair_expire_ledger_bucket_drift_accepts_cycle_scoped_expire_key(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-cycle-key",
            creator_bid="creator-expire-ledger-drift-cycle-key",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-cycle-key",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-cycle-key",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-cycle-key",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=_build_expire_ledger_idempotency_key(
                bucket.wallet_bucket_bid,
                effective_to=bucket.effective_to,
            ),
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-cycle-key"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-cycle-key"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.available_credits == Decimal("0")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")


def test_repair_expire_ledger_bucket_drift_keeps_existing_expired_amount(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-counted",
            creator_bid="creator-expire-ledger-drift-counted",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-counted",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-counted",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("2.5000000000"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-counted",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-counted"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["bucket_count"] == 1
    assert payload["buckets"][0]["previous_expired_credits"] == 2.5
    assert payload["buckets"][0]["expired_credits"] == 2.5
    assert bucket.available_credits == Decimal("0")
    assert bucket.expired_credits == Decimal("2.5000000000")


def test_repair_expire_ledger_bucket_drift_skips_reused_bucket_for_manual_review(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-reused",
            creator_bid="creator-expire-ledger-drift-reused",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("15.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-reused",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-reused-second-cycle",
            priority=30,
            original_credits=Decimal("15.0000000000"),
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            consumed_credits=Decimal("7.5000000000"),
            expired_credits=Decimal("2.5000000000"),
            effective_from=datetime(2026, 5, 1, 0, 0, 0),
            effective_to=datetime(2026, 5, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-reused-old",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-reused-first-cycle",
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=datetime(2026, 4, 7, 0, 0, 0),
            consumable_from=datetime(2026, 4, 1, 0, 0, 0),
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 5, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-reused"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-reused"
        ).one()

    assert payload["status"] == "manual_review"
    assert payload["bucket_count"] == 1
    assert payload["repaired_bucket_count"] == 0
    assert payload["manual_review_count"] == 1
    assert payload["buckets"][0]["repair_action"] == "manual_review"
    assert payload["buckets"][0]["repair_reason"] == "expire_ledger_expiry_mismatch"
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("5.0000000000")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("5.0000000000")
    assert wallet.version == 0


def test_repair_expire_ledger_bucket_drift_sets_exhausted_for_reserved_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-ledger-drift-reserved",
            creator_bid="creator-expire-ledger-drift-reserved",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("1.0000000000"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("7.5000000000"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-ledger-drift-reserved",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-ledger-drift-reserved",
            priority=30,
            original_credits=Decimal("10.0000000000"),
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("1.0000000000"),
            consumed_credits=Decimal("6.5000000000"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        ledger = CreditLedgerEntry(
            ledger_bid="ledger-expire-ledger-drift-reserved",
            creator_bid=wallet.creator_bid,
            wallet_bid=wallet.wallet_bid,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=bucket.source_bid,
            idempotency_key=f"expire:{bucket.wallet_bucket_bid}",
            amount=Decimal("-2.5000000000"),
            balance_after=Decimal("0"),
            expires_at=bucket.effective_to,
            consumable_from=bucket.effective_from,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket, ledger])
        dao.db.session.commit()

        payload = repair_expire_ledger_bucket_drift(
            billing_wallet_lifecycle_app,
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            repair_before=datetime(2026, 4, 8, 0, 0, 0),
            dry_run=False,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-ledger-drift-reserved"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-ledger-drift-reserved"
        ).one()

    assert payload["status"] == "repaired"
    assert payload["repaired_bucket_count"] == 1
    assert payload["manual_review_count"] == 0
    assert payload["buckets"][0]["repair_action"] == "repair"
    assert bucket.status == CREDIT_BUCKET_STATUS_EXHAUSTED
    assert bucket.available_credits == Decimal("0")
    assert bucket.reserved_credits == Decimal("1.0000000000")
    assert bucket.expired_credits == Decimal("2.5000000000")
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.reserved_credits == Decimal("1.0000000000")


def test_grant_refund_return_credits_creates_subscription_bucket_and_refund_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-refund-return-1",
                creator_bid="creator-refund-return-1",
                product_bid="bill-product-refund-return",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=datetime(2026, 4, 8, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 8, 0, 0, 0),
            )
        )
        dao.db.session.commit()

        payload = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-refund-return-1",
            amount=Decimal("1.2500000000"),
            refund_bid="refund-return-1",
            metadata={"reason": "usage_reversal"},
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-refund-return-1"
        ).one()
        bucket = CreditWalletBucket.query.filter_by(source_bid="refund-return-1").one()
        ledger = CreditLedgerEntry.query.filter_by(source_bid="refund-return-1").one()

        assert payload["status"] == "granted"
        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
        assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
        assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bucket.available_credits == Decimal("1.2500000000")
        assert bucket.metadata_json["refund_return"] is True
        assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND
        assert ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
        assert ledger.amount == Decimal("1.2500000000")
        assert ledger.balance_after == Decimal("1.2500000000")
        assert wallet.available_credits == Decimal("1.2500000000")

        second = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-refund-return-1",
            amount=Decimal("1.2500000000"),
            refund_bid="refund-return-1",
        )
        assert second["status"] == "already_granted"
        assert (
            CreditLedgerEntry.query.filter_by(source_bid="refund-return-1").count() == 1
        )


def test_grant_manual_credit_wallet_balance_returns_existing_ledger_payload(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        first = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-idempotent-1",
            amount=Decimal("2.5000000000"),
            source_bid="grant-manual-idempotent-1",
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
            effective_to=datetime(2026, 4, 9, 12, 0, 0),
            idempotency_key="manual-grant-idempotent-1",
            metadata={
                "grant_source": "reward",
                "validity_preset": "1d",
            },
        )
        second = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-idempotent-1",
            amount=Decimal("9.9000000000"),
            source_bid="grant-manual-idempotent-2",
            effective_from=datetime(2026, 4, 8, 13, 0, 0),
            effective_to=datetime(2026, 4, 15, 12, 0, 0),
            idempotency_key="manual-grant-idempotent-1",
            metadata={
                "grant_source": "compensation",
                "validity_preset": "7d",
            },
        )

        ledger = CreditLedgerEntry.query.filter_by(
            creator_bid="creator-manual-idempotent-1",
            idempotency_key="manual-grant-idempotent-1",
        ).one()

    assert first["status"] == "granted"
    assert second["status"] == "noop_existing"
    assert second["ledger_bid"] == first["ledger_bid"]
    assert second["amount"] == 2.5
    assert second["expires_at"] == datetime(2026, 4, 9, 12, 0, 0)
    assert second["metadata_json"]["grant_source"] == "reward"
    assert second["metadata_json"]["validity_preset"] == "1d"
    assert ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT


def test_grant_manual_credit_wallet_balance_returns_noop_existing_after_integrity_error(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = CreditLedgerEntry(
        ledger_bid="ledger-existing-manual-grant",
        creator_bid="creator-manual-race-1",
        wallet_bid="wallet-existing-manual-grant",
        wallet_bucket_bid="bucket-existing-manual-grant",
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        source_bid="grant-existing-manual-grant",
        idempotency_key="manual-grant-race-1",
        amount=Decimal("3.0000000000"),
        balance_after=Decimal("3.0000000000"),
        expires_at=datetime(2026, 4, 9, 12, 0, 0),
        consumable_from=datetime(2026, 4, 8, 12, 0, 0),
        metadata_json={
            "grant_source": "reward",
            "validity_preset": "1d",
        },
    )

    original_commit = dao.db.session.commit
    state = {"raised": False}

    def _commit_once_with_duplicate():
        if not state["raised"]:
            state["raised"] = True
            dao.db.session.rollback()
            dao.db.session.add(existing)
            original_commit()
            raise IntegrityError("duplicate", {}, Exception("duplicate"))
        return original_commit()

    monkeypatch.setattr(dao.db.session, "commit", _commit_once_with_duplicate)

    with billing_wallet_lifecycle_app.app_context():
        result = grant_manual_credit_wallet_balance(
            billing_wallet_lifecycle_app,
            creator_bid="creator-manual-race-1",
            amount=Decimal("4.0000000000"),
            source_bid="grant-manual-race-1",
            effective_from=datetime(2026, 4, 8, 12, 0, 0),
            effective_to=datetime(2026, 4, 9, 12, 0, 0),
            idempotency_key="manual-grant-race-1",
            metadata={
                "grant_source": "compensation",
                "validity_preset": "7d",
            },
        )

    assert result["status"] == "noop_existing"
    assert result["ledger_bid"] == "ledger-existing-manual-grant"
    assert result["amount"] == 3
    assert result["metadata_json"]["grant_source"] == "reward"


def test_rebuild_credit_wallet_snapshots_recomputes_from_bucket_rows(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        snapshot_at = datetime(2026, 4, 10, 0, 0, 0)
        monkeypatch.setattr(
            "flaskr.service.billing.wallets.now_utc",
            lambda: snapshot_at,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-1",
            creator_bid="creator-rebuild-1",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("999.0000000000"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-rebuild-1",
                creator_bid="creator-rebuild-1",
                product_bid="product-rebuild-1",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=snapshot_at - timedelta(days=1),
                current_period_end_at=snapshot_at + timedelta(days=30),
            )
        )
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-1a",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_REFUND,
                    source_bid="refund-rebuild-1",
                    priority=10,
                    original_credits=Decimal("2.0000000000"),
                    available_credits=Decimal("1.5000000000"),
                    reserved_credits=Decimal("0.2500000000"),
                    consumed_credits=Decimal("0.5000000000"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-1b",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="topup-rebuild-1",
                    priority=30,
                    original_credits=Decimal("3.0000000000"),
                    available_credits=Decimal("2.0000000000"),
                    reserved_credits=Decimal("0.5000000000"),
                    consumed_credits=Decimal("1.0000000000"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-1",
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-rebuild-1").one()

        assert payload["status"] == "rebuilt"
        assert payload["wallet_count"] == 1
        assert payload["wallets"][0]["available_credits"] == 3.5
        assert payload["wallets"][0]["reserved_credits"] == 0.75
        assert wallet.available_credits == Decimal("3.5000000000")
        assert wallet.reserved_credits == Decimal("0.7500000000")
        assert wallet.version == 1


def test_rebuild_credit_wallet_snapshots_excludes_non_consumable_bucket_rows(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        snapshot_at = datetime(2026, 4, 10, 0, 0, 0)
        monkeypatch.setattr(
            "flaskr.service.billing.wallets.now_utc",
            lambda: snapshot_at,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-consumable-1",
            creator_bid="creator-rebuild-consumable-1",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("999.0000000000"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-consumable-manual",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-consumable-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-rebuild-consumable-1",
                    priority=20,
                    original_credits=Decimal("4.0000000000"),
                    available_credits=Decimal("4.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at - timedelta(days=1),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-consumable-topup",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-consumable-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="topup-rebuild-consumable-1",
                    priority=30,
                    original_credits=Decimal("6.0000000000"),
                    available_credits=Decimal("6.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at - timedelta(days=1),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-consumable-future",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-consumable-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-rebuild-consumable-future",
                    priority=20,
                    original_credits=Decimal("5.0000000000"),
                    available_credits=Decimal("5.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at + timedelta(days=1),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-consumable-1",
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-rebuild-consumable-1"
        ).one()

        assert payload["wallets"][0]["available_credits"] == 4
        assert wallet.available_credits == Decimal("4.0000000000")


def test_rebuild_credit_wallet_snapshots_keeps_current_bucket_with_reserved_balance(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        snapshot_at = datetime(2026, 7, 20, 0, 0, 0)
        current_period_start = datetime(2026, 6, 24, 7, 35, 58)
        current_period_end = datetime(2026, 7, 23, 15, 59, 59)
        monkeypatch.setattr(
            "flaskr.service.billing.wallets.now_utc",
            lambda: snapshot_at,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-reserved-current",
            creator_bid="creator-rebuild-reserved-current",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("999.0000000000"),
            lifetime_granted_credits=Decimal("4050.0000000000"),
            lifetime_consumed_credits=Decimal("315.2400000000"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="subscription-rebuild-reserved-current",
                creator_bid="creator-rebuild-reserved-current",
                product_bid="bill-product-plan-monthly-pro",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=current_period_start,
                current_period_end_at=current_period_end,
            )
        )
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-reserved-current",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-reserved-current",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="bill-current-period",
                    priority=20,
                    original_credits=Decimal("4050.0000000000"),
                    available_credits=Decimal("1684.7600000000"),
                    reserved_credits=Decimal("2050.0000000000"),
                    consumed_credits=Decimal("315.2400000000"),
                    expired_credits=Decimal("0"),
                    effective_from=current_period_start,
                    effective_to=current_period_end,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-reserved-topup",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-reserved-current",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="bill-topup-current",
                    priority=30,
                    original_credits=Decimal("250.0000000000"),
                    available_credits=Decimal("234.7800000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("15.2200000000"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at - timedelta(days=1),
                    effective_to=current_period_end,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-reserved-current",
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-rebuild-reserved-current"
        ).one()

        assert payload["wallets"][0]["available_credits"] == 1919.54
        assert payload["wallets"][0]["reserved_credits"] == 2050
        assert wallet.available_credits == Decimal("1919.5400000000")
        assert wallet.reserved_credits == Decimal("2050.0000000000")


def test_rebuild_credit_wallet_snapshots_dry_run_reports_without_writing(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        snapshot_at = datetime(2026, 4, 10, 0, 0, 0)
        monkeypatch.setattr(
            "flaskr.service.billing.wallets.now_utc",
            lambda: snapshot_at,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-dry-run-1",
            creator_bid="creator-rebuild-dry-run-1",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("3.0000000000"),
            lifetime_granted_credits=Decimal("20.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-dry-run-current",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-dry-run-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-rebuild-dry-run-1",
                    priority=20,
                    original_credits=Decimal("7.0000000000"),
                    available_credits=Decimal("7.0000000000"),
                    reserved_credits=Decimal("1.0000000000"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at - timedelta(days=1),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-rebuild-dry-run-future",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-rebuild-dry-run-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="subscription-rebuild-dry-run-1",
                    priority=20,
                    original_credits=Decimal("13.0000000000"),
                    available_credits=Decimal("13.0000000000"),
                    reserved_credits=Decimal("2.0000000000"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=snapshot_at + timedelta(days=1),
                    effective_to=snapshot_at + timedelta(days=31),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-dry-run-1",
            dry_run=True,
        )

        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-rebuild-dry-run-1"
        ).one()

        assert payload["status"] == "dry_run"
        assert payload["dry_run"] is True
        assert payload["wallet_count"] == 1
        assert payload["changed_wallet_count"] == 1
        assert payload["wallets"][0]["previous_available_credits"] == 999
        assert payload["wallets"][0]["available_credits"] == 7
        assert payload["wallets"][0]["available_credits_delta"] == -992
        assert payload["wallets"][0]["previous_reserved_credits"] == 3
        assert payload["wallets"][0]["reserved_credits"] == 3
        assert payload["wallets"][0]["changed"] is True
        assert wallet.available_credits == Decimal("999.0000000000")
        assert wallet.reserved_credits == Decimal("3.0000000000")
        assert wallet.version == 0


def test_rebuild_credit_wallet_snapshots_dry_run_preserves_outer_transaction(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        snapshot_at = datetime(2026, 4, 10, 0, 0, 0)
        monkeypatch.setattr(
            "flaskr.service.billing.wallets.now_utc",
            lambda: snapshot_at,
        )
        wallet = CreditWallet(
            wallet_bid="wallet-rebuild-dry-run-outer-1",
            creator_bid="creator-rebuild-dry-run-outer-1",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("1.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid="bucket-rebuild-dry-run-outer-1",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-rebuild-dry-run-outer-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="manual-rebuild-dry-run-outer-1",
                priority=20,
                original_credits=Decimal("1.0000000000"),
                available_credits=Decimal("1.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=snapshot_at - timedelta(days=1),
                effective_to=None,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={},
            )
        )
        dao.db.session.commit()

        outer_marker = CreditWallet(
            wallet_bid="wallet-outer-marker-1",
            creator_bid="creator-outer-marker-1",
            available_credits=Decimal("5.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(outer_marker)

        payload = rebuild_credit_wallet_snapshots(
            billing_wallet_lifecycle_app,
            creator_bid="creator-rebuild-dry-run-outer-1",
            dry_run=True,
        )
        dao.db.session.commit()

        marker = CreditWallet.query.filter_by(
            creator_bid="creator-outer-marker-1"
        ).one_or_none()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-rebuild-dry-run-outer-1"
        ).one()

        assert payload["status"] == "dry_run"
        assert marker is not None
        assert wallet.available_credits == Decimal("999.0000000000")
        assert wallet.version == 0


def test_grant_refund_return_credits_maps_topup_orders_back_to_topup_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        dao.db.session.add(
            BillingOrder(
                bill_order_bid="order-topup-refund-1",
                creator_bid="creator-topup-refund-1",
                order_type=BILLING_ORDER_TYPE_TOPUP,
                product_bid="bill-product-topup-small",
            )
        )
        dao.db.session.commit()

        payload = grant_refund_return_credits(
            billing_wallet_lifecycle_app,
            creator_bid="creator-topup-refund-1",
            amount=Decimal("2.0000000000"),
            refund_bid="refund-topup-refund-1",
            metadata={"bill_order_bid": "order-topup-refund-1"},
        )

        bucket = CreditWalletBucket.query.filter_by(
            source_bid="refund-topup-refund-1"
        ).one()

        assert payload["status"] == "granted"
        assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP


def test_usage_split_and_bucket_expiry_keep_wallet_bucket_and_ledger_consistent(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.billing.settlement.resolve_usage_creator_bid",
        lambda app, usage: "creator-consistency-1",
    )

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-consistency-1",
            creator_bid="creator-consistency-1",
            available_credits=Decimal("4.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("4.5000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        dao.db.session.add(wallet)
        dao.db.session.add_all(
            [
                BillingSubscription(
                    subscription_bid="subscription-consistency-1",
                    creator_bid="creator-consistency-1",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=datetime(2026, 4, 8, 0, 0, 0),
                    current_period_end_at=datetime(2026, 4, 30, 0, 0, 0),
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-free",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_REFUND,
                    source_bid="grant-consistency-free",
                    priority=10,
                    original_credits=Decimal("1.0000000000"),
                    available_credits=Decimal("1.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-sub",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=0,
                    source_bid="grant-consistency-sub",
                    priority=20,
                    original_credits=Decimal("1.5000000000"),
                    available_credits=Decimal("1.5000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-consistency-topup",
                    wallet_bid=wallet.wallet_bid,
                    creator_bid="creator-consistency-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="grant-consistency-topup",
                    priority=30,
                    original_credits=Decimal("2.0000000000"),
                    available_credits=Decimal("2.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=datetime(2026, 4, 9, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
                CreditUsageRate(
                    rate_bid="rate-consistency-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-consistency",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    unit_size=1000,
                    credits_per_unit=Decimal("0.5000000000"),
                    rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
                    effective_from=datetime(2026, 4, 8, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
                ),
                BillUsageRecord(
                    usage_bid="usage-consistency-1",
                    parent_usage_bid="",
                    user_bid="learner-consistency-1",
                    shifu_bid="shifu-consistency-1",
                    outline_item_bid="",
                    progress_record_bid="",
                    generated_block_bid="",
                    audio_bid="",
                    request_id="req-consistency-1",
                    trace_id="trace-consistency-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    record_level=0,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    provider="openai",
                    model="gpt-consistency",
                    is_stream=0,
                    input=5000,
                    input_cache=0,
                    output=0,
                    total=5000,
                    word_count=0,
                    duration_ms=1000,
                    latency_ms=100,
                    segment_index=0,
                    segment_count=0,
                    billable=1,
                    status=0,
                    error_message="",
                    extra={},
                    created_at=datetime(2026, 4, 8, 12, 0, 0),
                    updated_at=datetime(2026, 4, 8, 12, 0, 0),
                ),
            ]
        )
        dao.db.session.commit()

        settle_payload = settle_bill_usage(
            billing_wallet_lifecycle_app,
            usage_bid="usage-consistency-1",
        )
        expire_payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-consistency-1",
            expire_before=datetime(2026, 4, 10, 0, 0, 0),
        )

        wallet = CreditWallet.query.filter_by(creator_bid="creator-consistency-1").one()
        buckets = {
            bucket.wallet_bucket_bid: bucket
            for bucket in CreditWalletBucket.query.filter_by(
                creator_bid="creator-consistency-1"
            ).all()
        }
        usage_entries = (
            CreditLedgerEntry.query.filter_by(
                creator_bid="creator-consistency-1",
                source_type=CREDIT_SOURCE_TYPE_USAGE,
                source_bid="usage-consistency-1",
            )
            .order_by(CreditLedgerEntry.id.asc())
            .all()
        )
        expire_entry = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-consistency-topup",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).one()

        assert settle_payload["status"] == "settled"
        assert settle_payload["entry_count"] == 1
        assert settle_payload["consumed_credits"] == 2.5
        assert len(usage_entries) == 1
        assert usage_entries[0].wallet_bucket_bid == ""
        assert usage_entries[0].amount == Decimal("-2.5000000000")
        assert usage_entries[0].balance_after == Decimal("2.0000000000")
        assert [
            item["wallet_bucket_bid"]
            for item in usage_entries[0].metadata_json["bucket_breakdown"]
        ] == [
            "bucket-consistency-free",
            "bucket-consistency-sub",
        ]

        assert expire_payload["status"] == "expired"
        assert expire_payload["bucket_count"] == 1
        assert expire_payload["expired_credits"] == 2
        assert expire_entry.amount == Decimal("-2.0000000000")
        assert expire_entry.balance_after == Decimal("0E-10")

        assert wallet.available_credits == Decimal("0E-10")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert wallet.lifetime_consumed_credits == Decimal("2.5000000000")

        assert buckets["bucket-consistency-free"].available_credits == Decimal("0E-10")
        assert buckets["bucket-consistency-free"].consumed_credits == Decimal(
            "1.0000000000"
        )
        assert buckets["bucket-consistency-sub"].available_credits == Decimal("0E-10")
        assert buckets["bucket-consistency-sub"].consumed_credits == Decimal(
            "1.5000000000"
        )
        assert buckets["bucket-consistency-topup"].available_credits == Decimal("0")
        assert buckets["bucket-consistency-topup"].expired_credits == Decimal(
            "2.0000000000"
        )
        assert (
            buckets["bucket-consistency-topup"].status == CREDIT_BUCKET_STATUS_EXPIRED
        )

        bucket_available_total = sum(
            (bucket.available_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        bucket_consumed_total = sum(
            (bucket.consumed_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        bucket_expired_total = sum(
            (bucket.expired_credits for bucket in buckets.values()),
            start=Decimal("0"),
        )
        ledger_reduction_total = sum(
            (
                -entry.amount
                for entry in CreditLedgerEntry.query.filter_by(
                    creator_bid="creator-consistency-1"
                ).all()
            ),
            start=Decimal("0"),
        )

        assert bucket_available_total == wallet.available_credits
        assert bucket_consumed_total == Decimal("2.5000000000")
        assert bucket_expired_total == Decimal("2.0000000000")
        assert ledger_reduction_total == Decimal("4.5000000000")
        for bucket in buckets.values():
            assert bucket.original_credits == (
                bucket.available_credits
                + bucket.consumed_credits
                + bucket.expired_credits
            )
