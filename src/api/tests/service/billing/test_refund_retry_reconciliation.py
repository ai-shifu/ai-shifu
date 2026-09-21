"""Exercise durable refund recovery with real orders, wallets, and transactions."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from threading import Barrier, Event, Lock, Thread, current_thread
from traceback import format_exception
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr.dao import db, uow
from flaskr.service.billing import checkout, models
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppError
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRefundResult,
)
from flaskr.util.datetime import now_utc
from sqlalchemy import event, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tests.common.fixtures.bill_products import build_bill_products
from tests.migrations.test_fresh_mysql_upgrade import (
    _create_temp_database,
    _drop_temp_database,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

ORDER_BID = "bill-refund-recovery"
CREATOR_BID = "creator-refund-recovery"


def _create_refund_app(uri: str) -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_BINDS={"ai_shifu_saas": uri, "ai_shifu_admin": uri},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False, "timeout": 10}
        }
        if uri.startswith("sqlite")
        else {},
        TZ="UTC",
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all(build_bill_products())
        db.session.add(
            BillingSubscription(
                subscription_bid="sub-refund-recovery",
                creator_bid=CREATOR_BID,
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                current_period_start_at=now_utc() - timedelta(days=1),
                current_period_end_at=now_utc() + timedelta(days=30),
                metadata_json={},
            )
        )
        db.session.add(
            BillingOrder(
                bill_order_bid=ORDER_BID,
                creator_bid=CREATOR_BID,
                product_bid="bill-product-topup-small",
                subscription_bid="",
                order_type=BILLING_ORDER_TYPE_TOPUP,
                payment_provider="stripe",
                status=BILLING_ORDER_STATUS_PAID,
                currency="USD",
                payable_amount=1000,
                paid_amount=1000,
                provider_reference_id="cs_refund_recovery",
                metadata_json={
                    "operator_note": "preserve existing audit metadata",
                    "provider_extra": {
                        "payment_intent_id": "pi_refund_recovery",
                        "charge_id": "ch_refund_recovery",
                    },
                },
            )
        )
        db.session.commit()
    return app


def _dispose_refund_app(app: Flask) -> None:
    with app.app_context():
        db.session.remove()
        db.drop_all()
        for engine in db.engines.values():
            engine.dispose()


@pytest.fixture
def refund_app(tmp_path: Path) -> Iterator[Flask]:
    app = _create_refund_app(f"sqlite:///{tmp_path / 'refund-recovery.sqlite'}")
    yield app
    _dispose_refund_app(app)


@pytest.fixture
def mysql_refund_app() -> Iterator[Flask]:
    """Use an isolated generated schema when the MySQL admin DSN is supplied."""
    base_uri = os.getenv("TEST_BILLING_REFUND_MYSQL_URI")
    if not base_uri:
        pytest.skip(
            "Set TEST_BILLING_REFUND_MYSQL_URI for real MySQL row-lock coverage."
        )
    if not make_url(base_uri).drivername.startswith("mysql"):
        pytest.fail("TEST_BILLING_REFUND_MYSQL_URI must use a MySQL driver")
    uri, database_name = _create_temp_database(base_uri)
    try:
        app = _create_refund_app(uri)
        yield app
        _dispose_refund_app(app)
    finally:
        _drop_temp_database(base_uri, database_name)


class RefundGateway:
    """Model provider idempotency independently of the local database."""

    def __init__(self) -> None:
        """Keep remote refund state outside database transactions."""
        self.requests: list[PaymentRefundRequest] = []
        self.lookups: list[PaymentRefundRequest] = []
        self.remote: dict[str, PaymentRefundResult] = {}
        self.guard = Lock()
        self.status = "succeeded"
        self.historical: PaymentRefundResult | None = None
        self.lookup_error: Exception | None = None
        self.create_error: Exception | None = None
        self.after_create: Callable[[], None] | None = None
        self.after_lookup: Callable[[], None] | None = None
        self.assert_boundary = True

    def _check_boundary(self) -> None:
        if self.assert_boundary:
            assert not uow.in_unit_of_work(), "provider HTTP inside unit_of_work"
            assert not db.session().in_transaction(), (
                "provider HTTP holds a DB transaction"
            )

    def reconcile_refund(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult | None:
        _ = app
        self._check_boundary()
        with self.guard:
            self.lookups.append(deepcopy(request))
            if self.lookup_error is not None:
                raise self.lookup_error
            result = deepcopy(
                self.historical or self.remote.get(request.metadata["idempotency_key"])
            )
        if self.after_lookup is not None:
            self.after_lookup()
        return result

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        _ = app
        self._check_boundary()
        with self.guard:
            self.requests.append(deepcopy(request))
            if self.create_error is not None:
                raise self.create_error
            key = request.metadata.get("idempotency_key")
            assert isinstance(key, str), "refund must have a durable key"
            assert key, "refund must have a durable key"
            existing = self.remote.get(key)
            if existing is None:
                existing = self.result(request, self.status)
                self.remote[key] = existing
            else:
                assert request.amount == existing.raw_response["amount"]
                assert request.reason == existing.raw_response["reason"]
        if self.after_create is not None:
            self.after_create()
        return deepcopy(existing)

    @staticmethod
    def result(request: PaymentRefundRequest, status: str) -> PaymentRefundResult:
        metadata = request.metadata
        reference = (
            f"re_{metadata.get('refund_operation_bid', 'historical').replace('-', '')}"
        )
        return PaymentRefundResult(
            reference,
            {
                "object": "refund",
                "id": reference,
                "status": status,
                "amount": request.amount,
                "currency": str(metadata["currency"]).lower(),
                "payment_intent": metadata["payment_intent_id"],
                "charge": metadata["charge_id"],
                "reason": request.reason,
                "metadata": {
                    "order_bid": request.order_bid,
                    "bill_order_bid": request.order_bid,
                    "creator_bid": metadata["creator_bid"],
                    **(
                        {"refund_operation_bid": metadata["refund_operation_bid"]}
                        if metadata.get("refund_operation_bid")
                        else {}
                    ),
                },
            },
            status,
        )


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> RefundGateway:
    provider = RefundGateway()
    monkeypatch.setattr(checkout, "get_payment_provider", lambda _provider: provider)
    return provider


def _refund(app: Flask, payload: dict[str, object] | None = None) -> object:
    return checkout.refund_billing_order(app, CREATOR_BID, ORDER_BID, payload or {})


def _operation(app: Flask) -> dict[str, object]:
    with app.app_context(), Session(db.engine) as session:
        operation = session.execute(
            select(models.BillingRefundOperation).filter_by(bill_order_bid=ORDER_BID)
        ).scalar_one()
        return {
            column.name: getattr(operation, column.key)
            for column in operation.__table__.columns
        }


def _assert_accounting(app: Flask, *, finalized: bool) -> None:
    with app.app_context(), Session(db.engine) as session:
        order = session.execute(
            select(BillingOrder).filter_by(bill_order_bid=ORDER_BID)
        ).scalar_one()
        assert order.status == (
            BILLING_ORDER_STATUS_REFUNDED if finalized else BILLING_ORDER_STATUS_PAID
        )
        assert bool(order.refunded_at) is finalized
        assert (
            order.metadata_json["operator_note"] == "preserve existing audit metadata"
        )
        entries = (
            session.execute(
                select(CreditLedgerEntry).filter_by(creator_bid=CREATOR_BID)
            )
            .scalars()
            .all()
        )
        buckets = (
            session.execute(
                select(CreditWalletBucket).filter_by(creator_bid=CREATOR_BID)
            )
            .scalars()
            .all()
        )
        wallets = (
            session.execute(select(CreditWallet).filter_by(creator_bid=CREATOR_BID))
            .scalars()
            .all()
        )
        assert len(entries) == len(buckets) == len(wallets) == int(finalized)
        if finalized:
            assert entries[0].amount == Decimal(20)
            assert buckets[0].original_credits == buckets[0].available_credits == 20
            assert wallets[0].available_credits == entries[0].balance_after == 20
            assert entries[0].wallet_bucket_bid == buckets[0].wallet_bucket_bid
            assert (
                entries[0].idempotency_key == f"refund_return:{entries[0].source_bid}"
            )


def test_provider_is_called_after_durable_prepare_without_open_transaction(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    def verify_durable_claim() -> None:
        operation = _operation(refund_app)
        assert operation["submitted_at"] is not None
        assert operation["finalized_at"] is None
        assert (
            operation["idempotency_key"]
            == gateway.requests[0].metadata["idempotency_key"]
        )

    gateway.after_create = verify_durable_claim
    result = _refund(refund_app)
    assert result.status == "refunded"
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=True)


def test_remote_success_survives_late_local_failure_and_retry_grants_once(
    refund_app: Flask, gateway: RefundGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = checkout.grant_refund_return_credits

    def grant_then_fail(*args: object, **kwargs: object) -> object:
        original(*args, **kwargs)
        db.session.flush()
        assert CreditLedgerEntry.query.filter_by(creator_bid=CREATOR_BID).count() == 1
        message = "failure after real refund credit grant"
        raise RuntimeError(message)

    monkeypatch.setattr(checkout, "grant_refund_return_credits", grant_then_fail)
    with pytest.raises(RuntimeError, match="failure after real refund credit grant"):
        _refund(refund_app, {"amount": 1000, "reason": "requested_by_customer"})
    assert len(gateway.remote) == len(gateway.requests) == 1
    _assert_accounting(refund_app, finalized=False)
    pending_operation = _operation(refund_app)
    assert pending_operation["finalized_at"] is None

    monkeypatch.setattr(checkout, "grant_refund_return_credits", original)
    result = _refund(refund_app)
    assert result.status == "refunded"
    assert len(gateway.remote) == len(gateway.requests) == 1
    operation = _operation(refund_app)
    assert operation["idempotency_key"] == pending_operation["idempotency_key"]
    assert operation["reason"] == "requested_by_customer"
    assert operation["finalized_at"] is not None
    _assert_accounting(refund_app, finalized=True)
    assert _refund(refund_app).refund_reference_id == result.refund_reference_id
    _assert_accounting(refund_app, finalized=True)


def test_prepare_commit_failure_makes_no_provider_request(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    def reject_prepare(session: Session) -> None:
        _ = session
        message = "prepare commit failed"
        raise RuntimeError(message)

    event.listen(Session, "before_commit", reject_prepare)
    try:
        with pytest.raises(RuntimeError, match="prepare commit failed"):
            _refund(refund_app)
    finally:
        event.remove(Session, "before_commit", reject_prepare)
    assert gateway.requests == gateway.lookups == []
    assert gateway.remote == {}
    _assert_accounting(refund_app, finalized=False)


def test_historical_full_refund_is_reconciled_without_creating_another_refund(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.historical = RefundGateway.result(
        PaymentRefundRequest(
            ORDER_BID,
            amount=1000,
            metadata={
                "creator_bid": CREATOR_BID,
                "currency": "usd",
                "payment_intent_id": "pi_refund_recovery",
                "charge_id": "ch_refund_recovery",
            },
        ),
        "succeeded",
    )
    result = _refund(refund_app)
    assert result.refund_reference_id == "re_historical"
    assert gateway.requests == []
    assert len(gateway.lookups) == 1
    _assert_accounting(refund_app, finalized=True)
    assert _refund(refund_app).refund_reference_id == "re_historical"
    assert gateway.requests == []
    _assert_accounting(refund_app, finalized=True)


@pytest.mark.parametrize(
    "problem",
    [
        "historical partial refund is ambiguous",
        "multiple matching refunds",
        "lookup unavailable",
    ],
)
def test_ambiguous_or_unavailable_history_never_falls_back_to_new_refund(
    problem: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.lookup_error = RuntimeError(problem)
    with pytest.raises(RuntimeError, match=problem):
        _refund(refund_app)
    assert gateway.requests == []
    assert gateway.remote == {}
    _assert_accounting(refund_app, finalized=False)


@pytest.mark.parametrize("pending_status", ["pending", "requires_action"])
def test_pending_refund_preserves_credits_until_provider_confirms_success(
    pending_status: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.status = pending_status
    result = _refund(refund_app)
    assert result.status == "pending"
    assert result.refund_reference_id
    _assert_accounting(refund_app, finalized=False)
    operation = _operation(refund_app)
    assert operation["provider_status"] == pending_status
    assert operation["finalized_at"] is None
    for response in gateway.remote.values():
        response.status = "succeeded"
        response.raw_response["status"] = "succeeded"
    completed = _refund(refund_app)
    assert completed.status == "refunded"
    assert completed.refund_reference_id == result.refund_reference_id
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=True)


@pytest.mark.parametrize("failure_status", ["failed", "canceled"])
def test_failed_provider_refund_keeps_paid_order_and_does_not_credit_wallet(
    failure_status: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.status = failure_status
    with pytest.raises(AppError):
        _refund(refund_app)
    _assert_accounting(refund_app, finalized=False)
    operation = _operation(refund_app)
    assert operation["provider_status"] == failure_status
    assert operation["provider_refund_id"]
    assert operation["finalized_at"] is None
    with pytest.raises(AppError):
        _refund(refund_app)
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=False)


@pytest.mark.parametrize("changed", [{"amount": 400}, {"reason": "duplicate"}])
def test_retry_cannot_change_the_durable_refund_parameters(
    changed: dict[str, object], refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.status = "pending"
    assert (
        _refund(refund_app, {"amount": 1000, "reason": "requested_by_customer"}).status
        == "pending"
    )
    before = _operation(refund_app)
    lookup_count = len(gateway.lookups)
    with pytest.raises(AppError):
        _refund(refund_app, changed)
    after = _operation(refund_app)
    assert after == before
    assert len(gateway.lookups) == lookup_count
    assert len(gateway.requests) == 1
    _assert_accounting(refund_app, finalized=False)


@pytest.mark.parametrize("elapsed_hours", [-1, 22, 23, 48])
def test_missing_remote_result_retries_only_inside_the_provider_key_window(
    elapsed_hours: int, refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.create_error = TimeoutError("uncertain provider transport")
    with pytest.raises(TimeoutError, match="uncertain provider transport"):
        _refund(refund_app)
    assert len(gateway.requests) == 1
    assert gateway.remote == {}
    with refund_app.app_context():
        operation = models.BillingRefundOperation.query.filter_by(
            bill_order_bid=ORDER_BID
        ).one()
        operation.submitted_at = now_utc() - timedelta(hours=elapsed_hours)
        db.session.commit()
    gateway.create_error = None
    result = _refund(refund_app)
    if 0 <= elapsed_hours < 23:
        assert result.status == "refunded"
        assert len(gateway.requests) == 2
        assert (
            gateway.requests[0].metadata["idempotency_key"]
            == gateway.requests[1].metadata["idempotency_key"]
        )
        assert len(gateway.remote) == 1
        _assert_accounting(refund_app, finalized=True)
    else:
        assert result.status == "reconciliation_required"
        assert len(gateway.requests) == 1
        assert gateway.remote == {}
        assert _operation(refund_app)["finalized_at"] is None
        _assert_accounting(refund_app, finalized=False)


def test_remote_success_followed_by_lost_response_is_recovered_by_lookup(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    def lose_response() -> None:
        message = "response lost after remote acceptance"
        raise TimeoutError(message)

    gateway.after_create = lose_response
    with pytest.raises(TimeoutError, match="response lost after remote acceptance"):
        _refund(refund_app)
    assert len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=False)
    gateway.after_create = None
    assert _refund(refund_app).status == "refunded"
    assert len(gateway.requests) == 1
    _assert_accounting(refund_app, finalized=True)


def test_webhook_refunded_order_still_recovers_unfinished_local_accounting(
    refund_app: Flask, gateway: RefundGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = checkout.grant_refund_return_credits

    def fail_grant(*_args: object, **_kwargs: object) -> None:
        message = "local accounting unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(checkout, "grant_refund_return_credits", fail_grant)
    with pytest.raises(RuntimeError, match="local accounting unavailable"):
        _refund(refund_app)
    with refund_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=ORDER_BID).one()
        order.status = BILLING_ORDER_STATUS_REFUNDED
        order.refunded_at = now_utc()
        order.metadata_json = {**order.metadata_json, "latest_source": "webhook"}
        db.session.commit()
    monkeypatch.setattr(checkout, "grant_refund_return_credits", original)
    result = _refund(refund_app)
    assert result.status == "refunded"
    assert result.refund_reference_id
    assert len(gateway.requests) == 1
    assert _operation(refund_app)["finalized_at"] is not None
    _assert_accounting(refund_app, finalized=True)


def test_overlapping_requests_share_remote_refund_and_finalize_credits_once(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    accepted = Event()
    release_first = Event()
    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def pause_first_response() -> None:
        if current_thread().name == "refund-first":
            accepted.set()
            assert release_first.wait(timeout=10), (
                "second refund request did not complete"
            )

    def run_refund() -> None:
        try:
            results[current_thread().name] = _refund(refund_app)
        except BaseException as exc:
            errors.append(exc)

    gateway.after_create = pause_first_response
    first = Thread(target=run_refund, name="refund-first")
    second = Thread(target=run_refund, name="refund-second")
    first.start()
    try:
        assert accepted.wait(timeout=10), "first request did not reach provider"
        second.start()
        second.join(timeout=10)
        assert not second.is_alive(), (
            "second request held a transaction across provider IO"
        )
    finally:
        release_first.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
    assert not first.is_alive()
    assert errors == []
    assert set(results) == {"refund-first", "refund-second"}
    assert (
        results["refund-first"].refund_reference_id
        == results["refund-second"].refund_reference_id
    )
    assert {
        request.metadata["idempotency_key"]
        for request in gateway.requests + gateway.lookups
    } == {_operation(refund_app)["idempotency_key"]}
    assert len(gateway.remote) == len(gateway.requests) == 1
    _assert_accounting(refund_app, finalized=True)


def test_refund_rejects_nested_unit_of_work_before_provider_io(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    with (
        refund_app.app_context(),
        uow.unit_of_work(),
        pytest.raises(RuntimeError, match="owns its own transaction"),
    ):
        _refund(refund_app)
    assert gateway.requests == gateway.lookups == []
    _assert_accounting(refund_app, finalized=False)


@pytest.mark.parametrize("commit_event", ["before_commit", "after_commit"])
@pytest.mark.parametrize("include_provider_extra", [True, False])
def test_final_commit_failure_or_lost_ack_recovers_without_second_refund(
    commit_event: str,
    include_provider_extra: bool,
    refund_app: Flask,
    gateway: RefundGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not include_provider_extra:
        _use_expanded_payment_metadata(refund_app)
    original = checkout.grant_refund_return_credits

    def mark_final_transaction(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        db.session().info["fail_refund_final_commit"] = True
        return result

    def interrupt_commit(session: Session) -> None:
        if session.info.pop("fail_refund_final_commit", False):
            message = "refund final commit interrupted"
            raise RuntimeError(message)

    monkeypatch.setattr(checkout, "grant_refund_return_credits", mark_final_transaction)
    event.listen(Session, commit_event, interrupt_commit)
    try:
        with pytest.raises(RuntimeError, match="refund final commit interrupted"):
            _refund(refund_app)
    finally:
        event.remove(Session, commit_event, interrupt_commit)
    _assert_accounting(refund_app, finalized=commit_event == "after_commit")
    monkeypatch.setattr(checkout, "grant_refund_return_credits", original)
    result = _refund(refund_app)
    assert result.status == "refunded"
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=True)


def test_two_empty_lookups_can_post_the_same_key_without_two_refunds(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    first_queried = Event()
    second_queried = Event()
    second_accepted = Event()
    first_finished = Event()
    errors: list[BaseException] = []
    results: dict[str, object] = {}

    def synchronize_empty_lookups() -> None:
        if current_thread().name == "refund-first":
            first_queried.set()
            assert second_queried.wait(timeout=10)
        else:
            second_queried.set()

    def order_responses_after_both_posts() -> None:
        if current_thread().name == "refund-second":
            second_accepted.set()
            assert first_finished.wait(timeout=10)
        else:
            assert second_accepted.wait(timeout=10)

    def run_refund() -> None:
        try:
            results[current_thread().name] = _refund(refund_app)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if current_thread().name == "refund-first":
                first_finished.set()

    gateway.after_lookup = synchronize_empty_lookups
    gateway.after_create = order_responses_after_both_posts
    first = Thread(target=run_refund, name="refund-first")
    second = Thread(target=run_refund, name="refund-second")
    first.start()
    try:
        assert first_queried.wait(timeout=10)
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)
    finally:
        second_queried.set()
        second_accepted.set()
        first_finished.set()
        first.join(timeout=10)
        if second.ident is not None:
            second.join(timeout=10)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(gateway.requests) == 2
    assert gateway.requests[0] == gateway.requests[1]
    assert len(gateway.remote) == 1
    assert (
        results["refund-first"].refund_reference_id
        == results["refund-second"].refund_reference_id
    )
    _assert_accounting(refund_app, finalized=True)


def test_mysql_row_lock_blocks_refund_before_any_provider_call(
    mysql_refund_app: Flask, gateway: RefundGateway
) -> None:
    attempted_lock = Event()
    contacted_provider = Event()
    errors: list[BaseException] = []
    results: list[object] = []

    def observe_lock_query(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if (
            current_thread().name == "mysql-refund-request"
            and "bill_orders" in statement
            and "FOR UPDATE" in statement
        ):
            attempted_lock.set()

    def run_refund() -> None:
        try:
            results.append(_refund(mysql_refund_app))
        except BaseException as exc:
            errors.append(exc)

    gateway.after_lookup = contacted_provider.set
    worker = Thread(target=run_refund, name="mysql-refund-request")
    with mysql_refund_app.app_context(), Session(db.engine) as holder:
        holder.execute(
            select(BillingOrder).filter_by(bill_order_bid=ORDER_BID).with_for_update()
        ).scalar_one()
        engine = db.engine
        event.listen(engine, "before_cursor_execute", observe_lock_query)
        worker.start()
        try:
            assert attempted_lock.wait(timeout=10)
            assert not contacted_provider.wait(timeout=0.2)
        finally:
            holder.commit()
            worker.join(timeout=10)
            event.remove(engine, "before_cursor_execute", observe_lock_query)
    assert not worker.is_alive()
    assert errors == []
    assert len(results) == 1
    assert results[0].status == "refunded"
    assert contacted_provider.is_set()
    _assert_accounting(mysql_refund_app, finalized=True)


def test_mysql_concurrent_prepare_and_finalize_create_one_refund_operation(
    mysql_refund_app: Flask, gateway: RefundGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    # MySQL DATETIME(0) rounds fractional seconds by default. A legitimate
    # immediate retry must not mistake a rounded-up submitted_at for a future
    # timestamp and enter manual reconciliation.
    clock_now = now_utc().replace(microsecond=800000)
    monkeypatch.setattr(checkout, "now_utc", lambda: clock_now)
    both_waiting = Event()
    observed = set()
    guard = Lock()
    lookup_barrier = Barrier(2, timeout=10)
    response_barrier = Barrier(2, timeout=10)
    lookup_threads: set[str] = set()
    create_threads: set[str] = set()
    results: list[object] = []
    errors: list[BaseException] = []

    def observe_lock_query(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        worker_name = current_thread().name
        if (
            worker_name.startswith("mysql-refund-")
            and "bill_orders" in statement
            and "FOR UPDATE" in statement
        ):
            with guard:
                observed.add(worker_name)
                if len(observed) == 2:
                    both_waiting.set()

    def run_refund() -> None:
        try:
            results.append(_refund(mysql_refund_app))
        except BaseException as exc:
            errors.append(exc)

    def synchronize_initial_lookups() -> None:
        worker_name = current_thread().name
        with guard:
            first_lookup = worker_name not in lookup_threads
            lookup_threads.add(worker_name)
        if first_lookup:
            lookup_barrier.wait()

    def synchronize_initial_posts() -> None:
        operation = _operation(mysql_refund_app)
        assert operation["submitted_at"] <= clock_now
        worker_name = current_thread().name
        with guard:
            first_post = worker_name not in create_threads
            create_threads.add(worker_name)
        if first_post:
            response_barrier.wait()

    gateway.after_lookup = synchronize_initial_lookups
    gateway.after_create = synchronize_initial_posts
    workers = [
        Thread(target=run_refund, name=f"mysql-refund-{index}") for index in range(2)
    ]
    with mysql_refund_app.app_context(), Session(db.engine) as holder:
        holder.execute(
            select(BillingOrder).filter_by(bill_order_bid=ORDER_BID).with_for_update()
        ).scalar_one()
        engine = db.engine
        event.listen(engine, "before_cursor_execute", observe_lock_query)
        for worker in workers:
            worker.start()
        try:
            assert both_waiting.wait(timeout=10)
            assert gateway.requests == gateway.lookups == []
        finally:
            holder.commit()
            for worker in workers:
                worker.join(timeout=15)
            event.remove(engine, "before_cursor_execute", observe_lock_query)
            lookup_barrier.abort()
            response_barrier.abort()
            for worker in workers:
                worker.join(timeout=5)
    assert all(not worker.is_alive() for worker in workers)
    assert errors == [], (
        f"requests={gateway.requests!r}; lookups={gateway.lookups!r}; results={results!r}\n"
        + "\n".join("".join(format_exception(exc)) for exc in errors)
    )
    assert len(results) == 2
    assert {result.status for result in results} == {"refunded"}
    assert len({result.refund_reference_id for result in results}) == 1
    assert len(gateway.requests) == 2
    assert gateway.requests[0] == gateway.requests[1]
    assert len(gateway.remote) == 1
    with mysql_refund_app.app_context(), Session(db.engine) as session:
        operations = (
            session.execute(
                select(models.BillingRefundOperation).filter_by(
                    bill_order_bid=ORDER_BID
                )
            )
            .scalars()
            .all()
        )
        assert len(operations) == 1
        assert operations[0].finalized_at is not None
    _assert_accounting(mysql_refund_app, finalized=True)


@pytest.mark.parametrize("later_status", ["failed", "requires_action"])
def test_unfinalized_success_must_recheck_provider_status_before_crediting(
    later_status: str,
    refund_app: Flask,
    gateway: RefundGateway,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = checkout.grant_refund_return_credits

    def fail_after_credit_write(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)
        db.session.flush()
        assert CreditLedgerEntry.query.filter_by(creator_bid=CREATOR_BID).count() == 1
        message = "local finalization failed"
        raise RuntimeError(message)

    monkeypatch.setattr(
        checkout, "grant_refund_return_credits", fail_after_credit_write
    )
    with pytest.raises(RuntimeError, match="local finalization failed"):
        _refund(refund_app)
    before = _operation(refund_app)
    assert before["provider_status"] == "succeeded"
    assert before["finalized_at"] is None
    _assert_accounting(refund_app, finalized=False)
    for response in gateway.remote.values():
        response.status = later_status
        response.raw_response["status"] = later_status
    monkeypatch.setattr(checkout, "grant_refund_return_credits", original)
    if later_status == "failed":
        with pytest.raises(AppError):
            _refund(refund_app)
    else:
        assert _refund(refund_app).status == "pending"
    after = _operation(refund_app)
    assert after["provider_status"] == later_status
    assert after["finalized_at"] is None
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=False)


@pytest.mark.parametrize(
    ("stale_status", "latest_status"),
    [
        ("pending", "succeeded"),
        ("succeeded", "failed"),
        ("succeeded", "requires_action"),
    ],
)
def test_late_provider_observation_cannot_overwrite_a_newer_observation(
    stale_status: str,
    latest_status: str,
    refund_app: Flask,
    gateway: RefundGateway,
) -> None:
    gateway.status = "pending"
    assert _refund(refund_app).status == "pending"
    for response in gateway.remote.values():
        response.status = stale_status
        response.raw_response["status"] = stale_status
    stale_response_ready = Event()
    release_stale = Event()
    outcomes: list[object] = []

    def delay_first_observation() -> None:
        if (
            current_thread().name == "stale-refund-reader"
            and not stale_response_ready.is_set()
        ):
            stale_response_ready.set()
            assert release_stale.wait(timeout=10)

    def run_stale_request() -> None:
        try:
            outcomes.append(_refund(refund_app))
        except BaseException as exc:
            outcomes.append(exc)

    gateway.after_lookup = delay_first_observation
    worker = Thread(target=run_stale_request, name="stale-refund-reader")
    worker.start()
    try:
        assert stale_response_ready.wait(timeout=10)
        for response in gateway.remote.values():
            response.status = latest_status
            response.raw_response["status"] = latest_status
        if latest_status == "failed":
            with pytest.raises(AppError):
                _refund(refund_app)
        else:
            expected = "refunded" if latest_status == "succeeded" else "pending"
            assert _refund(refund_app).status == expected
    finally:
        release_stale.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert len(outcomes) == 1
    if latest_status == "failed":
        assert isinstance(outcomes[0], AppError)
    else:
        assert not isinstance(outcomes[0], BaseException)
        assert outcomes[0].status == (
            "refunded" if latest_status == "succeeded" else "pending"
        )
    operation = _operation(refund_app)
    assert operation["provider_status"] == latest_status
    assert bool(operation["finalized_at"]) is (latest_status == "succeeded")
    if latest_status != "succeeded":
        # Initial lookup, both overlapping observations, then a fresh lookup
        # after the late caller learns that its stored version is obsolete.
        assert len(gateway.lookups) >= 4
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=latest_status == "succeeded")


@pytest.mark.parametrize(
    "reason", ["requested", "requested_by_creator", "not_a_stripe_reason"]
)
def test_invalid_reason_does_not_claim_the_order_or_block_a_corrected_request(
    reason: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    with pytest.raises(AppError):
        _refund(refund_app, {"reason": reason})
    assert gateway.requests == gateway.lookups == []
    with refund_app.app_context(), Session(db.engine) as session:
        assert (
            session.execute(select(models.BillingRefundOperation)).scalars().all() == []
        )
    _assert_accounting(refund_app, finalized=False)
    assert _refund(refund_app, {"reason": "requested_by_customer"}).status == "refunded"
    assert len(gateway.requests) == 1
    assert gateway.requests[0].reason == "requested_by_customer"
    _assert_accounting(refund_app, finalized=True)


@pytest.mark.parametrize("currency", ["US", "USDX", "€US", "１２３"])
def test_invalid_payment_currency_does_not_leave_an_unusable_refund_operation(
    currency: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    with refund_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=ORDER_BID).one()
        order.currency = currency
        db.session.commit()
    with pytest.raises(AppError):
        _refund(refund_app)
    assert gateway.requests == gateway.lookups == []
    with refund_app.app_context(), Session(db.engine) as session:
        assert (
            session.execute(select(models.BillingRefundOperation)).scalars().all() == []
        )
    _assert_accounting(refund_app, finalized=False)
    with refund_app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=ORDER_BID).one()
        order.currency = "USD"
        db.session.commit()
    assert _refund(refund_app).status == "refunded"
    _assert_accounting(refund_app, finalized=True)


def test_continuously_superseded_observations_stop_without_refunding_or_crediting(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    gateway.status = "pending"
    assert _refund(refund_app).status == "pending"
    original_request = deepcopy(gateway.requests[0])
    competing_pending_result = RefundGateway.result(original_request, "pending")
    for response in gateway.remote.values():
        response.status = "succeeded"
        response.raw_response["status"] = "succeeded"
    observed_versions: list[int] = []

    def commit_a_newer_pending_observation() -> None:
        # This is a second database connection, independent of the request's
        # session. Each already-read success response becomes obsolete before
        # the request tries to store it, just as a competing worker can do.
        with refund_app.app_context(), Session(db.engine) as session:
            operation = session.execute(
                select(models.BillingRefundOperation).filter_by(
                    bill_order_bid=ORDER_BID
                )
            ).scalar_one()
            operation.provider_status = "pending"
            operation.provider_payload = deepcopy(competing_pending_result.raw_response)
            operation.provider_result_version += 1
            observed_versions.append(operation.provider_result_version)
            session.commit()

    gateway.after_lookup = commit_a_newer_pending_observation
    before_lookups = len(gateway.lookups)
    with pytest.raises(AppError):
        _refund(refund_app)
    assert len(gateway.lookups) - before_lookups == 3
    assert len(observed_versions) == 3
    assert observed_versions == sorted(set(observed_versions))
    assert len(gateway.requests) == len(gateway.remote) == 1
    operation = _operation(refund_app)
    assert operation["provider_status"] == "pending"
    assert operation["provider_result_version"] == observed_versions[-1]
    assert operation["finalized_at"] is None
    _assert_accounting(refund_app, finalized=False)


def test_provider_result_commit_failure_recovers_from_remote_operation_evidence(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    failed_commits: list[str] = []

    def fail_provider_result_commit(session: Session) -> None:
        for row in session.dirty:
            if (
                isinstance(row, models.BillingRefundOperation)
                and row.provider_status == "succeeded"
                and row.provider_result_version > 0
                and row.finalized_at is None
            ):
                failed_commits.append(row.refund_operation_bid)
                message = "provider result commit failed"
                raise RuntimeError(message)

    event.listen(Session, "before_commit", fail_provider_result_commit)
    try:
        with pytest.raises(RuntimeError, match="provider result commit failed"):
            _refund(refund_app)
    finally:
        event.remove(Session, "before_commit", fail_provider_result_commit)
    assert len(failed_commits) == 1
    assert len(gateway.remote) == len(gateway.requests) == 1
    operation = _operation(refund_app)
    assert operation["refund_operation_bid"] == failed_commits[0]
    assert operation["submitted_at"] is not None
    assert operation["provider_status"] == ""
    assert operation["provider_refund_id"] == ""
    assert operation["provider_result_version"] == 0
    assert operation["finalized_at"] is None
    _assert_accounting(refund_app, finalized=False)
    assert _refund(refund_app).status == "refunded"
    assert len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=True)


def _seed_legacy_refunded_subscription(
    app: Flask,
    *,
    completed: bool = False,
    credit_amount: Decimal = Decimal(20),
    refund_status: str = "succeeded",
) -> None:
    """Reproduce a webhook-only refund or a fully committed pre-journal refund."""
    with app.app_context(), Session(db.engine) as session:
        order = session.execute(select(BillingOrder)).scalar_one()
        plan = session.execute(select(BillingSubscription)).scalar_one()
        product = session.execute(
            select(BillingProduct).filter_by(product_bid=plan.product_bid)
        ).scalar_one()
        product.credit_amount = credit_amount
        order.product_bid = plan.product_bid
        order.subscription_bid = plan.subscription_bid
        order.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
        order.status = BILLING_ORDER_STATUS_REFUNDED
        order.refunded_at = now_utc() - timedelta(days=2)
        if completed:
            order.metadata_json = {
                **order.metadata_json,
                "refund_reference_id": "re_historical",
                "refund_status": refund_status,
            }
            plan.status = BILLING_SUBSCRIPTION_STATUS_CANCELED
            plan.cancel_at_period_end = 1
        session.add(
            BillingRenewalEvent(
                renewal_event_bid="renewal-before-legacy-refund",
                subscription_bid=plan.subscription_bid,
                creator_bid=CREATOR_BID,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                scheduled_at=plan.current_period_end_at,
                status=BILLING_RENEWAL_EVENT_STATUS_CANCELED
                if completed
                else BILLING_RENEWAL_EVENT_STATUS_PENDING,
                processed_at=order.refunded_at if completed else None,
                payload_json={"period": "original"},
            )
        )
        session.commit()
    if completed and credit_amount > 0:
        checkout.grant_refund_return_credits(
            app,
            creator_bid=CREATOR_BID,
            amount=credit_amount,
            refund_bid="re_historical",
            metadata={
                "bill_order_bid": ORDER_BID,
                "product_bid": "bill-product-plan-monthly",
            },
        )


def _legacy_refund_state(app: Flask) -> dict[str, object]:
    """Read durable business state through a fresh session, excluding the journal."""
    with app.app_context(), Session(db.engine) as session:
        order = session.execute(select(BillingOrder)).scalar_one()
        plan = session.execute(select(BillingSubscription)).scalar_one()
        return {
            "order_status": order.status,
            "refunded_at": order.refunded_at,
            "order_metadata": deepcopy(order.metadata_json),
            "subscription": (
                plan.status,
                plan.cancel_at_period_end,
                plan.current_period_start_at,
                plan.current_period_end_at,
                plan.updated_at,
                deepcopy(plan.metadata_json),
            ),
            "events": [
                (row.renewal_event_bid, row.status, row.processed_at, row.updated_at)
                for row in session.scalars(
                    select(BillingRenewalEvent).order_by(BillingRenewalEvent.id)
                )
            ],
            "entries": [
                (
                    row.ledger_bid,
                    row.source_bid,
                    row.idempotency_key,
                    row.amount,
                    row.wallet_bucket_bid,
                    row.balance_after,
                )
                for row in session.scalars(select(CreditLedgerEntry))
            ],
            "buckets": [
                (
                    row.wallet_bucket_bid,
                    row.original_credits,
                    row.available_credits,
                    row.reserved_credits,
                )
                for row in session.scalars(select(CreditWalletBucket))
            ],
            "wallets": [
                (row.wallet_bid, row.available_credits, row.reserved_credits)
                for row in session.scalars(select(CreditWallet))
            ],
        }


def _historical_refund() -> PaymentRefundResult:
    return RefundGateway.result(
        PaymentRefundRequest(
            ORDER_BID,
            amount=1000,
            metadata={
                "creator_bid": CREATOR_BID,
                "currency": "usd",
                "payment_intent_id": "pi_refund_recovery",
                "charge_id": "ch_refund_recovery",
            },
        ),
        "succeeded",
    )


def test_legacy_webhook_refunded_order_recovers_missing_subscription_effects(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    _seed_legacy_refunded_subscription(refund_app)
    before = _legacy_refund_state(refund_app)
    assert before["subscription"][0] == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert before["events"][0][1] == BILLING_RENEWAL_EVENT_STATUS_PENDING
    assert before["entries"] == []
    gateway.historical = _historical_refund()

    result = _refund(refund_app)

    assert result.status == "refunded"
    assert result.refund_reference_id == "re_historical"
    assert gateway.requests == []
    assert len(gateway.lookups) == 1
    after = _legacy_refund_state(refund_app)
    assert after["order_status"] == BILLING_ORDER_STATUS_REFUNDED
    assert after["refunded_at"] == before["refunded_at"]
    assert after["subscription"][:2] == (BILLING_SUBSCRIPTION_STATUS_CANCELED, 1)
    assert after["events"][0][1] == BILLING_RENEWAL_EVENT_STATUS_CANCELED
    assert after["events"][0][2] is not None
    assert len(after["entries"]) == len(after["buckets"]) == 1
    assert after["entries"][0][1:4] == (
        "re_historical",
        "refund_return:re_historical",
        Decimal(20),
    )
    assert after["entries"][0][4] == after["buckets"][0][0]
    assert after["buckets"][0][1:3] == (Decimal(20), Decimal(20))
    assert _operation(refund_app)["finalized_at"] is not None
    assert _refund(refund_app).refund_reference_id == "re_historical"
    assert _legacy_refund_state(refund_app) == after
    assert len(gateway.lookups) == 1
    assert gateway.requests == []


def _reactivate_legacy_subscription(app: Flask) -> None:
    with app.app_context(), Session(db.engine) as session:
        plan = session.execute(select(BillingSubscription)).scalar_one()
        plan.status = BILLING_SUBSCRIPTION_STATUS_ACTIVE
        plan.cancel_at_period_end = 0
        plan.current_period_start_at = now_utc()
        plan.current_period_end_at = now_utc() + timedelta(days=60)
        plan.metadata_json = {"reactivated_after_refund": True}
        session.add(
            BillingRenewalEvent(
                renewal_event_bid="renewal-after-reactivation",
                subscription_bid=plan.subscription_bid,
                creator_bid=CREATOR_BID,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
                scheduled_at=plan.current_period_end_at,
                status=BILLING_RENEWAL_EVENT_STATUS_PENDING,
                payload_json={"period": "reactivated"},
            )
        )
        session.commit()


@pytest.mark.parametrize(
    ("refund_status", "credit_amount"),
    [
        ("succeeded", Decimal(20)),
        ("pending", Decimal(0)),
        ("requires_action", Decimal(0)),
    ],
)
def test_legacy_completed_marker_preserves_reactivated_subscription_without_http(
    refund_status: str,
    credit_amount: Decimal,
    refund_app: Flask,
    gateway: RefundGateway,
) -> None:
    _seed_legacy_refunded_subscription(
        refund_app,
        completed=True,
        credit_amount=credit_amount,
        refund_status=refund_status,
    )
    _reactivate_legacy_subscription(refund_app)
    before = _legacy_refund_state(refund_app)
    assert len(before["entries"]) == len(before["buckets"]) == int(credit_amount > 0)
    assert before["subscription"][:2] == (BILLING_SUBSCRIPTION_STATUS_ACTIVE, 0)
    assert before["events"][-1][1] == BILLING_RENEWAL_EVENT_STATUS_PENDING
    # A later catalog edit must not reinterpret the old completed transaction.
    with refund_app.app_context(), Session(db.engine) as session:
        product = session.execute(
            select(BillingProduct).filter_by(product_bid="bill-product-plan-monthly")
        ).scalar_one()
        product.credit_amount = Decimal(100)
        session.commit()
    gateway.lookup_error = RuntimeError("completed local refund needs no HTTP")

    for _ in range(2):
        result = _refund(refund_app)
        assert result.status == "refunded"
        assert result.refund_reference_id == "re_historical"
        assert _legacy_refund_state(refund_app) == before
        assert gateway.requests == gateway.lookups == []
        with refund_app.app_context(), Session(db.engine) as session:
            assert session.scalars(select(models.BillingRefundOperation)).all() == []


def test_legacy_ledger_recovers_missing_marker_without_replaying_subscription_effects(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    _seed_legacy_refunded_subscription(refund_app, completed=True)
    _reactivate_legacy_subscription(refund_app)
    with refund_app.app_context(), Session(db.engine) as session:
        order = session.execute(select(BillingOrder)).scalar_one()
        metadata = dict(order.metadata_json)
        del metadata["refund_reference_id"]
        del metadata["refund_status"]
        order.metadata_json = metadata
        session.commit()
    before = _legacy_refund_state(refund_app)
    assert len(before["entries"]) == len(before["buckets"]) == 1
    assert before["entries"][0][1:4] == (
        "re_historical",
        "refund_return:re_historical",
        Decimal(20),
    )
    assert before["subscription"][:2] == (BILLING_SUBSCRIPTION_STATUS_ACTIVE, 0)
    assert before["events"][-1][1] == BILLING_RENEWAL_EVENT_STATUS_PENDING
    gateway.historical = _historical_refund()

    result = _refund(refund_app)

    assert result.status == "refunded"
    assert result.refund_reference_id == "re_historical"
    assert gateway.requests == []
    assert len(gateway.lookups) == 1
    assert _operation(refund_app)["finalized_at"] is not None
    after = _legacy_refund_state(refund_app)
    assert after == before
    assert _refund(refund_app).refund_reference_id == "re_historical"
    assert _legacy_refund_state(refund_app) == after
    assert len(gateway.lookups) == 1
    assert gateway.requests == []


def test_legacy_refunded_order_without_remote_evidence_never_posts_another_refund(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    _seed_legacy_refunded_subscription(refund_app)
    before = _legacy_refund_state(refund_app)

    for _ in range(2):
        result = _refund(refund_app)
        assert result.status == "reconciliation_required"
        assert gateway.requests == []
        assert gateway.remote == {}
        assert _legacy_refund_state(refund_app) == before
        operation = _operation(refund_app)
        assert operation["submitted_at"] is None
        assert operation["finalized_at"] is None
    assert len(gateway.lookups) == 2


def test_legacy_refunded_order_with_ambiguous_history_never_changes_local_effects(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    _seed_legacy_refunded_subscription(refund_app)
    before = _legacy_refund_state(refund_app)
    gateway.lookup_error = RuntimeError("historical partial refund is ambiguous")

    with pytest.raises(RuntimeError, match="historical partial refund is ambiguous"):
        _refund(refund_app)

    assert len(gateway.lookups) == 1
    assert gateway.requests == []
    assert gateway.remote == {}
    assert _legacy_refund_state(refund_app) == before
    assert _operation(refund_app)["finalized_at"] is None


def test_webhook_refund_after_prepare_blocks_dispatch_with_empty_remote_history(
    refund_app: Flask, gateway: RefundGateway
) -> None:
    def receive_webhook() -> None:
        assert _operation(refund_app)["submitted_at"] is None
        with refund_app.app_context(), Session(db.engine) as session:
            order = session.execute(select(BillingOrder)).scalar_one()
            order.status = BILLING_ORDER_STATUS_REFUNDED
            order.refunded_at = now_utc()
            session.commit()

    gateway.after_lookup = receive_webhook
    result = _refund(refund_app)

    assert result.status == "reconciliation_required"
    assert gateway.requests == []
    assert gateway.remote == {}
    state = _legacy_refund_state(refund_app)
    assert state["order_status"] == BILLING_ORDER_STATUS_REFUNDED
    assert state["entries"] == state["buckets"] == state["wallets"] == []
    assert state["subscription"][0] == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert _operation(refund_app)["submitted_at"] is None
    assert _operation(refund_app)["finalized_at"] is None


def _use_expanded_payment_metadata(app: Flask, *, checkout_extra: bool = False) -> None:
    """Persist the expanded payment objects returned by a manual Stripe sync."""
    with app.app_context(), Session(db.engine) as session:
        order = session.execute(select(BillingOrder)).scalar_one()
        metadata = {
            **order.metadata_json,
            "latest_provider_payload": {
                "payment_intent": {
                    "id": "pi_refund_recovery",
                    "latest_charge": "ch_refund_recovery",
                },
            },
        }
        metadata.pop("provider_extra", None)
        if checkout_extra:
            # The Stripe checkout adapter stores latest_charge_id, not charge_id.
            metadata["provider_extra"] = {
                "payment_intent_id": "pi_refund_recovery",
                "latest_charge_id": "ch_refund_recovery",
            }
        order.metadata_json = metadata
        session.commit()


@pytest.mark.parametrize("checkout_extra", [False, True])
def test_completed_refund_retry_accepts_saved_scalar_payment_references(
    checkout_extra: bool, refund_app: Flask, gateway: RefundGateway
) -> None:
    _use_expanded_payment_metadata(refund_app, checkout_extra=checkout_extra)

    first = _refund(refund_app)

    assert first.status == "refunded"
    assert gateway.requests[0].metadata["payment_intent_id"] == "pi_refund_recovery"
    assert gateway.requests[0].metadata["charge_id"] == "ch_refund_recovery"
    before = _legacy_refund_state(refund_app)
    saved_payload = before["order_metadata"]["latest_provider_payload"]
    assert saved_payload["payment_intent"] == "pi_refund_recovery"
    assert saved_payload["charge"] == "ch_refund_recovery"
    completed_operation = _operation(refund_app)
    assert completed_operation["finalized_at"] is not None
    gateway.lookup_error = RuntimeError("completed refund must not contact Stripe")

    for _ in range(2):
        retry = _refund(refund_app)
        assert retry.status == "refunded"
        assert retry.refund_reference_id == first.refund_reference_id
        assert _operation(refund_app) == completed_operation
        assert _legacy_refund_state(refund_app) == before
    assert len(gateway.lookups) == len(gateway.requests) == len(gateway.remote) == 1
    _assert_accounting(refund_app, finalized=True)


@pytest.mark.parametrize("reference_field", ["payment_intent", "charge"])
def test_completed_refund_still_rejects_changed_scalar_payment_identity(
    reference_field: str, refund_app: Flask, gateway: RefundGateway
) -> None:
    _use_expanded_payment_metadata(refund_app)
    _refund(refund_app)
    with refund_app.app_context(), Session(db.engine) as session:
        order = session.execute(select(BillingOrder)).scalar_one()
        metadata = deepcopy(order.metadata_json)
        metadata["latest_provider_payload"][reference_field] = "other_payment"
        order.metadata_json = metadata
        session.commit()
    before = _legacy_refund_state(refund_app)
    completed_operation = _operation(refund_app)

    with pytest.raises(AppError):
        _refund(refund_app)

    assert _legacy_refund_state(refund_app) == before
    assert _operation(refund_app) == completed_operation
    assert len(gateway.lookups) == len(gateway.requests) == len(gateway.remote) == 1
