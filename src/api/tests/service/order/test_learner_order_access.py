"""Regression coverage for learner order ownership and mutable states."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
)
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.order.funs import (
    generate_charge,
    get_payment_details,
    query_buy_record,
)
from flaskr.service.order.models import Order, PingxxOrder
from flaskr.service.promo.models import CouponUsage


def _seed_order(
    *,
    order_bid: str,
    user_bid: str = "owner-user",
    status: int = ORDER_STATUS_INIT,
    payment_channel: str = "pingxx",
) -> Order:
    order = Order(
        order_bid=order_bid,
        shifu_bid=f"course-{order_bid}",
        user_bid=user_bid,
        payable_price=Decimal("200.00"),
        paid_price=Decimal("200.00"),
        payment_channel=payment_channel,
        status=status,
        deleted=0,
    )
    db.session.add(order)
    db.session.commit()
    return order


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/order/query-order", {"order_id": "other-user-order"}),
        ("/api/order/reqiure-to-pay", {"order_id": "other-user-order"}),
        ("/api/order/payment-detail", {"order_id": "other-user-order"}),
        (
            "/api/order/apply-discount",
            {"order_id": "other-user-order", "discount_code": "PRIVATE"},
        ),
    ],
)
def test_learner_order_routes_hide_another_users_order(
    app: object,
    test_client: object,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, str],
) -> None:
    with app.app_context():
        _seed_order(order_bid="other-user-order", user_bid="owner-user")

    user = SimpleNamespace(user_id="attacker-user", is_creator=False, language="en-US")
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda _app, _token: user)

    response = test_client.post(path, json=payload, headers={"Token": "test-token"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["code"] != 0
    assert body["message"] == "Order Not Found"


def test_order_services_hide_another_users_order(app: object) -> None:
    with app.app_context():
        _seed_order(order_bid="service-owner-order", user_bid="owner-user")

    protected_calls = [
        lambda: query_buy_record(
            app, "service-owner-order", expected_user="attacker-user"
        ),
        lambda: get_payment_details(
            app, "service-owner-order", expected_user="attacker-user"
        ),
        lambda: generate_charge(
            app,
            "service-owner-order",
            "alipay_qr",
            "127.0.0.1",
            expected_user="attacker-user",
        ),
        lambda: use_coupon_code(app, "attacker-user", "PRIVATE", "service-owner-order"),
    ]

    for call in protected_calls:
        with pytest.raises(AppError, match="Order Not Found"):
            call()


@pytest.mark.parametrize(
    "status", [ORDER_STATUS_SUCCESS, ORDER_STATUS_REFUND, ORDER_STATUS_TIMEOUT]
)
def test_coupon_rejects_terminal_order_without_mutation(
    app: object, status: int
) -> None:
    order_bid = f"terminal-coupon-{status}"
    with app.app_context():
        order = _seed_order(order_bid=order_bid, status=status)
        before = (order.payable_price, order.paid_price, order.status, order.updated_at)

        with pytest.raises(AppError, match="Order status is invalid"):
            use_coupon_code(app, "owner-user", "PRIVATE", order_bid)

        db.session.expire_all()
        stored = Order.query.filter_by(order_bid=order_bid).one()
        after = (
            stored.payable_price,
            stored.paid_price,
            stored.status,
            stored.updated_at,
        )
        usage_count = CouponUsage.query.filter_by(order_bid=order_bid).count()

    assert after == before
    assert usage_count == 0


def test_pingxx_payment_detail_exposes_only_learner_status_fields(app: object) -> None:
    with app.app_context():
        order = _seed_order(order_bid="minimal-pingxx-detail")
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="pingxx-secret-snapshot",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                transaction_no="transaction-secret",
                channel="alipay_qr",
                amount=20000,
                currency="CNY",
                extra='{"credential":"secret"}',
                status=0,
                charge_id="charge-secret",
                charge_object='{"raw":"secret"}',
                deleted=0,
            )
        )
        db.session.commit()

    details = get_payment_details(
        app, "minimal-pingxx-detail", expected_user="owner-user"
    )

    assert details == {
        "payment_channel": "pingxx",
        "course_id": "course-minimal-pingxx-detail",
        "order_bid": "minimal-pingxx-detail",
        "status": 0,
    }
