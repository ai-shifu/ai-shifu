"""Keep authoritative contract state when asynchronous payment arrives later."""

from copy import deepcopy
from dataclasses import replace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)
from flaskr.service.billing.models import CreditLedgerEntry, CreditWallet
from flaskr.service.order.payment_providers.stripe import StripeProvider

from tests.service.billing.test_contract_identity import _case, _notification
from tests.service.order.test_payment_contract_extension import (
    HostedFixtureProvider,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("provider", ["stripe", "fixture-hosted"])
@pytest.mark.parametrize("upgrade", [False, True])
@pytest.mark.parametrize("source", ["webhook", "query"])
@pytest.mark.parametrize(
    "state", ["active", "trialing", "unknown", "canceled", "paused", "past_due"]
)
@pytest.mark.parametrize("cancel", [False, True])
def test_payment_only_confirmation_preserves_an_earlier_authoritative_contract(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    upgrade: bool,
    source: str,
    state: str,
    cancel: bool,
) -> None:
    app = integration_app
    order, sub = _case(app, provider, upgrade=True)
    if not upgrade:
        with unit_of_work():
            order.order_type = BILLING_ORDER_TYPE_SUBSCRIPTION_START
            sub.status = BILLING_SUBSCRIPTION_STATUS_DRAFT
    contract = _notification(provider, "sub_current", state)
    if provider == "stripe":
        contract.provider_payload["data"]["object"]["cancel_at_period_end"] = cancel
    else:
        contract = replace(
            contract,
            subscription=replace(contract.subscription, cancel_at_period_end=cancel),
        )
    assert (
        webhooks.apply_billing_provider_notification(
            app, provider, contract
        ).status_code
        == 200
    )
    assert order.status == BILLING_ORDER_STATUS_PENDING
    before = (sub.status, sub.cancel_at_period_end)
    assert sub.metadata_json["provider_contract_confirmed"] is True
    metadata = deepcopy(sub.metadata_json)
    if provider == "stripe":
        payment = _notification(
            provider, "sub_current", "active", payment=True, source=source
        )
        adapter = StripeProvider
    else:
        # The hosted transport sends a payment receipt, with no contract facts.
        payment = replace(
            _notification(provider, "sub_current", "active", payment=True),
            subscription=None,
            status="fixture.payment",
        )
        adapter = HostedFixtureProvider
    monkeypatch.setattr(adapter, "sync_reference", lambda *_a, **_k: payment)
    for _ in range(2):
        if source == "query":
            assert (
                checkout.sync_billing_order(
                    app, "creator-1", order.bill_order_bid, {}
                ).status
                == "paid"
            )
        else:
            assert (
                webhooks.apply_billing_provider_notification(
                    app, provider, payment
                ).status_code
                == 200
            )
    dao.db.session.expire_all()
    assert order.status == BILLING_ORDER_STATUS_PAID
    expected_status = (
        (
            BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            if cancel
            else BILLING_SUBSCRIPTION_STATUS_ACTIVE
        )
        if state in {"active", "trialing", "unknown"}
        else before[0]
    )
    assert (sub.status, sub.cancel_at_period_end) == (expected_status, int(cancel))
    assert sub.metadata_json["latest_event_type"] == metadata["latest_event_type"]
    assert sub.metadata_json.get("latest_event_time") == metadata.get(
        "latest_event_time"
    )
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )

    if state == "canceled":
        # Stripe cancellation is terminal; keep its paid bucket unavailable.
        assert (
            CreditWallet.query.filter_by(creator_bid="creator-1")
            .one()
            .available_credits
            == 0
        )
        return
    # Recoverable contracts must still unlock their existing paid grant.
    recovered = _notification(provider, "sub_current", "active")
    assert (
        webhooks.apply_billing_provider_notification(
            app, provider, recovered
        ).status_code
        == 200
    )
    dao.db.session.expire_all()
    assert sub.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
    assert sub.cancel_at_period_end == 0
    assert (
        CreditLedgerEntry.query.filter_by(source_bid=order.bill_order_bid).count() == 1
    )
    assert (
        CreditWallet.query.filter_by(creator_bid="creator-1").one().available_credits
        > 0
    )
