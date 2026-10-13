"""Protect learner admission and refund ownership for registered integrations."""

import threading
from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.common import cache_provider
from flaskr.dao import uow
from flaskr.service.order import funs, raw_snapshots
from flaskr.service.order.consts import ORDER_STATUS_REFUND
from flaskr.service.order.payment_providers.base import PaymentRefundResult
from flaskr.service.order.payment_providers.options import configured_payment_options
from flaskr.service.order.payment_snapshots import PaymentAttempt

from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("native_storage", [False, True])
def test_learner_options_require_usable_attempt_storage(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, native_storage: bool
) -> None:
    del integration_app
    if not native_storage:
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    learner = configured_payment_options(biz_domain="order")
    billing = configured_payment_options(biz_domain="billing")
    assert (
        any(option.provider == "fixture-hosted" for option in learner) == native_storage
    )
    assert any(option.provider == "fixture-hosted" for option in billing)
    assert any(option.provider == "fixture-pay" for option in learner)
    assert FixtureProvider.calls == []


def _paid_learner(app: Flask, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(funs, "cache_provider", cache_provider.InMemoryCacheProvider())
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )
    order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
    with app.test_client() as client:
        assert (
            _notify(client, "fixture-pay", snapshot.provider_attempt_id).status_code
            == 200
        )
    return order.order_bid


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("early_callback", [False, True])
def test_concurrent_learner_refunds_make_one_non_idempotent_provider_call(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch, early_callback: bool
) -> None:
    app = integration_app
    bid = _paid_learner(app, monkeypatch)
    reference = FixtureSnapshot.query.filter_by(order_bid=bid).one().provider_attempt_id
    entered, release, second_started, second_finished = (
        threading.Event() for _ in range(4)
    )
    calls, results, errors = [], [], []

    def refund(self: FixtureProvider, **_kwargs: object) -> PaymentRefundResult:
        del self
        assert not uow.in_unit_of_work()
        assert not dao.db.session().in_transaction()
        calls.append(True)
        entered.set()
        assert release.wait(5)
        return PaymentRefundResult(
            f"non-idempotent-refund-{len(calls)}", {}, "succeeded"
        )

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)

    def run(*, second: bool = False) -> None:
        try:
            with app.app_context():
                if second:
                    second_started.set()
                results.append(funs.refund_order_payment(app, bid))
        except Exception as error:
            errors.append(error)
        finally:
            if second:
                second_finished.set()

    first = threading.Thread(target=run, daemon=True)
    second = threading.Thread(target=lambda: run(second=True), daemon=True)
    first.start()
    try:
        assert entered.wait(5)
        if early_callback:
            with app.test_client() as client:
                assert (
                    _notify(
                        client, "fixture-pay", reference, state="refunded"
                    ).status_code
                    == 200
                )
        second.start()
        assert second_started.wait(5)
        assert not second_finished.wait(0.2)
        assert len(calls) == 1
    finally:
        release.set()
        first.join(5)
        if second.ident:
            second.join(5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(calls) == 1
    assert len(results) == 2
    assert results[0] == results[1]
    dao.db.session.expire_all()
    assert funs.Order.query.filter_by(order_bid=bid).one().status == ORDER_STATUS_REFUND


def test_learner_refund_keeps_the_receipt_after_local_finalization_failure(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = integration_app
    bid = _paid_learner(app, monkeypatch)
    calls, failures = [], []

    def refund(self: FixtureProvider, **_kwargs: object) -> PaymentRefundResult:
        del self
        calls.append(True)
        return PaymentRefundResult(
            f"non-idempotent-refund-{len(calls)}", {"id": "saved-refund"}, "succeeded"
        )

    original = PaymentAttempt.persist_refund

    def fail_once(self: PaymentAttempt, result: PaymentRefundResult) -> None:
        if not failures:
            failures.append(True)
            message = "Injected learner refund finalization failure"
            raise RuntimeError(message)
        original(self, result)

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    monkeypatch.setattr(PaymentAttempt, "persist_refund", fail_once)
    with pytest.raises(RuntimeError, match="Injected learner refund"):
        funs.refund_order_payment(app, bid)
    result = funs.refund_order_payment(app, bid)
    assert result["refund_id"] == "non-idempotent-refund-1"
    assert len(calls) == 1
