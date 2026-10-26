"""Verify cancellation credit finalization, request replay, and queue failures."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_HOLD,
    CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.models import (
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import account_cancellation as cancellation
from flaskr.service.user.models import UserAccountCancellation
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity
from flaskr.util.datetime import now_utc


@pytest.fixture
def account(app: object) -> Iterator[SimpleNamespace]:
    with app.app_context():
        context = SimpleNamespace(
            user_bid=uuid.uuid4().hex,
            cancellation_bid=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
        )
        create_user_entity(
            user_bid=context.user_bid, identify=f"{context.user_bid}@example.com"
        )
        db.session.commit()
        yield context
        db.session.rollback()
        for model in (CreditLedgerEntry, CreditWalletBucket, CreditWallet):
            model.query.filter_by(creator_bid=context.user_bid).delete()
        UserAccountCancellation.query.filter_by(user_bid=context.user_bid).delete()
        UserEntity.query.filter_by(user_bid=context.user_bid).delete()
        db.session.commit()


def _request_row(
    account: SimpleNamespace, *, status: str = "pending"
) -> UserAccountCancellation:
    row = UserAccountCancellation(
        cancellation_bid=account.cancellation_bid,
        user_bid=account.user_bid,
        idempotency_key=account.idempotency_key,
        operator_user_bid="operator",
        reason="Requested by account owner",
        status=status,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _params(app: object, account: SimpleNamespace) -> dict:
    preview = cancellation.get_account_cancellation_preview(
        app, user_bid=account.user_bid, operator_user_bid="operator"
    )
    return {
        "user_bid": account.user_bid,
        "operator_user_bid": "operator",
        "cancellation_bid": account.cancellation_bid,
        "idempotency_key": account.idempotency_key,
        "reason": "Requested by account owner",
        "preview_version": preview["preview_version"],
    }


@pytest.mark.parametrize(
    "operation",
    [cancellation.cancel_user_account, cancellation.request_user_account_cancellation],
)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_bid", " "),
        ("operator_user_bid", ""),
        ("cancellation_bid", ""),
        ("idempotency_key", " "),
        ("reason", "tiny"),
        ("reason", "x" * 501),
    ],
)
def test_cancellation_rejects_invalid_fields_before_mutation(
    app: object, operation: object, field: str, value: str
) -> None:
    params = {
        "user_bid": "account",
        "operator_user_bid": "operator",
        "cancellation_bid": "request",
        "idempotency_key": "key",
        "reason": "Valid cancellation reason",
        "preview_version": "preview",
    }
    params[field] = value
    with app.app_context(), pytest.raises(AppError) as error:
        operation(app, **params)
    assert error.value.code == ERROR_CODE["server.common.paramsError"]
    assert field in error.value.message


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("x", "x***"),
        ("@example.com", "***@example.com"),
        ("13800138000", "138****8000"),
    ],
)
def test_preview_masks_short_and_phone_identifiers(
    value: object, expected: str
) -> None:
    assert cancellation._mask_identifier(value) == expected


def test_missing_cancellation_status_and_worker_request_have_domain_errors(
    app: object,
) -> None:
    with app.app_context(), pytest.raises(AppError) as status_error:
        cancellation.get_account_cancellation_status(
            app, user_bid="missing", cancellation_bid="missing"
        )
    assert (
        status_error.value.code == ERROR_CODE["server.user.accountCancellationNotFound"]
    )
    with app.app_context(), pytest.raises(AppError) as worker_error:
        cancellation.execute_pending_account_cancellation(
            app, cancellation_bid="missing"
        )
    assert worker_error.value.code == ERROR_CODE["server.user.userNotFound"]


@pytest.mark.parametrize(
    "operation",
    [cancellation.cancel_user_account, cancellation.request_user_account_cancellation],
)
def test_idempotency_key_cannot_cancel_another_account(
    app: object, account: SimpleNamespace, operation: object
) -> None:
    _request_row(account)
    params = _params(app, account)
    params["user_bid"] = "another-account"
    with pytest.raises(AppError) as error:
        operation(app, **params)
    assert error.value.code == ERROR_CODE["server.user.accountCancellationConflict"]
    assert UserEntity.query.filter_by(user_bid=account.user_bid).one().deleted == 0


def test_failed_request_reuses_audit_identity_when_resubmitted(
    app: object, account: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _request_row(account, status="failed")
    row.failure_code = "enqueue_failed"
    db.session.commit()
    enqueue = Mock()
    monkeypatch.setattr(cancellation, "enqueue_account_cancellation", enqueue)
    params = _params(app, account)
    params.update(
        cancellation_bid="replacement-request", idempotency_key="replacement-key"
    )
    result = cancellation.request_user_account_cancellation(app, **params)
    assert result["cancellation_bid"] == account.cancellation_bid
    assert result["status"] == "pending"
    assert result["failure_code"] == ""
    assert row.idempotency_key == account.idempotency_key
    enqueue.assert_called_once_with(app, cancellation_bid=account.cancellation_bid)


@pytest.mark.parametrize("missing_registration", [False, True])
def test_queue_failure_is_durable_and_preserves_original_error(
    app: object,
    account: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    missing_registration: bool,
) -> None:
    from flaskr.common import celery_app

    row = _request_row(account)
    task = Mock()
    task.apply_async.side_effect = RuntimeError("broker unavailable")
    registry = SimpleNamespace(
        tasks={}
        if missing_registration
        else {cancellation.ACCOUNT_CANCELLATION_TASK_NAME: task}
    )
    monkeypatch.setattr(celery_app, "get_celery_app", Mock(return_value=registry))
    expected = (
        cancellation.AccountCancellationTaskRegistrationError
        if missing_registration
        else RuntimeError
    )
    with pytest.raises(expected):
        cancellation.enqueue_account_cancellation(
            app, cancellation_bid=f" {account.cancellation_bid} "
        )
    db.session.expire_all()
    assert row.status == "failed"
    assert row.failure_code == "enqueue_failed"
    assert UserEntity.query.filter_by(user_bid=account.user_bid).one().deleted == 0


def test_queue_dispatch_carries_only_the_cancellation_identifier(
    app: object, account: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.common import celery_app

    task = Mock()
    monkeypatch.setattr(
        celery_app,
        "get_celery_app",
        Mock(
            return_value=SimpleNamespace(
                tasks={cancellation.ACCOUNT_CANCELLATION_TASK_NAME: task}
            )
        ),
    )
    cancellation.enqueue_account_cancellation(
        app, cancellation_bid=f" {account.cancellation_bid} "
    )
    task.apply_async.assert_called_once_with(args=[account.cancellation_bid])


@pytest.mark.parametrize("status", ["pending", "failed", "completed"])
def test_retry_and_failure_updates_do_not_overwrite_completed_cancellations(
    app: object, account: SimpleNamespace, status: str
) -> None:
    row = _request_row(account, status=status)
    row.failure_code = "original"
    db.session.commit()
    cancellation.mark_account_cancellation_retrying(
        app, cancellation_bid=account.cancellation_bid
    )
    assert row.status == ("completed" if status == "completed" else "retrying")
    assert row.failure_code == ("original" if status == "completed" else "")
    cancellation.mark_account_cancellation_failed(
        app, cancellation_bid=account.cancellation_bid, failure_code=""
    )
    assert row.status == ("completed" if status == "completed" else "failed")
    assert row.failure_code == (
        "original" if status == "completed" else "execution_failed"
    )
    cancellation.mark_account_cancellation_retrying(app, cancellation_bid="missing")
    cancellation.mark_account_cancellation_failed(
        app, cancellation_bid="missing", failure_code="error"
    )


def test_completed_worker_is_idempotent_without_deidentifying_twice(
    app: object, account: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _request_row(account, status="completed")
    execute = Mock()
    monkeypatch.setattr(cancellation, "cancel_user_account", execute)
    result = cancellation.execute_pending_account_cancellation(
        app, cancellation_bid=account.cancellation_bid
    )
    assert result["status"] == "completed"
    execute.assert_not_called()


def test_account_cancellation_forfeits_credit_holds_and_available_balance_once(
    app: object, account: SimpleNamespace
) -> None:
    wallet = CreditWallet(
        wallet_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        available_credits=Decimal(12),
        reserved_credits=Decimal(5),
        lifetime_granted_credits=Decimal(17),
    )
    bucket = CreditWalletBucket(
        wallet_bucket_bid=uuid.uuid4().hex,
        wallet_bid=wallet.wallet_bid,
        creator_bid=account.user_bid,
        bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        priority=1,
        original_credits=Decimal(17),
        available_credits=Decimal(12),
        reserved_credits=Decimal(5),
        effective_from=now_utc() - timedelta(days=1),
    )
    hold = CreditLedgerEntry(
        ledger_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        wallet_bid=wallet.wallet_bid,
        wallet_bucket_bid=bucket.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        idempotency_key="held",
        amount=Decimal(5),
        balance_after=Decimal(12),
        metadata_json=None,
    )
    db.session.add_all([wallet, bucket, hold])
    db.session.commit()
    params = _params(app, account)
    result = cancellation.cancel_user_account(app, **params)
    assert result["status"] == "completed"
    db.session.expire_all()
    assert wallet.available_credits == 0
    assert wallet.reserved_credits == 0
    assert wallet.lifetime_consumed_credits == 5
    assert bucket.available_credits == 0
    assert bucket.reserved_credits == 0
    assert bucket.consumed_credits == 17
    entries = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.creator_bid == account.user_bid,
        CreditLedgerEntry.entry_type.in_(
            [CREDIT_LEDGER_ENTRY_TYPE_CONSUME, CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT]
        ),
    ).all()
    assert {(entry.entry_type, entry.amount) for entry in entries} == {
        (CREDIT_LEDGER_ENTRY_TYPE_CONSUME, Decimal(-5)),
        (CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT, Decimal(-12)),
    }
    repeated = cancellation.cancel_user_account(app, **params)
    assert repeated["status"] == "completed"
    assert CreditLedgerEntry.query.filter_by(creator_bid=account.user_bid).count() == 3
    with pytest.raises(AppError) as error:
        cancellation.get_account_cancellation_preview(
            app, user_bid=account.user_bid, operator_user_bid="operator"
        )
    assert error.value.code == ERROR_CODE["server.user.accountAlreadyCancelled"]


def test_reservation_finalization_ignores_terminal_holds_and_invalid_breakdowns(
    app: object, account: SimpleNamespace
) -> None:
    wallet = CreditWallet(
        wallet_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        available_credits=0,
        reserved_credits=5,
    )
    open_hold = CreditLedgerEntry(
        ledger_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        wallet_bid=wallet.wallet_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        idempotency_key="open",
        amount=5,
        metadata_json={
            "bucket_breakdown": [None, {"wallet_bucket_bid": "missing", "amount": 5}]
        },
    )
    released = CreditLedgerEntry(
        ledger_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        wallet_bid=wallet.wallet_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_HOLD,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        idempotency_key="released-hold",
        amount=9,
    )
    terminal = CreditLedgerEntry(
        ledger_bid=uuid.uuid4().hex,
        creator_bid=account.user_bid,
        wallet_bid=wallet.wallet_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_RELEASE,
        source_type=CREDIT_SOURCE_TYPE_MANUAL,
        idempotency_key=f"operation_reservation:{released.ledger_bid}:release",
        amount=9,
    )
    db.session.add_all([wallet, open_hold, released, terminal])
    db.session.flush()
    assert (
        cancellation._forfeit_open_credit_reservations(
            app,
            wallet=wallet,
            user_bid=account.user_bid,
            cancellation_bid=account.cancellation_bid,
            operator_user_bid="operator",
        )
        == 5
    )
    db.session.flush()
    assert wallet.reserved_credits == 0
    assert wallet.lifetime_consumed_credits == 5
    assert (
        CreditLedgerEntry.query.filter_by(
            creator_bid=account.user_bid, entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME
        ).count()
        == 1
    )
    assert (
        cancellation._forfeit_open_credit_reservations(
            app,
            wallet=wallet,
            user_bid=account.user_bid,
            cancellation_bid=account.cancellation_bid,
            operator_user_bid="operator",
        )
        == 0
    )
