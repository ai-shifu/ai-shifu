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


def _seed_pending_topup_order(
    app: object,
    *,
    payment_provider: str = "pingxx",
    channel: str = "alipay_qr",
    provider_reference_id: str = "",
) -> tuple[str, str]:
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
                    payment_provider=payment_provider,
                    channel=channel,
                    provider_reference_id=provider_reference_id,
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


def _install_sync_provider(
    monkeypatch: object, provider_payload: dict[str, object]
) -> None:
    def sync_reference(
        *, provider_reference: str, reference_type: str, app: object
    ) -> object:
        _ = (provider_reference, reference_type, app)
        return SimpleNamespace(provider_payload=provider_payload)

    monkeypatch.setattr(
        checkout,
        "get_payment_provider",
        lambda _name: SimpleNamespace(sync_reference=sync_reference),
    )


def _seed_expired_stripe_checkout_order(app: object, session_id: str) -> str:
    from datetime import timedelta

    from flaskr.util.datetime import now_utc

    bill_order_bid, _product_bid = _seed_pending_topup_order(
        app,
        payment_provider="stripe",
        channel="checkout_session",
        provider_reference_id=session_id,
    )
    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
        order.expires_at = now_utc() - timedelta(minutes=5)
        dao.db.session.commit()
    return bill_order_bid


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


def test_a_late_charge_snapshot_is_recorded_as_pending(
    app: object, monkeypatch: object
) -> None:
    """The charge is pending even when the order it belongs to is settled."""
    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_PAID
    from flaskr.service.common.models import AppError
    from flaskr.service.order.models import PingxxOrder

    bill_order_bid, _product_bid = _seed_pending_topup_order(app)

    def create_payment(*, request: object, app: object) -> object:
        _ = request
        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            order.status = BILLING_ORDER_STATUS_PAID
            dao.db.session.commit()
        return SimpleNamespace(
            provider_reference="ch_late_snapshot",
            raw_response={"id": "ch_late_snapshot"},
            checkout_session_id=None,
            extra={},
        )

    _install_provider(monkeypatch, create_payment)

    with pytest.raises(AppError):
        checkout.create_billing_order_checkout(
            app, _CREATOR, bill_order_bid, {"channel": "alipay_qr"}
        )

    with app.app_context():
        snapshot = (
            PingxxOrder.query.filter_by(
                biz_domain="billing", bill_order_bid=bill_order_bid
            )
            .order_by(PingxxOrder.id.desc())
            .first()
        )
        assert snapshot.charge_id == "ch_late_snapshot"
        # Pending (0), not the settled order's paid status (1).
        assert int(snapshot.status or 0) == 0


def test_an_expired_topup_leaves_pending_after_a_sync(app: object) -> None:
    """The timeout scan must not keep re-selecting a failed top-up attempt."""
    from datetime import timedelta

    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_TIMEOUT
    from flaskr.util.datetime import now_utc

    bill_order_bid, _product_bid = _seed_pending_topup_order(app)
    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
        order.expires_at = now_utc() - timedelta(minutes=5)
        dao.db.session.commit()

    checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_TIMEOUT


def test_an_abandoned_stripe_checkout_times_out(
    app: object, monkeypatch: object
) -> None:
    """A checkout the buyer never opened must still reach a terminal state.

    Stripe creates no PaymentIntent until the buyer starts paying, so the
    timeout scan reads a session that carries no metadata at all. That is
    absence of payment, not evidence of a mismatched order, and it must not
    stop the order from expiring.
    """
    from flaskr.service.billing.consts import BILLING_ORDER_STATUS_TIMEOUT

    session_id = "cs_test_abandoned_checkout"
    bill_order_bid = _seed_expired_stripe_checkout_order(app, session_id)
    _install_sync_provider(
        monkeypatch,
        {
            "checkout_session": {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
                "metadata": {},
                "payment_intent": None,
            },
            "payment_intent": {},
        },
    )

    checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_TIMEOUT


def test_a_paid_stripe_checkout_without_evidence_is_refused(
    app: object, monkeypatch: object
) -> None:
    """A session that claims to be paid must still prove whose order it is."""
    from flaskr.service.common.models import AppError

    session_id = "cs_test_paid_without_evidence"
    bill_order_bid = _seed_expired_stripe_checkout_order(app, session_id)
    _install_sync_provider(
        monkeypatch,
        {
            "checkout_session": {
                "id": session_id,
                "status": "complete",
                "payment_status": "paid",
                "metadata": {},
                "payment_intent": "pi_paid_without_evidence",
            },
            "payment_intent": {
                "id": "pi_paid_without_evidence",
                "status": "succeeded",
                "metadata": {},
            },
        },
    )

    with pytest.raises(AppError):
        checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PENDING


def test_a_stripe_checkout_belonging_to_another_order_is_refused(
    app: object, monkeypatch: object
) -> None:
    """Metadata that names a different order is a mismatch, not absence."""
    from flaskr.service.common.models import AppError

    session_id = "cs_test_foreign_metadata"
    bill_order_bid = _seed_expired_stripe_checkout_order(app, session_id)
    _install_sync_provider(
        monkeypatch,
        {
            "checkout_session": {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
                "metadata": {"bill_order_bid": "some-other-order"},
                "payment_intent": None,
            },
            "payment_intent": {},
        },
    )

    with pytest.raises(AppError):
        checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PENDING


def test_an_unpaid_stripe_checkout_naming_another_creator_is_refused(
    app: object, monkeypatch: object
) -> None:
    """Partial evidence pointing elsewhere is a mismatch, not absence.

    Metadata with no bill_order_bid is treated as "Stripe attached nothing
    yet", but whatever identity it does carry still has to match this order,
    otherwise the order would be expired on the strength of someone else's
    session.
    """
    from flaskr.service.common.models import AppError

    session_id = "cs_test_foreign_creator"
    bill_order_bid = _seed_expired_stripe_checkout_order(app, session_id)
    _install_sync_provider(
        monkeypatch,
        {
            "checkout_session": {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
                "metadata": {"creator_bid": "some-other-creator"},
                "payment_intent": None,
            },
            "payment_intent": {},
        },
    )

    with pytest.raises(AppError):
        checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PENDING


def test_an_unpaid_stripe_checkout_naming_another_product_is_refused(
    app: object, monkeypatch: object
) -> None:
    """The same holds for a product that belongs to a different order."""
    from flaskr.service.common.models import AppError

    session_id = "cs_test_foreign_product"
    bill_order_bid = _seed_expired_stripe_checkout_order(app, session_id)
    _install_sync_provider(
        monkeypatch,
        {
            "checkout_session": {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
                "metadata": {},
                "payment_intent": None,
            },
            "payment_intent": {"metadata": {"product_bid": "some-other-product"}},
        },
    )

    with pytest.raises(AppError):
        checkout.sync_billing_order(app, _CREATOR, bill_order_bid, {})

    persisted = _committed_order(app, bill_order_bid)
    assert persisted.status == BILLING_ORDER_STATUS_PENDING
