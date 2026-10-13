"""Freeze billing terms at the existing Stripe adapter entry before decoupling."""

from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.service.billing import checkout
from flaskr.service.order import payment_providers
from flaskr.service.order.payment_providers.base import (
    PaymentCreationResult,
    PaymentProvider,
    PaymentRequest,
)
from flaskr.service.order.payment_providers.contracts import (
    PaymentCapabilities,
    PaymentDefinition,
    PaymentRoute,
)


@pytest.mark.parametrize("mode", ["payment", "subscription"])
@pytest.mark.parametrize(
    ("payable", "coupon"),
    [(990, ""), (500, ""), (500, "coupon-once"), (0, "coupon-free")],
)
def test_checkout_preserves_price_discount_and_contract_terms(
    monkeypatch: pytest.MonkeyPatch, mode: str, payable: int, coupon: str
) -> None:
    """Verify exact externally observable request semantics, not helper structure."""
    mapping = SimpleNamespace(
        provider_price_id="price-original",
        unit_amount=990,
    )
    monkeypatch.setattr(
        checkout, "_resolve_checkout_product_name", lambda _product: "Monthly plan"
    )
    monkeypatch.setattr(
        checkout,
        "_stored_provider_price_snapshot_matches_mapping",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        checkout,
        "_build_provider_price_order_metadata",
        lambda _mapping: {"provider_price_bid": "mapping-original"},
    )
    monkeypatch.setattr(
        checkout,
        "build_payment_result_url",
        lambda _path, *, canceled=False: (
            "https://app.test/result" + ("?canceled=1" if canceled else "")
        ),
    )
    order = SimpleNamespace(
        bill_order_bid="bill-original",
        payable_amount=payable,
        currency="USD",
        metadata_json={
            "provider_price_bid": "mapping-original",
            "campaign_provider_discount": {
                "provider_coupon_id": coupon,
                "campaign_provider_discount_bid": "discount-original",
            },
        },
    )
    result = checkout._build_provider_checkout_request(
        Flask(__name__),
        creator_bid="teacher-original",
        order=order,
        product=SimpleNamespace(product_bid="product-original"),
        payment_provider="stripe",
        payment_mode=mode,
        channel="checkout_session",
        provider_price_mapping=mapping,
    )
    request = result.payment_request
    metadata = {
        "bill_order_bid": "bill-original",
        "creator_bid": "teacher-original",
        "product_bid": "product-original",
        "provider_price_bid": "mapping-original",
    }
    expected = {
        "metadata": metadata,
        "mode": "checkout_session",
        "success_url": "https://app.test/result?bill_order_bid=bill-original",
        "cancel_url": "https://app.test/result?canceled=1&bill_order_bid=bill-original",
        "session_params": {"mode": mode},
        "line_items": [{"price": "price-original", "quantity": 1}],
    }
    if coupon:
        metadata["campaign_provider_discount_bid"] = "discount-original"
        expected["discounts"] = [{"coupon": coupon}]
    if mode == "subscription":
        expected["session_params"].update(
            payment_method_collection="always", subscription_data={"metadata": metadata}
        )
        if payable < 990 and not coupon:
            expected["subscription_one_time_discount_amount"] = 990 - payable
    assert request.extra == expected
    assert (
        request.amount,
        request.currency,
        request.payment_mode,
        request.biz_domain,
    ) == (payable, "usd", mode, "billing")
    assert (request.order_bid, request.user_bid) == (
        "bill-original",
        "teacher-original",
    )


def test_new_catalog_adapter_receives_price_and_discount_without_a_business_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect the counterexample that failed before completing the shared checkout boundary."""

    class OtherCatalogProvider(PaymentProvider):
        channel = "another-catalog"
        definition = PaymentDefinition(
            capabilities=PaymentCapabilities(catalog=True, discounts=True),
            routes=(PaymentRoute("offer", "hosted", "redirect", "hosted"),),
        )

        @classmethod
        def checkout_options(cls, terms: object) -> dict:
            return {
                "offer": terms.price_reference,
                "promotion": terms.discount_reference,
            }

        def create_payment(
            self, *, request: PaymentRequest, app: object
        ) -> PaymentCreationResult:
            del request, app
            message = "Building a request must never call the gateway"
            raise AssertionError(message)

    monkeypatch.setattr(
        payment_providers,
        "_PROVIDER_REGISTRY",
        dict(payment_providers._PROVIDER_REGISTRY),
    )
    payment_providers.register_payment_provider(OtherCatalogProvider)
    monkeypatch.setattr(checkout, "_resolve_checkout_product_name", lambda _: "Plan")
    monkeypatch.setattr(
        checkout,
        "_stored_provider_price_snapshot_matches_mapping",
        lambda *_, **__: True,
    )
    monkeypatch.setattr(checkout, "_build_provider_price_order_metadata", lambda _: {})
    monkeypatch.setattr(
        checkout, "build_payment_result_url", lambda *_, **__: "https://app.test/result"
    )
    result = checkout._build_provider_checkout_request(
        Flask(__name__),
        creator_bid="teacher",
        order=SimpleNamespace(
            bill_order_bid="bill",
            payable_amount=500,
            currency="USD",
            metadata_json={
                "campaign_provider_discount": {"provider_coupon_id": "promotion-native"}
            },
        ),
        product=SimpleNamespace(product_bid="product"),
        payment_provider="another-catalog",
        payment_mode="subscription",
        channel="offer",
        provider_price_mapping=SimpleNamespace(
            provider_price_id="offer-native", unit_amount=1000
        ),
    )
    assert result.payment_request.extra == {
        "offer": "offer-native",
        "promotion": "promotion-native",
    }
