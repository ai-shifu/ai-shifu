from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ENTITLEMENT_ANALYTICS_TIER_ENTERPRISE,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY,
    BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP,
    BILLING_ENTITLEMENT_SUPPORT_TIER_PRIORITY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from flaskr.service.billing.models import (
    BillingEntitlement,
    BillingSubscription,
)
from tests.common.fixtures.billing_products import build_billing_products


@pytest.fixture
def billing_entitlement_app() -> Flask:
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
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_products_with_yearly_entitlements():
    return build_billing_products(
        overrides_by_bid={
            "billing-product-plan-yearly": {
                "entitlement_payload": {
                    "branding_enabled": True,
                    "custom_domain_enabled": False,
                    "priority_class": BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY,
                    "max_concurrency": "4",
                    "analytics_tier": "advanced",
                    "support_tier": "business_hours",
                    "feature_payload": {"report_export": True},
                }
            }
        }
    )


def test_resolve_creator_entitlement_state_prefers_latest_active_snapshot(
    billing_entitlement_app: Flask,
) -> None:
    now = datetime(2026, 4, 8, 12, 0, 0)
    with billing_entitlement_app.app_context():
        dao.db.session.add_all(_seed_products_with_yearly_entitlements())
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-snapshot-1",
                creator_bid="creator-snapshot-1",
                product_bid="billing-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=now - timedelta(days=7),
                current_period_end_at=now + timedelta(days=23),
            )
        )
        dao.db.session.add_all(
            [
                BillingEntitlement(
                    entitlement_bid="ent-old",
                    creator_bid="creator-snapshot-1",
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="sub-snapshot-1",
                    branding_enabled=0,
                    custom_domain_enabled=0,
                    priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY,
                    max_concurrency=2,
                    analytics_tier=7712,
                    support_tier=7722,
                    effective_from=now - timedelta(days=3),
                    effective_to=None,
                    created_at=now - timedelta(days=3),
                    updated_at=now - timedelta(days=3),
                ),
                BillingEntitlement(
                    entitlement_bid="ent-new",
                    creator_bid="creator-snapshot-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                    source_bid="manual-adjust-1",
                    branding_enabled=1,
                    custom_domain_enabled=1,
                    priority_class=BILLING_ENTITLEMENT_PRIORITY_CLASS_VIP,
                    max_concurrency=12,
                    analytics_tier=BILLING_ENTITLEMENT_ANALYTICS_TIER_ENTERPRISE,
                    support_tier=BILLING_ENTITLEMENT_SUPPORT_TIER_PRIORITY,
                    feature_payload={"priority_queue": True},
                    effective_from=now - timedelta(hours=1),
                    effective_to=None,
                    created_at=now - timedelta(hours=1),
                    updated_at=now - timedelta(hours=1),
                ),
            ]
        )
        dao.db.session.commit()

        state = resolve_creator_entitlement_state(
            "creator-snapshot-1",
            as_of=now,
        )

    assert state["source_kind"] == "snapshot"
    assert state["source_type"] == "manual"
    assert state["source_bid"] == "manual-adjust-1"
    assert state["feature_payload"] == {"priority_queue": True}
    assert serialize_creator_entitlements(state) == {
        "branding_enabled": True,
        "custom_domain_enabled": True,
        "priority_class": "vip",
        "max_concurrency": 12,
        "analytics_tier": "enterprise",
        "support_tier": "priority",
    }


def test_resolve_creator_entitlement_state_falls_back_to_product_payload_or_default(
    billing_entitlement_app: Flask,
) -> None:
    now = datetime(2026, 4, 8, 12, 0, 0)
    with billing_entitlement_app.app_context():
        dao.db.session.add_all(_seed_products_with_yearly_entitlements())
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-product-1",
                creator_bid="creator-product-1",
                product_bid="billing-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                current_period_start_at=now - timedelta(days=5),
                current_period_end_at=now + timedelta(days=25),
            )
        )
        dao.db.session.commit()

        product_state = resolve_creator_entitlement_state(
            "creator-product-1",
            as_of=now,
        )
        default_state = resolve_creator_entitlement_state(
            "creator-default-1",
            as_of=now,
        )

    assert product_state["source_kind"] == "product_payload"
    assert product_state["source_type"] == "subscription"
    assert product_state["source_bid"] == "sub-product-1"
    assert product_state["product_bid"] == "billing-product-plan-yearly"
    assert product_state["feature_payload"] == {"report_export": True}
    assert serialize_creator_entitlements(product_state) == {
        "branding_enabled": True,
        "custom_domain_enabled": False,
        "priority_class": "priority",
        "max_concurrency": 4,
        "analytics_tier": "advanced",
        "support_tier": "business_hours",
    }

    assert default_state["source_kind"] == "default"
    assert default_state["source_type"] is None
    assert default_state["feature_payload"] == {}
    assert serialize_creator_entitlements(default_state) == {
        "branding_enabled": False,
        "custom_domain_enabled": False,
        "priority_class": "standard",
        "max_concurrency": 1,
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }
