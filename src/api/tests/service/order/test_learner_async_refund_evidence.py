"""Complete registered learner refunds from verified callbacks or queries."""

import json
from dataclasses import replace
from decimal import Decimal

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.order import funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.payment_providers.base import PaymentRefundResult

from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


def _pending_refund(
    app: Flask, monkeypatch: pytest.MonkeyPatch, initial: str = "pending"
) -> tuple:
    order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
    reference = snapshot.provider_attempt_id
    bid = order.order_bid
    with app.test_client() as client:
        assert _notify(client, "fixture-pay", reference).status_code == 200
    calls = []
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        return PaymentRefundResult("refund-async", {"status": initial}, initial)

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    assert funs.refund_order_payment(app, bid)["status"] == initial
    return order, snapshot, reference, calls


@pytest.mark.parametrize("initial", ["pending", "requires_action"])
@pytest.mark.parametrize("source", ["webhook", "query"])
def test_registered_learner_refund_completes_once_from_current_verified_evidence(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    initial: str,
    source: str,
) -> None:
    app = integration_app
    order, snapshot, reference, calls = _pending_refund(app, monkeypatch, initial)
    bid = order.order_bid
    for _ in range(2):
        assert funs.refund_order_payment(app, bid)["status"] == initial
    assert order.status == ORDER_STATUS_SUCCESS
    for _ in range(2):
        if source == "webhook":
            with app.test_client() as client:
                assert (
                    _notify(
                        client, "fixture-pay", reference, state="refunded"
                    ).status_code
                    == 200
                )
        else:
            FixtureProvider.attempts[reference]["state"] = "refunded"
            assert (
                funs.sync_native_payment_order(app, bid, expected_user="creator-1")[
                    "status"
                ]
                == 2
            )
    dao.db.session.expire_all()
    assert order.status == ORDER_STATUS_REFUND
    assert snapshot.status == 2
    assert funs.refund_order_payment(app, bid)["status"] == "succeeded"
    assert funs.refund_order_payment(app, bid)["refund_id"] == "refund-async"
    with app.test_client() as client:
        assert (
            _notify(client, "fixture-pay", reference, state="paid").status_code == 200
        )
    dao.db.session.expire_all()
    assert order.status == ORDER_STATUS_REFUND
    assert snapshot.status == 2
    assert len(calls) == 1


@pytest.mark.parametrize(
    "admission", ["provider", "amount", "newer_attempt", "signature"]
)
def test_refund_evidence_cannot_settle_an_unadmitted_learner_attempt(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    admission: str,
) -> None:
    app = integration_app
    order, snapshot, reference, calls = _pending_refund(app, monkeypatch)
    with unit_of_work():
        if admission == "provider":
            order.payment_channel = "stripe"
        elif admission == "amount":
            order.paid_price = Decimal("9.00")
        elif admission == "newer_attempt":
            fields = {
                column.key: getattr(snapshot, column.key)
                for column in snapshot.__table__.columns
                if column.key not in {"id", "metadata"}
            }
            fields.update(
                alipay_order_bid="new-refund-attempt",
                provider_attempt_id="new-refund-reference",
                metadata_json="{}",
                status=1,
            )
            dao.db.session.add(FixtureSnapshot(**fields))
    with app.test_client() as client:
        response = _notify(
            client,
            "fixture-pay",
            reference,
            state="refunded",
            signed=admission != "signature",
        )
        assert response.status_code == (400 if admission == "signature" else 200)
    dao.db.session.expire_all()
    assert order.status == ORDER_STATUS_SUCCESS
    assert json.loads(snapshot.metadata_json)["refund_operation"]["status"] == "pending"
    assert len(calls) == 1


@pytest.mark.parametrize("initial", ["pending", "requires_action"])
def test_current_learner_refund_callback_can_finish_before_creation_receipt(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    initial: str,
) -> None:
    app = integration_app
    order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
    reference, bid = snapshot.provider_attempt_id, order.order_bid
    with app.test_client() as client:
        assert _notify(client, "fixture-pay", reference).status_code == 200
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )
    calls = []

    def refund(*_args: object, **_kwargs: object) -> PaymentRefundResult:
        calls.append(True)
        with app.test_client() as client:
            assert (
                _notify(client, "fixture-pay", reference, state="refunded").status_code
                == 200
            )
        return PaymentRefundResult("refund-early", {"status": initial}, initial)

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    for _ in range(2):
        result = funs.refund_order_payment(app, bid)
        assert result["status"] == "succeeded"
        assert result["refund_id"] == "refund-early"
    assert order.status == ORDER_STATUS_REFUND
    assert len(calls) == 1


