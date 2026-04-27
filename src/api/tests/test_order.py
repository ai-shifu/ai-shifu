from decimal import Decimal
from datetime import datetime, timedelta
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.order.funs import init_buy_record
from flaskr.service.order.consts import ORDER_STATUS_INIT
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_TYPE_FIXED,
    PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
    PROMO_CAMPAIGN_STATUS_ACTIVE,
)
from flaskr.service.promo.models import PromoCampaign, PromoRedemption


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


def test_init_buy_record_reactivates_voided_promo_redemption(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(price=Decimal("500.00")),
    )

    now = datetime.now()

    with app.app_context():
        order = Order(
            order_bid="order-reactivate-1",
            user_bid="user-reactivate-1",
            shifu_bid="course-reactivate-1",
            payable_price=Decimal("500.00"),
            paid_price=Decimal("500.00"),
            status=ORDER_STATUS_INIT,
        )
        campaign = PromoCampaign(
            promo_bid="promo-reactivate-1",
            shifu_bid="course-reactivate-1",
            name="春节专享",
            apply_type=PROMO_CAMPAIGN_JOIN_TYPE_AUTO,
            status=PROMO_CAMPAIGN_STATUS_ACTIVE,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("400.00"),
            channel="spring",
            filter="{}",
        )
        redemption = PromoRedemption(
            redemption_bid="redeem-reactivate-1",
            promo_bid="promo-reactivate-1",
            order_bid="order-reactivate-1",
            user_bid="user-reactivate-1",
            shifu_bid="course-reactivate-1",
            promo_name="旧春节专享",
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("400.00"),
            discount_amount=Decimal("400.00"),
            status=PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
        )
        db.session.add(order)
        db.session.add(campaign)
        db.session.add(redemption)
        db.session.commit()

        result = init_buy_record(app, "user-reactivate-1", "course-reactivate-1")

        assert result.order_id == "order-reactivate-1"
        assert Decimal(result.discount) == Decimal("400.00")
        assert Decimal(result.value_to_pay) == Decimal("100.00")
        assert any(item.price_name == "春节专享" for item in result.price_item)

        original_redemption = PromoRedemption.query.filter(
            PromoRedemption.redemption_bid == "redeem-reactivate-1"
        ).first()
        if original_redemption is not None:
            db.session.delete(original_redemption)
        db.session.delete(campaign)
        db.session.delete(order)
        db.session.commit()
