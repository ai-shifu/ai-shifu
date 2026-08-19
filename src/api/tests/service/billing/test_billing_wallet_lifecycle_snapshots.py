from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.wallets import (
    rebuild_credit_wallet_snapshots,
)

pytest_plugins = ["tests.service.billing.wallet_lifecycle_app_fixture"]


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
            lifetime_consumed_credits=Decimal(0),
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
                    expired_credits=Decimal(0),
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
                    expired_credits=Decimal(0),
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
            lifetime_consumed_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal("15.2200000000"),
                    expired_credits=Decimal(0),
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
            lifetime_consumed_credits=Decimal(0),
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
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("1.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
                reserved_credits=Decimal(0),
                consumed_credits=Decimal(0),
                expired_credits=Decimal(0),
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("5.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
