"""A webhook that fails mid-flow must leave the order untouched.

Provider notifications stage several writes (order status, raw snapshot,
subscription activation) in one unit of work and dispatch the order-update
side effects from ``on_commit``. A failure after the first writes has to roll
all of them back and fire nothing.
"""

from __future__ import annotations

import pytest
from flask import Flask
from flaskr import dao
from flaskr.route.callback import register_callback_handler
from flaskr.service.billing import webhooks
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.service.billing.provider_state import BillingOrderProviderUpdateResult
from flaskr.service.order.models import AlipayOrder

from tests.service.billing.test_billing_callbacks import (
    _alipay_notification,
    _create_active_subscription,
    _create_billing_native_raw_snapshot,
    _create_native_billing_order,
    build_bill_products,
)

_ORDER_BID = "bill-alipay-uow-failure"


def _paid_notification() -> object:
    return _alipay_notification(_ORDER_BID, "TRADE_SUCCESS")


@pytest.fixture
def webhook_app() -> object:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    register_callback_handler(app, "/api/callback")
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_pending_alipay_order(app: object) -> None:
    with app.app_context():
        dao.db.session.add_all(
            [
                _create_active_subscription(),
                _create_native_billing_order(_ORDER_BID, "alipay", _ORDER_BID),
                _create_billing_native_raw_snapshot("alipay", _ORDER_BID, _ORDER_BID),
            ]
        )
        dao.db.session.commit()


def test_native_webhook_failure_rolls_back_and_dispatches_nothing(
    webhook_app: object, monkeypatch: object
) -> None:
    dispatched: list[str] = []
    _seed_pending_alipay_order(webhook_app)

    def failing_stage(*_args: object, **_kwargs: object) -> None:
        message = "stage boom"
        raise RuntimeError(message)

    # Fails after the paid status and the raw snapshot have been staged.
    monkeypatch.setattr(
        BillingOrderProviderUpdateResult, "stage_after_state_changes", failing_stage
    )
    monkeypatch.setattr(
        BillingOrderProviderUpdateResult,
        "dispatch_after_commit",
        lambda *_a, **_k: dispatched.append("dispatched"),
    )

    with pytest.raises(RuntimeError, match="stage boom"):
        webhooks.apply_billing_native_notification(
            webhook_app, "alipay", _paid_notification()
        )

    with webhook_app.app_context():
        dao.db.session.expire_all()
        order = BillingOrder.query.filter_by(bill_order_bid=_ORDER_BID).one()
        raw_order = AlipayOrder.query.filter_by(
            biz_domain="billing", bill_order_bid=_ORDER_BID
        ).one()
        assert order.status == BILLING_ORDER_STATUS_PENDING
        assert not order.paid_at
        # The raw snapshot is staged in the same unit of work and rolls back
        # with it: its status and raw status are as seeded.
        assert int(raw_order.status or 0) == 0
        assert raw_order.raw_status == "pending"
    assert dispatched == []


def test_native_webhook_dispatches_only_after_the_paid_status_is_durable(
    webhook_app: object, monkeypatch: object
) -> None:
    seen_status: list[int] = []
    open_transactions: list[bool] = []
    _seed_pending_alipay_order(webhook_app)

    def record_dispatch(*_a: object, **_k: object) -> None:
        # This fixture runs on an in-memory SQLite database, where every
        # connection is the same underlying one, so reading through a second
        # connection could not tell committed from staged rows. What makes the
        # paid status durable here is that the unit of work has already
        # unwound, which is what `on_commit` guarantees.
        from flaskr.dao import uow

        open_transactions.append(uow.in_unit_of_work())
        with webhook_app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=_ORDER_BID).one()
            seen_status.append(int(order.status))

    monkeypatch.setattr(
        BillingOrderProviderUpdateResult, "dispatch_after_commit", record_dispatch
    )

    _payload, status_code = webhooks.apply_billing_native_notification(
        webhook_app, "alipay", _paid_notification()
    )

    assert status_code == 200
    assert open_transactions == [False]
    assert seen_status == [BILLING_ORDER_STATUS_PAID]
