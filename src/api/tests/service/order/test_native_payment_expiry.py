"""Native payment codes must expire no later than the order they pay for."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.service.order import funs
from flaskr.service.order.payment_providers import alipay, wechatpay
from flaskr.service.order.payment_providers.base import (
    PaymentRequest,
    PaymentWindowExpiredError,
    payment_request_expires_at,
)


def _request(**extra: object) -> PaymentRequest:
    return PaymentRequest(
        order_bid="native-attempt-test",
        user_bid="user-test",
        shifu_bid="course-test",
        amount=10,
        channel="wx_pub_qr",
        currency="CNY",
        subject="",
        body="",
        client_ip="127.0.0.1",
        extra=dict(extra),
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def test_expires_at_treats_naive_values_as_utc() -> None:
    naive = dt.datetime(2099, 1, 1, 0, 0, 0)
    aware = dt.datetime(2099, 1, 1, 8, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))

    assert payment_request_expires_at(_request(expires_at=naive)) == naive.replace(
        tzinfo=dt.UTC
    )
    assert payment_request_expires_at(_request(expires_at=aware)) == naive.replace(
        tzinfo=dt.UTC
    )
    assert payment_request_expires_at(_request()) is None
    assert payment_request_expires_at(_request(expires_at="2099-01-01")) is None


def test_wechat_time_expire_uses_the_order_deadline_in_china_time() -> None:
    request = _request(expires_at=dt.datetime(2099, 1, 1, 0, 0, 0))

    assert wechatpay._time_expire(request) == "2099-01-01T08:00:00+08:00"


@pytest.mark.parametrize(
    "remaining", [dt.timedelta(seconds=59), dt.timedelta(minutes=-5)]
)
def test_wechat_rejects_orders_without_a_full_minute_left(
    remaining: dt.timedelta,
) -> None:
    request = _request(expires_at=_utcnow() + remaining)

    with pytest.raises(PaymentWindowExpiredError):
        wechatpay._time_expire(request)


def test_wechat_time_expire_never_extends_a_short_window() -> None:
    deadline = (_utcnow() + dt.timedelta(seconds=90)).replace(microsecond=0)

    value = wechatpay._time_expire(_request(expires_at=deadline))

    assert dt.datetime.fromisoformat(value) == deadline


def test_wechat_body_omits_time_expire_without_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "WECHATPAY_APP_ID": "wx-test",
        "WECHATPAY_MCH_ID": "mch-test",
        "WECHATPAY_WEBHOOK_URL": "https://payments.example.test/wechatpay",
    }
    monkeypatch.setattr(
        wechatpay, "get_config", lambda key, default="": config.get(key, default)
    )
    provider = wechatpay.WechatPayProvider()

    assert "time_expire" not in provider._build_transaction_body(_request())
    body = provider._build_transaction_body(
        _request(expires_at=dt.datetime(2099, 1, 1))
    )
    assert body["time_expire"] == "2099-01-01T08:00:00+08:00"


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (dt.timedelta(minutes=29, seconds=40), "29m"),
        (dt.timedelta(seconds=90), "1m"),
    ],
)
def test_alipay_timeout_rounds_down_to_the_order_deadline(
    remaining: dt.timedelta, expected: str
) -> None:
    request = _request(expires_at=_utcnow() + remaining)

    assert alipay._timeout_express(request) == expected


@pytest.mark.parametrize(
    "remaining", [dt.timedelta(seconds=30), dt.timedelta(minutes=-5)]
)
def test_alipay_rejects_orders_without_a_full_minute_left(
    remaining: dt.timedelta,
) -> None:
    with pytest.raises(PaymentWindowExpiredError):
        alipay._timeout_express(_request(expires_at=_utcnow() + remaining))


def test_alipay_timeout_keeps_explicit_and_default_values() -> None:
    deadline = _utcnow() + dt.timedelta(minutes=29)

    assert alipay._timeout_express(_request(timeout_express="5m")) == "5m"
    assert (
        alipay._timeout_express(_request(timeout_express="5m", expires_at=deadline))
        == "5m"
    )
    assert alipay._timeout_express(_request()) == "15m"


def test_course_order_deadline_follows_pay_order_expire_time() -> None:
    app = Flask(__name__)
    app.config["PAY_ORDER_EXPIRE_TIME"] = 1800
    order = SimpleNamespace(created_at=dt.datetime(2026, 11, 25, 1, 9, 42))

    assert funs._order_payment_expires_at(app, order) == dt.datetime(
        2026, 11, 25, 1, 39, 42, tzinfo=dt.UTC
    )
    assert funs._order_payment_expires_at(app, SimpleNamespace(created_at=None)) is None
    app.config["PAY_ORDER_EXPIRE_TIME"] = None
    assert funs._order_payment_expires_at(app, order) is None


class _OrderPayExpiredError(Exception):
    pass


def _raise_key(key: str) -> None:
    raise _OrderPayExpiredError(key)


def test_course_payment_rejects_orders_in_their_last_minute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(funs, "raise_error", _raise_key)
    app = Flask(__name__)
    app.config["PAY_ORDER_EXPIRE_TIME"] = 1800
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    fresh = SimpleNamespace(created_at=now - dt.timedelta(minutes=5))
    closing = SimpleNamespace(created_at=now - dt.timedelta(minutes=29, seconds=30))

    assert funs._native_payment_expires_at(app, fresh) is not None
    with pytest.raises(_OrderPayExpiredError, match=r"server\.order\.orderPayExpired"):
        funs._native_payment_expires_at(app, closing)
