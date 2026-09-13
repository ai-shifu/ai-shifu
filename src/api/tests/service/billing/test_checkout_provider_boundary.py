"""The payment provider must be called with no transaction open.

The order row has to be durable before the charge is created: a webhook or a
reconcile that resolves the order by its bid must always find it, and a
provider failure must leave a retryable pending order instead of a charge with
no local row.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr import dao
from flaskr.service.billing import checkout
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_MODE_ONE_TIME,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingOrder, BillingProduct

_CREATOR = "checkout-boundary-creator"


def _committed_order(app: object, bill_order_bid: str) -> object:
    """Read through a separate connection: only committed state is visible."""
    with app.app_context(), dao.db.engine.connect() as connection:
        return connection.execute(
            BillingOrder.__table__.select().where(
                BillingOrder.bill_order_bid == bill_order_bid
            )
        ).first()


def _seed_pending_topup_order(app: object) -> tuple[str, str]:
    bill_order_bid = f"checkout-boundary-{uuid.uuid4().hex[:12]}"
    product_bid = f"product-{uuid.uuid4().hex[:12]}"
    with app.app_context():
        dao.db.session.add_all(
            [
                BillingProduct(
                    product_bid=product_bid,
                    product_code=f"topup-{uuid.uuid4().hex[:6]}",
                    product_type=BILLING_PRODUCT_TYPE_TOPUP,
                    billing_mode=BILLING_MODE_ONE_TIME,
                    billing_interval=0,
                    billing_interval_count=0,
                    display_name_i18n_key="billing.product.topup",
                    description_i18n_key="billing.product.topup.description",
                    currency="CNY",
                    price_amount=100,
                    credit_amount=Decimal("100.0000000000"),
                    allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
                    auto_renew_enabled=0,
                    status=BILLING_PRODUCT_STATUS_ACTIVE,
                ),
                BillingOrder(
                    bill_order_bid=bill_order_bid,
                    creator_bid=_CREATOR,
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid=product_bid,
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=100,
                    paid_amount=0,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="",
                    status=BILLING_ORDER_STATUS_PENDING,
                    metadata_json={},
                ),
            ]
        )
        dao.db.session.commit()
    return bill_order_bid, product_bid


def _install_provider(monkeypatch: object, create_payment: object) -> None:
    monkeypatch.setattr(
        checkout,
        "get_payment_provider",
        lambda _name: SimpleNamespace(create_payment=create_payment),
    )


def test_the_order_is_committed_before_the_provider_is_called(
    app: object, monkeypatch: object
) -> None:
    bill_order_bid, _product_bid = _seed_pending_topup_order(app)
    seen: list[object] = []

    def create_payment(*, request: object, app: object) -> object:
        _ = request
        seen.append(_committed_order(app, bill_order_bid))
        return SimpleNamespace(
            provider_reference="ch_boundary_1",
            raw_response={"id": "ch_boundary_1"},
            checkout_session_id=None,
            extra={},
        )

    _install_provider(monkeypatch, create_payment)

    checkout.create_billing_order_checkout(
        app, _CREATOR, bill_order_bid, {"channel": "alipay_qr"}
    )

    assert len(seen) == 1
    # Visible to another connection, and still without a provider reference.
    assert seen[0] is not None
    assert seen[0].status == BILLING_ORDER_STATUS_PENDING
    assert not seen[0].provider_reference_id

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.provider_reference_id == "ch_boundary_1"


def test_a_provider_failure_leaves_a_retryable_pending_order(
    app: object, monkeypatch: object
) -> None:
    bill_order_bid, _product_bid = _seed_pending_topup_order(app)

    def failing_create_payment(*, request: object, app: object) -> object:
        _ = (request, app)
        message = "provider down"
        raise RuntimeError(message)

    _install_provider(monkeypatch, failing_create_payment)

    with pytest.raises(RuntimeError, match="provider down"):
        checkout.create_billing_order_checkout(
            app, _CREATOR, bill_order_bid, {"channel": "alipay_qr"}
        )

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PENDING
    assert not persisted.provider_reference_id


def test_a_settled_order_never_points_at_a_late_charge(
    app: object, monkeypatch: object
) -> None:
    """A callback can settle the order while the charge is being created.

    The new charge must stay reconcilable through its raw snapshot, but the
    settled order must not be pointed at it.
    """
    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_PAID
    from flaskr.service.common.models import AppError

    bill_order_bid, _product_bid = _seed_pending_topup_order(app)

    def create_payment(*, request: object, app: object) -> object:
        _ = request
        # The webhook lands while we are talking to the provider.
        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            order.status = BILLING_ORDER_STATUS_PAID
            dao.db.session.commit()
        return SimpleNamespace(
            provider_reference="ch_boundary_late",
            raw_response={"id": "ch_boundary_late"},
            checkout_session_id=None,
            extra={},
        )

    _install_provider(monkeypatch, create_payment)

    with pytest.raises(AppError):
        checkout.create_billing_order_checkout(
            app, _CREATOR, bill_order_bid, {"channel": "alipay_qr"}
        )

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PAID
    assert not persisted.provider_reference_id


def test_a_topup_order_carries_a_deadline(app: object, monkeypatch: object) -> None:
    """A committed top-up must be able to time out if the provider call fails."""
    from flaskr.service.billing import checkout as checkout_module

    product_bid = _seed_pending_topup_order(app)[1]
    monkeypatch.setattr(
        checkout_module, "_load_effective_topup_subscription", lambda _bid: object()
    )

    def failing_create_payment(*, request: object, app: object) -> object:
        _ = (request, app)
        message = "provider down"
        raise RuntimeError(message)

    _install_provider(monkeypatch, failing_create_payment)

    with pytest.raises(RuntimeError, match="provider down"):
        checkout.create_billing_topup_checkout(
            app, _CREATOR, {"product_bid": product_bid, "channel": "alipay_qr"}
        )

    with app.app_context():
        order = (
            BillingOrder.query.filter_by(creator_bid=_CREATOR, product_bid=product_bid)
            .order_by(BillingOrder.id.desc())
            .first()
        )
        assert order.status == BILLING_ORDER_STATUS_PENDING
        assert order.expires_at is not None
