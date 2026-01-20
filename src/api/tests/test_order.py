from decimal import Decimal
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.order.funs import init_buy_record
from flaskr.service.order.models import Order


def test_init_buy_record_creates_order(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(price=Decimal("100.00")),
    )
    monkeypatch.setattr(order_funs, "query_and_join_active", lambda *args, **kwargs: [])

    result = init_buy_record(app, "user-order-1", "course-order-1")
    assert result.order_id
    assert result.user_id == "user-order-1"
    assert str(result.price) == "100.00"

    with app.app_context():
        stored = Order.query.filter(Order.order_bid == result.order_id).first()
        assert stored is not None
        assert stored.user_bid == "user-order-1"
        assert stored.shifu_bid == "course-order-1"
        assert str(stored.paid_price) == "100.00"
        db.session.delete(stored)
        db.session.commit()
