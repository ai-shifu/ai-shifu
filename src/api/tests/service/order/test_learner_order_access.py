"""Regression coverage for learner order ownership and mutable states."""

from datetime import timedelta
from decimal import Decimal
from threading import Event
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.order.consts import (
    ORDER_STATUS_INIT,
    ORDER_STATUS_REFUND,
    ORDER_STATUS_REPRICING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TIMEOUT,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.coupon_funcs import use_coupon_code
from flaskr.service.order.funs import (
    _payment_lock_ownership_events,
    _resume_pending_charge,
    cancel_pending_payment_for_repricing,
    generate_charge,
    get_payment_details,
    query_buy_record,
    success_buy_record_from_native,
    success_buy_record_from_pingxx,
)
from flaskr.service.order.models import (
    AlipayOrder,
    Order,
    PingxxOrder,
    StripeOrder,
    WechatPayOrder,
)
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.promo.consts import COUPON_TYPE_FIXED
from flaskr.service.promo.models import Coupon, CouponUsage
from flaskr.util.datetime import now_utc


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


def test_pending_order_reuses_existing_payment_attempt(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        order = _seed_order(
            order_bid="pending-payment-order",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="pending-provider-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                channel="alipay_qr",
                amount=20000,
                extra="{}",
                charge_object=('{"credential":{"alipay_qr":"https://pay.example/qr"}}'),
            )
        )
        db.session.commit()

    provider_requested = False

    def track_provider_request(_name: str) -> object:
        nonlocal provider_requested
        provider_requested = True
        return object()

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", track_provider_request
    )

    result = generate_charge(
        app,
        "pending-payment-order",
        "alipay_qr",
        "127.0.0.1",
        expected_user="owner-user",
    )

    assert provider_requested is False
    assert result.qr_url == "https://pay.example/qr"
    assert result.payment_payload == {
        "qr_url": "https://pay.example/qr",
        "credential": {"alipay_qr": "https://pay.example/qr"},
    }


def test_pending_order_does_not_resume_an_empty_qr_credential(app: object) -> None:
    with app.app_context():
        order = _seed_order(
            order_bid="pending-empty-payment-order",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="pending-empty-provider-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                channel="wx_pub_qr",
                amount=20000,
                status=0,
                extra="{}",
                charge_object='{"credential":{"wx_pub_qr":""}}',
            )
        )
        db.session.commit()

        assert _resume_pending_charge(app, order) is None


@pytest.mark.parametrize(
    ("payment_channel", "snapshot_factory"),
    [
        (
            "pingxx",
            lambda order: PingxxOrder(
                pingxx_order_bid="expired-pingxx-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                channel="wx_pub_qr",
                amount=20000,
                status=0,
                extra="{}",
                charge_object=(
                    '{"time_expire":1,"credential":'
                    '{"wx_pub_qr":"https://pay.example/expired"}}'
                ),
            ),
        ),
        (
            "stripe",
            lambda order: StripeOrder(
                stripe_order_bid="expired-stripe-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                amount=20000,
                status=0,
                checkout_session_object=(
                    '{"url":"https://stripe.example/expired","expires_at":1}'
                ),
            ),
        ),
    ],
)
def test_pending_order_does_not_resume_expired_payment_credentials(
    app: object,
    payment_channel: str,
    snapshot_factory: object,
) -> None:
    with app.app_context():
        order = _seed_order(
            order_bid=f"expired-{payment_channel}-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel=payment_channel,
        )
        db.session.add(snapshot_factory(order))
        db.session.commit()

        assert _resume_pending_charge(app, order) is None


@pytest.mark.parametrize(
    ("provider", "snapshot_model", "raw_status", "provider_payload"),
    [
        (
            "alipay",
            AlipayOrder,
            "TRADE_SUCCESS",
            {"trade_status": "TRADE_SUCCESS", "total_amount": "200.00"},
        ),
        (
            "wechatpay",
            WechatPayOrder,
            "SUCCESS",
            {"trade_state": "SUCCESS", "amount": {"total": 20000}},
        ),
    ],
)
def test_native_success_during_repricing_completes_the_order(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    snapshot_model: object,
    raw_status: str,
    provider_payload: dict[str, object],
) -> None:
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu", lambda *_args: None
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    with app.app_context():
        order = _seed_order(
            order_bid=f"repricing-{provider}-order",
            status=ORDER_STATUS_REPRICING,
            payment_channel=provider,
        )
        prefix = "alipay" if provider == "alipay" else "wechatpay"
        snapshot = snapshot_model(
            **{
                f"{prefix}_order_bid": f"{provider}-snapshot",
                "biz_domain": "order",
                "order_bid": order.order_bid,
                "user_bid": order.user_bid,
                "shifu_bid": order.shifu_bid,
                "provider_attempt_id": f"{provider}-attempt",
                "amount": 20000,
                "currency": "CNY",
                "status": 0,
                "raw_status": "pending",
            }
        )
        db.session.add(snapshot)
        db.session.commit()
        order_bid = order.order_bid

    accepted = success_buy_record_from_native(
        app,
        provider,
        PaymentNotificationResult(
            order_bid=f"{provider}-attempt",
            status=raw_status,
            provider_payload=provider_payload,
            charge_id=f"{provider}-transaction",
        ),
    )

    assert accepted is True
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid=order_bid).one().status
            == ORDER_STATUS_SUCCESS
        )


