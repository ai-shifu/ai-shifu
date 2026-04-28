from decimal import Decimal
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.order.funs import query_buy_record
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
)
from flaskr.service.promo.models import Coupon, CouponUsage


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
                discount_amount=Decimal("123.45"),
                promo_name="spring-promo",
            )
        ],
    )

    result = query_buy_record(app, "order-query-discount-1")
    assert result.order_id == "order-query-discount-1"
    assert str(result.discount) == "400.00"
    assert result.value_to_pay == "100.00"

    with app.app_context():
        order = Order.query.filter(Order.order_bid == "order-query-discount-1").first()
        if order is not None:
            db.session.delete(order)
            db.session.commit()


def test_query_buy_record_uses_coupon_name_and_code_in_price_item(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    with app.app_context():
        order = Order(
            order_bid="order-query-coupon-1",
            shifu_bid="shifu-query-coupon-1",
            user_bid="user-query-coupon-1",
            payable_price=Decimal("500.00"),
            paid_price=Decimal("490.00"),
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="pingxx",
        )
        coupon = Coupon(
            coupon_bid="coupon-query-1",
            name="新人券",
            code="NEW10",
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("10.00"),
            filter="{}",
        )
        usage = CouponUsage(
            coupon_usage_bid="usage-query-1",
            coupon_bid="coupon-query-1",
            user_bid="user-query-coupon-1",
            order_bid="order-query-coupon-1",
            code="NEW10",
            status=COUPON_STATUS_USED,
            value=Decimal("10.00"),
        )
        db.session.add(order)
        db.session.add(coupon)
        db.session.add(usage)
        db.session.commit()

    monkeypatch.setattr(
        order_funs,
        "query_promo_campaign_applications",
        lambda _app, _order_id, _recalc: [],
    )

    result = query_buy_record(app, "order-query-coupon-1")
    assert result.order_id == "order-query-coupon-1"
    assert any(item.price_name == "新人券 (NEW10)" for item in result.price_item)

    with app.app_context():
        usage = CouponUsage.query.filter(
            CouponUsage.coupon_usage_bid == "usage-query-1"
        ).first()
        coupon = Coupon.query.filter(Coupon.coupon_bid == "coupon-query-1").first()
        order = Order.query.filter(Order.order_bid == "order-query-coupon-1").first()
        if usage is not None:
            db.session.delete(usage)
        if coupon is not None:
            db.session.delete(coupon)
        if order is not None:
            db.session.delete(order)
        db.session.commit()


def test_query_buy_record_does_not_supplement_voided_campaign_redemption(
    app, monkeypatch
):
    from flaskr.service.order import funs as order_funs
    from flaskr.service.promo.consts import (
        PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
    )
    from flaskr.service.promo.models import PromoCampaign, PromoRedemption

    with app.app_context():
        order = Order(
            order_bid="order-query-voided-promo-1",
            shifu_bid="shifu-query-voided-1",
            user_bid="user-query-voided-1",
            payable_price=Decimal("500.00"),
            paid_price=Decimal("400.00"),
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="pingxx",
        )
        campaign = PromoCampaign(
            promo_bid="promo-query-voided-1",
            shifu_bid="shifu-query-voided-1",
            name="过期活动",
        )
        redemption = PromoRedemption(
            redemption_bid="redemption-query-voided-1",
            promo_bid="promo-query-voided-1",
            order_bid="order-query-voided-promo-1",
            user_bid="user-query-voided-1",
            shifu_bid="shifu-query-voided-1",
            promo_name="过期活动",
            discount_amount=Decimal("100.00"),
            status=PROMO_CAMPAIGN_APPLICATION_STATUS_VOIDED,
        )
        db.session.add(order)
        db.session.add(campaign)
        db.session.add(redemption)
        db.session.commit()

    monkeypatch.setattr(
        order_funs,
        "query_promo_campaign_applications",
        lambda _app, _order_id, _recalc: [],
    )

    result = query_buy_record(app, "order-query-voided-promo-1")
    assert result.order_id == "order-query-voided-promo-1"
    assert all(item.price_name != "过期活动" for item in result.price_item)

    with app.app_context():
        redemption = PromoRedemption.query.filter(
            PromoRedemption.redemption_bid == "redemption-query-voided-1"
        ).first()
        campaign = PromoCampaign.query.filter(
            PromoCampaign.promo_bid == "promo-query-voided-1"
        ).first()
        order = Order.query.filter(
            Order.order_bid == "order-query-voided-promo-1"
        ).first()
        if redemption is not None:
            db.session.delete(redemption)
        if campaign is not None:
            db.session.delete(campaign)
        if order is not None:
            db.session.delete(order)
        db.session.commit()
