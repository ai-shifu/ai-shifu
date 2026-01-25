from datetime import datetime, timedelta
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import COUPON_TYPE_FIXED
from flaskr.service.promo.models import Coupon, CouponUsage


def test_use_coupon_code_applies_discount(app, monkeypatch):
    order_bid = "order-fix-discount-1"
    course_bid = "course-fix-discount-1"
    user_bid = "user-fix-discount-1"
    coupon_bid = "coupon-fix-discount-1"
    coupon_code = "CODE-FIX-1"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("100.00"),
            paid_price=Decimal("100.00"),
        )
        db.session.add(order)

        now = datetime.now()
        coupon = Coupon(
            coupon_bid=coupon_bid,
            code=coupon_code,
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

    def fake_send_feishu_coupon_code(_app, user_id, code, _name, _value):
        sent["user_id"] = user_id
        sent["code"] = code

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        fake_send_feishu_coupon_code,
    )

    result = use_coupon_code(app, user_bid, coupon_code, order_bid)
    assert result.order_id == order_bid

    with app.app_context():
        refreshed = Order.query.filter(Order.order_bid == order_bid).first()
        usage = CouponUsage.query.filter(CouponUsage.order_bid == order_bid).first()
        updated_coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert str(refreshed.paid_price) == "90.00"
        assert usage is not None
        assert updated_coupon.used_count == 1
    assert sent["code"] == coupon_code