def test_pingxx_success_during_repricing_completes_the_order(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_shifu_creator_bid", lambda *_args: "teacher"
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.set_shifu_context", lambda *_args: None
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu", lambda *_args: None
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    with app.app_context():
        order = _seed_order(
            order_bid="repricing-pingxx-order",
            status=ORDER_STATUS_REPRICING,
        )
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="repricing-pingxx-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                channel="wx_pub_qr",
                amount=20000,
                status=0,
                charge_id="ch_repricing",
                extra="{}",
                charge_object="{}",
            )
        )
        db.session.commit()
        order_bid = order.order_bid

    result = success_buy_record_from_pingxx(app, "ch_repricing", {"paid": True})

    assert result is not None
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid=order_bid).one().status
            == ORDER_STATUS_SUCCESS
        )


def test_coupon_closes_pending_attempt_before_repricing(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancelled: list[tuple[str, str]] = []

    class Provider:
        def cancel_payment(
            self,
            *,
            provider_reference: str,
            reference_type: str,
            app: object,
        ) -> SimpleNamespace:
            del app
            cancelled.append((provider_reference, reference_type))
            return SimpleNamespace(status="cancelled")

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    now = now_utc()
    with app.app_context():
        order = _seed_order(
            order_bid="coupon-reprices-pending-order",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add_all(
            [
                PingxxOrder(
                    pingxx_order_bid="coupon-pending-attempt",
                    biz_domain="order",
                    order_bid=order.order_bid,
                    user_bid=order.user_bid,
                    shifu_bid=order.shifu_bid,
                    channel="wx_pub_qr",
                    amount=20000,
                    status=0,
                    charge_id="ch_coupon_pending",
                    extra="{}",
                    charge_object='{"credential":{"wx_pub_qr":"https://pay.example/old"}}',
                ),
                PingxxOrder(
                    pingxx_order_bid="coupon-second-pending-attempt",
                    biz_domain="order",
                    order_bid=order.order_bid,
                    user_bid=order.user_bid,
                    shifu_bid=order.shifu_bid,
                    channel="wx_pub",
                    amount=20000,
                    status=0,
                    charge_id="ch_coupon_second_pending",
                    extra="{}",
                    charge_object='{"credential":{"wx_pub":{"package":"prepay_id=test"}}}',
                ),
                Coupon(
                    coupon_bid="coupon-reprice-fixed",
                    code="REPRICE20",
                    discount_type=COUPON_TYPE_FIXED,
                    value=Decimal("20.00"),
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
        db.session.commit()

    result = use_coupon_code(
        app,
        "owner-user",
        "REPRICE20",
        "coupon-reprices-pending-order",
    )

    assert cancelled == [
        ("ch_coupon_second_pending", "charge"),
        ("ch_coupon_pending", "charge"),
    ]
    assert result is not None
    assert result.value_to_pay == "180.00"
    with app.app_context():
        stored_order = Order.query.filter_by(
            order_bid="coupon-reprices-pending-order"
        ).one()
        stored_attempt = PingxxOrder.query.filter_by(
            pingxx_order_bid="coupon-pending-attempt"
        ).one()
        second_attempt = PingxxOrder.query.filter_by(
            pingxx_order_bid="coupon-second-pending-attempt"
        ).one()
        assert stored_order.status == ORDER_STATUS_INIT
        assert stored_order.paid_price == Decimal("180.00")
        assert stored_attempt.status == 3
        assert second_attempt.status == 3


def test_repricing_cancels_a_recoverable_failed_stripe_attempt(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancelled: list[tuple[str, str]] = []

    class Provider:
        def cancel_payment(self, **kwargs: object) -> SimpleNamespace:
            cancelled.append(
                (str(kwargs["provider_reference"]), str(kwargs["reference_type"]))
            )
            return SimpleNamespace(status="cancelled")

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    with app.app_context():
        order = _seed_order(
            order_bid="recoverable-stripe-repricing",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="stripe",
        )
        db.session.add(
            StripeOrder(
                stripe_order_bid="stripe-recoverable-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                payment_intent_id="pi_recoverable",
                amount=20000,
                currency="cny",
                status=4,
            )
        )
        db.session.commit()

    assert cancel_pending_payment_for_repricing(
        app,
        "recoverable-stripe-repricing",
        expected_user="owner-user",
    )
    assert cancelled == [("pi_recoverable", "payment_intent")]
    with app.app_context():
        assert (
            StripeOrder.query.filter_by(stripe_order_bid="stripe-recoverable-attempt")
            .one()
            .status
            == 3
        )


def test_repricing_does_not_close_a_completed_stripe_attempt(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Provider:
        def cancel_payment(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(status="completed")

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    with app.app_context():
        order = _seed_order(
            order_bid="completed-stripe-repricing",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="stripe",
        )
        db.session.add(
            StripeOrder(
                stripe_order_bid="stripe-completed-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                checkout_session_id="cs_completed",
                amount=20000,
                currency="cny",
                status=0,
            )
        )
        db.session.commit()

    with pytest.raises(AppError):
        cancel_pending_payment_for_repricing(
            app,
            "completed-stripe-repricing",
            expected_user="owner-user",
        )
    with app.app_context():
        assert (
            StripeOrder.query.filter_by(stripe_order_bid="stripe-completed-attempt")
            .one()
            .status
            == 0
        )
        assert (
            Order.query.filter_by(order_bid="completed-stripe-repricing").one().status
            == ORDER_STATUS_TO_BE_PAID
        )


def test_invalid_coupon_keeps_pending_attempt_active(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider_requested = False

    def fail_if_provider_requested(_name: str) -> object:
        nonlocal provider_requested
        provider_requested = True
        return object()

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        fail_if_provider_requested,
    )
    with app.app_context():
        order = _seed_order(
            order_bid="invalid-coupon-pending-order",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="invalid-coupon-active-attempt",
                biz_domain="order",
                order_bid=order.order_bid,
                user_bid=order.user_bid,
                shifu_bid=order.shifu_bid,
                channel="wx_pub_qr",
                amount=20000,
                status=0,
                charge_id="ch_still_active",
                extra="{}",
                charge_object='{"credential":{"wx_pub_qr":"https://pay.example/current"}}',
            )
        )
        db.session.commit()

    with pytest.raises(AppError, match="voucher code does not exist"):
        use_coupon_code(
            app,
            "owner-user",
            "DOES-NOT-EXIST",
            "invalid-coupon-pending-order",
        )

    assert provider_requested is False
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid="invalid-coupon-pending-order").one().status
            == ORDER_STATUS_TO_BE_PAID
        )
        assert (
            PingxxOrder.query.filter_by(
                pingxx_order_bid="invalid-coupon-active-attempt"
            )
            .one()
            .status
            == 0
        )


def test_invalid_coupon_does_not_clear_an_inherited_repricing_claim(
    app: object,
) -> None:
    with app.app_context():
        _seed_order(
            order_bid="inherited-repricing-order",
            status=ORDER_STATUS_REPRICING,
        )

    with pytest.raises(AppError, match="voucher code does not exist"):
        use_coupon_code(
            app,
            "owner-user",
            "DOES-NOT-EXIST",
            "inherited-repricing-order",
        )

    with app.app_context():
        assert (
            Order.query.filter_by(order_bid="inherited-repricing-order").one().status
            == ORDER_STATUS_REPRICING
        )


def test_payment_provider_work_stops_after_lifecycle_lock_ownership_is_lost(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[str] = []

    class Provider:
        def create_payment(self, **_kwargs: object) -> None:
            provider_calls.append("create")

        def cancel_payment(self, **_kwargs: object) -> None:
            provider_calls.append("cancel")

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_shifu_creator_bid", lambda *_args: "teacher"
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.set_shifu_context", lambda *_args: None
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_shifu_info",
        lambda *_args, **_kwargs: SimpleNamespace(
            bid="course-lock-lost-create",
            price=Decimal("200.00"),
            title="Course",
            description="Course",
        ),
    )
    with app.app_context():
        _seed_order(
            order_bid="lock-lost-create",
            status=ORDER_STATUS_INIT,
            payment_channel="alipay",
        )
        cancel_order = _seed_order(
            order_bid="lock-lost-cancel",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        db.session.add(
            PingxxOrder(
                pingxx_order_bid="lock-lost-cancel-attempt",
                biz_domain="order",
                order_bid=cancel_order.order_bid,
                user_bid=cancel_order.user_bid,
                shifu_bid=cancel_order.shifu_bid,
                channel="wx_pub_qr",
                amount=20000,
                status=0,
                charge_id="ch_lock_lost",
                extra="{}",
                charge_object="{}",
            )
        )
        db.session.commit()

    ownership_lost = Event()
    ownership_lost.set()
    token = _payment_lock_ownership_events.set((ownership_lost,))
    try:
        with pytest.raises(AppError):
            generate_charge(
                app,
                "lock-lost-create",
                "alipay_qr",
                "127.0.0.1",
                payment_channel="alipay",
                expected_user="owner-user",
            )
        with pytest.raises(AppError):
            cancel_pending_payment_for_repricing(
                app,
                "lock-lost-cancel",
                expected_user="owner-user",
            )
    finally:
        _payment_lock_ownership_events.reset(token)

    assert provider_calls == []


@pytest.mark.parametrize(
    "status",
    [
        ORDER_STATUS_SUCCESS,
        ORDER_STATUS_REFUND,
        ORDER_STATUS_TIMEOUT,
    ],
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
