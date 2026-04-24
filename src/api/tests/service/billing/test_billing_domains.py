from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.common.shifu_context import get_shifu_creator_bid, with_shifu_context
from flaskr.service.billing.consts import (
    BILLING_DOMAIN_BINDING_STATUS_DISABLED,
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
    CREDIT_SOURCE_TYPE_MANUAL,
)
from flaskr.service.billing.domains import (
    verify_domain_binding,
)
from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement
from flaskr.service.common.models import AppException
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

billing_routes_module = load_billing_routes_module()
register_billing_routes = load_register_billing_routes()


@pytest.fixture
def billing_domain_client(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )

    dao.db.init_app(app)

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-1"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    @app.route("/_domain-context", methods=["GET"])
    @with_shifu_context()
    def _domain_context():
        return jsonify({"creator_bid": get_shifu_creator_bid()})

    monkeypatch.setattr(
        billing_routes_module,
        "is_billing_enabled",
        lambda: True,
    )

    register_billing_routes(app=app)

    now = datetime(2026, 4, 8, 12, 0, 0)
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(
            [
                BillingEntitlement(
                    entitlement_bid="ent-domain-1",
                    creator_bid="creator-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-1",
                    branding_enabled=1,
                    custom_domain_enabled=1,
                    priority_class=7702,
                    analytics_tier=7712,
                    support_tier=7722,
                    effective_from=now - timedelta(days=3),
                    effective_to=None,
                ),
                BillingEntitlement(
                    entitlement_bid="ent-domain-2",
                    creator_bid="creator-2",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-2",
                    branding_enabled=0,
                    custom_domain_enabled=0,
                    priority_class=7701,
                    analytics_tier=7711,
                    support_tier=7721,
                    effective_from=now - timedelta(days=3),
                    effective_to=None,
                ),
                BillingEntitlement(
                    entitlement_bid="ent-domain-3",
                    creator_bid="creator-3",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-3",
                    branding_enabled=1,
                    custom_domain_enabled=1,
                    priority_class=7702,
                    analytics_tier=7712,
                    support_tier=7722,
                    effective_from=now - timedelta(days=3),
                    effective_to=None,
                ),
                BillingDomainBinding(
                    domain_binding_bid="binding-verified-1",
                    creator_bid="creator-1",
                    host="academy.example.com",
                    status=BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
                    verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                    verification_token="token-academy",
                    last_verified_at=now - timedelta(hours=2),
                ),
                BillingDomainBinding(
                    domain_binding_bid="binding-disabled-1",
                    creator_bid="creator-1",
                    host="disabled.example.com",
                    status=BILLING_DOMAIN_BINDING_STATUS_DISABLED,
                    verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                    verification_token="token-disabled",
                ),
            ]
        )
        dao.db.session.commit()

        with app.test_client() as client:
            yield {"app": app, "client": client}

        dao.db.session.remove()
        dao.db.drop_all()


class TestBillingDomains:
    def test_admin_billing_domain_audits_lists_existing_bindings(
        self, billing_domain_client
    ) -> None:
        client = billing_domain_client["client"]

        audit_response = client.get(
            "/api/admin/billing/domain-audits?page_index=1&page_size=10"
        )
        audit_payload = audit_response.get_json(force=True)

        assert audit_payload["code"] == 0
        assert audit_payload["data"]["total"] == 2
        assert audit_payload["data"]["items"][0]["host"] == "academy.example.com"
        assert audit_payload["data"]["items"][0]["status"] == "verified"
        assert audit_payload["data"]["items"][0]["creator_bid"] == "creator-1"
        assert audit_payload["data"]["items"][0]["custom_domain_enabled"] is True
        assert audit_payload["data"]["items"][1]["host"] == "disabled.example.com"
        assert audit_payload["data"]["items"][1]["status"] == "disabled"

    def test_with_shifu_context_resolves_creator_from_custom_domain_host(
        self, billing_domain_client
    ) -> None:
        client = billing_domain_client["client"]

        direct_response = client.get(
            "/_domain-context",
            headers={"Host": "academy.example.com"},
        )
        forwarded_response = client.get(
            "/_domain-context",
            headers={
                "Host": "localhost",
                "X-Forwarded-Host": "ACADEMY.EXAMPLE.COM:443",
            },
        )
        disabled_response = client.get(
            "/_domain-context",
            headers={"Host": "disabled.example.com"},
        )

        assert direct_response.get_json(force=True)["creator_bid"] == "creator-1"
        assert forwarded_response.get_json(force=True)["creator_bid"] == "creator-1"
        assert disabled_response.get_json(force=True)["creator_bid"] is None

    def test_verify_domain_binding_helper_uses_existing_binding_token(
        self, billing_domain_client
    ) -> None:
        app = billing_domain_client["app"]

        with app.app_context():
            dao.db.session.add(
                BillingDomainBinding(
                    domain_binding_bid="binding-task-verify-1",
                    creator_bid="creator-1",
                    host="task-verify.example.com",
                    status=BILLING_DOMAIN_BINDING_STATUS_PENDING,
                    verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                    verification_token="token-task-verify-1",
                )
            )
            dao.db.session.commit()

            payload = verify_domain_binding(
                app,
                domain_binding_bid="binding-task-verify-1",
            )

            assert payload["action"] == "verify"
            assert payload["creator_bid"] == "creator-1"
            assert payload["binding"]["status"] == "verified"
            assert payload["binding"]["is_effective"] is True
