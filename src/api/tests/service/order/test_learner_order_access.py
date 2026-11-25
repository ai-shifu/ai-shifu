"""Regression coverage for learner order ownership and mutable states."""

from datetime import UTC, timedelta, timezone
from decimal import Decimal
from threading import Event
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
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
    sync_native_payment_order,
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


def _seed_native_attempt(
    order: Order,
    provider: str,
    attempt: str,
    *,
    status: int,
) -> None:
    model = AlipayOrder if provider == "alipay" else WechatPayOrder
    db.session.add(
        model(
            **{
                f"{provider}_order_bid": f"{attempt}-snapshot",
                "biz_domain": "order",
                "order_bid": order.order_bid,
                "user_bid": order.user_bid,
                "shifu_bid": order.shifu_bid,
                "provider_attempt_id": attempt,
                "amount": 20000,
                "currency": "CNY",
                "status": status,
                "raw_status": "pending" if status == 0 else "closed",
            }
        )
    )


def _paid_payload(provider: str, paid_at: object) -> dict[str, object]:
    if paid_at.tzinfo is None:
        # now_utc() is naive UTC; astimezone() would read it as local time.
        paid_at = paid_at.replace(tzinfo=UTC)
    china = paid_at.astimezone(timezone(timedelta(hours=8)))
    if provider == "alipay":
        return {
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "200.00",
            "gmt_payment": china.strftime("%Y-%m-%d %H:%M:%S"),
        }
    return {
        "trade_state": "SUCCESS",
        "amount": {"total": 20000},
        "success_time": china.isoformat(timespec="seconds"),
    }


def _notify_paid(app: object, provider: str, attempt: str, paid_at: object) -> bool:
    return success_buy_record_from_native(
        app,
        provider,
        PaymentNotificationResult(
            order_bid=attempt,
            status="paid",
            provider_payload=_paid_payload(provider, paid_at),
            charge_id=f"{attempt}-transaction",
        ),
    )


