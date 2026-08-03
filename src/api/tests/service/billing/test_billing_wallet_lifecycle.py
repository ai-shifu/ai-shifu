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
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingOrder,
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
    rebuild_credit_wallet_snapshots,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM
from flaskr.service.metering.models import BillUsageRecord


pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


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
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="order-topup-expire-1",
                priority=20,
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


def test_expire_credit_wallet_buckets_skips_credit_pack_bucket(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-topup-skip",
            creator_bid="creator-expire-topup-skip",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("2.5000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-topup-skip",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid="order-expire-topup-skip",
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
        )
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-topup-skip"
        ).one()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-topup-skip"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid,
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

        assert payload["status"] == "noop"
        assert payload["bucket_count"] == 0
        assert payload["expired_credits"] == 0
        assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
        assert bucket.available_credits == Decimal("2.5000000000")
        assert bucket.expired_credits == Decimal("0")
        assert wallet.available_credits == Decimal("0E-10")
        first_wallet_version = wallet.version
        assert ledgers == []

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid="creator-expire-topup-skip",
            expire_before=datetime(2026, 4, 9, 0, 0, 0),
        )

        dao.db.session.expire_all()
        wallet = CreditWallet.query.filter_by(
            creator_bid="creator-expire-topup-skip"
        ).one()

    assert payload["status"] == "noop"
    assert wallet.available_credits == Decimal("0E-10")
    assert wallet.version == first_wallet_version


def test_expire_credit_wallet_buckets_uses_actual_mutation_time_for_bucket_update(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    cutoff = datetime(2026, 4, 8, 0, 0, 0)
    mutation_at = datetime(2026, 4, 9, 12, 30, 0)
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-mutation-time",
            creator_bid="creator-expire-mutation-time",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-mutation-time",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-mutation-time",
            priority=20,
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
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()
        monkeypatch.setattr(wallets_mod, "now_utc", lambda: mutation_at)

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=cutoff,
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-mutation-time"
        ).one()

    assert payload["bucket_count"] == 1
    assert bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert bucket.updated_at == mutation_at
    assert bucket.updated_at != cutoff


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
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid=source,
                    priority=20,
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
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
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
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-reused-legacy-second-cycle",
            priority=20,
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
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
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
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-topup-realigned",
            priority=20,
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


def test_expire_credit_wallet_buckets_skips_bucket_consumed_before_write(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-consumed-before-write",
            creator_bid="creator-expire-consumed-before-write",
            available_credits=Decimal("6.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("6.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        skipped_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-consumed-before-write",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-consumed-before-write",
            priority=20,
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
            wallet_bucket_bid="bucket-expire-consumed-before-write-ok",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-consumed-before-write-ok",
            priority=20,
            original_credits=Decimal("2.0000000000"),
            available_credits=Decimal("2.0000000000"),
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

        real_expire = wallets_mod._expire_bucket_available_credits_if_unchanged
        changed = {"done": False}

        def _consume_before_expire(target_bucket, **kwargs):
            if (
                not changed["done"]
                and target_bucket.wallet_bucket_bid
                == "bucket-expire-consumed-before-write"
            ):
                changed["done"] = True
                CreditWalletBucket.query.filter(
                    CreditWalletBucket.id == target_bucket.id
                ).update(
                    {
                        "available_credits": Decimal("1.0000000000"),
                        "consumed_credits": Decimal("3.0000000000"),
                    },
                    synchronize_session=False,
                )
                CreditWallet.query.filter(CreditWallet.id == wallet.id).update(
                    {
                        "available_credits": Decimal("3.0000000000"),
                        "lifetime_consumed_credits": Decimal("3.0000000000"),
                    },
                    synchronize_session=False,
                )
                dao.db.session.flush()
            return real_expire(target_bucket, **kwargs)

        monkeypatch.setattr(
            wallets_mod,
            "_expire_bucket_available_credits_if_unchanged",
            _consume_before_expire,
        )

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        skipped_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-consumed-before-write"
        ).one()
        ok_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-consumed-before-write-ok"
        ).one()
        skipped_ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-consumed-before-write"
        ).all()
        ok_ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-consumed-before-write-ok"
        ).all()

    assert payload["bucket_count"] == 1
    assert payload["expired_credits"] == 2
    assert skipped_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert skipped_bucket.available_credits == Decimal("1.0000000000")
    assert skipped_bucket.expired_credits == Decimal("0")
    assert skipped_ledgers == []
    assert ok_bucket.status == CREDIT_BUCKET_STATUS_EXPIRED
    assert len(ok_ledgers) == 1


