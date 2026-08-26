"""Verify billing Ping++ JSAPI options refuse a missing WeChat openid."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr.service.billing import checkout as billing_checkout
from flaskr.service.common.models import AppError

WECHAT_OPEN_ID_REQUIRED_CODE = 5002


def _build(channel: str) -> dict:
    return billing_checkout._build_pingxx_provider_options(
        creator_bid="creator-jsapi-openid",
        product=SimpleNamespace(product_bid="product-jsapi-openid"),
        channel=channel,
    )


@pytest.fixture(autouse=True)
def _stub_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        billing_checkout, "get_config", lambda *_args, **_kwargs: "app_test"
    )


@pytest.mark.parametrize("open_id", ["", "   ", None])
def test_jsapi_options_reject_missing_open_id(
    monkeypatch: pytest.MonkeyPatch, open_id: str | None
) -> None:
    monkeypatch.setattr(
        billing_checkout,
        "load_user_aggregate",
        lambda _creator_bid: SimpleNamespace(wechat_open_id=open_id),
    )

    with pytest.raises(AppError) as excinfo:
        _build("wx_pub")

    assert excinfo.value.code == WECHAT_OPEN_ID_REQUIRED_CODE


def test_jsapi_options_reject_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        billing_checkout, "load_user_aggregate", lambda _creator_bid: None
    )

    with pytest.raises(AppError) as excinfo:
        _build("wx_pub")

    assert excinfo.value.code == WECHAT_OPEN_ID_REQUIRED_CODE


def test_jsapi_options_pass_bound_open_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        billing_checkout,
        "load_user_aggregate",
        lambda _creator_bid: SimpleNamespace(wechat_open_id="  o_test_openid  "),
    )

    assert _build("wx_pub")["charge_extra"] == {"open_id": "o_test_openid"}


def test_qr_options_do_not_need_open_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(_creator_bid: str) -> None:
        message = "QR channels must not load the user aggregate"
        raise AssertionError(message)

    monkeypatch.setattr(billing_checkout, "load_user_aggregate", _fail)

    assert _build("wx_pub_qr")["charge_extra"] == {"product_id": "product-jsapi-openid"}
    assert _build("alipay_qr")["charge_extra"] == {}
