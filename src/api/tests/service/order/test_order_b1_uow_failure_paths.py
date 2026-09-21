"""Unit-of-work behavior for the B1 order call sites.

Covers ``use_coupon_code`` (coupon redemption), ``open_api_revoke_order``
(post-commit notification), and ``import_activation_order`` (two explicit
steps: account first, order second).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr import dao
from flaskr.service.order import admin as order_admin
from flaskr.service.order import coupon_funcs, open_api
from flaskr.service.order import funs as order_funs
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.promo.consts import (
    COUPON_STATUS_USED,
    COUPON_TYPE_FIXED,
    COUPON_TYPE_PERCENT,
)
from flaskr.service.promo.models import Coupon, CouponUsage
from flaskr.service.user.repository import load_user_aggregate_by_identifier
from flaskr.util.datetime import now_utc


def _committed_order_status(order_bid: str) -> int | None:
    with dao.db.engine.connect() as connection:
        row = connection.execute(
            Order.__table__.select().where(Order.order_bid == order_bid)
        ).first()
    return None if row is None else row.status


def _seed_coupon_order(
    order_bid: str,
    coupon_code: str,
    *,
    discount_type: int = COUPON_TYPE_FIXED,
    value: Decimal = Decimal("10.00"),
) -> None:
    now = now_utc()
    dao.db.session.add_all(
        [
            Order(
                order_bid=order_bid,
                shifu_bid=f"{order_bid}-course",
                user_bid=f"{order_bid}-user",
                payable_price=Decimal("100.00"),
                paid_price=Decimal("100.00"),
            ),
            Coupon(
                coupon_bid=f"{order_bid}-coupon",
                code=coupon_code,
                discount_type=discount_type,
                value=value,
                start=now - timedelta(days=1),
                end=now + timedelta(days=1),
                channel="test",
                filter="",
                total_count=5,
                used_count=0,
                status=1,
            ),
        ]
    )
    dao.db.session.commit()


def test_use_coupon_code_late_failure_leaves_coupon_unused(
    app: object, monkeypatch: object
) -> None:
    order_bid = "uow-b1-coupon-order-1"
    coupon_code = "UOWB1FAIL"
    notified: list[str] = []
    monkeypatch.setattr(
        coupon_funcs,
        "send_feishu_coupon_code",
        lambda *_a, **_k: notified.append("sent"),
    )

    def failing_query(*_args: object, **_kwargs: object) -> object:
        message = "boom after redemption"
        raise RuntimeError(message)

    monkeypatch.setattr(coupon_funcs, "query_buy_record", failing_query)

    with app.app_context():
        _seed_coupon_order(order_bid, coupon_code)
        with pytest.raises(RuntimeError, match="boom after redemption"):
            coupon_funcs.use_coupon_code(
                app, f"{order_bid}-user", coupon_code, order_bid
            )
        dao.db.session.rollback()
        dao.db.session.expire_all()
        order = Order.query.filter(Order.order_bid == order_bid).first()
        coupon = Coupon.query.filter(Coupon.coupon_bid == f"{order_bid}-coupon").first()
        usage_count = CouponUsage.query.filter(
            CouponUsage.order_bid == order_bid,
            CouponUsage.status == COUPON_STATUS_USED,
        ).count()

    assert order.paid_price == Decimal("100.00")
    assert coupon.used_count == 0
    assert usage_count == 0
    assert notified == []  # on_commit side effect dropped with the rollback


def test_use_coupon_code_notifies_after_commit(
    app: object, monkeypatch: object
) -> None:
    order_bid = "uow-b1-coupon-order-2"
    coupon_code = "UOWB1OK"
    seen: list[Decimal | None] = []

    def fake_notify(_app: object, _user: object, _code: object) -> None:
        with dao.db.engine.connect() as connection:
            row = connection.execute(
                Order.__table__.select().where(Order.order_bid == order_bid)
            ).first()
        seen.append(None if row is None else Decimal(str(row.paid_price)))

    monkeypatch.setattr(coupon_funcs, "send_feishu_coupon_code", fake_notify)

    with app.app_context():
        _seed_coupon_order(order_bid, coupon_code)
        result = coupon_funcs.use_coupon_code(
            app, f"{order_bid}-user", coupon_code, order_bid
        )

    assert result.order_id == order_bid
    # The notification observed the committed discounted price.
    assert seen == [Decimal("90.00")]


def test_use_percentage_coupon_applies_percent_of_order_price(
    app: object, monkeypatch: object
) -> None:
    order_bid = "uow-b1-percent-coupon-order"
    coupon_code = "PERCENT20"
    monkeypatch.setattr(coupon_funcs, "send_feishu_coupon_code", lambda *_a: None)

    with app.app_context():
        _seed_coupon_order(
            order_bid,
            coupon_code,
            discount_type=COUPON_TYPE_PERCENT,
            value=Decimal("20.00"),
        )
        result = coupon_funcs.use_coupon_code(
            app, f"{order_bid}-user", coupon_code, order_bid
        )
        order = Order.query.filter(Order.order_bid == order_bid).first()

    assert result.order_id == order_bid
    assert order.paid_price == Decimal("80.00")


def test_percentage_coupon_breakdown_uses_discounted_currency_amount(
    app: object,
) -> None:
    order_bid = "uow-b1-percent-breakdown-order"
    coupon_code = "PERCENT20BREAKDOWN"

    with app.app_context():
        _seed_coupon_order(
            order_bid,
            coupon_code,
            discount_type=COUPON_TYPE_PERCENT,
            value=Decimal("20.00"),
        )
        coupon = Coupon.query.filter(Coupon.coupon_bid == f"{order_bid}-coupon").first()
        discount_info = order_funs.calculate_discount_value(
            Decimal("200.00"),
            [],
            [CouponUsage(coupon_bid=coupon.coupon_bid)],
        )

    assert discount_info.discount_value == Decimal("40.00")
    assert discount_info.items[0].price == Decimal("40.00")


def test_open_api_revoke_notifies_only_after_the_refund_is_committed(
    app: object, monkeypatch: object
) -> None:
    order_bid = "uow-b1-revoke-order-1"
    shifu_bid = "uow-b1-revoke-course"
    user_bid = "uow-b1-revoke-user"
    seen: list[int | None] = []

    monkeypatch.setattr(open_api, "verify_course_ownership", lambda *_a, **_k: None)
    monkeypatch.setattr(
        open_api,
        "load_user_aggregate_by_identifier",
        lambda *_a, **_k: SimpleNamespace(user_bid=user_bid),
    )
    monkeypatch.setattr(
        open_api,
        "send_revoke_feishu",
        lambda *_a, **_k: seen.append(_committed_order_status(order_bid)),
    )

    with app.app_context():
        dao.db.session.add(
            Order(
                order_bid=order_bid,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                payable_price=Decimal("0.00"),
                paid_price=Decimal("0.00"),
                status=ORDER_STATUS_SUCCESS,
            )
        )
        dao.db.session.commit()
        result = open_api.open_api_revoke_order(
            app, "owner", shifu_bid, "13800000001", "phone"
        )

    assert result == {"order_bid": order_bid, "status": "revoked"}
    assert seen == [ORDER_STATUS_REFUND]


def test_import_activation_account_step_survives_order_failure(
    app: object, monkeypatch: object
) -> None:
    """Step 1 (account + credential) is durable before the order step runs."""
    identifier = "13800138999"
    course_id = "uow-b1-import-course"

    monkeypatch.setattr(
        order_admin, "ensure_demo_course_permissions", lambda *_a, **_k: None
    )

    def failing_init(*_args: object, **_kwargs: object) -> object:
        message = "order init boom"
        raise RuntimeError(message)

    monkeypatch.setattr(order_admin, "init_buy_record", failing_init)

    with app.app_context():
        with pytest.raises(RuntimeError, match="order init boom"):
            order_admin.import_activation_order(
                app, identifier, course_id, "Imported", contact_type="phone"
            )
        dao.db.session.rollback()
        dao.db.session.expire_all()
        aggregate = load_user_aggregate_by_identifier(identifier, providers=["phone"])
        order_count = Order.query.filter(
            Order.user_bid == (aggregate.user_bid if aggregate else "")
        ).count()

    assert aggregate is not None
    assert aggregate.nickname == "Imported"
    assert order_count == 0