def test_expire_credit_wallet_buckets_skips_bucket_extended_before_write(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    future_effective_to = datetime(2026, 4, 30, 0, 0, 0)
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-extended-before-write",
            creator_bid="creator-expire-extended-before-write",
            available_credits=Decimal("6.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("6.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        skipped_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-extended-before-write",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-extended-before-write",
            priority=20,
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
            wallet_bucket_bid="bucket-expire-extended-before-write-ok",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-extended-before-write-ok",
            priority=20,
            original_credits=Decimal("2.0000000000"),
            available_credits=Decimal("2.0000000000"),
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

        real_expire = wallets_mod._expire_bucket_available_credits_if_unchanged
        changed = {"done": False}

        def _extend_before_expire(target_bucket, **kwargs):
            if (
                not changed["done"]
                and target_bucket.wallet_bucket_bid
                == "bucket-expire-extended-before-write"
            ):
                changed["done"] = True
                CreditWalletBucket.query.filter(
                    CreditWalletBucket.id == target_bucket.id
                ).update(
                    {"effective_to": future_effective_to},
                    synchronize_session=False,
                )
                dao.db.session.flush()
            return real_expire(target_bucket, **kwargs)

        monkeypatch.setattr(
            wallets_mod,
            "_expire_bucket_available_credits_if_unchanged",
            _extend_before_expire,
        )

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        skipped_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-extended-before-write"
        ).one()
        ok_bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-extended-before-write-ok"
        ).one()
        skipped_ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-expire-extended-before-write"
        ).all()

    assert payload["bucket_count"] == 1
    assert payload["expired_credits"] == 2
    assert skipped_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert skipped_bucket.available_credits == Decimal("4.0000000000")
    assert skipped_bucket.expired_credits == Decimal("0")
    assert skipped_bucket.effective_to == future_effective_to
    assert skipped_ledgers == []
    assert ok_bucket.status == CREDIT_BUCKET_STATUS_EXPIRED


def test_expire_credit_wallet_buckets_skips_empty_bucket_released_before_status_write(
    billing_wallet_lifecycle_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing import wallets as wallets_mod

    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-empty-released-before-status",
            creator_bid="creator-expire-empty-released-before-status",
            available_credits=Decimal("0"),
            reserved_credits=Decimal("3.0000000000"),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-empty-released-before-status",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-empty-released-before-status",
            priority=20,
            original_credits=Decimal("3.0000000000"),
            available_credits=Decimal("0"),
            reserved_credits=Decimal("3.0000000000"),
            consumed_credits=Decimal("0"),
            expired_credits=Decimal("0"),
            effective_from=datetime(2026, 4, 1, 0, 0, 0),
            effective_to=datetime(2026, 4, 7, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()

        real_sync = wallets_mod._sync_empty_available_bucket_status_if_unchanged
        changed = {"done": False}

        def _release_before_status_sync(target_bucket, **kwargs):
            if not changed["done"]:
                changed["done"] = True
                CreditWalletBucket.query.filter(
                    CreditWalletBucket.id == target_bucket.id
                ).update(
                    {
                        "available_credits": Decimal("3.0000000000"),
                        "reserved_credits": Decimal("0"),
                    },
                    synchronize_session=False,
                )
                CreditWallet.query.filter(CreditWallet.id == wallet.id).update(
                    {
                        "available_credits": Decimal("3.0000000000"),
                        "reserved_credits": Decimal("0"),
                    },
                    synchronize_session=False,
                )
                dao.db.session.flush()
            return real_sync(target_bucket, **kwargs)

        monkeypatch.setattr(
            wallets_mod,
            "_sync_empty_available_bucket_status_if_unchanged",
            _release_before_status_sync,
        )

        payload = expire_credit_wallet_buckets(
            billing_wallet_lifecycle_app,
            creator_bid=wallet.creator_bid,
            expire_before=datetime(2026, 4, 8, 0, 0, 0),
        )

        dao.db.session.expire_all()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-expire-empty-released-before-status"
        ).one()
        ledgers = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid=bucket.wallet_bucket_bid
        ).all()

    assert payload["status"] == "noop"
    assert payload["bucket_count"] == 0
    assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
    assert bucket.available_credits == Decimal("3.0000000000")
    assert bucket.reserved_credits == Decimal("0")
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
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-refresh-skip",
            priority=20,
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
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-refresh-ok",
            priority=20,
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
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-refresh-error",
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
        ok_bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-expire-refresh-error-ok",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            source_bid="order-expire-refresh-error-ok",
            priority=20,
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
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid=f"order-{bid}",
                    priority=20,
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
        expire_entries = CreditLedgerEntry.query.filter_by(
            wallet_bucket_bid="bucket-consistency-topup",
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
        ).all()

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

        assert expire_payload["status"] == "noop"
        assert expire_payload["bucket_count"] == 0
        assert expire_payload["expired_credits"] == 0
        assert expire_entries == []

        assert wallet.available_credits == Decimal("2.0000000000")
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
        assert buckets["bucket-consistency-topup"].available_credits == Decimal(
            "2.0000000000"
        )
        assert buckets["bucket-consistency-topup"].expired_credits == Decimal("0")
        assert buckets["bucket-consistency-topup"].status == CREDIT_BUCKET_STATUS_ACTIVE

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
        assert bucket_expired_total == Decimal("0")
        assert ledger_reduction_total == Decimal("2.5000000000")
        for bucket in buckets.values():
            assert bucket.original_credits == (
                bucket.available_credits
                + bucket.consumed_credits
                + bucket.expired_credits
            )
