"""Exercise hosted integrations without native raw tables through real entry points."""

from dataclasses import replace

import pytest
from flask import Flask
from flaskr.service.billing import checkout, provider_snapshots
from flaskr.service.billing.consts import BILLING_ORDER_STATUS_CANCELED
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry
from flaskr.service.common.models import AppError
from flaskr.service.order import raw_snapshots

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    HostedFixtureProvider,
    HostedFixtureSnapshot,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("source", ["webhook", "query"])
@pytest.mark.parametrize("custom_writer", [False, True])
@pytest.mark.parametrize("state", ["pending", "paid", "refunded"])
def test_hosted_billing_settles_without_native_snapshot_registration(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    custom_writer: bool,
    state: str,
) -> None:
    app = integration_app
    add_active_subscription(app)
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities,
                query=source == "query",
                poll_provider=False,
            ),
        ),
    )
    writes = []
    if custom_writer:
        attribute = "_QUERY_WRITERS" if source == "query" else "_NOTIFICATION_WRITERS"
        monkeypatch.setattr(
            provider_snapshots, attribute, dict(getattr(provider_snapshots, attribute))
        )
        register = (
            provider_snapshots.register_query_writer
            if source == "query"
            else provider_snapshots.register_notification_writer
        )
        register("fixture-hosted", lambda *_args: writes.append(source))
    with app.test_client() as client:
        created = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
        assert created["code"] == 0, created
        reference = created["data"]["bill_order_bid"]
        assert (
            _notify(client, "fixture-hosted", reference, signed=False).status_code
            == 400
        )
        states = ["paid", "refunded"] if state == "refunded" else [state]
        for expected in states:
            FixtureProvider.attempts[reference]["state"] = expected
            for _ in range(2):
                if source == "webhook":
                    assert (
                        _notify(
                            client, "fixture-hosted", reference, state=expected
                        ).status_code
                        == 200
                    )
                else:
                    response = client.post(
                        f"/api/billing/orders/{reference}/sync", json={}
                    ).get_json(force=True)
                    assert response["code"] == 0, response
                    assert response["data"]["status"] == expected
        order = BillingOrder.query.filter_by(bill_order_bid=reference).one()
        grants = CreditLedgerEntry.query.filter_by(source_bid=reference).count()
        assert grants == int(state != "pending")
        assert HostedFixtureSnapshot.query.count() == 0
        if custom_writer:
            assert len(writes) == len(states) * 2
        else:
            key = (
                "last_provider_query"
                if source == "query"
                else "last_provider_notification"
            )
            assert order.metadata_json[key]["state"] == state


def test_unmatched_signed_hosted_callback_is_rejected_without_learner_fallback(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
    monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    FixtureProvider.attempts["unknown-hosted"] = {
        "state": "paid",
        "reference": "unknown-hosted",
        "amount": 100,
        "currency": "CNY",
    }
    with integration_app.test_client() as client:
        response = _notify(client, "fixture-hosted", "unknown-hosted")
        assert response.status_code == 400
        assert response.get_json(force=True)["code"] == "FAIL"
    assert BillingOrder.query.count() == 0


@pytest.mark.parametrize("native_storage", [False, True])
@pytest.mark.parametrize("can_close", [False, True])
def test_successful_close_does_not_require_an_unsupported_query(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    native_storage: bool,
    can_close: bool,
) -> None:
    app = integration_app
    add_active_subscription(app)
    if not native_storage:
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, "fixture-hosted")
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, "fixture-hosted")
    monkeypatch.setattr(
        HostedFixtureProvider,
        "definition",
        replace(
            HostedFixtureProvider.definition,
            capabilities=replace(
                HostedFixtureProvider.definition.capabilities,
                query=False,
                close=can_close,
            ),
        ),
    )
    calls = []
    original = HostedFixtureProvider.cancel_payment

    def close(self: HostedFixtureProvider, **kwargs: object) -> object:
        calls.append(kwargs["provider_reference"])
        return original(self, **kwargs)

    def query(*_args: object, **_kwargs: object) -> None:
        message = "Unsupported query was called"
        raise AssertionError(message)

    monkeypatch.setattr(HostedFixtureProvider, "cancel_payment", close)
    monkeypatch.setattr(HostedFixtureProvider, "sync_reference", query)
    with app.test_client() as client:
        created = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-hosted:fixture_checkout",
            },
        ).get_json(force=True)
    assert created["code"] == 0, created
    bid = created["data"]["bill_order_bid"]
    if not can_close:
        with pytest.raises(AppError):
            checkout._close_manual_payment_before_replacement(app, "creator-1", bid)
        assert calls == []
        return
    for _ in range(2):
        checkout._close_manual_payment_before_replacement(app, "creator-1", bid)
    order = BillingOrder.query.filter_by(bill_order_bid=bid).one()
    assert order.status == BILLING_ORDER_STATUS_CANCELED
    assert calls == [bid]
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == 0
    if native_storage:
        assert HostedFixtureSnapshot.query.one().status == 3
    else:
        assert order.metadata_json["latest_payment_state"] == "canceled"
