"""Keep external refunds idempotent across concurrency and local persistence failures."""

import threading
from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.common import cache_provider
from flaskr.dao import uow
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
)
from flaskr.service.common.models import AppError
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRefundResult,
)

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


def _paid_order(
    app: Flask, monkeypatch: pytest.MonkeyPatch, *, subscription: bool = False
) -> str:
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )
    with app.test_client() as client:
        if subscription:
            path, product = (
                "/api/billing/subscriptions/checkout",
                "bill-product-plan-monthly",
            )
        else:
            add_active_subscription(app)
            path, product = "/api/billing/topups/checkout", "bill-product-topup-small"
        created = client.post(
            path,
            json={"product_bid": product, "payment_option": "fixture-pay:fixture_qr"},
        ).get_json(force=True)
        assert created["code"] == 0, created
        bid = created["data"]["bill_order_bid"]
        assert _notify(client, "fixture-pay", bid).status_code == 200
    return bid


@pytest.mark.parametrize("failure", ["response", "receipt", "writer", "wallet"])
def test_refund_recovers_with_the_original_key_without_repeating_money_effects(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch, subscription=True)
    requests, external = [], {}
    tripped = []

    def refund(
        self: FixtureProvider, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del self, app
        assert not uow.in_unit_of_work()
        assert request.metadata["idempotency_key"]
        requests.append(request)
        result = external.setdefault(
            request.metadata["idempotency_key"],
            PaymentRefundResult("refund-once", {"id": "refund-once"}, "succeeded"),
        )
        if failure == "response" and not tripped:
            tripped.append(True)
            message = "Injected lost refund response"
            raise RuntimeError(message)
        return result

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    if failure == "receipt":
        original = dao.db.session.commit

        def commit() -> None:
            if external and not tripped:
                tripped.append(True)
                message = "Injected receipt commit failure"
                raise RuntimeError(message)
            original()

        monkeypatch.setattr(dao.db.session, "commit", commit)
    elif failure in {"writer", "wallet"}:
        name = (
            "persist_refund"
            if failure == "writer"
            else "refresh_credit_wallet_snapshot"
        )
        original = getattr(checkout, name)

        def fail_once(*args: object, **kwargs: object) -> object:
            if not tripped:
                tripped.append(True)
                message = "Injected refund finalization failure"
                raise RuntimeError(message)
            return original(*args, **kwargs)

        monkeypatch.setattr(checkout, name, fail_once)
    grants = CreditLedgerEntry.query.count()
    balance = (
        CreditWallet.query.filter_by(creator_bid="creator-1").one().available_credits
    )
    payload = {"amount": 100, "reason": "requested_by_customer"}
    with pytest.raises(RuntimeError, match="Injected"):
        checkout.refund_billing_order(app, "creator-1", bid, payload)
    dao.db.session.expire_all()
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    subscription = BillingSubscription.query.filter_by(
        subscription_bid=order.subscription_bid
    ).one()
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert subscription.cancel_at_period_end == 0
    assert CreditLedgerEntry.query.count() == grants
    assert (
        CreditWallet.query.filter_by(creator_bid="creator-1").one().available_credits
        == balance
    )
    operation = order.metadata_json["refund_operation"]
    assert operation["request"]["amount"] == 100
    assert bool(operation.get("response")) == (failure in {"writer", "wallet"})
    result = checkout.refund_billing_order(app, "creator-1", bid, payload)
    assert result.status == "refunded"
    assert result.refund_reference_id == "refund-once"
    assert len(external) == 1
    assert len(requests) == (2 if failure in {"response", "receipt"} else 1)
    assert all(item == requests[0] for item in requests)
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
    assert subscription.cancel_at_period_end == 1
    assert CreditLedgerEntry.query.count() == grants
    count = len(requests)
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert len(requests) == count


def test_refund_refuses_an_outer_unit_of_work_before_provider_io(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bid = _paid_order(integration_app, monkeypatch)
    called = []
    monkeypatch.setattr(
        FixtureProvider, "refund_payment", lambda *_a, **_k: called.append(True)
    )
    with unit_of_work(), pytest.raises(RuntimeError, match="owns its own transaction"):
        checkout.refund_billing_order(integration_app, "creator-1", bid, {})
    assert called == []


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
def test_concurrent_refunds_observe_a_committed_request_and_share_one_result(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch)
    locks = {}
    entered, release, second_started, second_finished = (
        threading.Event() for _ in range(4)
    )
    calls, results, errors = [], [], []

    class BlockingLock:
        def __init__(self, key: str) -> None:
            self.lock = locks.setdefault(key, threading.Lock())
            self.held = False

        def acquire(self, **_kwargs: object) -> bool:
            self.held = self.lock.acquire(timeout=5)
            return self.held

        def release(self) -> None:
            self.held = False
            self.lock.release()

        def extend(self, *_args: object, **_kwargs: object) -> bool:
            return self.held

    monkeypatch.setattr(
        cache_provider.cache, "lock", lambda key, **_kwargs: BlockingLock(key)
    )

    def refund(
        self: FixtureProvider, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del self
        assert not uow.in_unit_of_work()
        with app.app_context():
            stored = BillingOrder.query.filter_by(bill_order_bid=bid).one()
            assert (
                stored.metadata_json["refund_operation"]["request"]["metadata"][
                    "idempotency_key"
                ]
                == request.metadata["idempotency_key"]
            )
        calls.append(request)
        entered.set()
        assert release.wait(timeout=5)
        return PaymentRefundResult("refund-concurrent", {}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)

    def run(*, second: bool) -> None:
        try:
            with app.app_context():
                if second:
                    second_started.set()
                results.append(
                    checkout.refund_billing_order(app, "creator-1", bid, {}).status
                )
                if second:
                    second_finished.set()
        except Exception as error:
            errors.append(error)

    first = threading.Thread(target=run, kwargs={"second": False}, daemon=True)
    second = threading.Thread(target=run, kwargs={"second": True}, daemon=True)
    first.start()
    try:
        assert entered.wait(timeout=5)
        second.start()
        assert second_started.wait(timeout=5)
        assert not second_finished.wait(timeout=0.1)
    finally:
        release.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert results == ["refunded", "refunded"]
    assert len(calls) == 1


def test_lost_refund_lease_preserves_response_for_local_recovery(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch)
    calls, lost = [], []

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        return PaymentRefundResult("refund-before-lease-loss", {}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    original = cache_provider.RenewableLockLease.check_owned

    def check(lease: cache_provider.RenewableLockLease) -> None:
        if calls and not lost:
            lost.append(True)
            message = "Injected refund lease loss"
            raise cache_provider.CacheLockOwnershipError(message)
        original(lease)

    monkeypatch.setattr(cache_provider.RenewableLockLease, "check_owned", check)
    with pytest.raises(AppError):
        checkout.refund_billing_order(app, "creator-1", bid, {})
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    assert (
        order.metadata_json["refund_operation"]["response"]["provider_reference"]
        == "refund-before-lease-loss"
    )
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert calls == [True]


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("response_lost", [False, True])
def test_refund_callback_can_finish_during_provider_io_without_a_second_refund(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    response_lost: bool,
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch, subscription=True)
    calls, errors, acknowledgements = [], [], []

    def refund(
        self: FixtureProvider, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del self
        assert not uow.in_unit_of_work()
        calls.append(request)

        def callback() -> None:
            try:
                with app.app_context(), app.test_client() as client:
                    acknowledgements.append(
                        _notify(
                            client, "fixture-pay", bid, state="refunded"
                        ).status_code
                    )
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive()
        if response_lost:
            message = "Lost response after refund callback"
            raise RuntimeError(message)
        return PaymentRefundResult("refund-before-response", {}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    if response_lost:
        with pytest.raises(RuntimeError, match="Lost response"):
            checkout.refund_billing_order(app, "creator-1", bid, {})
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert errors == []
    assert acknowledgements == [200]
    assert len(calls) == 1
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    assert order.status == BILLING_ORDER_STATUS_REFUNDED
    assert order.metadata_json["refund_operation"]["status"] == "completed"
    subscription = BillingSubscription.query.filter_by(
        subscription_bid=order.subscription_bid
    ).one()
    assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
    assert subscription.cancel_at_period_end == 1


def test_uncertain_refund_does_not_accept_changed_parameters_or_a_new_key(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = integration_app
    bid = _paid_order(app, monkeypatch)
    requests = []

    def refund(
        self: FixtureProvider, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        del self, app
        requests.append(request)
        if len(requests) == 1:
            message = "Uncertain refund response"
            raise RuntimeError(message)
        return PaymentRefundResult("refund-original-request", {}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    original = {"amount": 100, "reason": "original_request"}
    with pytest.raises(RuntimeError, match="Uncertain"):
        checkout.refund_billing_order(app, "creator-1", bid, original)
    for changed in (
        {"amount": 200, "reason": "original_request"},
        {"amount": 100, "reason": "changed_request"},
    ):
        with pytest.raises(AppError):
            checkout.refund_billing_order(app, "creator-1", bid, changed)
    assert len(requests) == 1
    assert (
        checkout.refund_billing_order(app, "creator-1", bid, original).status
        == "refunded"
    )
    assert requests[0] == requests[1]
