from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.models import BillingOrder
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.funs import (
    BuyRecordDTO,
    generate_charge,
    init_buy_record,
    query_buy_record,
)
from flaskr.service.order.models import Order


@pytest.fixture
def legacy_order_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="legacy-order-test",
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_legacy_order_purchase_flow_stays_on_order_tables(
    legacy_order_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.order import funs as order_funs

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            price=Decimal("99.00"),
            title="Legacy course",
            description="Legacy checkout flow",
        ),
    )
    monkeypatch.setattr(
        order_funs, "apply_promo_campaigns", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        order_funs,
        "_generate_pingxx_charge",
        lambda **kwargs: _fake_pingxx_charge(**kwargs),
    )

    def _fake_pingxx_charge(**kwargs):
        buy_record = kwargs["buy_record"]
        buy_record.status = ORDER_STATUS_TO_BE_PAID
        dao.db.session.add(buy_record)
        dao.db.session.commit()
        return BuyRecordDTO(
            buy_record.order_bid,
            buy_record.user_bid,
            buy_record.paid_price,
            kwargs["channel"],
            "legacy-qr-url",
            payment_channel="pingxx",
        )

    init_result = init_buy_record(
        legacy_order_app,
        "legacy-user-1",
        "legacy-course-1",
    )
    charge_result = generate_charge(
        legacy_order_app,
        init_result.order_id,
        "wx_wap",
        "127.0.0.1",
    )
    query_result = query_buy_record(legacy_order_app, init_result.order_id)

    assert charge_result.payment_channel == "pingxx"
    assert charge_result.channel == "wx_wap"
    assert charge_result.qr_url == "legacy-qr-url"
    assert query_result.order_id == init_result.order_id
    assert query_result.user_id == "legacy-user-1"
    assert query_result.course_id == "legacy-course-1"

    with legacy_order_app.app_context():
        order = Order.query.filter(Order.order_bid == init_result.order_id).first()

        assert order is not None
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert order.payment_channel == "pingxx"
        assert BillingOrder.query.count() == 0
