"""Verify clone retirement reconciles job state and reserved credits atomically."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.operation_credits import (
    capture_reserved_operation_credits,
    release_reserved_operation_credits,
    reserve_operation_credits,
)
from flaskr.service.tts import clone_job_retirement
from flaskr.service.tts.models import TTSMiniMaxClonedVoice
from flaskr.service.user.models import UserInfo

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def retirement_app() -> Iterator[Flask]:
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
        dao.db.session.add_all(
            [
                UserInfo(user_bid="retirement-owner", is_creator=1),
                CreditWallet(
                    wallet_bid="retirement-wallet",
                    creator_bid="retirement-owner",
                    available_credits=Decimal(10),
                    reserved_credits=Decimal(0),
                    lifetime_granted_credits=Decimal(10),
                    lifetime_consumed_credits=Decimal(0),
                    last_settled_usage_id=0,
                    version=0,
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="retirement-bucket",
                    wallet_bid="retirement-wallet",
                    creator_bid="retirement-owner",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=0,
                    source_bid="retirement-source",
                    priority=10,
                    original_credits=Decimal(10),
                    available_credits=Decimal(10),
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
                    effective_from=datetime(2026, 1, 1),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_job(
    app: Flask,
    voice_bid: str = "retirement-job",
    *,
    status: str = "queued",
    provider: str = "minimax",
    deleted: int = 0,
    reservation_bid: str | None = None,
    billing_status: str = "reserved",
) -> str:
    if reservation_bid is None:
        reservation = reserve_operation_credits(
            app,
            creator_bid="retirement-owner",
            amount=Decimal(2),
            operation_type="voice_clone",
            operation_bid=voice_bid,
            metadata={},
        )
        reservation_bid = reservation.reservation_bid
    with app.app_context():
        dao.db.session.add(
            TTSMiniMaxClonedVoice(
                voice_bid=voice_bid,
                owner_user_bid="retirement-owner",
                provider=provider,
                voice_id="AiShifu_xxxxxxxxxx",
                display_name="External voice",
                status=status,
                status_msg="Previous status",
                failure_reason="previous_reason",
                billing_status=billing_status,
                billing_reservation_bid=reservation_bid,
                deleted=deleted,
            )
        )
        dao.db.session.commit()
    return reservation_bid


def _snapshot(app: Flask, voice_bid: str = "retirement-job") -> dict[str, object]:
    with app.app_context():
        row = TTSMiniMaxClonedVoice.query.filter_by(voice_bid=voice_bid).one()
        return {
            "status": row.status,
            "status_msg": row.status_msg,
            "failure_reason": row.failure_reason,
            "billing_status": row.billing_status,
            "updated_at": row.updated_at,
            **_financial_snapshot(),
        }


def _financial_snapshot() -> dict[str, object]:
    wallet = CreditWallet.query.filter_by(wallet_bid="retirement-wallet").one()
    bucket = CreditWalletBucket.query.filter_by(
        wallet_bucket_bid="retirement-bucket"
    ).one()
    return {
        "available": wallet.available_credits,
        "reserved": wallet.reserved_credits,
        "consumed": wallet.lifetime_consumed_credits,
        "bucket_available": bucket.available_credits,
        "bucket_reserved": bucket.reserved_credits,
        "bucket_consumed": bucket.consumed_credits,
        "ledger_count": CreditLedgerEntry.query.count(),
        "release_count": CreditLedgerEntry.query.filter_by(
            entry_type=CREDIT_LEDGER_ENTRY_TYPE_RELEASE
        ).count(),
    }


@pytest.mark.parametrize(
    ("status", "deleted", "billing_status"),
    [
        ("queued", 0, "reserved"),
        ("processing", 0, "reserved"),
        ("billing_pending", 0, "reserved"),
        ("queued", 1, "reserved"),
        ("failed", 0, "reserved"),
        ("failed", 1, "failed"),
    ],
)
def test_retirement_releases_unfinished_and_deleted_jobs(
    retirement_app: Flask, status: str, deleted: int, billing_status: str
) -> None:
    _seed_job(
        retirement_app, status=status, deleted=deleted, billing_status=billing_status
    )

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["dry_run"] is False
    assert result["jobs"] == [{"voice_bid": "retirement-job", "status": "cancelled"}]
    assert result["cancelled_count"] == 1
    assert result["captured_count"] == 0
    assert result["manual_review_count"] == 0
    state = _snapshot(retirement_app)
    assert state["status"] == "failed"
    assert state["failure_reason"] == "workflow_retired"
    assert state["billing_status"] == "released"
    assert state["available"] == state["bucket_available"] == Decimal(10)
    assert state["reserved"] == state["bucket_reserved"] == Decimal(0)
    assert state["release_count"] == 1

    repeated = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )
    assert repeated["jobs"] == []
    assert repeated["cancelled_count"] == 0
    assert _snapshot(retirement_app) == state


@pytest.mark.parametrize(
    ("provider", "status"), [("minimax", "ready"), ("volcengine", "processing")]
)
def test_retirement_preserves_ready_and_other_provider_jobs(
    retirement_app: Flask, provider: str, status: str
) -> None:
    _seed_job(
        retirement_app,
        provider=provider,
        status=status,
        reservation_bid="",
        billing_status="not_required",
    )
    before = _snapshot(retirement_app)

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["jobs"] == []
    assert _snapshot(retirement_app) == before


def test_retirement_dry_run_uses_release_without_persisting_changes(
    retirement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    reservation_bid = _seed_job(retirement_app)
    before = _snapshot(retirement_app)
    released: list[str] = []
    real_release = clone_job_retirement.release_reserved_operation_credits

    def spy_release(app: Flask, *, reservation_bid: str, reason: str) -> object:
        released.append(reservation_bid)
        return real_release(app, reservation_bid=reservation_bid, reason=reason)

    monkeypatch.setattr(
        clone_job_retirement, "release_reserved_operation_credits", spy_release
    )

    result = clone_job_retirement.retire_minimax_clone_jobs(retirement_app)

    assert result["dry_run"] is True
    assert result["jobs"] == [{"voice_bid": "retirement-job", "status": "would_cancel"}]
    assert result["cancelled_count"] == 0
    assert result["manual_review_count"] == 0
    assert released == [reservation_bid]
    assert _snapshot(retirement_app) == before


@pytest.mark.parametrize("apply", [False, True])
def test_retirement_preserves_captured_job_and_does_not_refund_consumption(
    retirement_app: Flask, apply: bool
) -> None:
    reservation_bid = _seed_job(retirement_app, status="billing_pending")
    capture_reserved_operation_credits(
        retirement_app,
        reservation_bid=reservation_bid,
        usage_bid="retirement-usage",
        metadata={},
    )
    before = _snapshot(retirement_app)

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=apply, workers_stopped=apply
    )

    assert result["jobs"] == [
        {"voice_bid": "retirement-job", "status": "already_captured"}
    ]
    assert result["captured_count"] == 1
    assert result["cancelled_count"] == 0
    assert _snapshot(retirement_app) == before
    assert before["consumed"] == before["bucket_consumed"] == Decimal(2)
    assert before["release_count"] == 0


def test_retirement_accepts_a_previously_released_hold(retirement_app: Flask) -> None:
    reservation_bid = _seed_job(retirement_app)
    release_reserved_operation_credits(
        retirement_app, reservation_bid=reservation_bid, reason="provider_failed"
    )

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["cancelled_count"] == 1
    state = _snapshot(retirement_app)
    assert state["billing_status"] == "released"
    assert state["release_count"] == 1
    assert state["available"] == state["bucket_available"] == Decimal(10)


@pytest.mark.parametrize("apply", [False, True])
def test_retirement_reports_missing_hold_for_manual_review(
    retirement_app: Flask, apply: bool
) -> None:
    _seed_job(retirement_app, reservation_bid="missing-reservation")
    before = _snapshot(retirement_app)

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=apply, workers_stopped=apply
    )

    assert result["manual_review_count"] == 1
    assert result["cancelled_count"] == 0
    assert result["jobs"] == [
        {
            "voice_bid": "retirement-job",
            "status": "manual_review",
            "error_type": "AppError",
        }
    ]
    assert _snapshot(retirement_app) == before


def test_retirement_releases_no_credits_for_unbilled_jobs(
    retirement_app: Flask,
) -> None:
    _seed_job(retirement_app, reservation_bid="", billing_status="not_required")

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["cancelled_count"] == 1
    state = _snapshot(retirement_app)
    assert state["status"] == "failed"
    assert state["billing_status"] == "not_required"
    assert state["available"] == state["bucket_available"] == Decimal(10)
    assert state["ledger_count"] == 0


def test_retirement_rolls_back_credit_release_and_continues_after_job_failure(
    retirement_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_reservation = _seed_job(retirement_app, "failed-retirement-job")
    _seed_job(retirement_app, "successful-retirement-job")
    before = _snapshot(retirement_app, "failed-retirement-job")
    real_release = clone_job_retirement.release_reserved_operation_credits

    def release_then_fail(app: Flask, *, reservation_bid: str, reason: str) -> object:
        release = real_release(app, reservation_bid=reservation_bid, reason=reason)
        if reservation_bid == failed_reservation:
            raise RuntimeError
        return release

    monkeypatch.setattr(
        clone_job_retirement, "release_reserved_operation_credits", release_then_fail
    )

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["manual_review_count"] == result["cancelled_count"] == 1
    assert result["jobs"] == [
        {
            "voice_bid": "failed-retirement-job",
            "status": "manual_review",
            "error_type": "RuntimeError",
        },
        {"voice_bid": "successful-retirement-job", "status": "cancelled"},
    ]
    failed_state = _snapshot(retirement_app, "failed-retirement-job")
    for field in (
        "status",
        "status_msg",
        "failure_reason",
        "billing_status",
        "updated_at",
    ):
        assert failed_state[field] == before[field]
    assert failed_state["available"] == failed_state["bucket_available"] == Decimal(8)
    assert failed_state["reserved"] == failed_state["bucket_reserved"] == Decimal(2)
    assert failed_state["release_count"] == 1
    assert _snapshot(retirement_app, "successful-retirement-job")["status"] == "failed"


def test_retirement_requires_acknowledging_stopped_workers(
    retirement_app: Flask,
) -> None:
    _seed_job(retirement_app)
    before = _snapshot(retirement_app)

    with pytest.raises(ValueError, match="Stop all old API instances"):
        clone_job_retirement.retire_minimax_clone_jobs(retirement_app, apply=True)

    assert _snapshot(retirement_app) == before


@pytest.mark.parametrize("apply", [False, True])
def test_retirement_rejects_callers_unit_of_work(
    retirement_app: Flask, apply: bool
) -> None:
    with (
        retirement_app.app_context(),
        unit_of_work(),
        pytest.raises(RuntimeError, match="owns its own transaction"),
    ):
        clone_job_retirement.retire_minimax_clone_jobs(
            retirement_app, apply=apply, workers_stopped=apply
        )


def test_retirement_releases_orphan_holds_and_preserves_other_operations(
    retirement_app: Flask,
) -> None:
    orphan = reserve_operation_credits(
        retirement_app,
        creator_bid="retirement-owner",
        amount=Decimal(2),
        operation_type="voice_clone",
        operation_bid="orphan-clone",
        metadata={},
    )
    reserve_operation_credits(
        retirement_app,
        creator_bid="retirement-owner",
        amount=Decimal(1),
        operation_type="other_operation",
        operation_bid="unrelated-operation",
        metadata={},
    )
    with retirement_app.app_context():
        before = _financial_snapshot()

    preview = clone_job_retirement.retire_minimax_clone_jobs(retirement_app)

    assert preview["jobs"] == [
        {
            "reservation_bid": orphan.reservation_bid,
            "status": "would_release_orphan",
        }
    ]
    assert preview["released_orphan_count"] == 0
    assert preview["manual_review_count"] == 0
    with retirement_app.app_context():
        assert _financial_snapshot() == before

    applied = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert applied["jobs"] == [
        {"reservation_bid": orphan.reservation_bid, "status": "released_orphan"}
    ]
    assert applied["released_orphan_count"] == 1
    with retirement_app.app_context():
        after = _financial_snapshot()
        assert after["available"] == after["bucket_available"] == Decimal(9)
        assert after["reserved"] == after["bucket_reserved"] == Decimal(1)
        assert after["release_count"] == 1

    repeated = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert repeated["jobs"] == []
    assert repeated["released_orphan_count"] == 0
    with retirement_app.app_context():
        assert _financial_snapshot() == after


@pytest.mark.parametrize("apply", [False, True])
def test_retirement_reports_ready_voice_with_unsettled_hold_without_refund(
    retirement_app: Flask, apply: bool
) -> None:
    reservation_bid = _seed_job(retirement_app, status="ready")
    before = _snapshot(retirement_app)

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=apply, workers_stopped=apply
    )

    assert result["jobs"] == [
        {"reservation_bid": reservation_bid, "status": "manual_review"}
    ]
    assert result["manual_review_count"] == 1
    assert result["cancelled_count"] == result["released_orphan_count"] == 0
    assert _snapshot(retirement_app) == before


def test_retirement_preserves_ready_voice_with_captured_hold(
    retirement_app: Flask,
) -> None:
    reservation_bid = _seed_job(
        retirement_app, status="ready", billing_status="charged"
    )
    capture_reserved_operation_credits(
        retirement_app,
        reservation_bid=reservation_bid,
        usage_bid="ready-retirement-usage",
        metadata={},
    )
    before = _snapshot(retirement_app)

    result = clone_job_retirement.retire_minimax_clone_jobs(
        retirement_app, apply=True, workers_stopped=True
    )

    assert result["jobs"] == []
    assert result["manual_review_count"] == result["cancelled_count"] == 0
    assert _snapshot(retirement_app) == before
