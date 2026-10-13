"""Protect read-only eligibility and prevent protocol logic returning to business."""

import ast
import inspect

import pytest
from flask import Flask
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import checkout, provider_state, webhooks
from flaskr.service.billing.consts import BILLING_ORDER_STATUS_PENDING
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.order import funs

from tests.service.billing.billing_write_routes_test_helpers import (
    add_active_subscription,
)
from tests.service.order.test_payment_contract_extension import (
    FixtureProvider,
    _notify,
    integration_app,
)

__all__ = ["integration_app"]


def test_catalog_operations_are_read_only_and_reuse_checkout_eligibility(
    integration_app: Flask,
) -> None:
    app = integration_app
    add_active_subscription(app)
    with unit_of_work():
        subscription = BillingSubscription.query.filter_by(
            creator_bid="creator-1"
        ).one()
        subscription.billing_provider = "fixture-pay"
        subscription.provider_subscription_id = ""
    with app.test_client() as client:
        before = BillingOrder.query.count()
        calls = list(FixtureProvider.calls)
        catalog = client.get("/api/billing/catalog").get_json(force=True)
        assert catalog.get("code") == 0, catalog
        operation = catalog["data"]["checkout_operations"]["bill-product-plan-monthly"]
        assert operation["action"] == "preorder"
        assert operation["available"]
        assert operation["option_ids"] == ["fixture-pay:fixture_qr"]
        assert BillingOrder.query.count() == before
        assert FixtureProvider.calls == calls
        created = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_option": operation["option_ids"][0],
                "action": operation["action"],
            },
        ).get_json(force=True)
        assert created.get("code") == 0, created
        assert (
            _notify(
                client, "fixture-pay", created["data"]["bill_order_bid"]
            ).status_code
            == 200
        )
        updated = client.get("/api/billing/catalog").get_json(force=True)["data"][
            "checkout_operations"
        ]["bill-product-plan-monthly"]
        assert not updated["available"]


@pytest.mark.parametrize(
    "consumer",
    [
        checkout._build_provider_checkout_request,
        checkout._sync_provider_order,
        provider_state.apply_subscription_contract,
        webhooks.apply_billing_provider_notification,
        funs._generate_charge_locked,
    ],
)
def test_business_consumers_do_not_branch_on_gateway_names_or_read_protocol_envelopes(
    consumer: object,
) -> None:
    tree = ast.parse(inspect.getsource(consumer))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            literals = {
                item.value
                for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            assert not literals.intersection(
                {"stripe", "pingxx", "alipay", "wechatpay"}
            ), inspect.getsource(consumer)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ):
            assert ast.unparse(node.func.value) not in {
                "notification.provider_payload",
                "result.provider_payload",
                "sync_result.provider_payload",
            }


def test_verified_notification_cannot_settle_an_order_owned_by_another_integration(
    integration_app: Flask,
) -> None:
    """A valid signature does not authorize changing another gateway's order."""
    app = integration_app
    add_active_subscription(app)
    with app.test_client() as client:
        created = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_option": "fixture-pay:fixture_qr",
            },
        ).get_json(force=True)
        assert created.get("code") == 0, created
        order_bid = created["data"]["bill_order_bid"]
        with unit_of_work():
            order = BillingOrder.query.filter_by(bill_order_bid=order_bid).one()
            order.payment_provider = "alipay"
        # A verified event without a matching owned attempt must remain retryable.
        response = _notify(client, "fixture-pay", order_bid)
        assert response.status_code == 400
        assert response.get_json(force=True)["code"] == "FAIL"
        assert (
            BillingOrder.query.filter_by(bill_order_bid=order_bid).one().status
            == BILLING_ORDER_STATUS_PENDING
        )
        assert CreditLedgerEntry.query.filter_by(source_bid=order_bid).count() == 0
