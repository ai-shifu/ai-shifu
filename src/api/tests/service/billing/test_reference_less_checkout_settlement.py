"""Keep a settled checkout addressable when its callback precedes creation."""

import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.billing import checkout, provider_recovery, provider_snapshots
from flaskr.service.billing.consts import BILLING_ORDER_STATUS_PAID
from flaskr.service.billing.models import BillingOrder, CreditLedgerEntry
from flaskr.service.common.models import AppError
from flaskr.service.order import raw_snapshots
from flaskr.service.order.payment_providers.base import PaymentRefundResult

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    FixtureSnapshot,
    HostedFixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("integration_app", ["file"], indirect=True)
@pytest.mark.parametrize("storage", ["native", "metadata", "writer"])
@pytest.mark.parametrize("reported", [False, True])
def test_early_paid_callback_retains_the_same_checkout_operational_reference(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    storage: str,
    reported: bool,
) -> None:
    app = integration_app
    add_active_subscription(app)
    adapter = FixtureProvider if storage == "native" else HostedFixtureProvider
    provider = adapter.channel
    if storage != "native":
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_MODELS, provider)
        monkeypatch.delitem(raw_snapshots._NATIVE_PAYMENT_BID_ATTRS, provider)
    monkeypatch.setattr(
        adapter,
        "definition",
        replace(
            adapter.definition,
            capabilities=replace(adapter.definition.capabilities, refund=True),
        ),
    )
    receipts, errors = [], []
    if storage == "writer":
        monkeypatch.setattr(provider_snapshots, "_CHECKOUT_WRITERS", {})

        def writer(order: BillingOrder, result: object, **kwargs: object) -> None:
            receipts.append((order.provider_reference_id, result, kwargs))

        provider_snapshots.register_checkout_writer(provider, writer)
    original = adapter.create_payment

    def create(self: FixtureProvider, **kwargs: object) -> object:
        result = original(self, **kwargs)
        bid = kwargs["request"].order_bid
        reference = f"gateway-{bid}"
        payload = self.attempts[bid]
        payload["trade"] = {
            **payload,
            "state": "paid",
            "reference": reference if reported else None,
        }
        self.attempts[reference] = payload

        def callback() -> None:
            try:
                with app.test_client() as client:
                    assert _notify(client, provider, bid).status_code == 200
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=callback, daemon=True)
        worker.start()
        worker.join(5)
        assert not worker.is_alive()
        assert errors == []
        return replace(result, provider_reference=reference)

    monkeypatch.setattr(adapter, "create_payment", create)
    with (
        app.test_request_context(base_url="https://fixture.test"),
        pytest.raises(AppError),
    ):
        checkout.create_billing_topup_checkout(
            app,
            "creator-1",
            {
                "product_bid": "bill-product-topup-small",
                "payment_option": f"{provider}:{adapter.definition.default_channel}",
            },
        )
    dao.db.session.expire_all()
    order = BillingOrder.query.filter_by(payment_provider=provider).one()
    bid = order.bill_order_bid
    reference = f"gateway-{bid}"
    assert order.status == BILLING_ORDER_STATUS_PAID
    assert order.provider_reference_id == reference
    assert provider_recovery.stored_checkout_reference(order) == reference
    assert "payment_action" not in order.metadata_json
    assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == 1
    if storage == "native":
        snapshot = FixtureSnapshot.query.filter_by(bill_order_bid=bid).one()
        assert snapshot.provider_attempt_id == reference
        assert snapshot.status == 1
    elif storage == "metadata":
        receipt = order.metadata_json["provider_checkout_attempts"][0]
        assert receipt["result"]["provider_reference"] == reference
        assert receipt["status"] == 1
    else:
        assert len(receipts) == 1
        assert receipts[0][0] == reference
        assert receipts[0][2]["raw_snapshot_status"] == 1

    # Queries must still independently identify their payment. Missing callback
    # identity is not permission to weaken query association validation.
    FixtureProvider.attempts[reference]["trade"]["reference"] = reference
    for _ in range(2):
        assert checkout.sync_billing_order(app, "creator-1", bid, {}).status == "paid"
        assert CreditLedgerEntry.query.filter_by(source_bid=bid).count() == 1
    assert ("query", reference) in FixtureProvider.calls
    # Reopening a paid checkout never exposes its stale QR/redirect action.
    with (
        app.test_request_context(base_url="https://fixture.test"),
        pytest.raises(AppError),
    ):
        checkout.create_billing_order_checkout(app, "creator-1", bid, {})
    refund = Mock(return_value=PaymentRefundResult("refund-current", {}, "succeeded"))
    monkeypatch.setattr(adapter, "refund_payment", refund)
    assert checkout.refund_billing_order(app, "creator-1", bid, {}).status == "refunded"
    assert (
        refund.call_args.kwargs["request"].metadata["provider_reference"] == reference
    )
    assert order.provider_reference_id == reference
