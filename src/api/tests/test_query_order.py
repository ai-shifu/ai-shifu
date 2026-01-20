from decimal import Decimal

from flaskr.dao import db
from flaskr.service.order.funs import query_buy_record
from flaskr.service.order.models import Order


def test_query_buy_record_returns_dto(app):
    with app.app_context():
        order = Order(
            order_bid="order-query-1",
            shifu_bid="shifu-query-1",
            user_bid="user-query-1",
            payable_price=Decimal("100.00"),
            paid_price=Decimal("80.00"),
            payment_channel="pingxx",
        )
        db.session.add(order)
        db.session.commit()

    result = query_buy_record(app, "order-query-1")
    assert result.order_id == "order-query-1"
    assert result.user_id == "user-query-1"
    assert result.course_id == "shifu-query-1"
