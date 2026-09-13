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

from tests.service.billing.test_billing_callbacks import (
    _create_active_subscription,
    _create_billing_pingxx_raw_snapshot,
    _create_pingxx_billing_order,
    build_bill_products,
)

_ORDER_BID = "bill-pingxx-uow-failure"
_CHARGE_ID = "ch_billing_pingxx_uow_failure"
_BODY = {
    "type": "charge.succeeded",
    "data": {
        "object": {
            "id": _CHARGE_ID,
            "order_no": _ORDER_BID,
            "paid": True,
            "time_paid": 1712577600,
        }
    },
}


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


def _seed_pending_pingxx_order(app: object) -> None:
    with app.app_context():
        dao.db.session.add_all(
            [
                _create_active_subscription(),
                _create_pingxx_billing_order(_ORDER_BID, _CHARGE_ID),
                _create_billing_pingxx_raw_snapshot(_ORDER_BID, _CHARGE_ID),
            ]
        )
        dao.db.session.commit()


def test_pingxx_webhook_failure_rolls_back_and_dispatches_nothing(
    webhook_app: object, monkeypatch: object
) -> None:
    dispatched: list[str] = []
    _seed_pending_pingxx_order(webhook_app)

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
        webhooks.handle_billing_pingxx_webhook(webhook_app, _BODY)

    with webhook_app.app_context():
        dao.db.session.expire_all()
        order = BillingOrder.query.filter_by(bill_order_bid=_ORDER_BID).one()
        assert order.status == BILLING_ORDER_STATUS_PENDING
        assert not order.paid_at
    assert dispatched == []


def test_pingxx_webhook_dispatches_only_after_the_paid_status_is_durable(
    webhook_app: object, monkeypatch: object
) -> None:
    seen_status: list[int] = []
    _seed_pending_pingxx_order(webhook_app)

    def record_dispatch(*_a: object, **_k: object) -> None:
        # Committed state only: a separate connection cannot see staged rows.
        with webhook_app.app_context(), dao.db.engine.connect() as connection:
            row = connection.execute(
                BillingOrder.__table__.select().where(
                    BillingOrder.bill_order_bid == _ORDER_BID
                )
            ).first()
            seen_status.append(int(row.status))

    monkeypatch.setattr(
        BillingOrderProviderUpdateResult, "dispatch_after_commit", record_dispatch
    )

    _payload, status_code = webhooks.handle_billing_pingxx_webhook(webhook_app, _BODY)

    assert status_code == 200
    assert seen_status == [BILLING_ORDER_STATUS_PAID]