def _quiet_order_side_effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    granted: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu",
        lambda _app, order_bid: granted.append(order_bid),
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    return granted


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
def test_paid_superseded_native_attempt_completes_the_order(
    app: object, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    """A code shown before switching payment method still grants the course."""
    granted = _quiet_order_side_effects(monkeypatch)
    with app.app_context():
        order = _seed_order(
            order_bid=f"superseded-{provider}-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        _seed_native_attempt(order, provider, f"{provider}-old", status=3)
        _seed_native_attempt(
            order, "wechatpay", f"wechatpay-latest-{provider}", status=0
        )
        db.session.commit()
        order_bid = order.order_bid

    assert _notify_paid(app, provider, f"{provider}-old", now_utc()) is True

    with app.app_context():
        assert Order.query.filter_by(order_bid=order_bid).one().status == (
            ORDER_STATUS_SUCCESS
        )
    assert granted == [order_bid]


@pytest.mark.parametrize("provider", ["alipay", "wechatpay"])
@pytest.mark.parametrize(
    ("paid_after_deadline", "expected_status"),
    [(False, ORDER_STATUS_SUCCESS), (True, ORDER_STATUS_TIMEOUT)],
)
def test_timed_out_order_accepts_only_payments_made_before_its_deadline(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    paid_after_deadline: bool,
    expected_status: int,
) -> None:
    _quiet_order_side_effects(monkeypatch)
    monkeypatch.setitem(app.config, "PAY_ORDER_EXPIRE_TIME", 1800)
    with app.app_context():
        order = _seed_order(
            order_bid=f"timeout-{provider}-{paid_after_deadline}",
            status=ORDER_STATUS_TIMEOUT,
            payment_channel=provider,
        )
        created_at = now_utc() - timedelta(hours=1)
        order.created_at = created_at.replace(tzinfo=None)
        _seed_native_attempt(
            order, provider, f"{provider}-late-{paid_after_deadline}", status=0
        )
        db.session.commit()
        order_bid = order.order_bid

    deadline = created_at + timedelta(seconds=1800)
    paid_at = deadline + timedelta(seconds=1 if paid_after_deadline else -60)
    _notify_paid(app, provider, f"{provider}-late-{paid_after_deadline}", paid_at)

    with app.app_context():
        assert Order.query.filter_by(order_bid=order_bid).one().status == (
            expected_status
        )


def test_second_paid_attempt_on_a_paid_order_is_not_granted_again(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    granted = _quiet_order_side_effects(monkeypatch)
    alerts: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_notify",
        lambda _app, title, msgs: alerts.append((title, msgs)),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _name: SimpleNamespace(cancel_payment=lambda **_kwargs: None),
    )
    with app.app_context():
        order = _seed_order(
            order_bid="double-paid-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        _seed_native_attempt(order, "alipay", "double-alipay", status=3)
        _seed_native_attempt(order, "wechatpay", "double-wechat", status=0)
        db.session.commit()

    assert _notify_paid(app, "wechatpay", "double-wechat", now_utc()) is True
    assert _notify_paid(app, "alipay", "double-alipay", now_utc()) is True
    assert _notify_paid(app, "alipay", "double-alipay", now_utc()) is True

    assert granted == ["double-paid-order"]
    assert len(alerts) == 1
    title, msgs = alerts[0]
    assert title == "重复支付告警"
    assert any("double-alipay" in line for line in msgs)
    assert any("double-alipay-transaction" in line for line in msgs)
    with app.app_context():
        snapshot = AlipayOrder.query.filter_by(
            provider_attempt_id="double-alipay"
        ).one()
        assert snapshot.status == 1


def test_paid_order_retires_open_orders_and_codes_for_the_same_course(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_order_side_effects(monkeypatch)
    closed: list[tuple[str, str]] = []

    def provider_for(name: str) -> object:
        def cancel_payment(**kwargs: object) -> None:
            closed.append((name, str(kwargs["provider_reference"])))

        return SimpleNamespace(cancel_payment=cancel_payment)

    monkeypatch.setattr("flaskr.service.order.funs.get_payment_provider", provider_for)
    with app.app_context():
        paid = _seed_order(
            order_bid="retire-paid-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        sibling = Order(
            order_bid="retire-sibling-order",
            shifu_bid=paid.shifu_bid,
            user_bid=paid.user_bid,
            payable_price=Decimal("200.00"),
            paid_price=Decimal("200.00"),
            payment_channel="alipay",
            status=ORDER_STATUS_TO_BE_PAID,
            deleted=0,
        )
        other_course = _seed_order(
            order_bid="retire-other-course-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        db.session.add(sibling)
        db.session.commit()
        _seed_native_attempt(paid, "wechatpay", "retire-paid-attempt", status=0)
        _seed_native_attempt(paid, "wechatpay", "retire-open-wechat", status=0)
        _seed_native_attempt(paid, "alipay", "retire-unscanned-alipay", status=3)
        _seed_native_attempt(sibling, "alipay", "retire-sibling-alipay", status=0)
        _seed_native_attempt(
            other_course, "wechatpay", "retire-other-course-wechat", status=0
        )
        db.session.commit()

    assert _notify_paid(app, "wechatpay", "retire-paid-attempt", now_utc()) is True

    assert sorted(closed) == [
        ("alipay", "retire-sibling-alipay"),
        ("wechatpay", "retire-open-wechat"),
    ]
    with app.app_context():
        statuses = {
            o.order_bid: o.status
            for o in Order.query.filter(Order.order_bid.like("retire-%")).all()
        }
        assert statuses == {
            "retire-paid-order": ORDER_STATUS_SUCCESS,
            "retire-sibling-order": ORDER_STATUS_TIMEOUT,
            "retire-other-course-order": ORDER_STATUS_TO_BE_PAID,
        }
        snapshots = {
            s.provider_attempt_id: s.status
            for model in (AlipayOrder, WechatPayOrder)
            for s in model.query.filter(
                model.provider_attempt_id.like("retire-%")
            ).all()
        }
        assert snapshots == {
            "retire-paid-attempt": 1,
            "retire-open-wechat": 3,
            "retire-unscanned-alipay": 3,
            "retire-sibling-alipay": 3,
            "retire-other-course-wechat": 0,
        }


def _capture_alerts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    titles: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_notify",
        lambda _app, title, _msgs: titles.append(title),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _name: SimpleNamespace(cancel_payment=lambda **_kwargs: None),
    )
    return titles


def test_on_time_payment_of_a_retired_sibling_is_a_duplicate(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sibling retired because the course was bought must not grant again."""
    granted = _quiet_order_side_effects(monkeypatch)
    alerts = _capture_alerts(monkeypatch)
    monkeypatch.setitem(app.config, "PAY_ORDER_EXPIRE_TIME", 1800)
    with app.app_context():
        paid = _seed_order(
            order_bid="retired-paid-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        sibling = Order(
            order_bid="retired-sibling-order",
            shifu_bid=paid.shifu_bid,
            user_bid=paid.user_bid,
            payable_price=Decimal("200.00"),
            paid_price=Decimal("200.00"),
            payment_channel="alipay",
            status=ORDER_STATUS_TO_BE_PAID,
            deleted=0,
        )
        db.session.add(sibling)
        db.session.commit()
        _seed_native_attempt(paid, "wechatpay", "retired-paid-attempt", status=0)
        _seed_native_attempt(sibling, "alipay", "retired-sibling-attempt", status=0)
        db.session.commit()

    assert _notify_paid(app, "wechatpay", "retired-paid-attempt", now_utc())
    assert _notify_paid(app, "alipay", "retired-sibling-attempt", now_utc())

    assert granted == ["retired-paid-order"]
    assert alerts == ["重复支付告警"]
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid="retired-sibling-order").one().status
            == ORDER_STATUS_TIMEOUT
        )


def _sync_paid(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    order_bid: str,
    attempt: str,
    paid_at: object,
) -> None:
    payload = _paid_payload("wechatpay", paid_at)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _name: SimpleNamespace(
            sync_reference=lambda **_kwargs: PaymentNotificationResult(
                order_bid=attempt,
                status="SUCCESS",
                provider_payload=payload,
                charge_id=f"{attempt}-transaction",
            ),
            cancel_payment=lambda **_kwargs: None,
        ),
    )
    sync_native_payment_order(app, order_bid, payment_channel="wechatpay")


def test_sync_uses_the_webhook_gate_for_late_payments(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    granted = _quiet_order_side_effects(monkeypatch)
    alerts = _capture_alerts(monkeypatch)
    monkeypatch.setitem(app.config, "PAY_ORDER_EXPIRE_TIME", 1800)
    with app.app_context():
        order = _seed_order(
            order_bid="sync-late-order",
            status=ORDER_STATUS_TIMEOUT,
            payment_channel="wechatpay",
        )
        created_at = now_utc() - timedelta(hours=1)
        order.created_at = created_at
        _seed_native_attempt(order, "wechatpay", "sync-late-attempt", status=0)
        db.session.commit()

    deadline = created_at + timedelta(seconds=1800)
    _sync_paid(
        app,
        monkeypatch,
        "sync-late-order",
        "sync-late-attempt",
        deadline + timedelta(seconds=1),
    )

    assert granted == []
    assert alerts == ["支付未入账告警"]
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid="sync-late-order").one().status
            == ORDER_STATUS_TIMEOUT
        )


def test_sync_rejects_a_code_priced_before_the_order_changed(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    granted = _quiet_order_side_effects(monkeypatch)
    alerts = _capture_alerts(monkeypatch)
    with app.app_context():
        order = _seed_order(
            order_bid="sync-repriced-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        _seed_native_attempt(order, "wechatpay", "sync-repriced-attempt", status=0)
        order.paid_price = Decimal("250.00")
        db.session.commit()

    _sync_paid(
        app, monkeypatch, "sync-repriced-order", "sync-repriced-attempt", now_utc()
    )

    assert granted == []
    assert alerts == ["支付未入账告警"]
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid="sync-repriced-order").one().status
            == ORDER_STATUS_TO_BE_PAID
        )


def test_failed_close_after_payment_keeps_the_purchase(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    granted = _quiet_order_side_effects(monkeypatch)

    def failing_cancel(**_kwargs: object) -> None:
        message = "provider unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _name: SimpleNamespace(cancel_payment=failing_cancel),
    )
    with app.app_context():
        order = _seed_order(
            order_bid="close-fails-order",
            status=ORDER_STATUS_TO_BE_PAID,
            payment_channel="wechatpay",
        )
        _seed_native_attempt(order, "wechatpay", "close-fails-paid", status=0)
        _seed_native_attempt(order, "wechatpay", "close-fails-open", status=0)
        db.session.commit()

    assert _notify_paid(app, "wechatpay", "close-fails-paid", now_utc()) is True

    assert granted == ["close-fails-order"]
    with app.app_context():
        assert Order.query.filter_by(order_bid="close-fails-order").one().status == (
            ORDER_STATUS_SUCCESS
        )
        assert (
            WechatPayOrder.query.filter_by(provider_attempt_id="close-fails-open")
            .one()
            .status
            == 0
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

    with pytest.raises(AppError) as error:
        use_coupon_code(
            app,
            "owner-user",
            "DOES-NOT-EXIST",
            "invalid-coupon-pending-order",
        )
    # Asserted by code: the learner-facing wording is translated copy.
    assert error.value.code == ERROR_CODE["server.discount.discountNotFound"]

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

    with pytest.raises(AppError) as error:
        use_coupon_code(
            app,
            "owner-user",
            "DOES-NOT-EXIST",
            "inherited-repricing-order",
        )
    # Asserted by code: the learner-facing wording is translated copy.
    assert error.value.code == ERROR_CODE["server.discount.discountNotFound"]

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
