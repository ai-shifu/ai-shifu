from __future__ import annotations

from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

from flaskr.service.billing.routes import register_billing_routes
from flaskr.service.common.models import AppException


@pytest.fixture
def billing_test_client():
    app = Flask(__name__)
    app.testing = True

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id="creator-1",
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    register_billing_routes(app=app)

    with app.test_client() as client:
        yield client


class TestBillingRoutes:
    def test_billing_bootstrap_route_returns_design_manifest(
        self, billing_test_client
    ) -> None:
        response = billing_test_client.get("/api/billing")
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["service"] == "billing"
        assert payload["data"]["status"] == "bootstrap"
        assert payload["data"]["path_prefix"] == "/api/billing"
        assert {
            "method": "GET",
            "path": "/api/billing/catalog",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "POST",
            "path": "/api/billing/orders/{billing_order_bid}/sync",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/orders",
        } in payload["data"]["admin_routes"]

    def test_billing_bootstrap_route_requires_creator(
        self, billing_test_client
    ) -> None:
        response = billing_test_client.get(
            "/api/billing",
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] != 0
