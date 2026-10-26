"""Verify Ping++ JSAPI charges refuse to run without a bound WeChat openid."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.order import funs as order_funs
from flaskr.service.order.consts import ORDER_STATUS_INIT
from flaskr.service.order.models import Order
from flaskr.service.order.payment_providers.base import PaymentCreationResult

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.order.payment_providers import PaymentRequest

WECHAT_OPEN_ID_REQUIRED_CODE = 5002


class _RecordingProvider:
    """Capture the charge payload instead of calling Ping++."""

    def __init__(self) -> None:
        self.requests: list[PaymentRequest] = []

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        del app
        self.requests.append(request)
        return PaymentCreationResult(
            provider_reference="ch_test",
            raw_response={
                "id": "ch_test",
                "order_no": request.order_bid,
                "app": "app_test",
                "channel": request.channel,
                "currency": request.currency,
                "subject": request.subject,
                "body": request.body,
                "client_ip": request.client_ip,
                "extra": request.extra.get("charge_extra", {}),
                "credential": {"wx_pub": {"package": "prepay_id=test"}},
            },
        )


@pytest.fixture
def pingxx_provider(monkeypatch: pytest.MonkeyPatch) -> _RecordingProvider:
    provider = _RecordingProvider()
    monkeypatch.setattr(order_funs, "get_payment_provider", lambda _name: provider)
    monkeypatch.setattr(order_funs, "get_config", lambda *_args, **_kwargs: "app_test")
    return provider


def _make_order(creator_bid: str = "") -> Order:
    return Order(
        order_bid="order-jsapi-openid",
        shifu_bid="shifu-jsapi-openid",
        user_bid="user-jsapi-openid",
        creator_bid=creator_bid,
        payable_price=Decimal("10.00"),
        paid_price=Decimal("10.00"),
        status=ORDER_STATUS_INIT,
    )


def _generate(app: Flask, creator_bid: str = "") -> object:
    return order_funs._generate_pingxx_charge(
        app=app,
        buy_record=_make_order(creator_bid),
        course=SimpleNamespace(bid="shifu-jsapi-openid", title="Course"),
        channel="wx_pub",
        client_ip="127.0.0.1",
        amount=1000,
        subject="Course",
        body="Course",
        order_no="order-jsapi-openid",
    )


class _UserStub:
    """Stand in for the user aggregate, recording which app was asked about."""

    def __init__(self, open_ids: dict[str, str | None]) -> None:
        self._open_ids = open_ids
        self.requested_app_ids: list[str] = []

    def wechat_open_id_for_app(self, app_id: str = "") -> str | None:
        self.requested_app_ids.append(app_id)
        return self._open_ids.get(app_id)

    @property
    def wechat_open_id(self) -> str | None:
        return self.wechat_open_id_for_app()


@pytest.mark.parametrize("open_id", ["", "   ", None])
def test_jsapi_charge_rejects_missing_open_id(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
    open_id: str | None,
) -> None:
    monkeypatch.setattr(
        order_funs,
        "load_user_aggregate",
        lambda _user_bid: _UserStub({"": open_id}),
    )

    with app.app_context(), pytest.raises(AppError) as excinfo:
        _generate(app)

    assert excinfo.value.code == WECHAT_OPEN_ID_REQUIRED_CODE
    assert pingxx_provider.requests == []


def test_jsapi_charge_rejects_unknown_user(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
) -> None:
    monkeypatch.setattr(order_funs, "load_user_aggregate", lambda _user_bid: None)

    with app.app_context(), pytest.raises(AppError) as excinfo:
        _generate(app)

    assert excinfo.value.code == WECHAT_OPEN_ID_REQUIRED_CODE
    assert pingxx_provider.requests == []


def test_jsapi_charge_sends_bound_open_id(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
) -> None:
    monkeypatch.setattr(
        order_funs,
        "load_user_aggregate",
        lambda _user_bid: _UserStub({"": "  o_test_openid  "}),
    )

    with app.app_context():
        result = _generate(app)

    assert len(pingxx_provider.requests) == 1
    assert pingxx_provider.requests[0].extra["charge_extra"] == {
        "open_id": "o_test_openid"
    }
    assert result.payment_channel == "pingxx"
    assert result.payment_payload["credential"] == {
        "wx_pub": {"package": "prepay_id=test"}
    }


def test_jsapi_charge_uses_the_creator_own_wechat_app(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
) -> None:
    """A learner of a creator with their own official account holds its open ID."""
    user = _UserStub({"": "o_platform", "wx-creator-app": "o_creator"})
    monkeypatch.setattr(order_funs, "load_user_aggregate", lambda _user_bid: user)
    monkeypatch.setattr(
        order_funs,
        "resolve_creator_wechat_oauth_app_id",
        lambda _creator_bid: "wx-creator-app",
    )

    with app.app_context():
        _generate(app, creator_bid="creator-with-wechat")

    assert user.requested_app_ids == ["wx-creator-app"]
    assert pingxx_provider.requests[0].extra["charge_extra"] == {"open_id": "o_creator"}


def test_jsapi_charge_falls_back_to_the_platform_app_when_resolution_fails(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
) -> None:
    """A broken lookup must not add a new failure path to a money flow."""

    def _explode(_creator_bid: str) -> str:
        message = "integration lookup failed"
        raise RuntimeError(message)

    user = _UserStub({"": "o_platform"})
    monkeypatch.setattr(order_funs, "load_user_aggregate", lambda _user_bid: user)
    monkeypatch.setattr(order_funs, "resolve_creator_wechat_oauth_app_id", _explode)

    with app.app_context():
        _generate(app, creator_bid="creator-with-broken-integration")

    assert user.requested_app_ids == [""]
    assert pingxx_provider.requests[0].extra["charge_extra"] == {
        "open_id": "o_platform"
    }


def test_jsapi_charge_refuses_a_foreign_apps_open_id(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    pingxx_provider: _RecordingProvider,
) -> None:
    """Charging a creator's app with a platform open ID would be rejected."""
    user = _UserStub({"": "o_platform"})
    monkeypatch.setattr(order_funs, "load_user_aggregate", lambda _user_bid: user)
    monkeypatch.setattr(
        order_funs,
        "resolve_creator_wechat_oauth_app_id",
        lambda _creator_bid: "wx-creator-app",
    )

    with app.app_context(), pytest.raises(AppError) as excinfo:
        _generate(app, creator_bid="creator-with-wechat")

    assert excinfo.value.code == WECHAT_OPEN_ID_REQUIRED_CODE
    assert pingxx_provider.requests == []
