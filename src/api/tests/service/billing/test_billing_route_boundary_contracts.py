"""Verify HTTP authorization, route-owned identity, and provider error contracts."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import Mock

import pytest
from flaskr.service.billing import routes
from flaskr.service.billing.campaign_provider_discounts import (
    CampaignProviderDiscountError,
)
from flaskr.service.billing.provider_price_mappings import ProviderPriceMappingError

from tests.service.billing import test_admin_billing_routes as route_fixtures

admin_billing_client = route_fixtures.admin_billing_client


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize(
    ("method", "suffix", "handler", "expected_tail"),
    [
        (
            "POST",
            "/domains",
            "manage_creator_domain_binding",
            ({"host": "learn.example.test", "action": "bind"},),
        ),
        (
            "POST",
            "/domains/binding-test/verify",
            "manage_creator_domain_binding",
            (
                {
                    "host": "learn.example.test",
                    "action": "verify",
                    "domain_binding_bid": "binding-test",
                },
            ),
        ),
        (
            "DELETE",
            "/domains/binding-test",
            "manage_creator_domain_binding",
            ({"action": "disable", "domain_binding_bid": "binding-test"},),
        ),
        (
            "PUT",
            "/integrations/wechat",
            "save_creator_integration",
            ("wechat", {"host": "learn.example.test", "action": "caller-controlled"}),
        ),
        (
            "POST",
            "/integrations/wechat/verify",
            "verify_creator_integration",
            ("wechat", ""),
        ),
        ("DELETE", "/integrations/wechat", "disable_creator_integration", ("wechat",)),
    ],
)
def test_customization_routes_own_action_and_identity(
    admin: bool,
    method: str,
    suffix: str,
    handler: str,
    expected_tail: tuple,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock(return_value={"status": "saved"})
    monkeypatch.setattr(routes, handler, service)
    monkeypatch.setattr(routes, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        routes,
        "_resolve_existing_admin_billing_target_user_bid",
        lambda **kwargs: kwargs["creator_bid"],
    )
    prefix = (
        "/api/admin/billing/customization/target-teacher"
        if admin
        else "/api/billing/customization"
    )
    response = admin_billing_client["client"].open(
        prefix + suffix,
        method=method,
        json={"host": "learn.example.test", "action": "caller-controlled"},
        headers={"X-User-Id": "signed-in-teacher"},
    )
    assert response.get_json(force=True)["code"] == 0
    assert response.get_json(force=True)["data"] == {"status": "saved"}
    assert service.call_args.args == (
        admin_billing_client["app"],
        "target-teacher" if admin else "signed-in-teacher",
        *expected_tail,
    )
    assert service.call_args.kwargs == (
        {"allow_when_customization_disabled": True}
        if admin and handler == "save_creator_integration"
        else {}
    )


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("missing_file", [False, True])
def test_brand_logo_upload_validates_multipart_and_forwards_selected_target(
    admin: bool,
    missing_file: bool,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock(return_value={"url": "https://assets.example.test/logo.png"})
    monkeypatch.setattr(routes, "upload_creator_brand_logo", service)
    monkeypatch.setattr(routes, "is_creator_customization_enabled", lambda: True)
    monkeypatch.setattr(
        routes,
        "_resolve_existing_admin_billing_target_user_bid",
        lambda **kwargs: kwargs["creator_bid"],
    )
    prefix = (
        "/api/admin/billing/customization/target-teacher"
        if admin
        else "/api/billing/customization"
    )
    response = admin_billing_client["client"].post(
        prefix + "/branding/logo",
        data={}
        if missing_file
        else {"file": (BytesIO(b"image"), "logo.png"), "target": "square"},
        content_type="multipart/form-data",
    )
    if missing_file:
        assert response.get_json(force=True)["code"] != 0
        service.assert_not_called()
    else:
        assert response.get_json(force=True)["code"] == 0
        assert service.call_args.args[2].filename == "logo.png"
        assert service.call_args.kwargs["target"] == "square"
        assert (
            service.call_args.kwargs.get("allow_when_customization_disabled", False)
            is admin
        )


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("PUT", "/branding"),
        ("POST", "/branding/logo"),
        ("POST", "/domains"),
        ("POST", "/domains/id/verify"),
        ("DELETE", "/domains/id"),
        ("PUT", "/integrations/wechat"),
        ("POST", "/integrations/wechat/verify"),
        ("DELETE", "/integrations/wechat"),
    ],
)
def test_creator_customization_feature_gate_blocks_all_mutation_routes(
    method: str,
    suffix: str,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "is_creator_customization_enabled", lambda: False)
    handlers = [
        "save_creator_branding",
        "upload_creator_brand_logo",
        "manage_creator_domain_binding",
        "save_creator_integration",
        "verify_creator_integration",
        "disable_creator_integration",
    ]
    calls = []
    for handler in handlers:
        callback = Mock()
        monkeypatch.setattr(routes, handler, callback)
        calls.append(callback)
    response = admin_billing_client["client"].open(
        "/api/billing/customization" + suffix, method=method, json={}
    )
    assert response.get_json(force=True)["code"] != 0
    assert all(not callback.called for callback in calls)


_DISCOUNT_OPERATIONS = [
    (
        "campaigns/campaign-test/publish",
        "publish_admin_campaign_provider_discounts",
        "campaign_bid",
        "campaign-test",
    ),
    (
        "campaigns/campaign-test/publish/retry",
        "publish_admin_campaign_provider_discounts",
        "campaign_bid",
        "campaign-test",
    ),
    (
        "campaigns/campaign-test/retire",
        "retire_admin_campaign_provider_discounts",
        "campaign_bid",
        "campaign-test",
    ),
    (
        "campaign-provider-discounts/discount-test/validate",
        "validate_admin_campaign_provider_discount",
        "campaign_provider_discount_bid",
        "discount-test",
    ),
]


@pytest.mark.parametrize(
    ("path", "handler", "identity_key", "identity"), _DISCOUNT_OPERATIONS
)
@pytest.mark.parametrize("failure", [None, "campaign", "price", "unexpected"])
def test_campaign_provider_routes_preserve_operator_identity_and_structured_errors(
    path: str,
    handler: str,
    identity_key: str,
    identity: str,
    failure: str | None,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock(return_value={"status": "verified"})
    if failure == "campaign":
        service.side_effect = CampaignProviderDiscountError(
            "provider_invalid",
            "Coupon is inactive",
            {"provider_coupon_id": "coupon-test"},
        )
    elif failure == "price":
        service.side_effect = ProviderPriceMappingError(
            "mapping_missing", "Price is missing"
        )
    elif failure == "unexpected":
        service.side_effect = RuntimeError("programming failure")
    monkeypatch.setattr(routes, handler, service)
    client = admin_billing_client["client"]
    if failure == "unexpected":
        with pytest.raises(RuntimeError, match="programming failure"):
            client.post("/api/admin/billing/" + path)
    else:
        response = client.post("/api/admin/billing/" + path)
        assert response.get_json(force=True)["code"] == (9999 if failure else 0)
        if failure:
            key = (
                "campaign_provider_discount_error"
                if failure == "campaign"
                else "provider_price_mapping_error"
            )
            assert response.get_json(force=True)[key]["code"] == (
                "provider_invalid" if failure == "campaign" else "mapping_missing"
            )
            if failure == "campaign":
                assert response.get_json(force=True)[key]["details"] == {
                    "provider_coupon_id": "coupon-test"
                }
        else:
            assert response.get_json(force=True)["data"] == {"status": "verified"}
    assert service.call_args.kwargs == {
        identity_key: identity,
        "operator_user_bid": "admin-creator",
    }


@pytest.mark.parametrize(
    ("path", "handler", "identity_key", "identity"), _DISCOUNT_OPERATIONS
)
def test_campaign_provider_routes_reject_non_operator_before_service(
    path: str,
    handler: str,
    identity_key: str,
    identity: str,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del identity_key, identity
    service = Mock()
    monkeypatch.setattr(routes, handler, service)
    response = admin_billing_client["client"].post(
        "/api/admin/billing/" + path, headers={"X-Operator": "0"}
    )
    assert response.get_json(force=True)["code"] != 0
    service.assert_not_called()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" ", None), ("off", False), ("YES", True), ("invalid", "error")],
)
def test_provider_list_query_boolean_contract(
    value: str,
    expected: object,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock(return_value={"items": []})
    monkeypatch.setattr(routes, "build_admin_billing_provider_prices_page", service)
    response = admin_billing_client["client"].get(
        "/api/admin/billing/provider-prices", query_string={"livemode": value}
    )
    if expected == "error":
        assert response.get_json(force=True)["code"] != 0
        service.assert_not_called()
    else:
        assert response.get_json(force=True)["code"] == 0
        assert service.call_args.kwargs["livemode"] is expected


@pytest.mark.parametrize(
    "query", [{"product_bid": "x" * 101}, {"provider_account_id": "x" * 256}]
)
def test_provider_list_rejects_oversized_identity_before_query(
    query: dict,
    admin_billing_client: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    monkeypatch.setattr(routes, "build_admin_billing_provider_prices_page", service)
    response = admin_billing_client["client"].get(
        "/api/admin/billing/provider-prices", query_string=query
    )
    assert response.get_json(force=True)["code"] != 0
    service.assert_not_called()
