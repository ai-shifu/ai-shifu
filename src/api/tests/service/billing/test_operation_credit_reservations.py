"""Verify operation credit reservations behavior."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_TTS_REQUEST_COUNT,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_HOLD,
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingSubscription,
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_TYPE_TTS,
)


@pytest.fixture
def operation_credit_app() -> object:
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


def _seed_wallet(creator_bid: str, amount: str = "10.0000000000") -> None:
    wallet = CreditWallet(
        wallet_bid=f"wallet-{creator_bid}",
        creator_bid=creator_bid,
        available_credits=Decimal(amount),
        reserved_credits=Decimal(0),
        lifetime_granted_credits=Decimal(amount),
        lifetime_consumed_credits=Decimal(0),
        last_settled_usage_id=0,
        version=0,
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=f"bucket-{creator_bid}",
        wallet_bid=wallet.wallet_bid,
        creator_bid=creator_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
        source_type=0,
        source_bid=f"source-{creator_bid}",
        priority=10,
        original_credits=Decimal(amount),
        available_credits=Decimal(amount),
        reserved_credits=Decimal(0),
        consumed_credits=Decimal(0),
        expired_credits=Decimal(0),
        effective_from=datetime(2026, 1, 1, 0, 0, 0),
        effective_to=None,
        status=CREDIT_BUCKET_STATUS_ACTIVE,
        metadata_json={},
    )
    dao.db.session.add_all([wallet, bucket])


def _seed_voice_clone_rate(credits_per_unit: str = "3.0000000000") -> None:
    dao.db.session.add(
        CreditUsageRate(
            rate_bid="rate-minimax-voice-clone-preview",
            usage_type=BILL_USAGE_TYPE_TTS,
            provider="minimax",
            model="voice_clone",
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
            billing_metric=BILLING_METRIC_TTS_REQUEST_COUNT,
            unit_size=1,
            credits_per_unit=Decimal(credits_per_unit),
            rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            effective_to=None,
            status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
        )
    )


def test_estimate_voice_clone_cost_uses_configured_rate(
    operation_credit_app: Flask,
) -> None:
    from flaskr.service.billing.operation_credits import (
        estimate_voice_clone_operation_credits,
    )

    with operation_credit_app.app_context():
        _seed_voice_clone_rate("2.5000000000")
        dao.db.session.commit()

    result = estimate_voice_clone_operation_credits(operation_credit_app)

    assert result.consumed_credits == Decimal("2.5000000000")
    assert result.billing_metric == BILLING_METRIC_TTS_REQUEST_COUNT


def test_estimate_voice_clone_cost_is_zero_without_configured_rate(
    operation_credit_app: Flask,
) -> None:
    from flaskr.service.billing.operation_credits import (
        estimate_voice_clone_operation_credits,
    )

    result = estimate_voice_clone_operation_credits(operation_credit_app)

    assert result.consumed_credits == Decimal(0)


def test_reserve_capture_and_release_operation_credits_are_idempotent(
    operation_credit_app: Flask,
) -> None:
    from flaskr.service.billing.operation_credits import (
        capture_reserved_operation_credits,
        release_reserved_operation_credits,
        reserve_operation_credits,
    )

    with operation_credit_app.app_context():
        _seed_wallet("creator-operation", "10.0000000000")
        dao.db.session.commit()

    reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid="creator-operation",
        amount=Decimal("3.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-1",
        metadata={"voice_id": "AiShifu_voice_1"},
    )
    repeated_reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid="creator-operation",
        amount=Decimal("3.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-1",
        metadata={"voice_id": "AiShifu_voice_1"},
    )

    assert repeated_reservation.reservation_bid == reservation.reservation_bid
    with operation_credit_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-operation").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-creator-operation"
        ).one()
        assert wallet.available_credits == Decimal("7.0000000000")
        assert wallet.reserved_credits == Decimal("3.0000000000")
        assert bucket.available_credits == Decimal("7.0000000000")
        assert bucket.reserved_credits == Decimal("3.0000000000")
        assert (
            CreditLedgerEntry.query.filter_by(
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD
            ).count()
            == 1
        )

    capture = capture_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        usage_bid="usage-voice-clone-1",
        metadata={"status": "ready"},
    )
    repeated_capture = capture_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        usage_bid="usage-voice-clone-1",
        metadata={"status": "ready"},
    )

    assert repeated_capture.ledger_bid == capture.ledger_bid
    with operation_credit_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-operation").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-creator-operation"
        ).one()
        assert wallet.available_credits == Decimal("7.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert wallet.lifetime_consumed_credits == Decimal("3.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert bucket.consumed_credits == Decimal("3.0000000000")
        assert (
            CreditLedgerEntry.query.filter_by(
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME
            ).count()
            == 1
        )

    release = release_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        reason="already_captured",
    )

    assert release.status == "already_captured"
    with operation_credit_app.app_context():
        assert (
            CreditLedgerEntry.query.filter_by(
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_RELEASE
            ).count()
            == 0
        )


def test_release_restores_reserved_credits(operation_credit_app: Flask) -> None:
    from flaskr.service.billing.operation_credits import (
        release_reserved_operation_credits,
        reserve_operation_credits,
    )

    with operation_credit_app.app_context():
        _seed_wallet("creator-release", "5.0000000000")
        dao.db.session.commit()

    reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid="creator-release",
        amount=Decimal("2.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-release",
        metadata={},
    )
    release = release_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        reason="provider_failed",
    )
    repeated_release = release_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        reason="provider_failed",
    )

    assert release.status == "released"
    assert repeated_release.status == "already_released"
    with operation_credit_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid="creator-release").one()
        bucket = CreditWalletBucket.query.filter_by(
            wallet_bucket_bid="bucket-creator-release"
        ).one()
        assert wallet.available_credits == Decimal("5.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert bucket.available_credits == Decimal("5.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert (
            CreditLedgerEntry.query.filter_by(
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_RELEASE
            ).count()
            == 1
        )


def test_reserve_operation_credits_rejects_insufficient_balance(
    operation_credit_app: Flask,
) -> None:
    from flaskr.service.billing.operation_credits import reserve_operation_credits

    with operation_credit_app.app_context():
        _seed_wallet("creator-insufficient", "1.0000000000")
        dao.db.session.commit()

    with pytest.raises(AppError) as exc_info:
        reserve_operation_credits(
            operation_credit_app,
            creator_bid="creator-insufficient",
            amount=Decimal("2.0000000000"),
            operation_type="voice_clone",
            operation_bid="voice-bid-insufficient",
            metadata={},
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]


def test_reserve_operation_credits_freezes_topup_without_active_subscription(
    operation_credit_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing.operation_credits import reserve_operation_credits

    monkeypatch.setattr(
        "flaskr.service.billing.operation_credits.now_utc",
        lambda: datetime(2026, 1, 16, 0, 0, 0),
    )
    creator_bid = "creator-frozen-topup"
    with operation_credit_app.app_context():
        wallet = CreditWallet(
            wallet_bid=f"wallet-{creator_bid}",
            creator_bid=creator_bid,
            available_credits=Decimal("15.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("15.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid=f"bucket-{creator_bid}",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=f"topup-{creator_bid}",
            priority=30,
            original_credits=Decimal("15.0000000000"),
            available_credits=Decimal("15.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            effective_to=datetime(2099, 1, 1, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        subscription = BillingSubscription(
            subscription_bid=f"subscription-{creator_bid}",
            creator_bid=creator_bid,
            product_bid="product-plan-expired",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 1, 15, 0, 0, 0),
        )
        dao.db.session.add_all([wallet, bucket, subscription])
        dao.db.session.commit()

    with pytest.raises(AppError) as exc_info:
        reserve_operation_credits(
            operation_credit_app,
            creator_bid=creator_bid,
            amount=Decimal("1.0000000000"),
            operation_type="voice_clone",
            operation_bid="voice-bid-frozen-topup",
            metadata={},
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]
    with operation_credit_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(creator_bid=creator_bid).one()
        assert wallet.available_credits == Decimal("15.0000000000")
        assert wallet.reserved_credits == Decimal("0E-10")
        assert bucket.available_credits == Decimal("15.0000000000")
        assert bucket.reserved_credits == Decimal("0E-10")
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
            ).count()
            == 0
        )
        subscription = BillingSubscription.query.filter_by(
            subscription_bid=f"subscription-{creator_bid}"
        ).one()
        subscription.current_period_start_at = datetime(2026, 1, 1, 0, 0, 0)
        subscription.current_period_end_at = datetime(2099, 1, 1, 0, 0, 0)
        dao.db.session.commit()

    reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid=creator_bid,
        amount=Decimal("1.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-frozen-topup",
        metadata={},
    )

    assert reservation.status == "reserved"
    assert reservation.wallet_bucket_bids == [f"bucket-{creator_bid}"]
    with operation_credit_app.app_context():
        wallet = CreditWallet.query.filter_by(creator_bid=creator_bid).one()
        bucket = CreditWalletBucket.query.filter_by(creator_bid=creator_bid).one()
        assert wallet.available_credits == Decimal("14.0000000000")
        assert wallet.reserved_credits == Decimal("1.0000000000")
        assert bucket.available_credits == Decimal("14.0000000000")
        assert bucket.reserved_credits == Decimal("1.0000000000")
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
            ).count()
            == 1
        )


def test_reserve_operation_credits_rejects_topup_after_consumption_window(
    operation_credit_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.billing.operation_credits import reserve_operation_credits

    monkeypatch.setattr(
        "flaskr.service.billing.operation_credits.now_utc",
        lambda: datetime(2026, 1, 16, 0, 0, 0),
    )
    creator_bid = "creator-expired-topup-window"
    with operation_credit_app.app_context():
        wallet = CreditWallet(
            wallet_bid=f"wallet-{creator_bid}",
            creator_bid=creator_bid,
            available_credits=Decimal("15.0000000000"),
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("15.0000000000"),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid=f"bucket-{creator_bid}",
            wallet_bid=wallet.wallet_bid,
            creator_bid=creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            source_type=CREDIT_SOURCE_TYPE_TOPUP,
            source_bid=f"topup-{creator_bid}",
            priority=30,
            original_credits=Decimal("15.0000000000"),
            available_credits=Decimal("15.0000000000"),
            reserved_credits=Decimal(0),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 1, 1, 0, 0, 0),
            effective_to=datetime(2026, 1, 15, 0, 0, 0),
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        subscription = BillingSubscription(
            subscription_bid=f"subscription-{creator_bid}",
            creator_bid=creator_bid,
            product_bid="product-plan-active",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
            current_period_end_at=datetime(2099, 1, 1, 0, 0, 0),
        )
        dao.db.session.add_all([wallet, bucket, subscription])
        dao.db.session.commit()

    with pytest.raises(AppError) as exc_info:
        reserve_operation_credits(
            operation_credit_app,
            creator_bid=creator_bid,
            amount=Decimal("1.0000000000"),
            operation_type="voice_clone",
            operation_bid="voice-bid-expired-topup-window",
            metadata={},
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]
    with operation_credit_app.app_context():
        assert (
            CreditLedgerEntry.query.filter_by(
                creator_bid=creator_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
            ).count()
            == 0
        )


def test_operation_credit_mutations_request_wallet_and_bucket_locks(
    operation_credit_app: Flask,
    monkeypatch: object,
) -> None:
    from flaskr.service.billing import operation_credits
    from flaskr.service.billing.operation_credits import (
        capture_reserved_operation_credits,
        release_reserved_operation_credits,
        reserve_operation_credits,
    )

    with operation_credit_app.app_context():
        _seed_wallet("creator-locks", "10.0000000000")
        dao.db.session.commit()

    wallet_lock_calls: list[bool] = []
    active_bucket_lock_calls: list[bool] = []
    hold_bucket_lock_calls: list[bool] = []
    real_load_wallet = operation_credits._load_wallet
    real_load_active_buckets = operation_credits._load_active_buckets
    real_iter_hold_buckets = operation_credits._iter_hold_buckets

    def spy_load_wallet(creator_bid: str, *, lock: bool = False):
        wallet_lock_calls.append(lock)
        return real_load_wallet(creator_bid, lock=lock)

    def spy_load_active_buckets(
        wallet: object, operation_at: object, *, lock: bool = False
    ):
        active_bucket_lock_calls.append(lock)
        return real_load_active_buckets(wallet, operation_at, lock=lock)

    def spy_iter_hold_buckets(hold: object, *, lock: bool = False):
        hold_bucket_lock_calls.append(lock)
        return real_iter_hold_buckets(hold, lock=lock)

    monkeypatch.setattr(operation_credits, "_load_wallet", spy_load_wallet)
    monkeypatch.setattr(
        operation_credits,
        "_load_active_buckets",
        spy_load_active_buckets,
    )
    monkeypatch.setattr(operation_credits, "_iter_hold_buckets", spy_iter_hold_buckets)

    reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid="creator-locks",
        amount=Decimal("3.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-locks",
        metadata={},
    )
    capture_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=reservation.reservation_bid,
        usage_bid="usage-locks",
        metadata={},
    )

    with operation_credit_app.app_context():
        _seed_wallet("creator-locks-release", "10.0000000000")
        dao.db.session.commit()

    release_reservation = reserve_operation_credits(
        operation_credit_app,
        creator_bid="creator-locks-release",
        amount=Decimal("2.0000000000"),
        operation_type="voice_clone",
        operation_bid="voice-bid-locks-release",
        metadata={},
    )
    release_reserved_operation_credits(
        operation_credit_app,
        reservation_bid=release_reservation.reservation_bid,
        reason="test",
    )

    assert wallet_lock_calls == [True, True, True, True]
    assert active_bucket_lock_calls == [True, True]
    assert hold_bucket_lock_calls == [True, True]
