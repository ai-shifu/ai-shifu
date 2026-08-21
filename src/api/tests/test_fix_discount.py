"""Verify coupon redemption applies valid legacy discounts."""

from datetime import timedelta
from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_STATUS_ACTIVE,
    COUPON_TYPE_FIXED,
)
from flaskr.service.promo.models import Coupon, CouponUsage
from flaskr.util.datetime import now_utc


def test_use_coupon_code_applies_discount(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
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

        now = now_utc()
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

    def fake_send_feishu_coupon_code(
        _app: object, user_id: object, code: object, _name: object, _value: object
    ) -> None:
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
        assert usage.shifu_bid == course_bid
        assert updated_coupon.used_count == 1
    assert sent["code"] == coupon_code


def test_use_specific_all_courses_coupon_keeps_unbound_usage_course(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_bid = "order-fix-discount-2"
    course_bid = "course-fix-discount-2"
    user_bid = "user-fix-discount-2"
    coupon_bid = "coupon-fix-discount-2"
    coupon_code = "CODE-FIX-2"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("100.00"),
            paid_price=Decimal("100.00"),
        )
        db.session.add(order)

        now = now_utc()
        coupon = Coupon(
            coupon_bid=coupon_bid,
            # Keep the batch code blank so this test explicitly exercises
            # CouponUsage-level code resolution for specific-use coupons.
            code="",
            usage_type=COUPON_APPLY_TYPE_SPECIFIC,
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("10.00"),
            start=now - timedelta(days=1),
            end=now + timedelta(days=1),
            channel="test",
            filter='{"course_id": ""}',
            total_count=1,
            used_count=0,
            status=1,
        )
        db.session.add(coupon)
        usage = CouponUsage(
            coupon_usage_bid="usage-fix-discount-2",
            coupon_bid=coupon_bid,
            code=coupon_code,
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("10.00"),
            status=COUPON_STATUS_ACTIVE,
            shifu_bid="",
        )
        db.session.add(usage)
        db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        lambda *_args, **_kwargs: None,
    )

    result = use_coupon_code(app, user_bid, coupon_code, order_bid)
    assert result.order_id == order_bid

    with app.app_context():
        refreshed = Order.query.filter(Order.order_bid == order_bid).first()
        usage = CouponUsage.query.filter(CouponUsage.order_bid == order_bid).first()
        updated_coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert refreshed is not None
        assert str(refreshed.paid_price) == "90.00"
        assert usage is not None
        assert usage.coupon_usage_bid == "usage-fix-discount-2"
        assert usage.coupon_bid == coupon_bid
        assert usage.order_bid == order_bid
        assert usage.shifu_bid == ""
        assert updated_coupon is not None
        assert updated_coupon.used_count == 1


def test_use_coupon_code_accepts_legacy_coupon_status(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    order_bid = "order-fix-discount-legacy"
    course_bid = "course-fix-discount-legacy"
    user_bid = "user-fix-discount-legacy"
    coupon_bid = "coupon-fix-discount-legacy"
    coupon_code = "CODE-FIX-LEGACY"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("100.00"),
            paid_price=Decimal("100.00"),
        )
        db.session.add(order)

        now = now_utc()
        coupon = Coupon(
            coupon_bid=coupon_bid,
            code=coupon_code,
            discount_type=COUPON_TYPE_FIXED,
            value=Decimal("10.00"),
            start=now - timedelta(days=1),
            end=now + timedelta(days=1),
            channel="legacy",
            filter="",
            total_count=5,
            used_count=0,
            status=0,
            created_user_bid="",
            updated_user_bid="",
        )
        db.session.add(coupon)
        db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        lambda *_args, **_kwargs: None,
    )

    result = use_coupon_code(app, user_bid, coupon_code, order_bid)
    assert result.order_id == order_bid

    with app.app_context():
        refreshed = Order.query.filter(Order.order_bid == order_bid).first()
        usage = CouponUsage.query.filter(CouponUsage.order_bid == order_bid).first()
        updated_coupon = Coupon.query.filter(Coupon.coupon_bid == coupon_bid).first()
        assert refreshed is not None
        assert str(refreshed.paid_price) == "90.00"
        assert usage is not None
        assert updated_coupon is not None
        assert updated_coupon.used_count == 1


def test_use_coupon_code_accepts_coupon_expiring_soon_in_utc(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: the validity window is stored and compared as naive UTC.
    # A localized (UTC+8) reading of `end` used to reject coupons that expire
    # within the next eight hours as already expired.
    order_bid = "order-fix-discount-utc-1"
    course_bid = "course-fix-discount-utc-1"
    user_bid = "user-fix-discount-utc-1"
    coupon_code = "CODE-FIX-UTC-1"

    with app.app_context():
        db.session.add(
            Order(
                order_bid=order_bid,
                shifu_bid=course_bid,
                user_bid=user_bid,
                payable_price=Decimal("100.00"),
                paid_price=Decimal("100.00"),
            )
        )
        now = now_utc()
        db.session.add(
            Coupon(
                coupon_bid="coupon-fix-discount-utc-1",
                code=coupon_code,
                discount_type=COUPON_TYPE_FIXED,
                value=Decimal("10.00"),
                start=now - timedelta(days=1),
                end=now + timedelta(hours=4),
                channel="test",
                filter="",
                total_count=5,
                used_count=0,
                status=1,
            )
        )
        db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        lambda *_args: None,
    )

    result = use_coupon_code(app, user_bid, coupon_code, order_bid)
    assert result.order_id == order_bid


def test_use_coupon_code_rejects_coupon_not_yet_started_in_utc(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: a localized (UTC+8) reading of `start` used to open the
    # redemption window eight hours before the stored UTC start time.
    order_bid = "order-fix-discount-utc-2"
    course_bid = "course-fix-discount-utc-2"
    user_bid = "user-fix-discount-utc-2"
    coupon_code = "CODE-FIX-UTC-2"

    with app.app_context():
        db.session.add(
            Order(
                order_bid=order_bid,
                shifu_bid=course_bid,
                user_bid=user_bid,
                payable_price=Decimal("100.00"),
                paid_price=Decimal("100.00"),
            )
        )
        now = now_utc()
        db.session.add(
            Coupon(
                coupon_bid="coupon-fix-discount-utc-2",
                code=coupon_code,
                discount_type=COUPON_TYPE_FIXED,
                value=Decimal("10.00"),
                start=now + timedelta(hours=4),
                end=now + timedelta(days=1),
                channel="test",
                filter="",
                total_count=5,
                used_count=0,
                status=1,
            )
        )
        db.session.commit()

    monkeypatch.setattr(
        "flaskr.service.order.coupon_funcs.send_feishu_coupon_code",
        lambda *_args: None,
    )

    with pytest.raises(AppError):
        use_coupon_code(app, user_bid, coupon_code, order_bid)
