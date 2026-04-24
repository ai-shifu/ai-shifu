from decimal import Decimal
from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.common.models import AppException
from flaskr.service.order.consts import ORDER_STATUS_INIT
from flaskr.service.order.funs import BuyRecordDTO, generate_charge
from flaskr.service.order.models import Order


def test_generate_charge_uses_pingxx_channel(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    order_bid = "order-wx-pub-1"
    course_bid = "course-wx-pub-1"
    user_bid = "user-wx-pub-1"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("10.00"),
            paid_price=Decimal("10.00"),
            status=ORDER_STATUS_INIT,
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            bid=course_bid, title="Course", description="Desc"
        ),
    )

    captured = {}

    def fake_generate_pingxx_charge(**kwargs):
        captured.update(kwargs)
        return BuyRecordDTO(
            kwargs["buy_record"].order_bid,
            kwargs["buy_record"].user_bid,
            kwargs["buy_record"].paid_price,
            kwargs["channel"],
            "qr-url",
            payment_channel="pingxx",
        )

    monkeypatch.setattr(
        order_funs, "_generate_pingxx_charge", fake_generate_pingxx_charge
    )

    result = generate_charge(
        app,
        order_bid,
        "wx_wap",
        "127.0.0.1",
        return_url="https://example.com/payment/pingxx/result?order_id=order-wx-pub-1",
    )
    assert result.channel == "wx_wap"
    assert result.payment_channel == "pingxx"
    assert captured["channel"] == "wx_wap"
    assert (
        captured["return_url"]
        == "https://example.com/payment/pingxx/result?order_id=order-wx-pub-1"
    )


def test_generate_charge_returns_redirect_url_for_wx_wap(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    order_bid = "order-wx-wap-1"
    course_bid = "course-wx-wap-1"
    user_bid = "user-wx-wap-1"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("10.00"),
            paid_price=Decimal("10.00"),
            status=ORDER_STATUS_INIT,
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            bid=course_bid, title="Course", description="Desc"
        ),
    )

    class FakeProvider:
        def create_payment(self, *, request, app):
            _ = app
            return SimpleNamespace(
                raw_response={
                    "id": "charge-1",
                    "order_no": request.order_bid,
                    "app": "app-1",
                    "channel": request.channel,
                    "currency": request.currency,
                    "subject": request.subject,
                    "body": request.body,
                    "client_ip": request.client_ip,
                    "extra": {},
                    "credential": {"wx_wap": "https://pay.example.com/wx-wap-session"},
                }
            )

    monkeypatch.setattr(
        order_funs, "get_payment_provider", lambda _channel: FakeProvider()
    )

    result = generate_charge(app, order_bid, "wx_wap", "127.0.0.1")

    assert result.qr_url == "https://pay.example.com/wx-wap-session"
    assert (
        result.payment_payload["redirect_url"]
        == "https://pay.example.com/wx-wap-session"
    )
    assert result.payment_payload["qr_url"] == ""


def test_generate_charge_passes_cancel_url_for_alipay_wap(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    order_bid = "order-alipay-wap-1"
    course_bid = "course-alipay-wap-1"
    user_bid = "user-alipay-wap-1"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("10.00"),
            paid_price=Decimal("10.00"),
            status=ORDER_STATUS_INIT,
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            bid=course_bid, title="Course", description="Desc"
        ),
    )

    captured = {}

    class FakeProvider:
        def create_payment(self, *, request, app):
            _ = app
            captured["extra"] = request.extra
            return SimpleNamespace(
                raw_response={
                    "id": "charge-2",
                    "order_no": request.order_bid,
                    "app": "app-1",
                    "channel": request.channel,
                    "currency": request.currency,
                    "subject": request.subject,
                    "body": request.body,
                    "client_ip": request.client_ip,
                    "extra": request.extra.get("charge_extra", {}),
                    "credential": {
                        "alipay_wap": "https://pay.example.com/alipay-wap-session"
                    },
                }
            )

    monkeypatch.setattr(
        order_funs, "get_payment_provider", lambda _channel: FakeProvider()
    )

    result = generate_charge(
        app,
        order_bid,
        "alipay_wap",
        "127.0.0.1",
        return_url="https://example.com/payment/pingxx/result?order_id=order-alipay-wap-1",
        cancel_url="https://example.com/c/course-alipay-wap-1",
    )

    assert captured["extra"]["charge_extra"] == {
        "success_url": "https://example.com/payment/pingxx/result?order_id=order-alipay-wap-1",
        "cancel_url": "https://example.com/c/course-alipay-wap-1",
    }
    assert result.qr_url == "https://pay.example.com/alipay-wap-session"
    assert (
        result.payment_payload["redirect_url"]
        == "https://pay.example.com/alipay-wap-session"
    )


def test_generate_charge_requires_return_url_for_alipay_wap(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    order_bid = "order-alipay-wap-missing-return"
    course_bid = "course-alipay-wap-missing-return"
    user_bid = "user-alipay-wap-missing-return"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("10.00"),
            paid_price=Decimal("10.00"),
            status=ORDER_STATUS_INIT,
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            bid=course_bid, title="Course", description="Desc"
        ),
    )

    with pytest.raises(AppException):
        generate_charge(app, order_bid, "alipay_wap", "127.0.0.1")
