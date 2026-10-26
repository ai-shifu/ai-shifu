"""Unit-of-work behavior for the B6 billing payment chain."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from flaskr import dao
from flaskr.service.billing import checkout, notifications
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc


def _committed_order(app: object, bill_order_bid: str) -> object:
    with app.app_context(), dao.db.engine.connect() as connection:
        return connection.execute(
            BillingOrder.__table__.select().where(
                BillingOrder.bill_order_bid == bill_order_bid
            )
        ).first()


def _seed_order(
    app: object,
    *,
    status: int,
    expires_at: object = None,
    order_type: int = BILLING_ORDER_TYPE_TOPUP,
) -> str:
    bill_order_bid = f"uow-b6-{uuid.uuid4().hex[:12]}"
    with app.app_context():
        dao.db.session.add(
            BillingOrder(
                bill_order_bid=bill_order_bid,
                creator_bid="uow-b6-creator",
                order_type=order_type,
                product_bid="uow-b6-product",
                subscription_bid="",
                currency="CNY",
                payable_amount=100,
                paid_amount=0,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="",
                status=status,
                expires_at=expires_at,
                metadata_json={},
            )
        )
        dao.db.session.commit()
    return bill_order_bid


def test_order_checkout_persists_the_expiry_before_raising(app: object) -> None:
    """The expiry flip is step 1; the error is raised only after it committed."""
    bill_order_bid = _seed_order(
        app,
        status=BILLING_ORDER_STATUS_PENDING,
        expires_at=now_utc() - timedelta(minutes=5),
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    )

    with app.app_context(), pytest.raises(AppError):
        checkout.create_billing_order_checkout(
            app, "uow-b6-creator", bill_order_bid, {"channel": "alipay_qr"}
        )

    row = _committed_order(app, bill_order_bid)
    assert row.status == BILLING_ORDER_STATUS_TIMEOUT


def test_order_checkout_rejects_non_pending_orders_without_writes(
    app: object,
) -> None:
    bill_order_bid = _seed_order(app, status=BILLING_ORDER_STATUS_PAID)

    with app.app_context(), pytest.raises(AppError):
        checkout.create_billing_order_checkout(
            app, "uow-b6-creator", bill_order_bid, {"channel": "alipay_qr"}
        )

    row = _committed_order(app, bill_order_bid)
    assert row.status == BILLING_ORDER_STATUS_PAID


def test_feishu_delivery_claim_survives_a_provider_failure(
    app: object, monkeypatch: object
) -> None:
    """Step 1 (processing claim) is durable; step 3 records the provider failure."""
    bill_order_bid = _seed_order(app, status=BILLING_ORDER_STATUS_PAID)
    monkeypatch.setattr(notifications, "_supports_billing_paid_feishu", lambda _o: True)
    monkeypatch.setattr(
        notifications, "load_user_aggregate", lambda _bid: SimpleNamespace(mobile="1")
    )
    monkeypatch.setattr(notifications, "_load_notification_product", lambda _o: None)
    monkeypatch.setattr(
        notifications, "resolve_notification_product_name", lambda *_a, **_k: "p"
    )
    monkeypatch.setattr(
        notifications, "_build_billing_paid_feishu_message", lambda *_a, **_k: ("t", [])
    )
    seen: list[str] = []

    def failing_notify(*_args: object, **_kwargs: object) -> None:
        # A fresh app context (separate session) only sees committed state.
        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            seen.append(
                order.metadata_json["notifications"]["billing_paid_feishu"]["status"]
            )
        message = "feishu down"
        raise RuntimeError(message)

    monkeypatch.setattr(notifications, "send_notify", failing_notify)
    with app.app_context():
        dao.db.session.query(BillingOrder).filter_by(
            bill_order_bid=bill_order_bid
        ).update(
            {
                "metadata_json": {
                    "notifications": {"billing_paid_feishu": {"status": "pending"}}
                }
            }
        )
        dao.db.session.commit()
        payload = notifications.deliver_billing_paid_feishu(
            app, bill_order_bid=bill_order_bid
        )

    assert seen == ["processing"]  # the claim was committed before the call
    assert payload["status"] == "failed_provider"
    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
        assert (
            order.metadata_json["notifications"]["billing_paid_feishu"]["status"]
            == "failed_provider"
        )
