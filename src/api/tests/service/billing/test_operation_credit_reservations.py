from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_METRIC_TTS_REQUEST_COUNT,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_HOLD,
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditUsageRate,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_TYPE_TTS,
)


@pytest.fixture
def operation_credit_app():
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
        reserved_credits=Decimal("0"),
        lifetime_granted_credits=Decimal(amount),
        lifetime_consumed_credits=Decimal("0"),
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
        reserved_credits=Decimal("0"),
        consumed_credits=Decimal("0"),
        expired_credits=Decimal("0"),
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

    assert result.consumed_credits == Decimal("0")


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

    with pytest.raises(AppException) as exc_info:
        reserve_operation_credits(
            operation_credit_app,
            creator_bid="creator-insufficient",
            amount=Decimal("2.0000000000"),
            operation_type="voice_clone",
            operation_bid="voice-bid-insufficient",
            metadata={},
        )

    assert exc_info.value.code == ERROR_CODE["server.billing.creditInsufficient"]


def test_operation_credit_mutations_request_wallet_and_bucket_locks(
    operation_credit_app: Flask,
    monkeypatch,
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
        return real_load_wallet(creator_bid)

    def spy_load_active_buckets(wallet, operation_at, *, lock: bool = False):
        active_bucket_lock_calls.append(lock)
        return real_load_active_buckets(wallet, operation_at)

    def spy_iter_hold_buckets(hold, *, lock: bool = False):
        hold_bucket_lock_calls.append(lock)
        return real_iter_hold_buckets(hold)

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
