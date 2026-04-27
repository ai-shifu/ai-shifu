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
    monkeypatch.setattr(
        order_funs, "apply_promo_campaigns", lambda *_args, **_kwargs: []
    )

    with app.app_context():
        result = init_buy_record(app, "user-order-1", "course-order-1")
        assert result.order_id
        assert result.user_id == "user-order-1"
        assert str(result.price) == "100.00"

        stored = Order.query.filter(Order.order_bid == result.order_id).first()
        assert stored is not None
        assert stored.user_bid == "user-order-1"
        assert stored.shifu_bid == "course-order-1"
        assert str(stored.paid_price) == "100.00"
        db.session.delete(stored)
        db.session.commit()


def test_init_buy_record_refreshes_existing_unpaid_order_promotions(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(price=Decimal("100.00")),
    )

    promo_application = SimpleNamespace(
        discount_amount=Decimal("20.00"),
        promo_name="spring-promo",
    )
    apply_calls = {"count": 0}

    def fake_apply_promo_campaigns(*_args, **_kwargs):
        apply_calls["count"] += 1
        if apply_calls["count"] == 1:
            return []
        return [promo_application]

    def fake_query_promo_campaign_applications(_app, _order_id, _recalc_discount):
        if apply_calls["count"] >= 2:
            return [promo_application]
        return []

    monkeypatch.setattr(
        order_funs,
        "apply_promo_campaigns",
        fake_apply_promo_campaigns,
    )
    monkeypatch.setattr(
        order_funs,
        "query_promo_campaign_applications",
        fake_query_promo_campaign_applications,
    )

    with app.app_context():
        first_result = init_buy_record(app, "user-order-2", "course-order-2")
        second_result = init_buy_record(app, "user-order-2", "course-order-2")

        assert apply_calls["count"] == 2
        assert second_result.order_id == first_result.order_id
        assert Decimal(second_result.discount) == Decimal("20.00")
        assert Decimal(second_result.value_to_pay) == Decimal("80.00")

        stored = Order.query.filter(Order.order_bid == first_result.order_id).first()
        assert stored is not None
        assert stored.user_bid == "user-order-2"
        assert stored.shifu_bid == "course-order-2"
        assert Decimal(stored.paid_price) == Decimal("80.00")

        db.session.delete(stored)
        db.session.commit()