@pytest.mark.parametrize("terminal", ["failed", "canceled"])
@pytest.mark.parametrize("outcome_source", ["response", "callback"])
def test_terminal_failure_allows_an_explicit_new_refund_with_a_new_key(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
    outcome_source: str,
) -> None:
    app = integration_app
    order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
    reference, bid = snapshot.provider_attempt_id, order.order_bid
    with app.test_client() as client:
        assert _notify(client, "fixture-pay", reference).status_code == 200
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )
    requests = []

    def refund(*_args: object, **kwargs: object) -> PaymentRefundResult:
        requests.append(kwargs["request"])
        if len(requests) == 1:
            status = terminal if outcome_source == "response" else "pending"
            return PaymentRefundResult("refund-rejected", {"status": status}, status)
        return PaymentRefundResult("refund-retry", {"status": "succeeded"}, "succeeded")

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    first = funs.refund_order_payment(app, bid)
    assert first["status"] == (terminal if outcome_source == "response" else "pending")
    if outcome_source == "callback":
        original = FixtureProvider.describe_notification.__func__

        def describe(cls: type, notification: object) -> object:
            return replace(
                original(cls, notification),
                kind="refund",
                refund_status=terminal,
                refund_reference="refund-rejected",
            )

        monkeypatch.setattr(
            FixtureProvider, "describe_notification", classmethod(describe)
        )
        with app.test_client() as client:
            assert (
                _notify(client, "fixture-pay", reference, state="unknown").status_code
                == 200
            )
    assert funs.refund_order_payment(app, bid)["status"] == "succeeded"
    assert len(requests) == 2
    assert (
        requests[0].metadata["idempotency_key"]
        != requests[1].metadata["idempotency_key"]
    )
    assert requests[0].amount == requests[1].amount
    assert funs.refund_order_payment(app, bid)["refund_id"] == "refund-retry"
    assert len(requests) == 2
    assert order.status == ORDER_STATUS_REFUND


@pytest.mark.parametrize("terminal", ["failed", "canceled"])
def test_retried_refund_retains_new_key_after_lost_response_and_ignores_old_events(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    app = integration_app
    order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
    reference, bid = snapshot.provider_attempt_id, order.order_bid
    with app.test_client() as client:
        assert _notify(client, "fixture-pay", reference).status_code == 200
    monkeypatch.setattr(
        FixtureProvider,
        "definition",
        replace(
            FixtureProvider.definition,
            capabilities=replace(FixtureProvider.definition.capabilities, refund=True),
        ),
    )
    original = FixtureProvider.describe_notification.__func__

    def describe(cls: type, notification: object) -> object:
        return replace(
            original(cls, notification),
            kind="refund",
            refund_status=terminal,
            refund_reference="refund-old-failure",
        )

    monkeypatch.setattr(FixtureProvider, "describe_notification", classmethod(describe))
    requests, external = [], {}

    def refund(*_args: object, **kwargs: object) -> PaymentRefundResult:
        request = kwargs["request"]
        requests.append(request)
        if len(requests) == 1:
            return PaymentRefundResult(
                "refund-old-failure", {"status": terminal}, terminal
            )
        result = external.setdefault(
            request.metadata["idempotency_key"],
            PaymentRefundResult("refund-new", {"status": "succeeded"}, "succeeded"),
        )
        if len(requests) == 2:
            with app.test_client() as client:
                assert (
                    _notify(
                        client, "fixture-pay", reference, state="unknown"
                    ).status_code
                    == 200
                )
            message = "Injected loss of the retried refund response"
            raise RuntimeError(message)
        return result

    monkeypatch.setattr(FixtureProvider, "refund_payment", refund)
    assert funs.refund_order_payment(app, bid)["status"] == terminal
    with pytest.raises(RuntimeError, match="Injected loss"):
        funs.refund_order_payment(app, bid)
    assert funs.refund_order_payment(app, bid)["status"] == "succeeded"
    assert (
        requests[0].metadata["idempotency_key"]
        != requests[1].metadata["idempotency_key"]
    )
    assert (
        requests[1].metadata["idempotency_key"]
        == requests[2].metadata["idempotency_key"]
    )
    assert len(external) == 1
    assert order.status == ORDER_STATUS_REFUND
    assert funs.refund_order_payment(app, bid)["refund_id"] == "refund-new"
    assert len(requests) == 3
