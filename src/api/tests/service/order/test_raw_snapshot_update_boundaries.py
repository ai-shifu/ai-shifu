"""Verify provider snapshots preserve domain isolation and terminal payment evidence."""

import json
from collections.abc import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.order import raw_snapshots as snapshots
from flaskr.service.order.models import PingxxOrder, StripeOrder


@pytest.fixture
def snapshot_scope(app: object) -> Iterator[None]:
    with app.app_context():
        yield
        db.session.rollback()


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
@pytest.mark.parametrize("lookup", ["order_bid", "bill_order_bid"])
@pytest.mark.parametrize("stored_metadata", ["broken", "[]", ""])
def test_native_update_ignores_other_domains_and_tombstones_and_preserves_refund(
    snapshot_scope: None, provider: str, lookup: str, stored_metadata: str
) -> None:
    del snapshot_scope
    model = snapshots.native_snapshot_model(provider)
    bid_attr = snapshots.native_snapshot_bid_attr(provider)
    identifier = uuid4().hex
    domain = "order" if lookup == "order_bid" else "billing"
    rows = []
    for row_domain, deleted in [
        (domain, 0),
        ("billing" if domain == "order" else "order", 0),
        (domain, 1),
    ]:
        row = model(
            **{bid_attr: uuid4().hex, lookup: identifier},
            provider_attempt_id=uuid4().hex,
            biz_domain=row_domain,
            deleted=deleted,
            amount=500,
            currency="CNY",
            status=2,
            raw_status="REFUNDED",
            raw_request="",
            raw_response="",
            raw_notification="",
            metadata_json=stored_metadata,
        )
        rows.append(row)
        db.session.add(row)
        db.session.flush()
    current, foreign, deleted = rows

    result = snapshots.upsert_native_snapshot(
        biz_domain=domain,
        payment_provider=provider,
        provider_attempt_id="",
        amount=None,
        currency="",
        raw_status="PENDING",
        raw_snapshot_status=0,
        metadata=["replacement"],
        **{lookup: identifier},
    )
    db.session.flush()

    assert result is current
    assert current.amount == 500
    assert current.currency == "CNY"
    assert current.status == 2
    assert current.raw_status == "REFUNDED"
    assert (current.raw_request, current.raw_response, current.raw_notification) == (
        "{}",
        "{}",
        "{}",
    )
    assert json.loads(current.metadata_json) == ["replacement"]
    for ignored in (foreign, deleted):
        assert ignored.metadata_json == stored_metadata
        assert ignored.raw_request == ""
    assert model.query.filter(getattr(model, lookup) == identifier).count() == 3


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_native_snapshot_requires_identity_and_initializes_absent_metadata(
    snapshot_scope: None, provider: str
) -> None:
    del snapshot_scope
    arguments = {
        "biz_domain": "order",
        "payment_provider": provider,
        "provider_attempt_id": "",
        "amount": 0,
        "currency": "CNY",
        "raw_status": "CREATED",
        "raw_snapshot_status": 0,
    }
    with pytest.raises(ValueError, match="requires a stable identifier"):
        snapshots.upsert_native_snapshot(**arguments)
    model = snapshots.native_snapshot_model(provider)
    row = model(
        **{snapshots.native_snapshot_bid_attr(provider): uuid4().hex},
        provider_attempt_id=uuid4().hex,
        metadata_json="",
    )
    db.session.add(row)
    db.session.flush()
    arguments["provider_attempt_id"] = row.provider_attempt_id
    assert snapshots.upsert_native_snapshot(**arguments) is row
    assert row.metadata_json == "{}"


@pytest.mark.parametrize(
    "resolver", [snapshots.native_snapshot_model, snapshots.native_snapshot_bid_attr]
)
def test_unknown_native_provider_cannot_select_snapshot_storage(
    resolver: object,
) -> None:
    with pytest.raises(ValueError, match="Unsupported native payment provider"):
        resolver("unknown")


def test_billing_stripe_update_repairs_blank_raw_payloads_without_touching_legacy_rows(
    snapshot_scope: None,
) -> None:
    del snapshot_scope
    bid = uuid4().hex
    legacy = StripeOrder(
        biz_domain="order",
        bill_order_bid=bid,
        checkout_session_object="legacy",
        payment_intent_object="legacy",
        metadata_json="legacy",
    )
    billing = StripeOrder(
        biz_domain="billing",
        bill_order_bid=bid,
        checkout_session_object="",
        payment_intent_object="",
        metadata_json="invalid legacy JSON",
    )
    db.session.add_all([legacy, billing])
    db.session.flush()
    result = snapshots.upsert_billing_stripe_snapshot(
        bill_order_bid=bid,
        creator_bid="teacher",
        amount=200,
        currency="USD",
        raw_status=1,
        metadata=SimpleNamespace(to_dict=lambda: {"fresh": True}),
    )
    db.session.flush()
    assert result is billing
    assert billing.checkout_session_object == "{}"
    assert billing.payment_intent_object == "{}"
    assert json.loads(billing.metadata_json) == {"fresh": True}
    assert billing.amount == 200
    assert legacy.metadata_json == "legacy"
    assert legacy.checkout_session_object == "legacy"


@pytest.mark.parametrize(
    "charge", [None, {"id": "not-a-charge", "app": "app-test", "channel": "alipay_qr"}]
)
def test_billing_pingxx_update_preserves_identifiers_and_initializes_legacy_payloads(
    snapshot_scope: None, charge: dict | None
) -> None:
    del snapshot_scope
    bid = uuid4().hex
    row = PingxxOrder(
        biz_domain="billing",
        bill_order_bid=bid,
        charge_id="ch-stored",
        transaction_no="stored-order",
        app_id="stored-app",
        extra="",
        charge_object="",
    )
    db.session.add(row)
    db.session.flush()
    result = snapshots.upsert_billing_pingxx_snapshot(
        bill_order_bid=bid,
        creator_bid="teacher",
        amount=200,
        currency="CNY",
        raw_status=1,
        charge_object=charge,
    )
    db.session.flush()
    assert result is row
    assert row.charge_id == "ch-stored"
    assert row.transaction_no == "stored-order"
    assert row.extra == "{}"
    assert row.app_id == ("app-test" if charge else "stored-app")
    assert json.loads(row.charge_object) == (charge or {})
