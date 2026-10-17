"""Admit saved refund identities before projecting learner or billing status."""

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
)
from flaskr.service.billing.models import CreditWallet
from flaskr.service.common.models import AppError
from flaskr.service.order import funs, raw_snapshots
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.payment_providers.base import (
    PaymentNotificationResult,
    PaymentRefundResult,
)
from flaskr.service.order.payment_providers.contracts import PaymentFacts

from tests.service.billing.test_contract_identity import _case
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    HostedFixtureProvider,
    _learner_sync_case,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("domain", ["learner", "billing-native", "billing-hosted"])
@pytest.mark.parametrize("source", ["callback", "query"])
@pytest.mark.parametrize("phase", ["pending", "inflight", "lost-response"])
@pytest.mark.parametrize("terminal", ["failed", "canceled"])
@pytest.mark.parametrize("payment_state", ["refunded", "unknown"])
def test_archived_success_cannot_project_a_replacement_refund(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    source: str,
    phase: str,
    terminal: str,
    payment_state: str,
) -> None:
    app = integration_app
    learner = domain == "learner"
    hosted = domain == "billing-hosted"
    provider_name = "fixture-hosted" if hosted else "fixture-pay"
    adapter = HostedFixtureProvider if hosted else FixtureProvider
    if learner:
        order, snapshot, _notifications = _learner_sync_case(app, monkeypatch)
        bid, reference = order.order_bid, snapshot.provider_attempt_id
        with app.test_client() as client:
            assert _notify(client, provider_name, reference).status_code == 200
        sub = wallet = None
    else:
        if hosted:
            monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, provider_name)
            monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, provider_name)
        order, sub = _case(app, provider_name)
        bid, reference = order.bill_order_bid, order.provider_reference_id
        snapshot = (
            None
            if hosted
            else FixtureSnapshot.query.filter_by(bill_order_bid=bid).one()
        )
        wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
    balance = wallet.available_credits if wallet else None
    monkeypatch.setattr(
        adapter,
        "definition",
        replace(
            adapter.definition,
            capabilities=replace(adapter.definition.capabilities, refund=True),
        ),
    )
    current = {"reference": "re_old", "status": "succeeded"}
    notice = PaymentNotificationResult(
        reference if learner else bid,
        "fixture.refund",
        {"refund": "old-success"},
        facts=PaymentFacts(
            state=payment_state,
            provider_reference=reference,
            order_amount=1000 if learner else 9900,
            currency="CNY",
        ),
    )
    monkeypatch.setattr(adapter, "sync_reference", Mock(return_value=notice))

    def metadata() -> dict:
        return json.loads(snapshot.metadata_json) if learner else order.metadata_json

    def deliver() -> None:
        # Exercise the shared default event producer, not an adapter override
        # that conceals missing fields in the notification/query contract.
        notice.refund_reference = current["reference"]
        notice.refund_status = current["status"]
        if source == "query":
            if learner:
                funs.sync_native_payment_order(app, bid, expected_user="creator-1")
            else:
                checkout.sync_billing_order(app, "creator-1", bid, {})
        elif learner:
            funs.success_buy_record_from_native(app, provider_name, notice)
        else:
            webhooks.apply_billing_native_notification(app, provider_name, notice)

    def execute() -> object:
        if learner:
            return funs.refund_order_payment(app, bid)
        return checkout.refund_billing_order(app, "creator-1", bid, {})

    requests, external = [], {}

    def refund(*_args: object, **kwargs: object) -> PaymentRefundResult:
        request = kwargs["request"]
        requests.append(request)
        if len(requests) == 1:
            return PaymentRefundResult("re_old", {}, terminal)
        result = external.setdefault(
            request.metadata["idempotency_key"],
            PaymentRefundResult("re_new", {}, "pending"),
        )
        if phase != "pending":
            assert_rejected()
        if phase == "lost-response" and len(requests) == 2:
            message = "Injected lost replacement response"
            raise RuntimeError(message)
        return result

    def assert_unsettled(before_snapshot: int | None) -> None:
        assert order.status == (
            ORDER_STATUS_SUCCESS if learner else BILLING_ORDER_STATUS_PAID
        )
        if snapshot:
            assert snapshot.status == before_snapshot
        if learner:
            assert funs.get_payment_details(app, bid)["status"] == before_snapshot
        else:
            assert order.refunded_at is None
            assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert wallet.available_credits == balance

    def assert_rejected() -> None:
        before = deepcopy(metadata()["refund_operation"])
        before_snapshot = snapshot.status if snapshot else None
        for _ in range(2):
            deliver()
            dao.db.session.expire_all()
            assert metadata()["refund_operation"] == before
            assert_unsettled(before_snapshot)

    rpc = Mock(side_effect=refund)
    monkeypatch.setattr(adapter, "refund_payment", rpc)
    if learner:
        assert execute()["status"] == terminal
    else:
        with pytest.raises(AppError):
            execute()
    if phase == "lost-response":
        with pytest.raises(RuntimeError, match="Injected lost"):
            execute()
    execute()
    assert_rejected()
    assert len(external) == 1
    assert (
        requests[0].metadata["idempotency_key"]
        != requests[1].metadata["idempotency_key"]
    )
    if phase == "lost-response":
        assert requests[1] == requests[2]
    # A payment-level reversal without a refund identity cannot claim a retry.
    current["reference"] = ""
    assert_rejected()
    current["reference"] = "re_new"
    before_snapshot = snapshot.status if snapshot else None
    # Even contradictory payment facts must not settle a non-final refund.
    for progress in ["pending", "requires_action", "unknown"]:
        current["status"] = progress
        for _ in range(2):
            deliver()
            dao.db.session.expire_all()
            assert_unsettled(before_snapshot)
            if progress != "unknown":
                assert metadata()["refund_operation"]["response"]["status"] == progress
    current["status"] = "succeeded"
    if phase == "pending" and terminal == "failed":
        owner, writer_name = (
            (funs, "_apply_native_snapshot_update")
            if learner
            else (checkout, "persist_query")
            if source == "query"
            else (webhooks, "persist_provider_notification")
        )
        original_writer = getattr(owner, writer_name)
        before = deepcopy(metadata()["refund_operation"])

        def fail_after_write(*args: object, **kwargs: object) -> None:
            original_writer(*args, **kwargs)
            message = "Injected registered refund projection failure"
            raise RuntimeError(message)

        with monkeypatch.context() as patch:
            patch.setattr(owner, writer_name, fail_after_write)
            with pytest.raises(RuntimeError, match="Injected registered refund"):
                deliver()
        dao.db.session.expire_all()
        assert metadata()["refund_operation"] == before
        assert_unsettled(before_snapshot)
    for _ in range(2):
        deliver()
        dao.db.session.expire_all()
        assert order.status == (
            ORDER_STATUS_REFUND if learner else BILLING_ORDER_STATUS_REFUNDED
        )
        assert (
            metadata()["refund_operation"]["response"]["provider_reference"] == "re_new"
        )
        if snapshot:
            assert snapshot.status == 2
        if not learner:
            assert sub.status == BILLING_SUBSCRIPTION_STATUS_CANCELED
            assert wallet.available_credits == 0
    calls = rpc.call_count
    execute()
    assert rpc.call_count == calls
