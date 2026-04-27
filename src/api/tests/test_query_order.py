from decimal import Decimal
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.order.funs import query_buy_record
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order


def test_query_buy_record_returns_dto(app):
    with app.app_context():
        order = Order(
            order_bid="order-query-1",
            shifu_bid="shifu-query-1",
            user_bid="user-query-1",
            payable_price=Decimal("0.00"),
            paid_price=Decimal("0.00"),
            payment_channel="pingxx",
        )
        db.session.add(order)
        db.session.commit()

    result = query_buy_record(app, "order-query-1")
    assert result.order_id == "order-query-1"
    assert result.user_id == "user-query-1"
    assert result.course_id == "shifu-query-1"


def test_query_buy_record_keeps_stored_discount_for_unpaid_order(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    with app.app_context():
        order = Order(
            order_bid="order-query-discount-1",
            shifu_bid="shifu-query-2",
            user_bid="user-query-2",
            payable_price=Decimal("500.00"),
            paid_price=Decimal("100.00"),
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="pingxx",
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(
        order_funs,
        "query_promo_campaign_applications",
        lambda _app, _order_id, _recalc: [
            SimpleNamespace(
                discount_amount=Decimal("400.00"),
                promo_name="spring-promo",
            )
        ],
        )

    result = query_buy_record(app, "order-query-discount-1")
    assert result.order_id == "order-query-discount-1"
    assert str(result.discount) == "400.00"
    assert result.value_to_pay == "100.00"
