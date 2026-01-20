from decimal import Decimal


def test_query_buy_record_returns_dto(app):
    from flaskr.dao import db
    from flaskr.service.order.funs import query_buy_record
    from flaskr.service.order.models import Order

    with app.app_context():
        order = Order(
            order_bid="order-1",
            shifu_bid="shifu-1",
            user_bid="user-1",
            payable_price=Decimal("100.00"),
            paid_price=Decimal("80.00"),
            payment_channel="pingxx",
        )
        db.session.add(order)
        db.session.commit()

    result = query_buy_record(app, "order-1")
    assert result.order_id == "order-1"
    assert result.user_id == "user-1"
    assert result.course_id == "shifu-1"
