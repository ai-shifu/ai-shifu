"""Verify billing wallet lifecycle expiration behavior."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr import dao
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_EXPIRE,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    _build_expire_ledger_idempotency_key,
    expire_credit_wallet_buckets,
)
from sqlalchemy.orm import attributes
from sqlalchemy.orm.exc import ObjectDeletedError

if TYPE_CHECKING:
    import pytest
    from flask import Flask

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


def test_expire_credit_wallet_buckets_marks_bucket_expired_and_writes_ledger(
    billing_wallet_lifecycle_app: Flask,
) -> None:
    with billing_wallet_lifecycle_app.app_context():
        wallet = CreditWallet(
            wallet_bid="wallet-expire-1",
            creator_bid="creator-expire-1",
            available_credits=Decimal("2.5000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
                reserved_credits=Decimal(0),
                consumed_credits=Decimal(0),
                expired_credits=Decimal(0),
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
        assert bucket.available_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("2.5000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
        assert bucket.expired_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("10.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
        assert ok_bucket.available_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
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
                    balance_after=Decimal(0),
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
    assert bucket.available_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("4.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
        assert refreshed_bucket.expired_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("6.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
    assert skipped_bucket.expired_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("6.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
    assert skipped_bucket.expired_credits == Decimal(0)
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
            available_credits=Decimal(0),
            reserved_credits=Decimal("3.0000000000"),
            lifetime_granted_credits=Decimal("3.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            available_credits=Decimal(0),
            reserved_credits=Decimal("3.0000000000"),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
                        "reserved_credits": Decimal(0),
                    },
                    synchronize_session=False,
                )
                CreditWallet.query.filter(CreditWallet.id == wallet.id).update(
                    {
                        "available_credits": Decimal("3.0000000000"),
                        "reserved_credits": Decimal(0),
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
    assert bucket.reserved_credits == Decimal(0)
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("9.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("8.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
