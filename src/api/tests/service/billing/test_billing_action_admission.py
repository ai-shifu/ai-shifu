"""Advertise and accept only actions implemented by the billing browser."""

from dataclasses import replace

import pytest
from flask import Flask
from flaskr.service.billing import checkout
from flaskr.service.billing.models import BillingOrder
from flaskr.service.config import config_overrides
from flaskr.service.order.payment_providers.options import configured_payment_options

from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.mark.parametrize("scene", ["qr", "hosted", "embedded"])
@pytest.mark.parametrize("action", ["qr", "redirect", "jsapi", "sdk_confirm", "none"])
def test_billing_route_listing_operations_and_explicit_checkout_agree_with_ui_actions(
    integration_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    scene: str,
    action: str,
) -> None:
    app = integration_app
    definition = FixtureProvider.definition
    route = replace(definition.routes[0], scene=scene, action=action)
    monkeypatch.setattr(
        FixtureProvider, "definition", replace(definition, routes=(route,))
    )
    allowed = scene in {"qr", "hosted"} and action in {"qr", "redirect"}
    option_id = f"fixture-pay:{route.channel}"
    options = configured_payment_options(biz_domain="billing")
    assert any(option.id == option_id for option in options) == allowed
    with app.test_client() as client:
        catalog = client.get("/api/billing/catalog").get_json(force=True)
        assert catalog["code"] == 0, catalog
        assert (
            any(
                option["id"] == option_id
                for option in catalog["data"]["payment_options"]
            )
            == allowed
        )
        for operation in catalog["data"]["checkout_operations"].values():
            assert (option_id in operation["option_ids"]) == allowed
        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": option_id,
            },
        ).get_json(force=True)
    if allowed:
        assert response["code"] == 0, response
        assert response["data"]["payment_action"]["type"] in {"qr", "redirect"}
        assert len(FixtureProvider.calls) == 1
    else:
        assert response["code"] != 0, response
        assert FixtureProvider.calls == []
        assert BillingOrder.query.count() == 0


def test_billing_filter_keeps_existing_stripe_modes_and_learner_sdk_jsapi_options(
    integration_app: Flask,
) -> None:
    del integration_app
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": "stripe,wechatpay", "STRIPE_ENABLED": True}
    ):
        billing = configured_payment_options(biz_domain="billing")
        learner = configured_payment_options(biz_domain="order")
    assert any(
        option.id == "stripe:checkout_session" and option.action == "redirect"
        for option in billing
    )
    assert any(
        option.id == "stripe:payment_intent" and option.action == "sdk_confirm"
        for option in learner
    )
    assert any(
        option.provider == "wechatpay" and option.action == "jsapi"
        for option in learner
    )
    assert all(option.action in {"redirect", "qr"} for option in billing)


def test_legacy_explicit_channel_selection_keeps_its_existing_transport_contract(
    integration_app: Flask,
) -> None:
    del integration_app
    # Existing API clients can own JSAPI execution outside the teacher web UI.
    with config_overrides({"PAYMENT_CHANNELS_ENABLED": "wechatpay"}):
        assert checkout._resolve_billing_payment_channel(
            {"payment_provider": "wechatpay", "channel": "wx_pub"},
            default_pingxx_channel="alipay_qr",
        ) == ("wechatpay", "wx_pub")
