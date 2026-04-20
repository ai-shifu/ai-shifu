from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_TRIAL_PRODUCT_BID,
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
from flaskr.service.billing.queries import (
    load_current_subscription,
    load_primary_active_subscription,
)
from flaskr.service.billing.models import (
    BillingEntitlement,
    BillingSubscription,
)
from tests.common.fixtures.bill_products import build_bill_products


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
    return build_bill_products(
        overrides_by_bid={
            "bill-product-plan-yearly": {
                "entitlement_payload": {
                    "branding_enabled": True,
                    "custom_domain_enabled": False,
                    "priority_class": BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY,
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
                product_bid="bill-product-plan-yearly",
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
                product_bid="bill-product-plan-yearly",
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
    assert product_state["product_bid"] == "bill-product-plan-yearly"
    assert product_state["feature_payload"] == {"report_export": True}
    assert serialize_creator_entitlements(product_state) == {
        "branding_enabled": True,
        "custom_domain_enabled": False,
        "priority_class": "priority",
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
        "analytics_tier": "basic",
        "support_tier": "self_serve",
    }


def test_primary_active_subscription_prefers_higher_sort_order_paid_plan_over_trial(
    billing_entitlement_app: Flask,
) -> None:
    now = datetime.now()
    with billing_entitlement_app.app_context():
        dao.db.session.add_all(build_bill_products())
        dao.db.session.add_all(
            [
                BillingSubscription(
                    subscription_bid="sub-trial-overlap",
                    creator_bid="creator-overlap-1",
                    product_bid=BILLING_TRIAL_PRODUCT_BID,
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=14),
                    created_at=now - timedelta(days=1),
                    updated_at=now - timedelta(days=1),
                ),
                BillingSubscription(
                    subscription_bid="sub-paid-overlap",
                    creator_bid="creator-overlap-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(hours=6),
                    current_period_end_at=now + timedelta(days=1),
                    created_at=now - timedelta(hours=6),
                    updated_at=now - timedelta(hours=6),
                ),
            ]
        )
        dao.db.session.commit()

        primary = load_primary_active_subscription(
            "creator-overlap-1",
            as_of=now,
        )
        current = load_current_subscription("creator-overlap-1")

    assert primary is not None
    assert primary.subscription_bid == "sub-paid-overlap"
    assert current is not None
    assert current.subscription_bid == "sub-paid-overlap"


def test_resolve_creator_entitlement_state_prefers_paid_plan_over_longer_trial(
    billing_entitlement_app: Flask,
) -> None:
    now = datetime(2026, 4, 8, 12, 0, 0)
    with billing_entitlement_app.app_context():
        dao.db.session.add_all(
            build_bill_products(
                overrides_by_bid={
                    BILLING_TRIAL_PRODUCT_BID: {
                        "entitlement_payload": {
                            "priority_class": "standard",
                            "analytics_tier": "basic",
                            "support_tier": "self_serve",
                        }
                    },
                    "bill-product-plan-monthly": {
                        "entitlement_payload": {
                            "branding_enabled": True,
                            "priority_class": BILLING_ENTITLEMENT_PRIORITY_CLASS_PRIORITY,
                            "analytics_tier": "advanced",
                            "support_tier": "business_hours",
                            "feature_payload": {"paid_plan": True},
                        }
                    },
                }
            )
        )
        dao.db.session.add_all(
            [
                BillingSubscription(
                    subscription_bid="sub-trial-entitlement",
                    creator_bid="creator-overlap-2",
                    product_bid=BILLING_TRIAL_PRODUCT_BID,
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=14),
                    created_at=now - timedelta(days=1),
                    updated_at=now - timedelta(days=1),
                ),
                BillingSubscription(
                    subscription_bid="sub-paid-entitlement",
                    creator_bid="creator-overlap-2",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    current_period_start_at=now - timedelta(hours=6),
                    current_period_end_at=now + timedelta(days=1),
                    created_at=now - timedelta(hours=6),
                    updated_at=now - timedelta(hours=6),
                ),
            ]
        )
        dao.db.session.commit()

        state = resolve_creator_entitlement_state(
            "creator-overlap-2",
            as_of=now,
        )

    assert state["source_kind"] == "product_payload"
    assert state["source_bid"] == "sub-paid-entitlement"
    assert state["product_bid"] == "bill-product-plan-monthly"
    assert state["feature_payload"] == {"paid_plan": True}
