from datetime import datetime, timedelta
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import COUPON_TYPE_FIXED
from flaskr.service.promo.models import Coupon, CouponUsage


def test_use_coupon_code_applies_discount(app, monkeypatch):
    with app.app_context():
        order = Order(
            order_bid="order-1",
            shifu_bid="course-1",
            user_bid="user-1",
            payable_price=Decimal("100.00"),
            paid_price=Decimal("100.00"),
        )
        db.session.add(order)

        now = datetime.now()
        coupon = Coupon(
            coupon_bid="coupon-1",
            code="CODE1",
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("10.00"),
            start=now - timedelta(days=1),
            end=now + timedelta(days=1),
            channel="test",
            filter="",
            total_count=5,
            used_count=0,
            status=1,
        )
        db.session.add(coupon)
        db.session.commit()

    sent = {}

    def fake_send_feishu_coupon_code(_app, user_id, code, name, value):
        sent["user_id"] = user_id
        sent["code"] = code

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        fake_send_feishu_coupon_code,
    )

    result = use_coupon_code(app, "user-1", "CODE1", "order-1")
    assert result.order_id == "order-1"

    with app.app_context():
        refreshed = Order.query.filter(Order.order_bid == "order-1").first()
        usage = CouponUsage.query.filter(CouponUsage.order_bid == "order-1").first()
        updated_coupon = Coupon.query.filter(Coupon.coupon_bid == "coupon-1").first()

    assert str(refreshed.paid_price) == "90.00"
    assert usage is not None
    assert updated_coupon.used_count == 1
    assert sent["code"] == "CODE1"
